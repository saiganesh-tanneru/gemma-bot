"""
Gemma-Bot Desktop Companion Controller for Webots.
Coordinates Webots hardware devices, modular OLED face rendering,
phase-based gesture trajectories, keyboard/touch input, and HTTP AI commands.
"""

import logging
import math
import random
import sys
import time
from pathlib import Path
from typing import Optional

from controller import Keyboard, Robot, Supervisor

_CONTROLLER_DIR = str(Path(__file__).resolve().parent)
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
for _path in (_CONTROLLER_DIR, _REPO_ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import config
from desk import (
    DEMO_DOCK_XYZ,
    FACE_HOLD_SECONDS,
    GREETING_TEXT,
    PHASE_BREAK,
    PHASE_FOCUS,
    PHASE_STRETCH,
    STRETCH_TEXT,
    Pomodoro,
    WakePlan,
    boot_flag_path,
    clamp_pitch,
    clamp_yaw,
    crown_action,
    display_mode,
    draw_clock,
    is_docked,
    draw_greeting_caption,
    draw_stretch_caption,
    draw_timer,
    long_press_ticks,
    pomodoro_durations,
    read_dock_translation,
    read_has_booted,
    read_robot_translation,
    voice_can_speak,
    write_has_booted,
)
from faces import (
    EMOJI_MOOD_MAP,
    SCREEN_THEMES,
    THEME_KEYS,
    FaceRenderer,
    WebotsDisplayTarget,
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
    """Main Webots companion robot controller."""

    def __init__(self, start_server: bool = True, tts_provider: Optional[TTSProvider] = None):
        self.robot = Supervisor()
        self.timestep = int(self.robot.getBasicTimeStep())

        # Hardware devices
        self.display = self.robot.getDevice("oled_display")
        self.camera = self.robot.getDevice("camera")
        self.yaw_motor = self.robot.getDevice("head_yaw")
        self.pitch_motor = self.robot.getDevice("head_pitch")
        self.touch = self.robot.getDevice("head_touch")

        if self.display:
            self.display.setOpacity(1.0)
            self.display.setAlpha(1.0)
        if self.camera:
            self.camera.enable(self.timestep * 2)
        if self.touch:
            self.touch.enable(self.timestep)

        self.keyboard = self.robot.getKeyboard()
        self.keyboard.enable(self.timestep)
        self.keymap = build_keymap(Keyboard)

        # Motor setup
        self.yaw_motor.setPosition(0.0)
        self.pitch_motor.setPosition(0.0)
        self.yaw_motor.setVelocity(3.0)
        self.pitch_motor.setVelocity(2.5)

        # Head position targets
        self.cur_yaw = 0.0
        self.cur_pitch = 0.0
        self.target_yaw = 0.0
        self.target_pitch = 0.0

        # OLED renderer
        self.disp_w = 128
        self.disp_h = 64
        target = WebotsDisplayTarget(self.display) if self.display else None
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
        self._touch_hold_ticks = 0
        self._long_press_fired = False

        # Phase 1 desk: wake, dock clock, Pomodoro. Idle until run().
        focus_s, break_s = pomodoro_durations()
        self.pomodoro = Pomodoro(focus_s, break_s)
        self.long_press_ticks = long_press_ticks(self.timestep)
        self.sim_time = 0.0
        self.docked = True
        self._dock_xyz = None
        self._wake: Optional[WakePlan] = None
        self._wake_active = False
        self._greeting_caption = None
        self._show_face_until = 0.0

        # Background HTTP AI command server
        self.server = start_command_server(config.BOT_PORT, config.BOT_HOST) if start_server else None

        self.render_face()

        print("=" * 65)
        print("🤖 Gemma-Bot Desktop Companion Initialized with AI Integration!")
        print(f"🌐 AI Command Server listening on: http://{config.BOT_HOST}:{config.BOT_PORT}/command")
        print("Controls:")
        print("  [1] Neutral       [2] Happy        [3] Surprised")
        print("  [4] Sleepy        [5] Angry        [6] Thinking")
        print("  [SPACE] Pet Head  [Arrow Keys] Manual Pan/Tilt")
        print("  [F] Crown tap (face / pause) or hold ~0.8s (Pomodoro)")
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
        elif self._wake_active:
            pass
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
        self.yaw_motor.setPosition(self.cur_yaw)
        self.pitch_motor.setPosition(self.cur_pitch)

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

    def handle_keyboard_input(self) -> None:
        """Processes manual keyboard and rising-edge touch input."""
        crown_key = False
        key = self.keyboard.getKey()
        while key > 0:
            if (key & 0xFFFF) in (ord("F"), ord("f")):
                crown_key = True
            action = self.keymap.get(key)
            if action is not None:
                apply_key_action(self, action)
                self._show_face_until = self.sim_time + FACE_HOLD_SECONDS
            key = self.keyboard.getKey()

        is_touched = crown_key or bool(self.touch and self.touch.getValue() > 0.5)
        if is_touched and not self._was_touched:
            self._touch_hold_ticks = 1
            self._long_press_fired = False
            self._show_face_until = self.sim_time + FACE_HOLD_SECONDS
            if crown_action(active=self.pomodoro.active, paused=self.pomodoro.paused, event="rising") == "pet":
                self.mood = "HAPPY"
                self.idle_timer = 0
                self.trigger_gesture("wiggle")
                self.trigger_blink()
                print("Head Touched! -> HAPPY")
        elif is_touched:
            self._touch_hold_ticks += 1
        else:
            if self._was_touched and not self._long_press_fired:
                action = crown_action(active=self.pomodoro.active, paused=self.pomodoro.paused, event="release")
                self._apply_crown_action(action)
            self._touch_hold_ticks = 0

        if is_touched and not self._long_press_fired and self._touch_hold_ticks >= self.long_press_ticks:
            self._long_press_fired = True
            action = crown_action(active=self.pomodoro.active, paused=self.pomodoro.paused, event="long")
            self._apply_crown_action(action)
        self._was_touched = is_touched

    def _apply_crown_action(self, action: str) -> None:
        if action == "start":
            self.pomodoro.start()
            self.active_gesture = None
            self.mood = "NEUTRAL"
            self.target_yaw = 0.0
            self.target_pitch = 0.0
            kind = "60s/20s demo" if self.pomodoro.focus_s < 120 else "25/5"
            print(f"Pomodoro started ({kind}). Short tap pauses. Long press cancels.")
        elif action == "cancel":
            self.pomodoro.cancel()
            self.mood = "NEUTRAL"
            self.active_gesture = None
            self.target_yaw = 0.0
            self.target_pitch = 0.0
            print("Pomodoro cancelled.")
        elif action == "pause":
            self.pomodoro.pause()
            print("Pomodoro paused.")
        elif action == "resume":
            self.pomodoro.resume()
            print("Pomodoro resumed.")

    def _begin_wake(self) -> None:
        first = not read_has_booted(boot_flag_path())
        self._wake = WakePlan(first_boot=first)
        self._wake_active = True
        self._greeting_caption = None
        print("Gema wake: first boot." if first else "Gema wake: short wake.")

    def _deliver_greeting(self) -> None:
        if voice_can_speak(self.tts_provider):
            self.trigger_speech(GREETING_TEXT)
            self._greeting_caption = None
        else:
            print(f"🗣️ Gemma-Bot: \"{GREETING_TEXT}\"")
            self._greeting_caption = GREETING_TEXT
        self._show_face_until = self.sim_time + 30.0

    def _finish_wake(self) -> None:
        first = bool(self._wake and self._wake.first_boot)
        if first:
            try:
                write_has_booted(boot_flag_path())
            except OSError as exc:
                print(f"[Wake] Could not store the boot flag: {exc}")
        hold = 4.0 if first else 1.5
        if self.speech_timer > 0:
            hold = max(hold, (self.speech_timer * self.timestep) / 1000.0 + 0.4)
        self._show_face_until = self.sim_time + hold
        self._wake = None
        self._wake_active = False
        self.is_blinking = False
        self.blink_progress = 0.0
        self.target_yaw = 0.0
        self.target_pitch = 0.0

    def _apply_wake(self) -> None:
        if not self._wake_active or self._wake is None:
            return
        step = self._wake.advance()
        if step is None:
            self._finish_wake()
            return
        self.blink_progress = step.blink
        self.is_blinking = step.blink > 0.2
        yaw = clamp_yaw(step.yaw)
        pitch = clamp_pitch(step.pitch)
        self.target_yaw = yaw
        self.target_pitch = pitch
        self.cur_yaw = yaw
        self.cur_pitch = pitch
        self.yaw_motor.setPosition(yaw)
        self.pitch_motor.setPosition(pitch)
        if step.greet:
            self._deliver_greeting()
        if step.done:
            self._finish_wake()

    def _refresh_docked(self) -> None:
        if self._dock_xyz is None:
            self._dock_xyz = read_dock_translation(self.robot) or DEMO_DOCK_XYZ
        pos = read_robot_translation(self.robot)
        if pos is None:
            return
        self.docked = is_docked(pos, self._dock_xyz)

    def _on_pomodoro_phase(self, phase: Optional[str]) -> None:
        if phase == PHASE_STRETCH:
            self.mood = "HAPPY"
            self.trigger_gesture("wiggle")
            print(STRETCH_TEXT)
        elif phase in (PHASE_BREAK, PHASE_FOCUS):
            self.mood = "NEUTRAL"
            self.active_gesture = None
            self.target_yaw = 0.0
            self.target_pitch = 0.0

    def _render_screen(self) -> None:
        mode = display_mode(
            docked=self.docked,
            waking=self._wake_active,
            phase=self.pomodoro.phase,
            face_hold=self.sim_time < self._show_face_until,
        )
        if mode == "clock":
            self._greeting_caption = None
            draw_clock(self.display, time.localtime())
            return
        if mode == "pomodoro":
            self._greeting_caption = None
            draw_timer(self.display, self.pomodoro)
            return
        if mode == "stretch":
            self.mood = "HAPPY"
            self.render_face()
            draw_stretch_caption(self.display)
            return
        self.render_face()
        if self._greeting_caption:
            draw_greeting_caption(self.display, self._greeting_caption)
            if self.sim_time >= self._show_face_until:
                self._greeting_caption = None

    def run(self) -> None:
        """Main simulation execution loop."""
        self._begin_wake()
        while self.robot.step(self.timestep) != -1:
            self.sim_time += self.timestep / 1000.0
            self._refresh_docked()
            self.handle_keyboard_input()
            self.process_ai_commands()
            self._on_pomodoro_phase(self.pomodoro.tick(self.timestep / 1000.0))
            self.update_animation()
            self._apply_wake()
            self._render_screen()


if __name__ == "__main__":
    companion = GemmaBotCompanion()
    companion.run()
