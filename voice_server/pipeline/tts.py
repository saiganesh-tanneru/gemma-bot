import asyncio
import base64
import io
import logging
import os
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Optional

import httpx
import numpy as np

import config

logger = logging.getLogger(__name__)

INDIC_VOICE_MAP = [
    (0x0C00, 0x0C7F, "Geeta"),   # Telugu
    (0x0900, 0x097F, "Lekha"),   # Hindi / Devanagari
    (0x0B80, 0x0BFF, "Vani"),    # Tamil
    (0x0C80, 0x0CFF, "Soumya"),  # Kannada
    (0x0980, 0x09FF, "Piya"),    # Bengali
]


def _contains_telugu(text: str) -> bool:
    return any("\u0C00" <= ch <= "\u0C7F" for ch in text)


def _wav_to_pcm16(wav_bytes: bytes) -> bytes:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        return wf.readframes(wf.getnframes())


class VoicePipelineTTS:
    """24kHz Int16 PCM synthesizer supporting Sarvam Bulbul cloud TTS and Kokoro ONNX."""

    def __init__(
        self,
        engine: str = config.VOICE_TTS_ENGINE,
        model_path: Path = config.VOICE_MODELS_DIR / "kokoro-v1.0.onnx",
        voices_path: Path = config.VOICE_MODELS_DIR / "voices-v1.0.bin",
        default_voice: str = config.TTS_MAC_VOICE,
        kokoro_voice: str = config.VOICE_TTS_VOICE,
        speed: float = config.VOICE_TTS_SPEED,
        sarvam_api_key: Optional[str] = None,
        sarvam_endpoint: str = config.SARVAM_TTS_URL,
        sarvam_model: str = config.SARVAM_TTS_MODEL,
        sarvam_speaker: str = config.SARVAM_TTS_SPEAKER,
        sarvam_language: str = config.SARVAM_TTS_LANGUAGE,
    ):
        self.engine = engine.lower().strip()
        self.default_voice = kokoro_voice
        self.mac_voice = default_voice
        self.speed = speed
        self.sample_rate = config.VOICE_TTS_SAMPLE_RATE
        self.sarvam_api_key = config.SARVAM_API_KEY if sarvam_api_key is None else sarvam_api_key
        self.sarvam_endpoint = sarvam_endpoint
        self.sarvam_model = sarvam_model
        self.sarvam_speaker = sarvam_speaker
        self.sarvam_language = sarvam_language
        self.kokoro = None
        self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))

        if self.engine == "kokoro":
            if model_path.is_file() and voices_path.is_file():
                import onnxruntime as ort
                from kokoro_onnx import Kokoro

                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 4
                opts.inter_op_num_threads = 1
                opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                session = ort.InferenceSession(str(model_path), sess_options=opts, providers=["CPUExecutionProvider"])
                self.kokoro = Kokoro(str(model_path), str(voices_path))
                self.kokoro.sess = session
                logger.info("Kokoro-82M TTS initialized from %s", model_path)
            else:
                logger.warning("Kokoro model files not found at %s; falling back to Sarvam/macOS TTS", model_path)
                if self.sarvam_api_key:
                    self.engine = "sarvam"

    async def close(self) -> None:
        await self._http_client.aclose()

    @staticmethod
    def detect_indic_voice(text: str) -> Optional[str]:
        for char in text:
            cp = ord(char)
            for start, end, voice in INDIC_VOICE_MAP:
                if start <= cp <= end:
                    return voice
        return None

    def _synthesize_mac_say(self, text: str, voice: str) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
        try:
            cmd = [
                "say",
                "--file-format=WAVE",
                "--data-format=LEI16@24000",
                "-v",
                voice,
                "-o",
                tmp_path,
                text,
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with wave.open(tmp_path, "rb") as wf:
                return wf.readframes(wf.getnframes())
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    async def _synthesize_sarvam(self, text: str) -> bytes:
        if not self.sarvam_api_key:
            logger.warning("SARVAM_API_KEY missing for Sarvam TTS; returning silence")
            return b""
        lang = "te-IN" if _contains_telugu(text) else self.sarvam_language
        payload = {
            "text": text[:2500],
            "target_language_code": lang,
            "model": self.sarvam_model,
            "speaker": self.sarvam_speaker,
            "speech_sample_rate": self.sample_rate,
            "output_audio_codec": "wav",
        }
        headers = {
            "Content-Type": "application/json",
            "api-subscription-key": self.sarvam_api_key,
        }
        resp = await self._http_client.post(self.sarvam_endpoint, json=payload, headers=headers)
        resp.raise_for_status()
        audios = resp.json().get("audios") or []
        if not audios:
            return b""
        wav_bytes = base64.b64decode(audios[0])
        return _wav_to_pcm16(wav_bytes)

    def _synthesize_kokoro_sync(self, text: str, voice: Optional[str] = None) -> bytes:
        indic_voice = self.detect_indic_voice(text)
        if indic_voice:
            return self._synthesize_mac_say(text, indic_voice)
        if self.kokoro is None:
            return self._synthesize_mac_say(text, self.mac_voice)
        samples, _sr = self.kokoro.create(text, voice=voice or self.default_voice, speed=self.speed)
        int16_samples = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
        return int16_samples.tobytes()

    async def synthesize_sentence(self, text: str, voice: Optional[str] = None) -> bytes:
        """Synthesizes a sentence into 24kHz Int16 linear PCM bytes."""
        if self.engine == "sarvam":
            try:
                return await self._synthesize_sarvam(text)
            except Exception as exc:
                logger.warning("Sarvam voice TTS failed (%s); falling back", exc)
                if self.kokoro is not None:
                    return await asyncio.to_thread(self._synthesize_kokoro_sync, text, voice)
                return b""
        return await asyncio.to_thread(self._synthesize_kokoro_sync, text, voice)
