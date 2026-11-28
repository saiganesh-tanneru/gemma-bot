"""128x64 OLED expression renderer shared by Webots controller and asset scripts."""

import math
import sys
from pathlib import Path
from typing import Optional

_CONTROLLER_DIR = str(Path(__file__).resolve().parents[1])
if _CONTROLLER_DIR not in sys.path:
    sys.path.insert(0, _CONTROLLER_DIR)

from emotion_engine.presets import CLASSIC_MOODS, EMOTIONS, EyeConfig, resolve_mood  # noqa: E402
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
        self.draw_filled_round_rect(cx - w / 2, cy - h / 2, w, h, corner_r, col)

    def draw_filled_round_rect(self, x, y, w, h, r, color):
        """Solid rounded rectangle. The corner radius cannot punch a hole through the fill."""
        r = int(min(max(0, r), w / 2.0, h / 2.0))
        if r <= 1:
            self.draw_filled_box(x, y, w, h, color)
            return
        self.draw_filled_box(x, y + r, w, h - 2 * r, color)
        for i in range(r):
            dist = r - (i + 0.5)
            span = max(0.0, (r * r - dist * dist)) ** 0.5
            inset = r - span
            self.draw_filled_box(x + inset, y + i, w - 2 * inset, 1, color)
            self.draw_filled_box(x + inset, y + h - 1 - i, w - 2 * inset, 1, color)

    def draw_happy_eye(self, cx, cy, w=22):
        """22x26 soft-blue eye with a 4 px highlight at the top-left."""
        ew, eh = 22, 26
        x = cx - ew / 2
        y = cy - eh / 2
        self.draw_filled_round_rect(x, y, ew, eh, 8, self.eye_color)
        self.draw_filled_box(x + 4, y + 3, 4, 4, self.white)

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

    def draw_parametric_eye(
        self,
        cx: float,
        cy: float,
        eye_cfg: EyeConfig,
        blink_progress: float = 0.0,
        color: Optional[int] = None,
    ) -> None:
        """Draws a 12-parameter EyeConfig with rounded corners, sloped lids, and inverse curve."""
        col = color if color is not None else self.eye_color
        cfg = eye_cfg.scaled(self.disp_w, self.disp_h)
        w = max(2.0, cfg.width)
        h = max(3.0, cfg.height * max(0.08, 1.0 - blink_progress))

        ex = cx + cfg.offset_x
        ey = cy + cfg.offset_y
        left_x = ex - w / 2.0
        right_x = ex + w / 2.0

        # Vertical edge offsets from top/bottom eyelid slopes
        dy_top = (h * cfg.slope_top) / 2.0
        dy_bot = (h * cfg.slope_bottom) / 2.0
        y_top_l = ey - h / 2.0 - dy_top
        y_top_r = ey - h / 2.0 + dy_top
        y_bot_l = ey + h / 2.0 - dy_bot
        y_bot_r = ey + h / 2.0 + dy_bot

        top_min = min(y_top_l, y_top_r)
        bot_max = max(y_bot_l, y_bot_r)
        min_y = int(math.ceil(top_min))
        max_y = int(math.floor(bot_max))
        if max_y < min_y:
            max_y = min_y

        rt = max(0.0, min(cfg.radius_top, w / 2.0, h / 2.0))
        rb = max(0.0, min(cfg.radius_bottom, w / 2.0, h / 2.0))

        # Scanline rasterization supports arbitrary slopes & inverse curves on any fillRectangle target
        for y in range(min_y, max_y + 1):
            dist_top = y - top_min
            dist_bot = bot_max - y
            if dist_top < 0.0 or dist_bot < 0.0:
                continue

            y_top_at_x_mid = (y_top_l + y_top_r) * 0.5
            # Horizontal bounds from sloped top/bottom edges
            x0 = left_x
            x1 = right_x
            if cfg.slope_top > 0 and y < max(y_top_l, y_top_r):
                frac = (y - y_top_l) / max(0.5, y_top_r - y_top_l)
                x1 = min(x1, left_x + w * max(0.0, min(1.0, frac)))
            elif cfg.slope_top < 0 and y < max(y_top_l, y_top_r):
                frac = (y - y_top_r) / max(0.5, y_top_l - y_top_r)
                x0 = max(x0, right_x - w * max(0.0, min(1.0, frac)))

            if cfg.slope_bottom > 0 and y > min(y_bot_l, y_bot_r):
                frac = (y_bot_r - y) / max(0.5, y_bot_r - y_bot_l)
                x0 = max(x0, right_x - w * max(0.0, min(1.0, frac)))
            elif cfg.slope_bottom < 0 and y > min(y_bot_l, y_bot_r):
                frac = (y_bot_l - y) / max(0.5, y_bot_l - y_bot_r)
                x1 = min(x1, left_x + w * max(0.0, min(1.0, frac)))

            # Apply rounded top/bottom corners (dist_top & dist_bot guaranteed >= 0)
            inset = 0.0
            if rt > 1.0 and dist_top < rt:
                d = max(0.0, rt - (dist_top + 0.5))
                inset = max(inset, rt - math.sqrt(max(0.0, rt * rt - d * d)))
            if rb > 1.0 and dist_bot < rb:
                d = max(0.0, rb - (dist_bot + 0.5))
                inset = max(inset, rb - math.sqrt(max(0.0, rb * rb - d * d)))

            sx0 = x0 + inset
            sx1 = x1 - inset
            if sx1 > sx0:
                self.draw_filled_box(sx0, y, sx1 - sx0, 1, col)

            # Optional inverse bottom cutout (creates arched "happy/glee" crescent)
            if cfg.inverse_radius_bottom > 1.0 and dist_bot < cfg.inverse_radius_bottom:
                ir = cfg.inverse_radius_bottom
                dy_inv = max(0.0, ir - dist_bot)
                half_cut = math.sqrt(max(0.0, ir * ir - dy_inv * dy_inv))
                cut_w = min(w * 0.7, half_cut * 2.0)
                if cut_w > 1.0 and y > y_top_at_x_mid + 2:
                    self.draw_filled_box(ex - cut_w / 2.0, y, cut_w, 1, self.bg_color)

    def _draw_scaled_box(self, x: float, y: float, w: float, h: float, color: int, sx: float, sy: float) -> None:
        self.draw_filled_box(x * sx, y * sy, max(1.0, w * sx), max(1.0, h * sy), color)

    def _render_special_eyes(
        self,
        mood: str,
        lcx: float,
        rcx: float,
        cy: float,
        sx: float,
        sy: float,
    ) -> bool:
        """Draws special icon eyes (LOVE/STAR/COOL/DIZZY) on scaled displays."""
        if mood == "LOVE":
            for ex in (lcx, rcx):
                self._draw_scaled_box(ex / sx - 7, cy / sy - 4, 6, 6, self.accent_pink, sx, sy)
                self._draw_scaled_box(ex / sx + 1, cy / sy - 4, 6, 6, self.accent_pink, sx, sy)
                self._draw_scaled_box(ex / sx - 9, cy / sy, 18, 5, self.accent_pink, sx, sy)
                self._draw_scaled_box(ex / sx - 7, cy / sy + 5, 14, 4, self.accent_pink, sx, sy)
                self._draw_scaled_box(ex / sx - 4, cy / sy + 9, 8, 4, self.accent_pink, sx, sy)
                self._draw_scaled_box(ex / sx - 1, cy / sy + 13, 2, 2, self.accent_pink, sx, sy)
            self._draw_scaled_box(self.disp_w / (2.0 * sx) - 5, cy / sy + 16, 10, 3, self.accent_pink, sx, sy)
            return True
        if mood == "STAR_EYES":
            r = 12
            for ex in (lcx / sx, rcx / sx):
                for i in range(r):
                    w = r - i
                    self._draw_scaled_box(ex - w, cy / sy - i, w * 2, 1.2, self.accent_yellow, sx, sy)
                    self._draw_scaled_box(ex - w, cy / sy + i, w * 2, 1.2, self.accent_yellow, sx, sy)
                self._draw_scaled_box(ex - 2, cy / sy - 2, 4, 4, self.white, sx, sy)
            self._draw_scaled_box(self.disp_w / (2.0 * sx) - 6, cy / sy + 16, 12, 4, self.mouth_color, sx, sy)
            return True
        if mood == "COOL":
            w, h = self.eye_w, self.eye_h
            top_y = cy / sy - h / 2 + 2
            lens_h = h - 6
            for ex in (lcx / sx, rcx / sx):
                self._draw_scaled_box(ex - w / 2 - 2, top_y, w + 4, lens_h, self.sunglass_frame, sx, sy)
                self._draw_scaled_box(ex - w / 2, top_y + 2, w, lens_h - 4, 0x111111, sx, sy)
                self._draw_scaled_box(ex - w / 4, top_y + 3, 3, lens_h - 6, self.white, sx, sy)
            bridge_start = lcx / sx + w / 2 - 1
            bridge_w = (rcx / sx - w / 2) - bridge_start + 1
            self._draw_scaled_box(bridge_start, top_y + 2, bridge_w, 3, self.sunglass_frame, sx, sy)
            self._draw_scaled_box(self.disp_w / (2.0 * sx) - 4, cy / sy + 17, 10, 3, self.mouth_color, sx, sy)
            return True
        if mood == "DIZZY":
            size, t = 10, 3
            for ex in (lcx / sx, rcx / sx):
                for i in range(-size, size):
                    self._draw_scaled_box(ex + i - t / 2, cy / sy + i - t / 2, t, t, self.eye_color, sx, sy)
                    self._draw_scaled_box(ex + i - t / 2, cy / sy - i - t / 2, t, t, self.eye_color, sx, sy)
            cx_mid = self.disp_w / (2.0 * sx)
            self._draw_scaled_box(cx_mid - 6, cy / sy + 16, 4, 3, self.mouth_color, sx, sy)
            self._draw_scaled_box(cx_mid - 2, cy / sy + 18, 4, 3, self.mouth_color, sx, sy)
            self._draw_scaled_box(cx_mid + 2, cy / sy + 16, 4, 3, self.mouth_color, sx, sy)
            return True
        return False

    def _render_parametric_post_overlays(
        self,
        mood: str,
        lcx: float,
        rcx: float,
        cy: float,
        sx: float,
        sy: float,
        blink_progress: float,
        idle_timer: int,
        speech_timer: int,
    ) -> None:
        """Draws eye highlights, tears, thinking dots, and mouths on top of parametric eyes."""
        cx_mid = self.disp_w / (2.0 * sx)
        if blink_progress < 0.5:
            if mood == "PLEADING":
                for ex in (lcx / sx, rcx / sx):
                    self._draw_scaled_box(ex - 7, cy / sy - 9, 6, 6, self.white, sx, sy)
                    self._draw_scaled_box(ex + 4, cy / sy + 5, 3, 3, self.white, sx, sy)
            elif mood == "NEUTRAL":
                self._draw_scaled_box(lcx / sx - 6, cy / sy - 8, 3.5, 3.5, self.white, sx, sy)
                self._draw_scaled_box(rcx / sx - 6, cy / sy - 8, 3.5, 3.5, self.white, sx, sy)
            elif mood == "CRYING":
                tear_y = cy / sy + 10 + (idle_timer * 2.2) % 20
                for ex in (lcx / sx, rcx / sx):
                    self._draw_scaled_box(ex - 3, min(60, tear_y), 6, 6, self.tear_blue, sx, sy)
                    self._draw_scaled_box(ex - 2, min(56, tear_y - 5), 4, 4, self.white, sx, sy)

        if mood == "THINKING":
            phase = (idle_timer // 15) % 3
            for i in range(3):
                col = self.eye_color if i == phase else self.eye_dim
                self._draw_scaled_box(96 + i * 8, 10, 4, 4, col, sx, sy)

        if speech_timer <= 0:
            if mood == "HAPPY":
                self._draw_scaled_box(cx_mid - 6, cy / sy + 16, 12, 3, self.mouth_color, sx, sy)
                self._draw_scaled_box(cx_mid - 3, cy / sy + 19, 6, 2, self.mouth_color, sx, sy)
            elif mood == "TONGUE":
                self._draw_scaled_box(cx_mid - 6, cy / sy + 15, 12, 3, self.mouth_color, sx, sy)
                self._draw_scaled_box(cx_mid - 3, cy / sy + 17, 7, 6, self.accent_pink, sx, sy)
                self._draw_scaled_box(cx_mid - 1, cy / sy + 22, 3, 2, self.accent_pink, sx, sy)
            elif mood == "SURPRISED":
                self._draw_scaled_box(cx_mid - 4, cy / sy + 15, 8, 8, self.mouth_color, sx, sy)
            elif mood == "NEUTRAL":
                self._draw_scaled_box(54, 46, 4, 2, self.mouth_color, sx, sy)
                self._draw_scaled_box(57, 48, 5, 2, self.mouth_color, sx, sy)
                self._draw_scaled_box(62, 49, 4, 2, self.mouth_color, sx, sy)
                self._draw_scaled_box(66, 48, 5, 2, self.mouth_color, sx, sy)
                self._draw_scaled_box(70, 46, 4, 2, self.mouth_color, sx, sy)

    def render(
        self,
        mood: str,
        gaze_x: float = 0.0,
        gaze_y: float = 0.0,
        blink_progress: float = 0.0,
        idle_timer: int = 0,
        speech_timer: int = 0,
        left_eye: Optional[EyeConfig] = None,
        right_eye: Optional[EyeConfig] = None,
        is_transitioning: bool = False,
    ) -> None:
        """Renders the OLED facial expression (classic pixel-exact or Emotion Engine parametric)."""
        if not self.display:
            return

        use_parametric = (
            is_transitioning
            or mood not in CLASSIC_MOODS
            or self.disp_w != 128
            or self.disp_h != 64
        )
        if use_parametric:
            if left_eye is None:
                spec = EMOTIONS.get(resolve_mood(mood))
                if spec is not None:
                    left_eye = spec.eye_left
                    right_eye = spec.right_eye
            if left_eye is not None:
                self.display.setOpacity(1.0)
                self.display.setColor(self.bg_color)
                self.display.fillRectangle(0, 0, self.disp_w, self.disp_h)

                sx = self.disp_w / 128.0
                sy = self.disp_h / 64.0
                dx = gaze_x * 8.0 * sx
                dy = gaze_y * 6.0 * sy
                lcx = self.left_cx * sx + dx
                rcx = self.right_cx * sx + dx
                cy = self.base_cy * sy + dy

                r_eye = right_eye if right_eye is not None else left_eye
                special_eyes = False
                if not is_transitioning and (blink_progress <= 0.85 or mood == "COOL"):
                    special_eyes = self._render_special_eyes(
                        mood=mood,
                        lcx=lcx,
                        rcx=rcx,
                        cy=cy,
                        sx=sx,
                        sy=sy,
                    )
                if not special_eyes:
                    self.draw_parametric_eye(lcx, cy, left_eye, blink_progress=blink_progress)
                    self.draw_parametric_eye(rcx, cy, r_eye, blink_progress=blink_progress)
                    self._render_parametric_post_overlays(
                        mood=mood,
                        lcx=lcx,
                        rcx=rcx,
                        cy=cy,
                        sx=sx,
                        sy=sy,
                        blink_progress=blink_progress,
                        idle_timer=idle_timer,
                        speech_timer=speech_timer,
                    )

                if speech_timer > 0:
                    mouth_phase = speech_timer * 0.4
                    mouth_w = (12 + int(abs(math.cos(mouth_phase * 0.7)) * 8)) * sx
                    mouth_h = (4 + int(abs(math.sin(mouth_phase)) * 8)) * sy
                    self.draw_filled_box(
                        self.disp_w / 2 - mouth_w / 2,
                        cy + 16 * sy - mouth_h / 2,
                        mouth_w,
                        mouth_h,
                        self.mouth_color,
                    )
                    bar_w = (int(abs(math.sin(mouth_phase * 0.9)) * 24) + 10) * sx
                    self.draw_filled_box(self.disp_w / 2 - bar_w / 2, 59 * sy, bar_w, max(2, 2 * sy), self.eye_color)
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
            self.draw_happy_eye(38, 26)
            self.draw_happy_eye(90, 26)
            self.draw_filled_box(54, 46, 4, 2, self.mouth_color)
            self.draw_filled_box(57, 48, 5, 2, self.mouth_color)
            self.draw_filled_box(62, 49, 4, 2, self.mouth_color)
            self.draw_filled_box(66, 48, 5, 2, self.mouth_color)
            self.draw_filled_box(70, 46, 4, 2, self.mouth_color)

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
