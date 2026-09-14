"""Plotly echo preview generation; the GUI opens the HTML in the system browser."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import storage
from ..qt_compat import QDesktopServices, QUrl


def echo_preview_html_path(run_dir: Path) -> Path:
    preview_dir = storage.PREVIEW_DIR / run_dir.name.replace(" ", "_")
    preview_dir.mkdir(parents=True, exist_ok=True)
    return preview_dir / "echo_preview.html"


def build_echo_preview_html(echo_npz: Path, html_path: Path) -> Path:
    """Create an interactive Plotly HTML preview from echo.npz."""

    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    data = np.load(echo_npz, allow_pickle=False)
    iq = np.asarray(data["iq"])
    elapsed = np.asarray(data["elapsed_s"], dtype=float)
    metadata = {}
    if "metadata_json" in data.files:
        import json

        metadata = json.loads(str(data["metadata_json"]))

    html_path.parent.mkdir(parents=True, exist_ok=True)
    if iq.ndim == 1:
        _write_cw_preview(go, make_subplots, elapsed, iq, html_path, metadata)
    elif iq.ndim == 2:
        fast_time = np.asarray(data["fast_time_s"], dtype=float) if "fast_time_s" in data.files else None
        _write_chirp_preview(go, make_subplots, elapsed, iq, fast_time, html_path, metadata, data)
    else:
        raise ValueError(f"不支持的 iq 维度：{iq.ndim}")
    return html_path


def _write_cw_preview(go, make_subplots, elapsed, iq, html_path, metadata):
    stride = max(1, len(elapsed) // 8000)
    t = elapsed[::stride]
    z = iq[::stride]
    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=(
            "实部 I  (= Re{iq})",
            "虚部 Q  (= Im{iq})",
            "幅度 |iq|",
            "解缠相位",
        ),
    )
    fig.add_trace(
        go.Scatter(x=t, y=z.real, mode="lines", name="实部 I"),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=t, y=z.imag, mode="lines", name="虚部 Q"),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=t, y=np.abs(z), mode="lines", name="|iq|"),
        row=3,
        col=1,
    )
    fig.add_trace(
        go.Scatter(x=t, y=np.unwrap(np.angle(z)), mode="lines", name="phase"),
        row=4,
        col=1,
    )
    title = "回波预览（连续波）"
    if metadata.get("scattering_model") == "point_target":
        title += " · 点目标"
    ref = metadata.get("echo_output_reference")
    if ref:
        title += f" · {ref}"
    fig.update_yaxes(title_text="Re", row=1, col=1)
    fig.update_yaxes(title_text="Im", row=2, col=1)
    fig.update_yaxes(title_text="|iq|", row=3, col=1)
    fig.update_yaxes(title_text="rad", row=4, col=1)
    fig.update_xaxes(title_text="Elapsed (s)", row=4, col=1)
    fig.update_layout(
        height=900,
        title=title,
        margin={"l": 55, "r": 20, "t": 60, "b": 40},
        legend={"orientation": "h", "y": 1.02, "x": 1, "xanchor": "right"},
    )
    fig.write_html(str(html_path), include_plotlyjs=True)


def _write_chirp_preview(go, make_subplots, elapsed, iq, fast_time, html_path, metadata, data):
    amplitude = np.abs(iq)
    pulse_axis = np.arange(iq.shape[0])
    if fast_time is None or len(fast_time) != iq.shape[1]:
        fast_time = np.arange(iq.shape[1], dtype=float)

    # Downsample for browser responsiveness.
    pulse_step = max(1, iq.shape[0] // 400)
    fast_step = max(1, iq.shape[1] // 500)
    amp_view = amplitude[::pulse_step, ::fast_step]
    fig = make_subplots(
        rows=2,
        cols=1,
        vertical_spacing=0.12,
        subplot_titles=("Pulse × fast-time amplitude", "Matched-filter range profile (mean)"),
        row_heights=[0.62, 0.38],
    )
    fig.add_trace(
        go.Heatmap(
            z=amp_view,
            x=fast_time[::fast_step],
            y=pulse_axis[::pulse_step],
            colorbar={"title": "|iq|"},
            name="amplitude",
        ),
        row=1,
        col=1,
    )

    try:
        root = Path(__file__).resolve().parents[2]
        inversion_src = root / "inversion" / "src"
        import sys

        if str(inversion_src) not in sys.path:
            sys.path.insert(0, str(inversion_src))
        from radar_signal import matched_filter_chirp

        width = float(metadata.get("pulse_width_s") or 0.0)
        bandwidth = float(metadata.get("pulse_bandwidth_hz") or 0.0)
        convention = str(metadata.get("baseband_convention", "zero_to_bandwidth"))
        if width > 0 and abs(bandwidth) > 0:
            compressed = matched_filter_chirp(
                iq,
                fast_time,
                width,
                bandwidth,
                baseband_convention=convention,
            )
            profile = np.mean(np.abs(compressed), axis=0)
            fig.add_trace(
                go.Scatter(x=fast_time, y=profile, mode="lines", name="|MF| mean"),
                row=2,
                col=1,
            )
            if metadata.get("scattering_model") == "point_target":
                tx = np.asarray(data["tx_range_m"], dtype=float) if "tx_range_m" in data.files else None
                rx = np.asarray(data["rx_range_m"], dtype=float) if "rx_range_m" in data.files else None
                if metadata.get("echo_output_reference") == "centroid_compensated":
                    expected_s = 0.0
                elif tx is not None and rx is not None and len(tx):
                    expected_s = float(np.mean(tx + rx) / 299_792_458.0)
                else:
                    expected_s = None
                if expected_s is not None:
                    fig.add_vline(
                        x=expected_s,
                        line_dash="dash",
                        line_color="#c2410c",
                        annotation_text="expected delay",
                        row=2,
                        col=1,
                    )
    except Exception as exc:
        fig.add_annotation(
            text=f"Matched filter unavailable: {exc}",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.12,
            showarrow=False,
        )

    title = "Echo preview (chirp)"
    if metadata.get("scattering_model") == "point_target":
        title += " · point target"
    fig.update_xaxes(title_text="Fast time (s)", row=1, col=1)
    fig.update_yaxes(title_text="Pulse", row=1, col=1)
    fig.update_xaxes(title_text="Fast time / delay (s)", row=2, col=1)
    fig.update_yaxes(title_text="Amplitude", row=2, col=1)
    fig.update_layout(height=820, title=title, margin={"l": 55, "r": 20, "t": 50, "b": 40})
    fig.write_html(str(html_path), include_plotlyjs=True)


def open_echo_preview_in_browser(html_path: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(html_path).resolve())))
