# src/_diarize_worker.py
# This script runs in its own Python process — completely isolated from
# the main process. Fixes PyTorch kernel conflict with ECAPA-TDNN.

import sys
import os
import json
import types

# ── Patches must come before any torch/pyannote imports ──────────────────────
if "k2" not in sys.modules:
    sys.modules["k2"] = types.ModuleType("k2")

import warnings
warnings.filterwarnings("ignore")

os.environ["TORCHAUDIO_USE_SOX"] = "0"

# Add project root to path so imports work
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

import numpy as np
import soundfile as sf
import torch
from dotenv import load_dotenv
from pyannote.audio import Pipeline


def main():
    if len(sys.argv) < 2:
        print("Usage: _diarize_worker.py <audio_path>", file=sys.stderr)
        sys.exit(1)

    audio_path = sys.argv[1]

    load_dotenv()
    hf_token = os.getenv("HF_TOKEN")

    if not hf_token:
        print("HF_TOKEN not found in .env file", file=sys.stderr)
        sys.exit(1)

    # Load pipeline
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        token=hf_token,
    )

    # Load audio
    audio_data, sample_rate = sf.read(audio_path)
    if len(audio_data.shape) > 1:
        audio_data = np.mean(audio_data, axis=1)

    waveform = torch.tensor(audio_data, dtype=torch.float32).unsqueeze(0)

    # Run diarization
    diarization = pipeline(
        {"waveform": waveform, "sample_rate": sample_rate}
    )

    annotation = diarization.speaker_diarization

    speaker_segments = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        speaker_segments.append({
            "start":   round(turn.start, 2),
            "end":     round(turn.end, 2),
            "speaker": speaker,
        })

    # Print JSON to stdout — parent process reads this
    print(json.dumps(speaker_segments))
    sys.exit(0)


if __name__ == "__main__":
    main()