"""Qt binding selection and optional WebEngine discovery."""

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


def _qt_binding_package_dir() -> Path | None:
    preferred = os.environ.get("ROTATION_GUI_QT_BINDING", "PySide6").strip().lower()
    package_name = "PyQt6" if preferred == "pyqt6" else "PySide6"
    try:
        package = __import__(package_name)
    except ImportError:
        return None
    return Path(package.__file__).resolve().parent


def _prepare_qt_webengine_paths() -> bool:
    """Point Qt WebEngine at helper files bundled with PySide/PyQt wheels."""

    package_dir = _qt_binding_package_dir()
    if package_dir is None:
        return False

    process_candidates = [
        package_dir / "QtWebEngineProcess.exe",
        package_dir / "Qt6" / "bin" / "QtWebEngineProcess.exe",
        package_dir / "Qt" / "bin" / "QtWebEngineProcess.exe",
        package_dir / "Library" / "lib" / "qt6" / "bin" / "QtWebEngineProcess.exe",
        package_dir / "Library" / "bin" / "QtWebEngineProcess.exe",
    ]
    resources_candidates = [
        package_dir / "resources",
        package_dir / "Qt6" / "resources",
        package_dir / "Qt" / "resources",
        package_dir / "Library" / "share" / "qt6" / "resources",
        package_dir / "Library" / "resources",
    ]
    locales_candidates = [
        package_dir / "translations" / "qtwebengine_locales",
        package_dir / "Qt6" / "translations" / "qtwebengine_locales",
        package_dir / "Qt" / "translations" / "qtwebengine_locales",
        package_dir / "Library" / "share" / "qt6" / "translations" / "qtwebengine_locales",
        package_dir / "Library" / "translations" / "qtwebengine_locales",
    ]

    existing_process = os.environ.get("QTWEBENGINEPROCESS_PATH")
    process_path = (
        Path(existing_process)
        if existing_process and Path(existing_process).exists()
        else next((path for path in process_candidates if path.exists()), None)
    )

    existing_resources = os.environ.get("QTWEBENGINE_RESOURCES_PATH")
    resources_path = (
        Path(existing_resources)
        if existing_resources and (Path(existing_resources) / "qtwebengine_resources.pak").exists()
        else next(
            (path for path in resources_candidates if (path / "qtwebengine_resources.pak").exists()),
            None,
        )
    )

    existing_locales = os.environ.get("QTWEBENGINE_LOCALES_PATH")
    locales_path = (
        Path(existing_locales)
        if existing_locales and Path(existing_locales).exists()
        else next((path for path in locales_candidates if path.exists()), None)
    )

    if not process_path:
        return False
    if not resources_path:
        return False
    if not locales_path:
        return False

    os.environ["QTWEBENGINEPROCESS_PATH"] = str(process_path)
    os.environ["QTWEBENGINE_RESOURCES_PATH"] = str(resources_path)
    os.environ["QTWEBENGINE_LOCALES_PATH"] = str(locales_path)
    return True


_prepare_qt_plugin_path()
QT_WEBENGINE_AVAILABLE = _prepare_qt_webengine_paths()


def _load_qt_binding():
    preferred = os.environ.get("ROTATION_GUI_QT_BINDING", "PySide6").strip().lower()
    if preferred != "pyqt6":
        from PySide6.QtCore import QProcess, QProcessEnvironment, QSize, Qt, QTimer, QUrl
        from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
        from PySide6.QtWidgets import (
            QApplication,
            QAbstractItemView,
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
            QTableWidget,
            QTableWidgetItem,
            QTabWidget,
            QTextEdit,
            QToolButton,
            QVBoxLayout,
            QWidget,
        )
        return locals(), "PySide6"

    from PyQt6.QtCore import QProcess, QProcessEnvironment, QSize, Qt, QTimer, QUrl
    from PyQt6.QtGui import QDesktopServices, QIcon, QPixmap
    from PyQt6.QtWidgets import (
        QApplication,
        QAbstractItemView,
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
        QTableWidget,
        QTableWidgetItem,
        QTabWidget,
        QTextEdit,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
    return locals(), "PyQt6"


_qt, QT_BINDING = _load_qt_binding()
globals().update(_qt)
try:
    if not QT_WEBENGINE_AVAILABLE:
        QWebEngineView = None
    elif QT_BINDING == "PyQt6":
        from PyQt6.QtWebEngineWidgets import QWebEngineView
    else:
        from PySide6.QtWebEngineWidgets import QWebEngineView
except Exception:
    QWebEngineView = None


ALIGN_CENTER = Qt.AlignmentFlag.AlignCenter
HORIZONTAL = Qt.Orientation.Horizontal
VERTICAL = Qt.Orientation.Vertical
KEEP_ASPECT = Qt.AspectRatioMode.KeepAspectRatio
SMOOTH_TRANSFORM = Qt.TransformationMode.SmoothTransformation
EXPANDING = QSizePolicy.Policy.Expanding
FIXED = QSizePolicy.Policy.Fixed
PREFERRED = QSizePolicy.Policy.Preferred
STYLED_PANEL = QFrame.Shape.StyledPanel
NO_EDIT_TRIGGERS = QAbstractItemView.EditTrigger.NoEditTriggers
NOT_RUNNING = QProcess.ProcessState.NotRunning
