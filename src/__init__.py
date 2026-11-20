"""Shared runtime setup for the Meeting AI package."""

from __future__ import annotations

import sys
from typing import TextIO


def configure_console_streams(
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> None:
    """Prevent Windows console encodings from crashing background work.

    Some Windows terminals expose ``cp1252`` instead of UTF-8. Application status
    messages and user-controlled filenames may contain characters that encoding
    cannot represent. Reconfiguring the standard streams to replace unsupported
    display characters keeps processing alive without changing stored data.
    """

    streams = (
        sys.stdout if stdout is None else stdout,
        sys.stderr if stderr is None else stderr,
    )
    for stream in streams:
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(errors="replace")
        except (AttributeError, OSError, ValueError):
            # Captured or already-closed streams may reject reconfiguration.
            pass


configure_console_streams()
