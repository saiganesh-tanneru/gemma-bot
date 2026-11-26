"""Tiny WAV helpers shared by the speaker drivers. No audio device access."""

from __future__ import annotations

import io
import wave
from typing import Optional


def wav_duration_seconds(wav_bytes: bytes) -> Optional[float]:
    """Return the duration of a WAV payload, or None if it is not a WAV."""
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            if rate > 0:
                return frames / float(rate)
    except Exception:
        return None
    return None
