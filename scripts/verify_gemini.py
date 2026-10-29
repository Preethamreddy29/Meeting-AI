"""Optional live Gemini smoke test using fictional notes only.

Run from the repository root after configuring GEMINI_API_KEY:
    .venv\Scripts\python.exe scripts\verify_gemini.py
"""

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.meeting_actions import (  # noqa: E402
    MeetingActionError,
    model_extract,
    validate_output,
)


load_dotenv(ROOT / ".env")


def main() -> int:
    if not os.getenv("GEMINI_API_KEY", "").strip():
        print("GEMINI_API_KEY is not configured. Copy .env.example to .env and add it.")
        return 2

    document = {
        "meeting_id": 0,
        "title": "Fictional Gemini verification",
        "source_type": "notes",
        "meeting_date": "2026-10-27",
        "timezone": "Asia/Kolkata",
        "units": [
            {
                "id": "line-1",
                "text": "Asha will send the fictional launch checklist tomorrow.",
            },
            {
                "id": "line-2",
                "text": "The team agreed to run a synthetic demo on Friday.",
            },
        ],
    }
    try:
        output, model = model_extract(document)
    except MeetingActionError as exc:
        print(f"Live Gemini verification failed [{exc.code}]: {exc}")
        return 1
    validated = validate_output(output, document)
    print(f"Live Gemini verification succeeded with model: {model}")
    print(json.dumps(validated, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
