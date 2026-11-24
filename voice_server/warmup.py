import logging
import time

import numpy as np

import config
from voice_server.pipeline.stt import SpeechToText
from voice_server.pipeline.tts import VoicePipelineTTS
from voice_server.pipeline.vad import SileroVAD

logger = logging.getLogger(__name__)


async def run_warmup(vad: SileroVAD, stt: SpeechToText, tts: VoicePipelineTTS) -> None:
    """Pre-warms local VAD/STT/TTS models and verifies Sarvam API key status."""
    t0 = time.perf_counter()

    if vad is not None:
        try:
            zero_chunk = np.zeros(config.VOICE_AUDIO_CHUNK_SAMPLES, dtype=np.float32)
            vad.process_chunk(zero_chunk)
            vad.reset()
            logger.info("✓ Silero VAD warmed")
        except Exception as exc:
            logger.warning("VAD warmup warning: %s", exc)

    if stt is not None:
        try:
            dummy_audio = np.zeros(16000, dtype=np.float32)
            await stt.transcribe(dummy_audio)
            logger.info("✓ STT (%s) warmed", config.VOICE_STT_ENGINE)
        except Exception as exc:
            logger.warning("STT warmup warning: %s", exc)

    if tts is not None and tts.engine == "kokoro":
        try:
            await tts.synthesize_sentence("Ready.")
            logger.info("✓ Kokoro TTS warmed")
        except Exception as exc:
            logger.warning("TTS warmup warning: %s", exc)

    if config.SARVAM_API_KEY:
        logger.info("✓ Sarvam AI configured (LLM=%s, TTS=%s)", config.SARVAM_LLM_MODEL, config.VOICE_TTS_ENGINE)
    else:
        logger.warning("SARVAM_API_KEY is not set; voice LLM replies will prompt for configuration.")

    logger.info("Warmup completed in %.1fms.", (time.perf_counter() - t0) * 1000)
