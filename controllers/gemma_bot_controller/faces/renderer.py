"""128x64 OLED expression renderer shared by Webots controller and asset scripts."""

import math
from faces.themes import SCREEN_THEMES


class WebotsDisplayTarget:
    """Adapts a Webots Display device to the FaceRenderer drawing target interface."""

    def __init__(self, display):
        self._display = display

    def setOpacity(self, alpha: float) -> None:
        self._display.setOpacity(alpha)

    def setColor(self, color: int) -> None:
        self._display.setColor(color)

    def fillRectangle(self, x: int, y: int, w: int, h: int) -> None:
        self._display.fillRectangle(x, y, w, h)

    def drawText(self, text: str, x: int, y: int) -> None:
        self._display.drawText(text, x, y)


class CanvasTarget:
    """Adapts an RGBA Canvas (with fill_rect and draw_text) to FaceRenderer."""

    def __init__(self, canvas):
        self._canvas = canvas
        self._rgb = (0, 0, 0)

    def setOpacity(self, alpha: float) -> None:
        pass

    def setColor(self, color: int) -> None:
        self._rgb = ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF)

    def fillRectangle(self, x: int, y: int, w: int, h: int) -> None:
        self._canvas.fill_rect(x, y, w, h, self._rgb[0], self._rgb[1], self._rgb[2])

    def drawText(self, text: str, x: int, y: int) -> None:
        self._canvas.draw_text(text, x, y, self._rgb[0], self._rgb[1], self._rgb[2], scale=1)


