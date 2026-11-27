"""Unit tests for the phase-1 desk timer and wake state."""

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTROLLER_DIR = REPO_ROOT / "controllers" / "gemma_bot_controller"
if str(CONTROLLER_DIR) not in sys.path:
    sys.path.insert(0, str(CONTROLLER_DIR))

from desk import (  # noqa: E402
    BREAK_SECONDS,
    DEMO_BREAK_SECONDS,
    DEMO_DOCK_XYZ,
    DEMO_FOCUS_SECONDS,
    DEMO_ROBOT_XYZ,
    FOCUS_SECONDS,
    GREETING_TEXT,
    PHASE_BREAK,
    PHASE_FOCUS,
    PHASE_IDLE,
    PHASE_STRETCH,
    PITCH_MAX,
    PITCH_MIN,
    SOFT_BLUE,
    STRETCH_TEXT,
    Pomodoro,
    WakePlan,
    crown_action,
    display_mode,
    draw_clock,
    draw_stretch_caption,
    draw_timer,
    format_hhmm,
    format_remaining,
    is_docked,
    long_press_ticks,
    pomodoro_durations,
    read_dock_translation,
    read_has_booted,
    voice_can_speak,
    write_has_booted,
)


class _Display:
    def __init__(self):
        self.ops = []
        self.color = 0

    def setColor(self, color):
        self.color = color

    def fillRectangle(self, x, y, w, h):
        self.ops.append(("rect", int(x), int(y), int(w), int(h), int(self.color)))

    def drawText(self, text, x, y):
        self.ops.append(("text", str(text), int(x), int(y), int(self.color)))


def test_boot_flag_roundtrip(tmp_path):
    path = tmp_path / "gema" / "review_plan_has_booted"
    assert read_has_booted(path) is False
    write_has_booted(path)
    assert read_has_booted(path) is True
    assert path.read_text(encoding="utf-8").strip() == "1"


def test_first_boot_nod_stays_inside_tilt_stops_and_greets_once():
    plan = WakePlan(first_boot=True)
    later = WakePlan(first_boot=False)
    greets = 0
    saw_closed_blink = False
    saw_nod = False
    steps = 0
    while True:
        step = plan.advance()
        if step is None:
            break
        steps += 1
        assert PITCH_MIN <= step.pitch <= PITCH_MAX
        assert abs(step.yaw) <= 1.4
        greets += int(step.greet)
        if step.blink > 0.85:
            saw_closed_blink = True
        if abs(step.pitch) > 0.05 or abs(step.yaw) > 0.01:
            saw_nod = True
            assert step.blink == 0.0
    assert steps == plan.total
    assert plan.total > later.total
    assert greets == 1
    assert saw_closed_blink
    assert saw_nod

    later_greets = 0
    while True:
        step = later.advance()
        if step is None:
            break
        later_greets += int(step.greet)
        assert PITCH_MIN <= step.pitch <= PITCH_MAX
    assert later_greets == 0


def test_docked_at_the_demo_pose_and_not_when_moved_away():
    assert is_docked(DEMO_ROBOT_XYZ, DEMO_DOCK_XYZ)
    assert not is_docked((0.50, 0.06, 0.753), DEMO_DOCK_XYZ)
    assert not is_docked((0.30, 0.06, 0.90), DEMO_DOCK_XYZ)


def test_dock_translation_reads_the_named_clock_dock():
    class _Field:
        def __init__(self, value):
            self.value = value

        def getSFString(self):
            return self.value

        def getSFVec3f(self):
            return self.value

    class _Node:
        def __init__(self, name, translation):
            self.fields = {"name": _Field(name), "translation": _Field(translation)}

        def getField(self, name):
            return self.fields.get(name)

    class _Children:
        def __init__(self, nodes):
            self.nodes = nodes

        def getCount(self):
            return len(self.nodes)

        def getMFNode(self, index):
            return self.nodes[index]

    class _Robot:
        def getRoot(self):
            return self

        def getField(self, name):
            assert name == "children"
            return _Children([
                _Node("Gemma-Bot", (0.3, 0.06, 0.753)),
                _Node("clock dock", (0.3, 0.06, 0.74)),
            ])

    assert read_dock_translation(_Robot()) == (0.3, 0.06, 0.74)
    assert read_dock_translation(object()) is None


def test_display_mode_clock_face_and_timer():
    assert display_mode(docked=True, waking=False, phase=PHASE_IDLE, face_hold=False) == "clock"
    assert display_mode(docked=True, waking=True, phase=PHASE_IDLE, face_hold=False) == "face"
    assert display_mode(docked=True, waking=False, phase=PHASE_IDLE, face_hold=True) == "face"
    assert display_mode(docked=False, waking=False, phase=PHASE_IDLE, face_hold=False) == "face"
    assert display_mode(docked=True, waking=False, phase=PHASE_FOCUS, face_hold=False) == "pomodoro"
    assert display_mode(docked=False, waking=False, phase=PHASE_STRETCH, face_hold=False) == "stretch"
    assert display_mode(docked=True, waking=True, phase=PHASE_FOCUS, face_hold=False) == "face"


