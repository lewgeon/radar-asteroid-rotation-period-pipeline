from __future__ import annotations

from pathlib import Path

from .. import qt_compat, storage
from ..qt_compat import QHBoxLayout, QLabel, QPushButton, QUrl, QVBoxLayout, QWidget
from ..schema import STAGES
from ..storage import now_text
from ..widgets import ImagePreview


class PreviewMixin:
    def _update_result_preview(self, stage: str, run_dir: Path) -> None:
        try:
            image_path, result_path, plotly_path, message = self._create_stage_preview(stage, run_dir)
        except Exception as exc:
            self.latest_image_path = None
            self.latest_result_path = run_dir
            self.latest_plotly_path = None
            self.stage_preview_records[stage] = {
                "image_path": None,
                "result_path": run_dir,
                "plotly_path": None,
                "message": f"结果预览生成失败：{exc}",
            }
            self._refresh_result_tabs(stage)
            self._set_preview_sidebar_visible(True)
            self._append_warning(f"[{now_text()}] 结果预览生成失败：{exc}")
            return
        self.latest_image_path = image_path
        self.latest_result_path = result_path
        if stage == "observation":
            self.latest_observation_path = Path(result_path)
        self.latest_plotly_path = plotly_path
        self.stage_preview_records[stage] = {
            "image_path": image_path,
            "result_path": result_path,
            "plotly_path": plotly_path,
            "message": message,
        }
        self._refresh_result_tabs(stage)
        self._set_preview_sidebar_visible(True)

    def _refresh_result_tabs(self, active_stage: str | None = None) -> None:
        # 仅摘除标签页，保留已构建的页面（尤其是 qt_compat.QWebEngineView）。反复
        # setParent(None)/deleteLater 会销毁并重建 WebEngine 原生窗口，是
        # “阶段完成后界面闪一下”的来源。
        while self.result_tabs.count():
            self.result_tabs.removeTab(0)
        ordered = [stage for stage in STAGES if stage in self.stage_preview_records]
        has_records = bool(ordered)
        self.result_tabs.setVisible(has_records)
        self.empty_preview_label.setVisible(not has_records)
        if not has_records:
            return
        active_index = 0
        for stage in ordered:
            record = self.stage_preview_records[stage]
            page = record.get("page")
            if page is None:
                page = self._create_preview_page(
                    record.get("image_path"),
                    record.get("result_path"),
                    record.get("plotly_path"),
                    str(record.get("message") or ""),
                )
                record["page"] = page
            index = self.result_tabs.addTab(page, self._stage_label(stage))
            if stage == active_stage:
                active_index = index
        self.result_tabs.setCurrentIndex(active_index)

    def _create_preview_page(
        self,
        image_path: Path | str | None,
        result_path: Path | str | None,
        plotly_path: Path | str | None,
        message: str,
    ) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        status = QLabel(message or self._tr("结果已生成。", "Result generated."))
        status.setWordWrap(True)
        open_result_btn = QPushButton(self._tr("打开结果", "Open Result"))
        open_plotly_btn = QPushButton(self._tr("打开交互图", "Open Interactive"))
        result = Path(result_path) if result_path else None
        plotly = Path(plotly_path) if plotly_path else None
        open_result_btn.setEnabled(bool(result and result.exists()))
        open_plotly_btn.setEnabled(bool(plotly and plotly.exists()))
        open_result_btn.clicked.connect(lambda _checked=False, path=result: self._open_path(path))
        open_plotly_btn.clicked.connect(lambda _checked=False, path=plotly: self._open_plotly_path(path))
        head = QHBoxLayout()
        head.addWidget(status, 1)
        head.addWidget(open_result_btn)
        head.addWidget(open_plotly_btn)
        layout.addLayout(head)
        image_preview = ImagePreview()
        web_preview = qt_compat.QWebEngineView() if qt_compat.QWebEngineView else None
        self._show_stage_preview(image_preview, web_preview, Path(image_path) if image_path else None, plotly, message)
        if web_preview and web_preview.isVisible():
            layout.addWidget(web_preview, 1)
        else:
            if web_preview:
                web_preview.deleteLater()
            layout.addWidget(image_preview, 1)
        return page

    def _show_stage_preview(
        self,
        preview: ImagePreview,
        web_preview,
        image_path: Path | None,
        plotly_path: Path | None,
        message: str,
    ) -> None:
        if web_preview and plotly_path and plotly_path.exists():
            preview.hide()
            web_preview.show()
            web_preview.load(QUrl.fromLocalFile(str(plotly_path.resolve())))
            return
        if web_preview:
            web_preview.hide()
        preview.show()
        preview.set_image(image_path, message)

    def _create_stage_preview(self, stage: str, run_dir: Path):
        storage.PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        preview_dir = storage.PREVIEW_DIR / run_dir.name.replace(" ", "_")
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
