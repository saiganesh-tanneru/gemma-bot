"""HAL mocks, Webots adapters, and controller wiring."""

import io
import json
import os
import shutil
import socket
import sys
import types
import wave
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTROLLER_DIR = REPO_ROOT / "controllers" / "gemma_bot_controller"
for _path in (str(REPO_ROOT), str(CONTROLLER_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from hal import (  # noqa: E402
    UnsupportedAxisError,
    UnsupportedOperationError,
    build_mock_hardware,
    build_webots_hardware,
)
from hal.mock import (  # noqa: E402
    MemoryAudioIn,
    MemoryAudioOut,
    MemoryClock,
    MemoryDisplay,
    MemoryHead,
    MemoryLeds,
    MemoryNetwork,
    MemoryPower,
    MemoryThermal,
    MemoryTouch,
)
from hal.storage import FileConfigStore, MemoryConfigStore, default_config_path  # noqa: E402
from hal.types import DISPLAY_COLOR_PANEL, POWER_DOCK, LedState, PowerState  # noqa: E402
from hal.webots import (  # noqa: E402
    HostClock,
    HostSpeaker,
    WebotsDisplay,
    WebotsHead,
    WebotsTouch,
    select_host_player,
)


def _wav_bytes(duration_sec: float = 0.5, sample_rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    frames = int(duration_sec * sample_rate)
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frames)
    return buffer.getvalue()


class _RecMotor:
    def __init__(self):
        self.positions = []
        self.velocities = []

    def setPosition(self, position):
        self.positions.append(position)

    def setVelocity(self, velocity):
        self.velocities.append(velocity)


class _RecTouch:
    def __init__(self):
        self.value = 0.0
        self.enabled = None

    def enable(self, timestep):
        self.enabled = timestep

    def getValue(self):
        return self.value


class _RecDisplay:
    def __init__(self):
        self.opacity = None
        self.alpha = None
        self.colors = []
        self.rects = []

    def setOpacity(self, value):
        self.opacity = value

    def setAlpha(self, value):
        self.alpha = value

    def setColor(self, color):
        self.colors.append(color)

    def fillRectangle(self, x, y, width, height):
        self.rects.append((x, y, width, height, self.colors[-1]))

    def drawText(self, text, x, y):
        pass


class _RecCamera:
    def __init__(self):
        self.enabled = None
        self.image_reads = 0

    def enable(self, timestep):
        self.enabled = timestep

    def getWidth(self):
        return 160

    def getHeight(self):
        return 120

    def getImage(self):
        self.image_reads += 1
        return b"frame"


class _RecSensor:
    def __init__(self, value):
        self.value = value
        self.enable_calls = []

    def enable(self, timestep):
        self.enable_calls.append(timestep)

    def getValue(self):
        return self.value


def _install_webots_stub():
    controller_stub = types.ModuleType("controller")

    class _Motor:
        def setPosition(self, position):
            pass

        def setVelocity(self, velocity):
            pass

    class _Display:
        def setOpacity(self, value):
            pass

        def setAlpha(self, value):
            pass

        def setColor(self, color):
            pass

        def fillRectangle(self, x, y, width, height):
            pass

        def drawText(self, text, x, y):
            pass

    class _Keyboard:
        LEFT, RIGHT, UP, DOWN = 314, 316, 315, 317

        def enable(self, timestep):
            pass

        def getKey(self):
            return -1

    class _Touch:
        def __init__(self):
            self.value = 0.0

        def enable(self, timestep):
            pass

        def getValue(self):
            return self.value

    class _Supervisor:
        def getBasicTimeStep(self):
            return 16

        def getDevice(self, name):
            if name == "oled_display":
                return _Display()
            if name in ("head_yaw", "head_pitch"):
                return _Motor()
            if name == "head_touch":
                return _Touch()
            return MagicMock()

        def getKeyboard(self):
            return _Keyboard()

        def step(self, timestep):
            return -1

    controller_stub.Robot = _Supervisor
    controller_stub.Supervisor = _Supervisor
    controller_stub.Keyboard = _Keyboard
    sys.modules["controller"] = controller_stub


def _controller_module():
    """Import the controller without replacing a stub an earlier test already bound."""
    if "gemma_bot_controller" in sys.modules:
        return sys.modules["gemma_bot_controller"]
    _install_webots_stub()
    import gemma_bot_controller

    return gemma_bot_controller


def test_mock_bundle_defaults_differ_from_the_sim():
    mock = build_mock_hardware()
    assert mock.head.capabilities().supports_roll is False
    assert mock.head.capabilities().supports_yaw is True
    assert mock.head.capabilities().supports_pitch is True
    assert mock.display.capabilities().kind == "mono_128x64"
    assert mock.display.capabilities().color is False
    assert (mock.display.capabilities().width, mock.display.capabilities().height) == (128, 64)
    assert mock.audio_in.state().device_present is True
    assert mock.leds.capabilities().present is True
    assert mock.power.state().source == "battery"
    assert mock.power.state().telemetry_present is True
    assert mock.power.state().battery_percent == 100.0
    assert mock.thermal.state().sensor_present is True
    assert mock.thermal.state().throttle == "normal"
    assert mock.network.state() == mock.network.state()
    assert mock.network.state().online is True
    assert mock.network.state().monitored is True
    assert mock.clock.now().valid is True

    rolled = build_mock_hardware(supports_roll=True, display_kind=DISPLAY_COLOR_PANEL)
    assert rolled.head.capabilities().supports_roll is True
    assert rolled.display.capabilities().color is True
    assert rolled.display.capabilities().kind == DISPLAY_COLOR_PANEL


def test_head_limits_roll_flag_and_exact_interior_position():
    head = MemoryHead()
    aimed = 0.25
    head.set_position("yaw", aimed)
    assert head.commanded_position("yaw") == aimed
    assert head.position_calls[-1] == ("yaw", aimed)
    head.set_position("YAW", 2.0)
    assert head.commanded_position("yaw") == pytest.approx(1.4)
    head.set_position("pitch", -1.0)
    assert head.commanded_position("pitch") == pytest.approx(-0.45)
    with pytest.raises(UnsupportedAxisError):
        head.set_position("roll", 0.1)
    with pytest.raises(ValueError):
        head.set_position("yaw", float("nan"))
    with pytest.raises(ValueError):
        head.set_velocity("pitch", -0.1)
    head.set_velocity("yaw", 10.0)
    assert head.last_velocity("yaw") == pytest.approx(4.0)
    assert head.feedback_position("yaw") == pytest.approx(1.4)

    roll = MemoryHead(supports_roll=True)
    roll.set_position("roll", 0.2)
    assert roll.commanded_position("roll") == pytest.approx(0.2)
    roll.set_position("roll", 3.0)
    assert roll.commanded_position("roll") == pytest.approx(0.6)
    assert "roll" in roll.capabilities().feedback_axes

    blind = MemoryHead(feedback=False)
    blind.set_position("yaw", 0.1)
    assert blind.feedback_position("yaw") is None


def test_webots_head_forwards_commands_and_reads_sensors_on_demand():
    yaw = _RecMotor()
    pitch = _RecMotor()
    yaw_sensor = _RecSensor(0.2)
    head = WebotsHead(yaw, pitch, yaw_sensor=yaw_sensor, timestep_ms=16)
    assert head.capabilities().supports_roll is False
    assert "yaw" in head.capabilities().feedback_axes
    assert "pitch" not in head.capabilities().feedback_axes
    head.set_position("yaw", 0.3)
    head.set_velocity("pitch", 2.5)
    assert yaw.positions == [0.3]
    assert pitch.velocities == [2.5]
    assert yaw_sensor.enable_calls == []
    assert head.feedback_position("yaw") == pytest.approx(0.2)
    assert yaw_sensor.enable_calls == [16]
    head.feedback_position("yaw")
    assert yaw_sensor.enable_calls == [16]
    assert head.feedback_position("pitch") is None
    with pytest.raises(UnsupportedAxisError):
        head.set_position("roll", 0.1)

    unreadable = WebotsHead(yaw, pitch, yaw_sensor=MagicMock(), timestep_ms=16)
    assert unreadable.feedback_position("yaw") is None


def test_display_mono_quantizes_and_color_panel_keeps_rgb():
    mono = MemoryDisplay()
    mono.set_color(0x00F0FF)
    mono.fill_rectangle(0, 0, 2, 2)
    assert mono.ops[-1] == ("rect", 0, 0, 2, 2, 0xFFFFFF)
    mono.set_color(0x003300)
    mono.fill_rectangle(1, 1, 1, 1)
    assert mono.ops[-1][-1] == 0x000000
    mono.set_color(0x808080)
    mono.fill_rectangle(0, 0, 1, 1)
    assert mono.ops[-1][-1] == 0xFFFFFF
    with pytest.raises(ValueError):
        MemoryDisplay(width=64, height=32)

    color = MemoryDisplay(kind=DISPLAY_COLOR_PANEL)
    color.set_color(0x00F0FF)
    color.draw_text("hi", 4, 5)
    assert color.ops[-1] == ("text", "hi", 4, 5, 0x00F0FF)

    panel = _RecDisplay()
    webots = WebotsDisplay(panel)
    assert webots.capabilities().color is True
    assert webots.capabilities().kind == DISPLAY_COLOR_PANEL
    assert (webots.capabilities().width, webots.capabilities().height) == (128, 64)
    webots.set_opacity(1.0)
    webots.set_alpha(1.0)
    webots.set_color(0x00F0FF)
    webots.fill_rectangle(1, 2, 3, 4)
    assert panel.opacity == 1.0
    assert panel.alpha == 1.0
    assert panel.rects == [(1, 2, 3, 4, 0x00F0FF)]


def test_audio_out_volume_and_host_player_order(monkeypatch):
    speaker = MemoryAudioOut()
    wav = _wav_bytes(0.5, 16000)
    playing = speaker.play_wav(wav)
    assert playing.duration_seconds == pytest.approx(0.5, abs=0.02)
    assert speaker.is_playing() is True
    speaker.stop()
    assert speaker.is_playing() is False
    speaker.set_volume(0.0)
    speaker.play_wav(wav)
    assert speaker.is_playing() is False
    assert speaker.plays[-1]["started"] is False

    host = HostSpeaker()
    host.set_volume(0.0)
    with patch("hal.webots.subprocess.Popen") as popen:
        silent = host.play_wav(wav)
        popen.assert_not_called()
    assert silent.duration_seconds == pytest.approx(0.5, abs=0.02)
    assert host.is_playing() is False

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(shutil, "which", lambda name: "/bin/aplay" if name == "aplay" else None)
    host.set_volume(1.0)
    with patch("hal.webots.subprocess.Popen") as popen:
        process = MagicMock()
        process.poll.return_value = None
        popen.return_value = process
        host.play_wav(wav)
        command = popen.call_args[0][0]
        assert command[0] == "aplay"
        assert command[1].endswith(".wav")
    assert host.is_playing() is True
    host.stop()
    process.terminate.assert_called_once()

    from tts import _select_audio_player

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(shutil, "which", lambda name: "/bin/aplay" if name == "aplay" else None)
    assert select_host_player("clip.wav") == ["aplay", "clip.wav"]
    assert select_host_player("clip.wav") == _select_audio_player("clip.wav")
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(shutil, "which", lambda name: "/bin/afplay" if name == "afplay" else None)
    assert select_host_player("clip.wav") == ["afplay", "clip.wav"]
    assert _select_audio_player("clip.wav") == ["afplay", "clip.wav"]
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(shutil, "which", lambda name: "/bin/ffplay" if name == "ffplay" else None)
    expected = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "clip.wav"]
    assert select_host_player("clip.wav") == expected
    assert _select_audio_player("clip.wav") == expected


def test_mic_hardware_mute_drops_samples_and_sim_has_no_mic():
    mic = MemoryAudioIn()
    mic.push_pcm(b"\x01\x00")
    assert mic.read(4) == b""
    mic.start()
    mic.push_pcm(b"\x01\x00\x02\x00")
    assert mic.read(4) == b"\x01\x00\x02\x00"
    mic.push_pcm(b"\x03\x00\x04\x00")
    mic.inject_hardware_mute(True)
    assert mic.state().hardware_mute is True
    assert mic.read(4) == b""
    mic.inject_hardware_mute(False)
    assert mic.read(4) == b""
    mic.push_pcm(b"\x05\x00")
    assert mic.read(1) == b"\x05\x00"
    mic.stop()
    mic.push_pcm(b"\x06\x00")
    assert mic.read(1) == b""
    with pytest.raises(ValueError):
        mic.push_pcm(b"\x01")

    sim = MemoryAudioIn(device_present=False)
    sim.start()
    sim.push_pcm(b"\x01\x00")
    assert sim.read(4) == b""
    sim.inject_hardware_mute(True)
    assert sim.state().hardware_mute is True


def test_touch_threshold_matches_the_controller():
    touch = MemoryTouch()
    touch.enable(16)
    touch.set_value(0.5)
    assert touch.is_pressed() is False
    touch.set_value(0.5 + 1e-9)
    assert touch.is_pressed() is True
    touch.set_pressed(False)
    assert touch.raw_value() == 0.0

    device = _RecTouch()
    wrapped = WebotsTouch(device)
    wrapped.enable(16)
    assert device.enabled == 16
    device.value = 0.5
    assert wrapped.is_pressed() is False
    device.value = 1.0
    assert wrapped.is_pressed() is True
    assert WebotsTouch(None).raw_value() == 0.0


def test_leds_power_thermal_and_network():
    leds = MemoryLeds(present=True)
    leds.set_rgb("status", 0xFF0000)
    leds.set_brightness("status", 0.25)
    assert leds.get("status") == LedState(rgb=0xFF0000, brightness=0.25)
    leds.set_rgb("celebration", 0x00FF00)
    leds.off("status")
    assert leds.get("status") == LedState(rgb=0, brightness=0.0)
    assert leds.get("celebration").rgb == 0x00FF00
    leds.off()
    assert leds.get("celebration") == LedState(rgb=0, brightness=0.0)
    with pytest.raises(KeyError):
        leds.set_rgb("not-a-led", 0)
    dark = MemoryLeds(present=False)
    assert dark.capabilities().present is False
    dark.set_rgb("offline", 0x0000FF)
    assert dark.get("offline").rgb == 0x0000FF

    power = MemoryPower()
    power.set_voltage(4.5)
    assert power.state().voltage_dip is True
    assert power.state().telemetry_present is True
    power.set_voltage(4.6)
    assert power.state().voltage_dip is False
    power.set_voltage(5.0)
    assert power.state().voltage_dip is False
    power.set_state(
        PowerState(
            source=POWER_DOCK,
            battery_percent=40.0,
            voltage_v=5.0,
            usb_connected=False,
            docked=True,
            charging=True,
            voltage_dip=False,
            telemetry_present=True,
        )
    )
    assert power.state().docked is True
    assert power.state().charging is True
    assert power.state().source == POWER_DOCK

    thermal = MemoryThermal()
    assert thermal.state().celsius == pytest.approx(28.0)
    thermal.set_celsius(33.9)
    assert thermal.state().throttle == "normal"
    thermal.set_celsius(34.0)
    assert thermal.state().throttle == "reduced"
    thermal.set_celsius(38.0)
    assert thermal.state().throttle == "limited"
    thermal.clear_sensor()
    assert thermal.state().sensor_present is False
    assert thermal.state().celsius is None
    assert thermal.state().throttle == "normal"

    link = MemoryNetwork()
    link.set_online(False)
    assert link.state().online is False
    assert link.state().monitored is True


def test_clock_validity_is_independent_of_monotonic_time():
    clock = MemoryClock()
    wall = clock.now().wall_time
    assert wall is not None and wall.tzinfo is not None
    clock.advance(5.0)
    assert clock.monotonic() == pytest.approx(5.0)
    assert clock.now().wall_time == wall
    clock.set_time(datetime(2026, 1, 1, tzinfo=timezone.utc), "manual")
    assert clock.now().valid is True
    assert clock.monotonic() == pytest.approx(5.0)
    clock.set_invalid()
    reading = clock.now()
    assert reading.valid is False
    assert reading.wall_time is None
    assert reading.source == "unset"
    with pytest.raises(ValueError):
        clock.advance(-1)
    with pytest.raises(ValueError):
        clock.set_wall(datetime(2026, 1, 1), "manual")

    host = HostClock()
    assert host.now().valid is True
    assert host.now().source == "host"
    assert host.now().wall_time.tzinfo is not None
    with pytest.raises(UnsupportedOperationError):
        host.set_time(datetime(2026, 1, 1, tzinfo=timezone.utc), "manual")


def test_memory_config_copies_values_and_rolls_back():
    store = MemoryConfigStore()
    store.set("name", {"robot": "Gema"})
    edited = store.get("name")
    edited["robot"] = "changed"
    assert store.get("name") == {"robot": "Gema"}
    store.set("city", "Pune")
    store.commit()
    store.set("city", "Hyderabad")
    store.delete("name")
    store.rollback()
    assert store.get("city") == "Pune"
    assert store.get("name") == {"robot": "Gema"}
    with pytest.raises(TypeError):
        store.set("bad", object())
    with pytest.raises(KeyError):
        store.delete("missing")
    with pytest.raises(ValueError):
        store.set("", 1)
    assert store.keys() == ["city", "name"]


def test_file_config_is_atomic_and_survives_a_missed_commit(tmp_path, monkeypatch):
    path = tmp_path / "robot-config.json"
    store = FileConfigStore(path)
    assert path.exists() is False
    store.set("a", 1)
    store.commit()
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
    assert path.with_name(path.name + ".tmp").exists() is False

    reopened = FileConfigStore(path)
    assert reopened.get("a") == 1
    reopened.set("a", 2)
    reopened.rollback()
    assert reopened.get("a") == 1

    reopened.set("a", 3)
    crashed = FileConfigStore(path)
    assert crashed.get("a") == 1

    dirty = FileConfigStore(path)
    dirty.set("a", 4)

    def fail_replace(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        dirty.commit()
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
    assert path.with_name(path.name + ".tmp").exists() is False
    dirty.rollback()
    assert dirty.get("a") == 1

    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        FileConfigStore(broken)
    broken.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        FileConfigStore(broken)


def test_webots_factory_does_not_touch_the_network_or_invent_sensors(tmp_path, monkeypatch):
    def fail_socket(*_args, **_kwargs):
        raise AssertionError("HAL opened a socket")

    monkeypatch.setattr(socket, "socket", fail_socket)
    monkeypatch.setattr(socket, "create_connection", fail_socket)

    camera = _RecCamera()
    hardware = build_webots_hardware(
        robot=None,
        timestep_ms=16,
        yaw_motor=_RecMotor(),
        pitch_motor=_RecMotor(),
        touch=_RecTouch(),
        display=_RecDisplay(),
        camera=camera,
        config_path=tmp_path / "robot-config.json",
    )
    build_mock_hardware()

    assert hardware.head.capabilities().supports_roll is False
    assert hardware.power.state().telemetry_present is False
    assert hardware.power.state().usb_connected is True
    assert hardware.power.state().docked is False
    assert hardware.power.state().voltage_dip is False
    assert hardware.power.state().voltage_v is None
    assert hardware.thermal.state().sensor_present is False
    assert hardware.thermal.state().throttle == "normal"
    assert hardware.network.state().online is True
    assert hardware.network.state().monitored is False
    assert hardware.audio_in.state().device_present is False
    assert hardware.audio_out.capabilities().device_present is False
    assert hardware.audio_out.capabilities().host_playback is True
    assert hardware.leds.capabilities().present is False
    assert hardware.clock.now().source == "host"
    assert (tmp_path / "robot-config.json").exists() is False

    hardware.camera.enable(32)
    assert camera.enabled == 32
    assert hardware.camera.frame() is None
    assert camera.image_reads == 0
    with pytest.raises(UnsupportedOperationError):
        hardware.clock.set_time(datetime(2026, 1, 1, tzinfo=timezone.utc), "ntp")


def test_controller_runs_motion_touch_and_display_through_the_hal(tmp_path):
    module = _controller_module()
    from tts import TTSHandle

    yaw = _RecMotor()
    pitch = _RecMotor()
    touch = _RecTouch()
    display = _RecDisplay()
    camera = _RecCamera()
    hardware = build_webots_hardware(
        robot=None,
        timestep_ms=16,
        yaw_motor=yaw,
        pitch_motor=pitch,
        touch=touch,
        display=display,
        camera=camera,
        config_path=tmp_path / "robot-config.json",
    )
    bot = module.GemmaBotCompanion(start_server=False, hardware=hardware)
    assert yaw.velocities == [bot.YAW_SPEED]
    assert pitch.velocities == [bot.PITCH_SPEED]
    assert yaw.positions[0] == 0.0
    assert pitch.positions[0] == 0.0
    assert camera.enabled == bot.timestep * 2
    assert camera.image_reads == 0
    assert display.rects
    assert (tmp_path / "robot-config.json").exists() is False

    bot.cur_yaw = 0.2
    bot.target_yaw = 0.2
    bot.cur_pitch = -0.1
    bot.target_pitch = -0.1
    speed_writes = (len(yaw.velocities), len(pitch.velocities))
    bot.update_animation()
    assert yaw.positions[-1] == pytest.approx(bot.cur_yaw)
    assert pitch.positions[-1] == pytest.approx(bot.cur_pitch)
    assert (len(yaw.velocities), len(pitch.velocities)) == speed_writes

    touch.value = 0.5
    bot.handle_keyboard_input()
    assert bot.active_gesture is None
    touch.value = 1.0
    bot.handle_keyboard_input()
    assert bot.mood == "HAPPY"
    assert bot.active_gesture == "wiggle"
    bot.gesture_frame = 5
    bot.handle_keyboard_input()
    assert bot.gesture_frame == 5

    fake_tts = MagicMock()
    fake_tts.speak.return_value = TTSHandle(duration_seconds=1.0)
    mock = build_mock_hardware()
    speaking = module.GemmaBotCompanion(start_server=False, hardware=mock, tts_provider=fake_tts)
    speaking.trigger_speech("hello")
    fake_tts.speak.assert_called_once()
    assert fake_tts.speak.call_args[0][0] == "hello"
    assert mock.audio_out.plays == []
    speaking.interrupt_speech()
    assert speaking.speech_timer == 0


def test_controller_honors_injected_mock_state_without_changing_pose_math():
    module = _controller_module()
    hardware = build_mock_hardware()
    bot = module.GemmaBotCompanion(start_server=False, hardware=hardware)
    assert hardware.camera.enabled_timestep == bot.timestep * 2
    assert hardware.head.velocity_calls[:2] == [("yaw", bot.YAW_SPEED), ("pitch", bot.PITCH_SPEED)]
    assert hardware.display.ops

    bot.cur_yaw = 0.2
    bot.target_yaw = 0.2
    bot.cur_pitch = -0.05
    bot.target_pitch = -0.05
    calls_before = len(hardware.head.velocity_calls)
    bot.update_animation()
    assert len(hardware.head.velocity_calls) == calls_before
    assert hardware.head.commanded_position("yaw") == pytest.approx(bot.cur_yaw)
    assert hardware.head.commanded_position("pitch") == pytest.approx(bot.cur_pitch)

    hardware.touch.set_pressed(True)
    bot.handle_keyboard_input()
    assert bot.active_gesture == "wiggle"

    hardware.audio_in.inject_hardware_mute(True)
    hardware.network.set_online(False)
    hardware.power.set_voltage(4.2)
    hardware.thermal.set_celsius(39.0)
    hardware.clock.set_invalid()
    held_yaw = bot.cur_yaw
    bot.update_animation()
    status = bot.hardware_status
    assert status["mic_hardware_mute"] is True
    assert status["mic_present"] is True
    assert status["online"] is False
    assert status["network_monitored"] is True
    assert status["voltage_dip"] is True
    assert status["power_telemetry"] is True
    assert status["throttle"] == "limited"
    assert status["thermal_sensor"] is True
    assert status["clock_valid"] is False
    assert status["display_color"] is False
    assert status["supports_roll"] is False
    assert hardware.head.last_velocity("yaw") == pytest.approx(bot.YAW_SPEED * 0.4)
    assert hardware.head.last_velocity("pitch") == pytest.approx(bot.PITCH_SPEED * 0.4)
    alpha = 0.22 if bot.active_gesture else 0.12
    assert bot.cur_yaw == pytest.approx(held_yaw + (bot.target_yaw - held_yaw) * alpha)

    hardware.thermal.clear_sensor()
    bot.update_animation()
    assert hardware.head.last_velocity("yaw") == pytest.approx(bot.YAW_SPEED)
    assert bot.hardware_status["throttle"] == "normal"
    assert bot.hardware_status["thermal_sensor"] is False


def test_default_controller_builds_a_webots_hal_and_does_not_write_config():
    module = _controller_module()
    path = default_config_path()
    existed = path.exists()
    bot = module.GemmaBotCompanion(start_server=False)
    assert path.exists() is existed
    assert bot.hardware.head.capabilities().supports_roll is False
    assert bot.hardware.display.capabilities().color is True
    assert (bot.hardware.display.capabilities().width, bot.hardware.display.capabilities().height) == (128, 64)
    assert bot.hardware.network.state().monitored is False
    assert bot.hardware.thermal.state().sensor_present is False
    assert bot.hardware.power.state().usb_connected is True
    assert bot.hardware.power.state().telemetry_present is False
    assert bot.hardware.audio_in.state().device_present is False
    assert bot.hardware.leds.capabilities().present is False
    assert bot.hardware_status["clock_valid"] is True
    assert bot.hardware_status["clock_source"] == "host"
    with pytest.raises(UnsupportedAxisError):
        bot.hardware.head.set_position("roll", 0.2)
    assert isinstance(bot.hardware.storage, FileConfigStore)
