"""In-memory hardware. Scriptable from tests. No Webots and no host audio."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from hal.errors import UnsupportedAxisError
from hal.interfaces import (
    AudioIn,
    AudioOut,
    Camera,
    Clock,
    Display,
    HeadServos,
    Leds,
    Network,
    Playback,
    Power,
    Thermal,
    Touch,
)
from hal.pcm import wav_duration_seconds
from hal.storage import MemoryConfigStore
from hal.types import (
    AXIS_PITCH,
    AXIS_ROLL,
    AXIS_YAW,
    DISPLAY_COLOR_PANEL,
    DISPLAY_MONO_128X64,
    LED_IDS,
    POWER_BATTERY,
    THROTTLE_NORMAL,
    AudioOutCapabilities,
    CameraCapabilities,
    ClockReading,
    DisplayCapabilities,
    LedCapabilities,
    LedState,
    MicState,
    NetworkState,
    PowerState,
    ThermalState,
    as_float,
    axis_name,
    check_clock_source,
    check_power_source,
    check_throttle,
    clamp_to_limits,
    clamp_velocity,
    finite_number,
    is_voltage_dip,
    make_head_capabilities,
    mono_color,
    rgb24,
    throttle_for_celsius,
    unit_interval,
)


class MemoryHead(HeadServos):
    """Head servos held in RAM. Roll exists only when supports_roll is set."""

    def __init__(self, supports_roll: bool = False, feedback: bool = True):
        feedback_axes = {AXIS_YAW, AXIS_PITCH}
        if supports_roll:
            feedback_axes.add(AXIS_ROLL)
        if not feedback:
            feedback_axes = set()
        self._caps = make_head_capabilities(supports_roll, frozenset(feedback_axes))
        self._position = {AXIS_YAW: 0.0, AXIS_PITCH: 0.0}
        if supports_roll:
            self._position[AXIS_ROLL] = 0.0
        self._velocity = {axis: 0.0 for axis in self._position}
        self.position_calls = []
        self.velocity_calls = []

    def capabilities(self):
        return self._caps

    def _require(self, axis: str) -> str:
        name = axis_name(axis)
        if name not in self._position:
            raise UnsupportedAxisError(name)
        return name

    def set_position(self, axis: str, radians: float) -> None:
        name = self._require(axis)
        value = finite_number(radians, "radians")
        clamped = clamp_to_limits(value, self._caps.limits[name])
        self._position[name] = clamped
        self.position_calls.append((name, clamped))

    def set_velocity(self, axis: str, radians_per_sec: float) -> None:
        name = self._require(axis)
        speed = clamp_velocity(radians_per_sec, self._caps.limits[name])
        self._velocity[name] = speed
        self.velocity_calls.append((name, speed))

    def commanded_position(self, axis: str) -> float:
        return self._position[self._require(axis)]

    def feedback_position(self, axis: str) -> Optional[float]:
        name = self._require(axis)
        if name not in self._caps.feedback_axes:
            return None
        return self._position[name]

    def last_velocity(self, axis: str) -> float:
        return self._velocity[self._require(axis)]


class MemoryDisplay(Display):
    """Recording panel. Mono quantizes the pen to black or white."""

    def __init__(self, kind: str = DISPLAY_MONO_128X64, width: int = 128, height: int = 64):
        if kind == DISPLAY_MONO_128X64:
            if (width, height) != (128, 64):
                raise ValueError("mono_128x64 is fixed at 128x64")
            color = False
        elif kind == DISPLAY_COLOR_PANEL:
            if width < 1 or height < 1:
                raise ValueError("display size must be positive")
            color = True
        else:
            raise ValueError(f"unknown display kind {kind!r}")
        self._caps = DisplayCapabilities(
            kind=kind, width=width, height=height, color=color, present=True
        )
        self._pen = 0xFFFFFF
        self._opacity = 1.0
        self._alpha = 1.0
        self.ops = []

    def capabilities(self) -> DisplayCapabilities:
        return self._caps

    def set_opacity(self, alpha: float) -> None:
        self._opacity = unit_interval(alpha, "opacity")

    def set_alpha(self, alpha: float) -> None:
        self._alpha = unit_interval(alpha, "alpha")

    def set_color(self, color: int) -> None:
        pen = rgb24(color)
        if not self._caps.color:
            pen = mono_color(pen)
        self._pen = pen

    def fill_rectangle(self, x: int, y: int, width: int, height: int) -> None:
        self.ops.append(("rect", int(x), int(y), int(width), int(height), self._pen))

    def draw_text(self, text: str, x: int, y: int) -> None:
        self.ops.append(("text", str(text), int(x), int(y), self._pen))


class MemoryAudioOut(AudioOut):
    """Records clip playback. Volume 0 does not start audio."""

    def __init__(self):
        self._volume = 1.0
        self._playing = False
        self._duration = None
        self.plays = []

    def capabilities(self) -> AudioOutCapabilities:
        return AudioOutCapabilities(
            device_present=True,
            host_playback=False,
            volume_control=True,
            sample_rate_hz=24000,
        )

    def set_volume(self, level: float) -> None:
        self._volume = unit_interval(level, "volume")

    def volume(self) -> float:
        return self._volume

    def play_wav(self, wav_bytes: bytes) -> Playback:
        if not isinstance(wav_bytes, (bytes, bytearray)):
            raise TypeError("wav_bytes must be bytes")
        payload = bytes(wav_bytes)
        duration = wav_duration_seconds(payload)
        started = self._volume > 0.0
        self.plays.append(
            {"nbytes": len(payload), "volume": self._volume, "started": started, "duration": duration}
        )
        self._playing = started
        self._duration = duration
        playback = Playback(duration_seconds=duration)
        if not started:
            return playback
        playback.is_playing = lambda: self._playing  # type: ignore[method-assign]
        playback.stop = self.stop  # type: ignore[method-assign]
        return playback

    def stop(self) -> None:
        self._playing = False

    def is_playing(self) -> bool:
        return self._playing


class MemoryAudioIn(AudioIn):
    """Scriptable mic. Hardware mute drops queued samples instead of delaying them."""

    def __init__(self, device_present: bool = True, sample_rate_hz: int = 16000):
        if sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive")
        self._present = bool(device_present)
        self._rate = int(sample_rate_hz)
        self._mute = False
        self._capturing = False
        self._buffer = b""

    def state(self) -> MicState:
        return MicState(
            hardware_mute=self._mute,
            capturing=self._capturing,
            sample_rate_hz=self._rate,
            device_present=self._present,
        )

    def start(self) -> None:
        self._capturing = True

    def stop(self) -> None:
        self._capturing = False

    def inject_hardware_mute(self, muted: bool) -> None:
        if not isinstance(muted, bool):
            raise TypeError("muted must be a bool")
        self._mute = muted

    def push_pcm(self, pcm: bytes) -> None:
        if not isinstance(pcm, (bytes, bytearray)):
            raise TypeError("pcm must be bytes")
        if len(pcm) % 2 != 0:
            raise ValueError("PCM must be whole signed-16 samples")
        self._buffer += bytes(pcm)

    def read(self, max_samples: int) -> bytes:
        if isinstance(max_samples, bool) or not isinstance(max_samples, int) or max_samples < 0:
            raise ValueError("max_samples must be a non-negative int")
        if not self._present or not self._capturing or self._mute:
            self._buffer = b""
            return b""
        take = max_samples * 2
        chunk = self._buffer[:take]
        self._buffer = self._buffer[take:]
        return chunk


class MemoryTouch(Touch):
    def __init__(self):
        self._value = 0.0
        self.enabled_timestep = None

    def enable(self, timestep_ms: int) -> None:
        self.enabled_timestep = int(timestep_ms)

    def raw_value(self) -> float:
        return self._value

    def set_value(self, value: float) -> None:
        self._value = finite_number(value, "touch")

    def set_pressed(self, pressed: bool) -> None:
        if not isinstance(pressed, bool):
            raise TypeError("pressed must be a bool")
        self._value = 1.0 if pressed else 0.0


class MemoryLeds(Leds):
    def __init__(self, present: bool = True):
        self._present = bool(present)
        self._state = {led_id: LedState(rgb=0, brightness=0.0) for led_id in LED_IDS}

    def capabilities(self) -> LedCapabilities:
        return LedCapabilities(present=self._present, color=True, ids=LED_IDS)

    def _require(self, led_id: str) -> str:
        if led_id not in self._state:
            raise KeyError(led_id)
        return led_id

    def set_rgb(self, led_id: str, rgb: int) -> None:
        name = self._require(led_id)
        current = self._state[name]
        self._state[name] = LedState(rgb=rgb24(rgb), brightness=current.brightness)

    def set_brightness(self, led_id: str, brightness: float) -> None:
        name = self._require(led_id)
        current = self._state[name]
        self._state[name] = LedState(rgb=current.rgb, brightness=unit_interval(brightness, "brightness"))

    def get(self, led_id: str) -> LedState:
        return self._state[self._require(led_id)]

    def off(self, led_id: Optional[str] = None) -> None:
        names = LED_IDS if led_id is None else (self._require(led_id),)
        for name in names:
            self._state[name] = LedState(rgb=0, brightness=0.0)


class MemoryPower(Power):
    """Scriptable power rail. The Webots factory uses the same class with sim defaults."""

    def __init__(self, state: Optional[PowerState] = None):
        self._state = state if state is not None else PowerState(
            source=POWER_BATTERY,
            battery_percent=100.0,
            voltage_v=5.0,
            usb_connected=False,
            docked=False,
            charging=False,
            voltage_dip=False,
            telemetry_present=True,
        )
        self._check(self._state)

    @staticmethod
    def _check(state: PowerState) -> None:
        check_power_source(state.source)
        if state.battery_percent is not None:
            percent = finite_number(state.battery_percent, "battery_percent")
            if percent < 0.0 or percent > 100.0:
                raise ValueError("battery_percent must be between 0 and 100")
        if state.voltage_v is not None:
            finite_number(state.voltage_v, "voltage")
        for name in ("usb_connected", "docked", "charging", "voltage_dip", "telemetry_present"):
            if not isinstance(getattr(state, name), bool):
                raise TypeError(f"{name} must be a bool")

    def state(self) -> PowerState:
        return self._state

    def set_state(self, state: PowerState) -> None:
        self._check(state)
        self._state = state

    def set_voltage(self, voltage_v: Optional[float]) -> None:
        """Record a rail measurement and set voltage_dip from USB_DIP_BELOW_V."""
        if voltage_v is None:
            dip = False
            voltage = None
        else:
            voltage = finite_number(voltage_v, "voltage")
            dip = is_voltage_dip(voltage)
        self._state = PowerState(
            source=self._state.source,
            battery_percent=self._state.battery_percent,
            voltage_v=voltage,
            usb_connected=self._state.usb_connected,
            docked=self._state.docked,
            charging=self._state.charging,
            voltage_dip=dip,
            telemetry_present=True,
        )


class MemoryThermal(Thermal):
    def __init__(self, sensor_present: bool = True, celsius: Optional[float] = 28.0):
        self._sensor = bool(sensor_present)
        if self._sensor:
            if celsius is None:
                raise ValueError("a present thermal sensor needs a temperature")
            temp = finite_number(celsius, "celsius")
            self._celsius = temp
            self._throttle = throttle_for_celsius(temp)
        else:
            self._celsius = None
            self._throttle = THROTTLE_NORMAL

    def state(self) -> ThermalState:
        return ThermalState(
            celsius=self._celsius,
            throttle=self._throttle,
            sensor_present=self._sensor,
        )

    def set_celsius(self, celsius: float) -> None:
        temp = finite_number(celsius, "celsius")
        self._sensor = True
        self._celsius = temp
        self._throttle = throttle_for_celsius(temp)

    def set_throttle(self, throttle: str) -> None:
        """Override the throttle. Marks the sensor present so callers will honor it."""
        self._sensor = True
        self._throttle = check_throttle(throttle)

    def clear_sensor(self) -> None:
        self._sensor = False
        self._celsius = None
        self._throttle = THROTTLE_NORMAL


class MemoryNetwork(Network):
    """Online/offline flag. Nothing here opens a socket."""

    def __init__(self, online: bool = True, monitored: bool = True):
        if not isinstance(online, bool) or not isinstance(monitored, bool):
            raise TypeError("online and monitored must be bools")
        self._online = online
        self._monitored = monitored

    def state(self) -> NetworkState:
        return NetworkState(online=self._online, monitored=self._monitored)

    def set_online(self, online: bool, monitored: bool = True) -> None:
        if not isinstance(online, bool) or not isinstance(monitored, bool):
            raise TypeError("online and monitored must be bools")
        self._online = online
        self._monitored = monitored


class MemoryClock(Clock):
    """Scriptable clock. advance() moves the monotonic clock only, not the wall time."""

    def __init__(self):
        self._wall = datetime(2026, 11, 26, 9, 0, tzinfo=timezone.utc)
        self._valid = True
        self._source = "manual"
        self._mono = 0.0

    def now(self) -> ClockReading:
        return ClockReading(
            wall_time=self._wall if self._valid else None,
            valid=self._valid,
            source=self._source,
            monotonic_s=self._mono,
        )

    def monotonic(self) -> float:
        return self._mono

    def advance(self, seconds: float) -> None:
        step = finite_number(seconds, "seconds")
        if step < 0.0:
            raise ValueError("seconds must be >= 0")
        self._mono += step

    def set_wall(self, wall_time: datetime, source: str = "manual") -> None:
        if not isinstance(wall_time, datetime) or wall_time.tzinfo is None:
            raise ValueError("wall time must be a timezone-aware datetime")
        self._wall = wall_time
        self._valid = True
        self._source = check_clock_source(source)

    def set_invalid(self) -> None:
        self._wall = None
        self._valid = False
        self._source = "unset"

    def set_time(self, wall_time: datetime, source: str) -> None:
        self.set_wall(wall_time, source)


class MemoryCamera(Camera):
    def __init__(self):
        self.enabled_timestep = None
        self._frame = None

    def capabilities(self) -> CameraCapabilities:
        return CameraCapabilities(present=True, width=160, height=120)

    def enable(self, timestep_ms: int) -> None:
        self.enabled_timestep = int(timestep_ms)

    def push_frame(self, frame: bytes) -> None:
        if not isinstance(frame, (bytes, bytearray)):
            raise TypeError("frame must be bytes")
        self._frame = bytes(frame)

    def frame(self):
        return self._frame


def sim_power_state() -> PowerState:
    """Workstation-powered sim: running, so USB is assumed, and nothing was measured."""
    return PowerState(
        source="usb",
        battery_percent=None,
        voltage_v=None,
        usb_connected=True,
        docked=False,
        charging=False,
        voltage_dip=False,
        telemetry_present=False,
    )


def sim_thermal() -> MemoryThermal:
    """The world has no temperature sensor, so throttle stays normal and unmeasured."""
    return MemoryThermal(sensor_present=False, celsius=None)


def build_mock_hardware(supports_roll: bool = False, display_kind: str = DISPLAY_MONO_128X64):
    """A full in-memory bundle. Roll is off and the panel is mono unless a test says otherwise."""
    from hal.bundle import Hardware

    return Hardware(
        head=MemoryHead(supports_roll=supports_roll),
        display=MemoryDisplay(kind=display_kind),
        audio_out=MemoryAudioOut(),
        audio_in=MemoryAudioIn(device_present=True),
        touch=MemoryTouch(),
        leds=MemoryLeds(present=True),
        power=MemoryPower(),
        thermal=MemoryThermal(),
        network=MemoryNetwork(online=True, monitored=True),
        clock=MemoryClock(),
        storage=MemoryConfigStore(),
        camera=MemoryCamera(),
    )
