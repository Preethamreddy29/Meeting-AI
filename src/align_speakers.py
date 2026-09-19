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

def align_transcript_segments(transcript_segments, speaker_segments):
    """
    Assign each Whisper transcript segment to the diarization speaker
    with the greatest time overlap.

    Transcript segments are the source of truth, ensuring that spoken
    text is not silently dropped when diarization boundaries differ.
    """
    aligned = []

    for transcript in transcript_segments:
        overlaps = []

        for speaker_segment in speaker_segments:
            overlap = calculate_overlap(
                transcript["start"],
                transcript["end"],
                speaker_segment["start"],
                speaker_segment["end"],
            )

            if overlap > 0:
                overlaps.append((overlap, speaker_segment))

        if overlaps:
            overlaps.sort(key=lambda item: item[0], reverse=True)
            best_segment = overlaps[0][1]
            speaker = best_segment["speaker"]

            overlapping_speakers = {
                segment["speaker"]
                for overlap, segment in overlaps
                if overlap > 0
            }
            is_overlap = len(overlapping_speakers) > 1
        else:
            speaker = "UNKNOWN"
            is_overlap = False

        aligned.append({
            "start": transcript["start"],
            "end": transcript["end"],
            "speaker": speaker,
            "text": transcript["text"].strip(),
            "is_overlap": is_overlap,
        })

    return aligned

def build_speaker_transcript(transcript_segments, speaker_segments):
    return align_transcript_segments(
        transcript_segments,
        speaker_segments,
    )


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

    merged = [speaker_transcript[0].copy()]

    for current in speaker_transcript[1:]:
        previous = merged[-1]

        same_speaker = current["speaker"] == previous["speaker"]
        close_enough = current["start"] - previous["end"] <= 1.0
        has_overlap = current.get("is_overlap") or previous.get("is_overlap")

        if same_speaker and close_enough and not has_overlap:
            previous["end"] = current["end"]
            previous["text"] = previous["text"] + " " + current["text"]
        else:
            merged.append(current.copy())

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