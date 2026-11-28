import io
import random
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTROLLER_DIR = REPO_ROOT / "controllers" / "gemma_bot_controller"
for _p in (str(REPO_ROOT), str(CONTROLLER_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def test_emotion_engine_smooth_morph_and_chirps():
    from emotion_engine import EMOTIONS, EmotionEngine, NullChirpPlayer, synthesize_chirp_wav

    player = NullChirpPlayer()
    engine = EmotionEngine(
        initial_mood="NEUTRAL",
        transition_ms=500.0,
        autonomous=False,
        chirp_player=player,
        rng=random.Random(42),
    )
    assert engine.current_mood == "NEUTRAL"
    assert not engine.is_transitioning

    # Smooth transition into BORED plays its sigh chirp and starts at t=0.0
    spec = engine.set_emotion("BORED", instant=False, play_chirp=True)
    assert spec.name == "BORED"
    assert engine.is_transitioning
    assert len(player.played) == 1
    assert player.played[0].pattern == "sigh"

    # Mid-transition interpolation differs from both endpoints
    engine.step_transition(250.0)
    assert 0.49 <= engine.transition_progress <= 0.51
    assert engine.current_left.height != EMOTIONS["NEUTRAL"].eye_left.height
    assert engine.current_left.height != EMOTIONS["BORED"].eye_left.height

    # Completing transition settles exactly on target EyeConfig
    engine.step_transition(250.0)
    assert engine.transition_progress == 1.0
    assert not engine.is_transitioning
    assert engine.current_left == EMOTIONS["BORED"].eye_left

    # Synthesize WAV bytes across every Emotion Engine chirp spec
    for name, em_spec in EMOTIONS.items():
        if em_spec.chirp is not None:
            wav_bytes = synthesize_chirp_wav(em_spec.chirp)
            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                assert wf.getnchannels() == 1, f"{name} chirp should be mono"
                assert wf.getsampwidth() == 2, f"{name} chirp should be 16-bit"
                assert wf.getnframes() > 0, f"{name} chirp produced empty WAV"


def test_weighted_roulette_and_drives():
    from emotion_engine import EmotionEngine

    engine = EmotionEngine(autonomous=True, autonomous_interval_ticks=10, rng=random.Random(7))
    engine.state.boredom = 0.95
    engine.state.energy = 0.2
    weights = engine.compute_dynamic_weights()
    assert weights["BORED"] > weights["HAPPY"]
    assert weights["SLEEPY"] > weights["HAPPY"]

    # Touch stimulus restores bond and lowers boredom
    reaction = engine.handle_touch(play_chirp=False)
    assert reaction.mood == "HAPPY"
    assert reaction.gesture == "wiggle"
    assert engine.state.boredom < 0.95
    assert engine.state.bond > 0.5

    # Explicit weight override forces deterministic roulette selection
    engine.set_weight("SULKING", 10.0)
    assert engine.select_weighted_emotion() == "SULKING"


def test_parametric_renderer_supports_all_emotions_and_410x502_amoled():
    from emotion_engine import ALL_MOODS, EMOTIONS
    from faces import FaceRenderer

    class _CountingDisplay:
        def __init__(self):
            self.rects = []

        def setOpacity(self, v):
            pass

        def setColor(self, col):
            pass

        def fillRectangle(self, x, y, w, h):
            self.rects.append((x, y, w, h))

        def drawText(self, t, x, y):
            pass

    assert len(ALL_MOODS) == 29
    for disp_w, disp_h in ((128, 64), (410, 502)):
        disp = _CountingDisplay()
        renderer = FaceRenderer(disp, theme="CYAN", disp_w=disp_w, disp_h=disp_h)
        for mood_name in sorted(ALL_MOODS):
            disp.rects.clear()
            spec = EMOTIONS[mood_name]
            renderer.render(
                mood=mood_name,
                left_eye=spec.eye_left,
                right_eye=spec.right_eye,
                is_transitioning=(disp_w == 410),
                speech_timer=4,
            )
            assert len(disp.rects) > 2, f"Nothing rendered for {mood_name} at {disp_w}x{disp_h}"


def test_intent_parser_and_directives_source_from_emotion_engine():
    from emotion_engine import ALL_MOODS
    from gestures import GESTURES
    from intent_parser import ALLOWED_GESTURES, ALLOWED_MOODS, parse_keyword_intent
    from voice_server.pipeline.directives import validate_directive_fields

    assert ALLOWED_MOODS == ALL_MOODS
    assert ALLOWED_GESTURES == frozenset(GESTURES.keys())

    bored = parse_keyword_intent("you look bored")
    assert bored["mood"] == "BORED"
    assert bored["gesture"] == "yawn"

    sulking = parse_keyword_intent("stop sulking")
    assert sulking["mood"] == "SULKING"
    assert sulking["gesture"] == "shy"

    validated = validate_directive_fields({"mood": "BORED", "gesture": "yawn"})
    assert validated == {"mood": "BORED", "gesture": "yawn"}


def test_controller_queues_smooth_emotion_transition():
    from test_controller_phase1 import _load_controller_module

    mod = _load_controller_module()
    while not mod.COMMAND_QUEUE.empty():
        mod.COMMAND_QUEUE.get_nowait()

    bot = mod.GemmaBotCompanion(start_server=False)
    mod.COMMAND_QUEUE.put({"mood": "SULKING"})
    bot.process_ai_commands()

    assert bot.mood == "SULKING"
    assert bot.emotion_engine.is_transitioning
    for _ in range(40):
        bot.update_animation()
    assert not bot.emotion_engine.is_transitioning
    assert bot.target_pitch > 0.0


def test_webots_proto_matches_fitted_cad_and_controller_autodetects_502x410():
    import importlib
    import types
    from unittest.mock import MagicMock

    proto_text = (REPO_ROOT / "protos" / "GemaBotReview.proto").read_text(encoding="utf-8")
    for token in (
        'name         "Chintu"',
        'url [ "textures/logo_chintu.png" ]',
        'name "oled_display"',
        "width 502",
        "height 410",
        'name "head_yaw"',
        'name "head_pitch"',
        "minStop -0.454",
        "maxStop 0.454",
        'name "head_touch"',
        'name "camera"',
        "mass 0.0906",
    ):
        assert token in proto_text, f"Missing fitted-CAD token in GemaBotReview.proto: {token}"
    assert "logo_gema.png" not in proto_text
    assert (REPO_ROOT / "protos" / "textures" / "logo_chintu.png").is_file()

    c = types.ModuleType("controller")

    class _Motor:
        def setPosition(self, p):
            pass

        def setVelocity(self, v):
            pass

    class _Display502:
        def __init__(self):
            self.ops = []

        def getWidth(self):
            return 502

        def getHeight(self):
            return 410

        def setOpacity(self, v):
            pass

        def setAlpha(self, v):
            pass

        def setColor(self, col):
            pass

        def fillRectangle(self, x, y, w, h):
            self.ops.append((x, y, w, h))

        def drawText(self, t, x, y):
            pass

    class _Keyboard:
        LEFT, RIGHT, UP, DOWN = 314, 316, 315, 317

        def enable(self, t):
            pass

        def getKey(self):
            return -1

    class _Touch:
        def enable(self, t):
            pass

        def getValue(self):
            return 0.0

    class _Supervisor:
        def getBasicTimeStep(self):
            return 16

        def getDevice(self, n):
            if n == "oled_display":
                return _Display502()
            if n in ("head_yaw", "head_pitch"):
                return _Motor()
            if n == "head_touch":
                return _Touch()
            return MagicMock()

        def getKeyboard(self):
            return _Keyboard()

        def step(self, ts):
            return -1

    c.Robot = c.Supervisor = _Supervisor
    c.Keyboard = _Keyboard
    sys.modules["controller"] = c
    if str(CONTROLLER_DIR) not in sys.path:
        sys.path.insert(0, str(CONTROLLER_DIR))
    import gemma_bot_controller as gbc

    gbc = importlib.reload(gbc)
    bot = gbc.GemmaBotCompanion(start_server=False)
    assert (bot.disp_w, bot.disp_h) == (502, 410)
    assert len(bot.display.ops) > 2

    default_world = (REPO_ROOT / "worlds" / "gemma_bot.wbt").read_text(encoding="utf-8")
    assert "GemaBotReview" in default_world
    assert "ORANGE_BODY" not in default_world
    assert "GemaClockDock" not in default_world


def test_parametric_eyes_have_no_top_row_horizontal_line_artifact():
    from emotion_engine import ALL_MOODS, EMOTIONS
    from faces import FaceRenderer

    class _PixelBufDisplay:
        def __init__(self, w, h):
            self.w, self.h = w, h
            self.buf = [[0] * w for _ in range(h)]
            self.col = 0

        def setOpacity(self, v):
            pass

        def setColor(self, col):
            self.col = col

        def fillRectangle(self, x, y, w, h):
            for yy in range(max(0, y), min(self.h, y + h)):
                for xx in range(max(0, x), min(self.w, x + w)):
                    self.buf[yy][xx] = 1 if self.col != 0 else 0

        def drawText(self, t, x, y):
            pass

    for mood_name in sorted(ALL_MOODS):
        spec = EMOTIONS[mood_name]
        if spec.eye_left.slope_top != 0 or spec.eye_left.radius_top <= 2:
            continue
        disp = _PixelBufDisplay(502, 410)
        renderer = FaceRenderer(disp, disp_w=502, disp_h=410)
        renderer.render(mood=mood_name, left_eye=spec.eye_left, right_eye=spec.right_eye)
        lit_rows = [y for y in range(410) if any(disp.buf[y][:251])]
        assert lit_rows, f"No lit pixels for {mood_name}"
        y0 = lit_rows[0]
        row0 = sum(disp.buf[y0][:251])
        row2 = sum(disp.buf[min(409, y0 + 2)][:251])
        assert row0 <= row2, f"Top-row bar artifact in {mood_name}: row0={row0}, row2={row2}"


def test_controller_skips_remote_tts_when_play_audio_false_and_sends_user_agent():
    import urllib.error
    from unittest.mock import MagicMock, patch
    from test_controller_phase1 import _load_controller_module
    from tts import SarvamTTS

    mod = _load_controller_module()
    fake_tts = MagicMock()
    bot = mod.GemmaBotCompanion(start_server=False, tts_provider=fake_tts)
    bot.trigger_speech("Connected from voice server", play_audio=False)
    fake_tts.speak.assert_not_called()
    assert bot.speech_timer > 0

    sarvam = SarvamTTS(api_key="dummy-key")
    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(
        "https://api.sarvam.ai/text-to-speech", 403, "Forbidden", {}, None
    )) as mock_open, patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock(poll=lambda: None)
        sarvam.speak("hello", play_audio=True)
        req = mock_open.call_args[0][0]
        assert req.get_header("User-agent") == "Gemma-Bot/1.0"
