# src/database.py
import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path("data/meeting_ai.db")


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS speakers (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            enrolled_at TEXT    NOT NULL,
            num_samples INTEGER NOT NULL DEFAULT 0,
            embedding   TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS voice_samples (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            speaker_id  INTEGER NOT NULL REFERENCES speakers(id),
            file_path   TEXT    NOT NULL,
            duration_sec REAL,
            enrolled_at TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS meetings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            filename     TEXT NOT NULL,
            processed_at TEXT NOT NULL,
            duration_sec REAL,
            num_speakers INTEGER DEFAULT 0,
            report_path  TEXT,
            summary_text TEXT,
            summary_path TEXT
        );

        CREATE TABLE IF NOT EXISTS segments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            meeting_id      INTEGER NOT NULL REFERENCES meetings(id),
            speaker_id      INTEGER REFERENCES speakers(id),
            speaker_label   TEXT,
            start_time      REAL,
            end_time        REAL,
            transcript_text TEXT,
            confidence      REAL,
            margin          REAL,
            tier            TEXT,
            is_overlap      INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS corrections (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            segment_id        INTEGER NOT NULL REFERENCES segments(id),
            original_label    TEXT,
            corrected_name    TEXT,
            corrected_at      TEXT,
            used_for_training INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id           TEXT PRIMARY KEY,
            job_type     TEXT NOT NULL,
            status       TEXT NOT NULL,
            message      TEXT,
            step         INTEGER DEFAULT 0,
            total        INTEGER DEFAULT 0,
            result_json  TEXT,
            error_detail TEXT,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_segments_meeting_start
        ON segments(meeting_id, start_time);

        CREATE INDEX IF NOT EXISTS idx_segments_speaker
        ON segments(speaker_id);

        CREATE INDEX IF NOT EXISTS idx_jobs_status_created
        ON jobs(status, created_at);
    """)

    # Migrate databases created by older versions of the application.
    meeting_columns = {
        row["name"]
        for row in cursor.execute("PRAGMA table_info(meetings)").fetchall()
    }
    if "summary_text" not in meeting_columns:
        cursor.execute("ALTER TABLE meetings ADD COLUMN summary_text TEXT")
    if "summary_path" not in meeting_columns:
        cursor.execute("ALTER TABLE meetings ADD COLUMN summary_path TEXT")

    cursor.execute(
        "INSERT OR IGNORE INTO schema_migrations (version, applied_at) VALUES (1, ?)",
        (datetime.now().isoformat(),),
    )

    conn.commit()
    conn.close()
    print("Database initialised: data/meeting_ai.db")


def create_job(job_id: str, job_type: str, message: str, total: int = 0):
    conn = get_connection()
    now = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO jobs
           (id, job_type, status, message, step, total, created_at, updated_at)
           VALUES (?, ?, 'queued', ?, 0, ?, ?, ?)""",
        (job_id, job_type, message, total, now, now),
    )
    conn.commit()
    conn.close()


def update_job(
    job_id: str,
    *,
    status: str = None,
    message: str = None,
    step: int = None,
    total: int = None,
    result: dict = None,
    error_detail: str = None,
):
    values = {
        "status": status,
        "message": message,
        "step": step,
        "total": total,
        "result_json": json.dumps(result) if result is not None else None,
        "error_detail": error_detail,
    }
    assignments = []
    params = []
    for column, value in values.items():
        if value is not None:
            assignments.append(f"{column} = ?")
            params.append(value)
    if not assignments:
        return

    assignments.append("updated_at = ?")
    params.append(datetime.now().isoformat())
    params.append(job_id)

    conn = get_connection()
    conn.execute(
        f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?",
        params,
    )
    conn.commit()
    conn.close()


def get_job(job_id: str):
    conn = get_connection()
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    conn.close()
    if not row:
        return None

    job = dict(row)
    result_json = job.pop("result_json", None)
    if result_json:
        job.update(json.loads(result_json))
    return job


def fail_incomplete_jobs():
    conn = get_connection()
    now = datetime.now().isoformat()
    conn.execute(
        """UPDATE jobs
           SET status = 'error',
               message = 'Job interrupted by application restart',
               updated_at = ?
           WHERE status IN ('queued', 'running')""",
        (now,),
    )
    conn.commit()
    conn.close()


# ── SPEAKERS ─────────────────────────────────────────────────────────────────

def upsert_speaker(name: str, embedding: list, num_samples: int) -> int:
    """
    Insert speaker if not exists, update embedding if already enrolled.
    Returns the speaker id.
    """
    conn = get_connection()
    cursor = conn.cursor()

    now = datetime.now().isoformat()
    embedding_json = json.dumps(embedding)

    existing = cursor.execute(
        "SELECT id FROM speakers WHERE name = ?", (name,)
    ).fetchone()

    if existing:
        cursor.execute(
            """UPDATE speakers
               SET embedding = ?, num_samples = ?, enrolled_at = ?
               WHERE name = ?""",
            (embedding_json, num_samples, now, name)
        )
        speaker_id = existing["id"]
        print(f"  Updated existing profile: {name} (id: {speaker_id})")
    else:
        cursor.execute(
            """INSERT INTO speakers (name, enrolled_at, num_samples, embedding)
               VALUES (?, ?, ?, ?)""",
            (name, now, num_samples, embedding_json)
        )
        speaker_id = cursor.lastrowid
        print(f"  New speaker enrolled: {name} (id: {speaker_id})")

    conn.commit()
    conn.close()
    return speaker_id


def insert_voice_sample(speaker_id: int, file_path: str, duration_sec: float = None):
    conn = get_connection()
    now = datetime.now().isoformat()
    existing = conn.execute(
        "SELECT id FROM voice_samples WHERE speaker_id = ? AND file_path = ?",
        (speaker_id, file_path),
    ).fetchone()
    if not existing:
        conn.execute(
            """INSERT INTO voice_samples (speaker_id, file_path, duration_sec, enrolled_at)
               VALUES (?, ?, ?, ?)""",
            (speaker_id, file_path, duration_sec, now)
        )
    conn.commit()
    conn.close()


def load_all_speaker_profiles() -> dict:
    """
    Returns dict of {name: {name, embedding, num_samples}}
    Same structure as the old speaker_profiles.json so
    recognize_speakers.py needs zero changes.
    """
    conn = get_connection()
    rows = conn.execute("SELECT name, embedding, num_samples FROM speakers").fetchall()
    conn.close()

    profiles = {}
    for row in rows:
        profiles[row["name"]] = {
            "name":        row["name"],
            "num_samples": row["num_samples"],
            "embedding":   json.loads(row["embedding"]),
        }
    return profiles


def get_speaker_id_by_name(name: str):
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM speakers WHERE name = ?", (name,)
    ).fetchone()
    conn.close()
    return row["id"] if row else None


