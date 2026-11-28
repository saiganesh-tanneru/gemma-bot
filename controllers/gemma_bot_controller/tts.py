"""Text-to-Speech provider abstraction with MacSayTTS, SarvamTTS, and NullTTS."""

from abc import ABC, abstractmethod
import base64
from dataclasses import dataclass
import io
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Optional
import urllib.request
import wave

import config

logger = logging.getLogger("gemma_bot_tts")

SARVAM_TTS_MAX_CHARS = 2500


@dataclass
class TTSHandle:
    """Represents an active or completed TTS utterance for lip-sync and barge-in."""

    duration_seconds: Optional[float] = None
    process: Optional[subprocess.Popen] = None
    temp_path: Optional[str] = None

    def is_playing(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.terminate()
            except Exception:
                pass
        self.process = None
        if self.temp_path and os.path.exists(self.temp_path):
            try:
                os.unlink(self.temp_path)
            except OSError:
                pass
            self.temp_path = None


class TTSProvider(ABC):
    """Interface for synthesizing and playing Gemma-Bot speech."""

    @abstractmethod
    def speak(self, text: str, play_audio: bool = True) -> TTSHandle:
        """Synthesizes/speaks text and returns a TTSHandle with duration when known."""


class NullTTS(TTSProvider):
    """Silent TTS provider for headless tests, CI, or muted operation."""

    def speak(self, text: str, play_audio: bool = True) -> TTSHandle:
        return TTSHandle(duration_seconds=None)


class MacSayTTS(TTSProvider):
    """macOS native `say` TTS provider (preserves original Samantha voice behavior)."""

    def __init__(self, voice: str = config.TTS_MAC_VOICE):
        self.voice = voice

    def speak(self, text: str, play_audio: bool = True) -> TTSHandle:
        if not play_audio:
            return TTSHandle(duration_seconds=None)
        try:
            proc = subprocess.Popen(
                ["say", "-v", self.voice, text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return TTSHandle(duration_seconds=None, process=proc)
        except Exception as exc:
            logger.warning("MacSayTTS playback failed: %s", exc)
            return TTSHandle(duration_seconds=None)


def _contains_telugu(text: str) -> bool:
    return any("\u0C00" <= ch <= "\u0C7F" for ch in text)


def _wav_duration_seconds(wav_bytes: bytes) -> Optional[float]:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            if rate > 0:
                return frames / float(rate)
    except Exception as exc:
        logger.warning("Could not parse WAV duration: %s", exc)
    return None


def _select_audio_player(wav_path: str) -> Optional[list]:
    if sys.platform == "darwin" and shutil.which("afplay"):
        return ["afplay", wav_path]
    for candidate in ("aplay", "paplay", "ffplay"):
        if shutil.which(candidate):
            if candidate == "ffplay":
                return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", wav_path]
            return [candidate, wav_path]
    return None


class SarvamTTS(TTSProvider):
    """Sarvam AI Bulbul REST TTS provider supporting Telugu/Indian languages and Pi Zero."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: str = config.SARVAM_TTS_URL,
        model: str = config.SARVAM_TTS_MODEL,
        speaker: str = config.SARVAM_TTS_SPEAKER,
        target_language_code: str = config.SARVAM_TTS_LANGUAGE,
        timeout: float = config.SARVAM_TTS_TIMEOUT_SECONDS,
        auto_detect_telugu: bool = True,
    ):
        self.api_key = config.SARVAM_API_KEY if api_key is None else api_key
        self.endpoint = endpoint
        self.model = model
        self.speaker = speaker
        self.target_language_code = target_language_code
        self.timeout = timeout
        self.auto_detect_telugu = auto_detect_telugu

    def speak(self, text: str, play_audio: bool = True) -> TTSHandle:
        if not self.api_key:
            logger.warning("SarvamTTS configured without SARVAM_API_KEY; skipping audio synthesis")
            return TTSHandle(duration_seconds=None)

        clean_text = text[:SARVAM_TTS_MAX_CHARS]
        if len(text) > SARVAM_TTS_MAX_CHARS:
            logger.warning("Truncated TTS input from %d to %d chars (Sarvam REST limit)", len(text), SARVAM_TTS_MAX_CHARS)

        lang = "te-IN" if (self.auto_detect_telugu and _contains_telugu(clean_text)) else self.target_language_code
        payload = {
            "text": clean_text,
            "target_language_code": lang,
            "model": self.model,
            "speaker": self.speaker,
            "speech_sample_rate": 24000,
            "output_audio_codec": "wav",
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Gemma-Bot/1.0",
                "api-subscription-key": self.api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
            audios = resp_data.get("audios") or []
            if not audios:
                logger.warning("SarvamTTS returned empty audios array")
                return TTSHandle(duration_seconds=None)
            wav_bytes = base64.b64decode(audios[0])
        except Exception as exc:
            logger.warning("SarvamTTS API request failed: %s", exc)
            if play_audio and sys.platform == "darwin":
                return MacSayTTS().speak(clean_text, play_audio=True)
            return TTSHandle(duration_seconds=None)

        duration = _wav_duration_seconds(wav_bytes)
        if not play_audio:
            return TTSHandle(duration_seconds=duration)

        fd, wav_path = tempfile.mkstemp(prefix="gemma_tts_", suffix=".wav")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(wav_bytes)
            player_cmd = _select_audio_player(wav_path)
            if player_cmd is None:
                logger.warning("No audio player found on PATH; returning duration without playback")
                os.unlink(wav_path)
                return TTSHandle(duration_seconds=duration)
            proc = subprocess.Popen(player_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return TTSHandle(duration_seconds=duration, process=proc, temp_path=wav_path)
        except Exception as exc:
            logger.warning("SarvamTTS playback failed: %s", exc)
            if os.path.exists(wav_path):
                try:
                    os.unlink(wav_path)
                except OSError:
                    pass
            return TTSHandle(duration_seconds=duration)


def create_tts_provider(provider_name: Optional[str] = None) -> TTSProvider:
    """Instantiates the configured TTSProvider."""
    name = (provider_name or config.TTS_PROVIDER).lower().strip()
    if name in ("mac", "mac_say", "say"):
        return MacSayTTS()
    if name == "sarvam":
        return SarvamTTS()
    if name in ("null", "none", "silent"):
        return NullTTS()
    logger.warning("Unknown TTS provider %r; falling back to NullTTS", name)
    return NullTTS()
