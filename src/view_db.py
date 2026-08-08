# src/view_db.py
import sqlite3
from pathlib import Path

DB_PATH = Path("data/meeting_ai.db")

QUERIES = {
    "1": {
        "label": "All enrolled speakers",
        "sql": """
            SELECT id, name, enrolled_at, num_samples
            FROM speakers
        """
    },
    "2": {
        "label": "Voice sample files per speaker",
        "sql": """
            SELECT s.name AS speaker, vs.file_path, vs.enrolled_at
            FROM voice_samples vs
            JOIN speakers s ON vs.speaker_id = s.id
        """
    },
    "3": {
        "label": "All meetings processed",
        "sql": """
            SELECT id, filename, processed_at, num_speakers, report_path
            FROM meetings
        """
    },
    "4": {
        "label": "All segments with speaker names (latest meeting)",
        "sql": """
            SELECT
                seg.start_time,
                seg.end_time,
                seg.speaker_label,
                spk.name    AS identified_as,
                seg.confidence,
                seg.tier,
                seg.transcript_text
            FROM segments seg
            LEFT JOIN speakers spk ON seg.speaker_id = spk.id
            WHERE seg.meeting_id = (SELECT MAX(id) FROM meetings)
            ORDER BY seg.start_time
        """
    },
    "5": {
        "label": "UNKNOWN segments only",
        "sql": """
            SELECT
                seg.start_time,
                seg.end_time,
                seg.speaker_label,
                seg.confidence,
                seg.tier,
                seg.transcript_text
            FROM segments seg
            WHERE seg.speaker_id IS NULL
            ORDER BY seg.start_time
        """
    },
    "6": {
        "label": "High confidence identifications only",
        "sql": """
            SELECT
                seg.start_time,
                seg.end_time,
                spk.name AS speaker,
                seg.confidence,
                seg.transcript_text
            FROM segments seg
            JOIN speakers spk ON seg.speaker_id = spk.id
            WHERE seg.tier = 'high'
            ORDER BY seg.confidence DESC
        """
    },
    "7": {
        "label": "Speaker talk time summary",
        "sql": """
            SELECT
                spk.name                                        AS speaker,
                COUNT(seg.id)                                   AS total_segments,
                ROUND(SUM(seg.end_time - seg.start_time), 1)   AS total_seconds,
                ROUND(AVG(seg.confidence), 3)                  AS avg_confidence
            FROM segments seg
            JOIN speakers spk ON seg.speaker_id = spk.id
            GROUP BY spk.name
            ORDER BY total_seconds DESC
        """
    },
    "8": {
        "label": "Row count across all tables",
        "sql": """
            SELECT 'speakers'     AS table_name, COUNT(*) AS rows FROM speakers
            UNION ALL SELECT 'voice_samples', COUNT(*) FROM voice_samples
            UNION ALL SELECT 'meetings',      COUNT(*) FROM meetings
            UNION ALL SELECT 'segments',      COUNT(*) FROM segments
            UNION ALL SELECT 'corrections',   COUNT(*) FROM corrections
        """
    },
}


def print_results(cursor, label):
    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]

    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")

    if not rows:
        print("  (no rows found)")
        return

    # Column widths
    widths = [max(len(str(c)), max(len(str(r[i])) for r in rows))
              for i, c in enumerate(cols)]
    widths = [min(w, 35) for w in widths]

    # Header
    header = "  " + "  |  ".join(
        str(c).ljust(widths[i]) for i, c in enumerate(cols)
    )
    print(header)
    print("  " + "-" * (sum(widths) + 5 * len(widths)))

    # Rows
    for row in rows:
        line_parts = []
        for i, val in enumerate(row):
            text = str(val) if val is not None else "NULL"
            if len(text) > 35:
                text = text[:32] + "..."
            line_parts.append(text.ljust(widths[i]))
        print("  " + "  |  ".join(line_parts))

    print(f"\n  {len(rows)} row(s) returned.")


def run_custom_query(conn, sql):
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        print_results(cursor, "Custom query result")
    except Exception as e:
        print(f"\n❌ Query error: {e}")


def run_menu():
    conn = sqlite3.connect(DB_PATH)

    while True:
        print(f"\n{'='*70}")
        print("  MEETING AI — Database Viewer")
        print(f"{'='*70}")

        for key, q in QUERIES.items():
            print(f"  [{key}] {q['label']}")

        print("  [c] Run custom SQL query")
        print("  [q] Quit")
        print(f"{'='*70}")

        choice = input("  Choose: ").strip().lower()

        if choice == "q":
            print("  Bye!")
            break

        elif choice == "c":
            print("\n  Type your SQL query (press Enter twice to run):")
            lines = []
            while True:
                line = input()
                if line == "" and lines:
                    break
                lines.append(line)
            sql = "\n".join(lines)
            run_custom_query(conn, sql)

        elif choice in QUERIES:
            q = QUERIES[choice]
            try:
                cursor = conn.cursor()
                cursor.execute(q["sql"])
                print_results(cursor, q["label"])
            except Exception as e:
                print(f"\n❌ Error: {e}")

        else:
            print("  Invalid choice. Try again.")

    conn.close()


if __name__ == "__main__":
    run_menu()