# ── MEETINGS ─────────────────────────────────────────────────────────────────

def insert_meeting(filename: str, duration_sec: float = None) -> int:
    """
    Creates a new meeting record. Returns meeting id.
    """
    conn = get_connection()
    now = datetime.now().isoformat()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO meetings (filename, processed_at, duration_sec)
           VALUES (?, ?, ?)""",
        (filename, now, duration_sec)
    )
    meeting_id = cursor.lastrowid
    conn.commit()
    conn.close()
    print(f"  Meeting record created: id={meeting_id}, file={filename}")
    return meeting_id


def update_meeting_report_path(meeting_id: int, report_path: str, num_speakers: int):
    conn = get_connection()
    conn.execute(
        """UPDATE meetings
           SET report_path = ?, num_speakers = ?
           WHERE id = ?""",
        (report_path, num_speakers, meeting_id)
    )
    conn.commit()
    conn.close()


def get_latest_meeting_id() -> int:
    """Returns the most recently created meeting id."""
    conn = get_connection()
    row = conn.execute(
        "SELECT id FROM meetings ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        raise ValueError("No meetings found in database. Run meeting_ai mode first.")
    return row["id"]


def get_meeting_by_id(meeting_id: int) -> dict:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM meetings WHERE id = ?", (meeting_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise ValueError(f"Meeting id {meeting_id} not found.")
    return dict(row)


# ── SEGMENTS ─────────────────────────────────────────────────────────────────

def insert_segment(
    meeting_id: int,
    speaker_label: str,
    start_time: float,
    end_time: float,
    transcript_text: str,
    is_overlap: bool = False,
) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO segments
           (meeting_id, speaker_label, start_time, end_time,
            transcript_text, is_overlap)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            meeting_id,
            speaker_label,
            start_time,
            end_time,
            transcript_text,
            1 if is_overlap else 0,
        )
    )
    seg_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return seg_id


def update_segment_speaker(
    segment_id: int,
    speaker_id: int,
    confidence: float,
    margin: float,
    tier: str,
):
    conn = get_connection()
    conn.execute(
        """UPDATE segments
           SET speaker_id = ?, confidence = ?, margin = ?, tier = ?
           WHERE id = ?""",
        (speaker_id, confidence, margin, tier, segment_id)
    )
    conn.commit()
    conn.close()


def get_segments_for_meeting(meeting_id: int) -> list:
    """
    Returns all segments for a meeting, joined with speaker name.
    Used by final_report mode.
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT
               seg.id,
               seg.speaker_label,
               seg.start_time,
               seg.end_time,
               seg.transcript_text,
               seg.confidence,
               seg.margin,
               seg.tier,
               seg.is_overlap,
               spk.name AS speaker_name
           FROM segments seg
           LEFT JOIN speakers spk ON seg.speaker_id = spk.id
           WHERE seg.meeting_id = ?
           ORDER BY seg.start_time""",
        (meeting_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_raw_segments_for_meeting(meeting_id: int) -> list:
    """
    Returns raw diarization segments for recognize_only mode.
    Same shape as old speaker_segments.json.
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, speaker_label AS speaker, start_time AS start, end_time AS end
           FROM segments
           WHERE meeting_id = ?
           ORDER BY start_time""",
        (meeting_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── CORRECTIONS ──────────────────────────────────────────────────────────────

def insert_correction(
    segment_id: int,
    original_label: str,
    corrected_name: str,
):
    conn = get_connection()
    now = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO corrections
           (segment_id, original_label, corrected_name, corrected_at)
           VALUES (?, ?, ?, ?)""",
        (segment_id, original_label, corrected_name, now)
    )
    conn.commit()
    conn.close()
