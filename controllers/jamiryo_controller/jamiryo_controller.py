"""
Jamiryo Desktop Companion Controller for Webots
Features:
- Real-time animated OLED eyes rendered on a 128x64 Webots Display device.
- Dual-axis servo head motion (Yaw / Pan and Pitch / Tilt).
- Expressive moods: Neutral, Happy, Surprised, Sleepy, Angry, and Idle wandering.
- Interactive keyboard controls & autonomous companion behaviors.
"""

import math
import random
from controller import Robot, Keyboard

class JamiryoCompanion:
    def __init__(self):
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())
        
        # Hardware devices
        self.display = self.robot.getDevice("oled_display")
        self.camera = self.robot.getDevice("camera")
        self.yaw_motor = self.robot.getDevice("head_yaw")
        self.pitch_motor = self.robot.getDevice("head_pitch")
        self.touch = self.robot.getDevice("head_touch")
        
        # Ensure display is fully opaque so graphics render brightly
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
        self.yaw_motor.setVelocity(2.5)
        self.pitch_motor.setVelocity(2.0)
        
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
        self.eye_dim = 0x008899       # Glow / edge shading
        self.mouth_color = 0x00BBDD
        
        # Eye baseline geometry
        self.left_cx = 38
        self.right_cx = 90
        self.base_cy = 32
        self.eye_w = 28
        self.eye_h = 34
        
        # Dynamic eye state
        self.gaze_x = 0.0   # -1.0 (left) to +1.0 (right)
        self.gaze_y = 0.0   # -1.0 (up) to +1.0 (down)
        self.blink_progress = 0.0  # 0.0 (open) to 1.0 (closed)
        self.is_blinking = False
        self.blink_speed = 0.18
        
        # Behavior / mood state
        self.mood = "NEUTRAL"
        self.mood_timer = 0
        self.idle_timer = 0
        self.next_idle_action = 100
        self.next_blink = 140
        
        # Render initial frame immediately
        self.render_face()
        
        # Print instructions
        print("=" * 60)
        print("🤖 Jamiryo Desktop Companion Simulator Initialized!")
        print("Controls:")
        print("  [1] Neutral / Idle     [2] Happy Mode")
        print("  [3] Surprised Mode     [4] Sleepy Mode")
        print("  [5] Angry Mode         [SPACE] Pet Head / Tap")
        print("  [Arrow Keys] Manually Pan / Tilt Head")
        print("=" * 60)

    def draw_filled_box(self, x, y, w, h, color):
        """Helper to draw a clamped filled box on the display."""
        x0 = max(0, min(self.disp_w - 1, int(x)))
        y0 = max(0, min(self.disp_h - 1, int(y)))
        x1 = max(0, min(self.disp_w, int(x + w)))
        y1 = max(0, min(self.disp_h, int(y + h)))
        if x1 > x0 and y1 > y0:
            self.display.setColor(color)
            self.display.fillRectangle(x0, y0, x1 - x0, y1 - y0)

    def draw_rounded_eye(self, cx, cy, w, h, corner_r=5):
        """Draws a clean rounded rectangle OLED eye."""
        x = cx - w / 2
        y = cy - h / 2
        # Center block
        self.draw_filled_box(x + corner_r, y, w - 2 * corner_r, h, self.eye_color)
        # Side blocks
        self.draw_filled_box(x, y + corner_r, corner_r, h - 2 * corner_r, self.eye_color)
        self.draw_filled_box(x + w - corner_r, y + corner_r, corner_r, h - 2 * corner_r, self.eye_color)
        # Soft corners
        self.draw_filled_box(x + 1, y + 1, corner_r - 1, corner_r - 1, self.eye_dim)
        self.draw_filled_box(x + w - corner_r, y + 1, corner_r - 1, corner_r - 1, self.eye_dim)
        self.draw_filled_box(x + 1, y + h - corner_r, corner_r - 1, corner_r - 1, self.eye_dim)
        self.draw_filled_box(x + w - corner_r, y + h - corner_r, corner_r - 1, corner_r - 1, self.eye_dim)

    def draw_happy_eye(self, cx, cy, w):
        """Draws a crescent / squinting happy eye curve (^_^)."""
        x = cx - w / 2
        # Upper curved arch
        self.draw_filled_box(x, cy - 2, w, 7, self.eye_color)
        self.draw_filled_box(x + 2, cy - 5, w - 4, 4, self.eye_color)
        self.draw_filled_box(x + 5, cy - 7, w - 10, 3, self.eye_color)
        # Cutout lower inner center to leave an arch
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

    def render_face(self):
        """Renders the complete OLED facial expression and eye gaze."""
        if not self.display:
            return
            
        # 1. Clear background with solid black
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
            # Closed blink slit
            self.draw_filled_box(lcx - self.eye_w/2, cy, self.eye_w, 4, self.eye_color)
            self.draw_filled_box(rcx - self.eye_w/2, cy, self.eye_w, 4, self.eye_color)
        elif self.mood == "HAPPY":
            self.draw_happy_eye(lcx, cy, self.eye_w)
            self.draw_happy_eye(rcx, cy, self.eye_w)
            # Smiling mouth
            self.draw_filled_box(self.disp_w/2 - 6, cy + 16, 12, 3, self.mouth_color)
            self.draw_filled_box(self.disp_w/2 - 3, cy + 19, 6, 2, self.mouth_color)
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
            # O mouth
            self.draw_filled_box(self.disp_w/2 - 4, cy + 15, 8, 8, self.mouth_color)
        elif self.mood == "ANGRY":
            self.draw_angry_eye(lcx, cy, self.eye_w, effective_h, is_left=True)
            self.draw_angry_eye(rcx, cy, self.eye_w, effective_h, is_left=False)
        else: # NEUTRAL
            self.draw_rounded_eye(lcx, cy, self.eye_w, effective_h, corner_r=6)
            self.draw_rounded_eye(rcx, cy, self.eye_w, effective_h, corner_r=6)

    def trigger_blink(self):
        """Initiates a blink sequence."""
        if not self.is_blinking:
            self.is_blinking = True
            self.blink_progress = 0.0

    def update_animation(self):
        """Updates eye blinks, saccades, and mood timers."""
        # Blink animation
        if self.is_blinking:
            self.blink_progress += self.blink_speed
            if self.blink_progress >= 1.0:
                self.blink_progress = 1.0
                self.blink_speed = -0.22
            elif self.blink_progress <= 0.0:
                self.blink_progress = 0.0
                self.is_blinking = False
                self.blink_speed = 0.20

        # Autonomous blinking in neutral or happy mode
        self.next_blink -= 1
        if self.next_blink <= 0:
            self.trigger_blink()
            self.next_blink = random.randint(120, 260)

        # Autonomous idle wandering
        self.idle_timer += 1
        if self.mood == "NEUTRAL":
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
                    self.target_yaw = random.uniform(0.2, 0.6)  # positive yaw = turn toward left
                    self.target_pitch = self.gaze_y * 0.2
                else:
                    self.gaze_x = 0.75
                    self.gaze_y = random.uniform(-0.3, 0.3)
                    self.target_yaw = random.uniform(-0.6, -0.2)
                    self.target_pitch = self.gaze_y * 0.2
                self.next_idle_action = random.randint(100, 240)
        elif self.mood == "HAPPY":
            wiggle = math.sin(self.idle_timer * 0.2) * 0.15
            self.target_yaw = wiggle
            self.target_pitch = -0.15 + abs(math.sin(self.idle_timer * 0.15)) * 0.1
        elif self.mood == "SLEEPY":
            self.target_yaw = 0.0
            self.target_pitch = 0.35
            self.gaze_x = 0.0
            self.gaze_y = 0.5
        elif self.mood == "SURPRISED":
            self.target_pitch = -0.25

        # Smooth servo interpolation
        alpha = 0.08
        self.cur_yaw += (self.target_yaw - self.cur_yaw) * alpha
        self.cur_pitch += (self.target_pitch - self.cur_pitch) * alpha
        self.yaw_motor.setPosition(self.cur_yaw)
        self.pitch_motor.setPosition(self.cur_pitch)

    def handle_input(self):
        """Processes keyboard and touch interaction."""
        key = self.keyboard.getKey()
        while key > 0:
            if key == ord('1'):
                self.mood = "NEUTRAL"
                print("Mood -> NEUTRAL")
            elif key == ord('2') or key == ord(' '):
                self.mood = "HAPPY"
                self.trigger_blink()
                print("Mood -> HAPPY (Pet / Tap)")
            elif key == ord('3'):
                self.mood = "SURPRISED"
                print("Mood -> SURPRISED")
            elif key == ord('4'):
                self.mood = "SLEEPY"
                print("Mood -> SLEEPY")
            elif key == ord('5'):
                self.mood = "ANGRY"
                print("Mood -> ANGRY")
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
                self.trigger_blink()
                print("Head Touched! -> HAPPY")

    def run(self):
        """Main simulation execution loop."""
        while self.robot.step(self.timestep) != -1:
            self.handle_input()
            self.update_animation()
            self.render_face()

if __name__ == "__main__":
    companion = JamiryoCompanion()
    companion.run()
