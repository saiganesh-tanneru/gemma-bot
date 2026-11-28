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

        if mood == "STAR_EYES":
            for i in range(8):
                span = 8 - i
                self._rect(cx - span, cy - i, span * 2, 1.2, COLOR_GOLD, b)
                self._rect(cx - span, cy + i, span * 2, 1.2, COLOR_GOLD, b)
            self._rect(cx - 2.0, cy - 2.0, 4.0, 4.0, COLOR_WHITE, b)
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

        gx = max(-1.0, min(1.0, state.gaze_x)) * 7.0
        gy = max(-1.0, min(1.0, state.gaze_y)) * 4.5
        bx = state.face_bob_x
        by = state.face_bob_y

        lcx = LEFT_EYE_CX + gx + bx
        rcx = RIGHT_EYE_CX + gx + bx
        ecy = EYE_CY + gy + by
        mcx = (DESIGN_W * 0.5) + gx * 0.4 + bx
        mcy = EYE_CY + gy * 0.5 + by

        self._draw_eye_shape(lcx, ecy, state.left_eye_open, state.eye_scale, state.mood, True, state)
        self._draw_eye_shape(rcx, ecy, state.right_eye_open, state.eye_scale, state.mood, False, state)
        self._draw_mouth(mcx, mcy, state)

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
