# src/chat.py
from pathlib import Path
from datetime import datetime
from src.database import get_connection
from src.gemini_client import generate_text


# ── DATABASE CONTEXT BUILDERS ─────────────────────────────────────────────────

def get_all_meetings_overview() -> str:
    """Returns a summary of all meetings in the DB for context."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, filename, processed_at, num_speakers, duration_sec
        FROM meetings
        ORDER BY id
    """).fetchall()
    conn.close()

    if not rows:
        return "No meetings found in the database."

    lines = ["MEETINGS IN DATABASE:"]
    for r in rows:
        dur = f"{round(r['duration_sec'], 0)}s" if r['duration_sec'] else "unknown duration"
        lines.append(
            f"  Meeting #{r['id']}: {r['filename']} | "
            f"processed: {r['processed_at'][:10]} | "
            f"speakers: {r['num_speakers']} | {dur}"
        )
    return "\n".join(lines)


def get_all_speakers() -> str:
    """Returns all enrolled speakers."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT name, enrolled_at, num_samples FROM speakers ORDER BY name
    """).fetchall()
    conn.close()

    if not rows:
        return "No speakers enrolled."

    lines = ["ENROLLED SPEAKERS:"]
    for r in rows:
        lines.append(
            f"  {r['name']} — enrolled: {r['enrolled_at'][:10]}, "
            f"samples: {r['num_samples']}"
        )
    return "\n".join(lines)


def get_full_transcript(meeting_id: int) -> str:
    """Returns full transcript for one meeting."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            seg.start_time,
            seg.end_time,
            seg.speaker_label,
            spk.name        AS speaker_name,
            seg.confidence,
            seg.tier,
            seg.transcript_text
        FROM segments seg
        LEFT JOIN speakers spk ON seg.speaker_id = spk.id
        WHERE seg.meeting_id = ?
        ORDER BY seg.start_time
    """, (meeting_id,)).fetchall()

    meeting = conn.execute(
        "SELECT filename FROM meetings WHERE id = ?", (meeting_id,)
    ).fetchone()
    conn.close()

    if not rows:
        return f"No segments found for meeting #{meeting_id}."

    fname = meeting["filename"] if meeting else f"meeting_{meeting_id}"
    lines = [f"TRANSCRIPT — Meeting #{meeting_id} ({fname}):"]
    for r in rows:
        name = r["speaker_name"] or "UNKNOWN"
        ts   = _fmt_ts(r["start_time"])
        text = r["transcript_text"] or ""
        if text.strip():
            lines.append(f"  [{ts}] {name}: {text.strip()}")

    return "\n".join(lines)


def get_all_transcripts() -> str:
    """Returns transcripts for ALL meetings — used for cross-meeting questions."""
    conn = get_connection()
    meetings = conn.execute(
        "SELECT id FROM meetings ORDER BY id"
    ).fetchall()
    conn.close()

    if not meetings:
        return "No meetings in database."

    all_text = []
    for m in meetings:
        all_text.append(get_full_transcript(m["id"]))
        all_text.append("")

    return "\n".join(all_text)


def search_by_speaker(speaker_name: str) -> str:
    """Find all segments attributed to a specific speaker across all meetings."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            seg.start_time,
            spk.name        AS speaker_name,
            meet.filename   AS meeting_file,
            meet.id         AS meeting_id,
            seg.transcript_text
        FROM segments seg
        JOIN speakers spk  ON seg.speaker_id  = spk.id
        JOIN meetings meet ON seg.meeting_id  = meet.id
        WHERE LOWER(spk.name) = LOWER(?)
        ORDER BY meet.id, seg.start_time
    """, (speaker_name,)).fetchall()
    conn.close()

    if not rows:
        return f"No segments found for speaker '{speaker_name}'."

    lines = [f"ALL SEGMENTS BY {speaker_name.upper()}:"]
    for r in rows:
        ts = _fmt_ts(r["start_time"])
        lines.append(
            f"  [Meeting #{r['meeting_id']} — {r['meeting_file']} @ {ts}] "
            f"{r['transcript_text']}"
        )
    return "\n".join(lines)


