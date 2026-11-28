"""Chintu 128x64 -> 410x502 uniform-scaled AMOLED face renderer.

Design space: 128x64.
- Eyes: filled rounded shapes, max 26x22 px, centres at (40, 28) and (88, 28).
- Yawn mouth: max 36x28 px oval with dark tongue notch at bottom past half-open.
Target 410x502 AMOLED: uniform scale = 3.203125 (~3.2), rendering a 410x205 band
centred vertically on a pure #000000 black background.
Never stretched; bright pixels only.
"""

from dataclasses import dataclass
import math
from typing import Dict, Optional, Protocol, Tuple


DESIGN_W = 128
DESIGN_H = 64
LEFT_EYE_CX = 40.0
RIGHT_EYE_CX = 88.0
EYE_CY = 28.0
EYE_MAX_W = 26.0
EYE_MAX_H = 22.0
YAWN_MOUTH_MAX_W = 36.0
YAWN_MOUTH_MAX_H = 28.0

# Colors (pure black background, bright AMOLED pixels)
COLOR_BG = 0x000000
COLOR_EYE = 0x8EC9DB
COLOR_EYE_BRIGHT = 0xA8ECFF
COLOR_EYE_DIM = 0x3D6878
COLOR_WHITE = 0xFFFFFF
COLOR_MOUTH = 0x8EC9DB
COLOR_TONGUE_DARK = 0x101820
COLOR_HEART = 0xFF5C8A
COLOR_SPARKLE = 0xFFFFFF
COLOR_GOLD = 0xFFD95A
COLOR_CHARGE = 0x4CE894
COLOR_TEAR = 0x44AAFF
COLOR_CLOUD = 0x6D8FA3
COLOR_CLOUD_BRIGHT = 0xA8C8DC
COLOR_ORANGE = 0xFFA94D
COLOR_LEAF = 0xFF8A5B


_PIXEL_FONT_3X5: Dict[str, Tuple[str, ...]] = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "001", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "-": ("000", "000", "111", "000", "000"),
    "C": ("111", "100", "100", "100", "111"),
    "F": ("111", "100", "110", "100", "100"),
    " ": ("000", "000", "000", "000", "000"),
}


class DisplayTarget(Protocol):
    def setOpacity(self, alpha: float) -> None: ...
    def setColor(self, color: int) -> None: ...
    def fillRectangle(self, x: int, y: int, w: int, h: int) -> None: ...
    def drawText(self, text: str, x: int, y: int) -> None: ...


class WebotsDisplayTarget:
    """Adapts a Webots Display device."""

    def __init__(self, display) -> None:
        self._display = display

    def setOpacity(self, alpha: float) -> None:
        if hasattr(self._display, "setOpacity"):
            self._display.setOpacity(alpha)

    def setColor(self, color: int) -> None:
        self._display.setColor(color)

    def fillRectangle(self, x: int, y: int, w: int, h: int) -> None:
        self._display.fillRectangle(int(x), int(y), int(w), int(h))

    def drawText(self, text: str, x: int, y: int) -> None:
        self._display.drawText(str(text), int(x), int(y))


class RecordingDisplayTarget:
    """In-memory target for verification, tests, and frame-for-frame assertions."""

    def __init__(self) -> None:
        self.opacity: float = 1.0
        self.color: int = 0
        self.ops: list = []

    def setOpacity(self, alpha: float) -> None:
        self.opacity = float(alpha)

    def setColor(self, color: int) -> None:
        self.color = int(color)

    def fillRectangle(self, x: int, y: int, w: int, h: int) -> None:
        self.ops.append(("rect", int(x), int(y), int(w), int(h), self.color))

    def drawText(self, text: str, x: int, y: int) -> None:
        self.ops.append(("text", str(text), int(x), int(y), self.color))

    def clear(self) -> None:
        self.ops.clear()


@dataclass
class FaceFrameState:
    """Parameterised target state written by the state machine and owned by the render engine."""

    face_mode: str = "content_idle"  # sleep | stir | flutter | yawn | look | found_you | content_idle
    mood: str = "NEUTRAL"
    left_eye_open: float = 1.0
    right_eye_open: float = 1.0
    eye_scale: float = 1.0
    face_scale: float = 1.0
    gaze_x: float = 0.0  # -1..+1
    gaze_y: float = 0.0  # -1..+1
    mouth_open: float = 0.0  # 0..1 for yawn bloom
    mouth_wobble: float = 0.0  # +/-0.04 scale modulation
    talk_open: float = 0.0  # 0..1 syllable lip-sync mouth openness
    talk_width: float = 0.5  # 0..1 vowel width ('oo' narrow vs 'ee' wide)
    face_bob_x: float = 0.0
    face_bob_y: float = 0.0  # breathing (+/-1 px) or yawn bob (+/-1.6 px)
    smile_amount: float = 0.35  # 0 = tiny dot/line, 1 = wide happy smile
    happy_arcs: bool = False
    sparkles: float = 0.0  # 0..1 intensity
    heart_alpha: float = 0.0  # 0..1 top-right pixel heart
    sweat_alpha: float = 0.0  # 0..1 anxious pixel sweat drop
    alert_alpha: float = 0.0  # 0..1 startled '!' pixel glyph
    bell_alpha: float = 0.0  # 0..1 ringing alarm bell glyph
    zzz_phase: float = -1.0  # 0..1 over 3s loop when sleeping, < 0 when off
    is_charging: bool = False
    brightness: float = 1.0  # 0.40 in sleep, 1.00 awake
    dizzy_phase: float = 0.0
    blink_progress: float = 0.0
    weather_condition: str = ""  # "" | sunny | cloudy | rainy | storm | snowy | windy | starry
    weather_intensity: float = 0.0  # 0..1
    weather_phase: float = 0.0  # continuous seconds for particles
    weather_flash: float = 0.0  # 0..1 lightning flash intensity
    weather_bolt: int = 0  # 0, 1, 2 alternating bolt positions during storm
    weather_temp_label: str = ""  # e.g. "22C" or "72F"
    umbrella_alpha: float = 0.0  # 0..1 overhead umbrella open progress during rain
    blanket_alpha: float = 0.0  # 0..1 cozy pull-up blanket during starry night
    jacket_alpha: float = 0.0  # 0..1 zip-up winter puffer jacket during snow


def compute_uniform_band(disp_w: int, disp_h: int) -> Tuple[float, float, float]:
    """Returns (scale, band_x0, band_y0) preserving 128x64 aspect ratio without stretching."""
    scale = min(disp_w / float(DESIGN_W), disp_h / float(DESIGN_H))
    band_w = DESIGN_W * scale
    band_h = DESIGN_H * scale
    return scale, (disp_w - band_w) * 0.5, (disp_h - band_h) * 0.5


def _scale_color(color: int, brightness: float) -> int:
    b = max(0.0, min(1.0, float(brightness)))
    r = int(((color >> 16) & 0xFF) * b)
    g = int(((color >> 8) & 0xFF) * b)
    bl = int((color & 0xFF) * b)
    return (r << 16) | (g << 8) | bl


