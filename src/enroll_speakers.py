# src/enroll_speakers.py
import json
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from speechbrain.inference.speaker import EncoderClassifier
from speechbrain.utils.fetching import LocalStrategy

from src.audio_preprocess import convert_to_wav
from src.database import init_db, upsert_speaker, insert_voice_sample

VOICE_SAMPLES_DIR    = Path("voice_samples")
PROCESSED_SAMPLES_DIR = Path("audio/processed/voice_samples")


def extract_embedding(classifier, audio_path: str):
    audio_data, sample_rate = sf.read(audio_path)
    if len(audio_data.shape) > 1:
        audio_data = np.mean(audio_data, axis=1)
    signal = torch.tensor(audio_data, dtype=torch.float32).unsqueeze(0)
    with torch.no_grad():
        embedding = classifier.encode_batch(signal)
    return embedding.squeeze().detach().cpu().numpy()


def enroll_speakers():
    init_db()

    print("Loading ECAPA speaker embedding model...")
    classifier = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir="models/spkrec-ecapa-voxceleb",
        local_strategy=LocalStrategy.COPY,
    )

    for speaker_folder in VOICE_SAMPLES_DIR.iterdir():
        if not speaker_folder.is_dir():
            continue

        speaker_name = speaker_folder.name
        print(f"\nEnrolling speaker: {speaker_name}")

        embeddings  = []
        sample_paths = []

        for sample_file in speaker_folder.iterdir():
            if sample_file.suffix.lower() not in [
                ".mp3", ".wav", ".ogg", ".mp4", ".m4a"
            ]:
                continue

            output_folder = PROCESSED_SAMPLES_DIR / speaker_name
            output_folder.mkdir(parents=True, exist_ok=True)
            wav_path = output_folder / f"{sample_file.stem}.wav"

            convert_to_wav(str(sample_file), str(wav_path))

            embedding = extract_embedding(classifier, str(wav_path))
            embeddings.append(embedding)
            sample_paths.append(str(sample_file))

            print(f"  Processed: {sample_file.name}")

        if not embeddings:
            continue

        # Average all embeddings → one profile per speaker
        avg_embedding = np.mean(embeddings, axis=0)

        # Save to database
        speaker_id = upsert_speaker(
            name=speaker_name,
            embedding=avg_embedding.tolist(),
            num_samples=len(embeddings),
        )

        # Save each sample file path
        for path in sample_paths:
            insert_voice_sample(
                speaker_id=speaker_id,
                file_path=path,
            )

    print("\n✅ All speakers enrolled into database.")

def enroll_single_speaker(speaker_name: str):
    """
    Enroll or re-enroll only one specific speaker.
    Used by the UI when uploading samples for one person.
    """
    from src.database import init_db, upsert_speaker, insert_voice_sample
    init_db()

    speaker_folder = VOICE_SAMPLES_DIR / speaker_name

    if not speaker_folder.exists():
        raise ValueError(f"No voice_samples folder found for: {speaker_name}")

    print(f"Loading ECAPA model...")
    classifier = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir="models/spkrec-ecapa-voxceleb",
        local_strategy=LocalStrategy.COPY,
    )

    print(f"Enrolling: {speaker_name}")
    embeddings   = []
    sample_paths = []

    for sample_file in speaker_folder.iterdir():
        if sample_file.suffix.lower() not in [
            ".mp3", ".wav", ".ogg", ".mp4", ".m4a"
        ]:
            continue

        output_folder = PROCESSED_SAMPLES_DIR / speaker_name
        output_folder.mkdir(parents=True, exist_ok=True)
        wav_path = output_folder / f"{sample_file.stem}.wav"

        convert_to_wav(str(sample_file), str(wav_path))

        embedding = extract_embedding(classifier, str(wav_path))
        embeddings.append(embedding)
        sample_paths.append(str(sample_file))

        print(f"  Processed: {sample_file.name}")

    if not embeddings:
        raise ValueError(f"No valid audio files found for: {speaker_name}")

    avg_embedding = np.mean(embeddings, axis=0)

    speaker_id = upsert_speaker(
        name=speaker_name,
        embedding=avg_embedding.tolist(),
        num_samples=len(embeddings),
    )

    for path in sample_paths:
        insert_voice_sample(
            speaker_id=speaker_id,
            file_path=path,
        )

    print(f"✅ Enrolled: {speaker_name} ({len(embeddings)} samples)")
    return speaker_id