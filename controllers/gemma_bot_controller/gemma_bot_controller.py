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
import subprocess
import os
import sys
from controller import Robot, Keyboard, Supervisor

# Thread-safe queue for incoming AI commands
COMMAND_QUEUE = queue.Queue()
ROBOT_STATE = {
    "mood": "NEUTRAL",
    "gesture": None,
    "screen_theme": "CYAN",
    "screen_color": "#00F0FF",
    "yaw": 0.0,
    "pitch": 0.0,
    "gaze": [0.0, 0.0],
    "is_speaking": False,
    "speech_text": ""
}

# High-contrast OLED Screen Color Themes
SCREEN_THEMES = {
    "CYAN": {
        "name": "Electric Cyan",
        "bg_color": 0x000000,
        "eye_color": 0x00F0FF,
        "eye_dim": 0x007799,
        "mouth_color": 0x00D0FF,
        "sunglass_frame": 0x00F0FF,
    },
    "GREEN": {
        "name": "Matrix Emerald",
        "bg_color": 0x000000,
        "eye_color": 0x00FF66,
        "eye_dim": 0x008833,
        "mouth_color": 0x33FF88,
        "sunglass_frame": 0x00FF66,
    },
    "AMBER": {
        "name": "Retro Amber",
        "bg_color": 0x000000,
        "eye_color": 0xFFAA00,
        "eye_dim": 0x996600,
        "mouth_color": 0xFFCC33,
        "sunglass_frame": 0xFFAA00,
    },
    "BLUE": {
        "name": "Neon Blue",
        "bg_color": 0x000000,
        "eye_color": 0x2979FF,
        "eye_dim": 0x1545A5,
        "mouth_color": 0x5393FF,
        "sunglass_frame": 0x2979FF,
    },
    "PURPLE": {
        "name": "Cyberpunk Violet",
        "bg_color": 0x000000,
        "eye_color": 0xD500F9,
        "eye_dim": 0x7A008F,
        "mouth_color": 0xE040FB,
        "sunglass_frame": 0xD500F9,
    },
    "WHITE": {
        "name": "High Contrast White",
        "bg_color": 0x000000,
        "eye_color": 0xFFFFFF,
        "eye_dim": 0x777777,
        "mouth_color": 0xCCCCCC,
        "sunglass_frame": 0xFFFFFF,
    }
}
THEME_KEYS = list(SCREEN_THEMES.keys())

# Supported Emoji and Mood Mappings
EMOJI_MOOD_MAP = {
    # Happy / Smile
    "😀": "HAPPY", "😃": "HAPPY", "😄": "HAPPY", "😁": "HAPPY", "😊": "HAPPY", "🙂": "HAPPY", "HAPPY": "HAPPY", "SMILE": "HAPPY", "GRIN": "HAPPY",
    # Love / Heart
    "😍": "LOVE", "🥰": "LOVE", "😘": "LOVE", "❤️": "LOVE", "💕": "LOVE", "LOVE": "LOVE", "HEART": "LOVE",
    # Wink
    "😉": "WINK", "WINK": "WINK",
    # Cool / Sunglasses
    "😎": "COOL", "COOL": "COOL", "SUNGLASSES": "COOL",
    # Pleading / Cute
    "🥺": "PLEADING", "PLEADING": "PLEADING", "CUTE": "PLEADING", "PUPPY": "PLEADING",
    # Crying / Sad
    "😭": "CRYING", "😢": "CRYING", "😞": "CRYING", "SAD": "CRYING", "CRY": "CRYING", "CRYING": "CRYING",
    # Surprised / Shock
    "😮": "SURPRISED", "😲": "SURPRISED", "😱": "SURPRISED", "SURPRISED": "SURPRISED", "WOW": "SURPRISED", "SHOCK": "SURPRISED",
    # Sleepy / Tired
    "😴": "SLEEPY", "🥱": "SLEEPY", "💤": "SLEEPY", "SLEEPY": "SLEEPY", "TIRED": "SLEEPY", "SLEEP": "SLEEPY",
    # Angry / Mad
    "😡": "ANGRY", "😠": "ANGRY", "🤬": "ANGRY", "ANGRY": "ANGRY", "MAD": "ANGRY",
    # Thinking / Ponder
    "🤔": "THINKING", "🧐": "THINKING", "THINKING": "THINKING", "PONDER": "THINKING",
    # Dizzy / KO
    "😵": "DIZZY", "😵‍💫": "DIZZY", "DIZZY": "DIZZY", "CONFUSED": "DIZZY", "KO": "DIZZY",
    # Star Eyes / Excited
    "🤩": "STAR_EYES", "✨": "STAR_EYES", "STAR_EYES": "STAR_EYES", "EXCITED": "STAR_EYES", "STAR": "STAR_EYES",
    # Tongue / Playful
    "😋": "TONGUE", "😛": "TONGUE", "😝": "TONGUE", "😜": "TONGUE", "TONGUE": "TONGUE", "PLAYFUL": "TONGUE",
    # Smirk
    "😏": "SMIRK", "SMIRK": "SMIRK", "SLY": "SMIRK",
    # Neutral
    "😐": "NEUTRAL", "😑": "NEUTRAL", "NEUTRAL": "NEUTRAL"
}

