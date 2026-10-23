"""Plot the actual centroid and full-correlation 90% energy interval."""

import argparse
from pathlib import Path
import sys
from types import SimpleNamespace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from inversion.src.dataset import load_echo
from inversion.src.inversion import prepare_chirp_pulse_profiles
from inversion.src.radar_signal import range_features
from rotation_gui.window.echo_preview import _pulse_compressed_amplitude


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--echo", type=Path, default=ROOT / "runs/paras_for_70m_3h/echo/echo.npz")
    parser.add_argument("--pulse", type=int, default=835, help="从 0 开始的脉冲行号")
    parser.add_argument("--output", type=Path, default=ROOT / "tmp/range_features/range_features_single_run.png")
    args = parser.parse_args()
    echo = load_echo(args.echo)
    count = len(echo.iq)
    if not 0 <= args.pulse < count:
        raise ValueError("pulse 超出回波行范围")
    offsets = np.asarray(echo.row_fast_time_offset_s)
    common = echo.fast_time_s + np.median(offsets)
    selected = {}
    for name, value in vars(echo).items():
        selected[name] = (value[args.pulse:args.pulse + 1]
                          if isinstance(value, np.ndarray) and value.ndim and value.shape[0] == count
                          and name != "fast_time_s" else value)
    one = SimpleNamespace(**selected)
    prepared = prepare_chirp_pulse_profiles(one, {"motion_compensation": "auto"})
    full = prepared["full_compressed"][0]
    axis = prepared["full_delay_axes"][0]
    lag = len(full) - one.iq.shape[1]
    cropped = full[lag:lag + one.iq.shape[1]]
    native_axis = axis[lag:lag + one.iq.shape[1]]
    valid = (one.valid[0] if one.valid.ndim == 2
             else np.full(len(cropped), bool(one.valid[0])))
    if np.count_nonzero(valid) < 2:
        raise ValueError("该行有效样点不足两个，无法标注现行对齐距离质心")
    aligned = (np.interp(common, native_axis[valid], cropped[valid].real, left=0, right=0)
               + 1j * np.interp(common, native_axis[valid], cropped[valid].imag, left=0, right=0))
    features = range_features(prepared["processing_times"], common, aligned[None, :], delay_axes_s=common)
    power = abs(full)**2
    if not np.all(np.isfinite(power)) or power.max() <= 0:
        raise ValueError("该行没有可估计的有限非零功率")
    cumulative = np.cumsum(power / power.max())
    cumulative /= cumulative[-1]
    lo, hi = np.searchsorted(cumulative, [.05, .95], side="left")
    left, right, centroid = axis[lo]*1e9, axis[hi]*1e9, features.centroid_delay_s[0]*1e9
    assert np.isclose(right-left, prepared["full_energy_width_90_s"][0]*1e9)
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.3), gridspec_kw={"width_ratios": [1.4, 1]})
    x = axis*1e9
    axes[0].plot(x, abs(full)/abs(full).max(), color="#159b8a", lw=1.3, label="完整脉压幅度 / 峰值")
    axes[1].plot(x, cumulative, color="#159b8a", lw=1.6, label="完整脉压累计功率比例")
    for ax in axes:
        ax.axvspan(left, right, color="#e38b22", alpha=.22, label=f"中央 90% 能量区间：{right-left:.0f} ns")
        ax.axvline(left, color="#bf6200", ls="--", lw=1)
        ax.axvline(right, color="#bf6200", ls="--", lw=1)
        ax.axvline(centroid, color="#dc3030", lw=1.6, label=f"当前距离质心：{centroid:.1f} ns")
        ax.set_xlim(left-150, right+150)
        ax.set_xlabel("相对质心参考事件的时延（ns）")
        ax.grid(alpha=.2)
    axes[0].set(ylabel="幅度 / 峰值幅度", title="红线为距离质心，橙色为 90% 能量宽度")
    axes[0].legend(loc="upper right", fontsize=8)
    axes[1].set(ylabel="累计功率比例", title="两端各排除 5% 的功率", ylim=(0, 1.04))
    for level in (.05, .95):
        axes[1].axhline(level, color="#bf6200", ls=":", lw=1)
        axes[1].text(right+20, level, f"{level:.0%}", color="#bf6200", fontsize=9)
    fig.suptitle(f"实际脉冲索引 {args.pulse}（从 0 开始）；散射时刻 {one.scatter_elapsed_s[0]:.3f} s\n"
                 f"总能量（现有裁后功率和）：{features.total_power[0]:.2f}", fontsize=11)
    fig.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=170)
    fig.savefig(args.output.with_suffix(".svg"))
    plt.close(fig)
    # A second figure retains the entire axis: the first figure is explicitly a zoom.
    mean_amplitude = np.zeros(one.iq.shape[1], dtype=float)
    for start in range(0, count, 32):
        block, error = _pulse_compressed_amplitude(
            echo.iq[start:start + 32], echo.fast_time_s, echo.metadata
        )
        if block is None:
            raise ValueError(error)
        mean_amplitude += block.sum(axis=0)
    mean_amplitude /= count
    fig, panels = plt.subplots(3, 1, figsize=(12, 9))
    row_x = (axis - offsets[args.pulse]) * 1e6
    full_amplitude = abs(full)
    panels[0].plot(echo.fast_time_s * 1e6, mean_amplitude, color="#159b8a")
    panels[0].set(title=f"与 GUI 相同定义：全部 {count} 行脉压幅度的平均值（裁后输出）", ylabel="平均幅度")
    panels[0].set_xlim(echo.fast_time_s[0] * 1e6, echo.fast_time_s[-1] * 1e6)
    panels[1].plot(row_x, full_amplitude, color="#159b8a")
    panels[1].set(title=f"脉冲索引 {args.pulse}：完整相关输出，全时间范围", ylabel="幅度")
    panels[2].plot(row_x, 20 * np.log10(np.maximum(full_amplitude / full_amplitude.max(), 1e-15)), color="#159b8a")
    panels[2].set(title="同一行的对数幅度：可见线性坐标下很小的拖尾", ylabel="相对峰值（dB）")
    for ax in panels[1:]:
        ax.set_xlim(row_x[0], row_x[-1])
        ax.axvspan((left * 1e-9 - offsets[args.pulse]) * 1e6,
                   (right * 1e-9 - offsets[args.pulse]) * 1e6, color="#e38b22", alpha=.22)
        ax.axvline((centroid * 1e-9 - offsets[args.pulse]) * 1e6, color="#dc3030", lw=1)
    for ax in panels:
        ax.set_xlabel("脉冲保存行起点参考时间（μs；完整相关允许负时延）")
        ax.grid(alpha=.2)
    fig.tight_layout()
    full_output = args.output.with_name(args.output.stem + "_full.png")
    fig.savefig(full_output, dpi=150)
    plt.close(fig)
    print(f"echo={args.echo.resolve()}; pulse_index_zero_based={args.pulse}; rows={count}")
    print(f"full_axis_us=[{row_x[0]:.6f}, {row_x[-1]:.6f}]; zoom_axis_ns=[{left-150:.6f}, {right+150:.6f}]")
    print(f"full_view={full_output}")
    print(f"centroid={centroid:.6f} ns; 5%={left:.6f} ns; 95%={right:.6f} ns; width={right-left:.6f} ns")


if __name__ == "__main__":
    main()
