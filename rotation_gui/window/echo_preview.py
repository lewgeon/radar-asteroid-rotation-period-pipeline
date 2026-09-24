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

    figure = build_echo_preview_figure(echo_npz)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    figure.write_html(str(html_path), include_plotlyjs=True)
    return html_path


def build_echo_preview_figure(echo_npz: Path):
    """Build the Plotly preview figure for one ``echo.npz`` (CW or chirp)."""

    with np.load(echo_npz, allow_pickle=False) as data:
        iq = np.asarray(data["iq"])
        elapsed = np.asarray(data["elapsed_s"], dtype=float)
        metadata = {}
        if "metadata_json" in data.files:
            import json

            metadata = json.loads(str(data["metadata_json"]))
        if iq.ndim == 1:
            return _cw_preview_figure(elapsed, iq, metadata)
        if iq.ndim == 2:
            fast_time = (
                np.asarray(data["fast_time_s"], dtype=float)
                if "fast_time_s" in data.files
                else None
            )
            return _chirp_preview_figure(iq, fast_time, metadata, data)
    raise ValueError(f"不支持的 iq 维度：{iq.ndim}")


def _cw_preview_figure(elapsed, iq, metadata):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

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
    return fig


def _pulse_compressed_amplitude(iq, fast_time, metadata):
    """Return ``(|matched-filter range image|, failure message)``.

    The range image keeps the ``[pulse, fast_time]`` shape of the raw window; its
    fast-time sample index denotes the echo leading edge, not the envelope centre.
    """

    width = float(metadata.get("pulse_width_s") or 0.0)
    bandwidth = float(metadata.get("pulse_bandwidth_hz") or 0.0)
    if width <= 0.0 or abs(bandwidth) <= 0.0:
        return None, "缺少 pulse_width_s / pulse_bandwidth_hz，无法做脉冲压缩"
    convention = str(metadata.get("baseband_convention", "centered"))
    try:
        import sys

        inversion_src = Path(__file__).resolve().parents[2] / "inversion" / "src"
        if str(inversion_src) not in sys.path:
            sys.path.insert(0, str(inversion_src))
        from radar_signal import matched_filter_chirp

        compressed = matched_filter_chirp(
            iq,
            fast_time,
            width,
            abs(bandwidth),
            baseband_convention=convention,
        )
    except Exception as exc:  # pragma: no cover - depends on optional imports
        return None, f"Matched filter unavailable: {exc}"
    return np.abs(compressed), None


def _chirp_preview_figure(iq, fast_time, metadata, data):
    """Build the chirp preview: raw 2D window, compressed 2D range image, 1D profile."""

    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    amplitude = np.abs(iq)
    pulse_axis = np.arange(iq.shape[0])
    if fast_time is None or len(fast_time) != iq.shape[1]:
        fast_time = np.arange(iq.shape[1], dtype=float)

    # Downsample for browser responsiveness.  Both heatmaps use the same pulse and
    # fast-time subset so the raw and compressed images can be compared column by
    # column.
    pulse_step = max(1, iq.shape[0] // 400)
    fast_step = max(1, iq.shape[1] // 500)
    amp_view = amplitude[::pulse_step, ::fast_step]
    fast_view = fast_time[::fast_step]
    pulse_view = pulse_axis[::pulse_step]

    compressed, compression_error = _pulse_compressed_amplitude(iq, fast_time, metadata)

    predicted_centroid_s = _predicted_centroid_row_time_s(data, iq.shape[0])
    expected_s = None
    if predicted_centroid_s is not None:
        finite_centroid_s = predicted_centroid_s[np.isfinite(predicted_centroid_s)]
        if len(finite_centroid_s):
            expected_s = float(np.median(finite_centroid_s))

    fig = make_subplots(
        rows=3,
        cols=1,
        vertical_spacing=0.10,
        subplot_titles=(
            "Pulse × fast-time amplitude (raw, before compression)",
            "Pulse × fast-time amplitude (after pulse compression)",
            "Matched-filter range profile (mean)",
        ),
        row_heights=[0.34, 0.34, 0.32],
    )
    fig.add_trace(
        go.Heatmap(
            z=amp_view,
            x=fast_view,
            y=pulse_view,
            colorbar={"title": "|iq|", "len": 0.27, "y": 0.864},
            name="amplitude",
        ),
        row=1,
        col=1,
    )

    if compressed is None:
        fig.add_annotation(
            text=compression_error or "Matched filter unavailable",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.5,
            showarrow=False,
        )
    else:
        fig.add_trace(
            go.Heatmap(
                z=compressed[::pulse_step, ::fast_step],
                x=fast_view,
                y=pulse_view,
                colorbar={"title": "|MF|", "len": 0.27, "y": 0.492},
                name="compressed amplitude",
            ),
            row=2,
            col=1,
        )
        profile = np.mean(compressed, axis=0)
        fig.add_trace(
            go.Scatter(x=fast_time, y=profile, mode="lines", name="|MF| mean"),
            row=3,
            col=1,
        )
        if expected_s is not None:
            # The same reference line is drawn on the compressed image and on the
            # range profile so a one-sample offset between them stays visible.
            fig.add_vline(
                x=expected_s,
                line_dash="dash",
                line_color="#f59e0b",
                row=2,
                col=1,
            )
            fig.add_vline(
                x=expected_s,
                line_dash="dash",
                line_color="#f59e0b",
                annotation_text="预计质心回波",
                row=3,
                col=1,
            )

    title = "Echo preview (chirp)"
    if metadata.get("scattering_model") == "point_target":
        title += " · point target"
    for row in (1, 2):
        fig.update_xaxes(title_text="脉冲保存行内时间 (s)", row=row, col=1)
        fig.update_yaxes(title_text="Pulse", row=row, col=1)
    fig.update_xaxes(title_text="脉冲保存行内时间 (s)", row=3, col=1)
    fig.update_yaxes(title_text="Amplitude", row=3, col=1)
    fig.update_layout(height=1100, title=title, margin={"l": 55, "r": 20, "t": 50, "b": 40})
    return fig


def _predicted_centroid_row_time_s(data, pulse_count: int):
    """Return each predicted centroid echo's position on the saved-row axis."""

    if "row_fast_time_offset_s" in data.files:
        offsets = np.asarray(data["row_fast_time_offset_s"], dtype=float)
        if offsets.shape == (pulse_count,):
            return -offsets

    required = {
        "elapsed_s",
        "rx_adc_start_elapsed_s",
        "row_start_sample",
    }
    if not required.issubset(data.files):
        return None
    receive = np.asarray(data["elapsed_s"], dtype=float)
    adc_start = np.asarray(data["rx_adc_start_elapsed_s"], dtype=float)
    row_start = np.asarray(data["row_start_sample"], dtype=float)
    if any(value.shape != (pulse_count,) for value in (receive, adc_start, row_start)):
        return None
    metadata = {}
    if "metadata_json" in data.files:
        import json

        metadata = json.loads(str(data["metadata_json"]))
    sample_rate = float(metadata.get("fast_sample_rate_hz") or 0.0)
    if not np.isfinite(sample_rate) or sample_rate <= 0.0:
        return None
    row_start_time = adc_start + row_start / sample_rate
    return receive - row_start_time


def open_echo_preview_in_browser(html_path: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(html_path).resolve())))
