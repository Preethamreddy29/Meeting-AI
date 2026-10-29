import csv
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import src.database as database
from src.meeting_actions import (
    change_item,
    create_notes,
    export_csv,
    extract_and_save,
    GEMINI_RESPONSE_SCHEMA,
    GeminiConfigurationError,
    get_meeting_context,
    init_actions,
    list_items,
    list_runs,
    model_extract,
    set_meeting_context,
    source_document,
    validate_output,
)


class MeetingActionsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = Path(self.temp_dir.name) / "meeting_ai.db"
        database.init_db()
        init_actions()
        self.meeting_id = create_notes(
            "Planning",
            "Rahul will send the revised API spec tomorrow.\n"
            "The team agreed to ship Friday.",
            "2026-10-27",
            "Asia/Kolkata",
        )
        self.fixture = {
            "actions": [
                {
                    "description": "Send the revised API spec",
                    "owner": "Rahul",
                    "due_date_text": "tomorrow",
                    "evidence": [
                        {
                            "source_unit_id": "line-1",
                            "quote": "Rahul will send the revised API spec tomorrow.",
                        }
                    ],
                }
            ],
            "decisions": [
                {
                    "description": "Ship Friday",
                    "owner": None,
                    "due_date_text": None,
                    "evidence": [
                        {
                            "source_unit_id": "line-2",
                            "quote": "The team agreed to ship Friday.",
                        }
                    ],
                }
            ],
            "follow_ups": [],
        }

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_gemini_schema_omits_unsupported_additional_properties(self):
        schema = json.dumps(GEMINI_RESPONSE_SCHEMA)
        self.assertNotIn("additionalProperties", schema)
        self.assertNotIn("maxLength", schema)
        self.assertNotIn("default", schema)

    def test_notes_persist_with_context_and_relative_date_resolution(self):
        run_id = extract_and_save(self.meeting_id, lambda _document: self.fixture)
        result = list_items(self.meeting_id, run_id)

        self.assertEqual(result["items"][0]["due_date_text"], "tomorrow")
        self.assertEqual(result["items"][0]["due_date_iso"], "2026-10-28")
        self.assertFalse(result["items"][0]["due_date_needs_review"])

    def test_stored_transcript_path_includes_speaker_and_timestamps(self):
        meeting_id = database.insert_meeting("stored.wav", duration_sec=8)
        database.insert_segment(
            meeting_id=meeting_id,
            speaker_label="SPEAKER_00",
            start_time=1.5,
            end_time=4.0,
            transcript_text="Maya will prepare the demo.",
        )

        document = source_document(meeting_id)

        self.assertEqual(document["source_type"], "transcript")
        self.assertEqual(document["units"][0]["start"], 1.5)
        self.assertEqual(document["units"][0]["speaker"], "SPEAKER_00")

        fixture = {
            "actions": [
                {
                    "description": "Prepare the demo",
                    "owner": None,
                    "due_date_text": "tomorrow",
                    "evidence": [
                        {
                            "source_unit_id": document["units"][0]["id"],
                            "quote": "Maya will prepare the demo.",
                        }
                    ],
                }
            ],
            "decisions": [],
            "follow_ups": [],
        }
        run_id = extract_and_save(meeting_id, lambda _document: fixture)
        item = list_items(meeting_id, run_id)["items"][0]
        approved = change_item(
            item["id"], item["version"], {"review_status": "approved"}
        )
        set_meeting_context(meeting_id, "2026-10-27", "Asia/Kolkata")
        context = get_meeting_context(meeting_id)
        document = source_document(meeting_id)
        updated = list_items(meeting_id, run_id)["items"][0]
        self.assertEqual(context["meeting_date"], "2026-10-27")
        self.assertEqual(document["timezone"], "Asia/Kolkata")
        self.assertEqual(updated["due_date_iso"], "2026-10-28")
        self.assertEqual(updated["review_status"], "draft")
        self.assertGreater(updated["version"], approved["version"])

    def test_unsupported_quote_is_flagged_and_cannot_be_approved(self):
        invalid = {
            **self.fixture,
            "actions": [
                {
                    **self.fixture["actions"][0],
                    "evidence": [
                        {"source_unit_id": "line-1", "quote": "invented quote"}
                    ],
                }
            ],
        }
        extract_and_save(self.meeting_id, lambda _document: invalid)
        item = list_items(self.meeting_id)["items"][0]

        self.assertFalse(item["evidence_valid"])
        with self.assertRaisesRegex(ValueError, "evidence"):
            change_item(item["id"], item["version"], {"review_status": "approved"})

        corrected = change_item(
            item["id"],
            item["version"],
            {
                "evidence": [
                    {
                        "source_unit_id": "line-1",
                        "quote": "Rahul will send the revised API spec tomorrow.",
                    }
                ]
            },
        )
        self.assertTrue(corrected["evidence_valid"])
        approved = change_item(
            corrected["id"],
            corrected["version"],
            {"review_status": "approved"},
        )
        self.assertEqual(approved["review_status"], "approved")

    def test_editing_invalidates_approval_and_csv_exports_only_approved(self):
        extract_and_save(self.meeting_id, lambda _document: self.fixture)
        items = list_items(self.meeting_id)["items"]
        action, decision = items
        approved = change_item(
            action["id"], action["version"], {"review_status": "approved"}
        )

        exported = export_csv(self.meeting_id)
        rows = list(csv.reader(io.StringIO(exported)))
        self.assertEqual(len(rows), 2)
        self.assertIn("Send the revised API spec", exported)
        self.assertNotIn("Ship Friday", exported)

        changed = change_item(
            action["id"], approved["version"], {"description": "Send validated spec"}
        )
        self.assertEqual(changed["review_status"], "draft")
        self.assertNotIn("Send validated spec", export_csv(self.meeting_id))
        self.assertEqual(decision["review_status"], "draft")

    def test_failed_regeneration_preserves_previous_reviewed_run(self):
        first_run = extract_and_save(self.meeting_id, lambda _document: self.fixture)
        item = list_items(self.meeting_id, first_run)["items"][0]
        change_item(item["id"], item["version"], {"review_status": "approved"})

        def fail(_document):
            raise RuntimeError("simulated Gemini outage")

        with self.assertRaises(RuntimeError):
            extract_and_save(self.meeting_id, fail)

        runs = list_runs(self.meeting_id)
        self.assertEqual([run["id"] for run in runs], [first_run])
        self.assertEqual(
            list_items(self.meeting_id, first_run)["items"][0]["review_status"],
            "approved",
        )

    def test_malformed_output_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_output(
                {"actions": "not-a-list", "decisions": [], "follow_ups": []},
                source_document(self.meeting_id),
            )

    def test_long_notes_are_chunked_and_duplicate_items_are_merged(self):
        lines = [f"line {index} " + ("x" * 990) for index in range(45)]
        meeting_id = create_notes("Long fictional meeting", "\n".join(lines))
        calls = []

        def extractor(document):
            calls.append(document)
            first = document["units"][0]
            return {
                "actions": [
                    {
                        "description": "Prepare the shared demo",
                        "owner": None,
                        "due_date_text": None,
                        "evidence": [
                            {
                                "source_unit_id": first["id"],
                                "quote": first["text"][:30],
                            }
                        ],
                    }
                ],
                "decisions": [],
                "follow_ups": [],
            }

        extract_and_save(meeting_id, extractor)
        result = list_items(meeting_id)
        self.assertGreater(len(calls), 1)
        self.assertEqual(len(result["items"]), 1)
        self.assertGreater(len(result["items"][0]["evidence"]), 1)

    def test_missing_gemini_configuration_fails_before_import_or_write(self):
        before = len(list_runs(self.meeting_id))
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            with self.assertRaisesRegex(GeminiConfigurationError, "GEMINI_API_KEY"):
                model_extract(source_document(self.meeting_id))
        self.assertEqual(len(list_runs(self.meeting_id)), before)


class MeetingActionsApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = database.DB_PATH
        database.DB_PATH = Path(self.temp_dir.name) / "meeting_ai.db"

    def tearDown(self):
        database.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def test_router_is_registered_and_validates_notes(self):
        from api.main import app

        paths = {route.path for route in app.routes}
        self.assertIn("/api/actions/notes", paths)
        self.assertIn("/api/actions/meetings/{meeting_id}/extract", paths)
        self.assertIn("/api/actions/meetings/{meeting_id}/context", paths)

        with TestClient(app) as client:
            response = client.post("/api/actions/notes", json={"title": "", "text": ""})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
