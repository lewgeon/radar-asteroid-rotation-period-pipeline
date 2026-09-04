"""Preview widgets with inexpensive resize behavior."""

from __future__ import annotations

from pathlib import Path

from ..qt_compat import QLabel, QPixmap, QSizePolicy, QFrame, QTimer, Qt

ALIGN_CENTER = Qt.AlignmentFlag.AlignCenter
KEEP_ASPECT = Qt.AspectRatioMode.KeepAspectRatio
SMOOTH_TRANSFORM = Qt.TransformationMode.SmoothTransformation
EXPANDING = QSizePolicy.Policy.Expanding
STYLED_PANEL = QFrame.Shape.StyledPanel

class ImagePreview(QLabel):
    def __init__(self):
        super().__init__("执行阶段后会在这里显示关键结果。")
        self.setAlignment(ALIGN_CENTER)
        self.setMinimumHeight(130)
        self.setFrameShape(STYLED_PANEL)
        self.setSizePolicy(EXPANDING, EXPANDING)
        self._pixmap: QPixmap | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._apply_scaled_pixmap)

    def set_image(self, path: Path | None, text: str) -> None:
        self._pixmap = QPixmap(str(path)) if path and path.exists() else None
        if self._pixmap is None or self._pixmap.isNull():
            self.setPixmap(QPixmap())
            self.setText(text)
            return
        self.setText("")
        self._apply_scaled_pixmap()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._pixmap and not self._pixmap.isNull():
            self._timer.start(40)

    def _apply_scaled_pixmap(self) -> None:
        if not self._pixmap or self._pixmap.isNull():
            return
        scaled = self._pixmap.scaled(
            self.size(),
            KEEP_ASPECT,
            SMOOTH_TRANSFORM,
        )
        self.setPixmap(scaled)
