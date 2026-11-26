"""Shared HAL values: limits, capability flags, and device state.

Strings are the stored form so snapshots stay JSON-friendly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from hal.errors import UnsupportedAxisError

# Head axes. Roll is a capability flag: the sim is yaw/pitch only.
AXIS_YAW = "yaw"
AXIS_PITCH = "pitch"
AXIS_ROLL = "roll"
HEAD_AXES = (AXIS_YAW, AXIS_PITCH, AXIS_ROLL)

# Display profiles. `color` is the capability flag features branch on.
DISPLAY_MONO_128X64 = "mono_128x64"
DISPLAY_COLOR_PANEL = "color_panel"

# Thermal throttle reported alongside temperature. The 38°C step is the
# spec's ambient design limit. 34°C is an earlier ease-off, not a measured
# servo curve.
THROTTLE_NORMAL = "normal"
THROTTLE_REDUCED = "reduced"
THROTTLE_LIMITED = "limited"
THROTTLE_STATES = (THROTTLE_NORMAL, THROTTLE_REDUCED, THROTTLE_LIMITED)
THERMAL_REDUCED_C = 34.0
THERMAL_LIMITED_C = 38.0

# 5 V USB-C rail. A reading strictly below this is a voltage dip.
USB_DIP_BELOW_V = 4.6

POWER_BATTERY = "battery"
POWER_USB = "usb"
POWER_DOCK = "dock"
POWER_UNKNOWN = "unknown"
POWER_SOURCES = (POWER_BATTERY, POWER_USB, POWER_DOCK, POWER_UNKNOWN)

# Where the wall clock reading came from. HOST is the computer running the
# sim. UNSET means the clock must not be shown as a real time.
CLOCK_UNSET = "unset"
CLOCK_MANUAL = "manual"
CLOCK_NTP = "ntp"
CLOCK_FACTORY = "factory"
CLOCK_HOST = "host"
CLOCK_RTC = "rtc"
CLOCK_SOURCES = (
    CLOCK_UNSET,
    CLOCK_MANUAL,
    CLOCK_NTP,
    CLOCK_FACTORY,
    CLOCK_HOST,
    CLOCK_RTC,
)

LED_STATUS = "status"
LED_MIC = "mic"
LED_OFFLINE = "offline"
LED_CELEBRATION = "celebration"
LED_IDS = (LED_STATUS, LED_MIC, LED_OFFLINE, LED_CELEBRATION)

# Mechanical stops from worlds/gemma_bot.wbt. Roll is not in that world;
# the placeholder is only used when a driver sets supports_roll.
YAW_MIN_RAD = -1.4
YAW_MAX_RAD = 1.4
YAW_MAX_VELOCITY = 4.0
PITCH_MIN_RAD = -0.45
PITCH_MAX_RAD = 0.45
PITCH_MAX_VELOCITY = 3.5
ROLL_MIN_RAD = -0.6
ROLL_MAX_RAD = 0.6
ROLL_MAX_VELOCITY = 3.0


@dataclass(frozen=True)
class AxisLimits:
    """Mechanical range for one head axis, in radians and radians/second."""

    min_rad: float
    max_rad: float
    max_velocity: float


@dataclass(frozen=True)
class HeadCapabilities:
    """Which head axes exist. `supports_roll` is false on the current sim."""

    supports_yaw: bool
    supports_pitch: bool
    supports_roll: bool
    limits: dict
    feedback_axes: frozenset


@dataclass(frozen=True)
class DisplayCapabilities:
    """Panel size and whether the panel can show color.

    `mono_128x64` is a 1-bit 128×64 panel. `color_panel` is an RGB panel
    (the Webots display is this, at 128×64).
    """

    kind: str
    width: int
    height: int
    color: bool
    present: bool


@dataclass(frozen=True)
class AudioOutCapabilities:
    """Speaker capabilities.

    `device_present` means a robot speaker exists. `host_playback` means
    clips can play on the computer that is running the sim (how speech
    works today). A board driver sets device_present and leaves host_playback
    false.
    """

    device_present: bool
    host_playback: bool
    volume_control: bool
    sample_rate_hz: int


@dataclass(frozen=True)
class CameraCapabilities:
    present: bool
    width: int
    height: int


@dataclass(frozen=True)
class LedCapabilities:
    present: bool
    color: bool
    ids: tuple


@dataclass(frozen=True)
class LedState:
    rgb: int
    brightness: float


@dataclass(frozen=True)
class MicState:
    """Microphone snapshot.

    `hardware_mute` is the physical mic-mute switch. It is not a software mute.
    `device_present` is false in the sim, which has no microphone.
    Samples are signed 16-bit little-endian, mono, at `sample_rate_hz`.
    """

    hardware_mute: bool
    capturing: bool
    sample_rate_hz: int
    device_present: bool


@dataclass(frozen=True)
class PowerState:
    """Battery, USB, and dock. `telemetry_present` is false when nothing was measured."""

    source: str
    battery_percent: Optional[float]
    voltage_v: Optional[float]
    usb_connected: bool
    docked: bool
    charging: bool
    voltage_dip: bool
    telemetry_present: bool


@dataclass(frozen=True)
class ThermalState:
    """Temperature and the throttle the driver wants motion and brightness to follow."""

    celsius: Optional[float]
    throttle: str
    sensor_present: bool


@dataclass(frozen=True)
class NetworkState:
    """Link state. `monitored` is false when this process did not actually check a link."""

    online: bool
    monitored: bool


@dataclass(frozen=True)
class ClockReading:
    """Wall clock plus a validity flag.

    When `valid` is false, `wall_time` is None. Callers must not display a
    time in that case. `monotonic_s` is for timers and is not the wall clock.
    """

    wall_time: Optional[datetime]
    valid: bool
    source: str
    monotonic_s: float


def standard_head_limits(supports_roll: bool) -> dict:
    limits = {
        AXIS_YAW: AxisLimits(YAW_MIN_RAD, YAW_MAX_RAD, YAW_MAX_VELOCITY),
        AXIS_PITCH: AxisLimits(PITCH_MIN_RAD, PITCH_MAX_RAD, PITCH_MAX_VELOCITY),
    }
    if supports_roll:
        limits[AXIS_ROLL] = AxisLimits(ROLL_MIN_RAD, ROLL_MAX_RAD, ROLL_MAX_VELOCITY)
    return limits


def make_head_capabilities(supports_roll: bool, feedback_axes: frozenset) -> HeadCapabilities:
    return HeadCapabilities(
        supports_yaw=True,
        supports_pitch=True,
        supports_roll=supports_roll,
        limits=standard_head_limits(supports_roll),
        feedback_axes=frozenset(feedback_axes),
    )


def axis_name(axis: str) -> str:
    if not isinstance(axis, str):
        raise TypeError("axis must be a string")
    name = axis.strip().lower()
    if name not in HEAD_AXES:
        raise UnsupportedAxisError(name)
    return name


def finite_number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value if isinstance(value, float) else float(value)


def unit_interval(value, name: str) -> float:
    number = finite_number(value, name)
    if number < 0.0 or number > 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return number


def rgb24(color, name: str = "color") -> int:
    if isinstance(color, bool) or not isinstance(color, int):
        raise ValueError(f"{name} must be an int in the range 0x000000..0xFFFFFF")
    if color < 0 or color > 0xFFFFFF:
        raise ValueError(f"{name} must be an int in the range 0x000000..0xFFFFFF")
    return color


def as_float(value) -> Optional[float]:
    """Return a finite float, or None when the device did not give one.

    Webots stubs often return a MagicMock. That must not leak into callers.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return float(value)


