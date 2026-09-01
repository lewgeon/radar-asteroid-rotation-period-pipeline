"""PySide6 GUI for the rotation-period measurement pipeline."""

from __future__ import annotations

import copy
import datetime as dt
import html
import json
import os
import re
import sys
import webbrowser
from pathlib import Path

import numpy as np

import pipeline


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
        from PySide6.QtGui import QDesktopServices, QPixmap
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
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )
        return locals(), "PySide6"

    from PyQt6.QtCore import QProcess, QProcessEnvironment, QSize, Qt, QTimer, QUrl
    from PyQt6.QtGui import QDesktopServices, QPixmap
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
        QTextEdit,
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


ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = ROOT / "configs" / "pipeline_example.json"
STATE_DIR = ROOT / ".gui_state"
STATE_PATH = STATE_DIR / "pipeline_gui_state.json"
HISTORY_PATH = STATE_DIR / "history.json"
PREVIEW_DIR = STATE_DIR / "previews"
STAGES = ("observation", "echo", "inversion")
STAGE_LABELS = {
    "observation": "1. 观测解算",
    "echo": "2. 回波仿真",
    "inversion": "3. 周期反演",
}
STAGE_LABELS_EN = {
    "observation": "1. Observation",
    "echo": "2. Echo Simulation",
    "inversion": "3. Period Inversion",
}
GROUP_LABELS = {
    "target": "目标参数",
    "transmitter": "发射站",
    "receiver": "接收站",
    "receive": "接收设置",
    "ephemeris": "星历查询",
    "solver": "求解器",
    "compute": "计算设置",
    "scattering_spot": "散射热点",
    "radar": "雷达参数",
    "waveform": "波形参数",
}
GROUP_LABELS_EN = {
    "target": "Target",
    "transmitter": "Transmitter",
    "receiver": "Receiver",
    "receive": "Receive",
    "ephemeris": "Ephemeris",
    "solver": "Solver",
    "compute": "Compute",
    "scattering_spot": "Scattering Spot",
    "radar": "Radar",
    "waveform": "Waveform",
    "通用参数": "General",
}
STAGE_GROUP_ORDER = {
    "observation": ("通用参数", "target", "transmitter", "receiver", "receive", "ephemeris", "solver"),
    "echo": ("通用参数", "compute", "target", "scattering_spot", "radar", "waveform"),
    "inversion": ("通用参数",),
}
CHOICES = {
    "state": ("static", "linear", "geodetic_fixed", "astropy_geodetic", "horizons_vectors"),
    "device": ("auto", "cuda:0", "cpu"),
    "dtype": ("float32", "float64"),
    "type": ("continuous_wave", "chirp_pulse_train"),
    "object_type": ("null", "smallbody"),
    "query_mode": ("auto", "range", "list"),
    "spin_pole_frame": ("equatorial", "ecliptic"),
}
OPTION_LABELS = {
    "zh": {
        "true": "是",
        "false": "否",
        "continuous_wave": "连续波",
        "chirp_pulse_train": "Chirp 脉冲序列",
        "equatorial": "赤道坐标系",
        "icrs": "赤道坐标系",
        "ecliptic": "黄道坐标系",
        "auto": "自动",
        "range": "范围查询",
        "list": "列表查询",
        "null": "无",
        "smallbody": "小天体",
        "static": "静态位置",
        "linear": "匀速直线",
        "geodetic_fixed": "固定大地坐标",
        "astropy_geodetic": "Astropy 大地坐标",
        "horizons_vectors": "Horizons 星历",
    },
    "en": {
        "true": "Yes",
        "false": "No",
        "continuous_wave": "Continuous Wave",
        "chirp_pulse_train": "Chirp Pulse Train",
        "equatorial": "Equatorial",
        "icrs": "Equatorial",
        "ecliptic": "Ecliptic",
        "auto": "Auto",
        "range": "Range",
        "list": "List",
        "null": "None",
        "smallbody": "Small Body",
        "static": "Static",
        "linear": "Linear",
        "geodetic_fixed": "Geodetic Fixed",
        "astropy_geodetic": "Astropy Geodetic",
        "horizons_vectors": "Horizons Vectors",
    },
}
HORIZONS_ID_TYPE_ALIASES = {
    "": None,
    "none": None,
    "null": None,
    "small body": "smallbody",
    "small_body": "smallbody",
    "small-body": "smallbody",
}
HORIZONS_OBJECT_TYPES = {None, "smallbody"}
STATE_FIELDS = {
    "static": ("position_m",),
    "linear": ("position0_m", "velocity_m_s"),
    "geodetic_fixed": ("lat_deg", "lon_deg", "height_m"),
    "astropy_geodetic": ("lat_deg", "lon_deg", "height_m"),
    "horizons_vectors": ("id", "object_type"),
}
STATE_DEFAULTS = {
    "position_m": [0.0, 0.0, 0.0],
    "position0_m": [0.0, 0.0, 0.0],
    "velocity_m_s": [0.0, 0.0, 0.0],
    "lat_deg": 0.0,
    "lon_deg": 0.0,
    "height_m": 0.0,
    "object_type": None,
}
EPHEMERIS_FIELD_DEFAULTS = {
    "location": "@399",
    "refplane": "earth",
    "padding_s": 7200.0,
    "query_step_s": 60.0,
    "query_mode": "auto",
    "query_chunk_size": 80,
    "min_query_chunk_size": 5,
    "query_retries": 2,
    "cache": True,
}
EPHEMERIS_FIELD_ORDER = (
    "location",
    "refplane",
    "padding_s",
    "query_step_s",
    "query_mode",
    "query_chunk_size",
    "min_query_chunk_size",
    "query_retries",
    "cache",
)
COMMON_FIELD_ORDER = ("id", "name", "state")
PROGRESS_PREFIX = "__PROGRESS__ "
WARNING_PREFIX = "__WARNING__ "
ERROR_PREFIX = "__ERROR__ "
FIELD_LABELS = {
    "id": "ID",
    "name": "名称",
    "state": "状态",
    "position_m": "位置",
    "position0_m": "初始位置",
    "velocity_m_s": "速度",
    "lat_deg": "纬度",
    "lon_deg": "经度",
    "height_m": "高度",
    "object_type": "目标类型",
    "start_utc": "开始时间",
    "duration_s": "接收时长",
    "sample_rate_hz": "采样率",
    "tolerance_s": "收敛阈值",
    "max_iter": "最大迭代",
    "location": "参考中心",
    "refplane": "参考平面",
    "padding_s": "星历余量",
    "query_step_s": "星历步长",
    "query_mode": "查询模式",
    "query_chunk_size": "查询分块",
    "min_query_chunk_size": "最小重试分块",
    "query_retries": "查询重试",
    "cache": "使用缓存",
    "model_path": "形状模型",
    "seed": "随机种子",
    "chunk_size": "计算分块",
    "device": "计算设备",
    "dtype": "浮点精度",
    "rotation_period_s": "自转周期",
    "initial_phase_deg": "初始相位",
    "spin_pole_frame": "坐标系",
    "spin_pole_icrs_deg": "α / δ",
    "spin_pole_ecliptic_deg": "λ / β",
    "scattering_power": "散射指数",
    "direction_body": "斑块方向",
    "enabled": "启用",
    "radius_deg": "斑块半径",
    "strength": "斑块强度",
    "carrier_frequency_hz": "载频",
    "type": "波形类型",
    "amplitude": "幅度",
    "pulse_width_s": "脉冲宽度",
    "bandwidth_hz": "Chirp 带宽",
    "pri_s": "脉冲重复间隔",
    "first_pulse_start_s": "首脉冲起点",
    "pulse_count": "脉冲数量",
    "pulse_start_s": "脉冲起点序列",
    "snr_db": "信噪比",
    "stft_window_samples": "STFT窗长",
    "stft_overlap_fraction": "STFT重叠",
    "period_min_s": "最小周期",
    "period_max_s": "最大周期",
    "period_grid_size": "周期网格数",
}
FIELD_LABELS_EN = {
    "id": "ID",
    "name": "Name",
    "state": "State",
    "position_m": "Position",
    "position0_m": "Initial Position",
    "velocity_m_s": "Velocity",
    "lat_deg": "Latitude",
    "lon_deg": "Longitude",
    "height_m": "Height",
    "object_type": "Object Type",
    "start_utc": "Start UTC",
    "duration_s": "Duration",
    "sample_rate_hz": "Sample Rate",
    "tolerance_s": "Tolerance",
    "max_iter": "Max Iterations",
    "location": "Center",
    "refplane": "Reference Plane",
    "padding_s": "Padding",
    "query_step_s": "Query Step",
    "query_mode": "Query Mode",
    "query_chunk_size": "Query Chunk",
    "min_query_chunk_size": "Min Retry Chunk",
    "query_retries": "Retries",
    "cache": "Use Cache",
    "model_path": "Shape Model",
    "seed": "Seed",
    "chunk_size": "Chunk Size",
    "device": "Device",
    "dtype": "Float Type",
    "rotation_period_s": "Rotation Period",
    "initial_phase_deg": "Initial Phase",
    "spin_pole_frame": "Frame",
    "spin_pole_icrs_deg": "α / δ",
    "spin_pole_ecliptic_deg": "λ / β",
    "scattering_power": "Scattering Power",
    "direction_body": "Spot Direction",
    "enabled": "Enabled",
    "radius_deg": "Spot Radius",
    "strength": "Spot Strength",
    "carrier_frequency_hz": "Carrier Frequency",
    "type": "Waveform",
    "amplitude": "Amplitude",
    "pulse_width_s": "Pulse Width",
    "bandwidth_hz": "Chirp Bandwidth",
    "pri_s": "PRI",
    "first_pulse_start_s": "First Pulse Start",
    "pulse_count": "Pulse Count",
    "pulse_start_s": "Pulse Starts",
    "snr_db": "SNR",
    "stft_window_samples": "STFT Window",
    "stft_overlap_fraction": "STFT Overlap",
    "period_min_s": "Min Period",
    "period_max_s": "Max Period",
    "period_grid_size": "Period Grid Size",
}
FIELD_UNITS = {
    "position_m": "m",
    "position0_m": "m",
    "velocity_m_s": "m/s",
    "lat_deg": "°",
    "lon_deg": "°",
    "height_m": "m",
    "duration_s": "s",
    "sample_rate_hz": "Hz",
    "tolerance_s": "s",
    "padding_s": "s",
    "query_step_s": "s",
    "rotation_period_s": "s",
    "initial_phase_deg": "°",
    "spin_pole_icrs_deg": "°",
    "spin_pole_ecliptic_deg": "°",
    "radius_deg": "°",
    "carrier_frequency_hz": "Hz",
    "pulse_width_s": "s",
    "bandwidth_hz": "Hz",
    "pri_s": "s",
    "first_pulse_start_s": "s",
    "snr_db": "dB",
    "period_min_s": "s",
    "period_max_s": "s",
}
UNIT_CHOICES = {
    "rotation_period_s": (("h", 3600.0), ("s", 1.0)),
    "period_min_s": (("h", 3600.0), ("s", 1.0)),
    "period_max_s": (("h", 3600.0), ("s", 1.0)),
    "carrier_frequency_hz": (("GHz", 1.0e9), ("MHz", 1.0e6), ("Hz", 1.0)),
    "bandwidth_hz": (("MHz", 1.0e6), ("kHz", 1.0e3), ("Hz", 1.0)),
    "sample_rate_hz": (("MHz", 1.0e6), ("kHz", 1.0e3), ("Hz", 1.0)),
}
CONTROL_HEIGHT = 32
GUI_STYLE = """
QWidget { font-family: "Microsoft YaHei", "Segoe UI"; font-size: 13px; color: #25354a; }
QMainWindow { background: #f3f5f8; }
QGroupBox { border: 1px solid #dce2eb; border-radius: 8px;
    margin-top: 12px; padding-top: 12px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
QScrollArea { border: none; background: transparent; }
QWidget#parameterCanvas, QWidget#parameterCards { background: #f3f5f8; }
QFrame#parameterCard { background: white; border: 1px solid #dce2eb; border-radius: 8px; }
QLabel#cardTitle { font-size: 16px; font-weight: 600; color: #193b61;
    background: #eff5fc; border: none; border-left: 3px solid #3979bf;
    border-radius: 3px; padding: 4px 9px; }
QLabel#subsectionTitle { font-size: 13px; font-weight: 600; color: #526882;
    border-top: 1px solid #e8edf3; padding-top: 8px; }
QLineEdit, QComboBox { background: white; border: 1px solid #cbd5e1;
    border-radius: 5px; padding: 0 8px; min-height: 30px; selection-background-color: #d9e9fb; }
QLineEdit:focus, QComboBox:focus { border-color: #3979bf; }
QComboBox { padding-right: 24px; combobox-popup: 0; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background: white; border: 1px solid #9bafc5;
    selection-background-color: #dbeafb; selection-color: #193b61; outline: 0; }
QWidget#unitValue { background: white; border: 1px solid #cbd5e1; border-radius: 5px; }
QWidget#unitValue QLineEdit { border: none; background: transparent; min-height: 0; }
QWidget#unitValue QLineEdit:focus { background: #edf5ff; }
QWidget#unitValue QLabel#unitSuffix, QWidget#unitValue QComboBox#unitSuffix {
    background: #f0f4f8; color: #526882; border: none; border-left: 1px solid #dce2eb;
    border-radius: 0; min-height: 0; padding: 0 6px; font-size: 12px; }
QWidget#unitValue QComboBox#unitSuffix { padding-right: 16px; }
QWidget#unitValue QComboBox#unitSuffix::drop-down { width: 16px; }
QLabel#componentLabel { color: #60738c; font-size: 12px; }
QPushButton { background: white; border: 1px solid #cbd5e1; border-radius: 5px;
    padding: 6px 10px; min-height: 20px; }
QPushButton:hover { background: #edf4fc; border-color: #92b4da; }
QPushButton:disabled { color: #94a3b8; background: #f1f4f8; }
QPushButton#runButton { background: #2868ab; color: white; border-color: #2868ab; font-weight: 600; }
QPushButton#runButton:disabled { background: #a7bfd9; border-color: #a7bfd9; }
QPushButton[activeStage="true"] { background: #e7f0fb; border-color: #9dbfe5; color: #215b99; font-weight: 600; }
QTableWidget, QTextEdit { background: white; border: 1px solid #dce2eb; border-radius: 4px; }
QHeaderView::section { background: #edf2f8; border: none; padding: 5px; }
QProgressBar { border: 1px solid #dce2eb; background: white; border-radius: 4px;
    text-align: center; min-height: 22px; }
QProgressBar::chunk { background: #b3d2f1; border-radius: 3px; }
QSplitter::handle { background: #e3e9f0; }
QScrollBar:vertical { background: #e8edf3; width: 12px; margin: 0; border-radius: 6px; }
QScrollBar:horizontal { background: #e8edf3; height: 12px; margin: 0; border-radius: 6px; }
QScrollBar::handle:vertical { background: #71859d; min-height: 32px; border: 2px solid #e8edf3; border-radius: 6px; }
QScrollBar::handle:horizontal { background: #71859d; min-width: 32px; border: 2px solid #e8edf3; border-radius: 6px; }
QScrollBar::handle:hover { background: #486785; }
QScrollBar::handle:pressed { background: #28598a; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; border-radius: 4px; }
QCheckBox::indicator:unchecked { background: white; border: 2px solid #71859d; }
QCheckBox::indicator:unchecked:hover { border-color: #2868ab; background: #edf5ff; }
QCheckBox::indicator:checked { background: #2868ab; border: 2px solid #2868ab; }
QCheckBox::indicator:checked:hover { background: #1e558e; border-color: #1e558e; }
"""
GUI_STYLE += (
    'QComboBox::down-arrow { image: url("'
    + (ROOT / "assets/gui/chevron-down.svg").as_posix()
    + '"); width: 10px; height: 6px; }'
)
GUI_STYLE += (
    'QCheckBox::indicator:checked { image: url("'
    + (ROOT / "assets/gui/check.svg").as_posix()
    + '"); }'
)
SCATTERING_SPOT_DEFAULTS = {
    "enabled": True,
    "direction_body": [1.0, 0.25, 0.15],
    "radius_deg": 12.0,
    "strength": 8.0,
}


