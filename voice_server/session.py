import asyncio
from enum import Enum
import json
import logging
import time
from typing import Dict, List, Optional, Set

from fastapi import WebSocket, WebSocketDisconnect
import httpx
import numpy as np

import config
from voice_server.pipeline.chunker import SentenceChunker
from voice_server.pipeline.llm import SarvamStreamingClient
from voice_server.pipeline.stt import SpeechToText
from voice_server.pipeline.tts import VoicePipelineTTS
from voice_server.pipeline.vad import SileroVAD, VoiceActivityDetector

logger = logging.getLogger(__name__)


class EventBroadcaster:
    """Pub/sub hub forwarding live voice session events to bridge clients (/ws/events)."""

    def __init__(self):
        self._subscribers: Set[asyncio.Queue] = set()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=128)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def publish(self, event: dict) -> None:
        for q in list(self._subscribers):
            try:
                if q.full():
                    q.get_nowait()
                q.put_nowait(event)
            except Exception:
                pass


async def _notify_robot(payload: dict) -> None:
    """Fallback direct HTTP notification to Gemma-Bot controller when no bridge is attached."""
    headers = {"Content-Type": "application/json"}
    if config.BOT_AUTH_TOKEN:
        headers["X-Bot-Token"] = config.BOT_AUTH_TOKEN
    try:
        async with httpx.AsyncClient(timeout=0.5) as client:
            await client.post(config.BOT_COMMAND_URL, json=payload, headers=headers)
    except Exception as exc:
        logger.debug("Direct robot notify failed (%s): %s", config.BOT_COMMAND_URL, exc)


class SessionState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    INTERRUPTED = "INTERRUPTED"


