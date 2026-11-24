#!/usr/bin/env python3
"""
Generates high-contrast visual assets for Gemma-Bot README:
1. expressions_grid.png: 5x3 grid of all 15 OLED companion moods & emojis
2. color_themes.png: Showcase of all 6 high-contrast screen color themes
"""

import os
import struct
import sys
import zlib
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[1])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import config

# 5x7 Pixel Font for Labels
FONT_5X7 = {
    'A': [0x0C, 0x12, 0x12, 0x1E, 0x12, 0x12, 0x12],
    'B': [0x1C, 0x12, 0x12, 0x1C, 0x12, 0x12, 0x1C],
    'C': [0x0E, 0x12, 0x10, 0x10, 0x10, 0x12, 0x0E],
    'D': [0x1C, 0x12, 0x12, 0x12, 0x12, 0x12, 0x1C],
    'E': [0x1E, 0x10, 0x10, 0x1C, 0x10, 0x10, 0x1E],
    'F': [0x1E, 0x10, 0x10, 0x1C, 0x10, 0x10, 0x10],
    'G': [0x0E, 0x12, 0x10, 0x16, 0x12, 0x12, 0x0E],
    'H': [0x12, 0x12, 0x12, 0x1E, 0x12, 0x12, 0x12],
    'I': [0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
    'J': [0x02, 0x02, 0x02, 0x02, 0x12, 0x12, 0x0C],
    'K': [0x12, 0x14, 0x18, 0x10, 0x18, 0x14, 0x12],
    'L': [0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1E],
    'M': [0x11, 0x1B, 0x15, 0x11, 0x11, 0x11, 0x11],
    'N': [0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11],
    'O': [0x0C, 0x12, 0x12, 0x12, 0x12, 0x12, 0x0C],
    'P': [0x1C, 0x12, 0x12, 0x1C, 0x10, 0x10, 0x10],
    'Q': [0x0C, 0x12, 0x12, 0x12, 0x16, 0x12, 0x0D],
    'R': [0x1C, 0x12, 0x12, 0x1C, 0x14, 0x12, 0x12],
    'S': [0x0E, 0x10, 0x10, 0x0C, 0x02, 0x02, 0x1C],
    'T': [0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04],
    'U': [0x12, 0x12, 0x12, 0x12, 0x12, 0x12, 0x0C],
    'V': [0x11, 0x11, 0x11, 0x0A, 0x0A, 0x04, 0x04],
    'W': [0x11, 0x11, 0x11, 0x15, 0x15, 0x15, 0x0A],
    'X': [0x11, 0x0A, 0x04, 0x04, 0x0A, 0x11, 0x11],
    'Y': [0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04],
    'Z': [0x1F, 0x02, 0x04, 0x08, 0x10, 0x10, 0x1F],
    ' ': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
    '-': [0x00, 0x00, 0x00, 0x1F, 0x00, 0x00, 0x00],
    '_': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F],
    '/': [0x01, 0x02, 0x04, 0x08, 0x10, 0x00, 0x00],
    ':': [0x00, 0x04, 0x00, 0x00, 0x04, 0x00, 0x00],
    '.': [0x00, 0x00, 0x00, 0x00, 0x00, 0x04, 0x00],
    '0': [0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E],
    '1': [0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E],
    '2': [0x0E, 0x11, 0x01, 0x06, 0x08, 0x10, 0x1F],
    '3': [0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E],
    '4': [0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02],
    '5': [0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E],
    '6': [0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E],
    '7': [0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08],
    '8': [0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E],
    '9': [0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C]
}

def write_png(filename, width, height, rgba_data):
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw.extend(rgba_data[y * width * 4 : (y + 1) * width * 4])
    compressed = zlib.compress(bytes(raw), 9)
    def chunk(chunk_type, data):
        c = chunk_type + data
        crc = zlib.crc32(c) & 0xffffffff
        return struct.pack('>I', len(data)) + c + struct.pack('>I', crc)
    ihdr_data = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr_data) + chunk(b'IDAT', compressed) + chunk(b'IEND', b'')
    with open(filename, 'wb') as f:
        f.write(png)

