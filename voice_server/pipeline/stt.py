import asyncio
import io
import logging
from typing import Optional, Tuple
import wave

import httpx
import numpy as np

import config

logger = logging.getLogger(__name__)


def _float32_to_wav_bytes(audio_float32: np.ndarray, sample_rate: int = 16000) -> bytes:
    clipped = np.clip(audio_float32, -1.0, 1.0)
    pcm16 = (clipped * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())
    return buf.getvalue()


class SpeechToText:
    """Pluggable STT supporting Sarvam Saaras cloud STT, AI4Bharat ONNX, and faster-whisper."""

    def __init__(
        self,
        engine: str = config.VOICE_STT_ENGINE,
        indic_lang: str = config.VOICE_INDIC_LANG,
        model_size: str = config.VOICE_WHISPER_MODEL,
        device: str = config.VOICE_WHISPER_DEVICE,
        compute_type: str = config.VOICE_WHISPER_COMPUTE_TYPE,
        cpu_threads: int = config.VOICE_WHISPER_CPU_THREADS,
        sarvam_api_key: Optional[str] = None,
        sarvam_endpoint: str = config.SARVAM_STT_URL,
        sarvam_model: str = config.SARVAM_STT_MODEL,
        sarvam_language: str = config.SARVAM_STT_LANGUAGE,
        sarvam_mode: str = config.SARVAM_STT_MODE,
        sarvam_timeout: float = config.SARVAM_STT_TIMEOUT_SECONDS,
    ):
        self.engine = engine.lower().strip()
        self.indic_lang = indic_lang
        self.sarvam_api_key = config.SARVAM_API_KEY if sarvam_api_key is None else sarvam_api_key
        self.sarvam_endpoint = sarvam_endpoint
        self.sarvam_model = sarvam_model
        self.sarvam_language = sarvam_language
        self.sarvam_mode = sarvam_mode
        self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(sarvam_timeout, connect=5.0))
        self.model = None

        if self.engine == "sarvam":
            logger.info("Using Sarvam AI Speech-to-Text (%s).", self.sarvam_model)
        elif self.engine == "ai4bharat":
            model_id = f"OpenVoiceOS/ai4bharat-indicconformer-{indic_lang}-onnx"
            logger.info("Loading AI4Bharat IndicConformer model '%s'...", model_id)
            import onnx_asr

            self.model = onnx_asr.load_model(model_id)
        else:
            logger.info("Loading faster-whisper model '%s' on %s (%s)...", model_size, device, compute_type)
            from faster_whisper import WhisperModel

            self.model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
                cpu_threads=cpu_threads,
            )

    async def close(self) -> None:
        await self._http_client.aclose()

    async def _transcribe_sarvam(
        self,
        audio_float32: np.ndarray,
        language: Optional[str] = None,
    ) -> Tuple[str, str, float]:
        if not self.sarvam_api_key:
            logger.warning("SARVAM_API_KEY missing for Sarvam STT; returning empty transcript")
            return "", "unknown", 0.0

        wav_bytes = _float32_to_wav_bytes(audio_float32, sample_rate=config.VOICE_AUDIO_SAMPLE_RATE)
        form_data = {
            "model": self.sarvam_model,
            "language_code": language or self.sarvam_language,
            "mode": self.sarvam_mode,
        }
        headers = {"api-subscription-key": self.sarvam_api_key}
        files = {"file": ("utterance.wav", wav_bytes, "audio/wav")}
        resp = await self._http_client.post(
            self.sarvam_endpoint,
            data=form_data,
            files=files,
            headers=headers,
        )
        resp.raise_for_status()
        payload = resp.json()
        transcript = str(payload.get("transcript") or "").strip()
        detected_lang = str(payload.get("language_code") or "unknown")
        return transcript, detected_lang, 1.0

    def _transcribe_sync(
        self,
        audio_float32: np.ndarray,
        language: Optional[str] = None,
    ) -> Tuple[str, str, float]:
        if audio_float32.dtype != np.float32:
            audio_float32 = audio_float32.astype(np.float32)

        if self.engine == "ai4bharat":
            result = self.model.recognize(audio_float32, sample_rate=16000)
            transcript = str(result).strip() if result else ""
            return transcript, self.indic_lang, 1.0

        segments, info = self.model.transcribe(
            audio_float32,
            language=language,
            beam_size=1,
            condition_on_previous_text=False,
            temperature=0.0,
        )
        transcript = " ".join(seg.text.strip() for seg in segments).strip()
        detected_lang = info.language or "unknown"
        confidence = info.language_probability or 0.0
        return transcript, detected_lang, confidence

    async def transcribe(
        self,
        audio_float32: np.ndarray,
        language: Optional[str] = None,
    ) -> Tuple[str, str, float]:
        if self.engine == "sarvam":
            try:
                return await self._transcribe_sarvam(audio_float32, language=language)
            except Exception as exc:
                logger.warning("Sarvam STT failed: %s", exc)
                return "", "unknown", 0.0
        return await asyncio.to_thread(self._transcribe_sync, audio_float32, language)
