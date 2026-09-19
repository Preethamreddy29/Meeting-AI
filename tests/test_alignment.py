import unittest

from src.align_speakers import (
    align_transcript_segments,
    merge_consecutive_speaker_lines,
)


class TranscriptAlignmentTests(unittest.TestCase):
    def test_assigns_speaker_with_largest_overlap(self):
        transcript = [{
            "start": 2.0,
            "end": 6.0,
            "text": "Hello everyone",
        }]

        speakers = [
            {"start": 0.0, "end": 3.0, "speaker": "SPEAKER_00"},
            {"start": 3.0, "end": 8.0, "speaker": "SPEAKER_01"},
        ]

        result = align_transcript_segments(transcript, speakers)

        self.assertEqual(result[0]["speaker"], "SPEAKER_01")
        self.assertTrue(result[0]["is_overlap"])

    def test_keeps_text_when_no_speaker_overlaps(self):
        transcript = [{
            "start": 10.0,
            "end": 12.0,
            "text": "Unmatched speech",
        }]

        result = align_transcript_segments(transcript, [])

        self.assertEqual(result[0]["speaker"], "UNKNOWN")
        self.assertEqual(result[0]["text"], "Unmatched speech")
        self.assertFalse(result[0]["is_overlap"])

    def test_does_not_merge_overlap_segments(self):
        segments = [
            {
                "start": 0.0,
                "end": 2.0,
                "speaker": "SPEAKER_00",
                "text": "First",
                "is_overlap": False,
            },
            {
                "start": 2.2,
                "end": 4.0,
                "speaker": "SPEAKER_00",
                "text": "Second",
                "is_overlap": True,
            },
        ]

        result = merge_consecutive_speaker_lines(segments)

        self.assertEqual(len(result), 2)

    def test_merge_does_not_modify_original_segments(self):
        segments = [
            {
                "start": 0.0,
                "end": 2.0,
                "speaker": "SPEAKER_00",
                "text": "First",
                "is_overlap": False,
            },
            {
                "start": 2.2,
                "end": 4.0,
                "speaker": "SPEAKER_00",
                "text": "Second",
                "is_overlap": False,
            },
        ]

        merge_consecutive_speaker_lines(segments)

        self.assertEqual(segments[0]["text"], "First")
        self.assertEqual(segments[0]["end"], 2.0)


if __name__ == "__main__":
    unittest.main()