import io
import unittest

from src import configure_console_streams


class ConsoleCompatibilityTests(unittest.TestCase):
    def test_cp1252_console_replaces_unsupported_status_characters(self):
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")

        configure_console_streams(stream, stream)
        stream.write("Converted: \u2705")
        stream.flush()

        self.assertEqual(stream.errors, "replace")
        self.assertIn(b"Converted:", raw.getvalue())

    def test_captured_stream_without_reconfigure_is_supported(self):
        stream = io.StringIO()

        configure_console_streams(stream, stream)
        stream.write("still available")

        self.assertEqual(stream.getvalue(), "still available")


if __name__ == "__main__":
    unittest.main()
