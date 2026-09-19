# app/main.py
from pathlib import Path

from src.audio_preprocess import convert_to_wav
from src.transcribe import transcribe_audio
from src.file_utils import save_text, save_json, load_json
from src.align_speakers import (
    align_transcript_segments,
    merge_consecutive_speaker_lines,
    replace_speaker_labels_with_names,
    format_speaker_transcript,
)
from src.check_voice_samples import check_voice_samples
from src.database import (
    init_db,
    insert_meeting,
    insert_segment,
    update_segment_speaker,
    update_meeting_report_path,
    get_latest_meeting_id,
    get_meeting_by_id,
    get_segments_for_meeting,
    get_raw_segments_for_meeting,
    get_speaker_id_by_name,
)

# ── Choose mode ───────────────────────────────────────────────────────────────
MODE = "chat"

INPUT_FILE     = "audio/input/chatgptandpreethamsample1mix.mp3"
PROCESSED_FILE = "audio/processed/output.wav"


def get_report_dir(meeting_id: int) -> Path:
    """Each meeting gets its own output folder."""
    report_dir = Path(f"outputs/transcripts/meeting_{meeting_id}")
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


def format_timestamp(seconds: float) -> str:
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


# ── Mode: enroll ──────────────────────────────────────────────────────────────
# No changes needed — enroll_speakers.py handles DB directly


# ── Mode: meeting_ai ──────────────────────────────────────────────────────────
def run_meeting_ai():
    
    from src.diarize import diarize_audio

    print("Running meeting AI mode")
    init_db()

    convert_to_wav(INPUT_FILE, PROCESSED_FILE)

    # Create meeting record in DB
    filename   = Path(INPUT_FILE).name
    meeting_id = insert_meeting(filename=filename)

    # Transcribe
    transcript_segments, transcript_text = transcribe_audio(PROCESSED_FILE)

    report_dir = get_report_dir(meeting_id)
    save_text(transcript_text, str(report_dir / "sample_transcript.txt"))

    # Diarize
    speaker_segments = diarize_audio(PROCESSED_FILE)

    # Save raw segments to DB
    for seg in speaker_segments:
        # Find matching transcript text for this segment
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
    # Also save JSON files for compatibility
    save_json(speaker_segments,    str(report_dir / "speaker_segments.json"))
    save_json(transcript_segments, str(report_dir / "transcript_segments.json"))

    # Build readable speaker transcript for the folder
    merged_transcript = merge_consecutive_speaker_lines(aligned_segments)
    detailed_text      = format_speaker_transcript(merged_transcript)
    save_text(detailed_text, str(report_dir / "speaker_transcript_detailed.txt"))

    print(f"\n✅ Meeting {meeting_id} saved to database.")
    print(f"   Output folder: {report_dir}")
    print(f"\nSpeaker Transcript:\n")
    print(detailed_text)


# ── Mode: recognize_only ──────────────────────────────────────────────────────
def run_recognize_only():
    from src.recognize_speakers import recognize_diarized_speakers

    print("Running recognize-only mode")
    init_db()

    meeting_id = get_latest_meeting_id()
    print(f"  Using meeting id: {meeting_id}")

    # Load raw segments from DB (same shape as old speaker_segments.json)
    raw_segments = get_raw_segments_for_meeting(meeting_id)

    speaker_label_to_name = recognize_diarized_speakers(
        PROCESSED_FILE,
        raw_segments,
    )

    # Update each segment row in DB with speaker identity
    for seg in raw_segments:
        label  = seg["speaker"]
        result = speaker_label_to_name.get(label)
        if not result:
            continue

        # Get the real speaker_id from DB (None if UNKNOWN)
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

    # Save mapping JSON for reference
    report_dir = get_report_dir(meeting_id)
    save_json(speaker_label_to_name, str(report_dir / "speaker_mapping.json"))

    print("\nSpeaker Mapping:")
    for label, info in speaker_label_to_name.items():
        print(f"  {label} -> {info}")


# ── Mode: final_report ────────────────────────────────────────────────────────
def run_final_report():
    print("Running final report mode")
    init_db()

    meeting_id = get_latest_meeting_id()
    meeting    = get_meeting_by_id(meeting_id)
    segments   = get_segments_for_meeting(meeting_id)

    report_dir = get_report_dir(meeting_id)

    # Build transcript lines
    lines = []
    for seg in segments:
        start_ts   = format_timestamp(seg["start_time"])
        name       = seg["speaker_name"]
        confidence = seg["confidence"]
        tier       = seg["tier"] or "low"

        if name:
            display = f"{name} ({confidence})"
        elif confidence and confidence >= 0.50:
            display = f"UNKNOWN (conf: {confidence})"
        else:
            display = f"UNKNOWN (conf: {confidence})" if confidence else "UNKNOWN"

        line = f"[{start_ts}] {display}: {seg['transcript_text']}"
        lines.append(line)

    named_text = "\n".join(lines)

    # Build speaker summary
    seen = {}
    for seg in segments:
        name = seg["speaker_name"] or "UNKNOWN"
        if name not in seen:
            seen[name] = seg

    summary_lines = ["", "=" * 60, "  SPEAKER SUMMARY", "=" * 60]
    for name, seg in seen.items():
        conf = seg["confidence"] or 0.0
        tier = seg["tier"] or "low"
        summary_lines.append(
            f"  {name}  |  confidence: {conf}  |  tier: {tier}"
        )

    summary_text = "\n".join(summary_lines)

    full_report = (
        "=" * 60 + "\n"
        f"  MEETING REPORT — {meeting['filename']}\n"
        f"  Meeting ID: {meeting_id}\n"
        + "=" * 60 + "\n"
        + named_text
        + "\n"
        + summary_text
        + "\n"
    )

    report_path = str(report_dir / "named_transcript.txt")
    save_text(full_report, report_path)

    # Update meetings table with report path and speaker count
    update_meeting_report_path(
        meeting_id=meeting_id,
        report_path=report_path,
        num_speakers=len(seen),
    )

    print("\n" + full_report)
    print(f"✅ Named transcript saved: {report_path}")


# ── Mode: transcribe only ─────────────────────────────────────────────────────
def run_transcribe_only():
    print("Running transcription-only mode")
    convert_to_wav(INPUT_FILE, PROCESSED_FILE)
    transcript_segments, transcript_text = transcribe_audio(PROCESSED_FILE)
    save_text(transcript_text, "outputs/transcripts/sample_transcript.txt")
    print("\nFinal Transcript:\n")
    print(transcript_text)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Meeting AI started")

    if MODE == "meeting_ai":
        run_meeting_ai()
    elif MODE == "recognize_only":
        run_recognize_only()
    elif MODE == "final_report":
        run_final_report()
    elif MODE == "enroll":
        from src.enroll_speakers import enroll_speakers
        enroll_speakers()
    elif MODE == "check_samples":
        check_voice_samples()
    elif MODE == "transcribe_only":
        run_transcribe_only()
    elif MODE == "view_db":
        from src.view_db import run_menu
        run_menu()
    elif MODE == "summarize":
        from src.summarize import run_summarize
        run_summarize()
    elif MODE == "chat":
        from src.chat import run_chat
        run_chat()
    else:
        raise ValueError(f"Unknown mode: {MODE}")