class Canvas:
    def __init__(self, w, h, bg_rgba=(10, 12, 16, 255)):
        self.w = w
        self.h = h
        self.data = bytearray(list(bg_rgba) * (w * h))

    def set_pixel(self, x, y, r, g, b, a=255):
        if 0 <= x < self.w and 0 <= y < self.h:
            idx = (y * self.w + x) * 4
            self.data[idx] = r
            self.data[idx + 1] = g
            self.data[idx + 2] = b
            self.data[idx + 3] = a

    def fill_rect(self, x, y, w, h, r, g, b, a=255):
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(self.w, int(x + w))
        y1 = min(self.h, int(y + h))
        for py in range(y0, y1):
            row_start = (py * self.w + x0) * 4
            row_end = (py * self.w + x1) * 4
            self.data[row_start:row_end] = bytearray([r, g, b, a] * (x1 - x0))

    def draw_text(self, text, x, y, r, g, b, scale=1):
        cx = x
        for ch in text.upper():
            glyph = FONT_5X7.get(ch, FONT_5X7.get(' '))
            for row_idx, row_val in enumerate(glyph):
                for col_idx in range(5):
                    if (row_val >> (4 - col_idx)) & 1:
                        self.fill_rect(cx + col_idx * scale, y + row_idx * scale, scale, scale, r, g, b)
            cx += 6 * scale