class FaceRenderer:
    """Draws Chintu's 7 wake/sleep states and 15 moods in 128x64 scaled uniformly to 410x502."""

    def __init__(self, target: Optional[DisplayTarget] = None, disp_w: int = 410, disp_h: int = 502) -> None:
        self.target = target
        self.disp_w = int(disp_w)
        self.disp_h = int(disp_h)
        self.scale, self.band_x, self.band_y = compute_uniform_band(self.disp_w, self.disp_h)

    def to_screen(self, x_design: float, y_design: float) -> Tuple[float, float]:
        return (self.band_x + x_design * self.scale, self.band_y + y_design * self.scale)

    def _rect(self, x: float, y: float, w: float, h: float, color: int, brightness: float = 1.0) -> None:
        if self.target is None or w <= 0 or h <= 0:
            return
        sx, sy = self.to_screen(x, y)
        sw = w * self.scale
        sh = h * self.scale
        x0 = max(0, min(self.disp_w - 1, int(round(sx))))
        y0 = max(0, min(self.disp_h - 1, int(round(sy))))
        x1 = max(0, min(self.disp_w, int(round(sx + sw))))
        y1 = max(0, min(self.disp_h, int(round(sy + sh))))
        if x1 > x0 and y1 > y0:
            self.target.setColor(_scale_color(color, brightness))
            self.target.fillRectangle(x0, y0, x1 - x0, y1 - y0)

    def _screen_rect(self, x: float, y: float, w: float, h: float, color: int, brightness: float = 1.0) -> None:
        if self.target is None or w <= 0 or h <= 0:
            return
        x0 = max(0, min(self.disp_w - 1, int(round(x))))
        y0 = max(0, min(self.disp_h - 1, int(round(y))))
        x1 = max(0, min(self.disp_w, int(round(x + w))))
        y1 = max(0, min(self.disp_h, int(round(y + h))))
        if x1 > x0 and y1 > y0:
            self.target.setColor(_scale_color(color, brightness))
            self.target.fillRectangle(x0, y0, x1 - x0, y1 - y0)

    def _draw_rounded_rect(
        self, x: float, y: float, w: float, h: float, r: float, color: int, brightness: float = 1.0
    ) -> None:
        """Scanline rounded rectangle in design space mapped cleanly to screen pixels."""
        if self.target is None or w <= 0 or h <= 0:
            return
        sx, sy = self.to_screen(x, y)
        sw = w * self.scale
        sh = h * self.scale
        sr = max(0.0, min(r * self.scale, sw * 0.5, sh * 0.5))
        y_start = int(math.floor(sy))
        y_end = int(math.ceil(sy + sh))
        col = _scale_color(color, brightness)
        self.target.setColor(col)

        for py in range(y_start, y_end):
            if py < 0 or py >= self.disp_h:
                continue
            dist_top = (py + 0.5) - sy
            dist_bot = (sy + sh) - (py + 0.5)
            inset = 0.0
            if sr > 0.5:
                if dist_top < sr:
                    d = sr - max(0.0, dist_top)
                    inset = max(inset, sr - math.sqrt(max(0.0, sr * sr - d * d)))
                if dist_bot < sr:
                    d = sr - max(0.0, dist_bot)
                    inset = max(inset, sr - math.sqrt(max(0.0, sr * sr - d * d)))
            rx0 = max(0, int(round(sx + inset)))
            rx1 = min(self.disp_w, int(round(sx + sw - inset)))
            if rx1 > rx0:
                self.target.fillRectangle(rx0, py, rx1 - rx0, 1)

    def _draw_oval(
        self, cx: float, cy: float, w: float, h: float, color: int, brightness: float = 1.0
    ) -> None:
        """Filled ellipse in design space mapped cleanly to screen scanlines."""
        if self.target is None or w <= 0.5 or h <= 0.5:
            return
        scx, scy = self.to_screen(cx, cy)
        rx = (w * 0.5) * self.scale
        ry = (h * 0.5) * self.scale
        y_start = int(math.floor(scy - ry))
        y_end = int(math.ceil(scy + ry))
        self.target.setColor(_scale_color(color, brightness))
        for py in range(y_start, y_end + 1):
            if py < 0 or py >= self.disp_h:
                continue
            dy = ((py + 0.5) - scy) / max(0.5, ry)
            if abs(dy) > 1.0:
                continue
            dx = rx * math.sqrt(max(0.0, 1.0 - dy * dy))
            px0 = max(0, int(round(scx - dx)))
            px1 = min(self.disp_w, int(round(scx + dx)))
            if px1 > px0:
                self.target.fillRectangle(px0, py, px1 - px0, 1)

    def _draw_closed_curve_eye(self, cx: float, cy: float, w: float, brightness: float) -> None:
        """Sleep closed-curve eye (downward gentle U curve)."""
        hw = w * 0.46
        steps = 10
        for i in range(-steps, steps + 1):
            u = i / float(steps)
            px = cx + u * hw
            py = cy + 2.5 - (u * u) * 3.0
            self._rect(px - 1.2, py - 1.0, 2.4, 2.2, COLOR_EYE, brightness)

    def _draw_happy_arc_eye(self, cx: float, cy: float, w: float, brightness: float) -> None:
        """Upward happy arc eye (inverted U)."""
        hw = w * 0.46
        steps = 12
        for i in range(-steps, steps + 1):
            u = i / float(steps)
            px = cx + u * hw
            py = cy - 4.0 + (u * u) * 7.5
            self._rect(px - 1.4, py - 1.2, 2.8, 2.6, COLOR_EYE_BRIGHT, brightness)

    def _draw_pixel_z(self, x: float, y: float, size: float, brightness: float) -> None:
        """Crisp pixel 'Z' glyph."""
        t = max(1.0, size * 0.22)
        self._rect(x, y, size, t, COLOR_EYE_DIM, brightness)
        for i in range(5):
            u = i / 4.0
            self._rect(x + (1.0 - u) * (size - t), y + u * (size - t), t, t, COLOR_EYE_DIM, brightness)
        self._rect(x, y + size - t, size, t, COLOR_EYE_DIM, brightness)

    def _draw_pixel_heart(self, cx: float, cy: float, alpha: float, brightness: float) -> None:
        """Top-right pixel heart glyph for Found You / Head Pat."""
        if alpha <= 0.05:
            return
        b = brightness * alpha
        self._rect(cx - 4.0, cy - 2.5, 3.2, 3.0, COLOR_HEART, b)
        self._rect(cx + 0.8, cy - 2.5, 3.2, 3.0, COLOR_HEART, b)
        self._rect(cx - 5.0, cy - 0.5, 10.0, 2.8, COLOR_HEART, b)
        self._rect(cx - 3.8, cy + 2.0, 7.6, 2.2, COLOR_HEART, b)
        self._rect(cx - 2.2, cy + 4.0, 4.4, 1.8, COLOR_HEART, b)
        self._rect(cx - 0.9, cy + 5.6, 1.8, 1.3, COLOR_HEART, b)

    def _draw_pixel_sweat_drop(self, cx: float, cy: float, alpha: float, phase: float, brightness: float) -> None:
        """Anxious pixel sweat drop sliding gently down upper-right temple."""
        if alpha <= 0.05:
            return
        b = brightness * alpha
        drop_y = cy + (phase * 3.0) % 4.0
        self._rect(cx - 1.0, drop_y - 3.0, 2.0, 2.2, COLOR_TEAR, b)
        self._rect(cx - 2.0, drop_y - 1.0, 4.0, 3.0, COLOR_TEAR, b)
        self._rect(cx - 1.4, drop_y + 2.0, 2.8, 1.4, COLOR_TEAR, b)
        self._rect(cx - 0.8, drop_y - 0.5, 1.2, 1.4, COLOR_WHITE, b)

    def _draw_pixel_alert(self, cx: float, cy: float, alpha: float, brightness: float) -> None:
        """Startled pixel exclamation '!' at top-right."""
        if alpha <= 0.05:
            return
        b = brightness * alpha
        self._rect(cx - 1.4, cy - 6.0, 2.8, 7.0, COLOR_GOLD, b)
        self._rect(cx - 1.4, cy + 2.6, 2.8, 2.6, COLOR_GOLD, b)

    def _draw_pixel_bell(self, cx: float, cy: float, alpha: float, phase: float, brightness: float) -> None:
        """Animated ringing alarm bell glyph with sound-wave ticks."""
        if alpha <= 0.05:
            return
        b = brightness * alpha
        shake = math.sin(phase * 38.0) * 1.4
        bx = cx + shake
        # Bell dome + brim + clapper
        self._rect(bx - 1.5, cy - 5.5, 3.0, 1.5, COLOR_GOLD, b)
        self._rect(bx - 3.5, cy - 4.0, 7.0, 4.0, COLOR_GOLD, b)
        self._rect(bx - 5.0, cy, 10.0, 2.0, COLOR_GOLD, b)
        self._rect(bx - 1.2 + shake * 0.5, cy + 2.2, 2.4, 2.0, COLOR_WHITE, b)
        # Ringing sound-wave arcs
        if int(phase * 12.0) % 2 == 0:
            self._rect(bx - 7.5, cy - 3.0, 1.4, 3.5, COLOR_EYE_BRIGHT, b)
            self._rect(bx + 6.1, cy - 3.0, 1.4, 3.5, COLOR_EYE_BRIGHT, b)

    def _draw_charging_glyph(self, brightness: float) -> None:
        """One tiny charging glyph in the top-right corner of the 410x502 display."""
        # Positioned neatly in the top-right corner outside the 410x205 band (or top-right on 128x64)
        if self.disp_h >= 300:
            gx = self.disp_w - 38.0
            gy = 18.0
            self._screen_rect(gx, gy, 22, 12, COLOR_CHARGE, brightness)
            self._screen_rect(gx + 2, gy + 2, 18, 8, COLOR_BG, 1.0)
            self._screen_rect(gx + 22, gy + 3, 3, 6, COLOR_CHARGE, brightness)
            # Tiny lightning bolt inside
            self._screen_rect(gx + 9, gy + 3, 4, 3, COLOR_CHARGE, brightness)
            self._screen_rect(gx + 7, gy + 5, 7, 2, COLOR_CHARGE, brightness)
            self._screen_rect(gx + 10, gy + 7, 4, 3, COLOR_CHARGE, brightness)
        else:
            self._rect(116, 4, 8, 5, COLOR_CHARGE, brightness)
            self._rect(124, 5, 2, 3, COLOR_CHARGE, brightness)

    def _draw_pixel_cloud(self, cx: float, cy: float, scale_c: float, color: int, brightness: float) -> None:
        self._rect(cx - 5.0 * scale_c, cy - 1.5 * scale_c, 10.0 * scale_c, 3.0 * scale_c, color, brightness)
        self._rect(cx - 3.5 * scale_c, cy - 3.2 * scale_c, 4.5 * scale_c, 2.5 * scale_c, color, brightness)
        self._rect(cx + 0.2 * scale_c, cy - 2.6 * scale_c, 3.5 * scale_c, 2.0 * scale_c, color, brightness)

    def _draw_pixel_umbrella(self, cx: float, cy: float, progress: float, phase: float, brightness: float) -> None:
        """Draws a smooth tilted umbrella with center shaft & J-handle held by Chintu's cyan paw."""
        if progress <= 0.04:
            return
        p = max(0.0, min(1.0, float(progress)))
        ease_open = 1.0 - (1.0 - p) ** 3
        b = brightness * min(1.0, p * 1.6)

        # Anchor paw & J-handle at right side (84, 53); shaft angles -21 deg up-left to dome center!
        angle = -0.37 + math.sin(phase * 2.2) * 0.05 * p
        sin_a = math.sin(angle)
        cos_a = math.cos(angle)
        paw_x = 84.0
        paw_y = 53.0 + math.sin(phase * 3.0) * 0.9 * p
        shaft_len = 46.0 * (0.4 + 0.6 * ease_open)
        dome_cx = paw_x + shaft_len * sin_a
        dome_cy = paw_y - shaft_len * cos_a

        # Draw angled shaft from dome center down to paw
        steps_s = 24
        for i in range(steps_s + 1):
            t = i / float(steps_s)
            sx_pt = dome_cx - t * shaft_len * sin_a
            sy_pt = dome_cy + t * shaft_len * cos_a
            self._rect(sx_pt - 0.9, sy_pt - 0.9, 1.8, 1.8, 0xE2E8F0, b)

        # Curved golden J-handle below paw + cute cyan paw gripping shaft
        if p > 0.25:
            self._draw_rounded_rect(paw_x - 0.8, paw_y, 2.0, 5.0, 0.8, COLOR_GOLD, b)
            self._draw_rounded_rect(paw_x - 4.8, paw_y + 3.6, 5.8, 2.0, 0.9, COLOR_GOLD, b)
            self._draw_rounded_rect(paw_x - 4.8, paw_y + 1.0, 2.0, 3.6, 0.9, COLOR_GOLD, b)
            self._draw_oval(paw_x - 0.6, paw_y - 1.2, 6.2, 5.2, COLOR_EYE, b)
            self._draw_oval(paw_x - 1.5, paw_y - 2.0, 2.0, 1.8, COLOR_WHITE, b * 0.8)

        # Tilted smooth semicircular canopy centered on (dome_cx, dome_cy)
        hw = 6.0 + 38.0 * ease_open
        dome_h = 5.0 + 16.0 * ease_open
        for i in range(-32, 33):
            u = i / 32.0
            # Local coords before tilt: smooth circular arc top, scalloped rim bottom
            lx = u * hw
            ly_top = -dome_h * math.sqrt(max(0.0, 1.0 - u * u))
            scallop = abs(math.sin(u * math.pi * 1.5)) * 2.2 * ease_open
            ly_bot = -scallop
            # Fill column in rotated frame
            steps_y = max(2, int(abs(ly_bot - ly_top) / 1.4))
            is_rib = abs(u) < 0.04 or abs(abs(u) - 0.52) < 0.03
            col = 0xBAE6FD if is_rib else (0x0EA5E9 if u < 0 else 0x0284C7)
            for j in range(steps_y + 1):
                ly = ly_top + (ly_bot - ly_top) * (j / float(steps_y))
                rx = dome_cx + lx * cos_a - ly * sin_a
                ry = dome_cy + lx * sin_a + ly * cos_a
                self._rect(rx - 1.1, ry - 1.1, 2.2, 2.2, col, b)
        # Top ferrule finial tip along shaft axis
        fx = dome_cx + (dome_h + 2.2) * sin_a
        fy = dome_cy - (dome_h + 2.2) * cos_a
        self._draw_oval(fx, fy, 3.0, 3.0, COLOR_GOLD, b)

    def _draw_pixel_blanket(self, progress: float, phase: float, brightness: float) -> None:
        """Draws a cozy quilted starry blanket pulled up to Chintu's chin."""
        if progress <= 0.04:
            return
        p = max(0.0, min(1.0, float(progress)))
        b = brightness
        top_y = 64.0 - 17.0 * p  # rises from y=64 up to y=47
        h = max(1.0, 64.0 - top_y)
        # Quilted blanket body
        self._rect(12.0, top_y + 2.5, 104.0, max(0.0, h - 2.5), 0x264659, b)
        # Soft folded top cuff
        self._rect(11.0, top_y, 106.0, 3.0, COLOR_EYE, b)
        self._rect(13.0, top_y + 0.6, 102.0, 1.2, COLOR_EYE_BRIGHT, b * 0.9)
        # Little paws/tuck bumps gripping the blanket edge
        if p > 0.35:
            self._draw_rounded_rect(22.0, top_y - 1.4, 8.0, 3.6, 1.5, COLOR_EYE_BRIGHT, b)
            self._draw_rounded_rect(98.0, top_y - 1.4, 8.0, 3.6, 1.5, COLOR_EYE_BRIGHT, b)
        # Tiny cozy star speckles on the blanket once pulled up
        if p > 0.55:
            tw = 0.55 + 0.45 * abs(math.sin(phase * 2.0))
            for sx0, sy0 in ((30.0, top_y + 7.0), (54.0, top_y + 10.0), (76.0, top_y + 7.5), (96.0, top_y + 10.5)):
                if sy0 < 62.5:
                    self._rect(sx0, sy0, 2.0, 2.0, COLOR_GOLD, b * tw)

    def _draw_pixel_jacket(self, progress: float, phase: float, brightness: float) -> None:
        """Draws Chintu wearing a cozy quilted winter parka + sherpa hood + scarf + rising zipper."""
        if progress <= 0.04:
            return
        p = max(0.0, min(1.0, float(progress)))
        b = brightness
        slide = 1.0 - (1.0 - min(1.0, p * 1.4)) ** 3
        bob_y = math.sin(phase * 3.0) * 0.7 * p

        if self.disp_h >= 300:
            # Cozy parka torso + padded shoulders in lower AMOLED space (y_design = 51..87)
            top_y = 88.0 - 37.0 * slide + bob_y
            coat_col = 0xE11D48  # rich winter crimson-berry parka
            coat_seam = 0x9F1239
            fur_col = 0xF8FAFC
            scarf_col = 0x38BDF8

            # Puffer sleeves / arms tucked snugly at sides
            self._draw_rounded_rect(14.0, top_y + 4.0, 20.0, 26.0, 8.0, coat_col, b)
            self._draw_rounded_rect(94.0, top_y + 4.0, 20.0, 26.0, 8.0, coat_col, b)
            # Cute warm mitten-paws tucked at chest
            self._draw_oval(33.0, top_y + 21.0, 11.0, 9.0, fur_col, b)
            self._draw_oval(95.0, top_y + 21.0, 11.0, 9.0, fur_col, b)

            # Main quilted puffer parka body
            self._draw_rounded_rect(22.0, top_y, 84.0, 34.0, 10.0, coat_col, b)
            # Horizontal quilted puffer ribs
            for ry in (top_y + 10.0, top_y + 20.0, top_y + 29.0):
                self._rect(25.0, ry, 78.0, 1.6, coat_seam, b)

            # Center zipper track + animated gold zipper pull zipping UP
            zip_prog = max(0.0, min(1.0, (p - 0.18) / 0.68))
            self._rect(63.0, top_y + 2.0, 2.0, 30.0, 0x334155, b)
            zip_y = (top_y + 28.0) - 24.0 * zip_prog
            self._rect(63.2, zip_y, 1.6, (top_y + 31.0) - zip_y, COLOR_GOLD, b)
            self._draw_rounded_rect(61.5, zip_y - 2.0, 5.0, 4.0, 1.2, COLOR_WHITE, b)

            # Cozy blue knit scarf wrapped below chin + dangling scarf tail
            sway = math.sin(phase * 3.5) * 1.4 * p
            self._draw_rounded_rect(28.0, top_y - 2.5, 72.0, 7.0, 3.2, scarf_col, b)
            self._draw_rounded_rect(36.0 + sway * 0.4, top_y + 3.0, 11.0, 15.0, 3.0, scarf_col, b)
            self._rect(36.5 + sway * 0.4, top_y + 14.5, 10.0, 1.8, COLOR_WHITE, b * 0.9)

            # Fluffy sherpa hood arch framing top/sides of head once zipped past halfway
            if p > 0.35:
                hp = min(1.0, (p - 0.35) / 0.45)
                hood_y = -6.0 + (1.0 - hp) * -10.0 + bob_y * 0.5
                self._draw_oval(64.0, hood_y + 4.0, 86.0, 18.0, coat_col, b * hp)
                self._draw_oval(64.0, hood_y + 7.5, 76.0, 14.0, COLOR_BG, 1.0)
                # Plush sherpa fur puffs arching over brow
                for idx in range(-4, 5):
                    fx = 64.0 + idx * 9.5
                    fy = hood_y + 3.0 + (idx * idx) * 0.45
                    self._draw_oval(fx, fy, 11.5, 8.5, fur_col, b * hp)
        else:
            top_y = 64.0 - 13.0 * slide
            self._draw_rounded_rect(20.0, top_y, 88.0, 15.0, 4.0, 0xE11D48, b)
            self._draw_rounded_rect(28.0, top_y - 2.0, 72.0, 4.5, 2.0, 0x38BDF8, b)

    def _draw_pixel_text_screen(self, x: float, y: float, text: str, pixel_sz: float, color: int, brightness: float) -> None:
        cx = x
        for ch in str(text).upper():
            if ch in ("C", "F") and cx > x:
                # Tiny degree dot before C/F
                self._screen_rect(cx, y, pixel_sz * 0.9, pixel_sz * 0.9, color, brightness)
                cx += pixel_sz * 1.6
            glyph = _PIXEL_FONT_3X5.get(ch)
            if glyph is not None:
                for row_idx, row in enumerate(glyph):
                    for col_idx, bit in enumerate(row):
                        if bit == "1":
                            self._screen_rect(
                                cx + col_idx * pixel_sz,
                                y + row_idx * pixel_sz,
                                pixel_sz,
                                pixel_sz,
                                color,
                                brightness,
                            )
                cx += pixel_sz * 4.0

    def _draw_weather_badge(self, state: FaceFrameState) -> None:
        if self.disp_h < 300 or not state.weather_temp_label or state.bell_alpha > 0.05:
            return
        cond = state.weather_condition
        b = max(0.55, state.brightness) * min(1.0, 0.55 + 0.45 * state.weather_intensity)
        bx, by = 18.0, 18.0
        # Mini corner icon
        if cond == "sunny":
            self._screen_rect(bx, by + 2, 10, 10, COLOR_GOLD, b)
            self._screen_rect(bx + 3, by - 1, 4, 16, COLOR_GOLD, b)
            self._screen_rect(bx - 3, by + 5, 16, 4, COLOR_GOLD, b)
        elif cond == "starry":
            self._screen_rect(bx + 2, by + 1, 8, 10, COLOR_GOLD, b)
            self._screen_rect(bx + 5, by + 3, 6, 6, COLOR_BG, 1.0)
        elif cond == "storm":
            self._screen_rect(bx, by + 2, 12, 5, COLOR_CLOUD, b)
            self._screen_rect(bx + 5, by + 7, 3, 4, COLOR_GOLD, b)
            self._screen_rect(bx + 3, by + 10, 3, 4, COLOR_GOLD, b)
        elif cond == "snowy":
            self._screen_rect(bx + 4, by + 1, 2, 12, COLOR_WHITE, b)
            self._screen_rect(bx - 1, by + 6, 12, 2, COLOR_WHITE, b)
        elif cond == "windy":
            self._screen_rect(bx, by + 3, 11, 2, COLOR_EYE_BRIGHT, b)
            self._screen_rect(bx + 2, by + 8, 10, 2, COLOR_CHARGE, b)
        else:
            self._screen_rect(bx, by + 4, 12, 5, COLOR_CLOUD_BRIGHT, b)
            self._screen_rect(bx + 3, by + 1, 6, 4, COLOR_CLOUD_BRIGHT, b)

        self._draw_pixel_text_screen(bx + 20.0, by + 2.0, state.weather_temp_label, 2.5, COLOR_EYE_BRIGHT, b)

    def _draw_weather_backdrop(self, state: FaceFrameState) -> None:
        cond = state.weather_condition
        inten = max(0.0, min(1.0, state.weather_intensity))
        if not cond or inten <= 0.02:
            return
        t = state.weather_phase
        b = state.brightness * inten

        if cond == "sunny":
            # Glowing animated sun in top-left of design band with rotating rays
            sx0, sy0 = 14.0, 12.0
            pulse = 1.0 + 0.08 * math.sin(t * 3.0)
            self._draw_oval(sx0, sy0, 9.0 * pulse, 9.0 * pulse, COLOR_GOLD, b)
            self._draw_oval(sx0, sy0, 5.2, 5.2, COLOR_WHITE, b * 0.85)
            for k in range(8):
                ang = k * (math.pi / 4.0) + t * 0.9
                rx = sx0 + math.cos(ang) * 7.2
                ry = sy0 + math.sin(ang) * 7.2
                self._rect(rx - 0.9, ry - 0.9, 1.8, 1.8, COLOR_ORANGE, b)
            # Warm twinkling sun glints across tall AMOLED margin
            if self.disp_h >= 300:
                for idx in range(5):
                    gx = 55.0 + idx * 78.0
                    gy = 70.0 + 20.0 * math.sin(t * 1.4 + idx)
                    tw = 0.35 + 0.65 * abs(math.sin(t * 2.2 + idx * 1.1))
                    self._screen_rect(gx, gy, 4, 4, COLOR_GOLD, b * tw)

        elif cond == "cloudy":
            c1x = ((t * 5.0) % 150.0) - 11.0
            c2x = ((t * 3.2 + 75.0) % 150.0) - 11.0
            self._draw_pixel_cloud(c1x, 8.0, 1.15, COLOR_CLOUD_BRIGHT, b * 0.9)
            self._draw_pixel_cloud(c2x, 12.0, 0.9, COLOR_CLOUD, b * 0.8)

        elif cond in ("rainy", "storm"):
            if cond == "storm":
                c_lit = 0xCBD5E1 if state.weather_flash > 0.2 else 0x475569
                c_edge = 0x94A3B8 if state.weather_flash > 0.2 else 0x334155
                for cx0, cy0, sc in ((28.0 + math.sin(t * 0.6) * 2.0, -6.0, 1.45), (98.0 - math.sin(t * 0.5) * 2.0, -5.0, 1.35), (64.0, -9.0, 1.25)):
                    self._draw_oval(cx0 - 6.0 * sc, cy0 + 1.0 * sc, 11.0 * sc, 7.0 * sc, c_edge, b * 0.92)
                    self._draw_oval(cx0 + 6.0 * sc, cy0 + 1.5 * sc, 10.0 * sc, 6.5 * sc, c_edge, b * 0.92)
                    self._draw_oval(cx0, cy0 - 1.5 * sc, 13.0 * sc, 8.5 * sc, c_lit, b * 0.95)
            else:
                self._draw_pixel_cloud(22.0 + math.sin(t * 0.6) * 2.0, 8.0, 1.2, COLOR_CLOUD_BRIGHT, b * 0.9)
                self._draw_pixel_cloud(106.0 - math.sin(t * 0.5) * 2.0, 9.0, 1.05, COLOR_CLOUD_BRIGHT, b * 0.85)
            num_drops = 16 if cond == "storm" else 12
            speed = 54.0 if cond == "storm" else 38.0
            for i in range(num_drops):
                # Keep drops primarily around left/right margins and full top/bottom sweep
                lane = (i * 19 + 7) % 124
                if 28 < lane < 100 and (i % 3 != 0):
                    lane = (lane + 42) % 124
                dy = (t * speed + i * 11.3) % 64.0
                dx = (lane + dy * (0.25 if cond == "storm" else 0.10)) % 126.0
                # Deflect drops off the big overhead tilted umbrella canopy when open!
                if cond == "rainy" and state.umbrella_alpha > 0.35 and 16.0 <= dx <= 108.0:
                    u_arc = (dx - 64.0) / 44.0
                    dome_y = -4.0 + 14.0 * (u_arc * u_arc)
                    if dy > dome_y:
                        if dy < dome_y + 10.0:
                            self._rect(dx - 1.2, dome_y - 1.5, 2.6, 1.4, COLOR_WHITE, b * 0.85)
                        continue
                drop_col = COLOR_EYE_BRIGHT if (i % 2 == 0) else COLOR_TEAR
                self._rect(dx, dy, 1.3, 4.0 if cond == "storm" else 3.2, drop_col, b * 0.85)
                if dy > 58.0:
                    # Little puddle splash at floor
                    self._rect(dx - 1.5, 62.0, 4.0, 1.2, COLOR_EYE_BRIGHT, b * 0.7)

            if self.disp_h >= 300:
                # Raindrops falling in top/bottom AMOLED black bands too
                for i in range(10):
                    rx = (i * 43 + 15) % self.disp_w
                    ry = (t * 210.0 + i * 61.0) % self.disp_h
                    if ry < self.band_y - 12 or ry > self.band_y + DESIGN_H * self.scale + 4:
                        self._screen_rect(rx, ry, 2, 10, COLOR_TEAR, b * 0.65)

            if cond == "storm" and state.weather_flash > 0.08:
                fb = state.brightness * min(1.0, state.weather_flash)
                # Tapered continuous jagged lightning bolt from cloud to tip (3 positions)
                bolt_specs = (
                    (101.0, -2.0, -1.0),
                    (25.0, -3.0, 1.0),
                    (74.0, -6.0, -1.0),
                )
                bx0, by0, d = bolt_specs[int(state.weather_bolt) % len(bolt_specs)]
                for step_i in range(18):
                    u = step_i / 17.0
                    if u < 0.45:
                        lu = u / 0.45
                        px = bx0 + d * 7.0 * lu
                        py = by0 + 13.0 * lu
                        w = 5.2 - 1.2 * lu
                    elif u < 0.52:
                        px = bx0 + d * 1.5
                        py = by0 + 12.0
                        w = 6.5
                    else:
                        lu = (u - 0.52) / 0.48
                        px = bx0 + d * (1.5 + 8.0 * lu)
                        py = by0 + 12.0 + 14.0 * lu
                        w = max(1.2, 4.4 * (1.0 - 0.78 * lu))
                    self._rect(px - w * 0.5, py, w, 1.6, COLOR_GOLD, fb)
                    if w > 2.2:
                        self._rect(px - w * 0.25, py + 0.2, w * 0.5, 1.2, COLOR_WHITE, fb)

        elif cond == "snowy":
            for i in range(16):
                base_x = (i * 17 + 5) % 124
                fx = (base_x + math.sin(t * 1.8 + i) * 4.5) % 126.0
                fy = (t * (10.0 + (i % 3) * 3.0) + i * 9.7) % 63.0
                if i % 3 == 0:
                    self._rect(fx - 1.2, fy, 3.4, 1.0, COLOR_WHITE, b * 0.9)
                    self._rect(fx, fy - 1.2, 1.0, 3.4, COLOR_WHITE, b * 0.9)
                else:
                    self._rect(fx, fy, 1.6, 1.6, COLOR_EYE_BRIGHT, b * 0.85)
            if self.disp_h >= 300:
                for i in range(14):
                    fx = ((i * 37 + 19) + math.sin(t * 1.4 + i) * 14.0) % self.disp_w
                    fy = (t * (45.0 + (i % 3) * 12.0) + i * 47.0) % self.disp_h
                    if fy < self.band_y - 8 or fy > self.band_y + DESIGN_H * self.scale + 4:
                        self._screen_rect(fx, fy, 4, 4, COLOR_WHITE, b * 0.8)

        elif cond == "windy":
            for i in range(6):
                wy = 7.0 + i * 10.5
                wx = ((t * (70.0 + i * 8.0) + i * 28.0) % 156.0) - 20.0
                wlen = 12.0 + (i % 3) * 5.0
                col = COLOR_EYE_BRIGHT if i % 2 == 0 else COLOR_CHARGE
                self._rect(wx, wy, wlen, 1.3, col, b * 0.75)
                self._rect(wx + wlen - 3.0, wy - 1.6, 3.0, 1.3, col, b * 0.65)
            # Tumbling pixel leaves
            for i in range(4):
                lx = ((t * 62.0 + i * 35.0) % 146.0) - 10.0
                ly = 14.0 + i * 12.0 + math.sin(t * 5.0 + i) * 4.0
                self._rect(lx, ly, 2.8, 1.8, COLOR_LEAF if i % 2 == 0 else COLOR_GOLD, b * 0.95)

        elif cond == "starry":
            # Crescent moon top-left
            mx, my = 15.0, 11.0
            self._draw_oval(mx, my, 8.5, 8.5, COLOR_GOLD, b * 0.95)
            self._draw_oval(mx + 2.4, my - 1.2, 6.8, 6.8, COLOR_BG, 1.0)
            # Twinkling stars
            star_coords = ((34, 8), (64, 6), (96, 9), (116, 15), (12, 48), (118, 52), (52, 57), (80, 56))
            for idx, (sx0, sy0) in enumerate(star_coords):
                tw = 0.25 + 0.75 * abs(math.sin(t * 2.1 + idx * 0.9))
                self._rect(sx0, sy0, 1.6, 1.6, COLOR_WHITE if idx % 2 == 0 else COLOR_GOLD, b * tw)
            if self.disp_h >= 300:
                for idx in range(12):
                    sx0 = (idx * 39 + 24) % (self.disp_w - 10)
                    sy0 = 44.0 + ((idx * 53) % 90) if idx < 6 else (self.disp_h - 120.0 + (idx * 17) % 95)
                    tw = 0.25 + 0.75 * abs(math.sin(t * 1.9 + idx * 1.3))
                    self._screen_rect(sx0, sy0, 3, 3, COLOR_GOLD if idx % 3 == 0 else COLOR_WHITE, b * tw)

    def _draw_eye_shape(
        self,
        cx: float,
        cy: float,
        open_amt: float,
        scale_mul: float,
        mood: str,
        is_left: bool,
        state: FaceFrameState,
    ) -> None:
        b = state.brightness
        open_clamped = max(0.0, min(1.0, float(open_amt))) * max(0.0, 1.0 - state.blink_progress)
        ew = min(EYE_MAX_W, 24.0 * scale_mul)
        eh = min(EYE_MAX_H, 21.0 * scale_mul)

        if state.happy_arcs or mood == "HAPPY" and state.face_mode == "found_you":
            self._draw_happy_arc_eye(cx, cy, ew, b)
            return

        if mood == "DIZZY":
            # Animated @_@ spiral eyes
            turns = 3.0 * 2.0 * math.pi
            steps = 44
            spin_dir = 1.0 if is_left else -1.0
            rot = state.dizzy_phase * 12.0 * spin_dir
            for i in range(steps + 1):
                t = i / float(steps)
                theta = t * turns + rot
                rad = 1.0 + t * 8.2
                px = cx + rad * math.cos(theta)
                py = cy + rad * math.sin(theta)
                self._rect(px - 1.05, py - 1.05, 2.1, 2.1, COLOR_EYE_BRIGHT, b)
            self._rect(cx - 1.1, cy - 1.1, 2.2, 2.2, COLOR_WHITE, b)
            return

        if mood == "COOL":
            self._draw_rounded_rect(cx - ew * 0.5, cy - eh * 0.35, ew, eh * 0.65, 3.0, COLOR_EYE, b)
            self._rect(cx - ew * 0.25, cy - eh * 0.25, 2.5, eh * 0.45, COLOR_WHITE, b)
            return

        if mood == "LOVE":
            self._draw_pixel_heart(cx, cy - 1.0, 1.0, b)
            return

        if mood == "WINK" and not is_left:
            self._draw_happy_arc_eye(cx, cy, ew, b)
            return

        if mood == "SMIRK" and not is_left:
            self._draw_closed_curve_eye(cx, cy + 1.0, ew, b)
            return

        if open_clamped <= 0.06:
            if state.face_mode == "sleep":
                self._draw_closed_curve_eye(cx, cy, ew, b)
            else:
                # Squished shut line
                self._draw_rounded_rect(cx - ew * 0.48, cy - 1.2, ew * 0.96, 2.4, 1.0, COLOR_EYE, b)
            return

        cur_h = max(2.8, eh * open_clamped)
        r = min(7.0, ew * 0.35, cur_h * 0.45)
        self._draw_rounded_rect(cx - ew * 0.5, cy - cur_h * 0.5, ew, cur_h, r, COLOR_EYE, b)

        if mood == "ANGRY":
            # Inner brow slant
            if is_left:
                self._rect(cx, cy - cur_h * 0.5, ew * 0.52, cur_h * 0.38, COLOR_BG, 1.0)
            else:
                self._rect(cx - ew * 0.52, cy - cur_h * 0.5, ew * 0.52, cur_h * 0.38, COLOR_BG, 1.0)
        elif mood == "CRYING":
            tear_y = cy + cur_h * 0.5 + 2.0 + (state.dizzy_phase * 4.0) % 5.0
            self._rect(cx - 2.0, tear_y, 4.0, 4.0, COLOR_TEAR, b)

        # Eye highlight + sparkle
        if open_clamped >= 0.45:
            hl_size = 3.2 if state.sparkles <= 0.1 else 4.2
            if mood == "PLEADING":
                hl_size = 4.4
            self._draw_rounded_rect(
                cx - ew * 0.28,
                cy - cur_h * 0.30,
                hl_size,
                hl_size,
                1.0,
                COLOR_WHITE,
                b,
            )
            if mood == "PLEADING":
                self._draw_rounded_rect(
                    cx + ew * 0.12,
                    cy + cur_h * 0.12,
                    2.2,
                    2.2,
                    0.8,
                    COLOR_WHITE,
                    b,
                )
        if state.sparkles > 0.1 and open_clamped >= 0.5:
            sb = b * state.sparkles
            # Twinkling second catchlight + mini 4-point sparkle
            self._rect(cx + ew * 0.14, cy + cur_h * 0.10, 2.4, 2.4, COLOR_SPARKLE, sb)
            self._rect(cx - ew * 0.36, cy - cur_h * 0.42, 1.6, 4.2, COLOR_SPARKLE, sb)
            self._rect(cx - ew * 0.44, cy - cur_h * 0.34, 4.2, 1.6, COLOR_SPARKLE, sb)

    def _draw_mouth(self, cx: float, cy: float, state: FaceFrameState) -> None:
        b = state.brightness
        if state.talk_open > 0.02:
            # Smooth tapered :D crescent talking mouth (zero boxy edges)
            o = max(0.0, min(1.0, state.talk_open))
            w_mod = max(0.0, min(1.0, state.talk_width))
            hw = 6.8 + 2.6 * w_mod
            depth = 2.2 + 8.2 * o
            steps = 48
            # Pass 1: solid outer cyan :D crescent
            for i in range(-steps, steps + 1):
                u = i / float(steps)
                px = cx + u * hw
                arc = math.sqrt(max(0.0, 1.0 - u * u))
                y_top = cy + 16.5 - (u * u) * 2.4
                y_bot = y_top + depth * arc
                self._rect(px - 1.1, y_top, 2.2, max(1.6, y_bot - y_top), COLOR_MOUTH, b)
            # Pass 2: dark inner mouth cavity (zero stripe overlap)
            if o > 0.28:
                for i in range(-steps, steps + 1):
                    u = i / float(steps)
                    arc = math.sqrt(max(0.0, 1.0 - u * u))
                    if arc <= 0.32:
                        continue
                    px = cx + u * (hw - 1.4)
                    y_top = cy + 16.5 - (u * u) * 2.4 + 1.5
                    y_bot = cy + 16.5 - (u * u) * 2.4 + depth * arc - 1.4
                    if y_bot > y_top:
                        self._rect(px - 1.0, y_top, 2.0, y_bot - y_top, COLOR_TONGUE_DARK, 1.0)
            # Pass 3: coral tongue arc tucked in lower D
            if o > 0.45:
                for i in range(-steps, steps + 1):
                    u = i / float(steps)
                    if abs(u) >= 0.56:
                        continue
                    arc = math.sqrt(max(0.0, 1.0 - u * u))
                    px = cx + u * (hw - 1.4)
                    in_top = cy + 16.5 - (u * u) * 2.4 + 1.5
                    in_bot = cy + 16.5 - (u * u) * 2.4 + depth * arc - 1.4
                    tg_arc = math.sqrt(max(0.0, 1.0 - (u / 0.56) ** 2))
                    tg_top = in_bot - max(0.0, in_bot - in_top) * 0.52 * tg_arc
                    if in_bot > tg_top:
                        self._rect(px - 1.0, tg_top, 2.0, in_bot - tg_top, COLOR_HEART, b)
            return

        if state.mouth_open > 0.02:
            # YAWN: ONE enormous oval up to 36x28 px in design space (115x90 px scaled)
            wobble = 1.0 + state.mouth_wobble
            mw = max(4.0, YAWN_MOUTH_MAX_W * state.mouth_open * wobble)
            mh = max(3.0, YAWN_MOUTH_MAX_H * state.mouth_open * (2.0 - wobble))
            my = cy + 16.0
            self._draw_oval(cx, my, mw, mh, COLOR_MOUTH, b)
            # Small dark tongue notch at bottom once past half-open
            if state.mouth_open > 0.5:
                nw = mw * 0.34
                nh = mh * 0.24
                self._draw_oval(cx, my + mh * 0.36, nw, nh, COLOR_TONGUE_DARK, 1.0)
            return

        if state.face_mode == "sleep":
            # Tiny content mouth
            self._draw_rounded_rect(cx - 3.5, cy + 16.0, 7.0, 2.0, 1.0, COLOR_MOUTH, b)
            return

        if state.mood == "SURPRISED":
            self._draw_oval(cx, cy + 16.0, 7.0, 7.0, COLOR_MOUTH, b)
            return

        if state.mood == "TONGUE":
            self._rect(cx - 5.5, cy + 15.0, 11.0, 2.2, COLOR_MOUTH, b)
            self._draw_rounded_rect(cx - 3.0, cy + 16.8, 6.0, 5.5, 2.5, COLOR_HEART, b)
            return

        if state.mood in ("ANGRY", "CRYING"):
            self._rect(cx - 5.0, cy + 16.5, 10.0, 2.2, COLOR_MOUTH, b)
            return

        if state.mood == "DIZZY":
            # Wavy dizzy squiggle mouth
            for i in range(-6, 7):
                u = i / 6.0
                self._rect(cx + u * 7.0 - 1.0, cy + 16.0 + math.sin(u * math.pi * 2.0) * 1.6, 2.2, 2.0, COLOR_MOUTH, b)
            return

        if state.mood == "PLEADING":
            # Small worried/trembling mouth
            quiver = math.sin(state.dizzy_phase * 28.0) * 0.45
            self._draw_rounded_rect(cx - 3.8, cy + 16.2 + quiver, 7.6, 2.4, 1.0, COLOR_MOUTH, b)
            return

        # Calm / happy smile scaled by smile_amount
        smile_w = 10.0 + 6.0 * max(0.0, min(1.0, state.smile_amount))
        steps = 8
        for i in range(-steps, steps + 1):
            u = i / float(steps)
            px = cx + u * (smile_w * 0.5)
            py = cy + 16.5 - (u * u) * (1.8 + 1.8 * state.smile_amount)
            self._rect(px - 1.1, py - 0.9, 2.2, 2.0, COLOR_MOUTH, b)

    def render(self, state: FaceFrameState) -> None:
        """Renders one complete frame onto the display target."""
        if self.target is None:
            return

        self.target.setOpacity(1.0)
        self.target.setColor(COLOR_BG)
        self.target.fillRectangle(0, 0, self.disp_w, self.disp_h)

        if state.weather_condition and state.weather_intensity > 0.02:
            self._draw_weather_backdrop(state)

        gx = max(-1.0, min(1.0, state.gaze_x)) * 7.0
        gy = max(-1.0, min(1.0, state.gaze_y)) * 4.5
        bx = state.face_bob_x
        by = state.face_bob_y
        fsc = max(0.6, min(1.15, state.face_scale))

        lcx = (DESIGN_W * 0.5) - 24.0 * fsc + gx + bx
        rcx = (DESIGN_W * 0.5) + 24.0 * fsc + gx + bx
        ecy = EYE_CY + gy + by
        mcx = (DESIGN_W * 0.5) + gx * 0.4 + bx
        mcy = EYE_CY + gy * 0.5 + by - (1.0 - fsc) * 10.0

        self._draw_eye_shape(lcx, ecy, state.left_eye_open, state.eye_scale * fsc, state.mood, True, state)
        self._draw_eye_shape(rcx, ecy, state.right_eye_open, state.eye_scale * fsc, state.mood, False, state)
        self._draw_mouth(mcx, mcy, state)

        if state.jacket_alpha > 0.04:
            self._draw_pixel_jacket(state.jacket_alpha, state.weather_phase, state.brightness)

        if state.blanket_alpha > 0.04:
            self._draw_pixel_blanket(state.blanket_alpha, state.weather_phase, state.brightness)

        if state.umbrella_alpha > 0.05:
            self._draw_pixel_umbrella(64.0, 5.5, state.umbrella_alpha, state.weather_phase, state.brightness)

        if state.weather_condition and state.weather_intensity > 0.02:
            self._draw_weather_badge(state)

        # Sleep Zzz drifting +6 px over 3 s then fading
        if state.zzz_phase >= 0.0:
            zp = max(0.0, min(1.0, state.zzz_phase))
            fade = 1.0 - max(0.0, (zp - 0.65) / 0.35)
            zx = 104.0 + zp * 6.0
            zy = 18.0 - zp * 6.0
            self._draw_pixel_z(zx, zy, 6.0, state.brightness * fade)

        # Top-right pixel heart on Found You / Pat
        if state.heart_alpha > 0.05:
            self._draw_pixel_heart(114.0, 12.0, state.heart_alpha, state.brightness)

        # Startled '!' & worried sweat drop when kicked off dock / shaken
        if state.alert_alpha > 0.05:
            self._draw_pixel_alert(114.0 + bx * 0.5, 13.0 + by * 0.5, state.alert_alpha, state.brightness)
        if state.bell_alpha > 0.05:
            self._draw_pixel_bell(14.0, 13.0, state.bell_alpha, state.dizzy_phase, state.brightness)
        if state.sweat_alpha > 0.05:
            self._draw_pixel_sweat_drop(109.0 + bx * 0.6, 14.0 + by * 0.6, state.sweat_alpha, state.dizzy_phase, state.brightness)

        if state.mood == "THINKING":
            dot_phase = int(state.dizzy_phase * 3.0) % 3
            for i in range(3):
                col = COLOR_EYE_BRIGHT if i == dot_phase else COLOR_EYE_DIM
                self._rect(96.0 + i * 6.0, 9.0, 3.0, 3.0, col, state.brightness)

        # Charging glyph (ONLY addition in CHARGING_SLEEP)
        if state.is_charging:
            self._draw_charging_glyph(max(0.55, state.brightness))


