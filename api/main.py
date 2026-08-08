# api/main.py
import sys
import os
import types
import warnings

# ── PyTorch kernel conflict patch ─────────────────────────────────────────────
# When FastAPI loads multiple torch-based models in the same process,
# PyTorch throws a kernel registration conflict. This suppresses it safely.
warnings.filterwarnings("ignore", message=".*already a kernel registered.*")
warnings.filterwarnings("ignore", message=".*_c10d_functional.*")
warnings.filterwarnings("ignore", message=".*wait_tensor.*")

# ── k2 dummy patch (same fix as diarize.py) ───────────────────────────────────
if "k2" not in sys.modules:
    sys.modules["k2"] = types.ModuleType("k2")

# ── TorchCodec patch ──────────────────────────────────────────────────────────
os.environ["TORCHAUDIO_USE_SOX"] = "0"

import sys
import os
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import shutil
from pathlib import Path
from datetime import datetime

app = FastAPI(title="Meeting AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Track background job status
job_status = {}


def make_job_id():
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


# ── DASHBOARD ─────────────────────────────────────────────────────────────────

@app.get("/api/dashboard")
def get_dashboard():
    from src.database import get_connection
    conn = get_connection()

    speakers     = conn.execute("SELECT COUNT(*) AS c FROM speakers").fetchone()["c"]
    meetings     = conn.execute("SELECT COUNT(*) AS c FROM meetings").fetchone()["c"]
    segments     = conn.execute("SELECT COUNT(*) AS c FROM segments").fetchone()["c"]
    unknowns     = conn.execute(
        "SELECT COUNT(*) AS c FROM segments WHERE speaker_id IS NULL"
    ).fetchone()["c"]
    recent_meetings = conn.execute("""
        SELECT id, filename, processed_at, num_speakers, duration_sec, report_path
        FROM meetings ORDER BY id DESC LIMIT 5
    """).fetchall()

    conn.close()

    return {
        "stats": {
            "total_speakers": speakers,
            "total_meetings": meetings,
            "total_segments": segments,
            "unknown_segments": unknowns,
        },
        "recent_meetings": [dict(r) for r in recent_meetings],
    }


# ── SPEAKERS ──────────────────────────────────────────────────────────────────

@app.get("/api/speakers")
def get_speakers():
    from src.database import get_connection
    conn = get_connection()
    rows = conn.execute("""
        SELECT s.id, s.name, s.enrolled_at, s.num_samples,
               COUNT(vs.id) AS sample_files
        FROM speakers s
        LEFT JOIN voice_samples vs ON vs.speaker_id = s.id
        GROUP BY s.id
        ORDER BY s.name
    """).fetchall()
    conn.close()
    return {"speakers": [dict(r) for r in rows]}


@app.post("/api/speakers/enroll")
async def enroll_speaker(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    files: list[UploadFile] = File(...),
):
    job_id   = make_job_id()
    save_dir = Path(f"voice_samples/{name}")
    save_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded files
    saved_paths = []
    for f in files:
        dest = save_dir / f.filename
        with open(dest, "wb") as out:
            shutil.copyfileobj(f.file, out)
        saved_paths.append(str(dest))

    job_status[job_id] = {
        "status":  "running",
        "message": f"Enrolling {name}...",
    }

    def do_enroll():
        try:
            # ── Only enroll THIS speaker, not everyone ──
            from src.enroll_speakers import enroll_single_speaker
            enroll_single_speaker(speaker_name=name)

            job_status[job_id] = {
                "status":  "done",
                "message": f"'{name}' enrolled successfully with {len(saved_paths)} sample(s).",
            }
        except Exception as e:
            import traceback
            job_status[job_id] = {
                "status":  "error",
                "message": str(e),
                "detail":  traceback.format_exc(),
            }

    background_tasks.add_task(do_enroll)
    return {"job_id": job_id, "message": f"Enrolling {name}..."}

# ── MEETINGS ──────────────────────────────────────────────────────────────────

@app.get("/api/meetings")
def get_meetings():
    from src.database import get_connection
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, filename, processed_at, num_speakers,
               duration_sec, report_path, summary_path
        FROM meetings ORDER BY id DESC
    """).fetchall()
    conn.close()
    return {"meetings": [dict(r) for r in rows]}


@app.post("/api/meetings/upload")
async def upload_meeting(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    job_id    = make_job_id()
    input_dir = Path("audio/input")
    input_dir.mkdir(parents=True, exist_ok=True)
    dest      = input_dir / file.filename

    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)

    job_status[job_id] = {
        "status":  "running",
        "message": "Starting pipeline...",
        "step":    1,
        "total":   6,
    }

    def do_process():
        try:
            import torch
            torch.set_num_threads(1)

            from src.audio_preprocess import convert_to_wav
            from src.transcribe import transcribe_audio
            from src.diarize import diarize_audio
            from src.align_speakers import (
                build_speaker_transcript,
                merge_consecutive_speaker_lines,
                format_speaker_transcript,
            )
            from src.database import (
                init_db, insert_meeting, insert_segment,
                get_raw_segments_for_meeting,
                update_segment_speaker,
                get_speaker_id_by_name,
                update_meeting_report_path,
                get_segments_for_meeting,
                get_meeting_by_id,
            )
            from src.file_utils import save_text, save_json

            processed = "audio/processed/output.wav"
            init_db()

            # ── Step 1: Convert audio ─────────────────────────────
            job_status[job_id].update({
                "message": "Step 1/6 — Converting audio to WAV...",
                "step": 1,
            })
            convert_to_wav(str(dest), processed)

            # ── Step 2: Transcribe ────────────────────────────────
            job_status[job_id].update({
                "message": "Step 2/6 — Transcribing audio (Whisper)...",
                "step": 2,
            })
            transcript_segments, transcript_text = transcribe_audio(processed)

            meeting_id = insert_meeting(
                filename=file.filename,
                duration_sec=(
                    transcript_segments[-1]["end"]
                    if transcript_segments else 0
                ),
            )

            # ── Step 3: Diarize ───────────────────────────────────
            job_status[job_id].update({
                "message": "Step 3/6 — Detecting speakers (pyannote)...",
                "step": 3,
            })
            speaker_segments = diarize_audio(processed)

            for seg in speaker_segments:
                matched_text = " ".join(
                    t["text"] for t in transcript_segments
                    if t["start"] >= seg["start"] - 0.5
                    and t["end"]   <= seg["end"]   + 0.5
                ).strip()
                insert_segment(
                    meeting_id=meeting_id,
                    speaker_label=seg["speaker"],
                    start_time=seg["start"],
                    end_time=seg["end"],
                    transcript_text=matched_text,
                )

            report_dir = Path(f"outputs/transcripts/meeting_{meeting_id}")
            report_dir.mkdir(parents=True, exist_ok=True)
            save_json(speaker_segments,    str(report_dir / "speaker_segments.json"))
            save_json(transcript_segments, str(report_dir / "transcript_segments.json"))

            speaker_transcript = build_speaker_transcript(
                transcript_segments, speaker_segments
            )
            merged   = merge_consecutive_speaker_lines(speaker_transcript)
            detailed = format_speaker_transcript(merged)
            save_text(detailed,        str(report_dir / "speaker_transcript_detailed.txt"))
            save_text(transcript_text, str(report_dir / "sample_transcript.txt"))

            # ── Step 4: Recognize speakers ────────────────────────
            job_status[job_id].update({
                "message": "Step 4/6 — Identifying speakers (ECAPA)...",
                "step": 4,
            })
            from src.recognize_speakers import recognize_diarized_speakers

            raw_segments          = get_raw_segments_for_meeting(meeting_id)
            speaker_label_to_name = recognize_diarized_speakers(
                processed, raw_segments
            )

            for seg in raw_segments:
                label  = seg["speaker"]
                result = speaker_label_to_name.get(label)
                if not result:
                    continue
                speaker_id = None
                if result["name"] != "UNKNOWN":
                    speaker_id = get_speaker_id_by_name(result["name"])
                update_segment_speaker(
                    segment_id=seg["id"],
                    speaker_id=speaker_id,
                    confidence=result["confidence"],
                    margin=result["margin"],
                    tier=result["tier"],
                )

            save_json(
                speaker_label_to_name,
                str(report_dir / "speaker_mapping.json")
            )

            # ── Step 5: Build final named transcript ──────────────
            job_status[job_id].update({
                "message": "Step 5/6 — Building named transcript...",
                "step": 5,
            })
            segments = get_segments_for_meeting(meeting_id)
            meeting  = get_meeting_by_id(meeting_id)

            def fmt_ts(s):
                s = int(s)
                return (
                    f"{s//3600:02d}:"
                    f"{(s%3600)//60:02d}:"
                    f"{s%60:02d}"
                )

            lines = []
            for seg in segments:
                name  = seg["speaker_name"]
                conf  = seg["confidence"]
                if name:
                    display = f"{name} ({conf})"
                elif conf and conf >= 0.50:
                    display = f"UNKNOWN (conf: {conf})"
                else:
                    display = f"UNKNOWN (conf: {conf})" if conf else "UNKNOWN"
                lines.append(
                    f"[{fmt_ts(seg['start_time'])}] "
                    f"{display}: {seg['transcript_text']}"
                )

            # Speaker summary
            seen = {}
            for seg in segments:
                n = seg["speaker_name"] or "UNKNOWN"
                if n not in seen:
                    seen[n] = seg

            summary_lines = [
                "", "="*60,
                "  SPEAKER SUMMARY",
                "="*60,
            ]
            for n, seg in seen.items():
                summary_lines.append(
                    f"  {n}"
                    f"  |  confidence: {seg['confidence']}"
                    f"  |  tier: {seg['tier']}"
                )

            full_report = (
                "="*60 + "\n"
                f"  MEETING REPORT — {meeting['filename']}\n"
                f"  Meeting ID    : {meeting_id}\n"
                f"  Speakers found: {len(seen)}\n"
                + "="*60 + "\n"
                + "\n".join(lines) + "\n"
                + "\n".join(summary_lines) + "\n"
            )

            report_path = str(report_dir / "named_transcript.txt")
            save_text(full_report, report_path)
            update_meeting_report_path(
                meeting_id=meeting_id,
                report_path=report_path,
                num_speakers=len(seen),
            )

            # ── Step 6: Done ──────────────────────────────────────
            job_status[job_id].update({
                "message": "Step 6/6 — Done! Named transcript ready.",
                "step": 6,
            })

            job_status[job_id] = {
                "status":       "done",
                "message":      "Meeting processed successfully.",
                "meeting_id":   meeting_id,
                "num_speakers": len(seen),
                "speakers":     list(seen.keys()),
                "step":         6,
                "total":        6,
            }

        except Exception as e:
            import traceback
            job_status[job_id] = {
                "status":  "error",
                "message": str(e),
                "detail":  traceback.format_exc(),
                "step":    job_status[job_id].get("step", 0),
                "total":   6,
            }

    background_tasks.add_task(do_process)
    return {"job_id": job_id, "message": "Processing started"}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    return job_status.get(job_id, {"status": "not_found"})


# ── TRANSCRIPTS ───────────────────────────────────────────────────────────────

@app.get("/api/meetings/{meeting_id}/transcript")
def get_transcript(meeting_id: int):
    from src.database import get_segments_for_meeting, get_meeting_by_id
    try:
        meeting  = get_meeting_by_id(meeting_id)
        segments = get_segments_for_meeting(meeting_id)
        return {"meeting": dict(meeting), "segments": segments}
    except Exception as e:
        return JSONResponse(status_code=404, content={"error": str(e)})


@app.get("/api/meetings/{meeting_id}/summary")
def get_summary(meeting_id: int):
    from src.database import get_connection
    conn = get_connection()
    row  = conn.execute(
        "SELECT summary_text FROM meetings WHERE id = ?", (meeting_id,)
    ).fetchone()
    conn.close()
    if not row or not row["summary_text"]:
        return JSONResponse(
            status_code=404,
            content={"error": "No summary yet. Run summarize mode first."}
        )
    return {"summary": row["summary_text"]}


@app.post("/api/meetings/{meeting_id}/summarize")
async def summarize_meeting(meeting_id: int, background_tasks: BackgroundTasks):
    job_id = make_job_id()
    job_status[job_id] = {"status": "running", "message": "Generating summary..."}

    def do_summarize():
        try:
            from src.summarize import run_summarize
            run_summarize(meeting_id=meeting_id)
            job_status[job_id] = {
                "status": "done",
                "message": "Summary generated.",
                "meeting_id": meeting_id,
            }
        except Exception as e:
            job_status[job_id] = {"status": "error", "message": str(e)}

    background_tasks.add_task(do_summarize)
    return {"job_id": job_id}


# ── CHAT ──────────────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat(payload: dict):
    question = payload.get("question", "").strip()
    history  = payload.get("history", [])

    if not question:
        return JSONResponse(
            status_code=400,
            content={"error": "Empty question"}
        )

    try:
        import ollama as ollama_client
        # Test Ollama connection first
        try:
            ollama_client.list()
        except Exception:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Ollama is not running. "
                             "Please start it from your system tray "
                             "or run 'ollama serve' in a terminal."
                }
            )
        from src.database import get_connection

        # ── Smart context builder inline ──────────────────────────
        import re
        conn    = get_connection()
        q_lower = question.lower()

        # Get all meetings overview
        meetings_rows = conn.execute("""
            SELECT id, filename, processed_at, num_speakers
            FROM meetings ORDER BY id
        """).fetchall()

        meetings_text = "MEETINGS IN DATABASE:\n"
        if meetings_rows:
            for r in meetings_rows:
                meetings_text += (
                    f"  Meeting #{r['id']}: {r['filename']} | "
                    f"processed: {str(r['processed_at'])[:10]} | "
                    f"speakers: {r['num_speakers']}\n"
                )
        else:
            meetings_text += "  No meetings yet.\n"

        # Get all speakers
        speakers_rows = conn.execute(
            "SELECT name, num_samples FROM speakers ORDER BY name"
        ).fetchall()

        speakers_text = "ENROLLED SPEAKERS:\n"
        if speakers_rows:
            for r in speakers_rows:
                speakers_text += f"  {r['name']} ({r['num_samples']} samples)\n"
        else:
            speakers_text += "  No speakers enrolled.\n"

        context_parts = [meetings_text, speakers_text]

        # Simple questions — metadata only
        simple_keywords = [
            "how many", "who is", "who are", "list",
            "show me", "what meetings", "count", "enrolled",
            "which meeting", "when was"
        ]
        is_simple = any(k in q_lower for k in simple_keywords)

        if not is_simple:
            # Check for speaker name mentions
            enrolled_names = [r["name"].lower() for r in speakers_rows]
            mentioned = [
                r["name"] for r in speakers_rows
                if r["name"].lower() in q_lower
            ]

            # Check for meeting ID
            meeting_ids = re.findall(r'meeting\s*#?(\d+)', q_lower)

            # Action items
            if any(w in q_lower for w in ["action", "task", "follow", "todo"]):
                summary_rows = conn.execute("""
                    SELECT id, filename, summary_text
                    FROM meetings WHERE summary_text IS NOT NULL
                """).fetchall()
                for r in summary_rows:
                    if r["summary_text"] and "ACTION ITEMS" in r["summary_text"]:
                        start = r["summary_text"].index("ACTION ITEMS")
                        end   = r["summary_text"].find("\n\n", start + 100)
                        chunk = r["summary_text"][start:end] if end != -1 else r["summary_text"][start:]
                        context_parts.append(
                            f"Meeting #{r['id']} ({r['filename']}) — {chunk.strip()}"
                        )

            elif mentioned:
                # Load segments for mentioned speakers
                for name in mentioned:
                    segs = conn.execute("""
                        SELECT
                            seg.start_time,
                            meet.filename,
                            meet.id AS meeting_id,
                            seg.transcript_text
                        FROM segments seg
                        JOIN speakers spk  ON seg.speaker_id = spk.id
                        JOIN meetings meet ON seg.meeting_id = meet.id
                        WHERE LOWER(spk.name) = LOWER(?)
                        ORDER BY meet.id, seg.start_time
                    """, (name,)).fetchall()

                    if segs:
                        block = f"ALL SEGMENTS BY {name.upper()}:\n"
                        for s in segs:
                            ts = int(s["start_time"])
                            ts_str = f"{ts//3600:02d}:{(ts%3600)//60:02d}:{ts%60:02d}"
                            block += (
                                f"  [Meeting #{s['meeting_id']} "
                                f"— {s['filename']} @ {ts_str}] "
                                f"{s['transcript_text']}\n"
                            )
                        context_parts.append(block)

            elif meeting_ids:
                # Load specific meeting transcript
                for mid in meeting_ids:
                    segs = conn.execute("""
                        SELECT
                            seg.start_time,
                            spk.name AS speaker_name,
                            seg.transcript_text
                        FROM segments seg
                        LEFT JOIN speakers spk ON seg.speaker_id = spk.id
                        WHERE seg.meeting_id = ?
                        ORDER BY seg.start_time
                    """, (int(mid),)).fetchall()

                    if segs:
                        block = f"TRANSCRIPT — Meeting #{mid}:\n"
                        for s in segs:
                            ts  = int(s["start_time"])
                            ts_str = f"{ts//3600:02d}:{(ts%3600)//60:02d}:{ts%60:02d}"
                            name = s["speaker_name"] or "UNKNOWN"
                            block += f"  [{ts_str}] {name}: {s['transcript_text']}\n"
                        context_parts.append(block)

            else:
                # Keyword search + latest meeting transcript
                skip = {
                    "what","who","when","where","how","did","the",
                    "about","meeting","say","said","tell","show",
                    "give","list","find","all","any","this","that"
                }
                words   = re.findall(r'\b[a-z]{4,}\b', q_lower)
                keywords = [w for w in words if w not in skip]

                found = False
                for kw in keywords[:2]:
                    segs = conn.execute("""
                        SELECT
                            seg.start_time,
                            spk.name AS speaker_name,
                            meet.filename,
                            meet.id AS meeting_id,
                            seg.transcript_text
                        FROM segments seg
                        LEFT JOIN speakers spk  ON seg.speaker_id = spk.id
                        LEFT JOIN meetings meet ON seg.meeting_id = meet.id
                        WHERE LOWER(seg.transcript_text) LIKE LOWER(?)
                        ORDER BY meet.id, seg.start_time
                        LIMIT 20
                    """, (f"%{kw}%",)).fetchall()

                    if segs:
                        block = f"SEGMENTS CONTAINING '{kw.upper()}':\n"
                        for s in segs:
                            ts  = int(s["start_time"])
                            ts_str = f"{ts//3600:02d}:{(ts%3600)//60:02d}:{ts%60:02d}"
                            nm  = s["speaker_name"] or "UNKNOWN"
                            block += (
                                f"  [Meeting #{s['meeting_id']} @ {ts_str}] "
                                f"{nm}: {s['transcript_text']}\n"
                            )
                        context_parts.append(block)
                        found = True

                # Fallback — load latest meeting
                if not found:
                    latest = conn.execute(
                        "SELECT MAX(id) AS id FROM meetings"
                    ).fetchone()
                    if latest and latest["id"]:
                        segs = conn.execute("""
                            SELECT
                                seg.start_time,
                                spk.name AS speaker_name,
                                seg.transcript_text
                            FROM segments seg
                            LEFT JOIN speakers spk ON seg.speaker_id = spk.id
                            WHERE seg.meeting_id = ?
                            ORDER BY seg.start_time
                            LIMIT 50
                        """, (latest["id"],)).fetchall()

                        if segs:
                            block = f"LATEST MEETING TRANSCRIPT:\n"
                            total = 0
                            for s in segs:
                                ts  = int(s["start_time"])
                                ts_str = f"{ts//3600:02d}:{(ts%3600)//60:02d}:{ts%60:02d}"
                                nm  = s["speaker_name"] or "UNKNOWN"
                                line = f"  [{ts_str}] {nm}: {s['transcript_text']}\n"
                                if total + len(line) > 3000:
                                    break
                                block += line
                                total += len(line)
                            context_parts.append(block)

        conn.close()

        context = "\n\n".join(context_parts)

        # Pick model based on question complexity
        simple_check = any(k in q_lower for k in simple_keywords)
        model = "llama3.2:3b" 

        # Build messages
        system_prompt = """You are a meeting intelligence assistant.
You have access to real data from recorded office meetings.
Answer questions based ONLY on the meeting data provided.
Be specific — mention speaker names and timestamps when relevant.
If the data does not contain the answer, say so clearly.
Never make up information."""

        recent_history = history[-8:] if history else []

        messages = (
            [{"role": "system", "content": system_prompt}]
            + recent_history
            + [{
                "role": "user",
                "content": (
                    f"Meeting data:\n\n{context}\n\n"
                    f"---\nQuestion: {question}"
                ),
            }]
        )

        # Call Ollama
        response = ollama_client.chat(
            model=model,
            messages=messages,
        )
        answer = response["message"]["content"].strip()

        return {
            "answer": answer,
            "model":  model,
        }

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"Chat error: {tb}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "detail": tb}
        )