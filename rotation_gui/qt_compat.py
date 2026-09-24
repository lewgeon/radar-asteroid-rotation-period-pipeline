"""Qt binding selection and constants used by the desktop GUI."""

from __future__ import annotations

import os
from pathlib import Path


def _prepare_qt_plugin_path() -> None:
    """Point Qt at the plugin directory bundled with the selected binding."""

    preferred = os.environ.get("ROTATION_GUI_QT_BINDING", "PySide6").strip().lower()
    package_name = "PyQt6" if preferred == "pyqt6" else "PySide6"
    try:
        package = __import__(package_name)
    except ImportError:
        return

    package_dir = Path(package.__file__).resolve().parent
    candidates = [
        package_dir / "plugins",
        package_dir / "Qt6" / "plugins",
        package_dir / "Qt" / "plugins",
    ]
    plugin_dir = next((path for path in candidates if (path / "platforms").exists()), None)
    if not plugin_dir:
        return

    os.environ["QT_PLUGIN_PATH"] = str(plugin_dir)
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugin_dir / "platforms")


_prepare_qt_plugin_path()


def _load_qt_binding():
    preferred = os.environ.get("ROTATION_GUI_QT_BINDING", "PySide6").strip().lower()
    if preferred != "pyqt6":
        from PySide6.QtCore import QEvent, QPointF, QProcess, QProcessEnvironment, QRectF, QSize, Qt, QTimer, QUrl
        from PySide6.QtGui import QColor, QBrush, QDesktopServices, QFont, QIcon, QPainter, QPen, QPolygonF
        from PySide6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QFileDialog,
            QFrame,
            QGridLayout,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QProgressBar,
            QScrollArea,
            QSizePolicy,
            QSplitter,
            QStyleFactory,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )
        return locals(), "PySide6"

    from PyQt6.QtCore import QEvent, QPointF, QProcess, QProcessEnvironment, QRectF, QSize, Qt, QTimer, QUrl
    from PyQt6.QtGui import QColor, QBrush, QDesktopServices, QFont, QIcon, QPainter, QPen, QPolygonF
    from PyQt6.QtWidgets import (
        QApplication,
            QCheckBox,
            QComboBox,
            QFileDialog,
            QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QProgressBar,
        QScrollArea,
        QSizePolicy,
        QSplitter,
        QStyleFactory,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
    return locals(), "PyQt6"


_qt, QT_BINDING = _load_qt_binding()
globals().update(_qt)

HORIZONTAL = Qt.Orientation.Horizontal
VERTICAL = Qt.Orientation.Vertical
EXPANDING = QSizePolicy.Policy.Expanding
FIXED = QSizePolicy.Policy.Fixed
NOT_RUNNING = QProcess.ProcessState.NotRunning
