# src/diarize.py
import sys
import os
import json
import subprocess
from pathlib import Path


def diarize_audio(audio_path: str):
    """
    Runs pyannote diarization in a completely separate subprocess.
    This permanently fixes the PyTorch kernel conflict with ECAPA.
    """
    print("Running speaker diarization in isolated subprocess...")

    # Path to the worker script
    worker_script = Path(__file__).parent / "_diarize_worker.py"

    result = subprocess.run(
        [sys.executable, str(worker_script), audio_path],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("Diarization worker error:")
        print(result.stderr)
        raise RuntimeError(
            f"Diarization failed: {result.stderr[-500:]}"
        )

    # Parse JSON output from worker
    try:
        speaker_segments = json.loads(result.stdout)
        print(f"  Found {len(speaker_segments)} segments")
        return speaker_segments
    except json.JSONDecodeError:
        print("Worker stdout:", result.stdout)
        print("Worker stderr:", result.stderr)
        raise RuntimeError("Diarization worker returned invalid output")