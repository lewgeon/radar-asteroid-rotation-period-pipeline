"""Application startup."""

from __future__ import annotations

import sys

from .qt_compat import QApplication
from .styling import configure_gui_style
from .window import PipelineWindow

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("自转周期测量流水线")
    configure_gui_style(app)
    window = PipelineWindow()
    window.show()
    sys.exit(app.exec())
