"""Plotly preview of the per-pulse features used by chirp period search."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from .. import storage
from .echo_preview import open_echo_preview_in_browser


def _views():
    source = storage.ROOT / 'inversion' / 'src'
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    import result_views
    return result_views


def feature_cache_key(source, config, *, saved=False, echo_npz=None):
    return _views().feature_view_key(source, config, saved=saved, echo_npz=echo_npz)


def cached_feature_html(source, config, html_path, *, saved=False, echo_npz=None):
    import json
    stamp = html_path.with_suffix('.view.json')
    try:
        return html_path.is_file() and json.loads(stamp.read_text(encoding='utf-8')) == feature_cache_key(source, config, saved=saved, echo_npz=echo_npz)
    except (OSError, ValueError):
        return False


_SERIES = (
    ("total_power", "总能量", "压缩后功率和"),
    ("range_centroid", "距离质心", "s"),
    ("range_energy_width", "距离 90% 能量宽度", "s"),
)

_TIME_LABELS = {
    "scatter_elapsed_s": "散射时刻（相对观测起点，s）",
    "receive_elapsed_s": "接收时刻（相对观测起点，s）",
}

# 只限制单块完整相关的 complex128 输出；FFT、功率和时延轴仍有额外工作区。
# 回波加载和一维输出仍随脉冲数增长，不是整个进程的峰值保证。
_FEATURE_WORKSPACE_BUDGET_BYTES = 32 * 1024 * 1024


def inversion_feature_html_path(run_dir: Path) -> Path:
    preview_dir = storage.PREVIEW_DIR / run_dir.name.replace(" ", "_")
    preview_dir.mkdir(parents=True, exist_ok=True)
    return preview_dir / "inversion_features.html"


def build_inversion_feature_html(echo_npz: Path, config: dict, html_path: Path,
                                 *, progress_callback=None, observables=None) -> Path:
    import json
    source = observables if observables is not None else echo_npz
    saved = observables is not None
    key = feature_cache_key(source, config, saved=saved, echo_npz=echo_npz)
    if cached_feature_html(source, config, html_path, saved=saved, echo_npz=echo_npz):
        if progress_callback:
            progress_callback(100, '复用已生成的特征图')
        return html_path
    if progress_callback:
        progress_callback(0, '读取已保存的反演特征' if saved else '载入回波')
    if saved:
        figure = _views().saved_feature_figure(observables, current_config=config, current_echo_identity=key['echo'])
    else:
        echo = _load_echo(echo_npz)
        try:figure = build_inversion_feature_figure(echo, config, progress_callback=progress_callback)
        finally:echo.close()
    if progress_callback:
        progress_callback(95, "写入特征图")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    # Publish only a complete HTML; cancellation must preserve the previous result.
    pending = html_path.with_suffix(".html.part")
    try:
        def validate():
            if feature_cache_key(source, config, saved=saved, echo_npz=echo_npz) != key:
                raise ValueError('生成特征图期间源文件发生变化，请重新查看')
        _views().write_html_atomic(figure,html_path,validate=validate,standalone=False)
        if feature_cache_key(source, config, saved=saved, echo_npz=echo_npz) != key:
            raise ValueError('生成特征图期间源文件发生变化，请重新查看')
    finally:
        pending.unlink(missing_ok=True)
    html_path.with_suffix('.view.json').write_text(json.dumps(key), encoding='utf-8')
    if progress_callback:
        progress_callback(100, "特征图已生成")
    return html_path


def build_inversion_feature_figure(echo, config: dict, *, progress_callback=None):
    """Scatter the three per-pulse observables against the period-search clock."""

    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    features, time_axis_role, run_id = _pulse_features(echo, config, progress_callback=progress_callback)
    return pulse_feature_figure(features,time_axis_role,run_id)


def pulse_feature_figure(features,time_axis_role,run_id):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    times = np.asarray(features.times_s, dtype=float)
    values = {
        "total_power": np.asarray(features.total_power, dtype=float),
        "range_centroid": np.asarray(features.centroid_delay_s, dtype=float),
        "range_energy_width": np.asarray(features.energy_width_90_s, dtype=float),
    }
    titles = tuple(f"{title}（{unit}）" for _key, title, unit in _SERIES)
    figure = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=titles,
    )
    runs=np.asarray(run_id,dtype=int)
    breaks=np.r_[False,np.diff(runs)!=0]
    # Insert a gap between runs, but retain connected samples inside each run.
    positions=np.arange(len(times))+np.cumsum(breaks)
    shown_times=np.full(len(times)+int(breaks.sum()),np.nan);shown_times[positions]=times
    custom=np.full((len(shown_times),2),np.nan);custom[positions]=np.column_stack((np.arange(len(times)),runs))
    hover = (
        "脉冲 %{customdata[0]}<br>run %{customdata[1]}"
        "<br>时刻 %{x:.6g} s<br>数值 %{y:.6g}<extra></extra>"
    )
    for row, (key, title, _unit) in enumerate(_SERIES, start=1):
        shown_values=np.full(len(shown_times),np.nan);shown_values[positions]=values[key]
        figure.add_trace(
            go.Scatter(
                x=shown_times,
                y=shown_values,
                mode="lines+markers",
                connectgaps=False,
                name=title,
                marker={"size": 6},
                customdata=custom,
                hovertemplate=hover,
            ),
            row=row,
            col=1,
        )
    figure.update_layout(
        title="逐脉冲特征：总能量、距离质心、90% 能量宽度",
        height=860,
        showlegend=False,
        margin={"l": 70, "r": 30, "t": 70, "b": 50},
    )
    figure.update_xaxes(
        title_text=_TIME_LABELS.get(time_axis_role, time_axis_role),
        row=3,
        col=1,
    )
    return figure


def _load_echo(echo_npz: Path):
    inversion_src = storage.ROOT / "inversion" / "src"
    if str(inversion_src) not in sys.path:
        sys.path.insert(0, str(inversion_src))
    from dataset import load_echo

    from processing_store import attach_store,identity
    before=identity(echo_npz)
    echo=attach_store(load_echo(echo_npz,mapped_directory=echo_npz.parent/'processing_cache'/'mapped',load_clean=False),echo_npz)
    if echo._source_identity!=before:raise ValueError('读取期间回波改变，请重新查看')
    return echo


def _pulse_features(echo, config: dict, *, progress_callback=None):
    iq = np.asarray(echo.iq)
    if iq.ndim != 2:
        raise ValueError("这张图只适用于 chirp 脉冲回波；当前文件不是二维脉冲距离像")
    module = _inversion_module()
    # 20000 个脉冲的全相关复数工作区是 6.08 GiB，而特征本身只是逐行归约；
    # 按脉冲分块限制二维中间工作区。
    chunk_size = module.bounded_pulse_chunk_size(echo, _FEATURE_WORKSPACE_BUDGET_BYTES)
    if progress_callback is None:
        return module.streamed_chirp_pulse_features(echo, config or {}, chunk_size)
    def report(done, total):
        progress_callback(5 + int(85 * done / total), f"计算逐脉冲特征 {done}/{total}")
    progress_callback(5, "计算逐脉冲特征")
    return module.streamed_chirp_pulse_features(
        echo, config or {}, chunk_size, progress_callback=report)


def _inversion_module():
    """Load ``inversion/src/inversion.py`` without colliding with the package."""

    import importlib.util
    source = storage.ROOT / 'inversion' / 'src'
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

    name = "rotation_period_inversion_impl"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    path = storage.ROOT / "inversion" / "src" / "inversion.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    """Dedicated GUI child process: progress on stdout, errors on stderr."""
    import argparse
    import json
    parser = argparse.ArgumentParser()
    parser.add_argument("--echo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config-json", required=True)
    parser.add_argument('--observables', type=Path)
    args = parser.parse_args()
    def report(percent, message):
        print("__PROGRESS__ " + json.dumps({"percent": percent, "message": message}), flush=True)
    try:
        build_inversion_feature_html(args.echo, json.loads(args.config_json), args.output,
                                     progress_callback=report, observables=args.observables)
    except Exception as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