def search_by_keyword(keyword: str) -> str:
    """Search transcript text for a keyword across all meetings."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            seg.start_time,
            spk.name        AS speaker_name,
            meet.filename   AS meeting_file,
            meet.id         AS meeting_id,
            seg.transcript_text
        FROM segments seg
        LEFT JOIN speakers spk  ON seg.speaker_id  = spk.id
        LEFT JOIN meetings meet ON seg.meeting_id  = meet.id
        WHERE LOWER(seg.transcript_text) LIKE LOWER(?)
        ORDER BY meet.id, seg.start_time
    """, (f"%{keyword}%",)).fetchall()
    conn.close()

    if not rows:
        return f"No segments found containing '{keyword}'."

    lines = [f"SEGMENTS CONTAINING '{keyword.upper()}':"]
    for r in rows:
        ts   = _fmt_ts(r["start_time"])
        name = r["speaker_name"] or "UNKNOWN"
        lines.append(
            f"  [Meeting #{r['meeting_id']} — {r['meeting_file']} @ {ts}] "
            f"{name}: {r['transcript_text']}"
        )
    return "\n".join(lines)


def get_action_items_all_meetings() -> str:
    """Pull summaries from all meetings that have them — focus on action items."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, filename, summary_text
        FROM meetings
        WHERE summary_text IS NOT NULL
        ORDER BY id
    """).fetchall()
    conn.close()

    if not rows:
        return "No meeting summaries found. Run summarize mode first."

    lines = []
    for r in rows:
        lines.append(f"MEETING #{r['id']} ({r['filename']}):")
        # Extract action items section from saved summary
        summary = r["summary_text"] or ""
        if "ACTION ITEMS" in summary:
            start = summary.index("ACTION ITEMS")
            end   = summary.find("\n\n", start + 100)
            chunk = summary[start:end] if end != -1 else summary[start:]
            lines.append(chunk.strip())
        else:
            lines.append("  (no summary available — run summarize mode)")
        lines.append("")

    return "\n".join(lines)


def smart_context_builder(question: str) -> str:
    """
    Automatically decides what data to pull from the DB
    based on keywords in the question.
    Builds the most relevant context for the LLM.
    """
    q_lower = question.lower()

    context_parts = []

    # Always include meetings overview and speaker list
    context_parts.append(get_all_meetings_overview())
    context_parts.append(get_all_speakers())

    # Detect speaker name mentions
    conn = get_connection()
    enrolled = conn.execute("SELECT name FROM speakers").fetchall()
    conn.close()

    mentioned_speakers = [
        r["name"] for r in enrolled
        if r["name"].lower() in q_lower
    ]

    # Detect meeting ID mention
    import re
    meeting_ids_mentioned = re.findall(r'meeting\s*#?(\d+)', q_lower)

    # Detect topic keywords
    topic_keywords = []
    skip_words = {
        "what", "who", "when", "where", "how", "did", "does",
        "the", "a", "an", "in", "on", "at", "to", "about",
        "meeting", "speaker", "say", "said", "talk", "spoke",
        "tell", "me", "all", "any", "is", "was", "were",
        "summarize", "summary", "give", "show", "list", "find"
    }
    words = re.findall(r'\b[a-z]{4,}\b', q_lower)
    topic_keywords = [w for w in words if w not in skip_words]

    # Pull speaker-specific data
    if mentioned_speakers:
        for name in mentioned_speakers:
            context_parts.append(search_by_speaker(name))
    
    # Pull specific meeting transcript
    if meeting_ids_mentioned:
        for mid in meeting_ids_mentioned:
            context_parts.append(get_full_transcript(int(mid)))
    
    # Action items question
    if any(w in q_lower for w in ["action", "task", "follow", "todo", "assigned"]):
        context_parts.append(get_action_items_all_meetings())

    # Cross-meeting or general question — pull all transcripts
    if (
        not mentioned_speakers
        and not meeting_ids_mentioned
        or any(w in q_lower for w in ["all meetings", "every meeting", "across", "compare"])
    ):
        context_parts.append(get_all_transcripts())
    elif mentioned_speakers or meeting_ids_mentioned:
        pass  # already added specific data
    else:
        # Keyword search
        for kw in topic_keywords[:3]:
            result = search_by_keyword(kw)
            if "No segments" not in result:
                context_parts.append(result)

        # Fallback — latest meeting transcript
        if not topic_keywords:
            conn = get_connection()
            latest = conn.execute(
                "SELECT MAX(id) AS id FROM meetings"
            ).fetchone()
            conn.close()
            if latest and latest["id"]:
                context_parts.append(get_full_transcript(latest["id"]))

    return "\n\n".join(context_parts)