def resolve_mood(val):
    """Normalizes any string, keyword, or unicode emoji into a canonical mood."""
    if not val:
        return "NEUTRAL"
    s = str(val).strip()
    if s in EMOJI_MOOD_MAP:
        return EMOJI_MOOD_MAP[s]
    upper = s.upper()
    if upper in EMOJI_MOOD_MAP:
        return EMOJI_MOOD_MAP[upper]
    for char, mood in EMOJI_MOOD_MAP.items():
        if char in s:
            return mood
    return "NEUTRAL"

# Default complementary facial expressions for physical gestures
GESTURE_DEFAULT_MOOD = {
    "curious": "THINKING",
    "tilt": "THINKING",
    "confused": "THINKING",
    "ponder": "THINKING",
    "perk_up": "SURPRISED",
    "alert": "SURPRISED",
    "peek_a_boo": "SURPRISED",
    "droop": "SLEEPY",
    "yawn": "SLEEPY",
    "nod": "HAPPY",
    "bounce": "STAR_EYES",
    "hop": "STAR_EYES",
    "cheer": "STAR_EYES",
    "celebrate": "STAR_EYES",
    "groove": "COOL",
    "dance": "COOL",
    "shiver": "CRYING",
    "tremble": "CRYING",
    "shy": "LOVE",
    "bashful": "LOVE",
    "dizzy_spin": "DIZZY",
    "swirl": "DIZZY",
    "orbital": "DIZZY",
    "wiggle": "HAPPY",
    "bow": "HAPPY",
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
        self.robot = Supervisor()
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
        
        self.current_theme = "CYAN"
        theme = SCREEN_THEMES[self.current_theme]
        self.bg_color = theme["bg_color"]           # True OLED black (no white blowout)
        self.eye_color = theme["eye_color"]         # High-contrast bright neon
        self.eye_dim = theme["eye_dim"]             # Secondary glow
        self.mouth_color = theme["mouth_color"]
        self.sunglass_frame = theme["sunglass_frame"]
        self.accent_pink = 0xFF4488     # Love / Hearts / Tongue
        self.accent_yellow = 0xFFDD00   # Star Eyes / Sparkle
        self.tear_blue = 0x44AAFF       # Crying Tears
        self.white = 0xFFFFFF           # Specular highlights & reflections
        
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
        
        # Speech state & audio process
        self.speech_text = ""
        self.speech_timer = 0
        self.speech_process = None
        
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
        """Draws a cute heart for LOVE mood (😍)."""
        self.draw_filled_box(cx - 7, cy - 4, 6, 6, self.accent_pink)
        self.draw_filled_box(cx + 1, cy - 4, 6, 6, self.accent_pink)
        self.draw_filled_box(cx - 9, cy, 18, 5, self.accent_pink)
        self.draw_filled_box(cx - 7, cy + 5, 14, 4, self.accent_pink)
        self.draw_filled_box(cx - 4, cy + 9, 8, 4, self.accent_pink)
        self.draw_filled_box(cx - 1, cy + 13, 2, 2, self.accent_pink)

    def draw_star(self, cx, cy, r=11):
        """Draws a bright 4-point twinkling star for STAR_EYES (🤩)."""
        for i in range(r):
            w = r - i
            self.draw_filled_box(cx - w, cy - i, w * 2, 1, self.accent_yellow)
            self.draw_filled_box(cx - w, cy + i, w * 2, 1, self.accent_yellow)
        self.draw_filled_box(cx - 2, cy - 2, 4, 4, self.white)

    def draw_sunglasses(self, lcx, rcx, cy, w, h):
        """Draws stylish cool pixel sunglasses with glossy reflections for COOL (😎)."""
        top_y = cy - h/2 + 2
        lens_h = h - 6
        # Left lens & outline
        self.draw_filled_box(lcx - w/2 - 2, top_y, w + 4, lens_h, self.sunglass_frame)
        self.draw_filled_box(lcx - w/2, top_y + 2, w, lens_h - 4, 0x111111)
        # Right lens & outline
        self.draw_filled_box(rcx - w/2 - 2, top_y, w + 4, lens_h, self.sunglass_frame)
        self.draw_filled_box(rcx - w/2, top_y + 2, w, lens_h - 4, 0x111111)
        # Bridge connecting glasses
        bridge_start = lcx + w/2 - 1
        bridge_w = (rcx - w/2) - bridge_start + 1
        self.draw_filled_box(bridge_start, top_y + 2, bridge_w, 3, self.sunglass_frame)
        # Glossy diagonal reflections
        self.draw_filled_box(lcx - w/4, top_y + 3, 3, lens_h - 6, self.white)
        self.draw_filled_box(rcx - w/4, top_y + 3, 3, lens_h - 6, self.white)

    def draw_pleading_eye(self, cx, cy, w, h):
        """Draws giant sparkly anime/puppy eye for PLEADING (🥺)."""
        self.draw_rounded_eye(cx, cy, w + 2, h + 2, corner_r=8, color=self.eye_color)
        # Upper large specular reflection
        self.draw_filled_box(cx - w/4 - 2, cy - h/4 - 2, 8, 8, self.white)
        # Lower small specular reflection
        self.draw_filled_box(cx + w/6, cy + h/6, 4, 4, self.white)

    def draw_cross_eye(self, cx, cy, size=10):
        """Draws an 'X' cross eye for DIZZY / KO (😵)."""
        t = 3
        for i in range(-size, size):
            self.draw_filled_box(cx + i - t//2, cy + i - t//2, t, t, self.eye_color)
            self.draw_filled_box(cx + i - t//2, cy - i - t//2, t, t, self.eye_color)

    def draw_crying_eye(self, cx, cy, w, h, is_left=True):
        """Draws sad eye with streaming tear drops for CRYING (😭)."""
        y = cy - h/2
        self.draw_filled_box(cx - w/2, y + 5, w, h - 8, self.eye_color)
        if is_left:
            self.draw_filled_box(cx - w/2, y, w/2, 7, self.bg_color)
        else:
            self.draw_filled_box(cx, y, w/2, 7, self.bg_color)
        # Animated tear droplets streaming down
        tear_y = int(cy + 10 + (self.idle_timer * 2.2) % 20)
        self.draw_filled_box(cx - 3, min(self.disp_h - 4, tear_y), 6, 6, self.tear_blue)
        self.draw_filled_box(cx - 2, min(self.disp_h - 8, tear_y - 5), 4, 4, self.white)

    def draw_tongue_mouth(self, cx, cy):
        """Draws open smiling mouth with cute pink tongue for TONGUE (😋)."""
        self.draw_filled_box(cx - 6, cy + 15, 12, 3, self.mouth_color)
        self.draw_filled_box(cx - 3, cy + 17, 7, 6, self.accent_pink)
        self.draw_filled_box(cx - 1, cy + 22, 3, 2, self.accent_pink)

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

        # 4. Render eyes according to mood / emoji
        if self.blink_progress > 0.85 and self.mood != "COOL":
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
        elif self.mood == "WINK":
            self.draw_rounded_eye(lcx, cy, self.eye_w, effective_h, corner_r=6)
            self.draw_happy_eye(rcx, cy, self.eye_w)
            self.draw_filled_box(self.disp_w/2 - 5, cy + 16, 10, 3, self.mouth_color)
            self.draw_filled_box(self.disp_w/2 + 3, cy + 14, 3, 3, self.mouth_color)
        elif self.mood == "COOL":
            self.draw_sunglasses(lcx, rcx, cy, self.eye_w, self.eye_h)
            # Confident corner smirk
            self.draw_filled_box(self.disp_w/2 - 4, cy + 17, 10, 3, self.mouth_color)
            self.draw_filled_box(self.disp_w/2 + 5, cy + 15, 3, 3, self.mouth_color)
        elif self.mood == "STAR_EYES":
            self.draw_star(lcx, cy, r=12)
            self.draw_star(rcx, cy, r=12)
            self.draw_filled_box(self.disp_w/2 - 6, cy + 16, 12, 4, self.mouth_color)
            self.draw_filled_box(self.disp_w/2 - 4, cy + 20, 8, 2, self.mouth_color)
        elif self.mood == "PLEADING":
            self.draw_pleading_eye(lcx, cy, self.eye_w, effective_h)
            self.draw_pleading_eye(rcx, cy, self.eye_w, effective_h)
            # Trembling small mouth
            tremble = 1 if (self.idle_timer // 8) % 2 == 0 else 0
            self.draw_filled_box(self.disp_w/2 - 4, cy + 17 + tremble, 8, 3, self.mouth_color)
        elif self.mood == "CRYING":
            self.draw_crying_eye(lcx, cy, self.eye_w, effective_h, is_left=True)
            self.draw_crying_eye(rcx, cy, self.eye_w, effective_h, is_left=False)
            # Downward pout
            self.draw_filled_box(self.disp_w/2 - 5, cy + 18, 10, 3, self.tear_blue)
            self.draw_filled_box(self.disp_w/2 - 5, cy + 20, 3, 2, self.tear_blue)
            self.draw_filled_box(self.disp_w/2 + 2, cy + 20, 3, 2, self.tear_blue)
        elif self.mood == "TONGUE":
            self.draw_happy_eye(lcx, cy, self.eye_w)
            self.draw_happy_eye(rcx, cy, self.eye_w)
            self.draw_tongue_mouth(self.disp_w/2, cy)
        elif self.mood == "SMIRK":
            self.draw_rounded_eye(lcx, cy - 2, self.eye_w, effective_h, corner_r=6)
            self.draw_sleepy_eye(rcx, cy + 3, self.eye_w)
            self.draw_filled_box(self.disp_w/2 - 3, cy + 16, 8, 3, self.mouth_color)
            self.draw_filled_box(self.disp_w/2 + 4, cy + 14, 3, 3, self.mouth_color)
        elif self.mood == "DIZZY":
            self.draw_cross_eye(lcx, cy, size=10)
            self.draw_cross_eye(rcx, cy, size=10)
            # Wavy mouth
            self.draw_filled_box(self.disp_w/2 - 6, cy + 16, 4, 3, self.mouth_color)
            self.draw_filled_box(self.disp_w/2 - 2, cy + 18, 4, 3, self.mouth_color)
            self.draw_filled_box(self.disp_w/2 + 2, cy + 16, 4, 3, self.mouth_color)
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
            self.draw_filled_box(self.disp_w/2 - 5, cy + 17, 10, 3, self.mouth_color)
        else: # NEUTRAL
            self.draw_rounded_eye(lcx, cy, self.eye_w, effective_h, corner_r=6)
            self.draw_rounded_eye(rcx, cy, self.eye_w, effective_h, corner_r=6)
            self.draw_filled_box(self.disp_w/2 - 5, cy + 17, 10, 2, self.mouth_color)

        # 5. Speech indicator & dynamic lip-sync mouth
        if self.speech_timer > 0:
            mouth_phase = self.speech_timer * 0.4
            mouth_w = 12 + int(abs(math.cos(mouth_phase * 0.7)) * 8)
            mouth_h = 4 + int(abs(math.sin(mouth_phase)) * 8)
            self.draw_filled_box(self.disp_w/2 - mouth_w/2, cy + 16 - mouth_h/2, mouth_w, mouth_h, self.mouth_color)
            bar_w = int(abs(math.sin(mouth_phase * 0.9)) * 24) + 10
            self.draw_filled_box(self.disp_w/2 - bar_w/2, 59, bar_w, 2, self.eye_color)

    def trigger_speech(self, text, play_audio=True):
        """Speaks text out loud and activates animated lip-sync."""
        if not text:
            return
        self.speech_text = str(text).strip()
        # Kill previous speech process if still running (instant barge-in cutoff)
        if self.speech_process and self.speech_process.poll() is None:
            try:
                self.speech_process.terminate()
            except Exception:
                pass
            self.speech_process = None

        # Estimate duration in frames (~32ms timestep)
        words = len(self.speech_text.split())
        est_seconds = max(1.6, words * 0.38 + 0.6)
        self.speech_timer = int((est_seconds * 1000) / max(1, self.timestep))

        # Launch native macOS TTS asynchronously if play_audio is True
        if play_audio:
            try:
                self.speech_process = subprocess.Popen(
                    ["say", "-v", "Samantha", self.speech_text],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception as e:
                print(f"[TTS Audio Error]: {e}")
        print(f"🗣️ Gemma-Bot: \"{self.speech_text}\"")

    def interrupt_speech(self):
        """Immediately silences speech playback and halts lip-sync."""
        if self.speech_process and self.speech_process.poll() is None:
            try:
                self.speech_process.terminate()
            except Exception:
                pass
        self.speech_process = None
        self.speech_timer = 0
        self.speech_text = ""
        self.trigger_blink()

    def trigger_blink(self):
        """Initiates a blink sequence."""
        if not self.is_blinking:
            self.is_blinking = True
            self.blink_progress = 0.0

    def set_screen_theme(self, theme):
        """Sets the active OLED screen color theme."""
        if not theme:
            return
        t = str(theme).upper().strip()
        if t in SCREEN_THEMES:
            cfg = SCREEN_THEMES[t]
            self.current_theme = t
            self.bg_color = cfg["bg_color"]
            self.eye_color = cfg["eye_color"]
            self.eye_dim = cfg["eye_dim"]
            self.mouth_color = cfg["mouth_color"]
            self.sunglass_frame = cfg["sunglass_frame"]
            print(f"[Screen Theme] Switched to {cfg['name']} (Color: #{self.eye_color:06X})")
            self.render_face()

    def cycle_screen_theme(self):
        """Cycles through available screen color themes."""
        try:
            curr_idx = THEME_KEYS.index(self.current_theme)
        except ValueError:
            curr_idx = 0
        next_theme = THEME_KEYS[(curr_idx + 1) % len(THEME_KEYS)]
        self.set_screen_theme(next_theme)

    def trigger_gesture(self, gesture_name):
        """Triggers a named physical head gesture with trajectory dynamics."""
        name = gesture_name.lower().strip()
        self.active_gesture = name
        self.gesture_frame = 0
        if name in ("nod", "yes"):
            self.gesture_total_frames = 60
        elif name in ("shake", "no", "shake_head"):
            self.gesture_total_frames = 70
        elif name in ("wiggle",):
            self.gesture_total_frames = 80
        elif name in ("curious", "tilt"):
            self.gesture_total_frames = 75
        elif name in ("tilt_left", "lean_left"):
            self.gesture_total_frames = 55
        elif name in ("tilt_right", "lean_right"):
            self.gesture_total_frames = 55
        elif name in ("perk_up", "alert"):
            self.gesture_total_frames = 65
        elif name in ("droop",):
            self.gesture_total_frames = 85
        elif name in ("bounce", "hop"):
            self.gesture_total_frames = 50
        elif name in ("groove", "dance"):
            self.gesture_total_frames = 90
        elif name in ("shiver", "tremble", "quiver"):
            self.gesture_total_frames = 60
        elif name in ("scan", "look_around", "search"):
            self.gesture_total_frames = 100
        elif name in ("confused", "ponder"):
            self.gesture_total_frames = 80
        elif name in ("bow", "respect"):
            self.gesture_total_frames = 70
        elif name in ("cheer", "celebrate"):
            self.gesture_total_frames = 70
        elif name in ("yawn",):
            self.gesture_total_frames = 80
        elif name in ("shy", "bashful"):
            self.gesture_total_frames = 65
        elif name in ("peek_a_boo", "hide"):
            self.gesture_total_frames = 85
        elif name in ("dizzy_spin", "swirl", "orbital"):
            self.gesture_total_frames = 90
        else:
            self.gesture_total_frames = 50

    def process_ai_commands(self):
        """Drains the AI command queue and executes actions."""
        while not COMMAND_QUEUE.empty():
            try:
                cmd = COMMAND_QUEUE.get_nowait()
                # 0. High-level Session State Transitions (Gemma-Talk compatibility)
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

                # 1. Instant Interruption / Barge-in trigger
                if cmd.get("interrupt") or cmd.get("flush"):
                    self.interrupt_speech()

                # 2. Update Mood / Emoji
                if "mood" in cmd:
                    self.mood = resolve_mood(cmd["mood"])
                    self.trigger_blink()

                # 3. Update Gaze / Look At
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

                # 4. Trigger Gesture
                if "gesture" in cmd and cmd["gesture"]:
                    g_name = str(cmd["gesture"]).lower().strip()
                    self.trigger_gesture(g_name)
                    # Automatically set matching expressive mood if none explicitly passed
                    if "mood" not in cmd and g_name in GESTURE_DEFAULT_MOOD:
                        self.mood = GESTURE_DEFAULT_MOOD[g_name]
                        self.trigger_blink()

                # 5. Handle Speech Text & Audible Talk-back
                if "speech" in cmd and cmd["speech"]:
                    text_str = str(cmd["speech"])
                    # Auto-detect emojis in speech to drive matching face
                    for char, m in EMOJI_MOOD_MAP.items():
                        if char in text_str and "mood" not in cmd:
                            self.mood = m
                            break
                    play_audio = bool(cmd.get("audio", True))
                    self.trigger_speech(text_str, play_audio=play_audio)

                # 6. Screen Color Theme
                if "screen_color" in cmd or "theme" in cmd or "color" in cmd:
                    col_val = cmd.get("screen_color") or cmd.get("theme") or cmd.get("color")
                    self.set_screen_theme(col_val)

                print(f"[AI Command Executed] Mood={self.mood}, Gesture={cmd.get('gesture')}, Theme={self.current_theme}")
            except Exception as e:
                print(f"[AI Command Error]: {e}")

    def update_animation(self):
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

        # Autonomous natural blink timer
        self.next_blink -= 1
        if self.next_blink <= 0:
            self.trigger_blink()
            self.next_blink = random.randint(120, 260)

        # Speech timer & conversational micro-nodding
        if self.speech_timer > 0:
            self.speech_timer -= 1
            if not self.active_gesture:
                self.target_pitch = math.sin(self.speech_timer * 0.22) * 0.08

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
            elif self.active_gesture in ("wiggle",):
                # Happy wiggle
                self.target_yaw = math.sin(t * 0.3) * 0.25
                self.target_pitch = -0.15 + abs(math.sin(t * 0.2)) * 0.1
            elif self.active_gesture in ("curious", "tilt"):
                # Expressive Inquisitive Head Tilt: tilts sideways decisively, bobs attentively, then eases back
                p = t / total
                if p < 0.25:
                    ease = math.sin(p * 2.0 * math.pi * 0.5)
                    self.target_yaw = 0.58 * ease
                    self.target_pitch = -0.15 * ease
                    self.gaze_x = -0.90 * ease
                    self.gaze_y = -0.35 * ease
                elif p < 0.75:
                    subtle_bob = math.sin((t - 18) * 0.28) * 0.06
                    self.target_yaw = 0.55 + subtle_bob
                    self.target_pitch = -0.15 + subtle_bob * 0.6
                    self.gaze_x = -0.90
                    self.gaze_y = -0.30
                else:
                    ease_back = (1.0 - p) / 0.25
                    self.target_yaw = 0.55 * ease_back
                    self.target_pitch = -0.15 * ease_back
                    self.gaze_x = -0.90 * ease_back
                    self.gaze_y = -0.30 * ease_back
            elif self.active_gesture in ("tilt_left", "lean_left"):
                self.target_yaw = 0.45
                self.target_pitch = -0.08
                self.gaze_x = -0.8
            elif self.active_gesture in ("tilt_right", "lean_right"):
                self.target_yaw = -0.45
                self.target_pitch = -0.08
                self.gaze_x = 0.8
            elif self.active_gesture in ("perk_up", "alert"):
                # Sudden Attentive Upward Motion: snaps head up high with alert flutter, then settles
                p = t / total
                if p < 0.20:
                    snap = math.sin(p * 2.5 * math.pi)
                    self.target_pitch = -0.38 * snap
                    self.target_yaw = 0.0
                    self.gaze_y = -0.95
                elif p < 0.75:
                    alert_flutter = math.sin((t - 13) * 0.45) * 0.05
                    self.target_pitch = -0.36 + alert_flutter
                    self.target_yaw = math.sin((t - 13) * 0.25) * 0.08
                    self.gaze_y = -0.90
                else:
                    ease_back = (1.0 - p) / 0.25
                    self.target_pitch = -0.36 * ease_back
                    self.gaze_y = -0.90 * ease_back
            elif self.active_gesture in ("droop",):
                # Sleepy / Resting Slump: heavy forward slump with rhythmic breathing
                p = t / total
                if p < 0.35:
                    slump = math.sin(p * (math.pi / 0.7))
                    self.target_pitch = 0.40 * slump
                    self.target_yaw = 0.0
                    self.gaze_y = 0.90 * slump
                elif p < 0.78:
                    sleep_breath = math.sin((t - 30) * 0.16) * 0.06
                    self.target_pitch = 0.38 + sleep_breath
                    self.target_yaw = math.sin((t - 30) * 0.08) * 0.04
                    self.gaze_y = 0.90
                else:
                    ease_back = (1.0 - p) / 0.22
                    self.target_pitch = 0.38 * ease_back
                    self.gaze_y = 0.90 * ease_back
            elif self.active_gesture in ("bounce", "hop"):
                # Fast energetic vertical bobbing
                self.target_pitch = -0.18 + math.sin(t * 0.4) * 0.18
                self.target_yaw = math.sin(t * 0.2) * 0.08
                self.gaze_y = -0.6
            elif self.active_gesture in ("groove", "dance"):
                # Smooth figure-8 dance
                self.target_yaw = math.sin(t * 0.18) * 0.38
                self.target_pitch = math.sin(t * 0.36) * 0.16
                self.gaze_x = math.sin(t * 0.18) * 0.7
            elif self.active_gesture in ("shiver", "tremble", "quiver"):
                # High-frequency micro-jitter
                self.target_yaw = math.sin(t * 1.8) * 0.07
                self.target_pitch = 0.14 + math.cos(t * 1.5) * 0.05
                self.gaze_y = 0.4
            elif self.active_gesture in ("scan", "look_around", "search"):
                # Wide sweeping panoramic room scan
                self.target_yaw = math.sin(t * 0.07) * 0.85
                self.target_pitch = -0.05 + math.cos(t * 0.14) * 0.08
                self.gaze_x = math.sin(t * 0.07) * 0.95
            elif self.active_gesture in ("confused", "ponder"):
                # Puzzled alternating tilt
                if t < 40:
                    self.target_yaw = 0.42
                    self.target_pitch = -0.1
                    self.gaze_x = -0.7
                else:
                    self.target_yaw = -0.42
                    self.target_pitch = -0.05
                    self.gaze_x = 0.7
            elif self.active_gesture in ("bow", "respect"):
                # Deep polite formal bow
                if t < 35:
                    self.target_pitch = (t / 35.0) * 0.38
                else:
                    self.target_pitch = ((70 - t) / 35.0) * 0.38
                self.target_yaw = 0.0
                self.gaze_y = 0.8
            elif self.active_gesture in ("cheer", "celebrate"):
                # Joyful head toss back with happy shakes
                self.target_pitch = -0.32 + math.sin(t * 0.3) * 0.08
                self.target_yaw = math.sin(t * 0.4) * 0.25
                self.gaze_y = -0.85
            elif self.active_gesture in ("yawn",):
                # Stretching upward then relaxing slump
                if t < 45:
                    self.target_pitch = -0.28 * (t / 45.0)
                    self.gaze_y = -0.7
                else:
                    self.target_pitch = 0.25 * ((t - 45) / 35.0)
                    self.gaze_y = 0.5
            elif self.active_gesture in ("shy", "bashful"):
                # Turn away and tuck down
                self.target_yaw = -0.45
                self.target_pitch = 0.24
                self.gaze_x = -0.8
                self.gaze_y = 0.6
            elif self.active_gesture in ("peek_a_boo", "hide"):
                if t < 45:
                    self.target_pitch = 0.38
                    self.blink_progress = 1.0
                    self.target_yaw = 0.0
                else:
                    self.target_pitch = -0.25
                    self.blink_progress = 0.0
                    self.target_yaw = math.sin(t * 0.3) * 0.15
            elif self.active_gesture in ("dizzy_spin", "swirl", "orbital"):
                # Circular orbital head roll
                self.target_yaw = math.sin(t * 0.18) * 0.35
                self.target_pitch = math.cos(t * 0.18) * 0.22
                self.gaze_x = math.sin(t * 0.18) * 0.8
                self.gaze_y = math.cos(t * 0.18) * 0.8

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

        # 4. Smooth servo interpolation (crisper response during active gestures)
        alpha = 0.22 if self.active_gesture else 0.12
        self.cur_yaw += (self.target_yaw - self.cur_yaw) * alpha
        self.cur_pitch += (self.target_pitch - self.cur_pitch) * alpha
        self.yaw_motor.setPosition(self.cur_yaw)
        self.pitch_motor.setPosition(self.cur_pitch)

        # Update global state for HTTP reporting
        ROBOT_STATE["mood"] = self.mood
        ROBOT_STATE["gesture"] = self.active_gesture
        ROBOT_STATE["screen_theme"] = self.current_theme
        ROBOT_STATE["screen_color"] = f"#{self.eye_color:06X}"
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
                print("Mood -> NEUTRAL 😐")
            elif key == ord('2') or key == ord(' '):
                self.mood = "HAPPY"
                self.trigger_gesture("wiggle")
                print("Mood -> HAPPY 😀")
            elif key == ord('3'):
                self.mood = "SURPRISED"
                self.trigger_gesture("perk_up")
                print("Mood -> SURPRISED 😮")
            elif key == ord('4'):
                self.mood = "SLEEPY"
                self.trigger_gesture("droop")
                print("Mood -> SLEEPY 😴")
            elif key == ord('5'):
                self.mood = "ANGRY"
                print("Mood -> ANGRY 😡")
            elif key == ord('6'):
                self.mood = "THINKING"
                self.trigger_gesture("curious")
                print("Mood -> THINKING 🤔")
            elif key == ord('7'):
                self.mood = "LOVE"
                self.trigger_gesture("wiggle")
                print("Mood -> LOVE 😍")
            elif key == ord('8'):
                self.mood = "COOL"
                print("Mood -> COOL 😎")
            elif key == ord('9'):
                self.mood = "STAR_EYES"
                self.trigger_gesture("perk_up")
                print("Mood -> STAR_EYES 🤩")
            elif key == ord('0'):
                self.mood = "PLEADING"
                print("Mood -> PLEADING 🥺")
            elif key in (ord('W'), ord('w')):
                self.mood = "WINK"
                print("Mood -> WINK 😉")
            elif key in (ord('C'), ord('c')):
                self.mood = "CRYING"
                self.trigger_gesture("droop")
                print("Mood -> CRYING 😭")
            elif key in (ord('T'), ord('t')):
                self.mood = "TONGUE"
                self.trigger_gesture("wiggle")
                print("Mood -> TONGUE 😋")
            elif key in (ord('D'), ord('d')):
                self.mood = "DIZZY"
                self.trigger_gesture("shake")
                print("Mood -> DIZZY 😵")
            elif key in (ord('S'), ord('s')):
                self.mood = "SMIRK"
                print("Mood -> SMIRK 😏")
            # --- Physical Gesture Triggers ---
            elif key in (ord('N'), ord('n')):
                self.trigger_gesture("nod")
                print("Gesture -> NOD")
            elif key in (ord('H'), ord('h')):
                self.trigger_gesture("shake")
                print("Gesture -> SHAKE")
            elif key in (ord('B'), ord('b')):
                self.trigger_gesture("bounce")
                print("Gesture -> BOUNCE")
            elif key in (ord('G'), ord('g')):
                self.trigger_gesture("groove")
                print("Gesture -> GROOVE / DANCE")
            elif key in (ord('V'), ord('v')):
                self.trigger_gesture("shiver")
                print("Gesture -> SHIVER / TREMBLE")
            elif key in (ord('R'), ord('r')):
                self.trigger_gesture("scan")
                print("Gesture -> SCAN / LOOK AROUND")
            elif key in (ord('P'), ord('p')):
                self.trigger_gesture("perk_up")
                print("Gesture -> PERK UP")
            elif key in (ord('Y'), ord('y')):
                self.trigger_gesture("yawn")
                print("Gesture -> YAWN")
            elif key in (ord('O'), ord('o')):
                self.trigger_gesture("bow")
                print("Gesture -> BOW")
            elif key in (ord('U'), ord('u')):
                self.trigger_gesture("confused")
                print("Gesture -> CONFUSED TILT")
            elif key in (ord('Z'), ord('z')):
                self.trigger_gesture("dizzy_spin")
                print("Gesture -> DIZZY SPIN")
            elif key in (ord('J'), ord('j')):
                self.trigger_gesture("cheer")
                print("Gesture -> CHEER / CELEBRATE")
            elif key in (ord('K'), ord('k')):
                self.trigger_gesture("shy")
                print("Gesture -> SHY / BASHFUL")
            elif key in (ord('Q'), ord('q')):
                self.trigger_gesture("peek_a_boo")
                print("Gesture -> PEEK-A-BOO")
            elif key in (ord('X'), ord('x')):
                self.cycle_screen_theme()
            elif key == ord('['):
                self.trigger_gesture("tilt_left")
                print("Gesture -> TILT LEFT")
            elif key == ord(']'):
                self.trigger_gesture("tilt_right")
                print("Gesture -> TILT RIGHT")
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
