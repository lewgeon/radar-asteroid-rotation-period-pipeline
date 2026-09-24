"""回波预览必须同时给出原始二维图、压缩二维距离像和一维距离像。

运行方式（需要 pytorch 环境中的 PySide6 与 plotly）：

    E:\\anaconda3\\envs\\pytorch\\python.exe -m pytest tests/test_echo_preview_panels.py -q
"""

import json
import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pytest

plotly = pytest.importorskip("plotly")

from rotation_gui.window.echo_preview import (  # noqa: E402
    build_echo_preview_figure,
    build_echo_preview_html,
)

_WORKSPACE_ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def _workspace_tmp(prefix: str):
    """A writable scratch directory under the workspace root.

    ``tmp_path`` points outside the workspace and is not writable by the
    sandbox, so allocate a deterministic name with ``Path.mkdir`` instead.
    """

    name = f".tmp_{prefix}_{os.getpid()}_{int(time.time() * 1000)}"
    path = _WORKSPACE_ROOT / name
    path.mkdir(parents=False, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _chirp_row(fast_time_s, leading_edge_s, pulse_width_s, bandwidth_hz):
    local = fast_time_s - leading_edge_s
    inside = (local >= 0.0) & (local < pulse_width_s)
    slope = bandwidth_hz / pulse_width_s
    return np.where(inside, np.exp(1j * np.pi * slope * (local - 0.5 * pulse_width_s) ** 2), 0.0)


def _write_chirp_npz(path, *, leading_edge_s=0.0008, pulse_count=6):
    sample_rate_hz = 5000.0
    fast_time_s = np.arange(60, dtype=float) / sample_rate_hz
    reference = _chirp_row(fast_time_s, leading_edge_s, 0.01, 1000.0)
    amplitude = np.linspace(1.0, 0.4, pulse_count)[:, None]
    iq = amplitude * reference[None, :]
    metadata = {
        "waveform_type": "chirp_pulse_train",
        "pulse_width_s": 0.01,
        "pulse_bandwidth_hz": 1000.0,
        "baseband_convention": "centered",
        "fast_sample_rate_hz": sample_rate_hz,
        "echo_output_reference": "centroid_compensated",
    }
    np.savez(
        path,
        iq=iq.astype(np.complex64),
        elapsed_s=np.arange(pulse_count, dtype=float) * 0.05,
        fast_time_s=fast_time_s,
        row_fast_time_offset_s=np.full(pulse_count, -leading_edge_s),
        row_start_sample=np.zeros(pulse_count, dtype=np.int64),
        rx_adc_start_elapsed_s=np.zeros(pulse_count, dtype=float),
        metadata_json=json.dumps(metadata),
    )
    return iq, fast_time_s


def test_chirp_preview_has_raw_and_compressed_2d_panels():
    with _workspace_tmp("echo_preview") as scratch:
        echo_npz = scratch / "echo.npz"
        iq, fast_time_s = _write_chirp_npz(echo_npz)

        figure = build_echo_preview_figure(echo_npz)

        assert [trace.type for trace in figure.data] == ["heatmap", "heatmap", "scatter"]
        raw, compressed, profile = figure.data
        assert np.asarray(raw.z).shape == iq.shape
        assert np.asarray(compressed.z).shape == iq.shape
        # 两幅二维图必须落在同一批快时间样点和同一批脉冲上，才能逐列比较
        assert np.allclose(raw.x, compressed.x)
        assert np.allclose(raw.y, compressed.y)

        # 原始行的第一个非零样点就是回波前沿所在样点
        leading_index = int(np.flatnonzero(fast_time_s >= 0.0008)[0])
        assert int(np.flatnonzero(np.abs(iq[0]) > 0)[0]) == leading_index
        # 压缩后的距离像峰值落在同一列，且峰值远高于未压缩幅度
        assert int(np.argmax(np.asarray(compressed.z).max(axis=0))) == leading_index
        assert float(np.max(compressed.z)) > float(np.max(raw.z)) * 10
        # 一维距离像与二维图共用同一条快时间轴
        assert np.allclose(profile.x, fast_time_s)
        assert int(np.argmax(np.asarray(profile.y))) == leading_index

        offsets = {round(float(shape.x0), 12) for shape in figure.layout.shapes}
        assert offsets == {round(0.0008, 12)}


def test_chirp_preview_html_written():
    with _workspace_tmp("echo_preview") as scratch:
        echo_npz = scratch / "echo.npz"
        _write_chirp_npz(echo_npz)
        html_path = scratch / "echo_preview.html"

        written = build_echo_preview_html(echo_npz, html_path)

        text = written.read_text(encoding="utf-8")
        assert "after pulse compression" in text
        assert "Matched-filter range profile (mean)" in text


def test_cw_preview_keeps_four_one_dimensional_panels():
    with _workspace_tmp("echo_preview") as scratch:
        echo_npz = scratch / "echo_cw.npz"
        elapsed = np.arange(500, dtype=float) / 100.0
        iq = np.exp(2j * np.pi * 3.0 * elapsed).astype(np.complex64)
        np.savez(
            echo_npz,
            iq=iq,
            elapsed_s=elapsed,
            metadata_json=json.dumps({"waveform_type": "continuous_wave"}),
        )

        figure = build_echo_preview_figure(echo_npz)

        assert [trace.type for trace in figure.data] == ["scatter"] * 4
