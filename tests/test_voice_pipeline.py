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
        assert "reasoning_effort" in call_kwargs["json"]
        assert call_kwargs["json"]["reasoning_effort"] is None

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


def test_directive_tag_extractor_parses_split_tokens_and_validates_allowlist():
    from voice_server.pipeline.directives import DirectiveTagExtractor

    ext = DirectiveTagExtractor()
    tokens = ["[BO", "T: mood=SLEEPY ", "gesture=droop", " screen=PURPLE] ", "Goodnight", "... zzz"]
    text_out = []
    for tok in tokens:
        text_out.append(ext.feed(tok))
    text_out.append(ext.flush())
    assert "".join(text_out) == "Goodnight... zzz"
    assert ext.directives == {"mood": "SLEEPY", "gesture": "droop", "screen_color": "PURPLE"}

    # Disallowed values are stripped safely without crashing or leaking invalid fields
    ext_bad = DirectiveTagExtractor()
    out_bad = ext_bad.feed("[BOT: mood=EVIL gesture=hack_db screen=NEON] Hello!") + ext_bad.flush()
    assert out_bad == "Hello!"
    assert ext_bad.directives == {}

    # Normal text without tag passes through cleanly
    ext_plain = DirectiveTagExtractor()
    out_plain = ext_plain.feed("Hello there, ") + ext_plain.feed("friend!") + ext_plain.flush()
    assert out_plain == "Hello there, friend!"
    assert ext_plain.directives == {}


def test_directive_tag_extractor_strips_trailing_and_midstream_tags():
    from voice_server.pipeline.directives import DirectiveTagExtractor

    ext = DirectiveTagExtractor()
    tokens = [
        "I do not know your name. ",
        "You can tell me though. ",
        "[BO",
        "T: mood=NEUTRAL gesture=nod gaze=center]",
    ]
    out = "".join(ext.feed(t) for t in tokens) + ext.flush()
    assert "[BOT" not in out
    assert out.strip() == "I do not know your name. You can tell me though."
    assert ext.directives == {"mood": "NEUTRAL", "gesture": "nod", "gaze": "center"}


def test_voice_session_emits_robot_action_and_preserves_turn_mood():
    from voice_server.session import EventBroadcaster, VoiceSession

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

    class _MockLLM:
        async def stream_response(self, messages, system_prompt):
            for tok in ["[BOT: mood=CRYING gesture=droop] ", "Oh no, ", "that makes me sad."]:
                yield tok

    class _MockTTS:
        async def synthesize_sentence(self, text):
            return b"\x00\x00" * 100

    async def _run():
        broadcaster = EventBroadcaster()
        sub_q = broadcaster.subscribe()

        with patch("voice_server.session.VoiceActivityDetector", return_value=_DummyDetector()):
            session = VoiceSession(
                websocket=_FakeWS(),
                vad_model=MagicMock(),
                stt=MagicMock(),
                tts=_MockTTS(),
                llm=_MockLLM(),
                broadcaster=broadcaster,
            )

        session.conversation_history.append({"role": "user", "content": "act sad"})
        await session._generate_and_stream_response()

        events = []
        while not sub_q.empty():
            events.append(sub_q.get_nowait())
        broadcaster.unsubscribe(sub_q)

        robot_actions = [e for e in events if e.get("type") == "robot_action"]
        assert robot_actions, f"Expected robot_action event, got {events}"
        assert robot_actions[-1]["mood"] == "CRYING"
        assert robot_actions[-1]["gesture"] == "droop"

        sentences = [e for e in events if e.get("type") == "llm_sentence"]
        assert sentences
        assert "[BOT:" not in sentences[0]["text"]
        assert sentences[0]["mood"] == "CRYING"

        speaking = [e for e in events if e.get("type") == "state_change" and e.get("state") == "SPEAKING"]
        assert speaking and speaking[0].get("mood") == "CRYING"

    asyncio.run(_run())


def test_voice_session_recovers_to_listening_if_llm_returns_empty():
    from voice_server.session import EventBroadcaster, SessionState, VoiceSession

    class _FakeWS:
        async def send_json(self, payload):
            pass

        async def send_bytes(self, data):
            pass

    class _DummyDetector:
        def reset(self):
            pass

    class _EmptyLLM:
        async def stream_response(self, messages, system_prompt):
            if False:
                yield ""

    async def _run():
        broadcaster = EventBroadcaster()
        with patch("voice_server.session.VoiceActivityDetector", return_value=_DummyDetector()):
            session = VoiceSession(
                websocket=_FakeWS(),
                vad_model=MagicMock(),
                stt=MagicMock(),
                tts=MagicMock(),
                llm=_EmptyLLM(),
                broadcaster=broadcaster,
            )
        session.conversation_history.append({"role": "user", "content": "hello"})
        await session._generate_and_stream_response()
        assert session.state == SessionState.LISTENING

    asyncio.run(_run())


def test_bridge_listening_returns_robot_to_neutral_after_response():
    import gemma_talk_bridge as bridge
    import json as _json
    import websockets

    sent_payloads = []

    async def _run():
        async def ws_handler(ws):
            await asyncio.sleep(0.05)
            await ws.send(_json.dumps({"type": "state_change", "state": "THINKING"}))
            await asyncio.sleep(0.05)
            await ws.send(_json.dumps({"type": "state_change", "state": "SPEAKING", "mood": "SURPRISED"}))
            await asyncio.sleep(0.05)
            await ws.send(_json.dumps({"type": "state_change", "state": "LISTENING"}))
            await asyncio.sleep(0.5)

        async with websockets.serve(ws_handler, "127.0.0.1", 0) as ws_srv:
            ws_port = ws_srv.sockets[0].getsockname()[1]
            orig_url = bridge.GEMMA_TALK_WS_URL
            bridge.GEMMA_TALK_WS_URL = f"ws://127.0.0.1:{ws_port}"
            try:
                with patch.object(
                    bridge,
                    "send_bot_command",
                    side_effect=lambda payload, *args, **kw: sent_payloads.append(payload) or {"status": "received"},
                ):
                    task = asyncio.create_task(bridge.connect_to_gemma_talk())
                    await asyncio.sleep(0.3)
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            finally:
                bridge.GEMMA_TALK_WS_URL = orig_url

    asyncio.run(_run())
    listening_cmds = [p for p in sent_payloads if p.get("state") == "LISTENING"]
    assert listening_cmds and listening_cmds[-1].get("mood") == "NEUTRAL"