def test_crown_short_tap_pets_and_running_timer_pauses_or_cancels():
    assert crown_action(active=False, paused=False, event="rising") == "pet"
    assert crown_action(active=False, paused=False, event="long") == "start"
    assert crown_action(active=False, paused=False, event="release") == "none"
    assert crown_action(active=True, paused=False, event="rising") == "face"
    assert crown_action(active=True, paused=False, event="release") == "pause"
    assert crown_action(active=True, paused=True, event="release") == "resume"
    assert crown_action(active=True, paused=True, event="long") == "cancel"


def test_pomodoro_25_5_cycle_pause_and_cancel():
    session = Pomodoro(FOCUS_SECONDS, BREAK_SECONDS, stretch_s=3)
    assert not session.active
    session.start()
    assert session.phase == PHASE_FOCUS
    assert session.minutes_left() == 25
    assert session.progress() == 0.0
    assert session.tick(60) is None
    assert session.minutes_left() == 24
    session.pause()
    assert session.tick(120) is None
    assert session.remaining == FOCUS_SECONDS - 60
    session.resume()
    assert session.tick(FOCUS_SECONDS - 60) == PHASE_STRETCH
    assert session.tick(3) == PHASE_BREAK
    assert session.minutes_left() == 5
    assert session.tick(BREAK_SECONDS) == PHASE_FOCUS
    assert session.remaining == FOCUS_SECONDS
    session.cancel()
    assert session.phase == PHASE_IDLE
    assert session.tick(5) is None
    assert session.minutes_left() == 0


def test_demo_env_shortens_to_60s_and_20s():
    assert pomodoro_durations({}) == (float(FOCUS_SECONDS), float(BREAK_SECONDS))
    assert pomodoro_durations({"GEMA_POMODORO_DEMO": "1"}) == (
        float(DEMO_FOCUS_SECONDS),
        float(DEMO_BREAK_SECONDS),
    )
    focus, brk = pomodoro_durations({"GEMA_POMODORO_DEMO": "1"})
    session = Pomodoro(focus, brk, stretch_s=3)
    session.start()
    assert session.tick(60) == PHASE_STRETCH
    assert session.tick(3) == PHASE_BREAK
    assert session.tick(20) == PHASE_FOCUS
    assert long_press_ticks(16) == 50
    assert long_press_ticks(20) == 40


def test_clock_and_pomodoro_screens_use_soft_blue():
    morning = time.struct_time((2026, 11, 27, 10, 42, 0, 4, 331, -1))
    later = time.struct_time((2026, 11, 27, 11, 5, 0, 4, 331, -1))
    assert format_hhmm(morning) == "10:42"
    assert format_hhmm(later) == "11:05"
    assert format_remaining(60) == "01:00"
    assert format_remaining(20.2) == "00:20"

    first = _Display()
    second = _Display()
    draw_clock(first, morning)
    draw_clock(second, later)
    assert first.ops != second.ops
    assert SOFT_BLUE == 0x00F0FF
    assert any(op[0] == "rect" and op[5] == SOFT_BLUE for op in first.ops)

    session = Pomodoro(FOCUS_SECONDS, BREAK_SECONDS)
    session.start()
    session.tick(90)
    screen = _Display()
    draw_timer(screen, session)
    texts = [op[1] for op in screen.ops if op[0] == "text"]
    assert "FOCUS" in texts
    assert "24 min" in texts
    blue_bars = [op for op in screen.ops if op[0] == "rect" and op[5] == SOFT_BLUE and op[2] == 52]
    assert blue_bars
    assert 0 < blue_bars[-1][3] < 112

    session.pause()
    paused = _Display()
    draw_timer(paused, session)
    assert "PAUSED" in [op[1] for op in paused.ops if op[0] == "text"]

    caption = _Display()
    draw_stretch_caption(caption)
    caption_text = [op[1] for op in caption.ops if op[0] == "text"]
    assert caption_text == ["Stand up", "and stretch!"]
    assert STRETCH_TEXT == "Stand up and stretch!"
    assert GREETING_TEXT == "Hello, I'm Gema."


def test_voice_can_speak_skips_null_and_keyless_sarvam():
    class NullTTS:
        pass

    class SarvamTTS:
        def __init__(self, api_key):
            self.api_key = api_key

    class MacSayTTS:
        pass

    assert voice_can_speak(None) is False
    assert voice_can_speak(NullTTS()) is False
    assert voice_can_speak(SarvamTTS("")) is False
    assert voice_can_speak(SarvamTTS("present")) is True
    assert voice_can_speak(MacSayTTS()) is True

    from tts import NullTTS as RealNull
    from tts import SarvamTTS as RealSarvam

    assert voice_can_speak(RealNull()) is False
    assert voice_can_speak(RealSarvam()) is False
