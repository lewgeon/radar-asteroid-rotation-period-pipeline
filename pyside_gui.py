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
        from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer, QUrl
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

    from PyQt6.QtCore import QProcess, QProcessEnvironment, Qt, QTimer, QUrl
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
CHOICES = {
    "state": ("static", "linear", "geodetic_fixed", "astropy_geodetic", "horizons_vectors"),
    "device": ("auto", "cuda:0", "cpu"),
    "dtype": ("float32", "float64"),
    "type": ("continuous_wave",),
    "object_type": ("null", "smallbody"),
    "query_mode": ("auto", "range", "list"),
    "spin_pole_frame": ("icrs", "ecliptic"),
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
    "device": "计算设备",
    "dtype": "浮点精度",
    "rotation_period_s": "自转周期",
    "initial_phase_deg": "初始相位",
    "spin_pole_frame": "自转轴坐标系",
    "spin_pole_icrs_deg": "自转轴赤经/赤纬",
    "spin_pole_ecliptic_deg": "自转轴黄经/黄纬",
    "scattering_power": "散射指数",
    "direction_body": "斑块方向",
    "radius_deg": "斑块半径",
    "strength": "斑块强度",
    "carrier_frequency_hz": "载频",
    "type": "波形类型",
    "amplitude": "幅度",
    "snr_db": "信噪比",
    "stft_window_samples": "STFT窗长",
    "stft_overlap_fraction": "STFT重叠",
    "period_min_s": "最小周期",
    "period_max_s": "最大周期",
    "period_grid_size": "周期网格数",
}
FIELD_UNITS = {
    "position_m": "m",
    "position0_m": "m",
    "velocity_m_s": "m/s",
    "lat_deg": "deg",
    "lon_deg": "deg",
    "height_m": "m",
    "duration_s": "s",
    "sample_rate_hz": "Hz",
    "tolerance_s": "s",
    "padding_s": "s",
    "query_step_s": "s",
    "rotation_period_s": "s",
    "initial_phase_deg": "deg",
    "spin_pole_icrs_deg": "deg",
    "spin_pole_ecliptic_deg": "deg",
    "radius_deg": "deg",
    "carrier_frequency_hz": "Hz",
    "snr_db": "dB",
    "period_min_s": "s",
    "period_max_s": "s",
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
        self.setMinimumHeight(260)
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
        self.field_widgets: dict[str, QLineEdit | QComboBox] = {}
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
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(14, 12, 14, 10)
        root_layout.setSpacing(10)

        config_row = QHBoxLayout()
        self.config_path_edit = QLineEdit(str(self.config_path))
        open_btn = QPushButton("打开")
        load_btn = QPushButton("载入")
        open_btn.clicked.connect(self._choose_config)
        load_btn.clicked.connect(self._load_config_from_entry)
        config_row.addWidget(QLabel("配置文件"))
        config_row.addWidget(self.config_path_edit, 1)
        config_row.addWidget(open_btn)
        config_row.addWidget(load_btn)
        root_layout.addLayout(config_row)

        run_row = QHBoxLayout()
        self.run_name_edit = QLineEdit(self.config_path.stem)
        self.runs_dir_edit = QLineEdit("runs")
        self.python_edit = QLineEdit(sys.executable)
        run_row.addWidget(QLabel("实验名"))
        run_row.addWidget(self.run_name_edit, 1)
        run_row.addWidget(QLabel("输出目录"))
        run_row.addWidget(self.runs_dir_edit, 1)
        run_row.addWidget(QLabel("Python"))
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
        self.next_btn.clicked.connect(self._run_current_stage)
        self.stop_btn = QPushButton("中止")
        self.stop_btn.clicked.connect(self._stop_current_stage)
        self.stop_btn.setEnabled(False)
        save_btn = QPushButton("保存参数")
        save_btn.clicked.connect(self._save_current_config)
        save_as_btn = QPushButton("另存 JSON")
        save_as_btn.clicked.connect(self._save_config_as_json)
        sidebar_layout.addWidget(self.next_btn)
        sidebar_layout.addWidget(self.stop_btn)
        sidebar_layout.addWidget(save_btn)
        sidebar_layout.addWidget(save_as_btn)

        self.history_table = QTableWidget(0, 3)
        self.history_table.setHorizontalHeaderLabels(("时间", "阶段", "状态"))
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setEditTriggers(NO_EDIT_TRIGGERS)
        sidebar_layout.addWidget(self.history_table, 1)

        main_splitter.addWidget(sidebar)

        work_splitter = QSplitter(VERTICAL)
        work_splitter.setChildrenCollapsible(False)
        main_splitter.addWidget(work_splitter)
        main_splitter.setSizes((280, 1080))

        self.params_group = QGroupBox("阶段参数")
        params_outer = QVBoxLayout(self.params_group)
        self.params_scroll = QScrollArea()
        self.params_scroll.setWidgetResizable(True)
        self.params_container = QWidget()
        self.params_layout = QVBoxLayout(self.params_container)
        self.params_layout.setContentsMargins(4, 4, 4, 4)
        self.params_layout.setSpacing(10)
        self.params_scroll.setWidget(self.params_container)
        params_outer.addWidget(self.params_scroll)
        work_splitter.addWidget(self.params_group)

        bottom_splitter = QSplitter(HORIZONTAL)
        bottom_splitter.setChildrenCollapsible(False)
        work_splitter.addWidget(bottom_splitter)
        work_splitter.setSizes((520, 300))

        log_group = QGroupBox("执行日志")
        log_layout = QVBoxLayout(log_group)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        log_layout.addWidget(self.log_edit)
        bottom_splitter.addWidget(log_group)

        result_group = QGroupBox("结果预览")
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

    def _render_stage_buttons(self) -> None:
        while self.stage_layout.count():
            item = self.stage_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        for stage in STAGES:
            btn = QPushButton(f"{STAGE_LABELS[stage]}  {self.stage_status[stage]}")
            btn.clicked.connect(lambda _checked=False, value=stage: self._select_stage(value))
            self.stage_layout.addWidget(btn)
        self.stage_layout.addStretch(1)

    def _render_current_stage(self) -> None:
        self._migrate_config()
        self._clear_layout(self.params_layout)
        self.field_widgets.clear()
        self.monostatic_checkbox = None
        self.params_group.setTitle(f"{STAGE_LABELS[self.current_stage]} 参数")
        if self.current_stage == "observation":
            self.monostatic_checkbox = QCheckBox("单基站观测：接收站沿用发射站参数")
            self.monostatic_checkbox.setChecked(self.monostatic_observation)
            self.monostatic_checkbox.toggled.connect(self._on_monostatic_toggled)
            self.params_layout.addWidget(self.monostatic_checkbox)
        stage_data = self.config_data.get(self.current_stage, {})
        for group_name, values in self._stage_groups(stage_data):
            group = QGroupBox(GROUP_LABELS.get(group_name, group_name))
            grid = QGridLayout(group)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(8)
            self._render_group_fields(grid, group_name, values)
            self.params_layout.addWidget(group)
        self.params_layout.addStretch(1)

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
        return groups

    def _render_group_fields(self, grid: QGridLayout, group_name: str, values: dict) -> None:
        row = 0
        compact_col = 0
        for relative_path, value in self._ordered_group_fields(values):
            full_path = relative_path if group_name == "通用参数" else f"{group_name}.{relative_path}"
            label = QLabel(self._display_label(relative_path))
            widget = self._field_widget(full_path, value)
            self.field_widgets[full_path] = widget

            if self._is_wide_field(relative_path, value):
                if compact_col:
                    row += 1
                    compact_col = 0
                grid.addWidget(label, row, 0)
                grid.addWidget(widget, row, 1, 1, 3)
                row += 1
            else:
                col = compact_col * 2
                grid.addWidget(label, row, col)
                grid.addWidget(widget, row, col + 1)
                compact_col += 1
                if compact_col >= 2:
                    compact_col = 0
                    row += 1

        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

    def _field_widget(self, full_path: str, value):
        key = full_path.split(".")[-1]
        if key in CHOICES or isinstance(value, bool):
            combo = NoWheelComboBox()
            choices = ("true", "false") if isinstance(value, bool) else self._choices_for_field(full_path)
            combo.addItems([str(item) for item in choices])
            current = "true" if value is True else "false" if value is False else format_value(value)
            if current not in [combo.itemText(i) for i in range(combo.count())]:
                combo.insertItem(0, current)
            combo.setCurrentText(current)
            if key == "state":
                combo.currentTextChanged.connect(lambda _text, path=full_path: self._on_state_changed(path))
            if key == "spin_pole_frame":
                combo.currentTextChanged.connect(lambda _text, path=full_path: self._on_spin_pole_frame_changed(path))
            return combo

        edit = QLineEdit(format_value(value))
        edit.setMinimumWidth(460 if self._is_wide_field(full_path, value) else 220)
        unit = FIELD_UNITS.get(key)
        if unit:
            edit.setPlaceholderText(unit)
            edit.setToolTip(f"单位：{unit}；配置字段：{full_path}")
        else:
            edit.setToolTip(f"配置字段：{full_path}")
        return edit

    def _display_label(self, relative_path: str) -> str:
        key = relative_path.split(".")[-1]
        text = FIELD_LABELS.get(key, key)
        unit = FIELD_UNITS.get(key)
        return f"{text} ({unit})" if unit else text

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
        state = values.get("state")
        if state in STATE_FIELDS:
            for key in STATE_FIELDS[state]:
                if key in flat:
                    ordered.append((key, flat.pop(key)))
        ordered.extend(flat.items())
        return ordered

    def _is_wide_field(self, relative_path: str, value) -> bool:
        key = relative_path.split(".")[-1]
        return isinstance(value, list) or key.endswith("_utc") or key in {
            "position_m",
            "position0_m",
            "velocity_m_s",
            "spin_pole_icrs_deg",
            "direction_body",
            "model_path",
            "observation_info_path",
        }

    def _migrate_config(self) -> None:
        echo_target = self.config_data.get("echo", {}).get("target")
        if isinstance(echo_target, dict):
            echo_target.setdefault("spin_pole_frame", "icrs")

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
            target.setdefault("spin_pole_icrs_deg", copy.deepcopy(target.get("spin_pole_ecliptic_deg", [0.0, 90.0])))
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
        stage_payload = {}
        for path, widget in self.field_widgets.items():
            text = widget.currentText() if isinstance(widget, QComboBox) else widget.text()
            assign_path(stage_payload, path, parse_value(text))
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
        self.status_label.setText(f"正在执行：{STAGE_LABELS[stage]}")
        self._append_log(f"\n[{now_text()}] 开始执行 {STAGE_LABELS[stage]}")
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
        label = STAGE_LABELS.get(stage, stage)
        self._append_warning(f"[{now_text()}] {label} 警告：{message}")
        return True

    def _handle_error_line(self, line: str) -> bool:
        try:
            payload = json.loads(line[len(ERROR_PREFIX):])
            stage = str(payload.get("stage") or self.process_stage or self.current_stage)
            message = str(payload.get("message", ""))
        except Exception:
            return False
        label = STAGE_LABELS.get(stage, stage)
        self._append_error(f"[{now_text()}] {label} 错误：{message}")
        return True

    def _set_progress(self, stage: str, percent: int, message: str) -> None:
        percent = max(0, min(100, int(percent)))
        label = STAGE_LABELS.get(stage, stage)
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
            message = f"{STAGE_LABELS[stage]} 已中止"
            self.stage_status[stage] = "已中止"
            self._append_history(stage, "中止", str(run_dir), message)
            self.status_label.setText(message)
            self.progress_bar.setFormat("已中止")
            self._append_log(f"[{now_text()}] {message}")
        elif exit_code != 0:
            error = f"{STAGE_LABELS[stage]} 失败，退出码 {exit_code}"
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
                self.status_label.setText(f"{STAGE_LABELS[stage]} 完成，已切换到 {STAGE_LABELS[next_stage]}")
                self._render_current_stage()
            else:
                self.status_label.setText(f"全部阶段已完成。实验目录：{run_dir}")
            self._append_log(f"[{now_text()}] {STAGE_LABELS[stage]} 完成。实验目录：{run_dir}")
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
                STAGE_LABELS.get(record.get("stage"), record.get("stage", "")),
                record.get("status", ""),
            )
            for col, value in enumerate(values):
                self.history_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.history_table.resizeColumnsToContents()

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
    for style_name in ("windowsvista", "windows11", "windows"):
        if style_name in {name.lower() for name in QStyleFactory.keys()}:
            app.setStyle(style_name)
            break
    window = PipelineWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