def read_json(path: Path, fallback):
    if not path.exists():
        return copy.deepcopy(fallback)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} 不是有效 JSON：{exc}") from exc


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def now_text() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_value(raw: str):
    text = raw.strip()
    if text == "":
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return raw


def format_value(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def flatten(prefix: str, value):
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else key
            yield from flatten(child_prefix, child)
    else:
        yield prefix, value


def assign_path(payload: dict, dotted_path: str, value) -> None:
    current = payload
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


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


class NoWheelComboBox(QComboBox):
    """A combo box that ignores mouse-wheel changes to avoid accidental edits."""

    def wheelEvent(self, event) -> None:
        event.ignore()


def configure_gui_style(app):
    """Use native Windows combo transitions, retaining Fusion as a fallback."""
    styles = {name.lower(): name for name in QStyleFactory.keys()}
    app.setStyle(next((styles[name] for name in ("windowsvista", "windows11", "windows") if name in styles), "Fusion"))
    app.setEffectEnabled(Qt.UIEffect.UI_AnimateCombo, True)


class ParameterCards(QWidget):
    """Stable semantic lanes, with explicit compact and wide-screen layouts."""

    def __init__(self, cards, stage, on_layout_changed=None):
        super().__init__()
        self.setObjectName("parameterCards")
        self.cards = cards
        self.stage = stage
        self.on_layout_changed = on_layout_changed
        self.layout_mode = "compact"
        self.column_count = 1
        self.gap = 14
        for card in cards:
            card.setParent(self)
            card.ensurePolished()
        self.card_minimum = max([360] + [card.minimumSizeHint().width() for card in cards])
        self.setMinimumWidth(self.card_minimum)
        self.setSizePolicy(EXPANDING, FIXED)
        QTimer.singleShot(0, self.reflow)

    def sizeHint(self):
        return QSize(self.card_minimum, self.minimumHeight())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def reflow(self):
        wide = self.width() >= max(1320, self.card_minimum * 3 + self.gap * 2)
        compact_lanes = {
            "observation": (("target", "transmitter", "receiver"), ("receive", "ephemeris", "solver")),
            "echo": (("通用参数", "signal", "compute"), ("target", "scattering_spot")),
            "inversion": (("spectrum",), ("period_search",)),
        }
        wide_lanes = {
            "observation": (("target",), ("transmitter", "receiver"), ("receive", "ephemeris", "solver")),
            "echo": (("通用参数", "compute"), ("target", "scattering_spot"), ("signal",)),
            "inversion": (("spectrum",), ("period_search",)),
        }
        lanes = (wide_lanes if wide else compact_lanes)[self.stage]
        if self.width() < self.card_minimum * 2 + self.gap:
            lanes = (tuple(name for lane in lanes for name in lane),)
        self.layout_mode = "wide" if wide else "compact"
        self.column_count = len(lanes)
        lane_map = {name: column for column, lane in enumerate(lanes) for name in lane}
        cards_by_name = {card.property("groupName"): card for card in self.cards}
        order = [name for lane in lanes for name in lane if name in cards_by_name]
        order.extend(name for name in cards_by_name if name not in lane_map)
        available = min(self.width() - self.gap * (self.column_count - 1), self.column_count * 620)
        heights = [0] * self.column_count
        for name in order:
            card = cards_by_name[name]
            column = lane_map.get(name, self.column_count - 1)
            left = column * available // self.column_count + column * self.gap
            right = (column + 1) * available // self.column_count + column * self.gap
            card.layout().itemAt(1).layout().invalidate()
            card.layout().invalidate()
            height = max(card.sizeHint().height(), card.minimumSizeHint().height())
            card.setGeometry(left, heights[column], right - left, height)
            heights[column] += height + self.gap
        self.setFixedHeight(max(0, max(heights) - self.gap))
        if self.on_layout_changed:
            self.on_layout_changed()


class UnitValueWidget(QWidget):
    def __init__(self, value, unit_options: tuple[tuple[str, float], ...], editable_unit: bool = False):
        super().__init__()
        self.setObjectName("unitValue")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(CONTROL_HEIGHT)
        self.setSizePolicy(EXPANDING, FIXED)
        self.unit_options = unit_options
        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.edit = QLineEdit()
        self.edit.setMinimumWidth(64)
        self.edit.setFixedHeight(CONTROL_HEIGHT - 2)
        unit_label, multiplier = self._best_unit(float(value) if isinstance(value, (int, float)) else 0.0)
        self.edit.setText(format_value(float(value) / multiplier if isinstance(value, (int, float)) else value))
        layout.addWidget(self.edit, 1)
        if editable_unit and len(unit_options) > 1:
            self.unit_combo = NoWheelComboBox()
            for label, factor in unit_options:
                self.unit_combo.addItem(label, factor)
            self.unit_combo.setCurrentText(unit_label)
            self.unit_combo.setObjectName("unitSuffix")
            longest = max(len(label) for label, _ in unit_options)
            self.unit_combo.setFixedSize(68 if longest > 2 else 48, CONTROL_HEIGHT - 2)
            self.unit_combo.setToolTip("切换输入单位 / Select input unit")
            layout.addWidget(self.unit_combo)
            self.unit_suffix = self.unit_combo
        else:
            self.unit_combo = None
            unit = QLabel(unit_options[0][0])
            unit.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            unit.setObjectName("unitSuffix")
            unit.setFixedSize(42 if len(unit_options[0][0]) > 2 else 32, CONTROL_HEIGHT - 2)
            unit.setToolTip("固定单位 / Fixed unit")
            layout.addWidget(unit)
            self.unit_suffix = unit
            unit.setVisible(bool(unit_options[0][0]))
        self.setFocusProxy(self.edit)

    def _best_unit(self, value: float) -> tuple[str, float]:
        abs_value = abs(value)
        for label, multiplier in self.unit_options:
            if multiplier > 1.0 and abs_value >= multiplier:
                return label, multiplier
        return self.unit_options[-1]

    def sizeHint(self):
        return QSize(super().sizeHint().width(), CONTROL_HEIGHT)

    def value(self):
        raw = parse_value(self.edit.text())
        if not isinstance(raw, (int, float)):
            return raw
        multiplier = self.unit_combo.currentData() if self.unit_combo else self.unit_options[0][1]
        return float(raw) * float(multiplier)


class VectorValueWidget(QWidget):
    def __init__(self, value, labels: tuple[str, ...], unit: str | None = None):
        super().__init__()
        values = list(value) if isinstance(value, list) else []
        stacked = len(labels) > 2
        layout = QVBoxLayout(self) if stacked else QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.edits: list[QLineEdit] = []
        for index, label_text in enumerate(labels):
            row = QHBoxLayout() if stacked else QVBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(4)
            label = QLabel(label_text)
            label.setObjectName("componentLabel")
            label.setFixedHeight(22)
            if stacked:
                label.setFixedWidth(18)
            row.addWidget(label)
            value_widget = UnitValueWidget(
                values[index] if index < len(values) else 0.0,
                ((unit, 1.0),) if unit else (("", 1.0),),
                editable_unit=False,
            )
            edit = value_widget.edit
            edit.setAccessibleName(label_text)
            label.setBuddy(edit)
            self.edits.append(edit)
            row.addWidget(value_widget, 1)
            layout.addLayout(row, 1)
        self.setSizePolicy(EXPANDING, FIXED)
        self.setFixedHeight(len(labels) * CONTROL_HEIGHT + (len(labels) - 1) * 10 if stacked else CONTROL_HEIGHT + 26)

    def value(self):
        return [parse_value(edit.text()) for edit in self.edits]


class DirectionBodyWidget(VectorValueWidget):
    def __init__(self, value, language: str = "zh"):
        vector = np_vector3(value)
        lon_rad = np.arctan2(vector[1], vector[0])
        lat_rad = np.arcsin(np.clip(vector[2] / np.linalg.norm(vector), -1.0, 1.0))
        labels = ("本体系经度", "本体系纬度") if language == "zh" else ("Body longitude", "Body latitude")
        super().__init__([float(np.rad2deg(lon_rad)), float(np.rad2deg(lat_rad))], labels, "°")
        self.lon_edit, self.lat_edit = self.edits

    def value(self):
        lon = np.deg2rad(float(parse_value(self.lon_edit.text())))
        lat = np.deg2rad(float(parse_value(self.lat_edit.text())))
        return [
            float(np.cos(lat) * np.cos(lon)),
            float(np.cos(lat) * np.sin(lon)),
            float(np.sin(lat)),
        ]


def np_vector3(value) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if array.shape != (3,) or not np.isfinite(array).all() or np.linalg.norm(array) == 0.0:
        return np.array([1.0, 0.0, 0.0], dtype=float)
    return array


class PipelineWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("自转周期测量流水线")
        self.resize(1360, 860)
        self.setMinimumSize(1100, 700)

        self.config_path = DEFAULT_CONFIG_PATH
        self.config_source_text = ""
        self.config_data = self._load_initial_config()
        self.current_stage = STAGES[0]
        self.stage_status = {stage: "待执行" for stage in STAGES}
        self.language = "zh"
        self.field_widgets: dict[str, QWidget] = {}
        self.monostatic_observation = self._is_monostatic_observation()
        self.monostatic_checkbox: QCheckBox | None = None
        self.latest_image_path: Path | None = None
        self.latest_result_path: Path | None = None
        self.latest_plotly_path: Path | None = None
        self.process: QProcess | None = None
        self.process_stage: str | None = None
        self.process_run_dir: Path | None = None
        self.process_log_path: Path | None = None
        self.process_output_buffer = ""
        self.stop_requested = False

        self._migrate_config()
        self._build_ui()
        self._render_stage_buttons()
        self._render_current_stage()
        self._render_history()
        self._append_log(f"[{now_text()}] 当前参数来源：{self.config_source_text}")

    def _load_initial_config(self):
        disk_config = read_json(DEFAULT_CONFIG_PATH, pipeline.DEFAULT_CONFIG)
        state = read_json(STATE_PATH, {})
        if isinstance(state, dict) and isinstance(state.get("config"), dict):
            self.config_source_text = f"GUI 状态文件 {STATE_PATH}"
            saved_path = state.get("config_path")
            if saved_path:
                self.config_path = Path(saved_path)
            return state["config"]
        self.config_source_text = f"磁盘配置 {DEFAULT_CONFIG_PATH}"
        return disk_config

    def _build_ui(self) -> None:
        self.setStyleSheet(GUI_STYLE)
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(14, 12, 14, 10)
        root_layout.setSpacing(10)

        config_row = QHBoxLayout()
        self.config_path_edit = QLineEdit(str(self.config_path))
        open_btn = QPushButton("打开")
        load_btn = QPushButton("载入")
        self.open_config_btn = open_btn
        self.load_config_btn = load_btn
        self.config_file_label = QLabel("配置文件")
        self.language_combo = NoWheelComboBox()
        self.language_combo.addItem("中文", "zh")
        self.language_combo.addItem("English", "en")
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        open_btn.clicked.connect(self._choose_config)
        load_btn.clicked.connect(self._load_config_from_entry)
        config_row.addWidget(self.config_file_label)
        config_row.addWidget(self.config_path_edit, 1)
        config_row.addWidget(open_btn)
        config_row.addWidget(load_btn)
        self.language_label = QLabel("语言")
        config_row.addWidget(self.language_label)
        config_row.addWidget(self.language_combo)
        root_layout.addLayout(config_row)

        run_row = QHBoxLayout()
        self.run_name_edit = QLineEdit(self.config_path.stem)
        self.runs_dir_edit = QLineEdit("runs")
        self.python_edit = QLineEdit(sys.executable)
        self.run_name_label = QLabel("实验名")
        self.runs_dir_label = QLabel("输出目录")
        self.python_label = QLabel("Python")
        run_row.addWidget(self.run_name_label)
        run_row.addWidget(self.run_name_edit, 1)
        run_row.addWidget(self.runs_dir_label)
        run_row.addWidget(self.runs_dir_edit, 1)
        run_row.addWidget(self.python_label)
        run_row.addWidget(self.python_edit, 2)
        root_layout.addLayout(run_row)

        main_splitter = QSplitter(HORIZONTAL)
        main_splitter.setChildrenCollapsible(False)
        root_layout.addWidget(main_splitter, 1)

        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 8, 0)
        sidebar_layout.setSpacing(8)
        self.stage_box = QGroupBox("流水线阶段")
        self.stage_layout = QVBoxLayout(self.stage_box)
        self.stage_layout.setSpacing(6)
        sidebar_layout.addWidget(self.stage_box)

        self.next_btn = QPushButton("执行下一步")
        self.next_btn.setObjectName("runButton")
        self.next_btn.clicked.connect(self._run_current_stage)
        self.stop_btn = QPushButton("中止")
        self.stop_btn.clicked.connect(self._stop_current_stage)
        self.stop_btn.setEnabled(False)
        save_btn = QPushButton("保存参数")
        save_btn.clicked.connect(self._save_current_config)
        save_as_btn = QPushButton("另存 JSON")
        save_as_btn.clicked.connect(self._save_config_as_json)
        self.save_btn = save_btn
        self.save_as_btn = save_as_btn
        sidebar_layout.addWidget(self.next_btn)
        sidebar_layout.addWidget(self.stop_btn)
        sidebar_layout.addWidget(save_btn)
        sidebar_layout.addWidget(save_as_btn)

        self.history_table = QTableWidget(0, 3)
        self.history_table.setHorizontalHeaderLabels(("时间", "阶段", "状态"))
        history_header = self.history_table.horizontalHeader()
        history_header.setSectionResizeMode(0, history_header.ResizeMode.Fixed)
        history_header.setSectionResizeMode(1, history_header.ResizeMode.Stretch)
        history_header.setSectionResizeMode(2, history_header.ResizeMode.Fixed)
        self.history_table.setColumnWidth(0, 86)
        self.history_table.setColumnWidth(2, 54)
        self.history_table.setWordWrap(False)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setEditTriggers(NO_EDIT_TRIGGERS)
        sidebar_layout.addWidget(self.history_table, 1)

        main_splitter.addWidget(sidebar)
        sidebar.setMinimumWidth(230)
        sidebar.setMaximumWidth(320)

        work_splitter = QSplitter(VERTICAL)
        self.work_splitter = work_splitter
        self._workspace_layout_key = None
        self._workspace_layout_timer = QTimer(self)
        self._workspace_layout_timer.setSingleShot(True)
        self._workspace_layout_timer.timeout.connect(self._adapt_workspace)
        work_splitter.setChildrenCollapsible(False)
        main_splitter.addWidget(work_splitter)
        main_splitter.setSizes((240, 1100))
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)

        self.params_group = QGroupBox("阶段参数")
        self.params_group.setMinimumHeight(240)
        params_outer = QVBoxLayout(self.params_group)
        self.params_scroll = QScrollArea()
        self.params_scroll.setWidgetResizable(True)
        self.params_container = QWidget()
        self.params_container.setObjectName("parameterCanvas")
        self.params_layout = QVBoxLayout(self.params_container)
        self.params_layout.setContentsMargins(8, 8, 8, 8)
        self.params_layout.setSpacing(14)
        self.params_scroll.setWidget(self.params_container)
        params_outer.addWidget(self.params_scroll)
        work_splitter.addWidget(self.params_group)

        bottom_splitter = QSplitter(HORIZONTAL)
        self.bottom_splitter = bottom_splitter
        bottom_splitter.setChildrenCollapsible(False)
        work_splitter.addWidget(bottom_splitter)
        work_splitter.setSizes((590, 230))
        work_splitter.setStretchFactor(0, 3)
        work_splitter.setStretchFactor(1, 1)

        log_group = QGroupBox("执行日志")
        self.log_group = log_group
        log_layout = QVBoxLayout(log_group)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        log_layout.addWidget(self.log_edit)
        bottom_splitter.addWidget(log_group)

        result_group = QGroupBox("结果预览")
        self.result_group = result_group
        result_layout = QVBoxLayout(result_group)
        result_head = QHBoxLayout()
        self.result_status = QLabel("执行阶段后会在这里显示关键结果。")
        self.result_status.setWordWrap(True)
        self.open_result_btn = QPushButton("打开结果")
        self.open_3d_btn = QPushButton("打开 3D")
        self.open_result_btn.setEnabled(False)
        self.open_3d_btn.setEnabled(False)
        self.open_result_btn.clicked.connect(self._open_latest_result)
        self.open_3d_btn.clicked.connect(self._open_plotly)
        result_head.addWidget(self.result_status, 1)
        result_head.addWidget(self.open_result_btn)
        result_head.addWidget(self.open_3d_btn)
        result_layout.addLayout(result_head)
        self.preview = ImagePreview()
        result_layout.addWidget(self.preview, 1)
        self.web_preview = QWebEngineView() if QWebEngineView else None
        if self.web_preview:
            result_layout.addWidget(self.web_preview, 1)
            self.web_preview.hide()
        bottom_splitter.addWidget(result_group)
        bottom_splitter.setSizes((650, 430))

        progress_row = QHBoxLayout()
        self.status_label = QLabel("就绪")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("就绪")
        progress_row.addWidget(self.status_label, 1)
        progress_row.addWidget(self.progress_bar, 2)
        root_layout.addLayout(progress_row)
        self._apply_language()
        self._workspace_layout_timer.start(0)

    def _adapt_workspace(self):
        """Rebalance only on stage/breakpoint changes; preserve manual splitter drags."""
        if not hasattr(self, "parameter_cards"):
            return
        mode = self.parameter_cards.layout_mode
        key = (self.current_stage, mode)
        if key == self._workspace_layout_key:
            return
        self._workspace_layout_key = key
        height = self.work_splitter.height()
        if self.current_stage == "inversion":
            parameter_height = min(max(240, self.parameter_cards.height() + 80), int(height * 0.55))
        else:
            parameter_height = int(height * (0.68 if mode == "wide" else 0.72))
        self.work_splitter.setSizes((parameter_height, height - parameter_height))
        width = self.bottom_splitter.width()
        log_share = 0.34 if mode == "wide" else 0.5
        self.bottom_splitter.setSizes((int(width * log_share), int(width * (1 - log_share))))

    def _tr(self, zh: str, en: str) -> str:
        return zh if self.language == "zh" else en

    def _stage_label(self, stage: str) -> str:
        labels = STAGE_LABELS if self.language == "zh" else STAGE_LABELS_EN
        return labels[stage]

    def _group_label(self, group_name: str) -> str:
        labels = GROUP_LABELS if self.language == "zh" else GROUP_LABELS_EN
        return labels.get(group_name, group_name)

    def _option_label(self, value) -> str:
        text = "null" if value is None else str(value)
        return OPTION_LABELS.get(self.language, {}).get(text, text)

    def _status_text(self, value: str) -> str:
        if self.language == "zh":
            return value
        return {
            "待执行": "Pending",
            "运行中": "Running",
            "执行中": "Running",
            "中止中": "Stopping",
            "已完成": "Done",
            "完成": "Done",
            "已中止": "Stopped",
            "中止": "Stopped",
            "失败": "Failed",
            "成功": "Success",
        }.get(value, value)

    def _apply_language(self) -> None:
        self.setWindowTitle(self._tr("自转周期测量流水线", "Rotation Period Measurement Pipeline"))
        self.config_file_label.setText(self._tr("配置文件", "Config"))
        self.language_label.setText(self._tr("语言", "Language"))
        self.open_config_btn.setText(self._tr("打开", "Browse"))
        self.load_config_btn.setText(self._tr("载入", "Load"))
        self.run_name_label.setText(self._tr("实验名", "Run Name"))
        self.runs_dir_label.setText(self._tr("输出目录", "Output Dir"))
        self.python_label.setText("Python")
        self.stage_box.setTitle(self._tr("流水线阶段", "Pipeline Stages"))
        self.next_btn.setText(self._tr("执行下一步", "Run Next Step"))
        self.stop_btn.setText(self._tr("中止", "Stop"))
        self.save_btn.setText(self._tr("保存参数", "Save Parameters"))
        self.save_as_btn.setText(self._tr("另存 JSON", "Save JSON As"))
        self.history_table.setHorizontalHeaderLabels(
            (
                self._tr("时间", "Time"),
                self._tr("阶段", "Stage"),
                self._tr("状态", "Status"),
            )
        )
        self.params_group.setTitle(f"{self._stage_label(self.current_stage)} {self._tr('参数', 'Parameters')}")
        self.log_group.setTitle(self._tr("执行日志", "Log"))
        self.result_group.setTitle(self._tr("结果预览", "Preview"))
        self.open_result_btn.setText(self._tr("打开结果", "Open Result"))
        self.open_3d_btn.setText(self._tr("打开 3D", "Open 3D"))
        if self.process is None:
            self.status_label.setText(self._tr("就绪", "Ready"))
            self.progress_bar.setFormat(self._tr("就绪", "Ready"))
        self._render_stage_buttons()
        self._render_current_stage()

    def _on_language_changed(self) -> None:
        data = self.language_combo.currentData()
        self.language = data if data in {"zh", "en"} else "zh"
        self._sync_stage_from_fields()
        self._apply_language()
        self._render_history()

    def _render_stage_buttons(self) -> None:
        while self.stage_layout.count():
            item = self.stage_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.deleteLater()
        for stage in STAGES:
            btn = QPushButton(f"{self._stage_label(stage)}  {self._status_text(self.stage_status[stage])}")
            btn.setProperty("activeStage", stage == self.current_stage)
            btn.clicked.connect(lambda _checked=False, value=stage: self._select_stage(value))
            self.stage_layout.addWidget(btn)
        self.stage_layout.addStretch(1)

    def _render_current_stage(self) -> None:
        self._migrate_config()
        self._clear_layout(self.params_layout)
        self.field_widgets.clear()
        self.monostatic_checkbox = None
        self.params_group.setTitle(f"{self._stage_label(self.current_stage)} {self._tr('参数', 'Parameters')}")
        if self.current_stage == "observation":
            self.monostatic_checkbox = QCheckBox(
                self._tr("单基站观测：接收站沿用发射站参数", "Monostatic: receiver uses transmitter parameters")
            )
            self.monostatic_checkbox.setChecked(self.monostatic_observation)
            self.monostatic_checkbox.toggled.connect(self._on_monostatic_toggled)
            self.params_layout.addWidget(self.monostatic_checkbox)
        stage_data = self.config_data.get(self.current_stage, {})
        self._render_stage_group_boxes(self._stage_groups(stage_data))
        self.params_layout.addStretch(1)

    def _render_stage_group_boxes(self, groups) -> None:
        # Presentation groups contain original config paths, never new JSON keys.
        sections = {}
        for group_name, values in groups:
            for relative_path, value in self._ordered_group_fields(values):
                path = relative_path if group_name == "通用参数" else f"{group_name}.{relative_path}"
                section = group_name
                if self.current_stage == "echo":
                    if group_name in {"radar", "waveform"}:
                        section = "signal"
                    elif path in {"seed", "chunk_size"}:
                        section = "compute"
                elif self.current_stage == "inversion" and group_name == "通用参数":
                    if path.startswith("stft_"):
                        section = "spectrum"
                    elif path.startswith("period_"):
                        section = "period_search"
                sections.setdefault(section, []).append((path, value))
        if self.current_stage == "echo":
            order = ("通用参数", "target", "signal", "scattering_spot", "compute")
        elif self.current_stage == "observation":
            order = ("receive", "target", "transmitter", "receiver", "ephemeris", "solver")
        else:
            order = ("spectrum", "period_search")
        names = sorted(sections, key=lambda name: order.index(name) if name in order else len(order))
        cards = [self._create_group_box(name, sections[name]) for name in names]
        self.parameter_cards = ParameterCards(cards, self.current_stage, lambda: self._workspace_layout_timer.start(0))
        self.params_layout.addWidget(self.parameter_cards)

    def _create_group_box(self, group_name: str, fields) -> QFrame:
        titles = {
            "signal": self._tr("雷达与波形", "Radar & Waveform"),
            "spectrum": self._tr("时频分析", "Time–Frequency Analysis"),
            "period_search": self._tr("周期搜索", "Period Search"),
        }
        title = titles.get(group_name, self._group_label(group_name))
        if self.current_stage == "echo" and group_name == "通用参数":
            title = self._tr("模型与散射", "Model & Scattering")
        group = QFrame()
        group.setObjectName("parameterCard")
        group.setProperty("groupName", group_name)
        group.setAccessibleName(title)
        outer = QVBoxLayout(group)
        outer.setContentsMargins(16, 14, 16, 16)
        outer.setSpacing(14)
        header = QLabel(title)
        header.setObjectName("cardTitle")
        outer.addWidget(header)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        self._render_group_fields(grid, group_name, fields)
        outer.addLayout(grid)
        group.setSizePolicy(EXPANDING, FIXED)
        return group

    def _stage_groups(self, stage_data: dict):
        groups = []
        loose = {}
        for key, value in stage_data.items():
            if self.current_stage == "observation" and self.monostatic_observation and key == "receiver":
                continue
            if isinstance(value, dict):
                groups.append((key, value))
            else:
                loose[key] = value
        if loose:
            groups.insert(0, ("通用参数", loose))
        order = STAGE_GROUP_ORDER.get(self.current_stage, ())
        return sorted(groups, key=lambda item: order.index(item[0]) if item[0] in order else len(order))

    def _render_group_fields(self, grid: QGridLayout, group_name: str, fields) -> None:
        row = 0
        spin_header_added = False
        for full_path, value in fields:
            key = full_path.split(".")[-1]
            is_spin = full_path.startswith("target.spin_pole_")
            if is_spin and not spin_header_added:
                header = QLabel(self._tr("自转轴", "Spin Axis"))
                header.setObjectName("subsectionTitle")
                grid.addWidget(header, row, 0, 1, 2)
                row += 1
                spin_header_added = True
            label = QLabel(self._display_label(full_path))
            label.setObjectName("fieldLabel")
            label.setProperty("configPath", full_path)
            widget = self._field_widget(full_path, value)
            widget.setToolTip(full_path)
            widget.setAccessibleName(self._display_label(full_path))
            label.setBuddy(widget)
            self.field_widgets[full_path] = widget
            if isinstance(widget, VectorValueWidget):
                if not is_spin:
                    grid.addWidget(label, row, 0, 1, 2)
                    row += 1
                else:
                    label.deleteLater()
                grid.addWidget(widget, row, 0, 1, 2)
                row += 1
            elif key in {"model_path", "observation_info_path", "pulse_start_s", "start_utc"}:
                grid.addWidget(label, row, 0, 1, 2)
                grid.addWidget(widget, row + 1, 0, 1, 2)
                row += 2
            else:
                label.setMinimumWidth(84 if self.language == "zh" else 120)
                grid.addWidget(label, row, 0)
                grid.addWidget(widget, row, 1)
                row += 1
        grid.setColumnStretch(1, 1)

    def _field_widget(self, full_path: str, value):
        key = full_path.split(".")[-1]
        if key in CHOICES or isinstance(value, bool):
            combo = NoWheelComboBox()
            choices = (True, False) if isinstance(value, bool) else self._choices_for_field(full_path)
            current = "true" if value is True else "false" if value is False else format_value(value)
            for item in choices:
                data = "true" if item is True else "false" if item is False else str(item)
                combo.addItem(self._option_label(data), data)
            existing_data = [combo.itemData(i) for i in range(combo.count())]
            if current == "icrs":
                current = "equatorial"
            if current not in existing_data:
                combo.insertItem(0, self._option_label(current), current)
            index = combo.findData(current)
            combo.setCurrentIndex(max(0, index))
            if key == "state":
                combo.currentTextChanged.connect(lambda _text, path=full_path: self._on_state_changed(path))
            if key == "spin_pole_frame":
                combo.currentTextChanged.connect(lambda _text, path=full_path: self._on_spin_pole_frame_changed(path))
            if full_path == "waveform.type":
                combo.currentTextChanged.connect(lambda _text: self._on_waveform_type_changed())
            if full_path == "scattering_spot.enabled":
                combo.currentTextChanged.connect(lambda _text: self._on_spot_enabled_changed())
            self._apply_field_width(combo, full_path, value)
            return combo

        custom = self._custom_value_widget(full_path, value)
        if custom is not None:
            self._apply_field_width(custom, full_path, value)
            return custom

        edit = QLineEdit(format_value(value))
        self._apply_field_width(edit, full_path, value)
        unit = FIELD_UNITS.get(key)
        if unit:
            edit.setPlaceholderText(unit)
            edit.setToolTip(f"单位：{unit}；配置字段：{full_path}")
        else:
            edit.setToolTip(f"配置字段：{full_path}")
        return edit

    def _apply_field_width(self, widget: QWidget, full_path: str, value) -> None:
        widget.setSizePolicy(EXPANDING, FIXED)
        if isinstance(widget, (QLineEdit, QComboBox)):
            widget.setMinimumWidth(160)
            widget.setFixedHeight(CONTROL_HEIGHT)
        elif isinstance(widget, UnitValueWidget):
            widget.setMinimumWidth(160)

    def _custom_value_widget(self, full_path: str, value):
        key = full_path.split(".")[-1]
        unit = FIELD_UNITS.get(key)
        if key == "scattering_power" and isinstance(value, list) and len(value) == 2:
            labels = ("发射照明", "接收散射") if self.language == "zh" else ("Tx", "Rx")
            return VectorValueWidget(value, labels)
        if key == "spin_pole_icrs_deg" and isinstance(value, list):
            labels = ("赤经", "赤纬") if self.language == "zh" else ("RA", "Dec")
            return VectorValueWidget(value, labels, "°")
        if key == "spin_pole_ecliptic_deg" and isinstance(value, list):
            labels = ("黄经", "黄纬") if self.language == "zh" else ("Lon", "Lat")
            return VectorValueWidget(value, labels, "°")
        if key == "direction_body" and isinstance(value, list):
            return DirectionBodyWidget(value, self.language)
        if isinstance(value, list) and len(value) in {2, 3} and all(isinstance(item, (int, float)) for item in value):
            labels = ("x", "y", "z")[: len(value)]
            return VectorValueWidget(value, labels, unit)
        if key in UNIT_CHOICES and isinstance(value, (int, float)):
            return UnitValueWidget(value, UNIT_CHOICES[key], editable_unit=True)
        if unit and (value is None or isinstance(value, (int, float))):
            return UnitValueWidget(value, ((unit, 1.0),), editable_unit=False)
        return None

    def _display_label(self, relative_path: str) -> str:
        key = relative_path.split(".")[-1]
        labels = FIELD_LABELS if self.language == "zh" else FIELD_LABELS_EN
        return labels.get(key, key)

    def _choices_for_field(self, full_path: str) -> tuple[str, ...]:
        key = full_path.split(".")[-1]
        if key != "state":
            return CHOICES[key]
        group_name = full_path.split(".")[0]
        if self.current_stage == "observation" and group_name == "target":
            return ("linear", "static", "horizons_vectors")
        if self.current_stage == "observation" and group_name in {"transmitter", "receiver"}:
            return ("static", "geodetic_fixed", "astropy_geodetic", "linear")
        return CHOICES[key]

    def _is_monostatic_observation(self) -> bool:
        observation = self.config_data.get("observation", {})
        transmitter = observation.get("transmitter")
        receiver = observation.get("receiver")
        return isinstance(transmitter, dict) and isinstance(receiver, dict) and transmitter == receiver

    def _on_monostatic_toggled(self, checked: bool) -> None:
        try:
            self._sync_stage_from_fields()
        except Exception:
            pass
        self.monostatic_observation = bool(checked)
        if self.monostatic_observation:
            self._apply_monostatic_receiver()
        self._save_state()
        self._render_current_stage()

    def _apply_monostatic_receiver(self) -> None:
        observation = self.config_data.setdefault("observation", {})
        transmitter = observation.get("transmitter")
        if isinstance(transmitter, dict):
            observation["receiver"] = copy.deepcopy(transmitter)

    def _ordered_group_fields(self, values: dict):
        flat = dict(flatten("", values))
        ordered = []
        for key in COMMON_FIELD_ORDER:
            if key in flat:
                ordered.append((key, flat.pop(key)))
        if "enabled" in flat:
            ordered.append(("enabled", flat.pop("enabled")))
            if values.get("enabled") is False or str(values.get("enabled")).lower() == "false":
                return ordered
        state = values.get("state")
        if state in STATE_FIELDS:
            for key in STATE_FIELDS[state]:
                if key in flat:
                    ordered.append((key, flat.pop(key)))
        spin_frame = str(values.get("spin_pole_frame", "equatorial")).lower()
        if spin_frame in {"icrs", "equatorial", "equtorial"}:
            flat.pop("spin_pole_ecliptic_deg", None)
        elif spin_frame == "ecliptic":
            flat.pop("spin_pole_icrs_deg", None)
        waveform_type = values.get("type")
        if waveform_type == "continuous_wave":
            for key in ("pulse_width_s", "bandwidth_hz", "pri_s", "first_pulse_start_s", "pulse_count", "pulse_start_s"):
                flat.pop(key, None)
        spin_coord_key = "spin_pole_ecliptic_deg" if spin_frame == "ecliptic" else "spin_pole_icrs_deg"
        for key in (
            "rotation_period_s",
            "initial_phase_deg",
            "spin_pole_frame",
            spin_coord_key,
            "direction_body",
            "radius_deg",
            "strength",
            "carrier_frequency_hz",
            "type",
            "amplitude",
            "pulse_width_s",
            "bandwidth_hz",
            "pri_s",
            "first_pulse_start_s",
            "pulse_count",
            "pulse_start_s",
        ):
            if key in flat:
                ordered.append((key, flat.pop(key)))
        ordered.extend(flat.items())
        return ordered

    def _migrate_config(self) -> None:
        echo_target = self.config_data.get("echo", {}).get("target")
        if isinstance(echo_target, dict):
            if str(echo_target.get("spin_pole_frame", "equatorial")).lower() in {"icrs", "equtorial"}:
                echo_target["spin_pole_frame"] = "equatorial"
            echo_target.setdefault("spin_pole_frame", "equatorial")
        echo_spot = self.config_data.get("echo", {}).get("scattering_spot")
        if isinstance(echo_spot, dict):
            echo_spot.setdefault("enabled", True)
            if str(echo_spot.get("enabled", True)).lower() != "false":
                for key, value in SCATTERING_SPOT_DEFAULTS.items():
                    echo_spot.setdefault(key, copy.deepcopy(value))
        echo_waveform = self.config_data.get("echo", {}).get("waveform")
        if isinstance(echo_waveform, dict) and echo_waveform.get("type") == "chirp_pulse_train":
            echo_waveform.setdefault("pulse_width_s", 120.0)
            echo_waveform.setdefault("bandwidth_hz", 4.0)
            echo_waveform.setdefault("pri_s", 180.0)
            echo_waveform.setdefault("first_pulse_start_s", 0.0)

        observation = self.config_data.get("observation")
        if not isinstance(observation, dict):
            return
        target = observation.get("target")
        if not isinstance(target, dict):
            return

        if "horizons_id" in target:
            if "id" not in target:
                target["id"] = target["horizons_id"]
            target.pop("horizons_id", None)
        if "id_type" in target:
            if "object_type" not in target:
                target["object_type"] = target["id_type"]
            target.pop("id_type", None)

        ephemeris = observation.setdefault("ephemeris", {})
        if target.get("state") == "horizons_vectors":
            for key in EPHEMERIS_FIELD_ORDER:
                if key in target:
                    ephemeris.setdefault(key, target[key])
                    target.pop(key, None)
            for key, value in EPHEMERIS_FIELD_DEFAULTS.items():
                ephemeris.setdefault(key, copy.deepcopy(value))

    def _select_stage(self, stage: str) -> None:
        self._sync_stage_from_fields()
        self.current_stage = stage
        self._render_stage_buttons()
        self._render_current_stage()

    def _on_state_changed(self, full_path: str) -> None:
        self._sync_stage_from_fields()
        parts = full_path.split(".")
        if len(parts) < 2:
            return
        group_name = parts[0]
        group = self.config_data.get(self.current_stage, {}).get(group_name)
        if not isinstance(group, dict):
            return
        self.config_data[self.current_stage][group_name] = self._normalize_state_group(group)
        self._save_state()
        self._render_current_stage()

    def _on_spin_pole_frame_changed(self, full_path: str) -> None:
        self._sync_stage_from_fields()
        target = self.config_data.get("echo", {}).get("target")
        if not isinstance(target, dict):
            return
        frame = str(target.get("spin_pole_frame", "icrs")).lower()
        if frame == "ecliptic":
            target.setdefault("spin_pole_ecliptic_deg", copy.deepcopy(target.get("spin_pole_icrs_deg", [0.0, 90.0])))
        else:
            target["spin_pole_frame"] = "equatorial"
            target.setdefault("spin_pole_icrs_deg", copy.deepcopy(target.get("spin_pole_ecliptic_deg", [0.0, 90.0])))
        self._save_state()
        self._render_current_stage()

    def _on_waveform_type_changed(self) -> None:
        self._sync_stage_from_fields()
        waveform = self.config_data.get("echo", {}).get("waveform")
        if not isinstance(waveform, dict):
            return
        if waveform.get("type") == "chirp_pulse_train":
            waveform.setdefault("pulse_width_s", 120.0)
            waveform.setdefault("bandwidth_hz", 4.0)
            waveform.setdefault("pri_s", 180.0)
            waveform.setdefault("first_pulse_start_s", 0.0)
        self._save_state()
        self._render_current_stage()

    def _on_spot_enabled_changed(self) -> None:
        self._sync_stage_from_fields()
        spot = self.config_data.get("echo", {}).get("scattering_spot")
        if isinstance(spot, dict) and str(spot.get("enabled", True)).lower() != "false":
            for key, value in SCATTERING_SPOT_DEFAULTS.items():
                spot.setdefault(key, copy.deepcopy(value))
        self._save_state()
        self._render_current_stage()

    def _normalize_state_group(self, group: dict) -> dict:
        state = group.get("state", "static")
        if state not in STATE_FIELDS:
            return group
        all_state_fields = set()
        for fields in STATE_FIELDS.values():
            all_state_fields.update(fields)
        all_state_fields.discard("id")

        normalized = {}
        for key in COMMON_FIELD_ORDER:
            if key in group:
                normalized[key] = group[key]
        normalized["state"] = state
        for key in STATE_FIELDS[state]:
            normalized[key] = self._state_field_value(key, group)
        for key, value in group.items():
            if key in normalized or key in all_state_fields:
                continue
            normalized[key] = value
        return normalized

    def _state_field_value(self, key: str, group: dict):
        if key in group:
            return group[key]
        if key == "position_m" and "position0_m" in group:
            return group["position0_m"]
        if key == "position0_m" and "position_m" in group:
            return group["position_m"]
        if key == "id" and "name" in group:
            return group["name"]
        return copy.deepcopy(STATE_DEFAULTS.get(key, ""))

    def _sync_stage_from_fields(self) -> None:
        existing = self.config_data.get(self.current_stage, {})
        stage_payload = copy.deepcopy(existing) if isinstance(existing, dict) else {}
        for path, widget in self.field_widgets.items():
            if hasattr(widget, "value"):
                value = widget.value()
            elif isinstance(widget, QComboBox):
                data = widget.currentData()
                text = widget.currentText() if data is None else str(data)
                value = parse_value(text)
            else:
                value = parse_value(widget.text())
            assign_path(stage_payload, path, value)
        self.config_data[self.current_stage] = stage_payload
        if self.current_stage == "observation" and self.monostatic_observation:
            self._apply_monostatic_receiver()
        self._migrate_config()
        self._normalize_horizons_object_type()

    def _save_current_config(self) -> None:
        try:
            self._sync_stage_from_fields()
            self._save_state()
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self._append_log(f"[{now_text()}] 参数已保存，下次打开会使用当前值。")
        self.status_label.setText("参数已保存")

    def _save_config_as_json(self) -> None:
        try:
            self._sync_stage_from_fields()
            pipeline.require_sections(self.config_data)
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        default_name = f"{self.run_name_edit.text().strip() or self.config_path.stem}.json"
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "将当前参数保存为 JSON",
            str(ROOT / "configs" / default_name),
            "JSON (*.json);;全部文件 (*)",
        )
        if not filename:
            return
        path = Path(filename)
        try:
            write_json(path, self.config_data)
            self.config_path = path
            self.config_path_edit.setText(str(path))
            self.run_name_edit.setText(path.stem)
            self._save_state()
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self._append_log(f"[{now_text()}] 当前参数已另存为：{path}")
        self.status_label.setText(f"已保存 JSON：{path}")

    def _save_state(self) -> None:
        write_json(
            STATE_PATH,
            {
                "config_path": str(self.config_path),
                "config": self.config_data,
                "saved_at": now_text(),
            },
        )

    def _choose_config(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择 pipeline JSON 配置",
            str(ROOT / "configs"),
            "JSON (*.json);;全部文件 (*)",
        )
        if filename:
            self.config_path_edit.setText(filename)
            self._load_config_from_entry()

    def _load_config_from_entry(self) -> None:
        path = Path(self.config_path_edit.text()).expanduser()
        if not path.is_absolute():
            path = ROOT / path
        try:
            data = read_json(path, {})
            pipeline.require_sections(data)
        except Exception as exc:
            QMessageBox.critical(self, "载入失败", str(exc))
            return
        self.config_path = path
        self.config_data = data
        self._migrate_config()
        self.monostatic_observation = self._is_monostatic_observation()
        self.run_name_edit.setText(path.stem)
        self.current_stage = STAGES[0]
        self.stage_status = {stage: "待执行" for stage in STAGES}
        self._render_stage_buttons()
        self._render_current_stage()
        self._save_state()
        self._append_log(f"[{now_text()}] 已载入配置：{path}")

    def _validate_role_states(self) -> None:
        self._normalize_horizons_object_type()
        observation = self.config_data.get("observation", {})
        target_state = observation.get("target", {}).get("state")
        if target_state not in {"linear", "static", "horizons_vectors"}:
            raise ValueError(
                "target.state 不应设置为 geodetic_fixed/astropy_geodetic。"
                "这些状态表示地面测站；目标建议使用 linear、static 或 horizons_vectors。"
            )
        station_allowed = {"static", "geodetic_fixed", "astropy_geodetic", "linear"}
        for role in ("transmitter", "receiver"):
            state = observation.get(role, {}).get("state")
            if state not in station_allowed:
                raise ValueError(f"{role}.state 当前不支持 {state}，请使用 static/geodetic_fixed/astropy_geodetic/linear。")

        target = observation.get("target", {})
        if target.get("state") == "horizons_vectors":
            if "id_type" in target or "horizons_id" in target:
                raise ValueError("target 中不再支持 id_type/horizons_id，请使用 id 和 object_type。")
            object_type = target.get("object_type")
            if object_type not in HORIZONS_OBJECT_TYPES:
                raise ValueError(
                    f"target.object_type={object_type!r} 不是当前配置支持的目标类型。"
                    "当前 GUI 仅支持 null 或 smallbody。"
                )

    def _normalize_horizons_object_type(self) -> None:
        target = self.config_data.get("observation", {}).get("target", {})
        if not isinstance(target, dict) or target.get("state") != "horizons_vectors":
            return
        if "horizons_id" in target:
            if "id" not in target:
                target["id"] = target["horizons_id"]
                self._append_log(f"[{now_text()}] 已将弃用字段 target.horizons_id 迁移为 target.id。")
            target.pop("horizons_id", None)
        if "id_type" in target:
            if "object_type" not in target:
                target["object_type"] = target["id_type"]
                self._append_log(f"[{now_text()}] 已将弃用字段 target.id_type 迁移为 target.object_type。")
            target.pop("id_type", None)
        value = target.get("object_type")
        if isinstance(value, str):
            normalized = HORIZONS_ID_TYPE_ALIASES.get(value.strip().lower(), value.strip())
        else:
            normalized = value
        if normalized != value:
            target["object_type"] = normalized
            self._append_log(f"[{now_text()}] 已将 target.object_type 从 {value!r} 归一化为 {normalized!r}。")

    def _run_current_stage(self) -> None:
        if self.process and self.process.state() != NOT_RUNNING:
            QMessageBox.information(self, "正在执行", "当前已有阶段在执行，请等待完成。")
            return
        try:
            self._sync_stage_from_fields()
            pipeline.require_sections(self.config_data)
            self._validate_role_states()
            self._save_state()
        except Exception as exc:
            QMessageBox.critical(self, "参数错误", str(exc))
            return

        stage = self.current_stage
        run_name = self.run_name_edit.text().strip() or self.config_path.stem
        runs_dir = self.runs_dir_edit.text().strip() or "runs"
        python_exe = self.python_edit.text().strip() or sys.executable
        run_dir = pipeline.abs_path(runs_dir) / run_name
        config_dir = run_dir / "configs"
        prepared = pipeline.prepared_configs(self.config_data, run_dir)
        write_json(config_dir / "experiment.json", self.config_data)
        write_json(config_dir / "observation.generated.json", prepared["observation"])
        write_json(config_dir / "echo.generated.json", prepared["echo"])
        write_json(config_dir / "inversion.generated.json", prepared["inversion"])

        command, cwd, env = self._stage_command(stage, python_exe, config_dir, prepared)
        self.process_stage = stage
        self.process_run_dir = run_dir
        self.process_log_path = run_dir / "logs" / f"{stage}.log"
        self.process_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.process_log_path.write_text("", encoding="utf-8")
        self.stop_requested = False
        self.stage_status[stage] = "执行中"
        self._render_stage_buttons()
        self.next_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._set_progress(stage, 0, "启动子进程")
        self.status_label.setText(f"{self._tr('正在执行', 'Running')}: {self._stage_label(stage)}")
        self._append_log(f"\n[{now_text()}] 开始执行 {self._stage_label(stage)}")
        self._append_log(f"命令：{' '.join(map(str, command))}\n工作目录：{cwd}")
        self._append_log(f"完整原始输出日志：{self.process_log_path}")
        self._append_log(
            "生成配置：\n"
            f"  experiment: {config_dir / 'experiment.json'}\n"
            f"  observation: {config_dir / 'observation.generated.json'}\n"
            f"  echo: {config_dir / 'echo.generated.json'}\n"
            f"  inversion: {config_dir / 'inversion.generated.json'}"
        )

        self.process = QProcess(self)
        self.process_output_buffer = ""
        if env:
            process_env = QProcessEnvironment.systemEnvironment()
            for key, value in env.items():
                process_env.insert(key, value)
            self.process.setProcessEnvironment(process_env)
        self.process.setWorkingDirectory(str(cwd))
        self.process.readyReadStandardOutput.connect(self._read_process_output)
        self.process.readyReadStandardError.connect(self._read_process_output)
        self.process.finished.connect(self._process_finished)
        self.process.start(str(command[0]), [str(item) for item in command[1:]])

    def _stop_current_stage(self) -> None:
        if not self.process or self.process.state() == NOT_RUNNING:
            return
        self.stop_requested = True
        if self.process_stage:
            self.stage_status[self.process_stage] = "中止中"
            self._render_stage_buttons()
            self._set_progress(self.process_stage, self.progress_bar.value(), "正在中止计算")
        self.stop_btn.setEnabled(False)
        self._append_log(f"[{now_text()}] 用户请求中止当前计算。")
        self._terminate_process_tree(self.process)

    def _terminate_process_tree(self, process: QProcess) -> None:
        pid = int(process.processId())
        if pid and sys.platform == "win32":
            QProcess.startDetached("taskkill", ["/PID", str(pid), "/T", "/F"])
            return
        process.terminate()
        QTimer.singleShot(1500, lambda: process.kill() if process.state() != NOT_RUNNING else None)

    def _stage_command(self, stage: str, python_exe: str, config_dir: Path, prepared: dict):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        if stage == "observation":
            return (
                [
                    python_exe,
                    "solve_observation_info.py",
                    "--config",
                    str(config_dir / "observation.generated.json"),
                    "--output",
                    str(prepared["observation_output"]),
                ],
                ROOT / "observation",
                env,
            )
        if stage == "echo":
            return (
                [
                    python_exe,
                    "simulate_echo.py",
                    "--config",
                    str(config_dir / "echo.generated.json"),
                    "--output",
                    str(prepared["echo_output_dir"]),
                ],
                ROOT / "echo",
                env,
            )
        inversion_src = str(ROOT / "inversion" / "src")
        env["PYTHONPATH"] = inversion_src + os.pathsep + env.get("PYTHONPATH", "")
        return (
            [
                python_exe,
                "scripts/estimate_period.py",
                "--echo",
                str(prepared["echo_output_dir"] / "echo.npz"),
                "--config",
                str(config_dir / "inversion.generated.json"),
                "--output",
                str(prepared["inversion_output_dir"]),
            ],
            ROOT / "inversion",
            env,
        )

    def _read_process_output(self) -> None:
        if not self.process:
            return
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        err = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        text = data + err
        if text:
            self._append_process_output(text)

    def _append_process_output(self, text: str) -> None:
        if self.process_log_path:
            with self.process_log_path.open("a", encoding="utf-8", errors="replace") as handle:
                handle.write(text)
        self.process_output_buffer += text
        lines = self.process_output_buffer.splitlines(keepends=True)
        if lines and not lines[-1].endswith(("\n", "\r")):
            self.process_output_buffer = lines.pop()
        else:
            self.process_output_buffer = ""

        display_lines = []
        for line in lines:
            clean_line = line.rstrip("\r\n")
            if self._handle_process_event_line(clean_line):
                continue
            display_lines.append(self._shorten_log_line(clean_line))
        display_text = "\n".join(line for line in display_lines if line)
        if display_text:
            self._append_log(display_text)

    def _handle_process_event_line(self, line: str) -> bool:
        if line.startswith(PROGRESS_PREFIX):
            return self._handle_progress_line(line)
        if line.startswith(WARNING_PREFIX):
            return self._handle_warning_line(line)
        if line.startswith(ERROR_PREFIX):
            return self._handle_error_line(line)
        return False

    def _handle_progress_line(self, line: str) -> bool:
        try:
            payload = json.loads(line[len(PROGRESS_PREFIX):])
            stage = str(payload.get("stage") or self.process_stage or self.current_stage)
            percent = int(payload.get("percent", 0))
            message = str(payload.get("message", ""))
        except Exception:
            return False
        self._set_progress(stage, percent, message)
        return True

    def _handle_warning_line(self, line: str) -> bool:
        try:
            payload = json.loads(line[len(WARNING_PREFIX):])
            stage = str(payload.get("stage") or self.process_stage or self.current_stage)
            message = str(payload.get("message", ""))
        except Exception:
            return False
        label = self._stage_label(stage) if stage in STAGES else stage
        self._append_warning(f"[{now_text()}] {label} 警告：{message}")
        return True

    def _handle_error_line(self, line: str) -> bool:
        try:
            payload = json.loads(line[len(ERROR_PREFIX):])
            stage = str(payload.get("stage") or self.process_stage or self.current_stage)
            message = str(payload.get("message", ""))
        except Exception:
            return False
        label = self._stage_label(stage) if stage in STAGES else stage
        self._append_error(f"[{now_text()}] {label} 错误：{message}")
        return True

    def _set_progress(self, stage: str, percent: int, message: str) -> None:
        percent = max(0, min(100, int(percent)))
        label = self._stage_label(stage) if stage in STAGES else stage
        self.progress_bar.setValue(percent)
        self.progress_bar.setFormat(f"{percent}%  {message}")
        self.status_label.setText(f"{label}：{message}")

    def _shorten_log_line(self, line: str) -> str:
        if "JPL Horizons 查询失败" in line:
            return re.sub(r"https://ssd\.jpl\.nasa\.gov/api/horizons\.api\?\S+", "<JPL Horizons URL 已省略>", line)
        if "Server Error:" in line and "ssd.jpl.nasa.gov/api/horizons.api" in line:
            return re.sub(r" for url: https://ssd\.jpl\.nasa\.gov/api/horizons\.api\?\S+", " for JPL Horizons URL，完整 URL 已写入原始输出日志。", line)
        if "Request-URI Too Large for url:" in line:
            return "requests.exceptions.HTTPError: 414 Client Error: Request-URI Too Large for JPL Horizons URL，完整 URL 已写入原始输出日志。"
        if "The uri used in this query is very long" in line:
            return "astroquery 警告：Horizons 查询 URL 很长，完整警告已写入原始输出日志。"
        line = re.sub(r"https://ssd\.jpl\.nasa\.gov/api/horizons\.api\?\S+", "<JPL Horizons URL 已省略>", line)
        if len(line) > 600:
            return line[:600] + " ... [界面日志已截断，完整内容见原始输出日志]"
        return line

    def _process_finished(self, exit_code: int, *_args) -> None:
        if self.process_output_buffer:
            pending = self.process_output_buffer
            self.process_output_buffer = ""
            if not self._handle_process_event_line(pending):
                self._append_log(self._shorten_log_line(pending))
        stage = self.process_stage
        run_dir = self.process_run_dir
        self.next_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        if not stage or not run_dir:
            return
        if self.stop_requested:
            message = f"{self._stage_label(stage)} 已中止"
            self.stage_status[stage] = "已中止"
            self._append_history(stage, "中止", str(run_dir), message)
            self.status_label.setText(message)
            self.progress_bar.setFormat("已中止")
            self._append_log(f"[{now_text()}] {message}")
        elif exit_code != 0:
            error = f"{self._stage_label(stage)} 失败，退出码 {exit_code}"
            self.stage_status[stage] = "失败"
            self._append_history(stage, "失败", "", error)
            self.status_label.setText(error)
            self.progress_bar.setFormat("失败")
            self._append_error(f"[{now_text()}] {error}")
            QMessageBox.critical(self, "执行失败", error)
        else:
            self.stage_status[stage] = "完成"
            self._set_progress(stage, 100, "完成")
            self._append_history(stage, "成功", str(run_dir), "")
            self._update_result_preview(stage, run_dir)
            next_stage = self._next_stage(stage)
            if next_stage:
                self.current_stage = next_stage
                self.status_label.setText(f"{self._stage_label(stage)} 完成，已切换到 {self._stage_label(next_stage)}")
                self._render_current_stage()
            else:
                self.status_label.setText(f"全部阶段已完成。实验目录：{run_dir}")
            self._append_log(f"[{now_text()}] {self._stage_label(stage)} 完成。实验目录：{run_dir}")
        self._render_stage_buttons()
        self._render_history()
        self.process = None
        self.process_stage = None
        self.process_run_dir = None
        self.process_log_path = None
        self.process_output_buffer = ""
        self.stop_requested = False

    def _update_result_preview(self, stage: str, run_dir: Path) -> None:
        try:
            image_path, result_path, plotly_path, message = self._create_stage_preview(stage, run_dir)
        except Exception as exc:
            self.latest_image_path = None
            self.latest_result_path = run_dir
            self.latest_plotly_path = None
            self.result_status.setText(f"结果预览生成失败：{exc}")
            self.preview.set_image(None, "结果已生成，但预览图创建失败。")
            self._append_warning(f"[{now_text()}] 结果预览生成失败：{exc}")
            return
        self.latest_image_path = image_path
        self.latest_result_path = result_path
        self.latest_plotly_path = plotly_path
        self.open_result_btn.setEnabled(bool(result_path))
        self.open_3d_btn.setEnabled(bool(plotly_path))
        self.result_status.setText(message)
        self._show_stage_preview(image_path, plotly_path, message)

    def _show_stage_preview(self, image_path: Path | None, plotly_path: Path | None, message: str) -> None:
        if self.web_preview and plotly_path and plotly_path.exists():
            self.preview.hide()
            self.web_preview.show()
            self.web_preview.load(QUrl.fromLocalFile(str(plotly_path.resolve())))
            return
        if self.web_preview:
            self.web_preview.hide()
        self.preview.show()
        self.preview.set_image(image_path, message)

    def _create_stage_preview(self, stage: str, run_dir: Path):
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        preview_dir = PREVIEW_DIR / run_dir.name.replace(" ", "_")
        preview_dir.mkdir(parents=True, exist_ok=True)
        if stage == "observation":
            image_path = preview_dir / "observation_preview.png"
            html_path = preview_dir / "observation_3d.html"
            result_path = run_dir / "observation_info.npz"
            self._make_observation_preview(result_path, image_path, html_path)
            return image_path, result_path, html_path, "观测解算完成：已生成距离/视线预览和可拖动 3D 画布。"
        if stage == "echo":
            image_path = preview_dir / "echo_preview.png"
            html_path = preview_dir / "echo_preview.html"
            result_path = run_dir / "echo" / "echo.npz"
            self._make_echo_preview(result_path, image_path, html_path)
            return image_path, result_path, html_path, "回波仿真完成：已生成可交互 I/Q、幅度与相位预览。"
        image_path = run_dir / "inversion" / "periodogram.png"
        html_path = run_dir / "inversion" / "periodogram.html"
        result_path = run_dir / "inversion" / "summary.json"
        plotly_path = html_path if html_path.exists() else None
        return image_path, result_path, plotly_path, "周期反演完成：已显示可交互周期图，可打开 summary 查看完整结果。"

    def _make_observation_preview(self, npz_path: Path, image_path: Path, html_path: Path) -> None:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        import plotly.graph_objects as go

        data = np.load(npz_path, allow_pickle=True)
        elapsed = data["elapsed_s"]
        tx_range_km = data["tx_range_m"] / 1000.0
        rx_range_km = data["rx_range_m"] / 1000.0
        tx_los = data["tx_los_icrs"]
        rx_los = data["rx_los_icrs"]

        fig, axes = plt.subplots(2, 1, figsize=(7.2, 4.5), sharex=True)
        axes[0].plot(elapsed, tx_range_km, label="tx range", linewidth=1.4)
        axes[0].plot(elapsed, rx_range_km, label="rx range", linewidth=1.4, linestyle="--")
        axes[0].set_ylabel("Range (km)")
        axes[0].legend(loc="best")
        axes[1].plot(elapsed, tx_los[:, 1], label="tx y", linewidth=1.2)
        axes[1].plot(elapsed, rx_los[:, 1], label="rx y", linewidth=1.2, linestyle="--")
        axes[1].set_xlabel("Elapsed (s)")
        axes[1].set_ylabel("LOS y")
        axes[1].legend(loc="best")
        fig.tight_layout()
        fig.savefig(image_path, dpi=220)
        plt.close(fig)

        stride = max(1, len(elapsed) // 800)
        tx_pos = tx_los[::stride] * tx_range_km[::stride, None]
        rx_pos = rx_los[::stride] * rx_range_km[::stride, None]
        plot = go.Figure()
        plot.add_trace(go.Scatter3d(x=tx_pos[:, 0], y=tx_pos[:, 1], z=tx_pos[:, 2], mode="lines", name="Tx LOS"))
        plot.add_trace(go.Scatter3d(x=rx_pos[:, 0], y=rx_pos[:, 1], z=rx_pos[:, 2], mode="lines", name="Rx LOS"))
        plot.update_layout(
            title="Observation LOS trajectory",
            scene={
                "xaxis_title": "ICRS x (km)",
                "yaxis_title": "ICRS y (km)",
                "zaxis_title": "ICRS z (km)",
                "aspectmode": "data",
            },
            margin={"l": 0, "r": 0, "t": 40, "b": 0},
        )
        plot.write_html(html_path, include_plotlyjs=True)

    def _make_echo_preview(self, npz_path: Path, image_path: Path, html_path: Path) -> None:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        data = np.load(npz_path, allow_pickle=True)
        elapsed = data["elapsed_s"]
        iq = data["iq"]
        clean_iq = data["clean_iq"] if "clean_iq" in data.files else None
        fig, axes = plt.subplots(3, 1, figsize=(7.2, 5.2), sharex=True)
        axes[0].plot(elapsed, iq.real, label="I", linewidth=1.0)
        axes[0].plot(elapsed, iq.imag, label="Q", linewidth=1.0)
        axes[0].set_ylabel("I/Q")
        axes[0].legend(loc="best")
        axes[1].plot(elapsed, np.abs(iq), label="noisy", linewidth=1.0)
        if clean_iq is not None:
            axes[1].plot(elapsed, np.abs(clean_iq), label="clean", linewidth=1.0, alpha=0.8)
        axes[1].set_ylabel("Amplitude")
        axes[1].legend(loc="best")
        axes[2].plot(elapsed, np.unwrap(np.angle(iq)), linewidth=1.0)
        axes[2].set_xlabel("Elapsed (s)")
        axes[2].set_ylabel("Phase (rad)")
        fig.tight_layout()
        fig.savefig(image_path, dpi=220)
        plt.close(fig)

        stride = max(1, len(elapsed) // 5000)
        plot_elapsed = elapsed[::stride]
        plot_iq = iq[::stride]
        plot = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.07,
            subplot_titles=("I/Q", "Amplitude", "Unwrapped phase"),
        )
        plot.add_trace(go.Scatter(x=plot_elapsed, y=plot_iq.real, mode="lines", name="I"), row=1, col=1)
        plot.add_trace(go.Scatter(x=plot_elapsed, y=plot_iq.imag, mode="lines", name="Q"), row=1, col=1)
        plot.add_trace(go.Scatter(x=plot_elapsed, y=np.abs(plot_iq), mode="lines", name="amplitude"), row=2, col=1)
        plot.add_trace(
            go.Scatter(x=plot_elapsed, y=np.unwrap(np.angle(plot_iq)), mode="lines", name="phase"),
            row=3,
            col=1,
        )
        plot.update_xaxes(title_text="Elapsed (s)", row=3, col=1)
        plot.update_layout(height=620, margin={"l": 55, "r": 20, "t": 45, "b": 40})
        plot.write_html(html_path, include_plotlyjs=True)

    def _render_history(self) -> None:
        history = read_json(HISTORY_PATH, [])
        rows = list(reversed(history[-80:]))
        self.history_table.setRowCount(len(rows))
        for row, record in enumerate(rows):
            values = (
                record.get("time", ""),
                self._stage_label(record.get("stage")) if record.get("stage") in STAGES else record.get("stage", ""),
                self._status_text(record.get("status", "")),
            )
            for col, value in enumerate(values):
                text = str(value)
                display = text.replace(" ", "\n", 1) if col == 0 else text
                if col == 1:
                    display = text.split(". ", 1)[-1]
                item = QTableWidgetItem(display)
                item.setToolTip(text)
                self.history_table.setItem(row, col, item)
            self.history_table.setRowHeight(row, 46)

    def _append_history(self, stage: str, status: str, run_dir: str, error: str) -> None:
        history = read_json(HISTORY_PATH, [])
        history.append(
            {
                "time": now_text(),
                "stage": stage,
                "status": status,
                "run_name": self.run_name_edit.text().strip(),
                "run_dir": run_dir,
                "error": error,
            }
        )
        write_json(HISTORY_PATH, history[-300:])

    def _append_log(self, text: str) -> None:
        self.log_edit.append(text)

    def _append_warning(self, text: str) -> None:
        self.log_edit.append(f'<span style="color:#b45309;font-weight:600;">{html.escape(text)}</span>')

    def _append_error(self, text: str) -> None:
        self.log_edit.append(f'<span style="color:#b91c1c;font-weight:700;">{html.escape(text)}</span>')

    def _open_latest_result(self) -> None:
        if self.latest_result_path and self.latest_result_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.latest_result_path.resolve())))

    def _open_plotly(self) -> None:
        if self.latest_plotly_path and self.latest_plotly_path.exists():
            webbrowser.open(self.latest_plotly_path.resolve().as_uri())

    def closeEvent(self, event) -> None:
        try:
            self._sync_stage_from_fields()
            self._save_state()
        except Exception:
            pass
        if self.process and self.process.state() != NOT_RUNNING:
            self.stop_requested = True
            self._terminate_process_tree(self.process)
        super().closeEvent(event)

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
            if child_layout:
                PipelineWindow._clear_layout(child_layout)

    @staticmethod
    def _next_stage(stage: str) -> str | None:
        index = STAGES.index(stage)
        if index + 1 >= len(STAGES):
            return None
        return STAGES[index + 1]


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("自转周期测量流水线")
    configure_gui_style(app)
    window = PipelineWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
