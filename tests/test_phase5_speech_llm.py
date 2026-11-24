import asyncio
import base64
import io
import json
import sys
import time
import types
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTROLLER_DIR = REPO_ROOT / "controllers" / "gemma_bot_controller"
for p in (str(REPO_ROOT), str(CONTROLLER_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _make_wav_bytes(duration_sec: float = 0.5, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    n_frames = int(duration_sec * sample_rate)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


def test_tts_providers_and_audio_duration_lipsync():
    from tts import MacSayTTS, NullTTS, SarvamTTS, create_tts_provider

    # NullTTS
    null_tts = create_tts_provider("null")
    assert isinstance(null_tts, NullTTS)
    handle = null_tts.speak("hello", play_audio=False)
    assert handle.duration_seconds is None
    handle.stop()

    # MacSayTTS preserves `say -v Samantha` when play_audio=True
    mac_tts = MacSayTTS(voice="Samantha")
    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        h = mac_tts.speak("Hello world", play_audio=True)
        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert cmd[:3] == ["say", "-v", "Samantha"]
        h.stop()
        mock_proc.terminate.assert_called_once()

    # SarvamTTS derives duration from returned WAV audio and enforces char limit
    wav_bytes = _make_wav_bytes(duration_sec=2.5, sample_rate=24000)
    fake_resp_body = json.dumps({"audios": [base64.b64encode(wav_bytes).decode("ascii")]}).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.read.return_value = fake_resp_body

    sarvam_tts = SarvamTTS(api_key="test-key", target_language_code="te-IN")
    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        h = sarvam_tts.speak("నమస్కారం", play_audio=False)
        assert mock_open.called
        req = mock_open.call_args[0][0]
        assert req.get_header("Api-subscription-key") == "test-key"
        sent = json.loads(req.data.decode("utf-8"))
        assert sent["target_language_code"] == "te-IN"
        assert sent["model"] == "bulbul:v3"
        assert h.duration_seconds == pytest.approx(2.5, abs=0.05)


def test_controller_uses_actual_audio_duration_when_available():
    c = types.ModuleType("controller")

    class _M:
        def setPosition(self, p):
            pass

        def setVelocity(self, v):
            pass

    class _D:
        def setOpacity(self, v):
            pass

        def setAlpha(self, v):
            pass

        def setColor(self, col):
            pass

        def fillRectangle(self, x, y, w, h):
            pass

        def drawText(self, t, x, y):
            pass

    class _K:
        LEFT, RIGHT, UP, DOWN = 314, 316, 315, 317

        def enable(self, t):
            pass

        def getKey(self):
            return -1

    class _T:
        def enable(self, t):
            pass

        def getValue(self):
            return 0.0

    class _S:
        def getBasicTimeStep(self):
            return 20  # 50 FPS

        def getDevice(self, n):
            if n == "oled_display":
                return _D()
            if n in ("head_yaw", "head_pitch"):
                return _M()
            if n == "head_touch":
                return _T()
            return MagicMock()

        def getKeyboard(self):
            return _K()

        def step(self, t):
            return -1

    c.Robot = c.Supervisor = _S
    c.Keyboard = _K
    sys.modules["controller"] = c

    import importlib
    import gemma_bot_controller as gbc
    from tts import TTSHandle

    gbc = importlib.reload(gbc)
    fake_tts = MagicMock()
    fake_tts.speak.return_value = TTSHandle(duration_seconds=3.0)
    bot = gbc.GemmaBotCompanion(start_server=False, tts_provider=fake_tts)
    bot.trigger_speech("hi", play_audio=True)
    # 3.0s at 20ms timestep = 150 frames (vs ~80 frames for 1-word fallback)
    assert bot.speech_timer == 150


def test_intent_parser_valid_json_and_mocked_telugu_tanglish():
    from intent_parser import IntentParser, IntentProvider

    table = [
        (
            "నమస్కారం గెమ్మా, తల ఊపు",
            '{"action": "express", "mood": "HAPPY", "gesture": "nod", "speech": "నమస్కారం!"}',
            {"action": "express", "mood": "HAPPY", "gesture": "nod", "speech": "నమస్కారం!"},
        ),
        (
            "konchem curious ga chudu",
            '{"action": "express", "mood": "THINKING", "gesture": "curious", "speech": "Hmm!"}',
            {"action": "express", "mood": "THINKING", "gesture": "curious", "speech": "Hmm!"},
        ),
        (
            "screen green color pettu",
            '{"action": "theme", "screen": "GREEN", "speech": "Matrix green!"}',
            {"action": "theme", "screen_color": "GREEN", "speech": "Matrix green!"},
        ),
        (
            "aapeyyi silent ga undu",
            '{"action": "interrupt"}',
            {"action": "interrupt", "interrupt": True},
        ),
    ]

    class _MockProvider(IntentProvider):
        def __init__(self, mapping):
            self.mapping = mapping

        def parse_raw(self, text: str, timeout: float) -> str:
            return self.mapping[text]

    parser = IntentParser(provider=_MockProvider({p: raw for p, raw, _ in table}), timeout=1.0)
    for prompt, _, expected in table:
        cmd = parser.parse(prompt)
        for k, v in expected.items():
            assert cmd.get(k) == v, f"Prompt {prompt!r}: expected {k}={v!r}, got {cmd}"


def test_intent_parser_falls_back_on_malformed_json_timeout_and_disallowed_action():
    from intent_parser import IntentParser, IntentProvider

    class _BadJsonProvider(IntentProvider):
        def parse_raw(self, text: str, timeout: float) -> str:
            return "{not valid json"

    class _TimeoutProvider(IntentProvider):
        def parse_raw(self, text: str, timeout: float) -> str:
            raise TimeoutError("timed out")

    class _DisallowedActionProvider(IntentProvider):
        def parse_raw(self, text: str, timeout: float) -> str:
            return '{"action": "run_shell", "speech": "rm -rf /"}'

    for bad_provider in (_BadJsonProvider(), _TimeoutProvider(), _DisallowedActionProvider()):
        parser = IntentParser(provider=bad_provider, timeout=0.5)
        # Should safely fall back to Phase 1 word-boundary keyword parser
        cmd = parser.parse("nod yes and smile")
        assert cmd.get("gesture") == "nod"
        assert cmd.get("mood") == "HAPPY"

        # And keyword fallback still rejects substring false positives
        cmd_know = parser.parse("know")
        assert "gesture" not in cmd_know


def test_intent_parser_async_does_not_block_event_loop():
    from intent_parser import IntentParser, IntentProvider

    class _SlowProvider(IntentProvider):
        def parse_raw(self, text: str, timeout: float) -> str:
            time.sleep(0.25)
            return '{"action": "express", "mood": "HAPPY", "gesture": "nod"}'

    parser = IntentParser(provider=_SlowProvider(), timeout=1.0)
    ticks = 0

    async def ticker():
        nonlocal ticks
        for _ in range(15):
            await asyncio.sleep(0.01)
            ticks += 1

    async def runner():
        res, _ = await asyncio.gather(parser.parse_async("hello"), ticker())
        assert res.get("mood") == "HAPPY"

    asyncio.run(runner())
    assert ticks >= 8, f"Event loop blocked during LLM intent parsing (ticks={ticks})"
