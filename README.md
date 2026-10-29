# Meeting AI

Meeting AI is a Windows application for transcribing recorded meetings, aligning
speakers, reviewing transcripts, generating Gemini summaries, asking questions about
stored meetings, and producing source-backed actions for human review.

## What is local and what is sent to Google

Audio conversion, Whisper transcription, diarization, speaker recognition, and
SQLite storage remain local. The FastAPI backend sends relevant transcript or note
text to Google only when the user requests a Gemini Summary, Chat answer, or Actions
extraction. The original audio is not sent to Gemini by these workflows.

Do not use confidential meeting material unless your organization's data policy
permits it. API keys remain on the FastAPI backend and are never included in the
React bundle, URLs, CSV exports, or application logs.

## Application structure

- `api/main.py` — FastAPI application and background jobs
- `src/` — SQLite helpers, local audio pipeline, summaries, chat, and action extraction
- `meeting-ai-ui/` — React/Vite frontend
- `data/meeting_ai.db` — ignored local SQLite database
- `audio/`, `voice_samples/`, `outputs/` — ignored/private local artifacts
- `tests/` — backend unit and integration tests using temporary databases

## Windows setup

Use Python 3.10 and run commands from the repository root in PowerShell.

```powershell
py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-core.txt
python -m pip install -r requirements-gemini.txt
python -m pip install -r requirements-test.txt
```

The local audio/model pipeline is optional and substantially larger:

```powershell
python -m pip install -r requirements-audio.txt
```

Install `ffmpeg` separately and ensure it is available on `PATH` when processing
audio. No separate local language-model server is required.

Install frontend packages:

```powershell
cd meeting-ai-ui
npm ci
cd ..
```

## Backend configuration

Copy the placeholder file and fill only the ignored copy:

```powershell
Copy-Item .env.example .env
```

`api/main.py` explicitly loads the project-root `.env` with `python-dotenv`. You can
instead set the values in the backend PowerShell session:

```powershell
$env:GEMINI_API_KEY = "your-key"
$env:GEMINI_MODEL = "gemini-3.5-flash-lite"
$env:HF_TOKEN = "your-hugging-face-token"
```

- `GEMINI_API_KEY` is required for Actions extraction, Summary, and Chat.
- `GEMINI_MODEL` is configurable. Check current model availability, quota, privacy,
  and billing status in Google AI Studio before use. The application does not enable
  billing or fall back to another provider.
- `HF_TOKEN` is required by the optional diarization worker for accepted gated models.

The real `.env` and `.env.*` files are ignored; `.env.example` is intentionally safe
to commit.

## Start the application

Terminal 1 — backend:

```powershell
.venv\Scripts\Activate.ps1
uvicorn api.main:app --reload --port 8000
```

Terminal 2 — frontend:

```powershell
cd meeting-ai-ui
npm run dev
```

Open `http://localhost:5173`.

## Meeting-to-Action workflow

1. Open **Action center** in the meeting workflow navigation.
2. Paste meeting notes (or upload `.txt`/`.md`) and save them, or select a stored
   meeting whose transcript has already been processed.
3. Optionally provide or update the meeting date and an IANA timezone such as
   `Asia/Kolkata`, including for stored audio transcripts.
4. Click **Extract with Gemini**.
5. Review every action, decision, follow-up, and its exact supporting quotation.
   Transcript sources include timestamps when available.
6. Edit descriptions, owners, or original due-date wording and save. Missing values
   stay visibly **Unspecified**. Editing an approved item returns it to draft.
7. Resolve an unsupported item by selecting the correct source unit and copying an
   exact quotation, or reject it. Unsupported items cannot be approved.
8. Approve items individually, then download the CSV. Only approved items from the
   selected extraction run are exported.

Each regeneration creates a new run. Existing reviewed and approved runs are retained
and selectable; the UI asks for confirmation before regenerating a meeting with
reviewed work. A failed Gemini request saves no new run.

Relative due dates retain the model's original wording. `today`, `tomorrow`, `in N
days`, and `next <weekday>` are resolved only when both a meeting date and valid
timezone were supplied. Other unresolved relative wording is flagged for review.

Sources up to 250,000 characters are split into bounded Gemini requests. Duplicate
items with the same normalized description and category are merged across chunks,
including distinct supporting quotations.

## Verification

Verified on 2026-10-30 in the local Windows checkout:

- Backend tests pass using temporary SQLite databases and mocked Gemini output.
- The Vite production build and ESLint checks passed.
- The complete npm production/development dependency audit reported zero
  vulnerabilities after dependency updates.
- Browser-to-backend checks passed for saving fictional notes, loading a review run,
  editing, approval invalidation, reapproval, and approved-only CSV export.
- Missing Gemini configuration was verified to fail clearly without saving a run.
- A live Gemini structured extraction request passed with fictional notes.
- The local audio/model pipeline was not exercised end to end during this change.

Backend tests use temporary SQLite files and mocked Gemini responses:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Frontend checks:

```powershell
npm run build --prefix meeting-ai-ui
npm run lint --prefix meeting-ai-ui
```

GitHub Actions runs the same backend tests, dependency checks, frontend lint,
production build, and production dependency audit for the feature branch and pull
requests. The optional audio/model requirements are not installed in CI; audio-only
imports stay lazy so the core test suite remains lightweight.

No automated test sends meeting content to Gemini. A live Gemini check requires a
configured key and should use fictional notes only:

```powershell
.venv\Scripts\python.exe scripts\verify_gemini.py
```

See `docs/meeting-actions-demo.md` and `examples/fictional_meeting_notes.txt` for a
repeatable assignment demonstration that contains no real meeting information.

## Known limitations

- This is a single-user local application without server authentication.
- Meeting-to-Action extraction has a 250,000-character safety limit per run. Chunk
  merging uses normalized descriptions and may still require human duplicate review.
- Only explicit source-quotation presence is checked automatically. Human review is
  still required to verify meaning, ownership, and due dates.
- Relative date resolution intentionally handles a small, deterministic set of phrases.
- Audio quality, speaker recognition, Gemini availability, model access, free-tier
  eligibility, quotas, and privacy terms depend on the local machine and external
  accounts.
