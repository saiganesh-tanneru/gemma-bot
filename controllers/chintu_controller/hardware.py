"""Hardware abstraction for Chintu (ESP32-S3 SKU 31957 + MG90S gimbal + AXP2101 + pogo dock)."""

from dataclasses import dataclass
import math
import re
from typing import Callable, List, Optional, Tuple


# Physical MG90S gimbal limits vs wake ritual envelope
SERVO_PAN_MIN_DEG = -80.0
SERVO_PAN_MAX_DEG = 80.0
SERVO_TILT_MIN_DEG = -26.0
SERVO_TILT_MAX_DEG = 26.0

WAKE_PAN_MIN_DEG = -50.0
WAKE_PAN_MAX_DEG = 50.0
WAKE_TILT_MIN_DEG = -12.0
WAKE_TILT_MAX_DEG = 14.0

MAX_SERVO_SPEED_DEG_S = 90.0


def smoothstep_ease(u: float) -> float:
    """Cubic ease-in-out in [0, 1] for quiet, organic servo moves."""
    x = max(0.0, min(1.0, float(u)))
    return x * x * (3.0 - 2.0 * x)


class ChargingSensor:
    """Single-flag AXP2101 charging detector with stub + manual test hook.

    Does NOT fake a battery percentage or invent telemetry.
    """

    def __init__(self, board_reader: Optional[Callable[[], bool]] = None) -> None:
        self._board_reader = board_reader
        self._override: Optional[bool] = None

    def set_manual_override(self, value: Optional[bool]) -> None:
        """Manual test hook: True/False to force charge state, None to read board stub."""
        self._override = None if value is None else bool(value)

    def is_charging(self) -> bool:
        """Single source of truth for charging detection."""
        if self._override is not None:
            return self._override
        if self._board_reader is not None:
            return bool(self._board_reader())
        return False


class DockDetector:
    """Magnetic pogo-pin dock detector (attached body vs keychain detached head)."""

    def __init__(self, board_reader: Optional[Callable[[], bool]] = None) -> None:
        self._board_reader = board_reader
        self._override: Optional[bool] = None

    def set_manual_override(self, docked: Optional[bool]) -> None:
        self._override = None if docked is None else bool(docked)

    def is_docked(self) -> bool:
        if self._override is not None:
            return self._override
        if self._board_reader is not None:
            return bool(self._board_reader())
        return True


@dataclass
class ServoMove:
    start_pan_deg: float
    start_tilt_deg: float
    end_pan_deg: float
    end_tilt_deg: float
    start_time_s: float
    duration_s: float