def build_storyboard_frame(state_name: str, progress: float = 0.5, is_charging: bool = False) -> FaceFrameState:
    """Produces a deterministic FaceFrameState for any of the 7 storyboard states."""
    u = max(0.0, min(1.0, float(progress)))
    key = str(state_name).lower().strip()
    if key == "sleep":
        return FaceFrameState(
            face_mode="sleep",
            mood="SLEEPY",
            left_eye_open=0.0,
            right_eye_open=0.0,
            face_bob_y=math.sin(u * 2.0 * math.pi) * 1.0,
            zzz_phase=u,
            is_charging=is_charging,
            brightness=0.40,
        )
    if key == "stir":
        return FaceFrameState(
            face_mode="stir",
            mood="SLEEPY",
            left_eye_open=0.25,
            right_eye_open=0.0 if u < 0.57 else 0.25 * min(1.0, (u - 0.57) / 0.29),
            brightness=0.40 + 0.60 * u,
        )
    if key == "flutter":
        pts = [0.25, 0.70, 0.35, 0.85, 0.50, 1.00]
        seg = min(len(pts) - 2, int(u * (len(pts) - 1)))
        local = (u * (len(pts) - 1)) - seg
        op = pts[seg] + (pts[seg + 1] - pts[seg]) * local
        return FaceFrameState(face_mode="flutter", mood="SLEEPY", left_eye_open=op, right_eye_open=op)
    if key == "yawn":
        return FaceFrameState(
            face_mode="yawn",
            mood="SLEEPY",
            left_eye_open=0.0,
            right_eye_open=0.35,
            mouth_open=1.0,
            mouth_wobble=0.04 * math.sin(u * 6.0 * math.pi),
            face_bob_y=1.6 * math.sin(u * 4.0 * math.pi),
        )
    if key == "look":
        return FaceFrameState(
            face_mode="look",
            mood="SURPRISED",
            left_eye_open=1.0,
            right_eye_open=1.0,
            eye_scale=1.08,
            gaze_x=-0.85 if u < 0.5 else 0.85,
            smile_amount=0.15,
        )
    if key in ("found-you", "found_you"):
        if u < 0.25:
            return FaceFrameState(face_mode="found_you", mood="HAPPY", happy_arcs=True, smile_amount=0.85)
        return FaceFrameState(
            face_mode="found_you",
            mood="HAPPY",
            left_eye_open=1.0,
            right_eye_open=1.0,
            eye_scale=1.06,
            sparkles=1.0,
            heart_alpha=1.0,
            smile_amount=0.95,
        )
    return FaceFrameState(
        face_mode="content_idle",
        mood="NEUTRAL",
        left_eye_open=1.0,
        right_eye_open=1.0,
        smile_amount=0.35,
    )