def _fmt_ts(seconds: float) -> str:
    if not seconds:
        return "00:00:00"
    seconds = int(seconds)
    return f"{seconds//3600:02d}:{(seconds%3600)//60:02d}:{seconds%60:02d}"


# ── CHAT SESSION ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a meeting intelligence assistant.
You have access to real data from recorded meetings including:
transcripts, speaker identifications, timestamps, and summaries.

Answer questions based ONLY on the meeting data provided in the context.
Be specific — mention speaker names, timestamps, and exact quotes when relevant.
If the data doesn't contain the answer, say so clearly.
Never make up information that isn't in the context.

You can answer ANY type of question about the meetings:
- What specific people said
- Topics and themes discussed
- Action items and decisions
- Comparisons between speakers
- Cross-meeting patterns
- General questions about what happened
"""


def answer_question(question: str, history: list[dict] | None = None) -> tuple[str, str]:
    """Answer from bounded database context through backend-only Gemini."""
    question = question.strip()
    if not question:
        raise ValueError("Question cannot be empty")

    context = smart_context_builder(question)
    if len(context) > 200_000:
        context = context[:200_000] + "\n[Additional meeting context omitted for size.]"

    return generate_text(
        f"""Relevant meeting data:

{context}

---
Question: {question}""",
        system_instruction=SYSTEM_PROMPT,
        history=history,
        temperature=0.1,
    )


def run_chat():
    print("\n" + "="*60)
    print("  MEETING AI — Chat Mode")
    print("  Ask anything about your meetings.")
    print("  Type 'quit' or 'exit' to stop.")
    print("  Type 'clear' to reset conversation history.")
    print("  Type 'meetings' to see all meetings in DB.")
    print("  Type 'speakers' to see all enrolled speakers.")
    print("="*60 + "\n")

    # Check DB has data
    conn = get_connection()
    meeting_count = conn.execute(
        "SELECT COUNT(*) AS c FROM meetings"
    ).fetchone()["c"]
    conn.close()

    if meeting_count == 0:
        print("❌ No meetings in database yet.")
        print("   Run meeting_ai → recognize_only → final_report first.\n")
        return

    print(f"  ✅ {meeting_count} meeting(s) found in database.\n")

    # Chat history for multi-turn conversation
    chat_history = []

    # Save file setup
    save_dir  = Path("outputs/chat_logs")
    save_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_path = save_dir / f"chat_{timestamp}.txt"

    log_lines = [
        f"Meeting AI Chat Session — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "="*60,
        ""
    ]

    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Chat ended.")
            break

        if not question:
            continue

        if question.lower() in ["quit", "exit"]:
            print("  Chat ended.")
            break

        if question.lower() == "clear":
            chat_history = []
            print("  ✅ Conversation history cleared.\n")
            continue

        if question.lower() == "meetings":
            print("\n" + get_all_meetings_overview() + "\n")
            continue

        if question.lower() == "speakers":
            print("\n" + get_all_speakers() + "\n")
            continue

        print("  [searching database...]\n")
        # Ask Gemini through the shared backend-only client.
        print("AI: ", end="", flush=True)
        try:
            full_response, model = answer_question(question, chat_history)
            print(full_response + "\n")
            print(f"  [model: {model}]\n")

        except Exception as e:
            full_response = f"[Error: {e}]"
            print(full_response + "\n")
            continue

        # Add to history for follow-up support
        chat_history.append({"role": "user",      "content": question})
        chat_history.append({"role": "assistant",  "content": full_response})

        # Log to file
        log_lines.append(f"You: {question}")
        log_lines.append(f"AI:  {full_response}")
        log_lines.append("")

        # Save after every exchange
        with open(save_path, "w", encoding="utf-8") as f:
            f.write("\n".join(log_lines))

    # Final save
    if len(log_lines) > 3:
        with open(save_path, "w", encoding="utf-8") as f:
            f.write("\n".join(log_lines))
        print(f"\n  ✅ Chat saved to: {save_path}")
