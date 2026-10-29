# api/main.py
import sys
import os
import types
import warnings
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


# Load the ignored project-root .env explicitly for backend-only configuration.
# No environment values are exposed to the frontend or logged here.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


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

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.database import (
    create_job,
    fail_incomplete_jobs,
    get_job,
    init_db,
    update_job,
)
from src.jobs import submit_job
from src.meeting_actions import init_actions
from src.storage import remove_job_directory, safe_name, save_audio_upload
from api.meeting_actions import router as meeting_actions_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    init_actions()
    fail_incomplete_jobs()
    yield


app = FastAPI(title="Meeting AI API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meeting_actions_router)

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
    name: str = Form(...),
    files: list[UploadFile] = File(...),
):
    display_name = name.strip()
    if not display_name:
        return JSONResponse(status_code=400, content={"error": "Speaker name is required"})
    if not files:
        return JSONResponse(status_code=400, content={"error": "At least one sample is required"})

    job_id = make_job_id()
    save_dir = Path("voice_samples") / safe_name(display_name, "speaker")
    saved_paths = []
    try:
        for upload in files:
            destination, _ = save_audio_upload(upload, save_dir)
            saved_paths.append(str(destination))
    except ValueError as exc:
        for saved_path in saved_paths:
            Path(saved_path).unlink(missing_ok=True)
        return JSONResponse(status_code=400, content={"error": str(exc)})

    create_job(job_id, "speaker_enrollment", f"Enrolling {display_name}...")

    def do_enroll():
        try:
            # ── Only enroll THIS speaker, not everyone ──
            from src.enroll_speakers import enroll_single_speaker
            enroll_single_speaker(display_name, sample_paths=saved_paths)

            update_job(
                job_id,
                status="done",
                message=f"'{display_name}' enrolled successfully with {len(saved_paths)} sample(s).",
                result={"speaker_name": display_name, "sample_count": len(saved_paths)},
            )
        except Exception as e:
            import traceback
            update_job(
                job_id,
                status="error",
                message=str(e),
                error_detail=traceback.format_exc(),
            )

    submit_job(job_id, do_enroll)
    return {"job_id": job_id, "message": f"Enrolling {display_name}..."}

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
    file: UploadFile = File(...),
):
    job_id = make_job_id()
    job_dir = Path("runtime/jobs") / job_id
    try:
        dest, original_filename = save_audio_upload(file, job_dir / "input")
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    processed = job_dir / "processed.wav"
    create_job(job_id, "meeting_processing", "Waiting to process meeting...", total=6)

    def do_process():
        try:
            import torch
            torch.set_num_threads(1)

            from src.audio_preprocess import convert_to_wav
            from src.transcribe import transcribe_audio
            from src.diarize import diarize_audio
            from src.align_speakers import (
                align_transcript_segments,
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

            init_db()

            # ── Step 1: Convert audio ─────────────────────────────
            update_job(job_id, message="Step 1/6 — Converting audio to WAV...", step=1)
            convert_to_wav(str(dest), processed)

            # ── Step 2: Transcribe ────────────────────────────────
            update_job(job_id, message="Step 2/6 — Transcribing audio (Whisper)...", step=2)
            transcript_segments, transcript_text = transcribe_audio(processed)

            meeting_id = insert_meeting(
                filename=original_filename,
                duration_sec=(
                    transcript_segments[-1]["end"]
                    if transcript_segments else 0
                ),
            )

            # ── Step 3: Diarize ───────────────────────────────────
            update_job(job_id, message="Step 3/6 — Detecting speakers (pyannote)...", step=3)
            speaker_segments = diarize_audio(processed)

            aligned_segments = align_transcript_segments(
                transcript_segments,
                speaker_segments,
            )

            for segment in aligned_segments:
                insert_segment(
                    meeting_id=meeting_id,
                    speaker_label=segment["speaker"],
                    start_time=segment["start"],
                    end_time=segment["end"],
                    transcript_text=segment["text"],
                    is_overlap=segment["is_overlap"],
                )

            report_dir = Path(f"outputs/transcripts/meeting_{meeting_id}")
            report_dir.mkdir(parents=True, exist_ok=True)
            save_json(speaker_segments,    str(report_dir / "speaker_segments.json"))
            save_json(transcript_segments, str(report_dir / "transcript_segments.json"))

            merged = merge_consecutive_speaker_lines(aligned_segments)
            detailed = format_speaker_transcript(merged)
            save_text(detailed,        str(report_dir / "speaker_transcript_detailed.txt"))
            save_text(transcript_text, str(report_dir / "sample_transcript.txt"))

            # ── Step 4: Recognize speakers ────────────────────────
            update_job(job_id, message="Step 4/6 — Identifying speakers (ECAPA)...", step=4)
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
            update_job(job_id, message="Step 5/6 — Building named transcript...", step=5)
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
            update_job(
                job_id,
                status="done",
                message="Meeting processed successfully.",
                step=6,
                total=6,
                result={
                    "meeting_id": meeting_id,
                    "num_speakers": len(seen),
                    "speakers": list(seen.keys()),
                },
            )

        except Exception as e:
            import traceback
            update_job(
                job_id,
                status="error",
                message=str(e),
                total=6,
                error_detail=traceback.format_exc(),
            )

    submit_job(job_id, do_process, cleanup=lambda: remove_job_directory(job_dir))
    return {"job_id": job_id, "message": "Processing started"}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str):
    return get_job(job_id) or {"status": "not_found"}


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
            content={"error": "No summary yet. Generate one from the Summary page."}
        )
    return {"summary": row["summary_text"]}


@app.post("/api/meetings/{meeting_id}/summarize")
async def summarize_meeting(meeting_id: int):
    job_id = make_job_id()
    create_job(job_id, "meeting_summary", "Waiting for Gemini summary generation...")

    def do_summarize():
        from src.summarize import run_summarize

        update_job(job_id, message="Gemini is generating the meeting summary...")
        run_summarize(meeting_id=meeting_id)
        update_job(
            job_id,
            status="done",
            message="Gemini summary generated.",
            result={"meeting_id": meeting_id},
        )

    submit_job(job_id, do_summarize)
    return {"job_id": job_id}


# ── CHAT ──────────────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat(payload: dict):
    question = str(payload.get("question", "")).strip()
    history = payload.get("history", [])

    if not question:
        return JSONResponse(
            status_code=400,
            content={"error": "Question cannot be empty"},
        )
    if not isinstance(history, list):
        return JSONResponse(
            status_code=400,
            content={"error": "Chat history must be a list"},
        )

    try:
        from src.chat import answer_question

        answer, model = answer_question(question, history)
        return {"answer": answer, "model": model}
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": str(exc)},
        )
    except Exception as exc:
        from src.gemini_client import GeminiServiceError

        if isinstance(exc, GeminiServiceError):
            return JSONResponse(
                status_code=503,
                content={"error": str(exc), "error_code": exc.code},
            )
        print(f"Chat error: {type(exc).__name__}: {exc}")
        return JSONResponse(
            status_code=500,
            content={"error": "Meeting chat failed"},
        )
