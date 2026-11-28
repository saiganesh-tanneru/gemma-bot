"""Chintu by Sarworks — Main Webots & Desktop Companion Controller.

Startup sequence:
1. Cold startup: sleep face for ~1.0 s while centering servos safely, then run
   the full 5-act wordless wake ritual automatically.
2. Charging sleep: Act 0 sleep face, head bowed -12 deg, display 40%, tiny
   charging corner glyph, servos detached after 20 s.
3. Wake triggers: 'wake Chintu up', head tap, 'Hey Chintu', alarm, unplug from
   charging-sleep, cold power-on. Ignored mid-ritual.
"""

import os
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
from controllers.chintu_controller.server import (
    CHINTU_COMMAND_QUEUE,
    CHINTU_STATUS,
    start_chintu_server,
)
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

        self.machine = ChintuStateMachine(
            audio_player=self.audio_player,
            charging_sensor=self.charging_sensor,
            dock_detector=self.dock_detector,
            servo_rig=self.servo_rig,
            face_target_provider=self._detect_face_pan,
            cold_startup=cold_startup,
        )

        self.server = start_chintu_server() if start_server else None
        self._sync_status(self.machine._build_face_frame(0.0))

    def _detect_face_pan(self) -> Optional[float]:
        """Returns detected user face pan angle in [-50, +50] deg, or None when no face/camera."""
        if self._face_pan_override is not None:
            return self._face_pan_override
        return None

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
            key = self.keyboard.getKey()

        pressed = bool(self.touch and self.touch.getValue() > 0.5)
        self.machine.handle_raw_touch(pressed)

    def _process_commands(self) -> None:
        while not CHINTU_COMMAND_QUEUE.empty():
            cmd = CHINTU_COMMAND_QUEUE.get_nowait()
            if cmd.get("cold_startup"):
                self.machine = ChintuStateMachine(
                    audio_player=self.audio_player,
                    charging_sensor=self.charging_sensor,
                    dock_detector=self.dock_detector,
                    servo_rig=self.servo_rig,
                    face_target_provider=self._detect_face_pan,
                    cold_startup=True,
                )
                continue
            if cmd.get("kicked_off_dock"):
                self.machine.trigger_kicked_off_dock()
                continue
            if cmd.get("shake"):
                self.machine.trigger_shake()
            if "say" in cmd or "talk" in cmd:
                text = str(cmd.get("say") or cmd.get("talk") or "hello")
                self.machine.trigger_talk(text)
            if "is_charging" in cmd:
                val = cmd["is_charging"]
                self.charging_sensor.set_manual_override(None if val is None else bool(val))
            if "is_docked" in cmd:
                val = cmd["is_docked"]
                self.dock_detector.set_manual_override(None if val is None else bool(val))
            if cmd.get("tap"):
                self.machine.trigger_tap()
            if cmd.get("alarm"):
                self.machine.trigger_alarm()
            if "alarm_in_s" in cmd and cmd["alarm_in_s"] is not None:
                self.machine.schedule_alarm_in(float(cmd["alarm_in_s"]))
            if cmd.get("clap"):
                self.machine.handle_loud_sound(pan_deg=float(cmd.get("pan_deg", 20.0)))
            if "face_pan_deg" in cmd:
                pan = float(cmd["face_pan_deg"])
                self._face_pan_override = pan
                self.machine.handle_face_spotted(pan_deg=pan)
            for key in ("phrase", "wake_phrase", "wake_word", "speech", "text"):
                if isinstance(cmd.get(key), str):
                    self.machine.trigger_wake_phrase(cmd[key])

    def _sync_status(self, frame) -> None:
        CHINTU_STATUS.update({
            "state": self.machine.state.value,
            "mood": self.machine.current_mood,
            "pan_deg": round(self.servo_rig.pan_deg, 2),
            "tilt_deg": round(self.servo_rig.tilt_deg, 2),
            "is_charging": self.charging_sensor.is_charging(),
            "is_docked": self.dock_detector.is_docked(),
            "servos_attached": self.servo_rig.attached,
            "energy": round(self.machine.meters.energy, 2),
            "boredom": round(self.machine.meters.boredom, 2),
            "bond": round(self.machine.meters.bond, 2),
            "wake_count": self.machine.wake_count,
            "last_wake_duration_s": (
                round(self.machine.last_wake_duration_s, 3)
                if self.machine.last_wake_duration_s is not None
                else None
            ),
            "yawn_wav_duration_s": round(self.machine.yawn_duration_s, 4),
            "tts_calls_during_wake": self.machine.tts_call_count_during_wake,
            "last_audio_cue": (
                {
                    "seq": len(self.audio_player.events),
                    "cue": self.audio_player.events[-1].cue_name,
                }
                if getattr(self.audio_player, "events", None)
                else None
            ),
            "tag_log": [
                {"timestamp_s": e.timestamp_s, "state": e.state, "tag": e.tag}
                for e in self.machine.tag_log[-32:]
            ],
            "frame": {
                "face_mode": frame.face_mode,
                "mood": frame.mood,
                "left_eye_open": round(frame.left_eye_open, 3),
                "right_eye_open": round(frame.right_eye_open, 3),
                "eye_scale": round(frame.eye_scale, 3),
                "gaze_x": round(frame.gaze_x, 3),
                "gaze_y": round(frame.gaze_y, 3),
                "mouth_open": round(frame.mouth_open, 3),
                "mouth_wobble": round(frame.mouth_wobble, 4),
                "talk_open": round(frame.talk_open, 3),
                "talk_width": round(frame.talk_width, 3),
                "face_bob_x": round(frame.face_bob_x, 3),
                "face_bob_y": round(frame.face_bob_y, 3),
                "smile_amount": round(frame.smile_amount, 3),
                "happy_arcs": frame.happy_arcs,
                "sparkles": round(frame.sparkles, 3),
                "heart_alpha": round(frame.heart_alpha, 3),
                "sweat_alpha": round(frame.sweat_alpha, 3),
                "alert_alpha": round(frame.alert_alpha, 3),
                "bell_alpha": round(frame.bell_alpha, 3),
                "zzz_phase": round(frame.zzz_phase, 3),
                "dizzy_phase": round(frame.dizzy_phase, 3),
                "is_charging": frame.is_charging,
                "brightness": round(frame.brightness, 3),
                "blink_progress": round(frame.blink_progress, 3),
            },
        })

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
        while self.robot.step(self.timestep) != -1:
            self.step_once()


if __name__ == "__main__":
    companion = ChintuCompanion()
    companion.run()
