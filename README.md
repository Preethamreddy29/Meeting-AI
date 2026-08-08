# Meeting AI — Local Voice Recognition & Meeting Intelligence

A fully local, private AI system that transcribes meeting recordings,
identifies who spoke what, and generates intelligent summaries.
No paid APIs. Runs entirely on your own machine.

---

## What it does

- **Speaker Enrollment** — Feed 30 sec voice samples per person
- **Auto Transcription** — Whisper converts speech to text
- **Speaker Identification** — Knows who said what from voice alone
- **Meeting Summary** — LLM generates summary, action items, sentiment
- **Chat** — Ask anything about your meetings in plain English
- **Web UI** — Full React interface, no terminal needed

---

## Demo

> Upload a meeting recording → get a named transcript in minutes

[00:00:00] Preetham (0.934): Good morning, let's get started.
[00:00:26] Rahul (0.911) : Sure, I have the numbers ready.
[00:01:10] UNKNOWN (0.038) : I think we should postpone that.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Transcription | faster-whisper (OpenAI Whisper, int8 CPU) |
| Diarization | pyannote.audio 3.1 |
| Speaker ID | SpeechBrain ECAPA-TDNN |
| Local LLM | Ollama + llama3.2:3b |
| Database | SQLite |
| Backend API | FastAPI + uvicorn |
| Frontend | React + Vite |
| Audio processing | ffmpeg + soundfile |

---

## Hardware Requirements

- CPU: Any modern processor (tested on Intel i5-1235U)
- RAM: 8GB minimum, 16GB recommended
- GPU: Not required — fully CPU compatible
- Storage: ~5GB for models

---

## Installation

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/meeting-ai.git
cd meeting-ai
```

### 2. Create virtual environment
```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Mac/Linux
```

### 3. Install Python dependencies
```bash
pip install faster-whisper
pip install pyannote.audio
pip install speechbrain
pip install soundfile numpy
pip install python-dotenv
pip install fastapi uvicorn python-multipart aiofiles
pip install ollama
pip install transformers
```

### 4. Install system dependencies
- [ffmpeg](https://ffmpeg.org/download.html) — add to PATH
- [Ollama](https://ollama.com/download) — install and run

### 5. Download LLM model
```bash
ollama pull llama3.2:3b
```

### 6. Set up environment variables
Create a `.env` file:

HF_TOKEN=your_huggingface_token_here

Get your free token at: https://huggingface.co/settings/tokens
Accept pyannote model license at: https://huggingface.co/pyannote/speaker-diarization-3.1

### 7. Install React frontend
```bash
cd meeting-ai-ui
npm install
cd ..
```

---

## Running the system

**Terminal 1 — Backend:**
```bash
.venv\Scripts\activate
uvicorn api.main:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd meeting-ai-ui
npm run dev
```

Open: http://localhost:5173

---

## How to use

1. Go to Enroll page → upload voice samples for each team member
2. Go to Process page → upload a meeting recording
3. Go to Transcripts → view named transcript
4. Go to Summary → generate AI meeting summary
5. Go to Chat → ask questions about your meetings

---

## Architecture

Voice Enrollment
└── ECAPA-TDNN → 192D voice embedding → SQLite

Meeting Processing
└── ffmpeg → Whisper → pyannote → ECAPA matching
└── Named transcript → SQLite → Report file

LLM Layer
└── Ollama (llama3.2:3b) → Summary + Chat

---

## Privacy

Everything runs locally on your machine.
No audio, transcript, or summary data is ever sent externally.
The only optional external call is the LLM API 
(replaceable with local Ollama — already default).

---

## Project Structure

meeting-ai/
├── api/main.py # FastAPI backend
├── app/main.py # Terminal modes
├── src/
│ ├── audio_preprocess.py
│ ├── transcribe.py
│ ├── diarize.py
│ ├── _diarize_worker.py # Isolated subprocess
│ ├── align_speakers.py
│ ├── recognize_speakers.py
│ ├── enroll_speakers.py
│ ├── database.py
│ ├── summarize.py
│ ├── chat.py
│ └── file_utils.py
├── meeting-ai-ui/ # React frontend
├── data/ # SQLite database (gitignored)
├── models/ # Downloaded AI models (gitignored)
└── voice_samples/ # Speaker audio (gitignored)

---

## Author

Preetham Reddy Saddi
[LinkedIn](https://linkedin.com/in/YOUR_PROFILE)