"""
Gemma-Bot Desktop Companion Controller for Webots
Features:
- Real-time animated OLED eyes rendered on a 128x64 Webots Display device.
- Dual-axis servo head motion (Yaw / Pan and Pitch / Tilt).
- Expressive moods: Neutral, Happy, Surprised, Sleepy, Angry, Thinking, Love.
- Gesture engine: Nod, Shake Head, Wiggle, Curious Tilt, Perk Up, Droop.
- Embedded AI Command Server (HTTP REST on 127.0.0.1:8765):
  Allows external AI / LLMs (Gemini, scripts, chat interfaces) to control
  the robot's moods, gaze, gestures, and speech via simple JSON commands.
- Interactive keyboard controls & autonomous companion behaviors.
"""

import math
import random
import queue
import threading
import json
import http.server
from controller import Robot, Keyboard

# Thread-safe queue for incoming AI commands
COMMAND_QUEUE = queue.Queue()
ROBOT_STATE = {
    "mood": "NEUTRAL",
    "yaw": 0.0,
    "pitch": 0.0,
    "gaze": [0.0, 0.0],
    "is_speaking": False,
    "speech_text": ""
}

class AICommandHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler to receive external AI commands and report robot status."""
    def log_message(self, format, *args):
        pass  # Suppress default HTTP logging to keep console clean

    def do_GET(self):
        if self.path == "/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(ROBOT_STATE).encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Gemma-Bot AI Command Server Active\n")

    def do_POST(self):
        if self.path == "/command":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                cmd = json.loads(body)
                COMMAND_QUEUE.put(cmd)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "received", "command": cmd}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def start_command_server(port=8765):
    """Starts the background AI command server."""
    try:
        server = http.server.HTTPServer(("127.0.0.1", port), AICommandHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        return server
    except Exception as e:
        print(f"[AI Server] Warning: Could not bind port {port}: {e}")
        return None

class GemmaBotCompanion:
    def __init__(self):
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())
        
        # Hardware devices
        self.display = self.robot.getDevice("oled_display")
        self.camera = self.robot.getDevice("camera")
        self.yaw_motor = self.robot.getDevice("head_yaw")
        self.pitch_motor = self.robot.getDevice("head_pitch")
        self.touch = self.robot.getDevice("head_touch")
        
        # Ensure display is fully opaque for high-contrast graphics
        if self.display:
            self.display.setOpacity(1.0)
            self.display.setAlpha(1.0)
            
        if self.camera:
            self.camera.enable(self.timestep * 2)
        if self.touch:
            self.touch.enable(self.timestep)
            
        self.keyboard = self.robot.getKeyboard()
        self.keyboard.enable(self.timestep)
        
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
        
        # Display resolution & high-contrast colors
        self.disp_w = 128
        self.disp_h = 64
        self.bg_color = 0x000000      # True OLED black
        self.eye_color = 0x00E5FF     # Electric Cyan / OLED Blue
        self.eye_dim = 0x008899       # Secondary glow / dimming
        self.mouth_color = 0x00BBDD
        self.accent_pink = 0xFF4488   # For Love mood / hearts
        
        # Eye baseline geometry
        self.left_cx = 38
        self.right_cx = 90
        self.base_cy = 32
        self.eye_w = 28
        self.eye_h = 34
        
        # Dynamic eye state
        self.gaze_x = 0.0   # -1.0 (left) to +1.0 (right)
        self.gaze_y = 0.0   # -1.0 (up) to +1.0 (down)
        self.blink_progress = 0.0
        self.is_blinking = False
        self.blink_speed = 0.18
        
        # Behavior / mood state
        self.mood = "NEUTRAL"
        self.idle_timer = 0
        self.next_idle_action = 100
        self.next_blink = 140
        
        # Speech state
        self.speech_text = ""
        self.speech_timer = 0
        
        # Gesture engine state
        self.active_gesture = None
        self.gesture_frame = 0
        self.gesture_total_frames = 0
        
        # Start background HTTP AI command server
        self.server = start_command_server(8765)
        
        # Render initial frame immediately
        self.render_face()
        
        print("=" * 65)
        print("🤖 Gemma-Bot Desktop Companion Initialized with AI Integration!")
        print("🌐 AI Command Server listening on: http://127.0.0.1:8765/command")
        print("Controls:")
        print("  [1] Neutral       [2] Happy        [3] Surprised")
        print("  [4] Sleepy        [5] Angry        [6] Thinking")
        print("  [SPACE] Pet Head  [Arrow Keys] Manual Pan/Tilt")
        print("=" * 65)

    def draw_filled_box(self, x, y, w, h, color):
        """Helper to draw a clamped filled box on the display."""
        x0 = max(0, min(self.disp_w - 1, int(x)))
        y0 = max(0, min(self.disp_h - 1, int(y)))
        x1 = max(0, min(self.disp_w, int(x + w)))
        y1 = max(0, min(self.disp_h, int(y + h)))
        if x1 > x0 and y1 > y0:
            self.display.setColor(color)
            self.display.fillRectangle(x0, y0, x1 - x0, y1 - y0)

    def draw_rounded_eye(self, cx, cy, w, h, corner_r=5, color=None):
        """Draws a clean rounded rectangle OLED eye."""
        col = color if color is not None else self.eye_color
        x = cx - w / 2
        y = cy - h / 2
        self.draw_filled_box(x + corner_r, y, w - 2 * corner_r, h, col)
        self.draw_filled_box(x, y + corner_r, corner_r, h - 2 * corner_r, col)
        self.draw_filled_box(x + w - corner_r, y + corner_r, corner_r, h - 2 * corner_r, col)

    def draw_happy_eye(self, cx, cy, w):
        """Draws a crescent / squinting happy eye curve (^_^)."""
        x = cx - w / 2
        self.draw_filled_box(x, cy - 2, w, 7, self.eye_color)
        self.draw_filled_box(x + 2, cy - 5, w - 4, 4, self.eye_color)
        self.draw_filled_box(x + 5, cy - 7, w - 10, 3, self.eye_color)
        self.draw_filled_box(x + 3, cy, w - 6, 8, self.bg_color)

    def draw_sleepy_eye(self, cx, cy, w):
        """Draws a calm resting sleepy eye line."""
        x = cx - w / 2
        self.draw_filled_box(x, cy + 2, w, 5, self.eye_color)
        self.draw_filled_box(x + 2, cy + 5, w - 4, 3, self.eye_color)

    def draw_angry_eye(self, cx, cy, w, h, is_left=True):
        """Draws slanted, determined brows."""
        x = cx - w / 2
        y = cy - h / 2
        self.draw_filled_box(x, y, w, h, self.eye_color)
        if is_left:
            self.draw_filled_box(x + w/2, y, w/2, h * 0.45, self.bg_color)
        else:
            self.draw_filled_box(x, y, w/2, h * 0.45, self.bg_color)

    def draw_heart(self, cx, cy):
        """Draws a cute heart for LOVE mood."""
        self.draw_filled_box(cx - 7, cy - 4, 6, 6, self.accent_pink)
        self.draw_filled_box(cx + 1, cy - 4, 6, 6, self.accent_pink)
        self.draw_filled_box(cx - 9, cy, 18, 5, self.accent_pink)
        self.draw_filled_box(cx - 7, cy + 5, 14, 4, self.accent_pink)
        self.draw_filled_box(cx - 4, cy + 9, 8, 4, self.accent_pink)
        self.draw_filled_box(cx - 1, cy + 13, 2, 2, self.accent_pink)

    def render_face(self):
        """Renders the complete OLED facial expression and eye gaze."""
        if not self.display:
            return
            
        # 1. Clear background
        self.display.setOpacity(1.0)
        self.display.setColor(self.bg_color)
        self.display.fillRectangle(0, 0, self.disp_w, self.disp_h)

        # 2. Compute gaze displacement
        dx = self.gaze_x * 8.0
        dy = self.gaze_y * 6.0
        
        lcx = self.left_cx + dx
        rcx = self.right_cx + dx
        cy = self.base_cy + dy

        # 3. Handle blinking
        effective_h = self.eye_h * (1.0 - self.blink_progress)
        if effective_h < 3:
            effective_h = 3

        # 4. Render eyes according to mood
        if self.blink_progress > 0.85:
            self.draw_filled_box(lcx - self.eye_w/2, cy, self.eye_w, 4, self.eye_color)
            self.draw_filled_box(rcx - self.eye_w/2, cy, self.eye_w, 4, self.eye_color)
        elif self.mood == "HAPPY":
            self.draw_happy_eye(lcx, cy, self.eye_w)
            self.draw_happy_eye(rcx, cy, self.eye_w)
            self.draw_filled_box(self.disp_w/2 - 6, cy + 16, 12, 3, self.mouth_color)
            self.draw_filled_box(self.disp_w/2 - 3, cy + 19, 6, 2, self.mouth_color)
        elif self.mood == "LOVE":
            self.draw_heart(lcx, cy)
            self.draw_heart(rcx, cy)
            self.draw_filled_box(self.disp_w/2 - 5, cy + 16, 10, 3, self.accent_pink)
        elif self.mood == "THINKING":
            # Looking up-right with thinking bubble
            self.draw_rounded_eye(lcx + 4, cy - 6, self.eye_w - 2, effective_h - 2, corner_r=5)
            self.draw_rounded_eye(rcx + 4, cy - 6, self.eye_w - 2, effective_h - 2, corner_r=5)
            # Animated thinking dots
            phase = (self.idle_timer // 15) % 3
            for i in range(3):
                col = self.eye_color if i == phase else self.eye_dim
                self.draw_filled_box(96 + i * 8, 10, 4, 4, col)
        elif self.mood == "SLEEPY":
            self.draw_sleepy_eye(lcx, cy + 4, self.eye_w)
            self.draw_sleepy_eye(rcx, cy + 4, self.eye_w)
            if (self.idle_timer // 30) % 2 == 0:
                self.display.setColor(self.eye_dim)
                self.display.drawText("z", 108, 14)
                self.display.drawText("Z", 114, 8)
        elif self.mood == "SURPRISED":
            w = self.eye_w + 4
            h = effective_h + 6
            self.draw_rounded_eye(lcx, cy - 2, w, h, corner_r=8)
            self.draw_rounded_eye(rcx, cy - 2, w, h, corner_r=8)
            self.draw_filled_box(self.disp_w/2 - 4, cy + 15, 8, 8, self.mouth_color)
        elif self.mood == "ANGRY":
            self.draw_angry_eye(lcx, cy, self.eye_w, effective_h, is_left=True)
            self.draw_angry_eye(rcx, cy, self.eye_w, effective_h, is_left=False)
        else: # NEUTRAL
            self.draw_rounded_eye(lcx, cy, self.eye_w, effective_h, corner_r=6)
            self.draw_rounded_eye(rcx, cy, self.eye_w, effective_h, corner_r=6)

        # 5. Speech indicator (subtle audio bar on bottom)
        if self.speech_timer > 0:
            bar_w = int(abs(math.sin(self.speech_timer * 0.4)) * 24) + 8
            self.draw_filled_box(self.disp_w/2 - bar_w/2, 58, bar_w, 2, self.eye_color)

    def trigger_blink(self):
        """Initiates a blink sequence."""
        if not self.is_blinking:
            self.is_blinking = True
            self.blink_progress = 0.0

    def trigger_gesture(self, gesture_name):
        """Triggers a named physical head gesture."""
        name = gesture_name.lower().strip()
        self.active_gesture = name
        self.gesture_frame = 0
        if name in ("nod", "yes"):
            self.gesture_total_frames = 60
        elif name in ("shake", "no", "shake_head"):
            self.gesture_total_frames = 70
        elif name in ("wiggle", "dance"):
            self.gesture_total_frames = 80
        elif name in ("curious", "tilt"):
            self.gesture_total_frames = 60
        elif name in ("perk_up", "alert"):
            self.gesture_total_frames = 45
        elif name in ("droop", "bow"):
            self.gesture_total_frames = 60
        else:
            self.gesture_total_frames = 40

    def process_ai_commands(self):
        """Drains the AI command queue and executes actions."""
        while not COMMAND_QUEUE.empty():
            try:
                cmd = COMMAND_QUEUE.get_nowait()
                # 1. Update Mood
                if "mood" in cmd:
                    mood_str = str(cmd["mood"]).upper()
                    if mood_str in ("NEUTRAL", "HAPPY", "SURPRISED", "SLEEPY", "ANGRY", "THINKING", "LOVE"):
                        self.mood = mood_str
                        self.trigger_blink()

                # 2. Update Gaze / Look At
                if "gaze" in cmd:
                    g = str(cmd["gaze"]).lower()
                    if g == "left":
                        self.gaze_x = -0.9
                        self.target_yaw = 0.4
                    elif g == "right":
                        self.gaze_x = 0.9
                        self.target_yaw = -0.4
                    elif g == "up":
                        self.gaze_y = -0.8
                        self.target_pitch = -0.2
                    elif g == "down":
                        self.gaze_y = 0.8
                        self.target_pitch = 0.2
                    elif g in ("center", "forward"):
                        self.gaze_x = 0.0
                        self.gaze_y = 0.0
                        self.target_yaw = 0.0
                        self.target_pitch = 0.0

                if "look_at" in cmd:
                    coords = cmd["look_at"]
                    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
                        self.target_yaw = max(-1.2, min(1.2, float(coords[0])))
                        self.target_pitch = max(-0.4, min(0.4, float(coords[1])))
                        self.gaze_x = max(-1.0, min(1.0, self.target_yaw * 1.5))
                        self.gaze_y = max(-1.0, min(1.0, self.target_pitch * 2.0))

                # 3. Trigger Gesture
                if "gesture" in cmd:
                    self.trigger_gesture(cmd["gesture"])

                # 4. Handle Speech Text
                if "speech" in cmd and cmd["speech"]:
                    self.speech_text = str(cmd["speech"])
                    self.speech_timer = 90  # Display for ~1.5 seconds
                    print(f"🗣️ Gemma-Bot: \"{self.speech_text}\"")

                print(f"[AI Command Executed] Mood={self.mood}, Gesture={cmd.get('gesture')}")
            except Exception as e:
                print(f"[AI Command Error]: {e}")

    def update_animation(self):
        """Updates head servo positions, gestures, blinks, and timers."""
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

        # Autonomous natural blink timer
        self.next_blink -= 1
        if self.next_blink <= 0:
            self.trigger_blink()
            self.next_blink = random.randint(120, 260)

        # Speech timer
        if self.speech_timer > 0:
            self.speech_timer -= 1

        # 2. Gesture execution (overrides normal head target if active)
        if self.active_gesture:
            self.gesture_frame += 1
            t = self.gesture_frame
            total = self.gesture_total_frames

            if self.active_gesture in ("nod", "yes"):
                # Smooth double nod up & down
                self.target_pitch = math.sin(t * 0.25) * 0.25
                self.target_yaw = 0.0
            elif self.active_gesture in ("shake", "no", "shake_head"):
                # Smooth head shake left & right
                self.target_yaw = math.sin(t * 0.25) * 0.35
                self.target_pitch = 0.0
            elif self.active_gesture in ("wiggle", "dance"):
                # Happy wiggle
                self.target_yaw = math.sin(t * 0.3) * 0.25
                self.target_pitch = -0.15 + abs(math.sin(t * 0.2)) * 0.1
            elif self.active_gesture in ("curious", "tilt"):
                # Head tilts sideways with yaw
                self.target_yaw = 0.35
                self.target_pitch = -0.1
                self.gaze_x = -0.5
            elif self.active_gesture in ("perk_up", "alert"):
                self.target_pitch = -0.25
                self.target_yaw = 0.0
            elif self.active_gesture in ("droop", "bow"):
                self.target_pitch = 0.35
                self.target_yaw = 0.0

            if self.gesture_frame >= total:
                self.active_gesture = None
                self.target_yaw = 0.0
                self.target_pitch = 0.0
                self.gaze_x = 0.0
                self.gaze_y = 0.0

        # 3. Autonomous Idle Life (when no gesture is active)
        elif self.mood == "NEUTRAL":
            self.idle_timer += 1
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
        elif self.mood == "HAPPY" and not self.active_gesture:
            self.idle_timer += 1
            self.target_yaw = math.sin(self.idle_timer * 0.2) * 0.15
            self.target_pitch = -0.12
        elif self.mood == "SLEEPY" and not self.active_gesture:
            self.idle_timer += 1
            self.target_yaw = 0.0
            self.target_pitch = 0.32
            self.gaze_x = 0.0
            self.gaze_y = 0.5

        # 4. Smooth servo interpolation
        alpha = 0.10
        self.cur_yaw += (self.target_yaw - self.cur_yaw) * alpha
        self.cur_pitch += (self.target_pitch - self.cur_pitch) * alpha
        self.yaw_motor.setPosition(self.cur_yaw)
        self.pitch_motor.setPosition(self.cur_pitch)

        # Update global state for HTTP reporting
        ROBOT_STATE["mood"] = self.mood
        ROBOT_STATE["yaw"] = round(self.cur_yaw, 3)
        ROBOT_STATE["pitch"] = round(self.cur_pitch, 3)
        ROBOT_STATE["gaze"] = [round(self.gaze_x, 2), round(self.gaze_y, 2)]
        ROBOT_STATE["is_speaking"] = (self.speech_timer > 0)
        ROBOT_STATE["speech_text"] = self.speech_text if self.speech_timer > 0 else ""

    def handle_keyboard_input(self):
        """Processes manual keyboard and touch input."""
        key = self.keyboard.getKey()
        while key > 0:
            if key == ord('1'):
                self.mood = "NEUTRAL"
                print("Mood -> NEUTRAL")
            elif key == ord('2') or key == ord(' '):
                self.mood = "HAPPY"
                self.trigger_gesture("wiggle")
                print("Mood -> HAPPY (Pet / Tap)")
            elif key == ord('3'):
                self.mood = "SURPRISED"
                self.trigger_gesture("perk_up")
                print("Mood -> SURPRISED")
            elif key == ord('4'):
                self.mood = "SLEEPY"
                self.trigger_gesture("droop")
                print("Mood -> SLEEPY")
            elif key == ord('5'):
                self.mood = "ANGRY"
                print("Mood -> ANGRY")
            elif key == ord('6'):
                self.mood = "THINKING"
                self.trigger_gesture("curious")
                print("Mood -> THINKING")
            elif key == Keyboard.LEFT:
                self.target_yaw = min(1.2, self.target_yaw + 0.2)
                self.gaze_x = -0.9
            elif key == Keyboard.RIGHT:
                self.target_yaw = max(-1.2, self.target_yaw - 0.2)
                self.gaze_x = 0.9
            elif key == Keyboard.UP:
                self.target_pitch = max(-0.4, self.target_pitch - 0.1)
                self.gaze_y = -0.8
            elif key == Keyboard.DOWN:
                self.target_pitch = min(0.4, self.target_pitch + 0.1)
                self.gaze_y = 0.8
            key = self.keyboard.getKey()

        # Check physical capacitive head touch
        if self.touch and self.touch.getValue() > 0.5:
            if self.mood != "HAPPY":
                self.mood = "HAPPY"
                self.trigger_gesture("wiggle")
                print("Head Touched! -> HAPPY")

    def run(self):
        """Main simulation execution loop."""
        while self.robot.step(self.timestep) != -1:
            self.handle_keyboard_input()
            self.process_ai_commands()
            self.update_animation()
            self.render_face()

if __name__ == "__main__":
    companion = GemmaBotCompanion()
    companion.run()
