#check_voice_samples.py
from pathlib import Path

from src.audio_preprocess import convert_to_wav
from src.transcribe import transcribe_audio


VOICE_SAMPLES_DIR = Path("voice_samples")
CHECK_OUTPUT_DIR = Path("outputs/voice_sample_checks")


def check_voice_samples():
    CHECK_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for speaker_folder in VOICE_SAMPLES_DIR.iterdir():
        if not speaker_folder.is_dir():
            continue

        speaker_name = speaker_folder.name
        print(f"\nChecking speaker: {speaker_name}")

        for sample_file in speaker_folder.iterdir():
            if sample_file.suffix.lower() not in [".mp3", ".wav", ".ogg", ".mp4", ".m4a"]:
                continue

            print(f"\nSample: {sample_file.name}")

            wav_path = CHECK_OUTPUT_DIR / f"{speaker_name}_{sample_file.stem}.wav"
            transcript_path = CHECK_OUTPUT_DIR / f"{speaker_name}_{sample_file.stem}.txt"

            convert_to_wav(str(sample_file), str(wav_path))

            transcript_segments, transcript_text = transcribe_audio(str(wav_path))

            with open(transcript_path, "w", encoding="utf-8") as file:
                file.write(transcript_text)

            print(f"Saved check transcript: {transcript_path}")