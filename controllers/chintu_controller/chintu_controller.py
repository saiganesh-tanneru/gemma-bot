"""Chintu by Sarworks — Main Webots & Desktop Companion Controller.

Startup sequence:
1. Cold startup: sleep face for ~1.0 s while centering servos safely, then run
   the full 5-act wordless wake ritual automatically.
2. Charging sleep: Act 0 sleep face, head bowed -12 deg, display 40%, tiny
   charging corner glyph, servos detached after 20 s.
3. Wake triggers: 'wake Chintu up', head tap, 'Hey Chintu', alarm, unplug from
   charging-sleep, cold power-on. Ignored mid-ritual.
"""

from pathlib import Path
import sys
from typing import Optional

_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from controller import Keyboard, Supervisor  # type: ignore

from controllers.chintu_controller.audio_cues import AudioCuePlayer, create_audio_cue_player
from controllers.chintu_controller.face_renderer import FaceRenderer, WebotsDisplayTarget
from controllers.chintu_controller.hardware import ChargingSensor, DockDetector, ServoRig
from controllers.chintu_controller.runtime_helpers import (
    process_chintu_command_queue,
    sync_chintu_status,
)
from controllers.chintu_controller.server import start_chintu_server
from controllers.chintu_controller.wake_engine import ChintuStateMachine


class ChintuCompanion:
    """Main Webots controller for Chintu by Sarworks."""

    def __init__(
        self,
        start_server: bool = True,
        audio_player: Optional[AudioCuePlayer] = None,
        cold_startup: bool = True,
    ) -> None:
        self.robot = Supervisor()
        self.timestep = int(self.robot.getBasicTimeStep())

        self.display = self.robot.getDevice("oled_display")
        self.camera = self.robot.getDevice("camera")
        self.yaw_motor = self.robot.getDevice("head_yaw")
        self.pitch_motor = self.robot.getDevice("head_pitch")
        self.touch = self.robot.getDevice("head_touch")

        if self.camera:
            self.camera.enable(self.timestep * 2)
        if self.touch:
            self.touch.enable(self.timestep)

        self.keyboard = self.robot.getKeyboard()
        self.keyboard.enable(self.timestep)

        if self.display and hasattr(self.display, "getWidth") and hasattr(self.display, "getHeight"):
            w = int(self.display.getWidth())
            h = int(self.display.getHeight())
            self.disp_w = w if w > 0 else 410
            self.disp_h = h if h > 0 else 502
        else:
            self.disp_w = 410
            self.disp_h = 502

        target = WebotsDisplayTarget(self.display) if self.display else None
        self.renderer = FaceRenderer(target=target, disp_w=self.disp_w, disp_h=self.disp_h)

        self.charging_sensor = ChargingSensor()
        self.dock_detector = DockDetector()
        self.servo_rig = ServoRig(
            dock_detector=self.dock_detector,
            yaw_motor=self.yaw_motor,
            pitch_motor=self.pitch_motor,
        )
        self.audio_player = audio_player or create_audio_cue_player()
        self._face_pan_override: Optional[float] = None

        self.machine = self._make_machine(cold_startup=cold_startup)
        self.server = start_chintu_server() if start_server else None
        self._sync_status(self.machine._build_face_frame(0.0))

    def _make_machine(self, cold_startup: bool = True) -> ChintuStateMachine:
        return ChintuStateMachine(
            audio_player=self.audio_player,
            charging_sensor=self.charging_sensor,
            dock_detector=self.dock_detector,
            servo_rig=self.servo_rig,
            face_target_provider=self._detect_face_pan,
            cold_startup=cold_startup,
        )

    def _detect_face_pan(self) -> Optional[float]:
        """Returns detected user face pan angle in [-50, +50] deg, or None when no face/camera."""
        if self._face_pan_override is not None:
            return self._face_pan_override
        return None

    def _set_face_pan_override(self, pan: float) -> None:
        self._face_pan_override = pan

    def _handle_inputs(self) -> None:
        key = self.keyboard.getKey()
        while key > 0:
            if key == ord(" "):
                self.machine.trigger_tap()
            elif key in (ord("w"), ord("W")):
                self.machine.trigger_wake_phrase("wake Chintu up")
            elif key in (ord("c"), ord("C")):
                self.charging_sensor.set_manual_override(not self.charging_sensor.is_charging())
            elif key in (ord("d"), ord("D")):
                self.dock_detector.set_manual_override(not self.dock_detector.is_docked())
            elif key in (ord("s"), ord("S")):
                self.machine.trigger_wake_phrase("Chintu, go to sleep")
            elif key in (ord("k"), ord("K")):
                self.machine.trigger_kicked_off_dock()
            elif key in (ord("x"), ord("X")):
                self.machine.trigger_shake()
            elif key in (ord("a"), ord("A")):
                self.machine.trigger_alarm()
            elif key in (ord("t"), ord("T")):
                self.machine.trigger_talk("hello Chintu!")
            elif key in (ord("l"), ord("L")):
                self.machine.handle_loud_sound(pan_deg=20.0)
            elif key in (ord("f"), ord("F")):
                self._face_pan_override = 18.0
                self.machine.handle_face_spotted(pan_deg=18.0)
            key = self.keyboard.getKey()

        pressed = bool(self.touch and self.touch.getValue() > 0.5)
        self.machine.handle_raw_touch(pressed)

    def _process_commands(self) -> None:
        self.machine = process_chintu_command_queue(
            machine=self.machine,
            charging_sensor=self.charging_sensor,
            dock_detector=self.dock_detector,
            on_cold_startup=lambda: self._make_machine(cold_startup=True),
            on_face_pan_override=self._set_face_pan_override,
        )

    def _sync_status(self, frame) -> None:
        sync_chintu_status(
            machine=self.machine,
            servo_rig=self.servo_rig,
            charging_sensor=self.charging_sensor,
            dock_detector=self.dock_detector,
            audio_player=self.audio_player,
            frame=frame,
        )

    def step_once(self) -> None:
        self._handle_inputs()
        self._process_commands()
        frame = self.machine.step(self.timestep / 1000.0)
        self.renderer.render(frame)
        self._sync_status(frame)

    def run(self) -> None:
        print("Chintu by Sarworks — Wake Ritual Startup Active")
        if self.server is not None:
            addr = self.server.server_address
            print(f"Chintu Face Playground: http://{addr[0]}:{addr[1]}/playground")
        print("Keys: [SPACE]=Tap [W]=Wake [C]=Charging [D]=Docked [S]=Sleep [K]=KickOff [X]=Shake [A]=Alarm [T]=Talk [L]=Clap [F]=Face")
        try:
            while self.robot.step(self.timestep) != -1:
                self.step_once()
        finally:
            self.audio_player.close()
            if self.server is not None:
                self.server.shutdown()
                self.server.server_close()


if __name__ == "__main__":
    companion = ChintuCompanion()
    companion.run()
