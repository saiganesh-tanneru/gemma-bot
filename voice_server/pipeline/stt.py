import asyncio
import logging
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class SpeechToText:
    """Pluggable STT supporting AI4Bharat IndicConformer ONNX and faster-whisper."""

    def __init__(
        self,
        engine: str = "ai4bharat",
        indic_lang: str = "te",
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int = 4,
    ):
        self.engine = engine
        self.indic_lang = indic_lang

        if self.engine == "ai4bharat":
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
        return await asyncio.to_thread(self._transcribe_sync, audio_float32, language)
