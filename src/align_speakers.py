#align_speakers.py
def calculate_overlap(start1, end1, start2, end2):
    overlap_start = max(start1, start2)
    overlap_end = min(end1, end2)
    return max(0, overlap_end - overlap_start)


def find_best_speaker(transcript_segment, speaker_segments):
    best_speaker = "UNKNOWN"
    best_overlap = 0

    t_start = transcript_segment["start"]
    t_end = transcript_segment["end"]

    for speaker_segment in speaker_segments:
        s_start = speaker_segment["start"]
        s_end = speaker_segment["end"]

        overlap = calculate_overlap(t_start, t_end, s_start, s_end)

        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = speaker_segment["speaker"]

    return best_speaker


def build_speaker_transcript(transcript_segments, speaker_segments):
    final_lines = []

    for segment in transcript_segments:
        speaker = find_best_speaker(segment, speaker_segments)

        line = {
            "start": segment["start"],
            "end": segment["end"],
            "speaker": speaker,
            "text": segment["text"],
        }

        final_lines.append(line)

    return final_lines


def format_speaker_transcript(speaker_transcript):
    lines = []

    for item in speaker_transcript:
        line = (
            f"[{item['start']} - {item['end']}] "
            f"{item['speaker']}: {item['text']}"
        )
        lines.append(line)

    return "\n".join(lines)
def merge_consecutive_speaker_lines(speaker_transcript):
    if not speaker_transcript:
        return []

    merged = [speaker_transcript[0]]

    for current in speaker_transcript[1:]:
        previous = merged[-1]

        same_speaker = current["speaker"] == previous["speaker"]
        close_enough = current["start"] - previous["end"] <= 1.0

        if same_speaker and close_enough:
            previous["end"] = current["end"]
            previous["text"] = previous["text"] + " " + current["text"]
        else:
            merged.append(current)

    return merged

def replace_speaker_labels_with_names(speaker_transcript, speaker_label_to_name):
    updated = []

    for item in speaker_transcript:
        speaker_label = item["speaker"]
        speaker_info  = speaker_label_to_name.get(speaker_label)

        if speaker_info:
            name       = speaker_info["name"]
            confidence = speaker_info["confidence"]
            best_guess = speaker_info.get("best_guess")
            tier       = speaker_info.get("tier", "low")

            if name != "UNKNOWN":
                # High confidence — show name + confidence
                display_speaker = f"{name} ({confidence})"

            elif tier == "medium" and best_guess:
                # Medium confidence — show unknown + best guess
                display_speaker = f"UNKNOWN (best: {best_guess}, conf: {confidence})"

            else:
                # Low confidence — just show UNKNOWN + confidence, no name
                display_speaker = f"UNKNOWN (conf: {confidence})"
        else:
            display_speaker = speaker_label

        updated.append({**item, "speaker": display_speaker})

    return updated

def format_clean_transcript(speaker_transcript):
    lines = []

    for item in speaker_transcript:
        line = f"{item['speaker']}: {item['text']}"
        lines.append(line)

    return "\n".join(lines)