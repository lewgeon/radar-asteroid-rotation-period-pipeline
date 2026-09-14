"""Staged pipeline GUI: observation → echo → inversion, non-overlapping parameters."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pipeline

from .. import storage
from ..qt_compat import (
    HORIZONTAL,
    VERTICAL,
    QDesktopServices,
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
    QMessageBox,
    QProcess,
    QProcessEnvironment,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    NOT_RUNNING,
    Qt,
)
from ..schema import OPTION_LABELS, STAGE_LABELS, STAGES
from ..storage import now_text, read_json, write_json
from ..styling import GUI_STYLE
from .parameter_form import ParameterForm


class PipelineWindow(QMainWindow):
    """Three-stage parameter ownership with one executable stage at a time."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("自转周期测量流水线")
        self.resize(1440, 900)
        self.setMinimumSize(1100, 720)
        self.setStyleSheet(GUI_STYLE)

        self.config_path = storage.DEFAULT_CONFIG_PATH
        self.config_data = self._load_config(self.config_path)
        self.current_stage = "observation"
        self.monostatic_observation = self._is_monostatic_observation()
        self._bistatic_receiver_backup = None
        self.echo_preview_html = None
        self.stage_status = {stage: "未运行" for stage in STAGES}
        self.process: QProcess | None = None
        self.process_stage: str | None = None
        self.process_output_buffer = ""
        self.process_run_dir: Path | None = None

        self._build_ui()
        self._render_stage()
        self._append_log(f"[{now_text()}] 已载入配置：{self.config_path}")

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
        self.config_path_edit = QLineEdit(str(self.config_path))
        self.browse_btn = QPushButton("打开")
        self.load_btn = QPushButton("载入")
        self.save_btn = QPushButton("保存")
        self.save_as_btn = QPushButton("另存为")
        self.validate_btn = QPushButton("校验")
        config_row.addWidget(QLabel("配置文件"))
        config_row.addWidget(self.config_path_edit, 1)
        for button in (
            self.browse_btn,
            self.load_btn,
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
        self.runs_dir_edit = QLineEdit("runs")
        self.python_edit = QLineEdit(sys.executable)
        self.run_btn = QPushButton("运行当前阶段")
        self.run_btn.setObjectName("runButton")
        self.run_all_btn = QPushButton("运行完整 pipeline")
        self.stop_btn = QPushButton("中止")
        self.stop_btn.setEnabled(False)
        self.preview_btn = QPushButton("查看回波")
        self.preview_btn.setObjectName("previewButton")
        self.preview_btn.setEnabled(False)
        self.preview_btn.setProperty("previewReady", False)
        self.preview_btn.setToolTip("回波仿真完成后可查看交互预览")
        run_row.addWidget(QLabel("实验名"))
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
        for button in (self.run_btn, self.run_all_btn, self.stop_btn, self.preview_btn):
            action_row.addWidget(button)
        toolbar_layout.addLayout(action_row)
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

        log_group = QGroupBox("执行日志")
        self.log_group = log_group
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(10, 12, 10, 10)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(120)
        log_layout.addWidget(self.log)
        work_splitter.addWidget(log_group)
        work_splitter.setSizes((590, 230))
        work_splitter.setStretchFactor(0, 3)
        work_splitter.setStretchFactor(1, 1)

        main_splitter.addWidget(work_column)
        main_splitter.setSizes((220, 1100))
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)

        self.browse_btn.clicked.connect(self._choose_config)
        self.load_btn.clicked.connect(self._load_config_from_entry)
        self.save_btn.clicked.connect(self._save_config)
        self.save_as_btn.clicked.connect(self._save_config_as)
        self.validate_btn.clicked.connect(self._validate_config)
        self.run_btn.clicked.connect(self._run_current_stage)
        self.run_all_btn.clicked.connect(self._run_full_pipeline)
        self.stop_btn.clicked.connect(self._stop_pipeline)
        self.preview_btn.clicked.connect(self._open_echo_preview)
        self.waveform_combo.currentIndexChanged.connect(self._on_waveform_combo_changed)
        self.scattering_model_combo.currentIndexChanged.connect(
            self._on_scattering_model_combo_changed
        )

    def _sync_mode_combos(self) -> None:
        waveform = str(
            ((self.config_data.get("observation") or {}).get("waveform") or {}).get(
                "type", "continuous_wave"
            )
        )
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
        return pipeline.canonical_pipeline_config(read_json(path, {}))

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
        self.config_path_edit.deselect()

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
        self.config_path_edit.deselect()

    def _refresh_stage_chrome(self) -> None:
        for stage, button in self.stage_buttons.items():
            button.setProperty("activeStage", stage == self.current_stage)
            button.style().unpolish(button)
            button.style().polish(button)
            self.stage_status_labels[stage].setText(f"状态：{self.stage_status[stage]}")
        title = STAGE_LABELS[self.current_stage]
        self.scattering_model_control.setVisible(self.current_stage == "echo")
        self.monostatic_checkbox.setVisible(self.current_stage == "observation")
        self.monostatic_checkbox.blockSignals(True)
        self.monostatic_checkbox.setChecked(self.monostatic_observation)
        self.monostatic_checkbox.blockSignals(False)
        self._sync_mode_combos()
        self.run_btn.setText(f"运行：{title.split('. ')[-1]}")
        self.config_path_edit.deselect()

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
            self.config_path_edit.setText(filename)
            self._load_config_from_entry()

    def _load_config_from_entry(self) -> None:
        try:
            path = Path(self.config_path_edit.text()).expanduser()
            if not path.is_absolute():
                path = storage.ROOT / path
            self.config_path = path.resolve()
            self.config_data = self._load_config(self.config_path)
            self.monostatic_observation = self._is_monostatic_observation()
            self.run_name_edit.setText(self.config_path.stem)
            self.stage_status = {stage: "未运行" for stage in STAGES}
            self._render_stage()
            self._append_log(f"[{now_text()}] 已载入配置：{self.config_path}")
        except Exception as exc:
            QMessageBox.critical(self, "载入失败", str(exc))

    def _validate_config(self) -> bool:
        try:
            self._sync_current_stage()
            validated = pipeline.canonical_pipeline_config(self.config_data)
            self.config_data.clear()
            self.config_data.update(validated)
            pipeline.prepared_configs(
                self.config_data, pipeline.abs_path(self.runs_dir_edit.text() or "runs") / "validation"
            )
        except Exception as exc:
            QMessageBox.critical(self, "配置错误", str(exc))
            return False
        self._append_log(f"[{now_text()}] 配置校验通过。")
        self.progress.setFormat("配置校验通过")
        return True

    def _save_config(self) -> None:
        try:
            self._sync_current_stage()
            write_json(self.config_path, self.config_data)
            self._append_log(f"[{now_text()}] 已保存：{self.config_path}")
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))

    def _save_config_as(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "另存 pipeline JSON", str(self.config_path), "JSON files (*.json);;All files (*)"
        )
        if not filename:
            return
        self.config_path = Path(filename).resolve()
        self.config_path_edit.setText(str(self.config_path))
        self._save_config()

    def _run_directory(self) -> Path:
        run_name = self.run_name_edit.text().strip() or self.config_path.stem
        runs_dir = self.runs_dir_edit.text().strip() or "runs"
        return pipeline.abs_path(runs_dir) / run_name

    def _run_current_stage(self) -> None:
        self._start_stages([self.current_stage])

    def _run_full_pipeline(self) -> None:
        self._start_stages(list(STAGES))

    def _start_stages(self, stages: list[str]) -> None:
        if self.process and self.process.state() != NOT_RUNNING:
            QMessageBox.information(self, "正在运行", "当前已有任务在运行。")
            return
        if not self._validate_config():
            return
        self._pending_stages = list(stages)
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
            prepared = pipeline.prepared_configs(self.config_data, run_dir)
            write_json(config_dir / "experiment.json", self.config_data)
            write_json(config_dir / "observation.generated.json", prepared["observation"])
            write_json(config_dir / "echo.generated.json", prepared["echo"])
            write_json(config_dir / "inversion.generated.json", prepared["inversion"])
            write_json(run_dir / "manifest.json", pipeline.build_manifest(self.config_data))
            python_exe = self.python_edit.text().strip() or sys.executable
            command, cwd, env = self._stage_command(stage, python_exe, config_dir, prepared)
        except Exception as exc:
            QMessageBox.critical(self, "启动失败", str(exc))
            self._pending_stages = []
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
        self.process.readyReadStandardOutput.connect(self._read_process_output)
        self.process.readyReadStandardError.connect(self._read_process_output)
        self.process.finished.connect(self._process_finished)
        self.process.errorOccurred.connect(self._process_error)
        self.run_btn.setEnabled(False)
        self.run_all_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.stage_status[stage] = "执行中"
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

    def _render_stage_status_only(self) -> None:
        for stage, label in self.stage_status_labels.items():
            label.setText(f"状态：{self.stage_status[stage]}")

    def _stop_pipeline(self) -> None:
        self._pending_stages = []
        if self.process and self.process.state() != NOT_RUNNING:
            self.process.kill()
            self._append_log(f"[{now_text()}] 已请求中止。")

    def _read_process_output(self) -> None:
        if not self.process:
            return
        text = (
            bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
            + bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        )
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

    def _handle_output_line(self, line: str) -> None:
        if line.startswith("__PROGRESS__ "):
            try:
                payload = json.loads(line[len("__PROGRESS__ ") :])
                percent = int(payload.get("percent", 0))
                message = str(payload.get("message", ""))
                stage = str(payload.get("stage", self.process_stage or "pipeline"))
                self.progress.setValue(max(0, min(100, percent)))
                self.progress.setFormat(f"{percent}%  {message}")
                return
            except Exception:
                pass
        self._append_log(line)

    def _process_error(self, _error) -> None:
        if self.process:
            self._append_log(self.process.errorString())

    def _process_finished(self, exit_code: int, *_args) -> None:
        if self.process_output_buffer:
            self._handle_output_line(self.process_output_buffer)
            self.process_output_buffer = ""
        stage = self.process_stage
        self.process = None
        self.process_stage = None
        if exit_code == 0:
            if stage:
                self.stage_status[stage] = "完成"
            self.progress.setValue(100)
            self.progress.setFormat("完成")
            self._append_log(f"[{now_text()}] {STAGE_LABELS.get(stage, stage)} 完成。")
            self._render_stage_status_only()
            if stage == "echo" and self.process_run_dir is not None:
                self._prepare_echo_preview(self.process_run_dir)
            self._run_next_pending_stage()
            return
        if stage:
            self.stage_status[stage] = "失败"
        self._pending_stages = []
        self.run_btn.setEnabled(True)
        self.run_all_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress.setFormat(f"失败：退出码 {exit_code}")
        self._append_log(f"[{now_text()}] 失败，退出码 {exit_code}。")
        self._render_stage_status_only()
        QMessageBox.critical(self, "运行失败", f"阶段失败，退出码 {exit_code}")

    def _append_log(self, text: str) -> None:
        self.log.append(text)

    def _set_preview_ready(self, ready: bool) -> None:
        self.preview_btn.setEnabled(bool(ready))
        self.preview_btn.setProperty("previewReady", bool(ready))
        self.preview_btn.style().unpolish(self.preview_btn)
        self.preview_btn.style().polish(self.preview_btn)
        if ready:
            self.preview_btn.setToolTip("回波已生成，点击打开 Plotly 交互预览")
        else:
            self.preview_btn.setToolTip("回波仿真完成后可查看交互预览")

    def _prepare_echo_preview(self, run_dir: Path) -> None:
        echo_npz = run_dir / "echo" / "echo.npz"
        if not echo_npz.exists():
            self._set_preview_ready(False)
            self._append_log(f"[{now_text()}] 未找到回波文件，无法生成预览：{echo_npz}")
            return
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
        if not self.echo_preview_html or not Path(self.echo_preview_html).exists():
            # Try rebuild from current run directory.
            run_dir = self._run_directory()
            echo_npz = run_dir / "echo" / "echo.npz"
            if echo_npz.exists():
                self._prepare_echo_preview(run_dir)
        if not self.echo_preview_html or not Path(self.echo_preview_html).exists():
            QMessageBox.information(self, "回波预览", "尚无可用回波预览，请先成功运行回波仿真。")
            return
        from .echo_preview import open_echo_preview_in_browser

        open_echo_preview_in_browser(Path(self.echo_preview_html))