class FaceRenderer:
    """Renders Gemma-Bot's 15 OLED expressions, blinking, gaze, and lip-sync."""

    def __init__(self, display_target=None, theme: str = "CYAN", disp_w: int = 128, disp_h: int = 64):
        self.display = display_target
        self.disp_w = disp_w
        self.disp_h = disp_h
        self.left_cx = 38
        self.right_cx = 90
        self.base_cy = 32
        self.eye_w = 28
        self.eye_h = 34
        self.accent_pink = 0xFF4488
        self.accent_yellow = 0xFFDD00
        self.tear_blue = 0x44AAFF
        self.white = 0xFFFFFF
        self.current_theme = "CYAN"
        self.apply_theme(theme)

    def apply_theme(self, theme: str) -> bool:
        t = str(theme).upper().strip()
        if t not in SCREEN_THEMES:
            return False
        cfg = SCREEN_THEMES[t]
        self.current_theme = t
        self.bg_color = cfg["bg_color"]
        self.eye_color = cfg["eye_color"]
        self.eye_dim = cfg["eye_dim"]
        self.mouth_color = cfg["mouth_color"]
        self.sunglass_frame = cfg["sunglass_frame"]
        return True

    def draw_filled_box(self, x, y, w, h, color):
        """Draws a clamped filled box on the target display."""
        x0 = max(0, min(self.disp_w - 1, int(x)))
        y0 = max(0, min(self.disp_h - 1, int(y)))
        x1 = max(0, min(self.disp_w, int(x + w)))
        y1 = max(0, min(self.disp_h, int(y + h)))
        if x1 > x0 and y1 > y0:
            self.display.setColor(color)
            self.display.fillRectangle(x0, y0, x1 - x0, y1 - y0)

    def draw_rounded_eye(self, cx, cy, w, h, corner_r=5, color=None):
        col = color if color is not None else self.eye_color
        x = cx - w / 2
        y = cy - h / 2
        self.draw_filled_box(x + corner_r, y, w - 2 * corner_r, h, col)
        self.draw_filled_box(x, y + corner_r, corner_r, h - 2 * corner_r, col)
        self.draw_filled_box(x + w - corner_r, y + corner_r, corner_r, h - 2 * corner_r, col)

    def draw_happy_eye(self, cx, cy, w):
        """Large soft oval with a white highlight, matching the review-plan face."""
        h = max(self.eye_h, w * 1.05)
        self.draw_rounded_eye(cx, cy, w, h, corner_r=min(w, h) * 0.46)
        dot = max(3, int(w * 0.16))
        self.draw_filled_box(cx - w * 0.28, cy - h * 0.22, dot, dot, self.white)

    def draw_sleepy_eye(self, cx, cy, w):
        x = cx - w / 2
        self.draw_filled_box(x, cy + 2, w, 5, self.eye_color)
        self.draw_filled_box(x + 2, cy + 5, w - 4, 3, self.eye_color)

    def draw_angry_eye(self, cx, cy, w, h, is_left=True):
        x = cx - w / 2
        y = cy - h / 2
        self.draw_filled_box(x, y, w, h, self.eye_color)
        if is_left:
            self.draw_filled_box(x + w / 2, y, w / 2, h * 0.45, self.bg_color)
        else:
            self.draw_filled_box(x, y, w / 2, h * 0.45, self.bg_color)

    def draw_heart(self, cx, cy):
        self.draw_filled_box(cx - 7, cy - 4, 6, 6, self.accent_pink)
        self.draw_filled_box(cx + 1, cy - 4, 6, 6, self.accent_pink)
        self.draw_filled_box(cx - 9, cy, 18, 5, self.accent_pink)
        self.draw_filled_box(cx - 7, cy + 5, 14, 4, self.accent_pink)
        self.draw_filled_box(cx - 4, cy + 9, 8, 4, self.accent_pink)
        self.draw_filled_box(cx - 1, cy + 13, 2, 2, self.accent_pink)

    def draw_star(self, cx, cy, r=11):
        for i in range(r):
            w = r - i
            self.draw_filled_box(cx - w, cy - i, w * 2, 1, self.accent_yellow)
            self.draw_filled_box(cx - w, cy + i, w * 2, 1, self.accent_yellow)
        self.draw_filled_box(cx - 2, cy - 2, 4, 4, self.white)

    def draw_sunglasses(self, lcx, rcx, cy, w, h):
        top_y = cy - h / 2 + 2
        lens_h = h - 6
        self.draw_filled_box(lcx - w / 2 - 2, top_y, w + 4, lens_h, self.sunglass_frame)
        self.draw_filled_box(lcx - w / 2, top_y + 2, w, lens_h - 4, 0x111111)
        self.draw_filled_box(rcx - w / 2 - 2, top_y, w + 4, lens_h, self.sunglass_frame)
        self.draw_filled_box(rcx - w / 2, top_y + 2, w, lens_h - 4, 0x111111)
        bridge_start = lcx + w / 2 - 1
        bridge_w = (rcx - w / 2) - bridge_start + 1
        self.draw_filled_box(bridge_start, top_y + 2, bridge_w, 3, self.sunglass_frame)
        self.draw_filled_box(lcx - w / 4, top_y + 3, 3, lens_h - 6, self.white)
        self.draw_filled_box(rcx - w / 4, top_y + 3, 3, lens_h - 6, self.white)

    def draw_pleading_eye(self, cx, cy, w, h):
        self.draw_rounded_eye(cx, cy, w + 2, h + 2, corner_r=8, color=self.eye_color)
        self.draw_filled_box(cx - w / 4 - 2, cy - h / 4 - 2, 8, 8, self.white)
        self.draw_filled_box(cx + w / 6, cy + h / 6, 4, 4, self.white)

    def draw_cross_eye(self, cx, cy, size=10):
        t = 3
        for i in range(-size, size):
            self.draw_filled_box(cx + i - t // 2, cy + i - t // 2, t, t, self.eye_color)
            self.draw_filled_box(cx + i - t // 2, cy - i - t // 2, t, t, self.eye_color)

    def draw_crying_eye(self, cx, cy, w, h, is_left=True, idle_timer=0):
        y = cy - h / 2
        self.draw_filled_box(cx - w / 2, y + 5, w, h - 8, self.eye_color)
        if is_left:
            self.draw_filled_box(cx - w / 2, y, w / 2, 7, self.bg_color)
        else:
            self.draw_filled_box(cx, y, w / 2, 7, self.bg_color)
        tear_y = int(cy + 10 + (idle_timer * 2.2) % 20)
        self.draw_filled_box(cx - 3, min(self.disp_h - 4, tear_y), 6, 6, self.tear_blue)
        self.draw_filled_box(cx - 2, min(self.disp_h - 8, tear_y - 5), 4, 4, self.white)

    def draw_tongue_mouth(self, cx, cy):
        self.draw_filled_box(cx - 6, cy + 15, 12, 3, self.mouth_color)
        self.draw_filled_box(cx - 3, cy + 17, 7, 6, self.accent_pink)
        self.draw_filled_box(cx - 1, cy + 22, 3, 2, self.accent_pink)

    def render(
        self,
        mood: str,
        gaze_x: float = 0.0,
        gaze_y: float = 0.0,
        blink_progress: float = 0.0,
        idle_timer: int = 0,
        speech_timer: int = 0,
    ) -> None:
        """Renders the complete OLED facial expression and eye gaze."""
        if not self.display:
            return

        self.display.setOpacity(1.0)
        self.display.setColor(self.bg_color)
        self.display.fillRectangle(0, 0, self.disp_w, self.disp_h)

        dx = gaze_x * 8.0
        dy = gaze_y * 6.0
        lcx = self.left_cx + dx
        rcx = self.right_cx + dx
        cy = self.base_cy + dy

        effective_h = self.eye_h * (1.0 - blink_progress)
        if effective_h < 3:
            effective_h = 3

        if blink_progress > 0.85 and mood != "COOL":
            self.draw_filled_box(lcx - self.eye_w / 2, cy, self.eye_w, 4, self.eye_color)
            self.draw_filled_box(rcx - self.eye_w / 2, cy, self.eye_w, 4, self.eye_color)
        elif mood == "HAPPY":
            self.draw_happy_eye(lcx, cy, self.eye_w)
            self.draw_happy_eye(rcx, cy, self.eye_w)
            self.draw_filled_box(self.disp_w / 2 - 6, cy + 16, 12, 3, self.mouth_color)
            self.draw_filled_box(self.disp_w / 2 - 3, cy + 19, 6, 2, self.mouth_color)
        elif mood == "LOVE":
            self.draw_heart(lcx, cy)
            self.draw_heart(rcx, cy)
            self.draw_filled_box(self.disp_w / 2 - 5, cy + 16, 10, 3, self.accent_pink)
        elif mood == "WINK":
            self.draw_rounded_eye(lcx, cy, self.eye_w, effective_h, corner_r=6)
            self.draw_happy_eye(rcx, cy, self.eye_w)
            self.draw_filled_box(self.disp_w / 2 - 5, cy + 16, 10, 3, self.mouth_color)
            self.draw_filled_box(self.disp_w / 2 + 3, cy + 14, 3, 3, self.mouth_color)
        elif mood == "COOL":
            self.draw_sunglasses(lcx, rcx, cy, self.eye_w, self.eye_h)
            self.draw_filled_box(self.disp_w / 2 - 4, cy + 17, 10, 3, self.mouth_color)
            self.draw_filled_box(self.disp_w / 2 + 5, cy + 15, 3, 3, self.mouth_color)
        elif mood == "STAR_EYES":
            self.draw_star(lcx, cy, r=12)
            self.draw_star(rcx, cy, r=12)
            self.draw_filled_box(self.disp_w / 2 - 6, cy + 16, 12, 4, self.mouth_color)
            self.draw_filled_box(self.disp_w / 2 - 4, cy + 20, 8, 2, self.mouth_color)
        elif mood == "PLEADING":
            self.draw_pleading_eye(lcx, cy, self.eye_w, effective_h)
            self.draw_pleading_eye(rcx, cy, self.eye_w, effective_h)
            tremble = 1 if (idle_timer // 8) % 2 == 0 else 0
            self.draw_filled_box(self.disp_w / 2 - 4, cy + 17 + tremble, 8, 3, self.mouth_color)
        elif mood == "CRYING":
            self.draw_crying_eye(lcx, cy, self.eye_w, effective_h, is_left=True, idle_timer=idle_timer)
            self.draw_crying_eye(rcx, cy, self.eye_w, effective_h, is_left=False, idle_timer=idle_timer)
            self.draw_filled_box(self.disp_w / 2 - 5, cy + 18, 10, 3, self.tear_blue)
            self.draw_filled_box(self.disp_w / 2 - 5, cy + 20, 3, 2, self.tear_blue)
            self.draw_filled_box(self.disp_w / 2 + 2, cy + 20, 3, 2, self.tear_blue)
        elif mood == "TONGUE":
            self.draw_happy_eye(lcx, cy, self.eye_w)
            self.draw_happy_eye(rcx, cy, self.eye_w)
            self.draw_tongue_mouth(self.disp_w / 2, cy)
        elif mood == "SMIRK":
            self.draw_rounded_eye(lcx, cy - 2, self.eye_w, effective_h, corner_r=6)
            self.draw_sleepy_eye(rcx, cy + 3, self.eye_w)
            self.draw_filled_box(self.disp_w / 2 - 3, cy + 16, 8, 3, self.mouth_color)
            self.draw_filled_box(self.disp_w / 2 + 4, cy + 14, 3, 3, self.mouth_color)
        elif mood == "DIZZY":
            self.draw_cross_eye(lcx, cy, size=10)
            self.draw_cross_eye(rcx, cy, size=10)
            self.draw_filled_box(self.disp_w / 2 - 6, cy + 16, 4, 3, self.mouth_color)
            self.draw_filled_box(self.disp_w / 2 - 2, cy + 18, 4, 3, self.mouth_color)
            self.draw_filled_box(self.disp_w / 2 + 2, cy + 16, 4, 3, self.mouth_color)
        elif mood == "THINKING":
            self.draw_rounded_eye(lcx + 4, cy - 6, self.eye_w - 2, effective_h - 2, corner_r=5)
            self.draw_rounded_eye(rcx + 4, cy - 6, self.eye_w - 2, effective_h - 2, corner_r=5)
            phase = (idle_timer // 15) % 3
            for i in range(3):
                col = self.eye_color if i == phase else self.eye_dim
                self.draw_filled_box(96 + i * 8, 10, 4, 4, col)
        elif mood == "SLEEPY":
            self.draw_sleepy_eye(lcx, cy + 4, self.eye_w)
            self.draw_sleepy_eye(rcx, cy + 4, self.eye_w)
            if (idle_timer // 30) % 2 == 0:
                self.display.setColor(self.eye_dim)
                self.display.drawText("z", 108, 14)
                self.display.drawText("Z", 114, 8)
        elif mood == "SURPRISED":
            w = self.eye_w + 4
            h = effective_h + 6
            self.draw_rounded_eye(lcx, cy - 2, w, h, corner_r=8)
            self.draw_rounded_eye(rcx, cy - 2, w, h, corner_r=8)
            self.draw_filled_box(self.disp_w / 2 - 4, cy + 15, 8, 8, self.mouth_color)
        elif mood == "ANGRY":
            self.draw_angry_eye(lcx, cy, self.eye_w, effective_h, is_left=True)
            self.draw_angry_eye(rcx, cy, self.eye_w, effective_h, is_left=False)
            self.draw_filled_box(self.disp_w / 2 - 5, cy + 17, 10, 3, self.mouth_color)
        else:
            self.draw_happy_eye(lcx, cy, self.eye_w)
            self.draw_happy_eye(rcx, cy, self.eye_w)
            self.draw_filled_box(self.disp_w / 2 - 8, cy + 16, 3, 2, self.mouth_color)
            self.draw_filled_box(self.disp_w / 2 - 6, cy + 18, 4, 2, self.mouth_color)
            self.draw_filled_box(self.disp_w / 2 - 2, cy + 19, 4, 2, self.mouth_color)
            self.draw_filled_box(self.disp_w / 2 + 2, cy + 18, 4, 2, self.mouth_color)
            self.draw_filled_box(self.disp_w / 2 + 5, cy + 16, 3, 2, self.mouth_color)

        if speech_timer > 0:
            mouth_phase = speech_timer * 0.4
            mouth_w = 12 + int(abs(math.cos(mouth_phase * 0.7)) * 8)
            mouth_h = 4 + int(abs(math.sin(mouth_phase)) * 8)
            self.draw_filled_box(
                self.disp_w / 2 - mouth_w / 2,
                cy + 16 - mouth_h / 2,
                mouth_w,
                mouth_h,
                self.mouth_color,
            )
            bar_w = int(abs(math.sin(mouth_phase * 0.9)) * 24) + 10
            self.draw_filled_box(self.disp_w / 2 - bar_w / 2, 59, bar_w, 2, self.eye_color)
