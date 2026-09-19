# src/recognize_speakers.py
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from speechbrain.inference.speaker import EncoderClassifier
from speechbrain.utils.fetching import LocalStrategy

from src.database import load_all_speaker_profiles

HIGH_CONFIDENCE_THRESHOLD   = 0.80
HIGH_CONFIDENCE_MARGIN      = 0.08
MEDIUM_CONFIDENCE_THRESHOLD = 0.70
MEDIUM_CONFIDENCE_MARGIN    = 0.05
MIN_SEGMENT_DURATION        = 1.5
SHORT_SEGMENT_THRESHOLD     = 3.0
MIN_GUESS_DISPLAY_THRESHOLD = 0.50


def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    if denominator == 0:
        return 0.0
    return float(np.dot(a, b) / denominator)


def load_ecapa_model():
    return EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir="models/spkrec-ecapa-voxceleb",
        local_strategy=LocalStrategy.COPY,
    )


def extract_embedding_from_audio(classifier, audio_data):
    signal = torch.tensor(audio_data, dtype=torch.float32).unsqueeze(0)
    with torch.no_grad():
        embedding = classifier.encode_batch(signal)
    return embedding.squeeze().detach().cpu().numpy()


def extract_audio_chunk(audio_path, start, end):
    audio_data, sample_rate = sf.read(audio_path)
    if len(audio_data.shape) > 1:
        audio_data = np.mean(audio_data, axis=1)
    start_sample = int(start * sample_rate)
    end_sample   = int(end * sample_rate)
    return audio_data[start_sample:end_sample]


def apply_confidence_rules(best_score, second_score, duration):
    margin = best_score - second_score
    if duration < MIN_SEGMENT_DURATION:
        return "low"
    if duration < SHORT_SEGMENT_THRESHOLD:
        if best_score >= 0.85 and margin >= 0.10:
            return "high"
        return "low"
    if best_score >= HIGH_CONFIDENCE_THRESHOLD and margin >= HIGH_CONFIDENCE_MARGIN:
        return "high"
    if best_score >= MEDIUM_CONFIDENCE_THRESHOLD and margin >= MEDIUM_CONFIDENCE_MARGIN:
        return "medium"
    return "low"


def match_embedding_to_speaker(embedding, profiles, duration):
    if not profiles:
        return {
            "name": "UNKNOWN",
            "best_guess": None,
            "confidence": 0.0,
            "margin": 0.0,
            "tier": "low",
        }
    scores = {
        name: cosine_similarity(embedding, profile["embedding"])
        for name, profile in profiles.items()
    }
    sorted_speakers = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_name,   best_score   = sorted_speakers[0]
    second_name, second_score = sorted_speakers[1] if len(sorted_speakers) > 1 else ("UNKNOWN", 0.0)

    tier   = apply_confidence_rules(best_score, second_score, duration)
    margin = round(best_score - second_score, 3)

    if tier == "high":
        return {
            "name": best_name, "best_guess": best_name,
            "confidence": round(best_score, 3),
            "margin": margin, "tier": "high",
        }
    if tier == "medium":
        return {
            "name": "UNKNOWN", "best_guess": best_name,
            "confidence": round(best_score, 3),
            "margin": margin, "tier": "medium",
        }

    show_guess = best_score >= MIN_GUESS_DISPLAY_THRESHOLD
    return {
        "name": "UNKNOWN",
        "best_guess": best_name if show_guess else None,
        "confidence": round(best_score, 3),
        "margin": margin, "tier": "low",
    }


def recognize_diarized_speakers(audio_path, speaker_segments):
    print("Loading speaker profiles from database...")
    profiles = load_all_speaker_profiles()   # ← reads from DB now

    if not profiles:
        print("No enrolled speaker profiles found; keeping all speakers UNKNOWN.")
        return {
            segment["speaker"]: {
                "name": "UNKNOWN",
                "best_guess": None,
                "confidence": 0.0,
                "margin": 0.0,
                "tier": "low",
            }
            for segment in speaker_segments
        }

    print("Loading ECAPA model for recognition...")
    classifier = load_ecapa_model()

    speaker_label_to_segments = {}
    for segment in speaker_segments:
        label    = segment["speaker"]
        duration = segment["end"] - segment["start"]
        if duration < MIN_SEGMENT_DURATION:
            continue
        if label not in speaker_label_to_segments:
            speaker_label_to_segments[label] = []
        speaker_label_to_segments[label].append(segment)

    speaker_label_to_name = {}

    for label, segments in speaker_label_to_segments.items():
        print(f"\nProcessing {label} across {len(segments)} segment(s)...")
        embeddings     = []
        total_duration = 0.0

        for segment in segments:
            start    = segment["start"]
            end      = segment["end"]
            duration = end - start
            chunk     = extract_audio_chunk(audio_path, start, end)
            if chunk.size == 0:
                continue
            embedding = extract_embedding_from_audio(classifier, chunk)
            embeddings.append(embedding)
            total_duration += duration
            print(f"  Extracted [{start}s - {end}s] ({round(duration,2)}s)")

        if not embeddings:
            speaker_label_to_name[label] = {
                "name": "UNKNOWN",
                "best_guess": None,
                "confidence": 0.0,
                "margin": 0.0,
                "tier": "low",
            }
            continue

        avg_embedding = np.mean(embeddings, axis=0)
        result = match_embedding_to_speaker(avg_embedding, profiles, total_duration)
        speaker_label_to_name[label] = result

        print(
            f"{label} -> {result['name']} "
            f"(confidence: {result['confidence']}, "
            f"margin: {result['margin']}, tier: {result['tier']})"
        )

    return speaker_label_to_name
