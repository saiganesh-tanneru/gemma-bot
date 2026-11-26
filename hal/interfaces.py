"""Hardware interfaces. A board driver implements these; it does not import Webots."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from hal.errors import UnsupportedOperationError
from hal.types import (
    AudioOutCapabilities,
    CameraCapabilities,
    ClockReading,
    DisplayCapabilities,
    HeadCapabilities,
    LedCapabilities,
    LedState,
    MicState,
    NetworkState,
    PowerState,
    ThermalState,
)


class Playback:
    """A clip handed back by AudioOut.play_wav. Idle playback is not playing."""

    def __init__(self, duration_seconds: Optional[float] = None):
        self.duration_seconds = duration_seconds

    def stop(self) -> None:
        return None

    def is_playing(self) -> bool:
        return False


class HeadServos(ABC):
    """Yaw and pitch, plus an optional roll axis for a future head-bobble."""

    @abstractmethod
    def capabilities(self) -> HeadCapabilities:
        """Report which axes exist and whether position feedback is wired."""

    @abstractmethod
    def set_position(self, axis: str, radians: float) -> None:
        """Command a position. Drivers clamp to mechanical stops."""

    @abstractmethod
    def set_velocity(self, axis: str, radians_per_sec: float) -> None:
        """Set the position-control speed limit for one axis. Must be >= 0."""

    @abstractmethod
    def commanded_position(self, axis: str) -> float:
        """Last position this process commanded, after clamping."""

    @abstractmethod
    def feedback_position(self, axis: str) -> Optional[float]:
        """Measured position, or None when this axis has no sensor reading."""


class Display(ABC):
    """Face panel. Color versus mono 128×64 is a capability, not a separate type."""

    @abstractmethod
    def capabilities(self) -> DisplayCapabilities:
        """Report kind, size, color, and whether a panel is attached."""

    @abstractmethod
    def set_opacity(self, alpha: float) -> None:
        """Set panel opacity in 0..1."""

    @abstractmethod
    def set_alpha(self, alpha: float) -> None:
        """Set panel alpha in 0..1. The Webots display has this as well as opacity."""

    @abstractmethod
    def set_color(self, color: int) -> None:
        """Set the pen color as 0xRRGGBB. Mono panels quantize on write."""

    @abstractmethod
    def fill_rectangle(self, x: int, y: int, width: int, height: int) -> None:
        """Fill a rectangle in the current pen color."""

    @abstractmethod
    def draw_text(self, text: str, x: int, y: int) -> None:
        """Draw text in the current pen color."""


class AudioOut(ABC):
    """Robot speaker. Volume 0 is silence. This is not the TTS synthesizer."""

    @abstractmethod
    def capabilities(self) -> AudioOutCapabilities:
        """Report whether a speaker or host playback is available."""

    @abstractmethod
    def set_volume(self, level: float) -> None:
        """Set gain in 0..1. 0 mutes clip playback."""

    @abstractmethod
    def volume(self) -> float:
        """Current gain in 0..1."""

    @abstractmethod
    def play_wav(self, wav_bytes: bytes) -> Playback:
        """Play a WAV clip. Volume 0 returns a duration and does not start audio."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the current clip. Safe when nothing is playing."""

    @abstractmethod
    def is_playing(self) -> bool:
        """True while a clip started by play_wav is still going."""


class AudioIn(ABC):
    """Microphone. Hardware mute is a physical switch the driver reports."""

    @abstractmethod
    def state(self) -> MicState:
        """Current mute, capture, rate, and whether a mic exists."""

    @abstractmethod
    def start(self) -> None:
        """Begin capture. A missing mic stays silent."""

    @abstractmethod
    def stop(self) -> None:
        """Stop capture."""

    @abstractmethod
    def read(self, max_samples: int) -> bytes:
        """PCM s16le mono, or empty when muted, idle, or no mic is present."""

    def inject_hardware_mute(self, muted: bool) -> None:
        """Test/sim injection. A board driver samples a GPIO and does not implement this."""
        raise UnsupportedOperationError(
            "hardware mic mute is read from the switch, not set by software"
        )


class Touch(ABC):
    """Single head-touch sensor. Pressed means raw value strictly above 0.5."""

    @abstractmethod
    def enable(self, timestep_ms: int) -> None:
        """Enable the sensor at the controller timestep."""

    @abstractmethod
    def raw_value(self) -> float:
        """Latest sensor reading. 0 when no sensor is attached."""

    def is_pressed(self, threshold: float = 0.5) -> bool:
        return self.raw_value() > threshold


class Leds(ABC):
    """Status, mic, offline, and celebration LEDs. Missing hardware still accepts writes."""

    @abstractmethod
    def capabilities(self) -> LedCapabilities:
        """Report whether LEDs are physically present, and their ids."""

    @abstractmethod
    def set_rgb(self, led_id: str, rgb: int) -> None:
        """Set one LED to 0xRRGGBB."""

    @abstractmethod
    def set_brightness(self, led_id: str, brightness: float) -> None:
        """Set one LED's brightness in 0..1."""

    @abstractmethod
    def get(self, led_id: str) -> LedState:
        """Last commanded color and brightness."""

    @abstractmethod
    def off(self, led_id: Optional[str] = None) -> None:
        """Turn one LED off, or all of them when led_id is None."""


class Power(ABC):
    """Battery, USB-C, dock, and voltage-dip flag."""

    @abstractmethod
    def state(self) -> PowerState:
        """Latest power reading. telemetry_present is false when nothing was measured."""


class Thermal(ABC):
    """Temperature sensor and the throttle state derived from it."""

    @abstractmethod
    def state(self) -> ThermalState:
        """Latest temperature and throttle. sensor_present is false when unmeasured."""


class Network(ABC):
    """Online or offline. Drivers must not probe the public internet to answer this."""

    @abstractmethod
    def state(self) -> NetworkState:
        """Link state. monitored is false when the link was not actually checked."""


class Clock(ABC):
    """Wall clock with a validity flag, and a monotonic clock for timers."""

    @abstractmethod
    def now(self) -> ClockReading:
        """Wall time. Invalid clocks return valid=False and wall_time=None."""

    @abstractmethod
    def monotonic(self) -> float:
        """Seconds from an arbitrary origin. Not the wall clock. Used for timers."""

    def set_time(self, wall_time: datetime, source: str) -> None:
        """Set an on-board RTC. The host clock refuses this so the sim cannot change the OS clock."""
        raise UnsupportedOperationError(
            "this clock cannot be set from software"
        )


class ConfigStore(ABC):
    """Small JSON config. commit is atomic; rollback drops uncommitted edits."""

    @abstractmethod
    def get(self, key: str, default=None):
        """Return a copy of the value, or default when the key is absent."""

    @abstractmethod
    def set(self, key: str, value) -> None:
        """Stage a JSON value. Nothing is durable until commit."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Stage a deletion. Raises KeyError when the key is absent."""

    @abstractmethod
    def keys(self) -> list:
        """Staged keys, in sorted order."""

    @abstractmethod
    def commit(self) -> None:
        """Make the staged values durable."""

    @abstractmethod
    def rollback(self) -> None:
        """Drop staged edits and restore the last successful commit."""


class Camera(ABC):
    """Camera. The sim enables the device and does not read frames."""

    @abstractmethod
    def capabilities(self) -> CameraCapabilities:
        """Report presence and resolution."""

    @abstractmethod
    def enable(self, timestep_ms: int) -> None:
        """Enable capture at the given period."""

    def frame(self) -> Optional[bytes]:
        """Latest frame, or None when this driver is not reading the sensor."""
        return None
