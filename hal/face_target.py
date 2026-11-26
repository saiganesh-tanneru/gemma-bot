"""CamelCase drawing surface the existing FaceRenderer already calls."""

from __future__ import annotations

from hal.interfaces import Display


class FaceDrawTarget:
    """Forwards FaceRenderer draw calls into a Display driver."""

    def __init__(self, display: Display):
        self._display = display

    def setOpacity(self, alpha: float) -> None:
        self._display.set_opacity(alpha)

    def setColor(self, color: int) -> None:
        self._display.set_color(color)

    def fillRectangle(self, x: int, y: int, width: int, height: int) -> None:
        self._display.fill_rectangle(x, y, width, height)

    def drawText(self, text: str, x: int, y: int) -> None:
        self._display.draw_text(text, x, y)
