"""Pure-Python synthesized chirp generator and pluggable audio playback."""

from abc import ABC, abstractmethod
import io
import math
import os
import struct
import subprocess
import sys
import tempfile
import wave
from typing import List, Optional

from emotion_engine.presets import ChirpSpec


def synthesize_chirp_wav(spec: ChirpSpec, sample_rate: int = 16000) -> bytes:
    """Renders a ChirpSpec into 16-bit mono PCM WAV bytes with smooth fade envelopes."""
    total_samples = max(1, int(sample_rate * max(20, spec.duration_ms) / 1000.0))
    freqs = spec.freqs_hz if spec.freqs_hz else (440,)
    samples: List[int] = []
    phase = 0.0
    amp = max(0.0, min(1.0, spec.volume)) * 32767.0

    for i in range(total_samples):
        u = i / max(1, total_samples - 1)
        if spec.pattern in ("sweep", "sigh"):
            f0, f1 = freqs[0], freqs[-1]
            freq = f0 + (f1 - f0) * u
        elif spec.pattern in ("arpeggio", "chime", "trill"):
            seg = min(len(freqs) - 1, int(u * len(freqs)))
            freq = float(freqs[seg])
        else:
            freq = float(freqs[0])

        phase += 2.0 * math.pi * freq / sample_rate
        raw = math.sin(phase)
        if spec.waveform == "square":
            raw = 0.65 if raw >= 0.0 else -0.65

        # Smooth 12 ms fade-in / fade-out envelope prevents speaker clicks
        fade_samples = min(total_samples // 4, int(sample_rate * 0.012))
        env = 1.0
        if fade_samples > 0:
            if i < fade_samples:
                env = i / fade_samples
            elif i >= total_samples - fade_samples:
                env = (total_samples - 1 - i) / fade_samples
        samples.append(int(max(-32767, min(32767, raw * env * amp))))

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack("<" + "h" * len(samples), *samples))
    return buf.getvalue()


class ChirpPlayer(ABC):
    """Pluggable playback backend for synthesized emotion chirps."""

    @abstractmethod
    def play(self, spec: Optional[ChirpSpec]) -> None:
        """Plays the given ChirpSpec non-blockingly."""

    def close(self) -> None:
        """Releases any pending playback subprocesses."""


class NullChirpPlayer(ChirpPlayer):
    """No-op chirp player used in headless tests or muted environments."""

    def __init__(self) -> None:
        self.played: List[ChirpSpec] = []

    def play(self, spec: Optional[ChirpSpec]) -> None:
        if spec is not None:
            self.played.append(spec)


class MacAfplayChirpPlayer(ChirpPlayer):
    """Non-blocking macOS afplay chirp player using temporary WAV synthesis."""

    def __init__(self) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._tmp_path: Optional[str] = None

    def play(self, spec: Optional[ChirpSpec]) -> None:
        if spec is None:
            return
        self.close()
        wav_bytes = synthesize_chirp_wav(spec)
        fd, path = tempfile.mkstemp(prefix="chintu_chirp_", suffix=".wav")
        try:
            os.write(fd, wav_bytes)
        finally:
            os.close(fd)
        self._tmp_path = path
        self._proc = subprocess.Popen(
            ["afplay", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def close(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
        self._proc = None
        if self._tmp_path and os.path.exists(self._tmp_path):
            try:
                os.remove(self._tmp_path)
            except OSError:
                pass
        self._tmp_path = None


def create_chirp_player(enabled: Optional[bool] = None) -> ChirpPlayer:
    """Creates a platform-appropriate ChirpPlayer; muted under pytest or TTS_PROVIDER=null."""
    if enabled is None:
        if "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST"):
            enabled = False
        elif os.getenv("TTS_PROVIDER", "").strip().lower() == "null":
            enabled = False
        elif os.getenv("GEMMA_CHIRPS", "1").strip().lower() in ("0", "false", "no", "off"):
            enabled = False
        else:
            enabled = sys.platform == "darwin"

    if enabled and sys.platform == "darwin":
        return MacAfplayChirpPlayer()
    return NullChirpPlayer()
