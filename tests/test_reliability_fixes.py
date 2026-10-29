import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.database as database


class SummaryFailureTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = Path(self.temp_dir.name) / "meeting_ai.db"
        database.init_db()
        self.meeting_id = database.insert_meeting("summary.wav", duration_sec=4)
        database.insert_segment(
            meeting_id=self.meeting_id,
            speaker_label="SPEAKER_00",
            start_time=0,
            end_time=4,
            transcript_text="A real transcript line.",
        )

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_model_error_is_not_saved_as_completed_summary(self):
        from src.summarize import run_summarize

        with patch(
            "src.summarize.ask_gemini", side_effect=RuntimeError("model unavailable")
        ), patch("src.summarize.save_text"):
            with self.assertRaisesRegex(RuntimeError, "model unavailable"):
                run_summarize(self.meeting_id)

        conn = sqlite3.connect(database.DB_PATH)
        summary = conn.execute(
            "SELECT summary_text FROM meetings WHERE id = ?", (self.meeting_id,)
        ).fetchone()[0]
        conn.close()
        self.assertIsNone(summary)


class GeminiChatTests(unittest.TestCase):
    def test_chat_uses_shared_gemini_client_with_database_context(self):
        from src.chat import answer_question

        with patch(
            "src.chat.smart_context_builder",
            return_value="Meeting #1: fictional planning meeting",
        ), patch(
            "src.chat.generate_text",
            return_value=("Rahul owned the fictional follow-up.", "gemini-test"),
        ) as generate:
            answer, model = answer_question("Who owned the follow-up?", [])

        self.assertEqual(answer, "Rahul owned the fictional follow-up.")
        self.assertEqual(model, "gemini-test")
        self.assertIn("fictional planning meeting", generate.call_args.args[0])


class CliInsertionTests(unittest.TestCase):
    def test_each_aligned_transcript_segment_is_inserted_once(self):
        from app.main import insert_aligned_transcript

        transcripts = [
            {"start": 0.0, "end": 1.0, "text": "one"},
            {"start": 1.0, "end": 2.0, "text": "two"},
        ]
        speakers = [
            {"start": 0.0, "end": 2.0, "speaker": "SPEAKER_00"},
            {"start": 2.0, "end": 3.0, "speaker": "SPEAKER_01"},
        ]
        with patch("app.main.insert_segment") as insert:
            aligned = insert_aligned_transcript(7, transcripts, speakers)

        self.assertEqual(len(aligned), 2)
        self.assertEqual(insert.call_count, 2)


class JobErrorClassificationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = Path(self.temp_dir.name) / "meeting_ai.db"
        database.init_db()

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_job_exposes_safe_error_code(self):
        from src.jobs import submit_job

        class ExampleError(RuntimeError):
            code = "example_failure"

        database.create_job("coded-error", "test", "Queued")
        future = submit_job(
            "coded-error", lambda: (_ for _ in ()).throw(ExampleError("failed"))
        )
        future.result(timeout=5)

        job = database.get_job("coded-error")
        self.assertEqual(job["status"], "error")
        self.assertEqual(job["error_code"], "example_failure")


if __name__ == "__main__":
    unittest.main()
