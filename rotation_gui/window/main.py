"""Staged pipeline GUI: observation → echo → inversion, non-overlapping parameters."""

from __future__ import annotations

import copy
import codecs
import html
import re
import json
import os
import sys
import warnings
from pathlib import Path

import pipeline

from .. import storage
from ..qt_compat import (
    QApplication,
    HORIZONTAL,
    VERTICAL,
    QDesktopServices,
    QEvent,
    QUrl,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QDialog,
    QMessageBox,
    QProcess,
    QProcessEnvironment,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QTextEdit,
    QTimer,
    QVBoxLayout,
    QWidget,
    NOT_RUNNING,
    Qt,
)
from ..schema import (
    ERROR_PREFIX,
    OPTION_LABELS,
    PROGRESS_PREFIX,
    STAGE_LABELS,
    STAGES,
    SUMMARY_PREFIX,
    WARNING_PREFIX,
)
from ..storage import now_text, read_json, write_json, write_json_new
from ..styling import GUI_STYLE
from .parameter_form import ParameterForm
from ..widgets.attention_button import AttentionButton


class ConfigPathDisplay(QLabel):
    """Non-interactive current-file label with a middle-elided visible path."""

    def __init__(self, path: str):
        super().__init__()
        self._full_path = ""
        self.setObjectName("configPathDisplay")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setText(path)

    def setText(self, path: str) -> None:
        self._full_path = str(path)
        self.setToolTip(f"当前配置：{self._full_path}\n使用「打开」或「另存为」切换文件。")
        self._update_visible_path()

    def text(self) -> str:
        return self._full_path

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_visible_path()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if hasattr(self, "_full_path") and event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._update_visible_path()

    def _update_visible_path(self) -> None:
        available = max(1, self.contentsRect().width() - 20)
        visible = self.fontMetrics().elidedText(
            self._full_path, Qt.TextElideMode.ElideMiddle, available
        )
        super().setText(visible)


def stage_output_paths(prepared: dict) -> dict[str, tuple[tuple[str, Path], ...]]:
    """Artifact paths reported in the log when a stage finishes."""

    echo_dir = Path(prepared["echo_output_dir"])
    inversion_dir = Path(prepared["inversion_output_dir"])
    inversion_outputs = (("反演结果", inversion_dir / "summary.json"),)
    if prepared.get("inversion", {}).get("compare_methods", False):
        inversion_outputs += (("方法比较表", inversion_dir / "method_comparison.html"),
                              ("方法比较数据", inversion_dir / "method_comparison.json"))
    return {
        "observation": (("观测信息", Path(prepared["observation_output"])),),
        "echo": (
            ("回波数据", echo_dir / "echo.npz"),
            ("回波摘要", echo_dir / "summary.json"),
        ),
        "inversion": inversion_outputs,
    }


def _canonicalize_config(config: dict) -> tuple[dict, list[str]]:
    """Normalize a pipeline config and collect collection-path-gate fold notes."""

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        normalized = pipeline.canonical_pipeline_config(config)
    notes: list[str] = []
    for item in caught:
        text = str(item.message)
        if text.startswith("采集路径窗已合并"):
            notes.append(text)
        else:
            warnings.warn(text, item.category, stacklevel=2)
    return normalized, notes


class ResultPopup(QFrame):
    """Anchored popup with explicit outside-click behavior on both Qt backends."""

    def __init__(self, parent):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay, True)
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, watched, event):
        if (self.isVisible() and event.type() == QEvent.Type.MouseButtonPress
                and isinstance(watched, QWidget) and watched is not self
                and not self.isAncestorOf(watched)):
            # Qt reparents combo list windows; they can extend beyond our rect.
            for combo in self.findChildren(QComboBox):
                view = combo.view()
                if view.isVisible() and watched.window() is view.window():
                    return super().eventFilter(watched, event)
            if not self.rect().contains(self.mapFromGlobal(event.globalPosition().toPoint())):
                self.hide()
                anchor=getattr(self.parent(),'result_btn',None)
                if anchor is not None and anchor.rect().contains(anchor.mapFromGlobal(event.globalPosition().toPoint())):
                    # Consume the closing press: do not replay it as a new open.
                    return True
        return super().eventFilter(watched, event)


