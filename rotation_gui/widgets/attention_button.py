"""Toolbar button with a narrow pulsing edge until it has been opened."""

from __future__ import annotations

import math

from ..qt_compat import QColor, QPainter, QPen, Qt, QTimer, QPushButton


class AttentionButton(QPushButton):
    """Ordinary button plus a one-pixel breathing outline, in the Windows 7 glow style."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self._attention = False
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._advance)

    def set_attention(self, enabled: bool) -> None:
        enabled = bool(enabled) and self.isEnabled()
        if enabled == self._attention:
            self.update()
            return
        self._attention = enabled
        if enabled:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def attention_active(self) -> bool:
        return self._attention

    def _advance(self) -> None:
        self._phase = (self._phase + 0.11) % (2.0 * math.pi)
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._attention:
            return
        # One slow breath, about 1.4 s. The stroke stays a single pixel wide.
        strength = 0.5 + 0.5 * math.sin(self._phase)
        color = QColor(27, 108, 196)
        color.setAlpha(int(40 + 180 * strength))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(color)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rect = self.rect().adjusted(1, 1, -2, -2)
        painter.drawRoundedRect(rect, 4, 4)
        painter.end()

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        if not enabled:
            self.set_attention(False)