class ServoRig:
    """Quiet eased pan/tilt controller with attach/detach and keychain-mode safety."""

    def __init__(
        self,
        dock_detector: Optional[DockDetector] = None,
        yaw_motor=None,
        pitch_motor=None,
        max_speed_deg_s: float = MAX_SERVO_SPEED_DEG_S,
    ) -> None:
        self.dock_detector = dock_detector or DockDetector()
        self.yaw_motor = yaw_motor
        self.pitch_motor = pitch_motor
        self.max_speed_deg_s = max(10.0, float(max_speed_deg_s))

        self.attached: bool = True
        self.pan_deg: float = 0.0
        self.tilt_deg: float = 0.0
        self.target_pan_deg: float = 0.0
        self.target_tilt_deg: float = 0.0
        self._active_move: Optional[ServoMove] = None
        self._last_step_s: Optional[float] = None

        if self.yaw_motor is not None and hasattr(self.yaw_motor, "setVelocity"):
            self.yaw_motor.setVelocity(math.radians(self.max_speed_deg_s))
        if self.pitch_motor is not None and hasattr(self.pitch_motor, "setVelocity"):
            self.pitch_motor.setVelocity(math.radians(self.max_speed_deg_s))

    @staticmethod
    def clamp_angles(pan_deg: float, tilt_deg: float, wake_limits: bool = False) -> Tuple[float, float]:
        if wake_limits:
            p = max(WAKE_PAN_MIN_DEG, min(WAKE_PAN_MAX_DEG, float(pan_deg)))
            t = max(WAKE_TILT_MIN_DEG, min(WAKE_TILT_MAX_DEG, float(tilt_deg)))
            return p, t
        p = max(SERVO_PAN_MIN_DEG, min(SERVO_PAN_MAX_DEG, float(pan_deg)))
        t = max(SERVO_TILT_MIN_DEG, min(SERVO_TILT_MAX_DEG, float(tilt_deg)))
        return p, t

    def attach(self) -> None:
        """Attaches body servos when docked; no-op in detached keychain mode."""
        if not self.dock_detector.is_docked():
            self.attached = False
            return
        self.attached = True

    def detach(self) -> None:
        """Detaches PWM / holding torque so sleeping Chintu is completely silent."""
        self.attached = False
        self._active_move = None

    def move_to(
        self,
        pan_deg: float,
        tilt_deg: float,
        duration_s: float,
        now_s: float,
        wake_limits: bool = False,
    ) -> None:
        """Starts an eased move from current position to target over duration_s."""
        clamped_pan, clamped_tilt = self.clamp_angles(pan_deg, tilt_deg, wake_limits=wake_limits)
        self.target_pan_deg = clamped_pan
        self.target_tilt_deg = clamped_tilt

        if not self.dock_detector.is_docked() or not self.attached:
            return

        # Enforce quiet speed cap (~90 deg/s max)
        delta = max(abs(clamped_pan - self.pan_deg), abs(clamped_tilt - self.tilt_deg))
        min_dur = delta / self.max_speed_deg_s if delta > 0 else 0.0
        eff_dur = max(0.05, float(duration_s), min_dur)

        self._active_move = ServoMove(
            start_pan_deg=self.pan_deg,
            start_tilt_deg=self.tilt_deg,
            end_pan_deg=clamped_pan,
            end_tilt_deg=clamped_tilt,
            start_time_s=float(now_s),
            duration_s=eff_dur,
        )

    def snap_target_for_tick(self, pan_deg: float, tilt_deg: float, now_s: float, wake_limits: bool = False) -> None:
        """Sets an immediate rate-limited setpoint (for continuous oscillations)."""
        clamped_pan, clamped_tilt = self.clamp_angles(pan_deg, tilt_deg, wake_limits=wake_limits)
        self.target_pan_deg = clamped_pan
        self.target_tilt_deg = clamped_tilt
        self._active_move = None
        if not self.dock_detector.is_docked() or not self.attached:
            return
        dt = 0.02 if self._last_step_s is None else max(0.001, min(0.1, now_s - self._last_step_s))
        max_step = self.max_speed_deg_s * dt
        dp = max(-max_step, min(max_step, clamped_pan - self.pan_deg))
        dtilt = max(-max_step, min(max_step, clamped_tilt - self.tilt_deg))
        self.pan_deg += dp
        self.tilt_deg += dtilt
        self._apply_motors()

    def step(self, now_s: float) -> Tuple[float, float]:
        """Advances active eased move and updates motors if docked and attached."""
        if not self.dock_detector.is_docked():
            self.attached = False
            self._active_move = None
            self._last_step_s = now_s
            return self.pan_deg, self.tilt_deg

        if not self.attached:
            self._last_step_s = now_s
            return self.pan_deg, self.tilt_deg

        if self._active_move is not None:
            mv = self._active_move
            u = (now_s - mv.start_time_s) / max(1e-4, mv.duration_s)
            if u >= 1.0:
                desired_pan = mv.end_pan_deg
                desired_tilt = mv.end_tilt_deg
                self._active_move = None
            else:
                e = smoothstep_ease(u)
                desired_pan = mv.start_pan_deg + (mv.end_pan_deg - mv.start_pan_deg) * e
                desired_tilt = mv.start_tilt_deg + (mv.end_tilt_deg - mv.start_tilt_deg) * e

            dt = 0.02 if self._last_step_s is None else max(0.001, min(0.1, now_s - self._last_step_s))
            max_step = self.max_speed_deg_s * dt
            self.pan_deg += max(-max_step, min(max_step, desired_pan - self.pan_deg))
            self.tilt_deg += max(-max_step, min(max_step, desired_tilt - self.tilt_deg))
            self._apply_motors()

        self._last_step_s = now_s
        return self.pan_deg, self.tilt_deg

    def _apply_motors(self) -> None:
        if not self.attached or not self.dock_detector.is_docked():
            return
        if self.yaw_motor is not None:
            self.yaw_motor.setPosition(math.radians(self.pan_deg))
        if self.pitch_motor is not None:
            # In Webots PROTO: +pitch around +X pitches -Y face DOWN; negative tilt_deg = bowed down.
            self.pitch_motor.setPosition(-math.radians(self.tilt_deg))


