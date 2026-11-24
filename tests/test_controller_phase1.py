import logging
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTROLLER_DIR = REPO_ROOT / "controllers" / "gemma_bot_controller"


def _load_controller_module():
    # Provide lightweight Webots stubs so controller can be imported without Webots installed
    controller_stub = types.ModuleType("controller")

    class _DummyMotor:
        def setPosition(self, pos):
            pass

        def setVelocity(self, vel):
            pass

    class _DummyDisplay:
        def setOpacity(self, v):
            pass

        def setAlpha(self, v):
            pass

        def setColor(self, c):
            pass

        def fillRectangle(self, x, y, w, h):
            pass

        def drawText(self, t, x, y):
            pass

    class _DummyKeyboard:
        LEFT = 314
        RIGHT = 316
        UP = 315
        DOWN = 317

        def enable(self, ts):
            pass

        def getKey(self):
            return -1

    class _DummyTouch:
        def __init__(self):
            self.value = 0.0

        def enable(self, ts):
            pass

        def getValue(self):
            return self.value

    class _DummySupervisor:
        def getBasicTimeStep(self):
            return 16

        def getDevice(self, name):
            if name == "oled_display":
                return _DummyDisplay()
            if name in ("head_yaw", "head_pitch"):
                return _DummyMotor()
            if name == "head_touch":
                return _DummyTouch()
            return MagicMock()

        def getKeyboard(self):
            return _DummyKeyboard()

        def step(self, ts):
            return -1

    controller_stub.Robot = _DummySupervisor
    controller_stub.Supervisor = _DummySupervisor
    controller_stub.Keyboard = _DummyKeyboard
    sys.modules["controller"] = controller_stub

    if str(CONTROLLER_DIR) not in sys.path:
        sys.path.insert(0, str(CONTROLLER_DIR))
    import gemma_bot_controller
    return gemma_bot_controller


def test_idle_timer_increments_exactly_once_per_tick():
    mod = _load_controller_module()
    bot = mod.GemmaBotCompanion(start_server=False)

    moods = [
        "NEUTRAL",
        "HAPPY",
        "SLEEPY",
        "THINKING",
        "ANGRY",
        "LOVE",
        "SURPRISED",
        "CRYING",
        "DIZZY",
    ]
    for mood in moods:
        bot.active_gesture = None
        bot.mood = mood
        start = bot.idle_timer
        for step in range(1, 6):
            bot.update_animation()
            assert bot.idle_timer == start + step, (
                f"idle_timer incremented unexpectedly in mood={mood}: "
                f"expected {start + step}, got {bot.idle_timer}"
            )

    # Also verify during an active gesture
    bot.mood = "NEUTRAL"
    bot.trigger_gesture("nod")
    start = bot.idle_timer
    bot.update_animation()
    assert bot.idle_timer == start + 1


def test_confused_mood_and_gesture_are_consistent():
    mod = _load_controller_module()
    assert mod.resolve_mood("CONFUSED") == mod.GESTURE_DEFAULT_MOOD["confused"]
    assert mod.resolve_mood("confused") == "THINKING"


def test_touch_is_edge_triggered_and_retriggers_when_already_happy():
    mod = _load_controller_module()
    bot = mod.GemmaBotCompanion(start_server=False)
    bot.mood = "HAPPY"
    bot.active_gesture = None
    bot.idle_timer = 42

    # Rising edge while already HAPPY should re-trigger wiggle and refresh HAPPY timer
    bot.touch.value = 1.0
    bot.handle_keyboard_input()
    assert bot.mood == "HAPPY"
    assert bot.active_gesture == "wiggle"
    assert bot.idle_timer == 0

    # Holding touch down on next tick must NOT keep restarting the gesture
    bot.gesture_frame = 5
    bot.handle_keyboard_input()
    assert bot.gesture_frame == 5

    # Release and press again -> triggers new reaction
    bot.touch.value = 0.0
    bot.handle_keyboard_input()
    bot.gesture_frame = 10
    bot.touch.value = 1.0
    bot.handle_keyboard_input()
    assert bot.gesture_frame == 0
    assert bot.active_gesture == "wiggle"


def test_unknown_gesture_logs_warning(caplog):
    mod = _load_controller_module()
    bot = mod.GemmaBotCompanion(start_server=False)
    with caplog.at_level(logging.WARNING):
        bot.trigger_gesture("backflip_nonexistent")
    assert any("unknown gesture" in rec.message.lower() for rec in caplog.records)
    assert bot.active_gesture is None
