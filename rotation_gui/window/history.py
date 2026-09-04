from __future__ import annotations

import html
import webbrowser
from pathlib import Path

from .. import storage
from ..qt_compat import NOT_RUNNING, QDesktopServices, QTableWidgetItem, QUrl
from ..schema import STAGES
from ..storage import now_text, read_json, write_json


class HistoryMixin:
    def _render_history(self) -> None:
        history = read_json(storage.HISTORY_PATH, [])
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
        history = read_json(storage.HISTORY_PATH, [])
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
        write_json(storage.HISTORY_PATH, history[-300:])

    def _append_log(self, text: str) -> None:
        lines = str(text).splitlines()
        if not lines:
            self.log_edit.append("")
            return
        for line in lines:
            self.log_edit.append(self._format_log_line(line))

    def _append_warning(self, text: str) -> None:
        self.log_edit.append(self._log_badge_line("WARN", text, "#b45309", "#fff7ed", "#fed7aa"))

    def _append_error(self, text: str) -> None:
        self.log_edit.append(self._log_badge_line("ERROR", text, "#b91c1c", "#fef2f2", "#fecaca"))

    def _format_log_line(self, line: str) -> str:
        stripped = line.strip()
        escaped = html.escape(line)
        if not stripped:
            return ""
        if "开始执行" in stripped:
            return self._log_badge_line("RUN", stripped, "#215b99", "#eff6ff", "#bfdbfe")
        if "完成" in stripped or "已保存" in stripped or "已载入" in stripped or "已复用" in stripped:
            return self._log_badge_line("OK", stripped, "#166534", "#f0fdf4", "#bbf7d0")
        if stripped.startswith(("命令：", "工作目录：", "完整原始输出日志：", "生成配置：")):
            return self._log_badge_line("INFO", stripped, "#35506c", "#f8fafc", "#dce2eb")
        if stripped.startswith(("experiment:", "observation:", "echo:", "inversion:")):
            return (
                '<span style="font-family:Consolas,monospace;color:#486785;'
                f'background:#f8fafc;">  {escaped}</span>'
            )
        if "warning" in stripped.lower() or "警告" in stripped:
            return self._log_badge_line("WARN", stripped, "#b45309", "#fff7ed", "#fed7aa")
        return f'<span style="color:#25354a;">{escaped}</span>'

    def _log_badge_line(self, badge: str, text: str, color: str, background: str, border: str) -> str:
        return (
            f'<span style="background:{background};border:1px solid {border};border-radius:4px;'
            f'padding:2px 6px;color:{color};font-family:Consolas,monospace;font-weight:700;">'
            f'{badge}</span>'
            f' <span style="color:{color};font-weight:600;">{html.escape(str(text))}</span>'
        )

    def _open_latest_result(self) -> None:
        if self.latest_result_path and self.latest_result_path.exists():
            self._open_path(self.latest_result_path)

    def _open_plotly(self) -> None:
        if self.latest_plotly_path and self.latest_plotly_path.exists():
            self._open_plotly_path(self.latest_plotly_path)

    def _open_path(self, path: Path | None) -> None:
        if path and path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def _open_plotly_path(self, path: Path | None) -> None:
        if path and path.exists():
            webbrowser.open(path.resolve().as_uri())

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
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
            if child_layout:
                HistoryMixin._clear_layout(child_layout)

    @staticmethod
    def _next_stage(stage: str) -> str | None:
        index = STAGES.index(stage)
        if index + 1 >= len(STAGES):
            return None
        return STAGES[index + 1]