class TouchDebouncer:
    """Debounced single-tap capacitive/bumper detector (no long-press) + rapid-pat detector."""

    def __init__(self, debounce_s: float = 0.08, rapid_window_s: float = 3.0, rapid_count: int = 4) -> None:
        self.debounce_s = debounce_s
        self.rapid_window_s = rapid_window_s
        self.rapid_count = rapid_count
        self._is_pressed = False
        self._last_edge_s = -10.0
        self._tap_history: List[float] = []

    def update(self, pressed: bool, now_s: float) -> Tuple[bool, bool]:
        """Processes raw touch sample -> (single_tap_fired, is_rapid_dizzy_pat)."""
        fired = False
        rapid = False
        if pressed and not self._is_pressed and (now_s - self._last_edge_s) >= self.debounce_s:
            fired = True
            self._last_edge_s = now_s
            self._tap_history.append(now_s)
            cutoff = now_s - self.rapid_window_s
            self._tap_history = [t for t in self._tap_history if t >= cutoff]
            if len(self._tap_history) >= self.rapid_count:
                rapid = True
        self._is_pressed = bool(pressed)
        return fired, rapid


class LocalWakeWordDetector:
    """On-device phrase matcher working offline (no cloud, no streaming).

    Recognizes:
    - 'wake Chintu up' (primary wake test phrase)
    - 'Hey Chintu' (local wake word)
    - 'Chintu, go to sleep' (drowsy sleep command)
    - 'kick Chintu off' / 'kicked off dock' / 'detach Chintu' (mid-air startled sway)
    """

    _WAKE_UP_RE = re.compile(r"\bwake\s+chintu\s+up\b", re.IGNORECASE)
    _HEY_CHINTU_RE = re.compile(r"\bhey\s+chintu\b", re.IGNORECASE)
    _SLEEP_RE = re.compile(r"\bchintu[\s,]+go\s+to\s+sleep\b", re.IGNORECASE)
    _KICK_OFF_RE = re.compile(
        r"\b(?:kick\s+chintu\s+off|kicked\s+off(?:\s+dock)?|pop\s+off(?:\s+dock)?|detach\s+chintu|pick\s+chintu\s+up)\b",
        re.IGNORECASE,
    )
    _SHAKE_RE = re.compile(
        r"\b(?:shake\s+chintu|shake\s+him|shaken|earthquake)\b",
        re.IGNORECASE,
    )
    _ALARM_SET_RE = re.compile(
        r"\b(?:set\s+alarm(?:\s+in)?|alarm\s+in|wake\s+me\s+in)\s+(\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds?)?\b",
        re.IGNORECASE,
    )
    _ALARM_RING_RE = re.compile(
        r"\b(?:ring\s+alarm|trigger\s+alarm|alarm)\b",
        re.IGNORECASE,
    )

    @classmethod
    def extract_alarm_delay_s(cls, phrase: str) -> Optional[float]:
        if not phrase:
            return None
        m = cls._ALARM_SET_RE.search(" ".join(str(phrase).strip().split()))
        if m:
            return max(0.5, float(m.group(1)))
        return None

    @classmethod
    def classify_text(cls, phrase: str) -> Optional[str]:
        if not phrase:
            return None
        text = " ".join(str(phrase).strip().split())
        if cls._WAKE_UP_RE.search(text):
            return "wake_phrase"
        if cls._HEY_CHINTU_RE.search(text):
            return "wake_word"
        if cls._SLEEP_RE.search(text):
            return "go_to_sleep"
        if cls._KICK_OFF_RE.search(text):
            return "kicked_off_dock"
        if cls._SHAKE_RE.search(text):
            return "shake_chintu"
        if cls._ALARM_SET_RE.search(text):
            return "set_alarm"
        if cls._ALARM_RING_RE.search(text):
            return "ring_alarm"
        return None
