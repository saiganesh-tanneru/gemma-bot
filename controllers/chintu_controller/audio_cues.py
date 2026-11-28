"""Chintu wake and reaction audio cues.

Only two cues exist in the wake ritual:
1. STIR CHIRP (synthesized): soft two-tone 'mm?' (E5 659 Hz -> G5 784 Hz, sine, 2 x 0.11 s, -14 dB).
2. BABY YAWN (file playback ONLY): assets/chintu-baby-yawn.wav trimmed from Sai's reference clip.
   Synthesis of the yawn is strictly forbidden.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import io
import math
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys
import tempfile
from typing import List, Optional, Tuple
import wave

REPO_ROOT = Path(__file__).resolve().parents[2]
BABY_YAWN_WAV_PATH = REPO_ROOT / "assets" / "chintu-baby-yawn.wav"

STIR_TONES_HZ: Tuple[float, float] = (659.25, 783.99)  # E5 -> G5
STIR_TONE_DURATION_S: float = 0.11
STIR_PEAK_DB: float = -14.0


def measure_wav_duration(wav_path: Path = BABY_YAWN_WAV_PATH) -> float:
    """Measures exact duration in seconds from a WAV file on disk."""
    path = Path(wav_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Required baby yawn asset missing at {path}. "
            "Provide Sai's reference clip trimmed to assets/chintu-baby-yawn.wav."
        )
    with wave.open(str(path), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        if rate <= 0 or frames <= 0:
            raise ValueError(f"Invalid WAV asset {path}: frames={frames}, rate={rate}")
        return frames / float(rate)


def _render_sine_sequence_wav(
    tones_hz: Tuple[float, ...],
    tone_duration_s: float,
    peak_db: float,
    sample_rate: int = 44100,
    fade_s: float = 0.012,
) -> bytes:
    """Renders a pure sine tone sequence into 16-bit mono PCM WAV bytes."""
    peak_amp = (10.0 ** (peak_db / 20.0)) * 32767.0
    samples: List[int] = []
    phase = 0.0
    per_tone_n = max(1, int(round(tone_duration_s * sample_rate)))
    fade_n = min(per_tone_n // 3, max(1, int(round(fade_s * sample_rate))))

    for freq in tones_hz:
        for i in range(per_tone_n):
            phase += 2.0 * math.pi * float(freq) / sample_rate
            env = 1.0
            if i < fade_n:
                env = i / float(fade_n)
            elif i >= per_tone_n - fade_n:
                env = (per_tone_n - 1 - i) / float(fade_n)
            val = math.sin(phase) * env * peak_amp
            samples.append(int(max(-32767, min(32767, round(val)))))

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack("<" + "h" * len(samples), *samples))
    return buf.getvalue()


def synthesize_stir_chirp_wav(sample_rate: int = 44100) -> bytes:
    """Soft two-tone 'mm?': E5 659 Hz then G5 784 Hz, sine, 2 x 0.11 s, -14 dB."""
    return _render_sine_sequence_wav(
        tones_hz=STIR_TONES_HZ,
        tone_duration_s=STIR_TONE_DURATION_S,
        peak_db=STIR_PEAK_DB,
        sample_rate=sample_rate,
    )


def synthesize_pat_chirp_wav(double_pat: bool = False, sample_rate: int = 44100) -> bytes:
    """Soft non-verbal chirp for head-pat / attention reactions (outside wake)."""
    if double_pat:
        return _render_sine_sequence_wav((783.99, 987.77, 1174.66, 1318.51), 0.075, -14.0, sample_rate=sample_rate)
    return _render_sine_sequence_wav((698.46, 880.0), 0.09, -15.0, sample_rate=sample_rate)


def _render_procedural_sfx_wav(
    duration_s: float,
    freq_fn,
    peak_db: float = -13.0,
    sample_rate: int = 44100,
    harmonic2: float = 0.25,
) -> bytes:
    """Renders royalty-free procedural SFX (MIT, zero copyrighted samples) as 16-bit mono WAV."""
    total_n = max(1, int(round(duration_s * sample_rate)))
    fade_n = min(total_n // 4, max(1, int(round(0.015 * sample_rate))))
    peak_amp = (10.0 ** (peak_db / 20.0)) * 32767.0
    phase = 0.0
    samples: List[int] = []

    for i in range(total_n):
        u = i / float(max(1, total_n - 1))
        freq, amp_mod = freq_fn(u)
        phase += 2.0 * math.pi * float(freq) / sample_rate
        wave_val = (math.sin(phase) + harmonic2 * math.sin(phase * 2.0)) / (1.0 + harmonic2)
        env = 1.0
        if i < fade_n:
            env = i / float(fade_n)
        elif i >= total_n - fade_n:
            env = (total_n - 1 - i) / float(fade_n)
        val = wave_val * env * amp_mod * peak_amp
        samples.append(int(max(-32767, min(32767, round(val)))))

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack("<" + "h" * len(samples), *samples))
    return buf.getvalue()


SFX_KINDS: Tuple[str, ...] = (
    "pat",
    "double_pat",
    "attention",
    "curious",
    "startle_scared",
    "dizzy_swirl",
    "whimper",
    "shake_off",
    "shaken_rattle",
    "adjust_blip",
    "adjusted_ok",
    "alarm_ring",
    "babble_happy",
    "babble_curious",
    "babble_affection",
    "weather_sunny",
    "weather_cloudy",
    "weather_rainy",
    "weather_storm",
    "weather_thunder",
    "weather_snowy",
    "weather_windy",
    "weather_starry",
)


def synthesize_sfx_wav(kind: str, sample_rate: int = 44100) -> bytes:
    """Generates a royalty-free 16-bit mono reaction SFX WAV by kind (never used for wake yawn)."""
    k = str(kind).lower().strip()
    if k == "double_pat":
        return synthesize_pat_chirp_wav(double_pat=True, sample_rate=sample_rate)
    if k == "pat":
        return synthesize_pat_chirp_wav(double_pat=False, sample_rate=sample_rate)
    if k == "attention":
        return _render_sine_sequence_wav((587.33, 740.0), 0.10, -16.0, sample_rate=sample_rate)
    if k == "curious":
        return _render_procedural_sfx_wav(
            0.22,
            lambda u: (520.0 + 340.0 * (u ** 1.3), 1.0),
            peak_db=-14.0,
            sample_rate=sample_rate,
            harmonic2=0.18,
        )
    if k == "startle_scared":
        # Expressive mid-air yank: quick pop into a wobbling rollercoaster "woaaah..."
        def _woaah(u: float) -> Tuple[float, float]:
            if u < 0.16:
                t = u / 0.16
                return (460.0 + 480.0 * math.sin(t * math.pi * 0.5), 0.7 + 0.3 * t)
            t = (u - 0.16) / 0.84
            base = 880.0 - 340.0 * (t ** 0.85)
            sway = 75.0 * math.sin(t * 17.0)
            return (base + sway, 1.0 - 0.25 * t)

        return _render_procedural_sfx_wav(
            0.66,
            _woaah,
            peak_db=-10.5,
            sample_rate=sample_rate,
            harmonic2=0.30,
        )
    if k == "dizzy_swirl":
        # Continuing mid-air "@_@" dizzy swing: undulating "woooaah-ooo..."
        return _render_procedural_sfx_wav(
            0.96,
            lambda u: (
                510.0 + 150.0 * math.sin(u * 21.0) - 160.0 * u,
                0.90 - 0.25 * u,
            ),
            peak_db=-11.5,
            sample_rate=sample_rate,
            harmonic2=0.22,
        )
    if k == "whimper":
        # Soft descending vulnerable "mmm..." puppy sigh
        return _render_procedural_sfx_wav(
            0.48,
            lambda u: (460.0 - 180.0 * (u ** 0.8), 0.95 - 0.50 * u),
            peak_db=-14.0,
            sample_rate=sample_rate,
            harmonic2=0.14,
        )
    if k == "shake_off":
        # Quick cute double-blink feather-ruffle trill
        return _render_procedural_sfx_wav(
            0.22,
            lambda u: (640.0 + 180.0 * math.sin(u * 38.0), 0.9),
            peak_db=-15.0,
            sample_rate=sample_rate,
            harmonic2=0.15,
        )
    if k == "shaken_rattle":
        # Rapid shaky "wh-wh-whaa?!" rattle when shaken
        return _render_procedural_sfx_wav(
            0.85,
            lambda u: (
                560.0 + 210.0 * math.sin(u * 52.0) + 120.0 * math.sin(u * 13.0),
                0.70 + 0.30 * abs(math.sin(u * 26.0)),
            ),
            peak_db=-11.5,
            sample_rate=sample_rate,
            harmonic2=0.28,
        )
    if k == "adjust_blip":
        # Little self-righting recalibration chirp "bwoop-ding"
        return _render_sine_sequence_wav((440.0, 659.25, 880.0), 0.085, -14.5, sample_rate=sample_rate)
    if k == "adjusted_ok":
        # Cheerful relieved "all good!" chime
        return _render_sine_sequence_wav((587.33, 783.99, 1046.50), 0.095, -13.5, sample_rate=sample_rate)
    if k == "alarm_ring":
        # Crisp two-pulse glockenspiel bedside alarm bell ("ding-ding! ding-ding!")
        return _render_procedural_sfx_wav(
            0.56,
            lambda u: (
                1046.50 if int(u * 6) % 2 == 0 else 1318.51,
                (1.0 - (u * 2.0 % 1.0) * 0.65) if (u * 2.0 % 1.0) < 0.72 else 0.05,
            ),
            peak_db=-12.5,
            sample_rate=sample_rate,
            harmonic2=0.35,
        )
    if k in ("babble_happy", "babble_curious", "babble_affection"):
        # Warm soft marimba-like pet chirps (gentle pluck decay, never harsh beeps)
        if k == "babble_curious":
            notes = ((523.25, 659.25), (587.33, 783.99), (659.25, 880.0))
        elif k == "babble_affection":
            notes = ((587.33, 739.99), (659.25, 880.0), (739.99, 987.77))
        else:
            notes = ((523.25, 659.25), (659.25, 783.99), (587.33, 880.0), (783.99, 1046.50))

        def _babble_fn(u: float) -> Tuple[float, float]:
            n_notes = len(notes)
            pos = u * n_notes
            idx = min(n_notes - 1, int(pos))
            local = pos - idx
            f0, f1 = notes[idx]
            freq = f0 + (f1 - f0) * min(1.0, local * 1.4)
            # Soft pluck envelope: smooth quick rise, warm exponential decay
            rise = min(1.0, local / 0.10)
            decay = math.exp(-local * 3.8)
            return (freq, rise * decay)

        return _render_procedural_sfx_wav(
            1.10,
            _babble_fn,
            peak_db=-15.5,
            sample_rate=sample_rate,
            harmonic2=0.10,
        )
    if k in ("weather_sunny", "weather_cloudy", "weather_snowy", "weather_starry"):
        # Musical weather mood chimes (bright marimba, soft cloud pluck, celesta sparkle, starry lullaby)
        chords = {
            "weather_sunny": (523.25, 659.25, 783.99, 987.77, 1046.50),
            "weather_cloudy": (392.00, 493.88, 587.33, 440.00),
            "weather_snowy": (1318.51, 987.77, 830.61, 1318.51, 1975.53),
            "weather_starry": (440.00, 554.37, 659.25, 830.61, 880.00),
        }
        seq = chords[k]
        dur = 0.90 if k != "weather_cloudy" else 0.85
        harm = 0.08 if k in ("weather_snowy", "weather_starry") else 0.16

        def _wx_chime(u: float) -> Tuple[float, float]:
            n = len(seq)
            pos = u * n
            idx = min(n - 1, int(pos))
            local = pos - idx
            rise = min(1.0, local / 0.08)
            decay = math.exp(-local * (3.2 if k == "weather_cloudy" else 4.2))
            return (seq[idx], rise * decay)

        return _render_procedural_sfx_wav(
            dur,
            _wx_chime,
            peak_db=-14.5,
            sample_rate=sample_rate,
            harmonic2=harm,
        )
    if k in ("weather_rainy", "weather_storm", "weather_thunder", "weather_windy"):
        # Deterministic procedural atmospheric textures (raindrops, thunder + zap, wind sweep)
        dur = 1.15 if k == "weather_thunder" else (1.05 if k == "weather_storm" else 0.95)
        total_n = max(1, int(round(dur * sample_rate)))
        fade_n = max(1, int(round(0.03 * sample_rate)))
        peak_amp = (10.0 ** ((-10.5 if k in ("weather_storm", "weather_thunder") else -14.0) / 20.0)) * 32767.0
        seed = {"weather_rainy": 2026, "weather_storm": 991, "weather_thunder": 1337, "weather_windy": 404}[k]
        rng = random.Random(seed)
        lp = 0.0
        lp2 = 0.0
        drop_phase = 0.0
        samples: List[int] = []
        for i in range(total_n):
            u = i / float(max(1, total_n - 1))
            white = rng.uniform(-1.0, 1.0)
            if k == "weather_rainy":
                lp = lp * 0.82 + white * 0.18
                # Cute water-drop plinks at 0.20, 0.50, 0.78
                plink = 0.0
                for t0, f0 in ((0.20, 880.0), (0.50, 740.0), (0.78, 1046.5)):
                    if t0 <= u <= t0 + 0.14:
                        lu = (u - t0) / 0.14
                        drop_phase += 2.0 * math.pi * (f0 + 220.0 * lu) / sample_rate
                        plink += math.sin(drop_phase) * math.exp(-lu * 6.0) * 0.65
                sig = lp * 0.55 + plink
            elif k == "weather_storm":
                lp = lp * 0.96 + white * 0.04
                # Crackling thunderbolt burst early + deep rumble tail
                zap = (white * 0.9) * math.exp(-((u - 0.12) / 0.05) ** 2)
                rumble = lp * 2.4 * (0.4 + 0.6 * math.sin(u * math.pi))
                sig = max(-1.0, min(1.0, zap + rumble))
            elif k == "weather_thunder":
                lp = lp * 0.97 + white * 0.03
                # Deep rolling double-boom thunder clap
                clap1 = (white * 0.75) * math.exp(-((u - 0.08) / 0.04) ** 2)
                clap2 = (white * 0.65) * math.exp(-((u - 0.44) / 0.06) ** 2)
                boom = lp * 2.8 * (math.exp(-u * 1.4) + 0.65 * math.exp(-((u - 0.48) / 0.24) ** 2))
                sig = max(-1.0, min(1.0, clap1 + clap2 + boom))
            else:
                # Smooth sweeping wind whoosh + soft whistle
                alpha = 0.04 + 0.10 * math.sin(u * math.pi)
                lp = lp * (1.0 - alpha) + white * alpha
                lp2 = lp2 * 0.88 + lp * 0.12
                drop_phase += 2.0 * math.pi * (380.0 + 260.0 * math.sin(u * math.pi)) / sample_rate
                sig = lp2 * 1.9 + math.sin(drop_phase) * 0.16 * math.sin(u * math.pi)
            env = 1.0
            if i < fade_n:
                env = i / float(fade_n)
            elif i >= total_n - fade_n:
                env = (total_n - 1 - i) / float(fade_n)
            samples.append(int(max(-32767, min(32767, round(sig * env * peak_amp)))))
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(struct.pack("<" + "h" * len(samples), *samples))
        return buf.getvalue()
    raise ValueError(f"Unknown SFX kind {kind!r}; expected one of {SFX_KINDS}")


@dataclass
class AudioPlaybackEvent:
    """Recorded cue event for verification and diagnostics."""

    cue_name: str
    file_path: Optional[str]
    duration_s: float
    timestamp_s: float


class AudioCuePlayer(ABC):
    """Non-blocking audio cue interface for Chintu."""

    @abstractmethod
    def play_stir_chirp(self, now_s: float = 0.0) -> None:
        """Plays the E5 -> G5 stir chirp."""

    @abstractmethod
    def play_baby_yawn(self, now_s: float = 0.0) -> float:
        """Plays assets/chintu-baby-yawn.wav in full and returns its exact duration."""

    @abstractmethod
    def play_reaction_chirp(self, kind: str = "pat", now_s: float = 0.0) -> None:
        """Plays a brief non-verbal reaction chirp (pat, double_pat, attention)."""

    def close(self) -> None:
        """Releases any active playback handles."""


class NullAudioCuePlayer(AudioCuePlayer):
    """Silent cue player that still validates and measures real WAV assets."""

    def __init__(self, yawn_wav_path: Path = BABY_YAWN_WAV_PATH) -> None:
        self.yawn_wav_path = Path(yawn_wav_path)
        self.yawn_duration_s = measure_wav_duration(self.yawn_wav_path)
        self.events: List[AudioPlaybackEvent] = []

    def play_stir_chirp(self, now_s: float = 0.0) -> None:
        self.events.append(AudioPlaybackEvent("stir_chirp", None, STIR_TONE_DURATION_S * 2.0, now_s))

    def play_baby_yawn(self, now_s: float = 0.0) -> float:
        self.events.append(
            AudioPlaybackEvent("baby_yawn", str(self.yawn_wav_path), self.yawn_duration_s, now_s)
        )
        return self.yawn_duration_s

    def play_reaction_chirp(self, kind: str = "pat", now_s: float = 0.0) -> None:
        self.events.append(AudioPlaybackEvent(f"reaction_{kind}", None, 0.18, now_s))


class SystemAudioCuePlayer(AudioCuePlayer):
    """Non-blocking OS file player (afplay on macOS, aplay/paplay on Linux) for ES8311/host audio."""

    def __init__(self, yawn_wav_path: Path = BABY_YAWN_WAV_PATH) -> None:
        self.yawn_wav_path = Path(yawn_wav_path)
        self.yawn_duration_s = measure_wav_duration(self.yawn_wav_path)
        self.events: List[AudioPlaybackEvent] = []
        self._procs: List[subprocess.Popen] = []
        self._tmp_files: List[str] = []

    def _spawn_player(self, wav_path: str) -> None:
        self._reap_finished()
        cmd = None
        if sys.platform == "darwin" and shutil.which("afplay"):
            cmd = ["afplay", wav_path]
        else:
            for tool in ("aplay", "paplay"):
                if shutil.which(tool):
                    cmd = [tool, wav_path]
                    break
        if cmd is None:
            return
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._procs.append(proc)

    def _reap_finished(self) -> None:
        still_running: List[subprocess.Popen] = []
        for p in self._procs:
            if p.poll() is None:
                still_running.append(p)
        self._procs = still_running

    def _play_wav_bytes(self, wav_bytes: bytes, prefix: str) -> None:
        fd, path = tempfile.mkstemp(prefix=prefix, suffix=".wav")
        try:
            os.write(fd, wav_bytes)
        finally:
            os.close(fd)
        self._tmp_files.append(path)
        self._spawn_player(path)

    def play_stir_chirp(self, now_s: float = 0.0) -> None:
        self.events.append(AudioPlaybackEvent("stir_chirp", None, STIR_TONE_DURATION_S * 2.0, now_s))
        self._play_wav_bytes(synthesize_stir_chirp_wav(), "chintu_stir_")

    def play_baby_yawn(self, now_s: float = 0.0) -> float:
        # Real file playback only — never interrupt or fade early.
        self.events.append(
            AudioPlaybackEvent("baby_yawn", str(self.yawn_wav_path), self.yawn_duration_s, now_s)
        )
        self._spawn_player(str(self.yawn_wav_path))
        return self.yawn_duration_s

    def play_reaction_chirp(self, kind: str = "pat", now_s: float = 0.0) -> None:
        self.events.append(AudioPlaybackEvent(f"reaction_{kind}", None, 0.18, now_s))
        wav = synthesize_sfx_wav(kind)
        self._play_wav_bytes(wav, "chintu_sfx_")

    def close(self) -> None:
        for proc in self._procs:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except OSError:
                    pass
        self._procs.clear()
        for path in self._tmp_files:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        self._tmp_files.clear()


def create_audio_cue_player(
    enabled: Optional[bool] = None,
    yawn_wav_path: Path = BABY_YAWN_WAV_PATH,
) -> AudioCuePlayer:
    """Creates a local-first audio cue player; muted under pytest or CHINTU_AUDIO=0."""
    if enabled is None:
        if "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST"):
            enabled = False
        elif os.getenv("CHINTU_AUDIO", "1").strip().lower() in ("0", "false", "no", "off"):
            enabled = False
        else:
            enabled = True
    if enabled:
        return SystemAudioCuePlayer(yawn_wav_path=yawn_wav_path)
    return NullAudioCuePlayer(yawn_wav_path=yawn_wav_path)