class PipelineWindow(QMainWindow):
    """Three-stage parameter ownership with one executable stage at a time."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("自转周期测量流水线")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 720)
        self.setStyleSheet(GUI_STYLE)

        self.config_path, self.config_data, restored_state = self._load_initial_session()
        self.current_stage = "observation"
        self.monostatic_observation = self._is_monostatic_observation()
        self._bistatic_receiver_backup = None
        self.echo_preview_html = None
        self.stage_status = {stage: "未运行" for stage in STAGES}
        self._opened_previews: dict[str, set] = {"echo": set(), "features": set()}
        self._untracked_run_baselines: dict[tuple, str | None] = {}
        self.process: QProcess | None = None
        self.feature_preview_process: QProcess | None = None
        self.process_stage: str | None = None
        self.process_output_buffer = ""
        self.process_run_dir: Path | None = None
        self.process_prepared: dict | None = None
        self.process_outputs: dict[str, tuple[tuple[str, Path], ...]] = {}
        self._abort_requested = False
        self._fresh_artifacts: set[str] = set()

        self._build_ui()
        if restored_state:
            self.run_name_edit.setText(str(restored_state.get("run_name") or self.config_path.stem))
            self.runs_dir_edit.setText(str(restored_state.get("runs_dir") or "runs"))
        self._render_stage()
        self._append_log(f"[{now_text()}] {'已恢复上次会话' if restored_state else '已载入配置'}：{self.config_path}")
        for note in self._startup_notes:
            self._append_log(note, level="warning")

    def _load_initial_session(self) -> tuple[Path, dict, dict]:
        self._startup_notes: list[str] = []
        try:
            state = read_json(storage.STATE_PATH, {})
            if isinstance(state, dict) and state.get("config_path"):
                path = Path(str(state["config_path"])).expanduser().resolve()
                saved_config = state.get("config")
                if isinstance(saved_config, dict):
                    config, self._startup_notes = _canonicalize_config(saved_config)
                    return path, config, state
                if path.is_file():
                    return path, self._load_config(path), state
        except (OSError, ValueError, TypeError, KeyError):
            pass
        path = storage.DEFAULT_CONFIG_PATH.resolve()
        return path, self._load_config(path), {}

    def closeEvent(self, event) -> None:
        if hasattr(self,'_result_status_timer'):
            self._result_status_timer.stop()
            self._result_status_executor.shutdown(wait=False,cancel_futures=True)
        popup=getattr(self,'_result_popup',None)
        if popup is not None:popup.hide()
        if self.feature_preview_process is not None:
            self._feature_preview_cancelled = True
            self.feature_preview_process.kill()
            self.feature_preview_process.waitForFinished(3000)
        try:
            self._sync_current_stage()
            state = {
                "config_path": str(self.config_path),
                "config": pipeline.canonical_pipeline_config(self.config_data),
                "run_name": self.run_name_edit.text(),
                "runs_dir": self.runs_dir_edit.text(),
            }
            write_json(storage.STATE_PATH, state)
        except Exception:
            # Preserve the last known path even when an unfinished field is invalid.
            try:
                write_json(storage.STATE_PATH, {"config_path": str(self.config_path), "run_name": self.run_name_edit.text(), "runs_dir": self.runs_dir_edit.text()})
            except OSError:
                pass
        super().closeEvent(event)

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        toolbar = QFrame()
        toolbar.setObjectName("toolbarPanel")
        toolbar_layout = QVBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(14, 12, 14, 12)
        toolbar_layout.setSpacing(10)

        config_row = QHBoxLayout()
        self.config_path_edit = ConfigPathDisplay(str(self.config_path))
        self.browse_btn = QPushButton("打开")
        self.save_btn = QPushButton("保存")
        self.save_as_btn = QPushButton("另存为")
        self.validate_btn = QPushButton("校验")
        config_label = QLabel("配置文件")
        config_label.setToolTip("当前载入的 JSON 路径。要换文件请点「打开」；要创建新文件请点「另存为」。")
        self.browse_btn.setToolTip("选择一个已有 JSON 并载入。")
        self.save_btn.setToolTip("更新当前配置文件。实验名仅决定运行结果目录，不改变配置文件名。")
        self.save_as_btn.setToolTip("选择新 JSON 文件路径并保存。不会覆盖其他已有配置；实验名保持不变。")
        config_row.addWidget(config_label)
        config_row.addWidget(self.config_path_edit, 1)
        for button in (
            self.browse_btn,
            self.save_btn,
            self.save_as_btn,
            self.validate_btn,
        ):
            config_row.addWidget(button)
        toolbar_layout.addLayout(config_row)

        run_row = QHBoxLayout()
        run_row.setSpacing(8)
        waveform_label = QLabel("发射波形")
        self.waveform_combo = QComboBox()
        self.waveform_combo.setObjectName("globalWaveformType")
        self.waveform_combo.setMinimumWidth(145)
        for value in ("continuous_wave", "chirp_pulse_train"):
            self.waveform_combo.addItem(OPTION_LABELS[value], value)
        run_row.addWidget(waveform_label)
        run_row.addWidget(self.waveform_combo)

        scattering_label = QLabel("散射模型")
        self.scattering_model_combo = QComboBox()
        self.scattering_model_combo.setObjectName("echoScatteringModel")
        self.scattering_model_combo.setMinimumWidth(145)
        for value in ("mesh", "point_target"):
            self.scattering_model_combo.addItem(OPTION_LABELS[value], value)

        self.run_name_edit = QLineEdit(self.config_path.stem)
        self.run_name_edit.setToolTip("运行结果目录名：runs/<实验名>/。不会改变配置文件路径。")
        self.runs_dir_edit = QLineEdit("runs")
        self.python_edit = QLineEdit(sys.executable)
        self.run_btn = QPushButton("运行当前阶段")
        self.run_btn.setObjectName("runButton")
        self.run_all_btn = QPushButton("运行完整 pipeline")
        self.stop_btn = QPushButton("中止")
        self.stop_btn.setEnabled(False)
        self.preview_btn = AttentionButton("查看回波")
        self.preview_btn.setObjectName("previewButton")
        self.preview_btn.setEnabled(False)
        self.preview_btn.setToolTip("回波仿真完成后可查看交互预览")
        self.feature_preview_btn = AttentionButton("查看特征")
        self.feature_preview_btn.setObjectName("featurePreviewButton")
        self.feature_preview_btn.setEnabled(False)
        self.feature_preview_btn.setToolTip(
            '优先查看已保存的反演实际特征；尚未反演时计算逐脉冲特征'
        )
        self.result_btn = QPushButton('图像结果 ▾')
        self.result_btn.clicked.connect(self._open_result_dialog)
        run_name_label = QLabel("实验名")
        run_name_label.setToolTip(self.run_name_edit.toolTip())
        run_row.addWidget(run_name_label)
        run_row.addWidget(self.run_name_edit, 1)
        run_row.addWidget(QLabel("输出目录"))
        run_row.addWidget(self.runs_dir_edit, 1)
        run_row.addWidget(QLabel("Python"))
        run_row.addWidget(self.python_edit, 2)
        toolbar_layout.addLayout(run_row)
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("就绪")
        self.progress.setMinimumWidth(180)
        self.progress.setMinimumHeight(26)
        action_row.addWidget(self.progress, 1)
        for button in (
            self.run_btn,
            self.run_all_btn,
            self.stop_btn,
            self.result_btn,
        ):
            action_row.addWidget(button)
        toolbar_layout.addLayout(action_row)
        self.preview_btn.hide()
        self.feature_preview_btn.hide()
        layout.addWidget(toolbar)

        main_splitter = QSplitter(HORIZONTAL)
        main_splitter.setChildrenCollapsible(False)
        main_splitter.setHandleWidth(5)
        layout.addWidget(main_splitter, 1)

        left = QFrame()
        left.setObjectName("workPanel")
        left.setMinimumWidth(180)
        left.setMaximumWidth(320)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(8)
        left_title = QLabel("计算阶段")
        left_title.setObjectName("panelTitle")
        left_layout.addWidget(left_title)
        self.stage_buttons = {}
        self.stage_status_labels = {}
        for stage in STAGES:
            button = QPushButton(STAGE_LABELS[stage])
            button.setProperty("activeStage", stage == self.current_stage)
            button.setMinimumHeight(42)
            button.clicked.connect(lambda _checked=False, name=stage: self._select_stage(name))
            left_layout.addWidget(button)
            self.stage_buttons[stage] = button
            status = QLabel(f"状态：{self.stage_status[stage]}")
            status.setObjectName("panelHint")
            status.setWordWrap(True)
            left_layout.addWidget(status)
            self.stage_status_labels[stage] = status
        left_layout.addStretch(1)
        main_splitter.addWidget(left)

        work_column = QWidget()
        work_column_layout = QVBoxLayout(work_column)
        work_column_layout.setContentsMargins(0, 0, 0, 0)
        work_column_layout.setSpacing(8)

        work_splitter = QSplitter(VERTICAL)
        work_splitter.setChildrenCollapsible(False)
        work_splitter.setHandleWidth(5)
        work_column_layout.addWidget(work_splitter, 1)

        center = QFrame()
        center.setObjectName("workPanel")
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(14, 12, 14, 12)
        center_layout.setSpacing(8)
        self.scattering_model_control = QWidget()
        scattering_layout = QHBoxLayout(self.scattering_model_control)
        scattering_layout.setContentsMargins(0, 0, 0, 0)
        scattering_layout.setSpacing(8)
        scattering_layout.addWidget(scattering_label)
        scattering_layout.addWidget(self.scattering_model_combo)
        scattering_layout.addStretch(1)
        center_layout.addWidget(self.scattering_model_control)
        self.monostatic_checkbox = QCheckBox("单基站观测：接收站沿用发射站参数")
        self.monostatic_checkbox.setChecked(self.monostatic_observation)
        self.monostatic_checkbox.toggled.connect(self._on_monostatic_toggled)
        center_layout.addWidget(self.monostatic_checkbox)
        self.parameter_form = ParameterForm()
        center_layout.addWidget(self.parameter_form, 1)
        work_splitter.addWidget(center)

        log_group = QFrame()
        log_group.setObjectName("workPanel")
        self.log_group = log_group
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(10, 8, 10, 10)
        log_header = QHBoxLayout()
        log_title = QLabel("执行日志")
        log_title.setObjectName("logTitle")
        log_header.addWidget(log_title)
        log_header.addStretch(1)
        self.copy_log_btn = QPushButton("复制")
        self.clear_log_btn = QPushButton("清空")
        for button in (self.copy_log_btn, self.clear_log_btn):
            button.setObjectName("logActionButton")
            button.setFixedHeight(24)
            log_header.addWidget(button)
        self.copy_log_btn.setToolTip("复制当前日志")
        self.clear_log_btn.setToolTip("清空当前日志")
        log_layout.addLayout(log_header)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(120)
        # 批量 campaign 的逐 Run 警告可达上千条，限制块数以免长时间运行后界面变慢。
        self.log.document().setMaximumBlockCount(5000)
        log_layout.addWidget(self.log)
        self.copy_log_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.log.toPlainText()))
        self.clear_log_btn.clicked.connect(self.log.clear)
        work_splitter.addWidget(log_group)
        work_splitter.setSizes((590, 230))
        work_splitter.setStretchFactor(0, 3)
        work_splitter.setStretchFactor(1, 1)

        main_splitter.addWidget(work_column)
        main_splitter.setSizes((220, 1100))
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)

        self.browse_btn.clicked.connect(self._choose_config)
        self.save_btn.clicked.connect(self._save_config)
        self.save_as_btn.clicked.connect(self._save_config_as)
        self.validate_btn.clicked.connect(self._validate_config)
        self.run_btn.clicked.connect(self._run_current_stage)
        self.run_all_btn.clicked.connect(self._run_full_pipeline)
        self.stop_btn.clicked.connect(self._stop_pipeline)
        self.preview_btn.clicked.connect(self._open_echo_preview)
        self.feature_preview_btn.clicked.connect(self._open_feature_preview)
        self.parameter_form.on_edited = self._schedule_run_status_refresh
        self.run_name_edit.textChanged.connect(self._schedule_run_status_refresh)
        self.runs_dir_edit.textChanged.connect(self._schedule_run_status_refresh)
        self.waveform_combo.currentIndexChanged.connect(self._on_waveform_combo_changed)
        self.scattering_model_combo.currentIndexChanged.connect(
            self._on_scattering_model_combo_changed
        )

    def _sync_mode_combos(self) -> None:
        echo_type = ((self.config_data.get("echo") or {}).get("waveform") or {}).get("type")
        observation = self.config_data.get("observation") or {}
        if echo_type:
            waveform = str(echo_type)
        elif "schedule" in observation:
            waveform = "chirp_pulse_train"
        else:
            waveform = "continuous_wave"
        scattering = str(
            (self.config_data.get("echo") or {}).get("scattering_model", "mesh")
        )
        self.waveform_combo.blockSignals(True)
        self.scattering_model_combo.blockSignals(True)
        self.waveform_combo.setCurrentIndex(max(0, self.waveform_combo.findData(waveform)))
        self.scattering_model_combo.setCurrentIndex(
            max(0, self.scattering_model_combo.findData(scattering))
        )
        self.waveform_combo.blockSignals(False)
        self.scattering_model_combo.blockSignals(False)

    def _on_waveform_combo_changed(self) -> None:
        waveform = str(self.waveform_combo.currentData() or "continuous_wave")
        try:
            self.parameter_form.set_waveform_type(waveform)
            self._refresh_stage_chrome()
        except Exception as exc:
            QMessageBox.critical(self, "参数错误", str(exc))
            self._sync_mode_combos()

    def _on_scattering_model_combo_changed(self) -> None:
        model = str(self.scattering_model_combo.currentData() or "mesh")
        try:
            self.parameter_form.set_scattering_model(model)
            self._refresh_stage_chrome()
        except Exception as exc:
            QMessageBox.critical(self, "参数错误", str(exc))
            self._sync_mode_combos()

    def _load_config(self, path: Path) -> dict:
        config, self._startup_notes = _canonicalize_config(read_json(path, {}))
        return config

    def _is_monostatic_observation(self) -> bool:
        observation = self.config_data.get("observation", {})
        transmitter = observation.get("transmitter")
        receiver = observation.get("receiver")
        if not isinstance(transmitter, dict):
            return False
        if receiver is None:
            return True
        if not isinstance(receiver, dict):
            return False
        # Ignore decorative name differences when comparing geometry.
        left = {k: v for k, v in transmitter.items() if k not in {"id", "name", "same_as"}}
        right = {k: v for k, v in receiver.items() if k not in {"id", "name", "same_as"}}
        return left == right

    def _is_point_target(self) -> bool:
        echo = self.config_data.get("echo", {})
        return str(echo.get("scattering_model", "mesh")).lower() == "point_target"

    def _apply_monostatic_receiver(self) -> None:
        observation = self.config_data.setdefault("observation", {})
        observation.pop("receiver", None)

    def _on_monostatic_toggled(self, checked: bool) -> None:
        try:
            if self.current_stage == "observation":
                self._sync_current_stage(apply_monostatic=False)
        except Exception:
            pass
        self.monostatic_observation = bool(checked)
        observation = self.config_data.setdefault("observation", {})
        if self.monostatic_observation:
            receiver = observation.get("receiver")
            if isinstance(receiver, dict):
                self._bistatic_receiver_backup = copy.deepcopy(receiver)
            self._apply_monostatic_receiver()
        elif self._bistatic_receiver_backup is not None:
            observation["receiver"] = copy.deepcopy(self._bistatic_receiver_backup)
        self._render_stage(preserve_scroll=True)
        self.monostatic_checkbox.setFocus(Qt.FocusReason.OtherFocusReason)

    def _sync_current_stage(self, *, apply_monostatic: bool = True) -> None:
        synced = self.parameter_form.collect()
        if self.current_stage == "observation":
            observation = synced.setdefault("observation", {})
            if self.monostatic_observation and "receiver" not in observation:
                previous = self.config_data.get("observation", {}).get("receiver")
                if isinstance(previous, dict):
                    observation["receiver"] = copy.deepcopy(previous)
        # ParameterForm deliberately keeps a reference to this dict while it
        # rebuilds dynamic widgets.  Replacing it here leaves the form writing
        # to an orphaned model after the next state change.
        normalized = pipeline.normalize_parameter_ownership(synced)
        self.config_data.clear()
        self.config_data.update(normalized)
        if apply_monostatic and self.current_stage == "observation" and self.monostatic_observation:
            self._apply_monostatic_receiver()

    def _select_stage(self, stage: str) -> None:
        if stage == self.current_stage:
            return
        try:
            self._sync_current_stage()
        except Exception as exc:
            QMessageBox.critical(self, "参数错误", str(exc))
            return
        self.current_stage = stage
        self._render_stage(preserve_scroll=False)
        self.stage_buttons[stage].setFocus(Qt.FocusReason.OtherFocusReason)

    def _refresh_stage_chrome(self) -> None:
        for stage, button in self.stage_buttons.items():
            button.setProperty("activeStage", stage == self.current_stage)
            button.style().unpolish(button)
            button.style().polish(button)
        title = STAGE_LABELS[self.current_stage]
        self.scattering_model_control.setVisible(self.current_stage == "echo")
        self.monostatic_checkbox.setVisible(self.current_stage == "observation")
        self.monostatic_checkbox.blockSignals(True)
        self.monostatic_checkbox.setChecked(self.monostatic_observation)
        self.monostatic_checkbox.blockSignals(False)
        self._sync_mode_combos()
        self.run_btn.setText(f"运行：{title.split('. ')[-1]}")
        self._sync_echo_artifact_buttons()
        self._refresh_saved_run_status()
        self._apply_stage_status_labels()

    def _render_stage(self, *, preserve_scroll: bool = False) -> None:
        self.parameter_form.render(
            self.config_data,
            stage=self.current_stage,
            monostatic=self.monostatic_observation,
            point_target=self._is_point_target(),
            preserve_scroll=preserve_scroll,
        )
        self._refresh_stage_chrome()

    def _choose_config(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "选择 pipeline JSON", str(storage.ROOT), "JSON files (*.json);;All files (*)"
        )
        if filename:
            self._load_config_from_entry(Path(filename))

    def _load_config_from_entry(self, selected_path: Path | None = None) -> None:
        try:
            path = Path(selected_path or self.config_path_edit.text()).expanduser()
            if not path.is_absolute():
                path = storage.ROOT / path
            path = path.resolve()
            if not path.is_file():
                raise FileNotFoundError(f"配置文件不存在：{path}")
            loaded, notes = _canonicalize_config(read_json(path, {}))
        except Exception as exc:
            self.config_path_edit.setText(str(self.config_path))
            QMessageBox.critical(self, "载入失败", str(exc))
            return

        previous_path = self.config_path
        previous_config = self.config_data
        previous_name = self.run_name_edit.text()
        previous_status = self.stage_status.copy()
        try:
            self.config_path = path
            self.config_data = loaded
            self.config_path_edit.setText(str(path))
            self.monostatic_observation = self._is_monostatic_observation()
            self.run_name_edit.setText(self.config_path.stem)
            self.stage_status = {stage: "未运行" for stage in STAGES}
            self._render_stage()
            self._append_log(f"[{now_text()}] 已载入配置：{self.config_path}")
            for note in notes:
                self._append_log(note, level="warning")
        except Exception as exc:
            self.config_path = previous_path
            self.config_data = previous_config
            self.stage_status = previous_status
            self.config_path_edit.setText(str(previous_path))
            self.run_name_edit.setText(previous_name)
            self.monostatic_observation = self._is_monostatic_observation()
            self._render_stage()
            QMessageBox.critical(self, "载入失败", str(exc))

    def _validate_config(self, *, stage: str | None = None, through_stage: str | None = None) -> bool:
        try:
            self._sync_current_stage()
            resolved = through_stage or {
                "observation": "observation",
                "echo": "echo",
                "inversion": "inversion",
            }.get(stage, "full_pipeline")
            pipeline.prepare_run(
                self.config_data,
                config_path=self.config_path,
                run_dir=self._run_directory(),
                through_stage=resolved,
            )
        except Exception as exc:
            QMessageBox.critical(self, "配置错误", str(exc))
            return False
        self._append_log(f"[{now_text()}] 配置校验通过。")
        self.progress.setFormat("配置校验通过")
        return True

    def _experiment_name(self) -> str:
        name = self.run_name_edit.text().strip()
        if not name or name in {".", ".."} or name.rstrip(" .") != name or re.search(r'[<>:"/\\|?*\x00-\x1f]', name) or re.match(r"(?i)^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", name):
            raise ValueError("实验名不能留空，也不能包含路径分隔符、Windows 保留字符或保留文件名")
        return name

    def _save_config(self) -> None:
        try:
            self._write_config_to(self.config_path)
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))

    def _write_config_to(self, path: Path, *, create_new: bool = False) -> None:
        self._sync_current_stage()
        payload = copy.deepcopy(self.config_data)
        current_dir = self.config_path.resolve().parent
        target_dir = path.resolve().parent
        if target_dir != current_dir:
            echo = payload.get("echo")
            if isinstance(echo, dict):
                from echo.src.config_normalize import resolve_echo_input_paths

                for key in ("model_path", "observation_info_path"):
                    value = echo.get(key)
                    if not isinstance(value, str) or not value or Path(value).is_absolute():
                        continue
                    try:
                        resolved, _ = resolve_echo_input_paths(
                            {key: value}, config_path=self.config_path
                        )
                    except ValueError:
                        continue  # Preserve an unfinished path draft for later correction.
                    absolute = Path(resolved[key])
                    if not absolute.is_absolute():
                        continue  # A symbolic model such as "analytic" is not a file path.
                    try:
                        echo[key] = os.path.relpath(absolute, target_dir)
                    except ValueError:  # Relative paths cannot span Windows drives.
                        echo[key] = str(absolute)
        if create_new:
            write_json_new(path, payload)
        else:
            write_json(path, payload)
        self.config_data = payload
        self.config_path = path.resolve()
        self.config_path_edit.setText(str(self.config_path))
        self._append_log(f"[{now_text()}] 已保存：{self.config_path}")

    def _save_config_as(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "另存 pipeline JSON",
            str(self.config_path),
            "JSON files (*.json);;All files (*)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not filename:
            return
        try:
            target = Path(filename).resolve()
            if target != self.config_path.resolve() and target.exists():
                raise FileExistsError(f"配置文件已存在：{target}；请选择新文件名")
            self._write_config_to(target, create_new=target != self.config_path.resolve())
        except Exception as exc:
            QMessageBox.critical(self, "另存为失败", str(exc))

    def _run_directory(self) -> Path:
        run_name = self._experiment_name()
        runs_dir = self.runs_dir_edit.text().strip() or "runs"
        return pipeline.abs_path(runs_dir) / run_name

    def _upstream_artifact(self, stage: str, prepared: dict):
        """回波/反演阶段消费的上游产物：(标签, 路径, 缺失时的提示)。"""

        if stage == "echo":
            return (
                "观测信息",
                Path(prepared["observation_output"]),
                "请先运行「1. 观测解算」，或把「实验名 / 运行目录」指向已包含 observation_info.npz 的目录。",
            )
        if stage == "inversion":
            return (
                "回波数据",
                Path(prepared["echo_output_dir"]) / "echo.npz",
                "请先运行「2. 回波仿真」，或把「实验名 / 运行目录」指向已生成 echo.npz 的目录；"
                "该文件存在且阶段指纹一致时才会自动复用。",
            )
        return None

    def _reset_run_buttons(self) -> None:
        self.run_btn.setEnabled(True)
        self.run_all_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def _abort_pending(
        self,
        stage: str | None,
        progress_format: str,
        message: str,
        *,
        dialog_title: str,
        level: str = "error",
    ) -> None:
        if stage:
            self.stage_status[stage] = "失败"
        self._pending_stages = []
        self._reset_run_buttons()
        self.progress.setFormat(progress_format)
        self._render_stage_status_only()
        self._append_log(f"[{now_text()}] {message.splitlines()[0]}", level=level)
        QMessageBox.critical(self, dialog_title, message)

    def _reuse_upstream(self, stage: str, prepared: dict) -> bool:
        upstream = self._upstream_artifact(stage, prepared)
        if upstream is None:
            return True
        label, path, hint = upstream
        artifact_stage = "observation" if stage == "echo" else "echo"
        if not path.exists():
            self._abort_pending(
                stage,
                "缺少上游产物",
                f"找不到{label}：{path}。{hint}",
                dialog_title="缺少上游产物",
            )
            return False
        if label in self._fresh_artifacts:
            return True
        decision = pipeline.check_reusable_artifact(prepared, artifact_stage=artifact_stage)
        if decision.reusable:
            self._append_log(f"[{now_text()}] {decision.reason}：{path}")
            return True
        if decision.requires_confirmation:
            yes = getattr(getattr(QMessageBox, "StandardButton", QMessageBox), "Yes", True)
            reply = QMessageBox.question(
                self,
                "复用历史产物",
                f"{decision.reason}\n\n仍要复用 {path} 吗？",
            )
            if reply == yes:
                self._append_log(
                    f"[{now_text()}] 已确认复用缺少指纹的{label}：{path}",
                    level="warning",
                )
                return True
        self._abort_pending(
            stage,
            "上游产物不兼容",
            f"{decision.reason}\n{path}",
            dialog_title="上游产物不兼容",
        )
        return False

    def _run_current_stage(self) -> None:
        self._start_stages([self.current_stage])

    def _run_full_pipeline(self) -> None:
        self._start_stages(list(STAGES))

    def _start_stages(self, stages: list[str]) -> None:
        if self.feature_preview_process is not None:
            QMessageBox.information(self, "正在运行", "正在生成特征图，请先等待完成或中止。")
            return
        if self.process and self.process.state() != NOT_RUNNING:
            QMessageBox.information(self, "正在运行", "当前已有任务在运行。")
            return
        through = "full_pipeline" if list(stages) == list(STAGES) else stages[0]
        for stage in stages:
            self.stage_status[stage] = "校验中"
        self._render_stage_status_only()
        self.progress.setFormat("校验中")
        if not self._validate_config(through_stage=through):
            self.stage_status[stages[0]] = "失败"
            for stage in stages[1:]:
                if self.stage_status.get(stage) == "校验中":
                    self.stage_status[stage] = "未运行"
            self._pending_stages = []
            self._reset_run_buttons()
            self.progress.setFormat("校验失败")
            self._render_stage_status_only()
            return
        self._pending_stages = list(stages)
        self._fresh_artifacts = set()
        self._run_next_pending_stage()

    def _run_next_pending_stage(self) -> None:
        if not getattr(self, "_pending_stages", None):
            self.run_btn.setEnabled(True)
            self.run_all_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.progress.setFormat("全部完成")
            return
        stage = self._pending_stages.pop(0)
        try:
            run_dir = self._run_directory()
            config_dir = run_dir / "configs"
            through = {
                "observation": "observation",
                "echo": "echo",
                "inversion": "inversion",
            }[stage]
            prepared = pipeline.prepare_run(
                self.config_data,
                config_path=self.config_path,
                run_dir=run_dir,
                through_stage=through,
            )
            if not self._reuse_upstream(stage, prepared):
                return
            if stage == "inversion":
                observation_path = Path(prepared["observation_output"])
                echo_path = Path(prepared["echo_output_dir"]) / "echo.npz"
                if observation_path.exists() and echo_path.exists():
                    try:
                        pipeline.validate_observation_echo_contract(
                            observation_path, echo_path
                        )
                    except ValueError as exc:
                        self._abort_pending(
                            stage,
                            "上游产物不兼容",
                            str(exc),
                            dialog_title="上游产物不兼容",
                        )
                        return
            write_json(config_dir / f"{stage}.generated.json", prepared[stage])
            write_json(run_dir / "manifest.json", pipeline.build_manifest(prepared["snapshot"]))
            python_exe = self.python_edit.text().strip() or sys.executable
            command, cwd, env = self._stage_command(stage, python_exe, config_dir, prepared)
            self.process_outputs = stage_output_paths(prepared)
            self.process_prepared = prepared
        except Exception as exc:
            QMessageBox.critical(self, "启动失败", str(exc))
            self._pending_stages = []
            self._reset_run_buttons()
            if stage:
                self.stage_status[stage] = "失败"
            self.progress.setFormat("启动失败")
            self._render_stage_status_only()
            self._append_log(f"[{now_text()}] 启动失败：{exc}", level="error")
            return

        self.process = QProcess(self)
        self.process_stage = stage
        self.process_run_dir = run_dir
        self.process_output_buffer = ""
        self.process.setWorkingDirectory(str(cwd))
        process_env = QProcessEnvironment.systemEnvironment()
        for key, value in env.items():
            if value is not None:
                process_env.insert(str(key), str(value))
        self.process.setProcessEnvironment(process_env)
        # 合并两个通道，避免同一时刻读到的 stdout 残行与 stderr 文本粘成一行。
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_process_output)
        self.process.finished.connect(self._process_finished)
        self.process.errorOccurred.connect(self._process_error)
        self._abort_requested = False
        self.run_btn.setEnabled(False)
        self.run_all_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.stage_status[stage] = "运行中"
        self._render_stage_status_only()
        self.progress.setValue(0)
        self.progress.setFormat(f"正在执行 {STAGE_LABELS[stage]}")
        self._append_log(f"\n[{now_text()}] 启动 {STAGE_LABELS[stage]}")
        self._append_log("命令：" + " ".join(map(str, command)))
        self.process.start(str(command[0]), [str(item) for item in command[1:]])

    def _stage_command(self, stage: str, python_exe: str, config_dir: Path, prepared: dict):
        env = pipeline.child_env()
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
                storage.ROOT / "observation",
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
                storage.ROOT / "echo",
                env,
            )
        inversion_src = str(storage.ROOT / "inversion" / "src")
        if not pipeline.INVERSION_ENTRY.is_file():
            raise FileNotFoundError(f"找不到反演入口：{pipeline.INVERSION_ENTRY}")
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
            storage.ROOT / "inversion",
            pipeline.child_env([inversion_src]),
        )

    STALE_STATUS = "参数修改，需重新运行⚠"

    def _schedule_run_status_refresh(self) -> None:
        self._sync_echo_artifact_buttons()
        timer = getattr(self, "_run_status_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda: self._refresh_saved_run_status(overwrite_errors=True))
            self._run_status_timer = timer
        timer.start(200)

    def _apply_stage_status_labels(self) -> None:
        for stage, label in self.stage_status_labels.items():
            text = self.stage_status[stage]
            label.setText(f"状态：{text}")
            if text == self.STALE_STATUS:
                kind = "stale"
            elif text == "已运行":
                kind = "ran"
            else:
                kind = ""
            label.setProperty("statusKind", kind)
            label.style().unpolish(label)
            label.style().polish(label)

    def _render_stage_status_only(self) -> None:
        self._apply_stage_status_labels()

    def _refresh_saved_run_status(self, *, overwrite_errors: bool = False) -> None:
        """Mark a stage 已运行 when its product matches the current parameters."""

        if self.process is not None and self.process.state() != NOT_RUNNING:
            return
        try:
            synced = self.parameter_form.collect()
        except Exception:
            return
        self.config_data.clear()
        self.config_data.update(synced)
        run_dir = self._run_directory()
        try:
            prepared = pipeline.prepare_run(
                self.config_data,
                config_path=self.config_path,
                run_dir=run_dir,
                through_stage="full_pipeline",
            )
        except Exception:
            return
        manifest = pipeline.load_stage_manifest(run_dir)
        artifacts = {
            "observation": (
                Path(prepared["observation_output"]),
                prepared.get("observation_fingerprint"),
            ),
            "echo": (
                Path(prepared["echo_output_dir"]) / "echo.npz",
                prepared.get("echo_fingerprint"),
            ),
            "inversion": (
                Path(prepared["inversion_output_dir"]) / "summary.json",
                prepared.get("inversion_fingerprint"),
            ),
        }
        busy = {"运行中", "校验中"}
        held = set() if overwrite_errors else {"失败", "已中止"}
        for stage, (path, fingerprint) in artifacts.items():
            if self.stage_status.get(stage) in busy or self.stage_status.get(stage) in held:
                continue
            if not path.is_file() or path.stat().st_size <= 0:
                self.stage_status[stage] = "未运行"
                continue
            if (manifest.get(stage) or {}).get("invalidated_by"):
                self.stage_status[stage] = self.STALE_STATUS
                continue
            recorded = (manifest.get(stage) or {}).get("fingerprint")
            if recorded:
                matched = pipeline.stage_record_matches(prepared, stage, manifest.get(stage) or {})
                identity = (manifest.get(stage) or {}).get("output_identity")
                if identity is not None:
                    matched = matched and identity == pipeline.artifact_identity(path)
            else:
                key = (str(run_dir.resolve()), stage, path.stat().st_mtime_ns, path.stat().st_size)
                baseline = self._untracked_run_baselines.get(key)
                if baseline is None:
                    self._untracked_run_baselines[key] = fingerprint
                    matched = True
                else:
                    matched = fingerprint == baseline
            self.stage_status[stage] = "已运行" if matched else self.STALE_STATUS
        self._apply_stage_status_labels()

    def _stop_pipeline(self) -> None:
        if self.feature_preview_process is not None:
            self._feature_preview_cancelled = True
            self.feature_preview_process.kill()
            return
        self._pending_stages = []
        if self.process and self.process.state() != NOT_RUNNING:
            self._abort_requested = True
            self.process.kill()
            self._append_log(f"[{now_text()}] 已请求中止。")

    def _read_process_output(self) -> None:
        if not self.process:
            return
        text = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if not text:
            return
        self.process_output_buffer += text
        lines = self.process_output_buffer.splitlines(keepends=True)
        if lines and not lines[-1].endswith(("\n", "\r")):
            self.process_output_buffer = lines.pop()
        else:
            self.process_output_buffer = ""
        for line in lines:
            self._handle_output_line(line.rstrip())

    @staticmethod
    def _protocol_payload(raw: str):
        """解析机器协议载荷；解析失败返回 None，调用方不得回退到原始控制行。"""

        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _handle_output_line(self, line: str) -> None:
        for prefix, level in ((ERROR_PREFIX, "error"), (WARNING_PREFIX, "warning")):
            if not line.startswith(prefix):
                continue
            remainder = line[len(prefix) :]
            payload = self._protocol_payload(remainder)
            stage = str(payload.get("stage", self.process_stage or "")) if payload else str(self.process_stage or "")
            stage_name = STAGE_LABELS.get(stage, stage).split(". ", 1)[-1]
            # 严重程度由日志徽标表达，消息里不再重复“警告/错误”字样。
            message = str(payload.get("message", "")) if payload else remainder.strip()
            self._append_log(
                f"[{now_text()}] {stage_name}：{message}" if stage_name else f"[{now_text()}] {message}",
                level=level,
            )
            if payload and payload.get("dialog") and level == "warning" and message:
                QMessageBox.warning(self, "运行警告", message)
            return
        if line.startswith(PROGRESS_PREFIX):
            payload = self._protocol_payload(line[len(PROGRESS_PREFIX) :])
            if payload is not None:
                try:
                    percent = int(payload.get("percent", 0))
                except (TypeError, ValueError):
                    percent = self.progress.value()
                message = str(payload.get("message", ""))
                self.progress.setValue(max(0, min(100, percent)))
                self.progress.setFormat(f"{percent}%  {message}")
                return
            remainder = line[len(PROGRESS_PREFIX) :].strip()
            if remainder:
                self._append_log(f"[{now_text()}] {remainder}")
            return
        if line.startswith(SUMMARY_PREFIX):
            payload = self._protocol_payload(line[len(SUMMARY_PREFIX) :])
            if payload is None:
                remainder = line[len(SUMMARY_PREFIX) :].strip()
                if remainder:
                    self._append_log(f"[{now_text()}] {remainder}")
                return
            stage = str(payload.get("stage", self.process_stage or ""))
            title = str(payload.get("title") or STAGE_LABELS.get(stage, "结果"))
            self._append_log(f"[{now_text()}] {title}")
            for item in payload.get("items") or []:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    label, value = item
                elif isinstance(item, dict):
                    label, value = item.get("label", ""), item.get("value", "")
                else:
                    continue
                self._append_log(f"    {label}：{value}")
            return
        if line.startswith("Wrote "):
            written = line[6:].strip()
            outputs = self.process_outputs.get(self.process_stage or "", ())
            if outputs and Path(written) == Path(outputs[0][1]):
                # 阶段完成行会报告同一个产物，这里不再重复。
                return
            self._append_log(f"已写入：{written}")
            return
        if line.startswith("samples="):
            self._append_log(f"样本数：{line[8:]}")
            return
        if line.startswith("start_utc="):
            self._append_log(f"观测起点：{line[10:]}")
            return
        self._append_log(line)

    def _process_error(self, error) -> None:
        if self.process is None or self._abort_requested:
            return
        message = self.process.errorString()
        if error != QProcess.ProcessError.FailedToStart:
            self._append_log(message, level="error")
            return
        # 启动失败时 QProcess 不会再发 finished，必须在这里收尾，否则界面会一直停在“运行中”。
        stage = self.process_stage
        self.process = None
        self.process_stage = None
        if stage:
            self.stage_status[stage] = "失败"
        self._pending_stages = []
        self._reset_run_buttons()
        self.progress.setFormat("启动失败")
        self._render_stage_status_only()
        self._append_log(f"[{now_text()}] 无法启动进程：{message}", level="error")
        QMessageBox.critical(self, "运行失败", f"无法启动进程：{message}")

    def _process_finished(self, exit_code: int, *_args) -> None:
        if self.process_output_buffer:
            self._handle_output_line(self.process_output_buffer)
            self.process_output_buffer = ""
        stage = self.process_stage
        aborted = self._abort_requested
        self.process = None
        self.process_stage = None
        self._abort_requested = False
        if exit_code == 0 and not aborted:
            outputs = self.process_outputs.get(stage or "", ())
            primary = Path(outputs[0][1]) if outputs else None
            if primary is not None:
                try:
                    if stage in {"observation", "echo"}:
                        pipeline.require_stage_artifact(primary, stage)
                    elif not primary.exists():
                        raise ValueError(f"主产物为空或不存在：{primary}")
                except ValueError:
                    if stage:
                        self.stage_status[stage] = "失败"
                    self._pending_stages = []
                    self._reset_run_buttons()
                    self.progress.setFormat("主产物缺失")
                    self._render_stage_status_only()
                    self._append_log(
                        f"[{now_text()}] 退出码为 0 但未找到有效主产物：{primary}",
                        level="error",
                    )
                    QMessageBox.critical(self, "运行失败", f"退出码为 0 但未找到有效主产物：\n{primary}")
                    return
            if stage in {"observation", "echo"} and self.process_prepared and self.process_run_dir:
                prepared = self.process_prepared
                if stage == "observation":
                    pipeline.write_stage_success(
                        self.process_run_dir,
                        "observation",
                        fingerprint=prepared["observation_fingerprint"],
                        projection=pipeline.observation_dependency_projection(
                            prepared["observation"]
                        ),
                        output_path=prepared["observation_output"],
                    )
                else:
                    observation_sha = pipeline.artifact_identity(prepared["observation_output"])
                    echo_proj = pipeline.echo_dependency_projection(
                        prepared["echo"],
                        observation_sha,
                        config_path=prepared.get("config_path"),
                    )
                    pipeline.write_stage_success(
                        self.process_run_dir,
                        "echo",
                        fingerprint=pipeline.canonical_fingerprint(echo_proj),
                        projection=echo_proj,
                        output_path=Path(prepared["echo_output_dir"]) / "echo.npz",
                    )
            elif stage == "inversion" and self.process_prepared and self.process_run_dir:
                prepared = self.process_prepared
                summary = Path(prepared["inversion_output_dir"]) / "summary.json"
                pipeline.write_stage_success(
                    self.process_run_dir,
                    "inversion",
                    fingerprint=prepared["inversion_fingerprint"],
                    projection={
                        "inversion": prepared["inversion"],
                        "echo_identity": pipeline.artifact_identity(
                            Path(prepared["echo_output_dir"]) / "echo.npz"
                        ),
                    },
                    output_path=summary,
                    contract_version="inversion-1",
                )
            if stage:
                self.stage_status[stage] = "成功"
                self._fresh_artifacts.update(
                    label for label, _path in self.process_outputs.get(stage, ())
                )
            self.progress.setValue(100)
            self.progress.setFormat("完成")
            self._append_log(f"[{now_text()}] {STAGE_LABELS.get(stage, stage)} 完成。")
            self._refresh_saved_run_status(overwrite_errors=True)
            for label, path in self.process_outputs.get(stage, ()):
                self._append_log(f"[{now_text()}] {label}：{path}", level="success")
            if stage == "echo" and self.process_run_dir is not None:
                self._sync_echo_artifact_buttons()
            self._run_next_pending_stage()
            return
        if aborted:
            if stage:
                self.stage_status[stage] = "已中止"
            self._pending_stages = []
            self._reset_run_buttons()
            self.progress.setFormat("已中止")
            self._render_stage_status_only()
            self._append_log(
                f"[{now_text()}] 已中止：{STAGE_LABELS.get(stage, stage or '')}。",
                level="warning",
            )
            return
        if stage:
            self.stage_status[stage] = "失败"
        self._pending_stages = []
        self._reset_run_buttons()
        self.progress.setFormat(f"失败：退出码 {exit_code}")
        self._append_log(f"[{now_text()}] 失败，退出码 {exit_code}。", level="error")
        self._render_stage_status_only()
        QMessageBox.critical(self, "运行失败", f"阶段失败，退出码 {exit_code}")

    def _append_log(self, text: str, *, level: str | None = None) -> None:
        for line in str(text).split("\n"):
            kind = level
            if kind is None:
                if "警告" in line or "warning" in line.lower() or "中止" in line:
                    kind = "warning"
                elif "失败" in line or "错误" in line or "error" in line.lower():
                    kind = "error"
                elif any(token in line for token in (" 完成。", "已保存：", "已载入配置：", "已恢复上次会话：", "校验通过", "预览已就绪")):
                    kind = "success"
            colors = {
                "success": ("成功", "#177245", "#e8f7ed"),
                "warning": ("警告", "#a86100", "#fff3d6"),
                "error": ("错误", "#b4232c", "#fdebed"),
            }
            escaped = html.escape(line)
            if kind in colors:
                label, color, background = colors[kind]
                self.log.append(f'<span style="color:{color};background-color:{background};font-weight:600;"> {label} </span> <span style="color:{color};">{escaped}</span>')
            else:
                # QTextEdit.append() 只有在参数看起来像富文本时才按 HTML 解析；直接
                # 追加转义后的普通行会按字面插入，日志里就会出现 &quot; 之类的实体。
                # 因此普通行也显式包一层 span，并用 pre-wrap 保留 JSON 的缩进。
                self.log.append(f'<span style="white-space:pre-wrap;">{escaped}</span>')

    def _echo_identity(self):
        path = self._run_directory() / "echo" / "echo.npz"
        if not path.is_file() or path.stat().st_size <= 0:
            return None
        stat = path.stat()
        return (str(path.resolve()), stat.st_mtime_ns, stat.st_size)

    def _set_preview_ready(self, ready: bool) -> None:
        self.preview_btn.setEnabled(bool(ready))
        identity = self._echo_identity()
        seen = identity is not None and identity in self._opened_previews["echo"]
        self.preview_btn.set_attention(bool(ready) and not seen)
        if ready:
            self.preview_btn.setToolTip("回波已生成，点击打开 Plotly 交互预览")
        else:
            self.preview_btn.setToolTip("回波仿真完成后可查看交互预览")

    def _echo_preview_artifacts_compatible(self, run_dir: Path) -> bool:
        echo_npz = run_dir / "echo" / "echo.npz"
        if not echo_npz.exists():
            self._set_preview_ready(False)
            self._append_log(f"[{now_text()}] 未找到回波文件，无法生成预览：{echo_npz}")
            return False
        observation_npz = run_dir / "observation_info.npz"
        if observation_npz.exists():
            try:
                pipeline.validate_observation_echo_contract(
                    observation_npz, echo_npz
                )
            except ValueError as exc:
                self._set_preview_ready(False)
                self.echo_preview_html = None
                self._append_log(
                    f"[{now_text()}] 回波预览拒绝不兼容产物：{exc}", level="error"
                )
                return False
        return True

    def _prepare_echo_preview(self, run_dir: Path) -> None:
        if not self._echo_preview_artifacts_compatible(run_dir):
            return
        echo_npz = run_dir / "echo" / "echo.npz"
        try:
            from .echo_preview import build_echo_preview_html, echo_preview_html_path

            html_path = echo_preview_html_path(run_dir)
            build_echo_preview_html(echo_npz, html_path)
            self.echo_preview_html = html_path
            self._set_preview_ready(True)
            self._append_log(f"[{now_text()}] 回波预览已就绪：{html_path}")
        except Exception as exc:
            self._set_preview_ready(False)
            self.echo_preview_html = None
            self._append_log(f"[{now_text()}] 回波预览生成失败：{exc}")

    def _open_echo_preview(self) -> None:
        run_dir = self._run_directory()
        if not self._echo_preview_artifacts_compatible(run_dir):
            return
        self._open_run_view('raw')

    def _sync_echo_artifact_buttons(self) -> None:
        """Enable echo viewers when this experiment folder already has echo.npz."""

        identity = self._echo_identity()
        ready = identity is not None
        busy = self.feature_preview_process is not None or (
            self.process is not None and self.process.state() != NOT_RUNNING)
        self._set_preview_ready(ready and not busy)
        from .result_service import completed_inversion
        inversion_ready=completed_inversion(self._run_directory()/'echo/echo.npz') is not None
        self.feature_preview_btn.setEnabled(inversion_ready and not busy)
        self.result_btn.setEnabled(not busy)
        seen = identity is not None and identity in self._opened_previews["features"]
        self.feature_preview_btn.set_attention(inversion_ready and not seen)
        if inversion_ready:
            self.feature_preview_btn.setToolTip(
                '只查看已完成反演保存的实际特征；不启动计算'
            )
        else:
            self.feature_preview_btn.setToolTip(
                "当前实验尚无已完成的周期反演结果；请先运行周期反演。"
            )

    def _open_inversion_artifact(self, filename) -> None:
        from .result_service import completed_inversion
        if completed_inversion(self._run_directory()/'echo/echo.npz') is None:
            QMessageBox.information(self,'反演结果','请先完成周期反演；看图不启动计算。')
            return
        path = self._run_directory() / 'inversion' / filename
        if filename == 'processing.html' and path.with_name('processing_preview.npz').is_file():
            try:
                from .inversion_feature_preview import _views
                _views().render_saved_processing(path.with_name('processing_preview.npz'), path)
            except Exception as exc:
                QMessageBox.critical(self, '处理过程图', str(exc))
                return
        if not path.is_file():
            QMessageBox.information(self, '反演结果',
                '尚无此结果。新版反演完成后会保存处理过程；历史结果可直接查看已有周期搜索曲线。')
            return
        from .inversion_feature_preview import open_echo_preview_in_browser
        open_echo_preview_in_browser(path)
        self._append_log(f'[{now_text()}] 打开上次保存的反演结果：{path.name}')

    def _build_result_dialog(self, *, defer_status=False):
        # Qt.Popup is non-modal, anchored, and closes on outside click or Esc.
        popup = ResultPopup(self)
        popup._async_status = defer_status
        popup.setObjectName('resultPopup')
        popup.setMinimumWidth(430)
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        title = QLabel('图像结果 · ' + self.run_name_edit.text())
        title.setObjectName('cardTitle')
        layout.addWidget(title)
        selection = QHBoxLayout()
        self.result_run_combo = QComboBox(popup)
        self.result_cpi_spin = QComboBox(popup)
        self.result_cpi_spin.setToolTip('周期反演相同参数产生的CPI窗口，不是另一个时间步长。')
        echo_path = self._run_directory() / 'echo/echo.npz'
        chirp = False
        try:
            from .result_service import run_catalog, array_header
            if defer_status:
                self.result_run_combo.addItem('正在读取已保存结果…',None)
            else:
                chirp = len(array_header(echo_path, 'iq')[0]) == 2
                if chirp:self.result_run_combo.addItem('全观测区间 · 所有Run',-1)
                for number, (run, count) in enumerate(run_catalog(echo_path), 1):
                    self.result_run_combo.addItem(f'Run {number} · id={run} · {count}脉冲' if chirp else f'CW前{count}样点', run)
                current = self.result_run_combo.findData(getattr(self, '_selected_run', -1 if chirp else 0))
                if current >= 0:
                    self.result_run_combo.setCurrentIndex(current)
        except Exception:
            chirp = False
            self.result_run_combo.addItem('无有效回波', None)
        selection.addWidget(QLabel('查看范围'))
        selection.addWidget(self.result_run_combo, 1)
        selection.addWidget(QLabel('CPI窗口'))
        selection.addWidget(self.result_cpi_spin)
        layout.addLayout(selection)
        self.result_run_combo.currentIndexChanged.connect(lambda _: self._result_selection_changed(popup,run_changed=True))
        self.result_cpi_spin.currentIndexChanged.connect(lambda _: self._result_selection_changed(popup,run_changed=False))
        if not defer_status:self._selected_run = self.result_run_combo.currentData()
        self.result_cpi_spin.setEnabled(chirp)
        if not defer_status:self._refresh_cpi_windows()
        else:
            self.result_cpi_spin.blockSignals(True)
            self.result_cpi_spin.addItem('正在读取…',None)
            self.result_cpi_spin.blockSignals(False)
        from .result_service import saved_view_available
        selected_run=self.result_run_combo.currentData()
        if selected_run is None:selected_run=-1
        def available(kind):
            return False if defer_status else saved_view_available(echo_path,kind,selected_run)
        groups = (
            ('回波', (('原始回波', lambda: self._open_echo_preview(), False if defer_status else echo_path.is_file(), '默认全场；可选单Run；不脉压'),
                      ('脉冲压缩', lambda: self._open_run_view('compression'), chirp and available('compression'), '只读反演时保存的脉压检查；缺少时请运行周期反演'))),
            ('特征', (('实际反演特征', lambda: self._open_actual_features(), available('saved'), '上次完成反演的特征快照，不重新计算'),
                      ('逐脉冲检查', lambda: self._open_feature_preview(pulse_only=True), chirp and available('pulse'), '只读已保存的逐脉冲三特征；不计算多普勒'))),
            ('反演', (('距离—多普勒', lambda: self._open_run_view('rd'), chirp and available('rd'), '只读已保存CPI；不进行脉压、FFT或反演'),
                      ('周期搜索', lambda: self._open_inversion_artifact('periodogram.html'), available('period'), '上次保存的曲线和候选，不重跑搜索'),
                      ('融合诊断', lambda: self._open_inversion_artifact('period_selection.html'), available('selection'), '查看共同周期、留出预测和逐特征冲突；只读上次反演报告'),
                      ('误差诊断', lambda: self._open_inversion_artifact('period_uncertainty.html'), available('uncertainty'), '只读反演时保存的误差评估；需先启用按Run重采样并运行反演'))),
        )
        self._result_actions={}
        for group, items in groups:
            row = QHBoxLayout()
            row.addWidget(QLabel(group))
            for label, action, enabled, tip in items:
                button = QPushButton(label, popup)
                button.setEnabled(enabled)
                button.setToolTip(tip)
                self._result_actions[label]=button
                button.clicked.connect(lambda checked=False, action=action: (popup.hide(), action()))
                row.addWidget(button, 1)
            layout.addLayout(row)
        from .result_service import completed_inversion
        context=None if defer_status else completed_inversion(echo_path)
        saved_note=('尚未完成周期反演；图像按钮不启动反演计算。' if context is None else
            f"已保存结果：{context['path'] or 'CW'} · {context['observations']}个观测 · "
            f"{context['config'].get('doppler_estimator','spectral_moments')}。当前参数不参与绘图。")
        note = QLabel(saved_note+' Run / CPI用于回波与频谱图；特征和周期图保留全场观测。')
        note.setWordWrap(True)
        note.setObjectName('panelHint')
        if defer_status:note.setText('正在后台读取已有结果；可再次点击图像结果关闭。')
        popup._status_note=note
        layout.addWidget(note)
        return popup

    def _refresh_result_actions(self):
        from .result_service import saved_view_available
        source=self._run_directory()/'echo/echo.npz'
        run=self.result_run_combo.currentData()
        for label,kind in (('脉冲压缩','compression'),('实际反演特征','saved'),('逐脉冲检查','pulse'),('距离—多普勒','rd'),('周期搜索','period'),('融合诊断','selection'),('误差诊断','uncertainty')):
            button=getattr(self,'_result_actions',{}).get(label)
            if button is not None:button.setEnabled(saved_view_available(source,kind,-1 if run is None else run,getattr(self,'_selected_cpi',-1) if kind=='rd' else -1))

    def _refresh_cpi_windows(self):
        source=self._run_directory()/'echo/echo.npz'
        self.result_cpi_spin.blockSignals(True)
        self.result_cpi_spin.clear()
        try:
            from .result_service import cpi_catalog
            from .result_service import completed_inversion
            context=completed_inversion(source)
            if context is not None:
                for index,label in cpi_catalog(source,context['config'],self.result_run_combo.currentData()):
                    if index>=0:self.result_cpi_spin.addItem(label,index)
        except Exception:
            pass
        if self.result_cpi_spin.count()==0:self.result_cpi_spin.addItem('没有已保存的CPI窗口',None)
        self.result_cpi_spin.blockSignals(False)
        self._selected_cpi=self.result_cpi_spin.currentData() or 0

    def _open_result_dialog(self, _checked=False):
        previous = getattr(self, '_result_popup', None)
        if previous is not None:
            if previous.isVisible():
                previous.hide()
                return
            previous.hide()
            previous.deleteLater()
        popup = self._build_result_dialog(defer_status=True)
        self._result_popup = popup
        popup.adjustSize()
        position = self.result_btn.mapToGlobal(self.result_btn.rect().bottomLeft())
        position.setX(position.x() + self.result_btn.width() - popup.width())
        screen = self.screen().availableGeometry()
        position.setX(max(screen.left(), min(position.x(), screen.right() - popup.width())))
        position.setY(max(screen.top(), min(position.y(), screen.bottom() - popup.height())))
        popup.move(position)
        popup.show()
        self._request_result_status()

    def _result_selection_changed(self,popup,*,run_changed):
        if run_changed:self._selected_run=self.result_run_combo.currentData()
        else:self._selected_cpi=self.result_cpi_spin.currentData()
        if popup._async_status:
            self._request_result_status()
        else:
            if run_changed:self._refresh_cpi_windows()
            self._refresh_result_actions()

    def _request_result_status(self):
        from concurrent.futures import ThreadPoolExecutor
        from .result_service import result_menu_snapshot
        if not hasattr(self,'_result_status_executor'):
            self._result_status_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='result-status')
            self._result_status_timer=QTimer(self)
            self._result_status_timer.setInterval(20)
            self._result_status_timer.timeout.connect(self._poll_result_status)
        old=getattr(self,'_result_status_future',None)
        if old is not None:old.cancel()
        run=getattr(self,'_selected_run',-1)
        cpi=getattr(self,'_selected_cpi',-1)
        source=self._run_directory()/'echo/echo.npz'
        self._result_status_source=source
        self._result_status_popup=self._result_popup
        for button in getattr(self,'_result_actions',{}).values():
            if button.text()!='原始回波':button.setEnabled(False)
        self._result_popup._status_note.setText('正在后台读取已有结果；可再次点击图像结果关闭。')
        self._result_status_future=self._result_status_executor.submit(result_menu_snapshot,source,
            -1 if run is None else run,-1 if cpi is None else cpi)
        self._result_status_timer.start()

    def _poll_result_status(self):
        future=getattr(self,'_result_status_future',None)
        if future is None or not future.done():return
        self._result_status_timer.stop()
        popup=getattr(self,'_result_popup',None)
        if (popup is not self._result_status_popup or not popup.isVisible()
                or self._run_directory()/'echo/echo.npz'!=self._result_status_source):return
        try:state=future.result()
        except Exception as error:
            popup._status_note.setText(f'读取保存结果失败：{error}')
            return
        combo=self.result_run_combo
        combo.blockSignals(True)
        combo.clear()
        if state['chirp']:combo.addItem('全观测区间 · 所有Run',-1)
        for index,(run,count) in enumerate(state['runs'],1):
            combo.addItem(f'Run {index} · id={run} · {count}脉冲' if state['chirp'] else f'CW前{count}样点',run)
        if combo.count()==0:combo.addItem(state['error'] or '无有效回波',None)
        found=combo.findData(state['run_id'])
        if found>=0:combo.setCurrentIndex(found)
        self._selected_run=combo.currentData()
        combo.blockSignals(False)
        cpi=self.result_cpi_spin
        cpi.blockSignals(True)
        previous=state['cpi_index']
        cpi.clear()
        for index,label in state['cpis']:
            if index>=0:cpi.addItem(label,index)
        if cpi.count()==0:cpi.addItem('没有已保存的CPI窗口',None)
        found=cpi.findData(previous)
        if found>=0:cpi.setCurrentIndex(found)
        self._selected_cpi=cpi.currentData()
        cpi.setEnabled(state['chirp'])
        cpi.blockSignals(False)
        for label,kind in (('脉冲压缩','compression'),('实际反演特征','saved'),('逐脉冲检查','pulse'),
                ('距离—多普勒','rd'),('周期搜索','period'),('融合诊断','selection'),('误差诊断','uncertainty')):
            self._result_actions[label].setEnabled(state['available'].get(kind,False))
        context=state['context']
        self._result_actions['原始回波'].setEnabled(state['source_exists'])
        popup._status_note.setText(('尚未完成周期反演；图像按钮不启动计算。' if context is None else
            f"已保存结果：{context['path'] or 'CW'} · {context['observations']}个观测。当前参数不参与绘图。")+
            ' Run / CPI用于回波与频谱图；再次点击图像结果可关闭。')

    def _open_actual_features(self):
        from .result_service import saved_view_available
        if not saved_view_available(self._run_directory()/'echo/echo.npz','saved'):
            QMessageBox.information(self, '实际反演特征', '请先运行周期反演；看图不会启动计算。')
            return
        self._open_feature_preview()

    def _open_run_view(self, kind):
        if self.feature_preview_process is not None or (self.process is not None and self.process.state() != NOT_RUNNING):
            return
        try:
            source = self._run_directory() / 'echo/echo.npz'
            if kind=='raw' and not self._echo_preview_artifacts_compatible(self._run_directory()):
                return
            from .result_service import cached, run_catalog,completed_inversion,saved_view_available
            from .inversion_feature_preview import open_echo_preview_in_browser
            run = getattr(self, '_selected_run', None)
            if run is None:
                run = run_catalog(source)[0][0]
            cpi = getattr(self, '_selected_cpi', 0)
            context=completed_inversion(source)
            if kind!='raw' and (context is None or not saved_view_available(source,kind,run)):
                QMessageBox.information(self,'图像结果','尚无此保存结果；请运行周期反演。看图不会启动科学计算。')
                return
            config=dict(self.config_data.get('inversion') or {}) if kind=='raw' else context['config']
            folder = storage.PREVIEW_DIR / self._run_directory().name.replace(' ', '_')
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f'{kind}_run_{run}'
            path = path.with_name(path.name + (f'_cpi_{cpi}' if kind == 'rd' else '') + '.html')
            if cached(source, config, path, kind, run, cpi):
                open_echo_preview_in_browser(path)
                self._append_log(f'[{now_text()}] 复用图像：{path.name}')
                return
            args = ['-m', 'rotation_gui.window.result_service', '--echo', str(source), '--output', str(path),
                '--config-json', json.dumps(config), '--kind', kind, '--run-id', str(run), '--cpi-index', str(cpi),'--read-only']
            self._start_view_worker(path, args, kind)
        except Exception as exc:
            QMessageBox.critical(self, '图像结果', str(exc))

    def _open_feature_preview(self, _checked=False, *, pulse_only=False) -> None:
        if self.feature_preview_process is not None or (
            self.process is not None and self.process.state() != NOT_RUNNING):
            return
        echo_npz = self._run_directory() / "echo" / "echo.npz"
        from .result_service import completed_inversion,saved_view_available
        context=completed_inversion(echo_npz)
        if context is None or (pulse_only and not saved_view_available(echo_npz,'pulse')):
            QMessageBox.information(self,'特征图','尚无此保存结果。请先运行周期反演；看图不会启动科学计算。')
            return
        observables = self._run_directory() / 'inversion' / 'period_observables.npz'
        if not echo_npz.is_file() and (pulse_only or not observables.is_file()):
            QMessageBox.information(
                self,
                "特征图",
                "尚无回波文件。请先运行回波仿真，或把实验名指向已有 echo.npz 的目录。",
            )
            self._sync_echo_artifact_buttons()
            return
        try:
            from .inversion_feature_preview import inversion_feature_html_path
            html_path = inversion_feature_html_path(self._run_directory())
            config_json = json.dumps(context['config'])
            observables = self._run_directory() / 'inversion' / 'period_observables.npz'
            saved = observables.is_file() and not pulse_only
            if saved:
                html_path = observables.with_name('features.html')
            from .inversion_feature_preview import cached_feature_html, open_echo_preview_in_browser
            from .result_service import cached
            if cached_feature_html(observables if saved else echo_npz, json.loads(config_json), html_path, saved=saved, echo_npz=echo_npz) or (pulse_only and cached(echo_npz,context['config'],html_path,'pulse',0)):
                open_echo_preview_in_browser(html_path)
                identity = self._echo_identity()
                if identity is not None:
                    self._opened_previews['features'].add(identity)
                self._sync_echo_artifact_buttons()
                self._append_log(f'[{now_text()}] 复用已保存的特征图，无需计算回波。')
                return
        except Exception as exc:
            self._append_log(f"[{now_text()}] 特征图生成失败：{exc}", level="error")
            QMessageBox.critical(self, "特征图", str(exc))
            return
        kind='saved' if saved else 'pulse'
        args = ["-m", "rotation_gui.window.result_service", "--echo", str(echo_npz),
                "--output", str(html_path), "--config-json", config_json, '--kind', kind,'--read-only']
        self._append_log(f'[{now_text()}] 读取已完成反演快照；当前参数不参与绘图。')
        self._start_view_worker(html_path, args, 'features')

    def _start_view_worker(self, html_path, args, kind):
        self._view_kind = kind
        self._feature_preview_path = html_path
        self._feature_preview_identity = self._echo_identity()
        self._feature_preview_cancelled = False
        self._feature_preview_buffer = ""
        self._feature_preview_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._feature_preview_errors = []
        process = QProcess(self)
        self.feature_preview_process = process
        process.setWorkingDirectory(str(storage.ROOT))
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUNBUFFERED", "1")
        process.setProcessEnvironment(env)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_feature_preview_output)
        process.finished.connect(self._feature_preview_finished)
        process.errorOccurred.connect(self._feature_preview_error)
        self.run_btn.setEnabled(False)
        self.run_all_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress.setValue(0)
        self.progress.setFormat('准备图像：可中止')
        self._sync_echo_artifact_buttons()
        self._append_log(f'[{now_text()}] 后台生成图像（{kind}）；可用「中止」取消。')
        python_exe = self.python_edit.text().strip() or sys.executable
        process.start(python_exe, args)

    def _read_feature_preview_output(self) -> None:
        process = self.feature_preview_process
        if process is None:
            return
        self._feature_preview_buffer += self._feature_preview_decoder.decode(bytes(process.readAllStandardOutput()))
        while "\n" in self._feature_preview_buffer:
            line, self._feature_preview_buffer = self._feature_preview_buffer.split("\n", 1)
            line = line.strip()
            if line.startswith(PROGRESS_PREFIX):
                self._handle_output_line(line)
            elif line:
                self._feature_preview_errors.append(line)

    def _feature_preview_error(self, error) -> None:
        process = self.feature_preview_process
        if process is not None and error == QProcess.ProcessError.FailedToStart:
            self._feature_preview_errors.append(process.errorString())
            self._feature_preview_finished(-1)

    def _feature_preview_finished(self, exit_code, *_args) -> None:
        process = self.feature_preview_process
        if process is None:
            return
        self._read_feature_preview_output()
        self._feature_preview_buffer += self._feature_preview_decoder.decode(b"", final=True)
        if self._feature_preview_buffer.strip():
            self._feature_preview_errors.append(self._feature_preview_buffer.strip())
        self.feature_preview_process = None
        process.deleteLater()
        self._reset_run_buttons()
        path = self._feature_preview_path
        try:
            path.with_suffix(".html.part").unlink(missing_ok=True)
        except OSError:
            pass
        label = '特征图' if getattr(self, '_view_kind', 'features') == 'features' else '图像'
        if self._feature_preview_cancelled:
            self.progress.setFormat(f"{label}生成已中止")
            self._append_log(f"[{now_text()}] {label}生成已中止。")
        elif exit_code == 0 and path.is_file():
            from .inversion_feature_preview import open_echo_preview_in_browser
            self.progress.setValue(100)
            self.progress.setFormat(f"{label}已生成")
            self._append_log(f"[{now_text()}] {label}已打开：{path}", level="success")
            open_echo_preview_in_browser(path)
            if self._feature_preview_identity is not None:
                self._opened_previews['features' if getattr(self, '_view_kind', 'features') == 'features' else 'echo'].add(self._feature_preview_identity)
        else:
            message = "\n".join(self._feature_preview_errors) or f"退出码 {exit_code}，未生成{label}"
            self.progress.setFormat(f"{label}生成失败")
            self._append_log(f"[{now_text()}] {label}生成失败：{message}", level="error")
            QMessageBox.critical(self, label, message)
        self._sync_echo_artifact_buttons()