def clamp_to_limits(radians: float, limits: AxisLimits) -> float:
    """Clamp to the mechanical stop. Values already inside are returned unchanged."""
    if radians < limits.min_rad:
        return limits.min_rad
    if radians > limits.max_rad:
        return limits.max_rad
    return radians


def clamp_velocity(radians_per_sec: float, limits: AxisLimits) -> float:
    speed = finite_number(radians_per_sec, "velocity")
    if speed < 0.0:
        raise ValueError("velocity must be >= 0")
    if speed > limits.max_velocity:
        return limits.max_velocity
    return speed


def throttle_for_celsius(celsius: float) -> str:
    """Map a sensor reading to a throttle state. Does not invent a reading."""
    temp = finite_number(celsius, "celsius")
    if temp >= THERMAL_LIMITED_C:
        return THROTTLE_LIMITED
    if temp >= THERMAL_REDUCED_C:
        return THROTTLE_REDUCED
    return THROTTLE_NORMAL


def is_voltage_dip(voltage_v: float) -> bool:
    """True when a measured rail is strictly below USB_DIP_BELOW_V."""
    return finite_number(voltage_v, "voltage") < USB_DIP_BELOW_V


def mono_color(color: int) -> int:
    """Quantize 0xRRGGBB to black or white for a 1-bit panel.

    Weights are the integer Rec. 601 approximation (77, 150, 29) / 256.
    Luma at or above 128 is white.
    """
    value = rgb24(color)
    red = (value >> 16) & 0xFF
    green = (value >> 8) & 0xFF
    blue = value & 0xFF
    luma = (77 * red + 150 * green + 29 * blue) >> 8
    if luma >= 128:
        return 0xFFFFFF
    return 0x000000


def check_throttle(throttle: str) -> str:
    if throttle not in THROTTLE_STATES:
        raise ValueError(f"throttle must be one of {THROTTLE_STATES}")
    return throttle


def check_power_source(source: str) -> str:
    if source not in POWER_SOURCES:
        raise ValueError(f"power source must be one of {POWER_SOURCES}")
    return source


def check_clock_source(source: str) -> str:
    if source not in CLOCK_SOURCES:
        raise ValueError(f"clock source must be one of {CLOCK_SOURCES}")
    return source