class OLEDDisplay:
    def __init__(self, theme_dict):
        self.w = 128
        self.h = 64
        self.canvas = Canvas(self.w, self.h, (0, 0, 0, 255))
        self.theme = theme_dict
        self.bg_color = self.hex_to_rgb(theme_dict.get("bg_color", 0x000000))
        self.eye_color = self.hex_to_rgb(theme_dict.get("eye_color", 0x00F0FF))
        self.eye_dim = self.hex_to_rgb(theme_dict.get("eye_dim", 0x007799))
        self.mouth_color = self.hex_to_rgb(theme_dict.get("mouth_color", 0x00D0FF))
        self.sunglass_frame = self.hex_to_rgb(theme_dict.get("sunglass_frame", 0x00F0FF))
        self.accent_pink = (255, 68, 136)
        self.accent_yellow = (255, 221, 0)
        self.tear_blue = (68, 170, 255)
        self.white = (255, 255, 255)
        
        self.left_cx = 38
        self.right_cx = 90
        self.base_cy = 32
        self.eye_w = 28
        self.eye_h = 34

    @staticmethod
    def hex_to_rgb(val):
        return ((val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)

    def draw_box(self, x, y, w, h, col):
        self.canvas.fill_rect(x, y, w, h, col[0], col[1], col[2])

    def draw_rounded_eye(self, cx, cy, w, h, corner_r=5, col=None):
        c = col if col else self.eye_color
        x = cx - w / 2
        y = cy - h / 2
        self.draw_box(x + corner_r, y, w - 2 * corner_r, h, c)
        self.draw_box(x, y + corner_r, corner_r, h - 2 * corner_r, c)
        self.draw_box(x + w - corner_r, y + corner_r, corner_r, h - 2 * corner_r, c)

    def draw_happy_eye(self, cx, cy, w):
        x = cx - w / 2
        self.draw_box(x, cy - 2, w, 7, self.eye_color)
        self.draw_box(x + 2, cy - 5, w - 4, 4, self.eye_color)
        self.draw_box(x + 5, cy - 7, w - 10, 3, self.eye_color)
        self.draw_box(x + 3, cy, w - 6, 8, self.bg_color)

    def draw_sleepy_eye(self, cx, cy, w):
        x = cx - w / 2
        self.draw_box(x, cy + 2, w, 5, self.eye_color)
        self.draw_box(x + 2, cy + 5, w - 4, 3, self.eye_color)

    def draw_angry_eye(self, cx, cy, w, h, is_left=True):
        x = cx - w / 2
        y = cy - h / 2
        self.draw_box(x, y, w, h, self.eye_color)
        if is_left:
            self.draw_box(x + w/2, y, w/2, h * 0.45, self.bg_color)
        else:
            self.draw_box(x, y, w/2, h * 0.45, self.bg_color)

    def draw_heart(self, cx, cy):
        self.draw_box(cx - 7, cy - 4, 6, 6, self.accent_pink)
        self.draw_box(cx + 1, cy - 4, 6, 6, self.accent_pink)
        self.draw_box(cx - 9, cy, 18, 5, self.accent_pink)
        self.draw_box(cx - 7, cy + 5, 14, 4, self.accent_pink)
        self.draw_box(cx - 4, cy + 9, 8, 4, self.accent_pink)
        self.draw_box(cx - 1, cy + 13, 2, 2, self.accent_pink)

    def draw_star(self, cx, cy, r=12):
        for i in range(r):
            w = r - i
            self.draw_box(cx - w, cy - i, w * 2, 1, self.accent_yellow)
            self.draw_box(cx - w, cy + i, w * 2, 1, self.accent_yellow)
        self.draw_box(cx - 2, cy - 2, 4, 4, self.white)

    def draw_sunglasses(self, lcx, rcx, cy, w, h):
        top_y = cy - h/2 + 2
        lens_h = h - 6
        self.draw_box(lcx - w/2 - 2, top_y, w + 4, lens_h, self.sunglass_frame)
        self.draw_box(lcx - w/2, top_y + 2, w, lens_h - 4, (17, 17, 17))
        self.draw_box(rcx - w/2 - 2, top_y, w + 4, lens_h, self.sunglass_frame)
        self.draw_box(rcx - w/2, top_y + 2, w, lens_h - 4, (17, 17, 17))
        bridge_start = lcx + w/2 - 1
        bridge_w = (rcx - w/2) - bridge_start + 1
        self.draw_box(bridge_start, top_y + 2, bridge_w, 3, self.sunglass_frame)
        self.draw_box(lcx - w/4, top_y + 3, 3, lens_h - 6, self.white)
        self.draw_box(rcx - w/4, top_y + 3, 3, lens_h - 6, self.white)

    def draw_pleading_eye(self, cx, cy, w, h):
        self.draw_rounded_eye(cx, cy, w + 2, h + 2, corner_r=8, col=self.eye_color)
        self.draw_box(cx - w/4 - 2, cy - h/4 - 2, 8, 8, self.white)
        self.draw_box(cx + w/6, cy + h/6, 4, 4, self.white)

    def draw_cross_eye(self, cx, cy, size=10):
        t = 3
        for i in range(-size, size):
            self.draw_box(cx + i - t//2, cy + i - t//2, t, t, self.eye_color)
            self.draw_box(cx + i - t//2, cy - i - t//2, t, t, self.eye_color)

    def draw_crying_eye(self, cx, cy, w, h, is_left=True):
        y = cy - h/2
        self.draw_box(cx - w/2, y + 5, w, h - 8, self.eye_color)
        if is_left:
            self.draw_box(cx - w/2, y, w/2, 7, self.bg_color)
        else:
            self.draw_box(cx, y, w/2, 7, self.bg_color)
        self.draw_box(cx - 3, min(self.h - 4, cy + 18), 6, 6, self.tear_blue)
        self.draw_box(cx - 2, min(self.h - 8, cy + 13), 4, 4, self.white)

    def render_mood(self, mood):
        self.canvas.fill_rect(0, 0, self.w, self.h, self.bg_color[0], self.bg_color[1], self.bg_color[2])
        lcx = self.left_cx
        rcx = self.right_cx
        cy = self.base_cy
        w = self.eye_w
        h = self.eye_h

        if mood == "NEUTRAL":
            self.draw_rounded_eye(lcx, cy, w, h, corner_r=6)
            self.draw_rounded_eye(rcx, cy, w, h, corner_r=6)
            self.draw_box(self.w/2 - 4, cy + 17, 8, 2, self.mouth_color)
        elif mood == "HAPPY":
            self.draw_happy_eye(lcx, cy, w)
            self.draw_happy_eye(rcx, cy, w)
            self.draw_box(self.w/2 - 6, cy + 16, 12, 3, self.mouth_color)
            self.draw_box(self.w/2 - 3, cy + 19, 6, 2, self.mouth_color)
        elif mood == "LOVE":
            self.draw_heart(lcx, cy)
            self.draw_heart(rcx, cy)
            self.draw_box(self.w/2 - 5, cy + 16, 10, 3, self.accent_pink)
        elif mood == "COOL":
            self.draw_sunglasses(lcx, rcx, cy, w, h)
            self.draw_box(self.w/2 - 4, cy + 17, 10, 3, self.mouth_color)
            self.draw_box(self.w/2 + 5, cy + 15, 3, 3, self.mouth_color)
        elif mood == "STAR_EYES":
            self.draw_star(lcx, cy, r=12)
            self.draw_star(rcx, cy, r=12)
            self.draw_box(self.w/2 - 6, cy + 16, 12, 4, self.mouth_color)
            self.draw_box(self.w/2 - 4, cy + 20, 8, 2, self.mouth_color)
        elif mood == "PLEADING":
            self.draw_pleading_eye(lcx, cy, w, h)
            self.draw_pleading_eye(rcx, cy, w, h)
            self.draw_box(self.w/2 - 4, cy + 17, 8, 3, self.mouth_color)
        elif mood == "WINK":
            self.draw_rounded_eye(lcx, cy, w, h, corner_r=6)
            self.draw_happy_eye(rcx, cy, w)
            self.draw_box(self.w/2 - 5, cy + 16, 10, 3, self.mouth_color)
            self.draw_box(self.w/2 + 3, cy + 14, 3, 3, self.mouth_color)
        elif mood == "CRYING":
            self.draw_crying_eye(lcx, cy, w, h, is_left=True)
            self.draw_crying_eye(rcx, cy, w, h, is_left=False)
            self.draw_box(self.w/2 - 5, cy + 18, 10, 3, self.tear_blue)
            self.draw_box(self.w/2 - 5, cy + 20, 3, 2, self.tear_blue)
            self.draw_box(self.w/2 + 2, cy + 20, 3, 2, self.tear_blue)
        elif mood == "TONGUE":
            self.draw_happy_eye(lcx, cy, w)
            self.draw_happy_eye(rcx, cy, w)
            self.draw_box(self.w/2 - 6, cy + 15, 12, 3, self.mouth_color)
            self.draw_box(self.w/2 - 3, cy + 17, 7, 6, self.accent_pink)
            self.draw_box(self.w/2 - 1, cy + 22, 3, 2, self.accent_pink)
        elif mood == "DIZZY":
            self.draw_cross_eye(lcx, cy, size=10)
            self.draw_cross_eye(rcx, cy, size=10)
            self.draw_box(self.w/2 - 6, cy + 16, 4, 3, self.mouth_color)
            self.draw_box(self.w/2 - 2, cy + 18, 4, 3, self.mouth_color)
            self.draw_box(self.w/2 + 2, cy + 16, 4, 3, self.mouth_color)
        elif mood == "SMIRK":
            self.draw_rounded_eye(lcx, cy - 2, w, h, corner_r=6)
            self.draw_sleepy_eye(rcx, cy + 3, w)
            self.draw_box(self.w/2 - 3, cy + 16, 8, 3, self.mouth_color)
            self.draw_box(self.w/2 + 4, cy + 14, 3, 3, self.mouth_color)
        elif mood == "SURPRISED":
            self.draw_rounded_eye(lcx, cy - 2, w + 4, h + 6, corner_r=8)
            self.draw_rounded_eye(rcx, cy - 2, w + 4, h + 6, corner_r=8)
            self.draw_box(self.w/2 - 4, cy + 15, 8, 8, self.mouth_color)
        elif mood == "SLEEPY":
            self.draw_sleepy_eye(lcx, cy + 4, w)
            self.draw_sleepy_eye(rcx, cy + 4, w)
            self.canvas.draw_text("Z", 106, 12, self.eye_dim[0], self.eye_dim[1], self.eye_dim[2], scale=1)
            self.canvas.draw_text("Z", 114, 6, self.eye_color[0], self.eye_color[1], self.eye_color[2], scale=1)
        elif mood == "ANGRY":
            self.draw_angry_eye(lcx, cy, w, h, is_left=True)
            self.draw_angry_eye(rcx, cy, w, h, is_left=False)
            self.draw_box(self.w/2 - 5, cy + 17, 10, 3, self.mouth_color)
        elif mood == "THINKING":
            self.draw_rounded_eye(lcx + 4, cy - 6, w - 2, h - 2, corner_r=5)
            self.draw_rounded_eye(rcx + 4, cy - 6, w - 2, h - 2, corner_r=5)
            for i in range(3):
                col = self.eye_color if i == 2 else self.eye_dim
                self.draw_box(96 + i * 8, 10, 4, 4, col)

def generate_expressions_grid(out_path):
    moods = [
        ("NEUTRAL", "Neutral 1"),
        ("HAPPY", "Happy 2"),
        ("LOVE", "Love 7"),
        ("COOL", "Cool 8"),
        ("STAR_EYES", "Star Eyes 9"),
        ("PLEADING", "Pleading 0"),
        ("WINK", "Wink W"),
        ("CRYING", "Crying C"),
        ("TONGUE", "Tongue T"),
        ("DIZZY", "Dizzy D"),
        ("SMIRK", "Smirk S"),
        ("SURPRISED", "Surprised 3"),
        ("SLEEPY", "Sleepy 4"),
        ("ANGRY", "Angry 5"),
        ("THINKING", "Thinking 6"),
    ]
    
    cols = 5
    rows = 3
    scale = 2  # 128x64 -> 256x128
    tile_w = 128 * scale
    tile_h = 64 * scale
    margin_x = 20
    margin_y = 20
    header_h = 24
    
    grid_w = cols * tile_w + (cols + 1) * margin_x
    grid_h = rows * (tile_h + header_h) + (rows + 1) * margin_y + 40
    
    canvas = Canvas(grid_w, grid_h, (13, 17, 23, 255))
    canvas.draw_text("GEMMA-BOT OLED EMOTIONS & EMOJIS SUITE", margin_x, 14, 0, 240, 255, scale=2)
    
    cyan_theme = {
        "bg_color": 0x000000,
        "eye_color": 0x00F0FF,
        "eye_dim": 0x007799,
        "mouth_color": 0x00D0FF,
        "sunglass_frame": 0x00F0FF
    }
    oled = OLEDDisplay(cyan_theme)
    
    for idx, (m, label) in enumerate(moods):
        r = idx // cols
        c = idx % cols
        bx = margin_x + c * (tile_w + margin_x)
        by = 50 + margin_y + r * (tile_h + header_h + margin_y)
        
        oled.render_mood(m)
        
        # Visor outer frame border
        canvas.fill_rect(bx - 4, by - 4, tile_w + 8, tile_h + 8, 30, 36, 46)
        
        # Scale up OLED screen pixels
        for py in range(128):
            for px in range(64):
                si = (px * 128 + py) * 4
                pr = oled.canvas.data[si]
                pg = oled.canvas.data[si + 1]
                pb = oled.canvas.data[si + 2]
                canvas.fill_rect(bx + py * scale, by + px * scale, scale, scale, pr, pg, pb)
                
        # Label below
        canvas.draw_text(label, bx + 6, by + tile_h + 8, 180, 200, 220, scale=1)
        
    write_png(out_path, grid_w, grid_h, canvas.data)
    print(f"Generated {out_path} ({grid_w}x{grid_h})")

def generate_color_themes(out_path):
    themes = [
        ("CYAN", "ELECTRIC CYAN", 0x00F0FF, 0x007799, 0x00D0FF),
        ("GREEN", "MATRIX EMERALD", 0x00FF66, 0x008833, 0x33FF88),
        ("AMBER", "RETRO AMBER", 0xFFAA00, 0x996600, 0xFFCC33),
        ("BLUE", "NEON BLUE", 0x2979FF, 0x1545A5, 0x5393FF),
        ("PURPLE", "CYBERPUNK VIOLET", 0xD500F9, 0x7A008F, 0xE040FB),
        ("WHITE", "HIGH CONTRAST WHITE", 0xFFFFFF, 0x777777, 0xCCCCCC)
    ]
    
    cols = 3
    rows = 2
    scale = 2
    tile_w = 128 * scale
    tile_h = 64 * scale
    margin_x = 24
    margin_y = 24
    header_h = 24
    
    grid_w = cols * tile_w + (cols + 1) * margin_x
    grid_h = rows * (tile_h + header_h) + (rows + 1) * margin_y + 40
    
    canvas = Canvas(grid_w, grid_h, (13, 17, 23, 255))
    canvas.draw_text("SELECTABLE HIGH-CONTRAST OLED SCREEN COLOR THEMES (PRESS X)", margin_x, 14, 0, 255, 136, scale=2)
    
    sample_moods = ["HAPPY", "COOL", "STAR_EYES", "LOVE", "SURPRISED", "THINKING"]
    
    for idx, (t_key, t_name, e_col, dim_col, m_col) in enumerate(themes):
        r = idx // cols
        c = idx % cols
        bx = margin_x + c * (tile_w + margin_x)
        by = 50 + margin_y + r * (tile_h + header_h + margin_y)
        
        cfg = {
            "bg_color": 0x000000,
            "eye_color": e_col,
            "eye_dim": dim_col,
            "mouth_color": m_col,
            "sunglass_frame": e_col
        }
        oled = OLEDDisplay(cfg)
        oled.render_mood(sample_moods[idx])
        
        # Visor outer frame border
        canvas.fill_rect(bx - 4, by - 4, tile_w + 8, tile_h + 8, 30, 36, 46)
        
        # Scale up OLED screen pixels
        for py in range(128):
            for px in range(64):
                si = (px * 128 + py) * 4
                pr = oled.canvas.data[si]
                pg = oled.canvas.data[si + 1]
                pb = oled.canvas.data[si + 2]
                canvas.fill_rect(bx + py * scale, by + px * scale, scale, scale, pr, pg, pb)
                
        # Label below
        rgb = oled.hex_to_rgb(e_col)
        canvas.draw_text(t_name, bx + 6, by + tile_h + 8, rgb[0], rgb[1], rgb[2], scale=1)
        
    write_png(out_path, grid_w, grid_h, canvas.data)
    print(f"Generated {out_path} ({grid_w}x{grid_h})")

if __name__ == "__main__":
    assets_dir = str(config.ASSETS_DIR)
    os.makedirs(assets_dir, exist_ok=True)
    generate_expressions_grid(os.path.join(assets_dir, "expressions_grid.png"))
    generate_color_themes(os.path.join(assets_dir, "color_themes.png"))
