import asyncio
import base64
import io
import json
import sys
import wave
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _make_wav_bytes(samples_i16: bytes, sample_rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples_i16)
    return buf.getvalue()


def test_sentence_chunker_handles_abbreviations_decimals_and_think_tags():
    from voice_server.pipeline.chunker import SentenceChunker

    chunker = SentenceChunker()
    tokens = ["<think>internal</think>", "Dr. ", "Smith ", "found ", "3.14 ", "today. ", "Next?"]
    out = []
    for tok in tokens:
        out.extend(chunker.add_token(tok))
    out.extend(chunker.flush())
    assert out == ["Dr. Smith found 3.14 today.", "Next?"]


def test_sarvam_streaming_client_parses_sse_and_strips_markdown():
    from voice_server.pipeline.llm import SarvamStreamingClient

    assert SarvamStreamingClient.clean_voice_text("<think>hmm</think> **Hello** `world`!") == "Hello world!"

    sse_lines = [
        'data: {"choices":[{"delta":{"content":"నమస్కారం "}}]}',
        'data: {"choices":[{"delta":{"content":"మిత్రమా!"}}]}',
        "data: [DONE]",
    ]

    class _FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            for line in sse_lines:
                yield line

    class _FakeStreamCtx:
        async def __aenter__(self):
            return _FakeResponse()

        async def __aexit__(self, *args):
            return False

    async def _run():
        client = SarvamStreamingClient(api_key="test-sarvam-key", model="sarvam-105b")
        with patch.object(client.client, "stream", return_value=_FakeStreamCtx()) as mock_stream:
            chunks = []
            async for tok in client.stream_response(
                [{"role": "user", "content": "hi"}],
                system_prompt="Be concise.",
            ):
                chunks.append(tok)
            await client.close()

        assert "".join(chunks) == "నమస్కారం మిత్రమా!"
        call_kwargs = mock_stream.call_args.kwargs
        assert call_kwargs["headers"]["api-subscription-key"] == "test-sarvam-key"
        assert call_kwargs["json"]["model"] == "sarvam-105b"
        assert call_kwargs["json"]["stream"] is True

    asyncio.run(_run())


def test_voice_pipeline_sarvam_tts_returns_24khz_pcm():
    from voice_server.pipeline.tts import VoicePipelineTTS

    raw_pcm = b"\x01\x00\x02\x00\x03\x00\x04\x00"
    wav_bytes = _make_wav_bytes(raw_pcm, sample_rate=24000)
    b64_wav = base64.b64encode(wav_bytes).decode("ascii")

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"audios": [b64_wav]}

    async def _run():
        tts = VoicePipelineTTS(engine="sarvam", sarvam_api_key="test-sarvam-key")
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)) as mock_post:
            pcm = await tts.synthesize_sentence("నమస్కారం!")
        assert pcm == raw_pcm
        sent_json = mock_post.call_args.kwargs["json"]
        assert sent_json["target_language_code"] == "te-IN"
        assert sent_json["speech_sample_rate"] == 24000

    asyncio.run(_run())


def test_voice_session_broadcasts_events_and_respects_auth():
    from voice_server.session import EventBroadcaster, VoiceSession, SessionState

    class _FakeWS:
        def __init__(self):
            self.sent_json = []
            self.sent_bytes = []

        async def send_json(self, payload):
            self.sent_json.append(payload)

        async def send_bytes(self, data):
            self.sent_bytes.append(data)

    class _DummyDetector:
        def reset(self):
            pass

    async def _run():
        broadcaster = EventBroadcaster()
        sub_q = broadcaster.subscribe()

        fake_vad = MagicMock()
        fake_stt = MagicMock()
        fake_tts = MagicMock()
        fake_llm = MagicMock()

        with patch("voice_server.session.VoiceActivityDetector", return_value=_DummyDetector()):
            session = VoiceSession(
                websocket=_FakeWS(),
                vad_model=fake_vad,
                stt=fake_stt,
                tts=fake_tts,
                llm=fake_llm,
                broadcaster=broadcaster,
            )

        await session.set_state(SessionState.THINKING)
        event = await asyncio.wait_for(sub_q.get(), timeout=1.0)
        assert event == {"type": "state_change", "state": "THINKING"}
        broadcaster.unsubscribe(sub_q)

    asyncio.run(_run())


def test_voice_pipeline_sarvam_stt_transcribes_pcm():
    import numpy as np
    from voice_server.pipeline.stt import SpeechToText

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "request_id": "req-1",
        "transcript": "నమస్కారం గెమ్మా",
        "language_code": "te-IN",
    }

    async def _run():
        stt = SpeechToText(engine="sarvam", sarvam_api_key="test-sarvam-key")
        audio = np.zeros(16000, dtype=np.float32)
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)) as mock_post:
            transcript, lang, conf = await stt.transcribe(audio)
            await stt.close()
        assert transcript == "నమస్కారం గెమ్మా"
        assert lang == "te-IN"
        assert conf == 1.0
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["headers"]["api-subscription-key"] == "test-sarvam-key"
        assert call_kwargs["data"]["model"] == "saaras:v4"
        assert "file" in call_kwargs["files"]

    asyncio.run(_run())


def test_sarvam_api_key_defaults_full_stack_to_sarvam(monkeypatch):
    import importlib
    import config

    monkeypatch.setenv("GEMMA_SKIP_DOTENV", "1")
    for var in ("GEMMA_STT_ENGINE", "GEMMA_VOICE_TTS_ENGINE", "GEMMA_TTS_PROVIDER", "GEMMA_INTENT_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SARVAM_API_KEY", "dummy-key-for-config-test")

    cfg = importlib.reload(config)
    assert cfg.VOICE_STT_ENGINE == "sarvam"
    assert cfg.VOICE_TTS_ENGINE == "sarvam"
    assert cfg.TTS_PROVIDER == "sarvam"
    assert cfg.INTENT_PROVIDER == "sarvam"

    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    monkeypatch.setenv("GEMMA_INTENT_PROVIDER", "keyword")
    importlib.reload(config)


