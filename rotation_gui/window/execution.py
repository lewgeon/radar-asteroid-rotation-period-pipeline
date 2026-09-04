from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pipeline

from .. import storage
from ..qt_compat import NOT_RUNNING, QMessageBox, QProcess, QProcessEnvironment, QTimer
from ..schema import ERROR_PREFIX, PROGRESS_PREFIX, STAGES, WARNING_PREFIX
from ..storage import now_text, write_json


class ExecutionMixin:
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
        if stage == "observation" and self.reuse_observation_info:
            self._complete_reused_observation()
            return
        run_name = self.run_name_edit.text().strip() or self.config_path.stem
        runs_dir = self.runs_dir_edit.text().strip() or "runs"
        python_exe = self.python_edit.text().strip() or sys.executable
        run_dir = pipeline.abs_path(runs_dir) / run_name
        config_dir = run_dir / "configs"
        prepared = pipeline.prepared_configs(self.config_data, run_dir)
        if self.reuse_observation_info and self.reuse_observation_path:
            source = Path(self.reuse_observation_path).expanduser().resolve()
            try:
                self._validate_observation_info(source)
            except Exception as exc:
                QMessageBox.critical(self, self._tr("无法复用", "Cannot Reuse"), str(exc))
                return
            prepared["echo"]["observation_info_path"] = str(source)
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

    def _complete_reused_observation(self) -> None:
        source = Path(self.reuse_observation_path).expanduser()
        if not source.is_absolute():
            source = storage.ROOT / source
        try:
            self._validate_observation_info(source)
        except Exception as exc:
            QMessageBox.critical(self, self._tr("无法复用", "Cannot Reuse"), str(exc))
            return
        self.reuse_observation_path = str(source.resolve())
        self.latest_observation_path = source.resolve()
        self.stage_status["observation"] = "完成"
        self._append_history("observation", "复用", str(source), "")
        self._append_log(f"[{now_text()}] 已复用视线向量：{source}")
        self._set_progress("observation", 100, self._tr("已复用已有结果", "Reused existing result"))
        self.current_stage = "echo"
        self.status_label.setText(self._tr("视线向量已载入，已切换到回波仿真。", "Vectors loaded; switched to echo simulation."))
        self._save_state()
        self._render_stage_buttons()
        self._render_current_stage()
        self._render_history()

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
            storage.ROOT / "inversion",
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
