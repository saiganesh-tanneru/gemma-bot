"""Webots-backed drivers.

Devices that exist in worlds/gemma_bot.wbt are wrapped here. Devices the
world does not contain use the in-memory models with sim defaults, so the
controller has one code path and the sim does not pretend a sensor was read.
Nothing in this module opens a socket or contacts a cloud API.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Optional

from hal.interfaces import AudioOut, Camera, Clock, Display, HeadServos, Playback, Touch
from hal.mock import (
    MemoryAudioIn,
    MemoryLeds,
    MemoryNetwork,
    MemoryPower,
    sim_power_state,
    sim_thermal,
)
from hal.pcm import wav_duration_seconds
from hal.storage import FileConfigStore, default_config_path
from hal.types import (
    AXIS_PITCH,
    AXIS_YAW,
    DISPLAY_COLOR_PANEL,
    AudioOutCapabilities,
    CameraCapabilities,
    ClockReading,
    DisplayCapabilities,
    as_float,
    axis_name,
    clamp_to_limits,
    clamp_velocity,
    finite_number,
    make_head_capabilities,
    rgb24,
    unit_interval,
)

logger = logging.getLogger("gemma_bot_hal")

# World device names.
YAW_MOTOR_NAME = "head_yaw"
PITCH_MOTOR_NAME = "head_pitch"
YAW_SENSOR_NAME = "yaw_sensor"
PITCH_SENSOR_NAME = "pitch_sensor"
DISPLAY_NAME = "oled_display"
TOUCH_NAME = "head_touch"
CAMERA_NAME = "camera"

_DISPLAY_WIDTH = 128
_DISPLAY_HEIGHT = 64
_CAMERA_WIDTH = 160
_CAMERA_HEIGHT = 120


def select_host_player(wav_path: str) -> Optional[list]:
    """Same player order as controllers/gemma_bot_controller/tts.py.

    The sim has no speaker device. Clip playback uses the host, which is
    what speech already does.
    """
    if sys.platform == "darwin" and shutil.which("afplay"):
        return ["afplay", wav_path]
    for candidate in ("aplay", "paplay", "ffplay"):
        if shutil.which(candidate):
            if candidate == "ffplay":
                return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", wav_path]
            return [candidate, wav_path]
    return None


def _lookup(robot, provided, name: str):
    if provided is not None or robot is None:
        return provided
    getter = getattr(robot, "getDevice", None)
    if getter is None:
        return None
    return getter(name)


def _device_int(device, method: str) -> Optional[int]:
    getter = getattr(device, method, None)
    if not callable(getter):
        return None
    value = getter()
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 1:
        return None
    return value


class WebotsHead(HeadServos):
    """Yaw and pitch motors. supports_roll is false. Position sensors are read only on demand."""

    def __init__(self, yaw_motor, pitch_motor, yaw_sensor=None, pitch_sensor=None, timestep_ms: int = 16):
        self._motors = {AXIS_YAW: yaw_motor, AXIS_PITCH: pitch_motor}
        self._sensors = {}
        if yaw_sensor is not None:
            self._sensors[AXIS_YAW] = yaw_sensor
        if pitch_sensor is not None:
            self._sensors[AXIS_PITCH] = pitch_sensor
        self._timestep_ms = int(timestep_ms)
        self._sensor_enabled = set()
        self._position = {AXIS_YAW: 0.0, AXIS_PITCH: 0.0}
        self._caps = make_head_capabilities(False, frozenset(self._sensors))

    def capabilities(self):
        return self._caps

    def _require(self, axis: str) -> str:
        name = axis_name(axis)
        if name not in self._motors:
            raise UnsupportedAxisError(name)
        return name

    def set_position(self, axis: str, radians: float) -> None:
        name = self._require(axis)
        value = finite_number(radians, "radians")
        clamped = clamp_to_limits(value, self._caps.limits[name])
        self._position[name] = clamped
        motor = self._motors[name]
        if motor is not None:
            motor.setPosition(clamped)

    def set_velocity(self, axis: str, radians_per_sec: float) -> None:
        name = self._require(axis)
        speed = clamp_velocity(radians_per_sec, self._caps.limits[name])
        motor = self._motors[name]
        if motor is not None:
            motor.setVelocity(speed)

    def commanded_position(self, axis: str) -> float:
        return self._position[self._require(axis)]

    def feedback_position(self, axis: str) -> Optional[float]:
        name = self._require(axis)
        sensor = self._sensors.get(name)
        if sensor is None:
            return None
        if name not in self._sensor_enabled:
            enable = getattr(sensor, "enable", None)
            if callable(enable):
                enable(self._timestep_ms)
            self._sensor_enabled.add(name)
        getter = getattr(sensor, "getValue", None)
        if not callable(getter):
            return None
        return as_float(getter())


class WebotsDisplay(Display):
    """Webots Display. It is a color panel; pen colors are not quantized."""

    def __init__(self, device, width: int = _DISPLAY_WIDTH, height: int = _DISPLAY_HEIGHT):
        self._device = device
        measured_w = _device_int(device, "getWidth") if device is not None else None
        measured_h = _device_int(device, "getHeight") if device is not None else None
        self._caps = DisplayCapabilities(
            kind=DISPLAY_COLOR_PANEL,
            width=measured_w or width,
            height=measured_h or height,
            color=True,
            present=device is not None,
        )

    def capabilities(self) -> DisplayCapabilities:
        return self._caps

    def set_opacity(self, alpha: float) -> None:
        value = unit_interval(alpha, "opacity")
        if self._device is not None:
            self._device.setOpacity(value)

    def set_alpha(self, alpha: float) -> None:
        value = unit_interval(alpha, "alpha")
        if self._device is not None and hasattr(self._device, "setAlpha"):
            self._device.setAlpha(value)

    def set_color(self, color: int) -> None:
        pen = rgb24(color)
        if self._device is not None:
            self._device.setColor(pen)

    def fill_rectangle(self, x: int, y: int, width: int, height: int) -> None:
        if self._device is not None:
            self._device.fillRectangle(int(x), int(y), int(width), int(height))

    def draw_text(self, text: str, x: int, y: int) -> None:
        if self._device is not None:
            self._device.drawText(str(text), int(x), int(y))


class _HostPlayback(Playback):
    def __init__(self, duration_seconds, process, temp_path: Optional[str]):
        super().__init__(duration_seconds=duration_seconds)
        self._process = process
        self._temp_path = temp_path

    def is_playing(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def stop(self) -> None:
        if self._process is not None and self._process.poll() is None:
            try:
                self._process.terminate()
            except Exception:
                pass
        self._process = None
        if self._temp_path and os.path.exists(self._temp_path):
            try:
                os.unlink(self._temp_path)
            except OSError:
                pass
            self._temp_path = None


class HostSpeaker(AudioOut):
    """Host clip player. There is no speaker in the Webots world.

    Player choice matches tts.py. Volume 0 skips the player. Other volumes
    are stored; the host players do not share one volume flag, and a board
    driver is what actually scales the samples.
    """

    def __init__(self):
        self._volume = 1.0
        self._active: Optional[_HostPlayback] = None

    def capabilities(self) -> AudioOutCapabilities:
        return AudioOutCapabilities(
            device_present=False,
            host_playback=True,
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
        self.stop()
        payload = bytes(wav_bytes)
        duration = wav_duration_seconds(payload)
        if self._volume == 0.0:
            self._active = None
            return Playback(duration_seconds=duration)

        fd, wav_path = tempfile.mkstemp(prefix="gemma_hal_", suffix=".wav")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
            command = select_host_player(wav_path)
            if command is None:
                logger.warning("No audio player found on PATH; clip duration only")
                os.unlink(wav_path)
                self._active = None
                return Playback(duration_seconds=duration)
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            logger.warning("Host clip playback failed: %s", exc)
            if os.path.exists(wav_path):
                try:
                    os.unlink(wav_path)
                except OSError:
                    pass
            self._active = None
            return Playback(duration_seconds=duration)

        self._active = _HostPlayback(duration, process, wav_path)
        return self._active

    def stop(self) -> None:
        if self._active is not None:
            self._active.stop()
            self._active = None

    def is_playing(self) -> bool:
        return self._active is not None and self._active.is_playing()


class WebotsTouch(Touch):
    """head_touch. Pressed is raw value strictly above 0.5, matching the controller."""

    def __init__(self, device):
        self._device = device

    def enable(self, timestep_ms: int) -> None:
        if self._device is not None and hasattr(self._device, "enable"):
            self._device.enable(int(timestep_ms))

    def raw_value(self) -> float:
        if self._device is None:
            return 0.0
        getter = getattr(self._device, "getValue", None)
        if not callable(getter):
            return 0.0
        value = as_float(getter())
        if value is None:
            return 0.0
        return value


class WebotsCamera(Camera):
    """Enables the sim camera. frame() does not call getImage."""

    def __init__(self, device, width: int = _CAMERA_WIDTH, height: int = _CAMERA_HEIGHT):
        self._device = device
        measured_w = _device_int(device, "getWidth") if device is not None else None
        measured_h = _device_int(device, "getHeight") if device is not None else None
        self._caps = CameraCapabilities(
            present=device is not None,
            width=measured_w or width,
            height=measured_h or height,
        )

    def capabilities(self) -> CameraCapabilities:
        return self._caps

    def enable(self, timestep_ms: int) -> None:
        if self._device is not None and hasattr(self._device, "enable"):
            self._device.enable(int(timestep_ms))

    def frame(self):
        return None


class HostClock(Clock):
    """Wall time from the computer running the sim. set_time is refused.

    Refusing the set keeps a test from calling settimeofday on the host.
    A board driver with a coin-cell RTC implements set_time instead.
    """

    def now(self) -> ClockReading:
        mono = self.monotonic()
        return ClockReading(
            wall_time=_utc_now(),
            valid=True,
            source="host",
            monotonic_s=mono,
        )

    def monotonic(self) -> float:
        return _monotonic()


def _utc_now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def _monotonic() -> float:
    import time

    return time.monotonic()


def build_webots_hardware(
    robot=None,
    timestep_ms: int = 16,
    display=None,
    camera=None,
    yaw_motor=None,
    pitch_motor=None,
    yaw_sensor=None,
    pitch_sensor=None,
    touch=None,
    config_path=None,
):
    """Assemble drivers for the current Webots world.

    Imported lazily from hal.bundle to keep this module usable on its own
    in unit tests that construct individual drivers.
    """
    from hal.bundle import Hardware

    yaw_motor = _lookup(robot, yaw_motor, YAW_MOTOR_NAME)
    pitch_motor = _lookup(robot, pitch_motor, PITCH_MOTOR_NAME)
    yaw_sensor = _lookup(robot, yaw_sensor, YAW_SENSOR_NAME)
    pitch_sensor = _lookup(robot, pitch_sensor, PITCH_SENSOR_NAME)
    display = _lookup(robot, display, DISPLAY_NAME)
    touch = _lookup(robot, touch, TOUCH_NAME)
    camera = _lookup(robot, camera, CAMERA_NAME)
    path = default_config_path() if config_path is None else config_path

    return Hardware(
        head=WebotsHead(yaw_motor, pitch_motor, yaw_sensor, pitch_sensor, timestep_ms=timestep_ms),
        display=WebotsDisplay(display),
        audio_out=HostSpeaker(),
        audio_in=MemoryAudioIn(device_present=False),
        touch=WebotsTouch(touch),
        leds=MemoryLeds(present=False),
        power=MemoryPower(sim_power_state()),
        thermal=sim_thermal(),
        network=MemoryNetwork(online=True, monitored=False),
        clock=HostClock(),
        storage=FileConfigStore(path),
        camera=WebotsCamera(camera),
    )
