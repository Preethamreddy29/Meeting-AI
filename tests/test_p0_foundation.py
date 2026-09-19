import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.database as database
from src.storage import save_audio_upload


class FakeUpload:
    def __init__(self, filename, content=b"audio", content_type="audio/wav"):
        self.filename = filename
        self.content_type = content_type
        self.file = io.BytesIO(content)


class DatabaseFoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = Path(self.temp_dir.name) / "meeting_ai.db"

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_fresh_database_contains_summary_and_jobs_schema(self):
        database.init_db()
        conn = database.get_connection()
        meeting_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(meetings)")
        }
        job_columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
        foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        conn.close()

        self.assertIn("summary_text", meeting_columns)
        self.assertIn("summary_path", meeting_columns)
        self.assertIn("result_json", job_columns)
        self.assertEqual(foreign_keys, 1)

    def test_legacy_meetings_table_is_migrated(self):
        conn = sqlite3.connect(database.DB_PATH)
        conn.execute(
            """CREATE TABLE meetings (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   filename TEXT NOT NULL,
                   processed_at TEXT NOT NULL,
                   duration_sec REAL,
                   num_speakers INTEGER DEFAULT 0,
                   report_path TEXT
               )"""
        )
        conn.commit()
        conn.close()

        database.init_db()
        conn = database.get_connection()
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(meetings)")}
        conn.close()

        self.assertIn("summary_text", columns)
        self.assertIn("summary_path", columns)

    def test_job_result_survives_database_round_trip(self):
        database.init_db()
        database.create_job("job-1", "meeting_processing", "Queued", total=6)
        database.update_job(
            "job-1",
            status="done",
            message="Complete",
            step=6,
            result={"meeting_id": 42},
        )

        job = database.get_job("job-1")
        self.assertEqual(job["status"], "done")
        self.assertEqual(job["meeting_id"], 42)


class UploadSafetyTests(unittest.TestCase):
    def test_uploaded_name_cannot_control_destination_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            destination, original_name = save_audio_upload(
                FakeUpload("../../outside.wav"),
                root,
            )

            self.assertEqual(original_name, "outside.wav")
            self.assertEqual(destination.parent, root.resolve())
            self.assertTrue(destination.exists())

    def test_rejects_unsupported_extension(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                save_audio_upload(FakeUpload("payload.exe"), Path(temp_dir))


class SpeakerRecognitionGuardTests(unittest.TestCase):
    def test_no_profiles_returns_unknown_without_loading_model(self):
        from src.recognize_speakers import recognize_diarized_speakers

        segments = [{"speaker": "SPEAKER_00", "start": 0.0, "end": 4.0}]
        with patch("src.recognize_speakers.load_all_speaker_profiles", return_value={}), \
             patch("src.recognize_speakers.load_ecapa_model") as load_model:
            result = recognize_diarized_speakers("unused.wav", segments)

        self.assertEqual(result["SPEAKER_00"]["name"], "UNKNOWN")
        self.assertEqual(result["SPEAKER_00"]["confidence"], 0.0)
        load_model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
