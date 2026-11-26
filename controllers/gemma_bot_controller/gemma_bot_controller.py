"""
Gemma-Bot Desktop Companion Controller for Webots.
Coordinates the hardware abstraction layer, modular OLED face rendering,
phase-based gesture trajectories, keyboard/touch input, and HTTP AI commands.
"""

import logging
import math
import random
import sys
from pathlib import Path
from typing import Optional

from controller import Keyboard, Robot, Supervisor

_CONTROLLER_DIR = str(Path(__file__).resolve().parent)
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
for _path in (_CONTROLLER_DIR, _REPO_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import config
from hal import Hardware, build_webots_hardware
from hal.face_target import FaceDrawTarget
from hal.types import AXIS_PITCH, AXIS_YAW
from faces import (
    EMOJI_MOOD_MAP,
    SCREEN_THEMES,
    THEME_KEYS,
    FaceRenderer,
    resolve_mood,
)
from gestures import GESTURE_DEFAULT_MOOD, GESTURES, resolve_gesture
from input_map import KEYMAP, apply_key_action, build_keymap
from server import AICommandHandler, start_command_server
from state import COMMAND_QUEUE, ROBOT_STATE
from tts import TTSHandle, TTSProvider, create_tts_provider

logger = logging.getLogger("gemma_bot_controller")

__all__ = [
    "COMMAND_QUEUE",
    "ROBOT_STATE",
    "SCREEN_THEMES",
    "THEME_KEYS",
    "EMOJI_MOOD_MAP",
    "GESTURE_DEFAULT_MOOD",
    "GESTURES",
    "KEYMAP",
    "resolve_mood",
    "resolve_gesture",
    "AICommandHandler",
    "start_command_server",
    "GemmaBotCompanion",
]


class GemmaBotCompanion:
    """Main Webots companion robot controller.

    Servos, the face panel, touch, the camera enable, the speaker, and the
    other device readings go through ``self.hardware``. The Webots keyboard
    stays a sim input. Raw device attributes remain so existing tests can
    poke ``touch.value`` and ``display.ops`` on the same objects the Webots
    drivers wrap.
    """

    YAW_SPEED = 3.0
    PITCH_SPEED = 2.5
    # Applied only when a thermal sensor is present. The sim has none.
    THROTTLE_SPEED_SCALE = {
        "normal": 1.0,
        "reduced": 0.7,
        "limited": 0.4,
    }

    def __init__(
        self,
        start_server: bool = True,
        tts_provider: Optional[TTSProvider] = None,
        *,
        hardware: Optional[Hardware] = None,
    ):
        self.robot = Supervisor()
        self.timestep = int(self.robot.getBasicTimeStep())

        # Raw Webots devices. Motion, drawing, and touch reads go through HAL.
        self.display = self.robot.getDevice("oled_display")
        self.camera = self.robot.getDevice("camera")
        self.yaw_motor = self.robot.getDevice("head_yaw")
        self.pitch_motor = self.robot.getDevice("head_pitch")
        self.touch = self.robot.getDevice("head_touch")

        if hardware is None:
            hardware = build_webots_hardware(
                self.robot,
                timestep_ms=self.timestep,
                display=self.display,
                camera=self.camera,
                yaw_motor=self.yaw_motor,
                pitch_motor=self.pitch_motor,
                touch=self.touch,
            )
        self.hardware = hardware

        self.hardware.display.set_opacity(1.0)
        self.hardware.display.set_alpha(1.0)
        self.hardware.camera.enable(self.timestep * 2)
        self.hardware.touch.enable(self.timestep)

        self.keyboard = self.robot.getKeyboard()
        self.keyboard.enable(self.timestep)
        self.keymap = build_keymap(Keyboard)

        # Motor setup. Speeds drop only when thermal.state().sensor_present.
        self._speed_scale = None
        self._apply_servo_speeds()
        self.hardware.head.set_position(AXIS_YAW, 0.0)
        self.hardware.head.set_position(AXIS_PITCH, 0.0)

        # Head position targets
        self.cur_yaw = 0.0
        self.cur_pitch = 0.0
        self.target_yaw = 0.0
        self.target_pitch = 0.0

        # OLED renderer
        self.disp_w = 128
        self.disp_h = 64
        target = FaceDrawTarget(self.hardware.display)
        self.renderer = FaceRenderer(target, theme="CYAN", disp_w=self.disp_w, disp_h=self.disp_h)
        self._sync_theme_fields()

        # Dynamic eye state
        self.gaze_x = 0.0
        self.gaze_y = 0.0
        self.blink_progress = 0.0
        self.is_blinking = False
        self.blink_speed = 0.18

        # Behavior / mood state
        self.mood = "NEUTRAL"
        self.idle_timer = 0
        self.next_idle_action = 100
        self.next_blink = 140

        # Speech state & TTS provider
        self.speech_text = ""
        self.speech_timer = 0
        self.tts_provider = tts_provider or create_tts_provider()
        self.speech_handle: Optional[TTSHandle] = None

        # Gesture engine state
        self.active_gesture = None
        self.gesture_frame = 0
        self.gesture_total_frames = 0
        self._was_touched = False

        # Background HTTP AI command server
        self.server = start_command_server(config.BOT_PORT, config.BOT_HOST) if start_server else None

        self.hardware_status = {}
        self._refresh_hardware_status()
        self.render_face()

    def _servo_speed_scale(self) -> float:
        thermal = self.hardware.thermal.state()
        if not thermal.sensor_present:
            return 1.0
        return self.THROTTLE_SPEED_SCALE.get(thermal.throttle, 1.0)

    def _apply_servo_speeds(self) -> None:
        scale = self._servo_speed_scale()
        if scale == self._speed_scale:
            return
        self._speed_scale = scale
        self.hardware.head.set_velocity(AXIS_YAW, self.YAW_SPEED * scale)
        self.hardware.head.set_velocity(AXIS_PITCH, self.PITCH_SPEED * scale)

    def _refresh_hardware_status(self) -> None:
        self.hardware_status = self.hardware.snapshot()

        print("=" * 65)
        print("🤖 Gemma-Bot Desktop Companion Initialized with AI Integration!")
        print(f"🌐 AI Command Server listening on: http://{config.BOT_HOST}:{config.BOT_PORT}/command")
        print("Controls:")
        print("  [1] Neutral       [2] Happy        [3] Surprised")
        print("  [4] Sleepy        [5] Angry        [6] Thinking")
        print("  [SPACE] Pet Head  [Arrow Keys] Manual Pan/Tilt")
        print("=" * 65)

    def _sync_theme_fields(self) -> None:
        self.current_theme = self.renderer.current_theme
        self.bg_color = self.renderer.bg_color
        self.eye_color = self.renderer.eye_color
        self.eye_dim = self.renderer.eye_dim
        self.mouth_color = self.renderer.mouth_color
        self.sunglass_frame = self.renderer.sunglass_frame

    def render_face(self) -> None:
        """Renders the complete OLED facial expression and eye gaze."""
        self.renderer.render(
            mood=self.mood,
            gaze_x=self.gaze_x,
            gaze_y=self.gaze_y,
            blink_progress=self.blink_progress,
            idle_timer=self.idle_timer,
            speech_timer=self.speech_timer,
        )

    def trigger_speech(self, text: str, play_audio: bool = True) -> None:
        """Speaks text out loud via TTSProvider and activates animated lip-sync."""
        if not text:
            return
        self.speech_text = str(text).strip()
        if self.speech_handle is not None:
            self.speech_handle.stop()
            self.speech_handle = None
        # Clips use the speaker HAL. TTS stays the synthesizer and is stopped
        # via speech_handle so `say` / WAV playback is unchanged.
        self.hardware.audio_out.stop()

        handle = self.tts_provider.speak(self.speech_text, play_audio=play_audio)
        self.speech_handle = handle

        if handle.duration_seconds is not None and handle.duration_seconds > 0:
            duration_seconds = handle.duration_seconds
        else:
            words = len(self.speech_text.split())
            duration_seconds = max(1.6, words * 0.38 + 0.6)
        self.speech_timer = max(1, int((duration_seconds * 1000) / max(1, self.timestep)))
        print(f"🗣️ Gemma-Bot: \"{self.speech_text}\"")

    def interrupt_speech(self) -> None:
        """Immediately silences speech playback and halts lip-sync."""
        self.hardware.audio_out.stop()
        if self.speech_handle is not None:
            self.speech_handle.stop()
            self.speech_handle = None
        self.speech_timer = 0
        self.speech_text = ""
        self.trigger_blink()

    def trigger_blink(self) -> None:
        """Initiates a blink sequence."""
        if not self.is_blinking:
            self.is_blinking = True
            self.blink_progress = 0.0

    def set_screen_theme(self, theme: str) -> None:
        """Sets the active OLED screen color theme."""
        if not theme:
            return
        if self.renderer.apply_theme(theme):
            self._sync_theme_fields()
            cfg = SCREEN_THEMES[self.current_theme]
            print(f"[Screen Theme] Switched to {cfg['name']} (Color: #{self.eye_color:06X})")
            self.render_face()

    def cycle_screen_theme(self) -> None:
        """Cycles through available screen color themes."""
        try:
            curr_idx = THEME_KEYS.index(self.current_theme)
        except ValueError:
            curr_idx = 0
        next_theme = THEME_KEYS[(curr_idx + 1) % len(THEME_KEYS)]
        self.set_screen_theme(next_theme)

    def trigger_gesture(self, gesture_name: str) -> bool:
        """Triggers a named physical head gesture from the phase-based GESTURES registry."""
        canonical = resolve_gesture(gesture_name)
        if canonical is None:
            logger.warning("Unknown gesture requested: %r", gesture_name)
            print(f"[Gesture Warning] Unknown gesture: {gesture_name!r}")
            return False

        self.active_gesture = canonical
        self.gesture_frame = 0
        self.gesture_total_frames = GESTURES[canonical].frames
        return True

    def process_ai_commands(self) -> None:
        """Drains the AI command queue and executes actions."""
        gaze_presets = {
            "left": (-0.9, None, 0.4, None),
            "right": (0.9, None, -0.4, None),
            "up": (None, -0.8, None, -0.2),
            "down": (None, 0.8, None, 0.2),
            "center": (0.0, 0.0, 0.0, 0.0),
            "forward": (0.0, 0.0, 0.0, 0.0),
        }

        while not COMMAND_QUEUE.empty():
            try:
                cmd = COMMAND_QUEUE.get_nowait()
                if "state" in cmd:
                    state = str(cmd["state"]).upper()
                    if state == "LISTENING":
                        self.gaze_x = 0.0
                        self.gaze_y = 0.0
                        self.target_yaw = 0.0
                        self.target_pitch = -0.05
                    elif state == "THINKING":
                        self.mood = "THINKING"
                        self.gaze_x = 0.5
                        self.gaze_y = -0.6
                        self.target_yaw = 0.2
                        self.target_pitch = -0.15
                    elif state == "SPEAKING":
                        self.mood = "HAPPY"
                        if not self.active_gesture:
                            self.trigger_gesture("nod")
                    elif state in ("INTERRUPTED", "CANCELLED"):
                        self.interrupt_speech()
                        self.mood = "SURPRISED"

                if cmd.get("interrupt") or cmd.get("flush"):
                    self.interrupt_speech()

                if "mood" in cmd:
                    self.mood = resolve_mood(cmd["mood"])
                    self.trigger_blink()

                if "gaze" in cmd:
                    preset = gaze_presets.get(str(cmd["gaze"]).lower())
                    if preset:
                        gx, gy, ty, tp = preset
                        if gx is not None:
                            self.gaze_x = gx
                        if gy is not None:
                            self.gaze_y = gy
                        if ty is not None:
                            self.target_yaw = ty
                        if tp is not None:
                            self.target_pitch = tp

                if "look_at" in cmd:
                    coords = cmd["look_at"]
                    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                        self.target_yaw = max(-1.2, min(1.2, float(coords[0])))
                        self.target_pitch = max(-0.4, min(0.4, float(coords[1])))
                        self.gaze_x = max(-1.0, min(1.0, self.target_yaw * 1.5))
                        self.gaze_y = max(-1.0, min(1.0, self.target_pitch * 2.0))

                if "gesture" in cmd and cmd["gesture"]:
                    g_name = str(cmd["gesture"]).lower().strip()
                    self.trigger_gesture(g_name)
                    if "mood" not in cmd and g_name in GESTURE_DEFAULT_MOOD:
                        self.mood = GESTURE_DEFAULT_MOOD[g_name]
                        self.trigger_blink()

                if "speech" in cmd and cmd["speech"]:
                    text_str = str(cmd["speech"])
                    for char, m in EMOJI_MOOD_MAP.items():
                        if char in text_str and "mood" not in cmd:
                            self.mood = m
                            break
                    play_audio = bool(cmd.get("audio", True))
                    self.trigger_speech(text_str, play_audio=play_audio)

                if "screen_color" in cmd or "screen" in cmd or "theme" in cmd or "color" in cmd:
                    col_val = cmd.get("screen_color") or cmd.get("screen") or cmd.get("theme") or cmd.get("color")
                    self.set_screen_theme(col_val)

                print(f"[AI Command Executed] Mood={self.mood}, Gesture={cmd.get('gesture')}, Theme={self.current_theme}")
            except Exception as e:
                print(f"[AI Command Error]: {e}")

    def update_animation(self) -> None:
        """Updates head servo positions, gestures, blinks, and timers."""
        self._apply_servo_speeds()
        self.idle_timer += 1

        # 1. Blink cycle
        if self.is_blinking:
            self.blink_progress += self.blink_speed
            if self.blink_progress >= 1.0:
                self.blink_progress = 1.0
                self.blink_speed = -0.22
            elif self.blink_progress <= 0.0:
                self.blink_progress = 0.0
                self.is_blinking = False
                self.blink_speed = 0.20

        self.next_blink -= 1
        if self.next_blink <= 0:
            self.trigger_blink()
            self.next_blink = random.randint(120, 260)

        if self.speech_timer > 0:
            self.speech_timer -= 1
            if not self.active_gesture:
                self.target_pitch = math.sin(self.speech_timer * 0.22) * 0.08

        # 2. Gesture execution (phase-based trajectory in [0, 1])
        if self.active_gesture:
            self.gesture_frame += 1
            total = self.gesture_total_frames
            p = self.gesture_frame / total
            gesture_spec = GESTURES.get(self.active_gesture)
            if gesture_spec is not None:
                pose = gesture_spec.trajectory(p)
                if pose.yaw is not None:
                    self.target_yaw = pose.yaw
                if pose.pitch is not None:
                    self.target_pitch = pose.pitch
                if pose.gaze_x is not None:
                    self.gaze_x = pose.gaze_x
                if pose.gaze_y is not None:
                    self.gaze_y = pose.gaze_y
                if pose.blink_progress is not None:
                    self.blink_progress = pose.blink_progress

            if self.gesture_frame >= total:
                self.active_gesture = None
                self.target_yaw = 0.0
                self.target_pitch = 0.0
                self.gaze_x = 0.0
                self.gaze_y = 0.0

        # 3. Autonomous Idle Life (when no gesture is active)
        elif self.mood == "NEUTRAL":
            self.next_idle_action -= 1
            if self.next_idle_action <= 0:
                choice = random.random()
                if choice < 0.35:
                    self.gaze_x = 0.0
                    self.gaze_y = 0.0
                    self.target_yaw = 0.0
                    self.target_pitch = 0.0
                elif choice < 0.65:
                    self.gaze_x = -0.75
                    self.gaze_y = random.uniform(-0.3, 0.3)
                    self.target_yaw = random.uniform(0.2, 0.5)
                    self.target_pitch = self.gaze_y * 0.2
                else:
                    self.gaze_x = 0.75
                    self.gaze_y = random.uniform(-0.3, 0.3)
                    self.target_yaw = random.uniform(-0.5, -0.2)
                    self.target_pitch = self.gaze_y * 0.2
                self.next_idle_action = random.randint(100, 240)
        elif self.mood == "HAPPY":
            self.target_yaw = math.sin(self.idle_timer * 0.2) * 0.15
            self.target_pitch = -0.12
        elif self.mood == "SLEEPY":
            self.target_yaw = 0.0
            self.target_pitch = 0.32
            self.gaze_x = 0.0
            self.gaze_y = 0.5

        # 4. Smooth servo interpolation
        alpha = 0.22 if self.active_gesture else 0.12
        self.cur_yaw += (self.target_yaw - self.cur_yaw) * alpha
        self.cur_pitch += (self.target_pitch - self.cur_pitch) * alpha
        self.hardware.head.set_position(AXIS_YAW, self.cur_yaw)
        self.hardware.head.set_position(AXIS_PITCH, self.cur_pitch)

        # Update shared state for HTTP status reporting
        ROBOT_STATE["mood"] = self.mood
        ROBOT_STATE["gesture"] = self.active_gesture
        ROBOT_STATE["screen_theme"] = self.current_theme
        ROBOT_STATE["screen_color"] = f"#{self.eye_color:06X}"
        ROBOT_STATE["yaw"] = round(self.cur_yaw, 3)
        ROBOT_STATE["pitch"] = round(self.cur_pitch, 3)
        ROBOT_STATE["gaze"] = [round(self.gaze_x, 2), round(self.gaze_y, 2)]
        ROBOT_STATE["is_speaking"] = self.speech_timer > 0
        ROBOT_STATE["speech_text"] = self.speech_text if self.speech_timer > 0 else ""
        self._refresh_hardware_status()

    def handle_keyboard_input(self) -> None:
        """Processes manual keyboard and rising-edge touch input."""
        key = self.keyboard.getKey()
        while key > 0:
            action = self.keymap.get(key)
            if action is not None:
                apply_key_action(self, action)
            key = self.keyboard.getKey()

        is_touched = self.hardware.touch.is_pressed()
        if is_touched and not self._was_touched:
            self.mood = "HAPPY"
            self.idle_timer = 0
            self.trigger_gesture("wiggle")
            self.trigger_blink()
            print("Head Touched! -> HAPPY")
        self._was_touched = is_touched
        self._refresh_hardware_status()

    def run(self) -> None:
        """Main simulation execution loop."""
        while self.robot.step(self.timestep) != -1:
            self.handle_keyboard_input()
            self.process_ai_commands()
            self.update_animation()
            self.render_face()


if __name__ == "__main__":
    companion = GemmaBotCompanion()
    companion.run()
