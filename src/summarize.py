# src/summarize.py
import ollama
from src.database import (
    get_latest_meeting_id,
    get_meeting_by_id,
    get_segments_for_meeting,
    get_connection,
)
from src.file_utils import save_text
from pathlib import Path
from datetime import datetime


MODEL      = "llama3.2:3b"
OLLAMA_URL = "http://localhost:11434"


def format_timestamp(seconds: float) -> str:
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def build_transcript_for_llm(segments: list) -> str:
    """
    Builds a clean readable transcript string to feed into the LLM.
    Keeps it concise — LLM doesn't need JSON, just plain dialogue.
    """
    lines = []
    for seg in segments:
        name      = seg["speaker_name"] or "UNKNOWN"
        timestamp = format_timestamp(seg["start_time"])
        text      = seg["transcript_text"] or ""
        if text.strip():
            lines.append(f"[{timestamp}] {name}: {text.strip()}")
    return "\n".join(lines)


def build_speaker_list(segments: list) -> list:
    """Returns unique identified speaker names from segments."""
    seen  = set()
    names = []
    for seg in segments:
        name = seg["speaker_name"]
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def ask_ollama(prompt: str) -> str:
    """Send a prompt to Ollama and return the response text."""
    try:
        response = ollama.chat(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a professional meeting analyst. "
                        "You read meeting transcripts and produce clear, "
                        "concise, structured summaries. "
                        "Be factual and specific. Never make things up. "
                        "Only use what is in the transcript provided."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )
        return response["message"]["content"].strip()
    except Exception as e:
        return f"[LLM error: {e}]"


def run_summarize(meeting_id: int = None):
    print("Running summarize mode")

    if not meeting_id:
        meeting_id = get_latest_meeting_id()

    print(f"  Meeting id: {meeting_id}")

    meeting  = get_meeting_by_id(meeting_id)
    segments = get_segments_for_meeting(meeting_id)

    if not segments:
        print("❌ No segments found for this meeting. Run meeting_ai first.")
        return

    transcript   = build_transcript_for_llm(segments)
    speaker_list = build_speaker_list(segments)
    speakers_str = ", ".join(speaker_list) if speaker_list else "unknown speakers"

    print(f"\n  Speakers identified: {speakers_str}")
    print(f"  Total segments: {len(segments)}")
    print(f"  Sending transcript to {MODEL}...\n")

    # ── 1. What is this meeting about ─────────────────────────────
    print("  [1/6] Identifying meeting topic...")
    topic = ask_ollama(f"""
Here is a meeting transcript:

{transcript}

In 1-2 sentences, what is this meeting about?
What is the main topic or purpose of this meeting?
Be specific and direct.
""")

    # ── 2. Overall summary ─────────────────────────────────────────
    print("  [2/6] Generating overall summary...")
    overall = ask_ollama(f"""
Here is a meeting transcript:

{transcript}

Write a clear overall summary of this meeting in 3-5 sentences.
Cover: what was discussed, what decisions were made, and what the outcome was.
Do not use bullet points. Write in paragraph form.
""")

    # ── 3. Who spoke what — per person breakdown ───────────────────
    print("  [3/6] Building per-person breakdown...")
    per_person = ask_ollama(f"""
Here is a meeting transcript:

{transcript}

The speakers in this meeting are: {speakers_str}

For each speaker, write 2-4 bullet points summarizing:
- What topics they raised or discussed
- What opinions or positions they expressed
- Any specific points or numbers they mentioned

Format exactly like this for each person:
**[Speaker Name]**
- point one
- point two
- point three
""")

    # ── 4. Action items ────────────────────────────────────────────
    print("  [4/6] Extracting action items...")
    action_items = ask_ollama(f"""
Here is a meeting transcript:

{transcript}

List all action items, tasks, follow-ups, or commitments mentioned in this meeting.
For each one, identify who is responsible if mentioned.

Format exactly like this:
- [Person or UNKNOWN]: action item description

If no clear action items were mentioned, say "No explicit action items identified."
""")

    # ── 5. Key topics ──────────────────────────────────────────────
    print("  [5/6] Identifying key topics...")
    key_topics = ask_ollama(f"""
Here is a meeting transcript:

{transcript}

List the 3-6 key topics or themes discussed in this meeting.
For each topic, write one sentence explaining what was said about it.

Format exactly like this:
1. [Topic name]: one sentence explanation
2. [Topic name]: one sentence explanation
""")

    # ── 6. Sentiment per speaker ───────────────────────────────────
    print("  [6/6] Analysing sentiment per speaker...")
    sentiment = ask_ollama(f"""
Here is a meeting transcript:

{transcript}

The speakers are: {speakers_str}

For each speaker, assess their overall tone and sentiment in this meeting.
Choose from: Positive / Neutral / Cautious / Tense / Frustrated / Enthusiastic

Format exactly like this:
**[Speaker Name]**: [sentiment label] — one sentence explaining why

Base this only on what they actually said in the transcript.
""")

    # ── Build full summary report ──────────────────────────────────
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    full_summary = f"""
{'='*60}
  MEETING SUMMARY REPORT
  File     : {meeting['filename']}
  Meeting  : #{meeting_id}
  Generated: {now}
  Model    : {MODEL}
{'='*60}

WHAT IS THIS MEETING ABOUT
{'─'*60}
{topic}

OVERALL SUMMARY
{'─'*60}
{overall}

KEY TOPICS DISCUSSED
{'─'*60}
{key_topics}

WHO SPOKE WHAT
{'─'*60}
{per_person}

ACTION ITEMS
{'─'*60}
{action_items}

SENTIMENT PER SPEAKER
{'─'*60}
{sentiment}

{'='*60}
""".strip()

    # ── Save to file ───────────────────────────────────────────────
    report_dir  = Path(f"outputs/transcripts/meeting_{meeting_id}")
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(report_dir / "meeting_summary.txt")

    save_text(full_summary, output_path)

    # ── Save to database ───────────────────────────────────────────
    save_summary_to_db(meeting_id, full_summary, output_path)

    print("\n" + full_summary)
    print(f"\n✅ Summary saved: {output_path}")


def save_summary_to_db(meeting_id: int, summary_text: str, file_path: str):
    """Store a generated summary on its meeting record."""
    conn = get_connection()
    conn.execute(
        """UPDATE meetings
           SET summary_text = ?, summary_path = ?
           WHERE id = ?""",
        (summary_text, file_path, meeting_id)
    )
    conn.commit()
    conn.close()
    print("  ✅ Summary saved to database.")
