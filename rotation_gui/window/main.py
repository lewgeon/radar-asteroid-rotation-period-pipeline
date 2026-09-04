from __future__ import annotations

import sys
from pathlib import Path

from .. import qt_compat, storage
from ..qt_compat import (
    ALIGN_CENTER, HORIZONTAL, NO_EDIT_TRIGGERS, VERTICAL, QCheckBox, QFrame,
    QGroupBox, QHBoxLayout, QIcon, QLabel, QLineEdit, QMainWindow, QProcess,
    QProgressBar, QPushButton, QScrollArea, QSize, QSplitter, QTabWidget,
    QTableWidget, QTextEdit, QTimer, QToolButton, QVBoxLayout, QWidget, Qt,
)
from ..schema import GROUP_LABELS, GROUP_LABELS_EN, OPTION_LABELS, STAGES, STAGE_LABELS, STAGE_LABELS_EN
from ..storage import now_text, read_json
from ..styling import GUI_STYLE
from ..widgets import NoWheelComboBox

from .configuration import ConfigurationMixin
from .execution import ExecutionMixin
from .forms.rendering import FormRenderingMixin
from .forms.state import FormStateMixin
from .history import HistoryMixin
from .previews import PreviewMixin


class PipelineWindow(
    FormRenderingMixin,
    FormStateMixin,
    ConfigurationMixin,
    ExecutionMixin,
    PreviewMixin,
    HistoryMixin,
    QMainWindow,
):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("自转周期测量流水线")
        self.resize(1360, 860)
        self.setMinimumSize(1100, 700)

        self.config_path = storage.DEFAULT_CONFIG_PATH
        self.config_source_text = ""
        self.config_data = self._load_initial_config()
        self.current_stage = STAGES[0]
        self.stage_status = {stage: "待执行" for stage in STAGES}
        self.language = "zh"
        self.field_widgets: dict[str, QWidget] = {}
        self.monostatic_observation = False
        self.monostatic_checkbox: QCheckBox | None = None
        gui_state = read_json(storage.STATE_PATH, {})
        self.reuse_observation_info = bool(gui_state.get("reuse_observation_info", False))
        self.reuse_observation_path = str(gui_state.get("reuse_observation_path", ""))
        self.reuse_observation_checkbox: QCheckBox | None = None
        self.reuse_observation_edit: QLineEdit | None = None
        self.export_observation_btn: QPushButton | None = None
        self.latest_observation_path: Path | None = None
        self.latest_image_path: Path | None = None
        self.latest_result_path: Path | None = None
        self.latest_plotly_path: Path | None = None
        self.stage_preview_records: dict[str, dict[str, Path | str | None]] = {}
        self.process: QProcess | None = None
        self.process_stage: str | None = None
        self.process_run_dir: Path | None = None
        self.process_log_path: Path | None = None
        self.process_output_buffer = ""
        self.stop_requested = False

        # 提前初始化 QtWebEngine：否则第一次生成结果预览时才创建 qt_compat.QWebEngineView，
        # 会让主窗口在运行中途重新创建原生表面，表现为“闪一下再刷新”。
        self._webengine_warmup = None
        if qt_compat.QWebEngineView is not None:
            try:
                self._webengine_warmup = qt_compat.QWebEngineView()
                self._webengine_warmup.setHtml("<html><body></body></html>")
            except Exception:
                self._webengine_warmup = None

        self._migrate_config()
        self._build_ui()
        self._render_stage_buttons()
        self._render_current_stage()
        self._render_history()
        self._append_log(f"[{now_text()}] 当前参数来源：{self.config_source_text}")

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
        self.preview_toggle_btn = QToolButton()
        self.preview_toggle_btn.setObjectName("previewToggle")
        self.preview_toggle_btn.setCheckable(True)
        self.preview_toggle_btn.setFixedSize(32, 32)
        self.preview_toggle_btn.setIcon(QIcon(str(storage.ROOT / "assets/gui/sidebar-toggle.svg")))
        self.preview_toggle_btn.setIconSize(QSize(18, 18))
        self.preview_toggle_btn.setToolTip(self._tr("显示结果侧栏", "Show Result Sidebar"))
        self.preview_toggle_btn.toggled.connect(self._on_preview_sidebar_toggled)
        config_row.addWidget(self.preview_toggle_btn)
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
        main_splitter.setHandleWidth(5)
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
        work_splitter.setChildrenCollapsible(False)
        work_splitter.setHandleWidth(5)
        main_splitter.addWidget(work_splitter)
        main_splitter.setSizes((240, 1100))
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)

        top_region = QWidget()
        top_region_layout = QHBoxLayout(top_region)
        top_region_layout.setContentsMargins(0, 0, 0, 0)
        top_region_layout.setSpacing(0)

        self.preview_splitter = QSplitter(HORIZONTAL)
        self.preview_splitter.setObjectName("previewSplitter")
        self.preview_splitter.setChildrenCollapsible(False)
        self.preview_splitter.setHandleWidth(5)
        self.preview_splitter.splitterMoved.connect(self._remember_preview_sidebar_width)
        self.preview_sidebar_width = 500

        self.params_group = QGroupBox("阶段参数")
        self.params_group.setMinimumHeight(240)
        self.params_group.setMinimumWidth(380)
        params_outer = QVBoxLayout(self.params_group)
        self.params_scroll = QScrollArea()
        self.params_scroll.setWidgetResizable(True)
        self.params_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.params_container = QWidget()
        self.params_container.setObjectName("parameterCanvas")
        self.params_layout = QVBoxLayout(self.params_container)
        self.params_layout.setContentsMargins(8, 8, 8, 8)
        self.params_layout.setSpacing(14)
        self.params_scroll.setWidget(self.params_container)
        params_outer.addWidget(self.params_scroll)
        self.preview_splitter.addWidget(self.params_group)

        self.result_sidebar = QFrame()
        self.result_sidebar.setObjectName("resultSidebar")
        self.result_sidebar.setMinimumWidth(300)
        result_layout = QVBoxLayout(self.result_sidebar)
        result_layout.setContentsMargins(12, 12, 12, 12)
        result_layout.setSpacing(10)
        self.result_sidebar_title = QLabel("结果预览")
        self.result_sidebar_title.setObjectName("resultSidebarTitle")
        result_layout.addWidget(self.result_sidebar_title)
        self.result_tabs = QTabWidget()
        result_layout.addWidget(self.result_tabs, 1)
        self.empty_preview_label = QLabel("绘制结果会在此显示。")
        self.empty_preview_label.setAlignment(ALIGN_CENTER)
        self.empty_preview_label.setWordWrap(True)
        result_layout.addWidget(self.empty_preview_label, 1)
        self.result_sidebar.hide()
        self.preview_splitter.addWidget(self.result_sidebar)
        self.preview_splitter.setStretchFactor(0, 1)
        self.preview_splitter.setStretchFactor(1, 0)
        top_region_layout.addWidget(self.preview_splitter, 1)

        work_splitter.addWidget(top_region)

        work_splitter.addWidget(log_group := QGroupBox("执行日志"))
        work_splitter.setSizes((590, 230))
        work_splitter.setStretchFactor(0, 3)
        work_splitter.setStretchFactor(1, 1)

        self.log_group = log_group
        log_layout = QVBoxLayout(log_group)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        log_layout.addWidget(self.log_edit)

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

    def _on_preview_sidebar_toggled(self, visible: bool) -> None:
        self._set_preview_sidebar_visible(visible)

    def _set_preview_sidebar_visible(self, visible: bool) -> None:
        if not visible and hasattr(self, "preview_splitter") and self.result_sidebar.isVisible():
            self._remember_preview_sidebar_width()
        self.result_sidebar.setVisible(visible)
        if visible and hasattr(self, "preview_splitter"):
            QTimer.singleShot(0, self._restore_preview_sidebar_width)
        self.preview_toggle_btn.blockSignals(True)
        self.preview_toggle_btn.setChecked(visible)
        self.preview_toggle_btn.setToolTip(
            self._tr("隐藏结果侧栏", "Hide Result Sidebar") if visible else self._tr("显示结果侧栏", "Show Result Sidebar")
        )
        self.preview_toggle_btn.blockSignals(False)

    def _remember_preview_sidebar_width(self, *_args) -> None:
        if not hasattr(self, "preview_splitter"):
            return
        sizes = self.preview_splitter.sizes()
        if len(sizes) > 1 and sizes[1] > 0:
            self.preview_sidebar_width = sizes[1]

    def _restore_preview_sidebar_width(self) -> None:
        if not self.result_sidebar.isVisible():
            return
        total = max(self.preview_splitter.width(), 900)
        parameter_min = max(getattr(self.parameter_cards, "card_minimum", 360), 360) if hasattr(self, "parameter_cards") else 360
        sidebar_width = max(self.preview_sidebar_width, 300)
        sidebar_width = min(sidebar_width, max(300, total - parameter_min))
        self.preview_splitter.setSizes((max(parameter_min, total - sidebar_width), sidebar_width))

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
        self.result_sidebar_title.setText(self._tr("结果预览", "Preview"))
        self.empty_preview_label.setText(self._tr("绘制结果会在此显示。", "Rendered results will appear here."))
        self._set_preview_sidebar_visible(self.result_sidebar.isVisible())
        self._refresh_result_tabs()
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
        self.stage_buttons = {}
        for stage in STAGES:
            btn = QPushButton(f"{self._stage_label(stage)}  {self._status_text(self.stage_status[stage])}")
            btn.setProperty("activeStage", stage == self.current_stage)
            btn.clicked.connect(lambda _checked=False, value=stage: self._select_stage(value))
            self.stage_layout.addWidget(btn)
            self.stage_buttons[stage] = btn
        self.stage_layout.addStretch(1)
