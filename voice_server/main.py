import asyncio
from contextlib import asynccontextmanager
import logging
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import config
from voice_server.pipeline.llm import SarvamStreamingClient
from voice_server.pipeline.stt import SpeechToText
from voice_server.pipeline.tts import VoicePipelineTTS
from voice_server.pipeline.vad import SileroVAD
from voice_server.session import EventBroadcaster, VoiceSession
from voice_server.warmup import run_warmup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gemma-bot-voice")

vad_model: Optional[SileroVAD] = None
stt_model: Optional[SpeechToText] = None
tts_model: Optional[VoicePipelineTTS] = None
llm_client: Optional[SarvamStreamingClient] = None
event_broadcaster = EventBroadcaster()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global vad_model, stt_model, tts_model, llm_client

    logger.info("Initializing Gemma-Bot Voice Server (Sarvam AI)...")
    vad_path = config.VOICE_MODELS_DIR / "silero_vad.onnx"
    vad_model = SileroVAD(vad_path) if vad_path.is_file() else None
    if vad_model is None:
        logger.warning("Silero VAD model not found at %s; VAD disabled until model is placed.", vad_path)

    stt_model = SpeechToText(
        engine=config.VOICE_STT_ENGINE,
        indic_lang=config.VOICE_INDIC_LANG,
        model_size=config.VOICE_WHISPER_MODEL,
        device=config.VOICE_WHISPER_DEVICE,
        compute_type=config.VOICE_WHISPER_COMPUTE_TYPE,
        cpu_threads=config.VOICE_WHISPER_CPU_THREADS,
    )
    tts_model = VoicePipelineTTS()
    llm_client = SarvamStreamingClient()

    await run_warmup(vad_model, stt_model, tts_model)
    yield

    logger.info("Shutting down Gemma-Bot Voice Server...")
    if llm_client:
        await llm_client.close()
    if tts_model:
        await tts_model.close()


app = FastAPI(title="Gemma-Bot Sarvam Voice Server", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "llm_provider": "sarvam",
        "llm_model": config.SARVAM_LLM_MODEL,
        "stt_engine": config.VOICE_STT_ENGINE,
        "indic_lang": config.VOICE_INDIC_LANG,
        "tts_engine": config.VOICE_TTS_ENGINE,
        "sample_rate_in": config.VOICE_AUDIO_SAMPLE_RATE,
        "sample_rate_out": config.VOICE_TTS_SAMPLE_RATE,
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session = VoiceSession(
        websocket=websocket,
        vad_model=vad_model,
        stt=stt_model,
        tts=tts_model,
        llm=llm_client,
        broadcaster=event_broadcaster,
    )
    await session.run()


@app.websocket("/ws/events")
async def events_endpoint(websocket: WebSocket):
    """Event stream endpoint consumed by gemma_talk_bridge.py for physical robot sync."""
    await websocket.accept()
    queue = event_broadcaster.subscribe()

    async def _watch_disconnect():
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                return

    disconnect_task = asyncio.create_task(_watch_disconnect())
    try:
        while not disconnect_task.done():
            get_task = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait(
                {get_task, disconnect_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if disconnect_task in done:
                get_task.cancel()
                break
            event = get_task.result()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        logger.info("Bridge event listener disconnected.")
    except asyncio.CancelledError:
        pass
    finally:
        disconnect_task.cancel()
        event_broadcaster.unsubscribe(queue)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "voice_server.main:app",
        host=config.VOICE_SERVER_HOST,
        port=config.VOICE_SERVER_PORT,
        reload=False,
    )
