import hashlib
import importlib
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTROLLER_DIR = REPO_ROOT / "controllers" / "gemma_bot_controller"
GOLDEN_MASTER_PATH = Path(__file__).resolve().parent / "golden_master.json"


def _install_webots_stub():
    c = types.ModuleType("controller")

    class _Motor:
        def setPosition(self, p):
            pass

        def setVelocity(self, v):
            pass

    class _Display:
        def __init__(self):
            self.ops = []
            self.color = 0

        def setOpacity(self, v):
            pass

        def setAlpha(self, v):
            pass

        def setColor(self, col):
            self.color = col

        def fillRectangle(self, x, y, w, h):
            self.ops.append(["rect", int(x), int(y), int(w), int(h), int(self.color)])

        def drawText(self, t, x, y):
            self.ops.append(["text", str(t), int(x), int(y), int(self.color)])

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
                return _Display()
            if n in ("head_yaw", "head_pitch"):
                return _Motor()
            if n == "head_touch":
                return _Touch()
            return MagicMock()

        def getKeyboard(self):
            return _Keyboard()

        def step(self, t):
            return -1

    c.Robot = c.Supervisor = _Supervisor
    c.Keyboard = _Keyboard
    sys.modules["controller"] = c


def test_golden_master_gestures_and_moods():
    gm = json.loads(GOLDEN_MASTER_PATH.read_text(encoding="utf-8"))
    _install_webots_stub()
    if str(CONTROLLER_DIR) not in sys.path:
        sys.path.insert(0, str(CONTROLLER_DIR))
    import gemma_bot_controller as gbc
    gbc = importlib.reload(gbc)

    for g_name, expected in gm["gestures"].items():
        bot = gbc.GemmaBotCompanion(start_server=False)
        bot.next_blink = 10000
        assert bot.trigger_gesture(g_name)
        assert bot.gesture_total_frames == expected["total_frames"]
        for frame_idx, exp_vals in enumerate(expected["frames"]):
            bot.update_animation()
            actual = [bot.cur_yaw, bot.cur_pitch, bot.gaze_x, bot.gaze_y, bot.blink_progress]
            for got, want in zip(actual, exp_vals):
                assert got == pytest.approx(want, abs=1e-3), (
                    f"Gesture {g_name} frame {frame_idx} mismatch: got={actual}, want={exp_vals}"
                )

    bot = gbc.GemmaBotCompanion(start_server=False)
    for mood, expected_digest in gm["moods"].items():
        bot.mood = mood
        bot.idle_timer = 0
        bot.blink_progress = 0.0
        bot.speech_timer = 0
        bot.display.ops.clear()
        bot.render_face()
        digest = hashlib.sha256(json.dumps(bot.display.ops).encode("utf-8")).hexdigest()
        assert digest == expected_digest, f"Mood {mood} render mismatch"


def test_faces_importable_without_webots_or_server():
    sys.modules.pop("controller", None)
    if str(CONTROLLER_DIR) not in sys.path:
        sys.path.insert(0, str(CONTROLLER_DIR))
    from faces import FaceRenderer, SCREEN_THEMES  # noqa: F401
    assert "CYAN" in SCREEN_THEMES


def test_gestures_registry_is_phase_based():
    if str(CONTROLLER_DIR) not in sys.path:
        sys.path.insert(0, str(CONTROLLER_DIR))
    from gestures import GESTURES, Gesture, resolve_gesture

    assert isinstance(GESTURES, dict)
    assert "curious" in GESTURES
    assert isinstance(GESTURES["curious"], Gesture)
    # Phase trajectory works across [0, 1] regardless of frame count
    for name, spec in GESTURES.items():
        for p in (0.0, 0.25, 0.5, 0.75, 1.0):
            pose = spec.trajectory(p)
            assert hasattr(pose, "yaw") and hasattr(pose, "pitch"), f"{name} trajectory invalid"
    assert resolve_gesture("tilt") == "curious"


def test_keymap_dict_exists():
    if str(CONTROLLER_DIR) not in sys.path:
        sys.path.insert(0, str(CONTROLLER_DIR))
    from input_map import KEYMAP

    assert isinstance(KEYMAP, dict)
    assert ord("1") in KEYMAP
    assert ord(" ") in KEYMAP


def test_readme_asset_script_uses_shared_face_renderer():
    script_src = (REPO_ROOT / "scripts" / "generate_readme_assets.py").read_text(encoding="utf-8")
    assert "from faces" in script_src
    assert "def draw_happy_eye" not in script_src
