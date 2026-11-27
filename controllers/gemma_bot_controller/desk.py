"""Phase 1 desk behaviors: first-boot wake, dock clock, and Pomodoro.

Timer and gesture decisions live here so they can be tested without Webots.
The controller calls into this module; Sarvam request code is not involved.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Tuple

# head_pitch stops in protos/GemaBotReview.proto (tilt about X).
PITCH_MIN = -0.52
PITCH_MAX = 0.42
YAW_LIMIT = 1.4

SOFT_BLUE = 0x00F0FF
BAR_TRACK = 0x1A3338

FOCUS_SECONDS = 25 * 60
BREAK_SECONDS = 5 * 60
DEMO_FOCUS_SECONDS = 60
DEMO_BREAK_SECONDS = 20
STRETCH_SECONDS = 3.0
LONG_PRESS_SECONDS = 0.8
FACE_HOLD_SECONDS = 6.0

GREETING_TEXT = "Hello, I'm Gema."
STRETCH_TEXT = "Stand up and stretch!"

# worlds/gemabot_review_plan.wbt places the dock here and the robot 13 mm above it.
DEMO_DOCK_XYZ = (0.30, 0.06, 0.740)
DEMO_ROBOT_XYZ = (0.30, 0.06, 0.753)

PHASE_IDLE = "idle"
PHASE_FOCUS = "focus"
PHASE_STRETCH = "stretch"
PHASE_BREAK = "break"

_DIGITS = {
    "0": "abcdef",
    "1": "bc",
    "2": "abdeg",
    "3": "abcdg",
    "4": "bcfg",
    "5": "acdfg",
    "6": "acdefg",
    "7": "abc",
    "8": "abcdefg",
    "9": "abcdfg",
}


def boot_flag_path() -> Path:
    override = os.environ.get("GEMA_BOOT_FLAG_PATH", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".gema" / "review_plan_has_booted"


def read_has_booted(path: Path) -> bool:
    try:
        return path.is_file() and path.read_text(encoding="utf-8").strip() == "1"
    except OSError:
        return False


def write_has_booted(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("1\n", encoding="utf-8")


def pomodoro_durations(environ: Optional[dict] = None) -> Tuple[float, float]:
    """Return (focus_seconds, break_seconds). GEMA_POMODORO_DEMO=1 uses 60/20."""
    env = os.environ if environ is None else environ
    raw = str(env.get("GEMA_POMODORO_DEMO", "")).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return float(DEMO_FOCUS_SECONDS), float(DEMO_BREAK_SECONDS)
    return float(FOCUS_SECONDS), float(BREAK_SECONDS)


def long_press_ticks(timestep_ms: int, hold_s: float = LONG_PRESS_SECONDS) -> int:
    step = max(1, int(timestep_ms))
    return max(1, int(round(hold_s * 1000.0 / step)))


def voice_can_speak(provider) -> bool:
    """True when the existing TTS provider can attempt playback.

    NullTTS, and SarvamTTS with no API key, are treated as silent. This does
    not call the provider.
    """
    if provider is None:
        return False
    name = type(provider).__name__
    if name in {"NullTTS", "MagicMock", "Mock"}:
        return False
    if name == "SarvamTTS":
        return bool(getattr(provider, "api_key", None))
    if name == "MacSayTTS":
        return True
    return False


def clamp_pitch(pitch: float) -> float:
    return max(PITCH_MIN, min(PITCH_MAX, pitch))


def clamp_yaw(yaw: float) -> float:
    return max(-YAW_LIMIT, min(YAW_LIMIT, yaw))


@dataclass
class WakeStep:
    blink: float
    yaw: float
    pitch: float
    greet: bool
    done: bool


class WakePlan:
    """Blink, then the resting smile, with a small nod on the yaw and pitch motors."""

    def __init__(self, first_boot: bool):
        self.first_boot = first_boot
        self.blink_frames = 24 if first_boot else 12
        self.nod_frames = 40 if first_boot else 16
        self.total = self.blink_frames + self.nod_frames
        self.frame = 0
        self._greeted = False

    def advance(self) -> Optional[WakeStep]:
        if self.frame >= self.total:
            return None
        index = self.frame
        self.frame += 1
        done = self.frame >= self.total
        if index < self.blink_frames:
            phase = index / max(1, self.blink_frames - 1)
            blink = math.sin(phase * math.pi)
            return WakeStep(blink=blink, yaw=0.0, pitch=0.0, greet=False, done=done)

        nod_index = index - self.blink_frames
        phase = nod_index / max(1, self.nod_frames - 1)
        amp = 0.16 if self.first_boot else 0.07
        yaw_amp = 0.05 if self.first_boot else 0.02
        wave = math.sin(phase * 2.0 * math.pi)
        greet = False
        if self.first_boot and not self._greeted:
            self._greeted = True
            greet = True
        return WakeStep(
            blink=0.0,
            yaw=clamp_yaw(wave * yaw_amp),
            pitch=clamp_pitch(wave * amp),
            greet=greet,
            done=done,
        )


def is_docked(
    robot_xyz: Sequence[float],
    dock_xyz: Sequence[float],
    xy_radius: float = 0.08,
    z_slack: float = 0.04,
) -> bool:
    dx = float(robot_xyz[0]) - float(dock_xyz[0])
    dy = float(robot_xyz[1]) - float(dock_xyz[1])
    dz = abs(float(robot_xyz[2]) - float(dock_xyz[2]))
    return (dx * dx + dy * dy) <= xy_radius * xy_radius and dz <= z_slack


def xyz_from(value) -> Optional[Tuple[float, float, float]]:
    try:
        if len(value) < 3:
            return None
        coords = tuple(float(value[i]) for i in range(3))
    except (TypeError, ValueError, IndexError):
        return None
    if any(math.isnan(n) or math.isinf(n) for n in coords):
        return None
    return coords


def read_dock_translation(robot) -> Optional[Tuple[float, float, float]]:
    """Read the GemaClockDock translation from the world, if Supervisor can see it."""
    try:
        root = robot.getRoot()
        children = root.getField("children")
        for index in range(children.getCount()):
            node = children.getMFNode(index)
            name_field = node.getField("name")
            if name_field is None or name_field.getSFString() != "clock dock":
                continue
            return xyz_from(node.getField("translation").getSFVec3f())
    except Exception:
        return None
    return None


def read_robot_translation(robot) -> Optional[Tuple[float, float, float]]:
    try:
        get_self = getattr(robot, "getSelf", None)
        if get_self is None:
            return None
        return xyz_from(get_self().getPosition())
    except Exception:
        return None


def display_mode(*, docked: bool, waking: bool, phase: str, face_hold: bool) -> str:
    if waking:
        return "face"
    if phase == PHASE_STRETCH:
        return "stretch"
    if phase in (PHASE_FOCUS, PHASE_BREAK):
        return "pomodoro"
    if docked and not face_hold:
        return "clock"
    return "face"


def crown_action(*, active: bool, paused: bool, event: str) -> str:
    """Map a crown event to pet / start / pause / resume / cancel.

    A long press starts the timer, or cancels it if one is running.
    A short tap (release before the long-press threshold) pets the head when
    idle, and pauses or resumes a running timer.
    """
    if event == "long":
        return "cancel" if active else "start"
    if event == "release":
        if not active:
            return "none"
        return "resume" if paused else "pause"
    if event == "rising":
        return "face" if active else "pet"
    return "none"


def format_hhmm(tm) -> str:
    return f"{int(tm.tm_hour):02d}:{int(tm.tm_min):02d}"


def format_remaining(seconds: float) -> str:
    total = max(0, int(seconds + 1e-6))
    minutes, secs = divmod(total, 60)
    return f"{minutes:02d}:{secs:02d}"


class Pomodoro:
    def __init__(self, focus_s: float, break_s: float, stretch_s: float = STRETCH_SECONDS):
        self.focus_s = float(focus_s)
        self.break_s = float(break_s)
        self.stretch_s = float(stretch_s)
        self.phase = PHASE_IDLE
        self.paused = False
        self.remaining = 0.0
        self.phase_length = 0.0

    @property
    def active(self) -> bool:
        return self.phase != PHASE_IDLE

    def start(self) -> None:
        self.phase = PHASE_FOCUS
        self.paused = False
        self.remaining = self.focus_s
        self.phase_length = self.focus_s

    def pause(self) -> None:
        if self.active:
            self.paused = True

    def resume(self) -> None:
        if self.active:
            self.paused = False

    def cancel(self) -> None:
        self.phase = PHASE_IDLE
        self.paused = False
        self.remaining = 0.0
        self.phase_length = 0.0

    def tick(self, dt: float) -> Optional[str]:
        """Advance by dt seconds. Returns the phase name when it just changed."""
        if not self.active or self.paused or dt <= 0:
            return None
        self.remaining -= dt
        if self.remaining > 0:
            return None
        if self.phase == PHASE_FOCUS:
            self.phase = PHASE_STRETCH
            self.phase_length = self.stretch_s
            self.remaining = self.stretch_s
            return PHASE_STRETCH
        if self.phase == PHASE_STRETCH:
            self.phase = PHASE_BREAK
            self.phase_length = self.break_s
            self.remaining = self.break_s
            return PHASE_BREAK
        self.phase = PHASE_FOCUS
        self.phase_length = self.focus_s
        self.remaining = self.focus_s
        return PHASE_FOCUS

    def minutes_left(self) -> int:
        if not self.active or self.remaining <= 0:
            return 0
        return int(math.ceil(self.remaining / 60.0))

    def progress(self) -> float:
        if self.phase_length <= 0:
            return 0.0
        done = 1.0 - (self.remaining / self.phase_length)
        return max(0.0, min(1.0, done))


def _segment_rects(x: int, y: int, w: int, h: int, t: int):
    mid = y + h // 2
    return {
        "a": (x + t, y, w - 2 * t, t),
        "b": (x + w - t, y + t, t, h // 2 - t),
        "c": (x + w - t, mid, t, h // 2 - t),
        "d": (x + t, y + h - t, w - 2 * t, t),
        "e": (x, mid, t, h // 2 - t),
        "f": (x, y + t, t, h // 2 - t),
        "g": (x + t, mid - t // 2, w - 2 * t, t),
    }


def _draw_digit(display, digit: str, x: int, y: int, w: int, h: int, color: int) -> None:
    thickness = max(2, h // 10)
    rects = _segment_rects(x, y, w, h, thickness)
    display.setColor(color)
    for segment in _DIGITS.get(digit, ""):
        sx, sy, sw, sh = rects[segment]
        if sw > 0 and sh > 0:
            display.fillRectangle(int(sx), int(sy), int(sw), int(sh))


def _draw_colon(display, x: int, y: int, h: int, color: int) -> None:
    display.setColor(color)
    dot = max(2, h // 10)
    display.fillRectangle(x, y + h // 3 - dot // 2, dot, dot)
    display.fillRectangle(x, y + (2 * h) // 3 - dot // 2, dot, dot)


def _glyph_advance(char: str, digit_w: int) -> int:
    gap = max(2, digit_w // 5)
    if char == ":":
        return gap + 2
    return digit_w + gap


def _time_row_width(text: str, digit_w: int) -> int:
    if not text:
        return 0
    return sum(_glyph_advance(char, digit_w) for char in text) - max(2, digit_w // 5)


def draw_time_digits(display, text: str, x: int, y: int, digit_w: int, digit_h: int, color: int = SOFT_BLUE) -> None:
    cursor = x
    for char in text:
        if char == ":":
            _draw_colon(display, cursor, y, digit_h, color)
        else:
            _draw_digit(display, char, cursor, y, digit_w, digit_h, color)
        cursor += _glyph_advance(char, digit_w)


def _clear(display, width: int = 128, height: int = 64) -> None:
    display.setColor(0x000000)
    display.fillRectangle(0, 0, width, height)


def draw_clock(display, tm, width: int = 128, height: int = 64) -> None:
    if display is None:
        return
    _clear(display, width, height)
    text = format_hhmm(tm)
    digit_w, digit_h = 18, 36
    row_w = _time_row_width(text, digit_w)
    x = max(0, (width - row_w) // 2)
    y = max(0, (height - digit_h) // 2)
    draw_time_digits(display, text, x, y, digit_w, digit_h, SOFT_BLUE)


def draw_timer(display, pomodoro: Pomodoro, width: int = 128, height: int = 64) -> None:
    if display is None:
        return
    _clear(display, width, height)
    if pomodoro.paused:
        label = "PAUSED"
    elif pomodoro.phase == PHASE_BREAK:
        label = "BREAK"
    else:
        label = "FOCUS"
    display.setColor(SOFT_BLUE)
    display.drawText(label, 4, 2)
    minutes = pomodoro.minutes_left()
    minute_label = f"{minutes} min" if minutes != 1 else "1 min"
    display.drawText(minute_label, 78, 2)
    draw_time_digits(display, format_remaining(pomodoro.remaining), 22, 14, 14, 28, SOFT_BLUE)
    track_x, track_y, track_w, track_h = 8, 52, width - 16, 8
    display.setColor(BAR_TRACK)
    display.fillRectangle(track_x, track_y, track_w, track_h)
    filled = int(round(track_w * pomodoro.progress()))
    if filled > 0:
        display.setColor(SOFT_BLUE)
        display.fillRectangle(track_x, track_y, filled, track_h)


def draw_stretch_caption(display) -> None:
    if display is None:
        return
    display.setColor(SOFT_BLUE)
    display.fillRectangle(6, 2, 5, 5)
    display.fillRectangle(8, 7, 2, 7)
    display.fillRectangle(3, 8, 12, 2)
    display.drawText("Stand up", 20, 1)
    display.drawText("and stretch!", 20, 10)


def draw_greeting_caption(display, text: str) -> None:
    if display is None:
        return
    display.setColor(SOFT_BLUE)
    # Happy eyes occupy about y=19..45. "I'm Gema." used to start at y=10 and
    # crossed the left eye, so the second line sits below the face.
    if "," in text:
        head, tail = text.split(",", 1)
        display.drawText(head.strip() + ",", 4, 1)
        display.drawText(tail.strip(), 4, 53)
    else:
        display.drawText(text, 4, 53)