class VoiceSession:
    """Manages a full-duplex browser voice conversation session over WebSocket."""

    def __init__(
        self,
        websocket: WebSocket,
        vad_model: SileroVAD,
        stt: SpeechToText,
        tts: VoicePipelineTTS,
        llm: SarvamStreamingClient,
        broadcaster: Optional[EventBroadcaster] = None,
    ):
        self.ws = websocket
        self.vad_model = vad_model
        self.stt = stt
        self.tts = tts
        self.llm = llm
        self.broadcaster = broadcaster

        self.state: SessionState = SessionState.IDLE
        self.detector = VoiceActivityDetector(
            vad_model=self.vad_model,
            sample_rate=config.VOICE_AUDIO_SAMPLE_RATE,
            chunk_samples=config.VOICE_AUDIO_CHUNK_SAMPLES,
            speech_threshold=config.VOICE_VAD_THRESHOLD,
            silence_duration_ms=config.VOICE_VAD_SILENCE_MS,
        )
        self.chunker = SentenceChunker()
        self.conversation_history: List[Dict[str, str]] = []
        self.chunks_received_count = 0
        self.active_generation_task: Optional[asyncio.Task] = None
        self.is_active = False

        self.utterance_end_time: float = 0.0
        self.stt_latency_ms: float = 0.0
        self.llm_ttft_ms: float = 0.0
        self.tts_first_chunk_ms: float = 0.0
        self.total_e2e_ms: float = 0.0

    async def _emit_event(self, payload: dict) -> None:
        if self.broadcaster is not None:
            await self.broadcaster.publish(payload)

    def _has_bridge_subscribers(self) -> bool:
        return self.broadcaster is not None and self.broadcaster.subscriber_count > 0

    async def set_state(self, new_state: SessionState) -> None:
        if self.state != new_state:
            self.state = new_state
            event = {"type": "state_change", "state": new_state.value}
            await self.send_json(event)
            await self._emit_event(event)

            # Avoid duplicating bridge commands if gemma_talk_bridge.py is subscribed
            if not self._has_bridge_subscribers():
                if new_state == SessionState.LISTENING:
                    asyncio.create_task(
                        _notify_robot({"state": "LISTENING", "gaze": "center", "look_at": [0.0, -0.05]})
                    )
                elif new_state in (SessionState.TRANSCRIBING, SessionState.THINKING):
                    asyncio.create_task(
                        _notify_robot({"state": "THINKING", "mood": "THINKING", "gesture": "curious"})
                    )
                elif new_state == SessionState.SPEAKING:
                    asyncio.create_task(_notify_robot({"state": "SPEAKING", "mood": "HAPPY", "gesture": "nod"}))
                elif new_state == SessionState.INTERRUPTED:
                    asyncio.create_task(
                        _notify_robot({"state": "INTERRUPTED", "interrupt": True, "mood": "SURPRISED"})
                    )

    async def send_json(self, payload: dict) -> None:
        try:
            await self.ws.send_json(payload)
        except Exception as exc:
            logger.debug("Failed to send JSON: %s", exc)

    async def send_audio_bytes(self, data: bytes) -> None:
        try:
            await self.ws.send_bytes(data)
        except Exception as exc:
            logger.debug("Failed to send audio bytes: %s", exc)

    async def handle_barge_in(self) -> None:
        logger.info("BARGE-IN DETECTED: cancelling generation and flushing playback.")
        if self.active_generation_task and not self.active_generation_task.done():
            self.active_generation_task.cancel()
            try:
                await self.active_generation_task
            except asyncio.CancelledError:
                pass
            self.active_generation_task = None

        self.chunker.reset()
        flush_event = {"type": "flush"}
        await self.send_json(flush_event)
        await self._emit_event(flush_event)

        await self.set_state(SessionState.INTERRUPTED)
        await asyncio.sleep(0.05)
        await self.set_state(SessionState.LISTENING)

    async def process_utterance(self, audio_data) -> None:
        self.utterance_end_time = time.perf_counter()
        await self.set_state(SessionState.TRANSCRIBING)
        t_stt_start = time.perf_counter()
        transcript, detected_lang, _ = await self.stt.transcribe(audio_data, language=config.VOICE_WHISPER_LANGUAGE)
        self.stt_latency_ms = (time.perf_counter() - t_stt_start) * 1000.0

        if not transcript or not transcript.strip():
            await self.set_state(SessionState.LISTENING)
            return

        transcript_event = {
            "type": "transcript",
            "role": "user",
            "text": transcript,
            "language": detected_lang,
        }
        await self.send_json(transcript_event)
        await self._emit_event(transcript_event)

        self.conversation_history.append({"role": "user", "content": transcript})
        if len(self.conversation_history) > 6:
            self.conversation_history = self.conversation_history[-6:]

        self.active_generation_task = asyncio.create_task(self._generate_and_stream_response())

    async def _dispatch_sentence(self, clean_sentence: str, first_audio_sent: bool) -> bool:
        await self.send_json({"type": "transcript", "role": "assistant", "text": clean_sentence})
        await self._emit_event({"type": "llm_sentence", "text": clean_sentence})
        if not self._has_bridge_subscribers():
            asyncio.create_task(_notify_robot({"speech": clean_sentence, "mood": "HAPPY", "audio": False}))

        t_tts_start = time.perf_counter()
        pcm_bytes = await self.tts.synthesize_sentence(clean_sentence)
        tts_duration_ms = (time.perf_counter() - t_tts_start) * 1000.0

        if not first_audio_sent:
            first_audio_sent = True
            self.tts_first_chunk_ms = tts_duration_ms
            self.total_e2e_ms = (time.perf_counter() - self.utterance_end_time) * 1000.0
            await self.set_state(SessionState.SPEAKING)
            await self.send_json(
                {
                    "type": "telemetry",
                    "stt_ms": round(self.stt_latency_ms, 1),
                    "ttft_ms": round(self.llm_ttft_ms, 1),
                    "tts_first_chunk_ms": round(self.tts_first_chunk_ms, 1),
                    "total_e2e_ms": round(self.total_e2e_ms, 1),
                }
            )
        if pcm_bytes:
            await self.send_audio_bytes(pcm_bytes)
        return first_audio_sent

    async def _generate_and_stream_response(self) -> None:
        full_assistant_reply: List[str] = []
        try:
            await self.set_state(SessionState.THINKING)
            self.chunker.reset()
            t_llm_start = time.perf_counter()
            first_token_received = False
            first_audio_sent = False

            async for token in self.llm.stream_response(
                messages=self.conversation_history,
                system_prompt=config.VOICE_SYSTEM_PROMPT,
            ):
                if not first_token_received:
                    first_token_received = True
                    self.llm_ttft_ms = (time.perf_counter() - t_llm_start) * 1000.0

                full_assistant_reply.append(token)
                for sentence in self.chunker.add_token(token):
                    clean_sentence = SarvamStreamingClient.clean_voice_text(sentence)
                    if clean_sentence:
                        first_audio_sent = await self._dispatch_sentence(clean_sentence, first_audio_sent)

            for remaining in self.chunker.flush():
                clean_sentence = SarvamStreamingClient.clean_voice_text(remaining)
                if clean_sentence:
                    first_audio_sent = await self._dispatch_sentence(clean_sentence, first_audio_sent)

            complete_reply = "".join(full_assistant_reply).strip()
            if complete_reply:
                clean_reply = SarvamStreamingClient.clean_voice_text(complete_reply)
                self.conversation_history.append({"role": "assistant", "content": clean_reply})

            await self.send_json({"type": "turn_complete"})
        except asyncio.CancelledError:
            if full_assistant_reply:
                partial = SarvamStreamingClient.clean_voice_text("".join(full_assistant_reply))
                if partial:
                    self.conversation_history.append({"role": "assistant", "content": partial})
            raise
        except Exception as exc:
            logger.error("Error in response generation: %s", exc, exc_info=True)
            await self.set_state(SessionState.LISTENING)
        finally:
            self.active_generation_task = None

    async def run(self) -> None:
        self.is_active = True
        await self.set_state(SessionState.LISTENING)
        try:
            while self.is_active:
                message = await self.ws.receive()
                if message.get("type") == "websocket.disconnect":
                    break

                if "bytes" in message and message["bytes"]:
                    pcm_chunk = message["bytes"]
                    self.chunks_received_count += 1
                    is_speaking = self.state in (SessionState.SPEAKING, SessionState.THINKING)
                    utterance, barge_in = self.detector.process(chunk_pcm16=pcm_chunk, is_assistant_speaking=is_speaking)
                    if barge_in:
                        await self.handle_barge_in()
                    if utterance is not None:
                        await self.process_utterance(utterance)
                elif "text" in message and message["text"]:
                    text_msg = message["text"]
                    if text_msg.startswith("{"):
                        try:
                            msg_obj = json.loads(text_msg)
                            if msg_obj.get("type") == "playback_ended" and self.state == SessionState.SPEAKING:
                                await self.set_state(SessionState.LISTENING)
                            elif msg_obj.get("type") == "stop":
                                self.is_active = False
                                break
                        except Exception:
                            pass
        except WebSocketDisconnect:
            logger.info("Voice WebSocket client disconnected.")
        finally:
            self.is_active = False
            if self.active_generation_task and not self.active_generation_task.done():
                self.active_generation_task.cancel()
            self.detector.reset()
