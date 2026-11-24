#!/usr/bin/env python3
"""
Generates high-contrast visual assets for Gemma-Bot README using the shared
OLED FaceRenderer from controllers/gemma_bot_controller/faces:
1. expressions_grid.png: 5x3 grid of all 15 OLED companion moods & emojis
2. color_themes.png: Showcase of all 6 high-contrast screen color themes
"""

import os
import struct
import sys
import zlib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONTROLLER_DIR = _REPO_ROOT / "controllers" / "gemma_bot_controller"
for _path in (str(_REPO_ROOT), str(_CONTROLLER_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import config
from faces import CanvasTarget, FaceRenderer, SCREEN_THEMES

# 5x7 Pixel Font for Labels & OLED text
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
    '9': [0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C],
}


def write_png(filename, width, height, rgba_data):
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        raw.extend(rgba_data[y * width * 4 : (y + 1) * width * 4])
    compressed = zlib.compress(bytes(raw), 9)

    def chunk(chunk_type, data):
        c = chunk_type + data
        crc = zlib.crc32(c) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + c + struct.pack(">I", crc)

    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr_data) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")
    with open(filename, "wb") as f:
        f.write(png)


class Canvas:
    def __init__(self, w, h, bg_rgba=(10, 12, 16, 255)):
        self.w = w
        self.h = h
        self.data = bytearray(list(bg_rgba) * (w * h))

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
            glyph = FONT_5X7.get(ch, FONT_5X7.get(" "))
            for row_idx, row_val in enumerate(glyph):
                for col_idx in range(5):
                    if (row_val >> (4 - col_idx)) & 1:
                        self.fill_rect(cx + col_idx * scale, y + row_idx * scale, scale, scale, r, g, b)
            cx += 6 * scale


def _blit_oled(dest_canvas, oled_canvas, bx, by, scale):
    for py in range(128):
        for px in range(64):
            si = (px * 128 + py) * 4
            pr = oled_canvas.data[si]
            pg = oled_canvas.data[si + 1]
            pb = oled_canvas.data[si + 2]
            dest_canvas.fill_rect(bx + py * scale, by + px * scale, scale, scale, pr, pg, pb)


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

    cols, rows, scale = 5, 3, 2
    tile_w, tile_h = 128 * scale, 64 * scale
    margin_x, margin_y, header_h = 20, 20, 24
    grid_w = cols * tile_w + (cols + 1) * margin_x
    grid_h = rows * (tile_h + header_h) + (rows + 1) * margin_y + 40

    canvas = Canvas(grid_w, grid_h, (13, 17, 23, 255))
    canvas.draw_text("GEMMA-BOT OLED EMOTIONS & EMOJIS SUITE", margin_x, 14, 0, 240, 255, scale=2)

    oled_canvas = Canvas(128, 64, (0, 0, 0, 255))
    renderer = FaceRenderer(CanvasTarget(oled_canvas), theme="CYAN")

    for idx, (m, label) in enumerate(moods):
        r = idx // cols
        c = idx % cols
        bx = margin_x + c * (tile_w + margin_x)
        by = 50 + margin_y + r * (tile_h + header_h + margin_y)

        renderer.render(m)
        canvas.fill_rect(bx - 4, by - 4, tile_w + 8, tile_h + 8, 30, 36, 46)
        _blit_oled(canvas, oled_canvas, bx, by, scale)
        canvas.draw_text(label, bx + 6, by + tile_h + 8, 180, 200, 220, scale=1)

    write_png(out_path, grid_w, grid_h, canvas.data)
    print(f"Generated {out_path} ({grid_w}x{grid_h})")


def generate_color_themes(out_path):
    theme_order = ["CYAN", "GREEN", "AMBER", "BLUE", "PURPLE", "WHITE"]
    sample_moods = ["HAPPY", "COOL", "STAR_EYES", "LOVE", "SURPRISED", "THINKING"]

    cols, rows, scale = 3, 2, 2
    tile_w, tile_h = 128 * scale, 64 * scale
    margin_x, margin_y, header_h = 24, 24, 24
    grid_w = cols * tile_w + (cols + 1) * margin_x
    grid_h = rows * (tile_h + header_h) + (rows + 1) * margin_y + 40

    canvas = Canvas(grid_w, grid_h, (13, 17, 23, 255))
    canvas.draw_text("SELECTABLE HIGH-CONTRAST OLED SCREEN COLOR THEMES (PRESS X)", margin_x, 14, 0, 255, 136, scale=2)

    oled_canvas = Canvas(128, 64, (0, 0, 0, 255))
    renderer = FaceRenderer(CanvasTarget(oled_canvas), theme="CYAN")

    for idx, t_key in enumerate(theme_order):
        r = idx // cols
        c = idx % cols
        bx = margin_x + c * (tile_w + margin_x)
        by = 50 + margin_y + r * (tile_h + header_h + margin_y)

        theme_cfg = SCREEN_THEMES[t_key]
        renderer.apply_theme(t_key)
        renderer.render(sample_moods[idx])

        canvas.fill_rect(bx - 4, by - 4, tile_w + 8, tile_h + 8, 30, 36, 46)
        _blit_oled(canvas, oled_canvas, bx, by, scale)

        e_col = theme_cfg["eye_color"]
        canvas.draw_text(
            theme_cfg["name"],
            bx + 6,
            by + tile_h + 8,
            (e_col >> 16) & 0xFF,
            (e_col >> 8) & 0xFF,
            e_col & 0xFF,
            scale=1,
        )

    write_png(out_path, grid_w, grid_h, canvas.data)
    print(f"Generated {out_path} ({grid_w}x{grid_h})")


if __name__ == "__main__":
    assets_dir = str(config.ASSETS_DIR)
    os.makedirs(assets_dir, exist_ok=True)
    generate_expressions_grid(os.path.join(assets_dir, "expressions_grid.png"))
    generate_color_themes(os.path.join(assets_dir, "color_themes.png"))
