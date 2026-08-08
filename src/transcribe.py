#transcribe.py
from faster_whisper import WhisperModel


def transcribe_audio(audio_path: str):
    print("Loading Whisper model...")

    model = WhisperModel(
        "small",
        compute_type="int8",
    )

    print("Transcribing...")

    segments, info = model.transcribe(audio_path)

    transcript_segments = []
    full_text = ""

    for segment in segments:
        item = {
            "start": round(segment.start, 2),
            "end": round(segment.end, 2),
            "text": segment.text.strip(),
        }

        transcript_segments.append(item)

        line = f"[{item['start']} - {item['end']}] {item['text']}"
        print(line)
        full_text += line + "\n"

    return transcript_segments, full_text