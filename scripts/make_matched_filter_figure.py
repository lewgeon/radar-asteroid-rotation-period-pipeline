"""生成 §2 的匹配滤波示意图（五面板，共用同一根横轴）。

输出 `outputs/fig/matched_filter_peak_at_leading_edge.svg` 与同名 `.png`。

**本图的关键是几何**：五幅面板共用同一个横轴原点与同一个比例尺
（figure 横坐标 = ``F0 + 样点下标 * S``），因此：

* 两条红色竖虚线是**真正贯穿全图的两条线**，位于回波前沿 $i_k$ 与后沿 $i_k+N_r-1$；
* (b) 模板按真实长度 $N_r$ 画在 $[0,\;N_r-1]$，左沿就在纵轴处；
* (c) 翻折模板画在 $[-N_r+1,\;0]$，即沿纵轴翻折到原点左侧；
* (d) 完整卷积画在 $[0,\;N_f+N_r-2]$，比回波长 $N_r-1$，前 $L=N_r-1$ 个样点为灰区（切片丢弃）；
* (e) 切片输出画在 $[0,\;N_f-1]$，与 (a) 同刻度。

于是可以直接看出：完整卷积的峰在 $m=L+i_k=N_r-1+i_k$，正好落在**后沿**那条红线上；
丢掉前 $L$ 个样点后峰左移 $L$，落到 $i_k$，即**前沿**那条红线上——这就是
"匹配滤波后峰值位于回波前沿"的来源。

其余绘图约定：
* 中文正文宋体、数学 STIX（不要把 Times New Roman 放字体链首位：它无中文字形，
  matplotlib 不做逐字形回退，会整片变方框）；
* 坐标轴本身就是箭头（一条 annotate 画完轴+箭头），头部细长尖锐；坐标轴浅灰细线、
  信号饱和蓝粗线；信号为 0 的区段显示为"蓝粗线盖住灰细线"，覆盖区起止一目了然；
* 刻度与轴标签用 point 偏移定位；标题短、坐标区外左对齐；
* 图内不写结论（交给文档图注）。

物理约定：`baseband_convention = "centered"`，脉冲内瞬时频率由 −B/2 线性升到 +B/2、
在脉冲中点过零，因此实部波形两端密、中间疏、关于中点对称。
"""

from __future__ import annotations

import re
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import ArrowStyle  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "fig"
NAME = "matched_filter_peak_at_leading_edge"

INK, MUTED, BLUE, SHADE = "#1f2429", "#4a545e", "#1f5fa8", "#e8ecf0"
LIGHT, BAND, RED = "#cfe0f2", "#f4f7fa", "#b8433f"
AXIS, RULE = "#7b858d", "#c9d0d6"

N_F = 400            # 行内样点数（示意值）
N_R = 120            # 参考模板样点数（示意值）
I_K = 150            # 回波前沿所在样点下标
L_LAG = N_R - 1      # 匹配滤波切掉的已知相关峰滞后
I_TAIL = I_K + N_R - 1     # 回波后沿
I_MID = I_K + (N_R - 1) / 2.0
M_FULL = N_F + N_R - 2     # 完整卷积的末样点下标
M_PEAK = L_LAG + I_K       # 完整卷积峰位（= I_TAIL）
BETA = 1.0 / 6.0     # 归一化带宽 B/f_s（示意值）
Y_LIM = 2.0          # 波形面板纵轴半幅：横轴（零幅度）正好在纵轴中点
Y_TIP = 1.90
Y_OUT_TOP = 1.34     # 单极性面板量程上限：使 N_r 刻度与 +1 刻度同高
TICK_PT, LABEL_PT, YLABEL_PT = -7.0, -11.0, -42.0

# 共用坐标系：figure_x = F0 + 样点下标 * S
S = 0.0012763
F0 = 0.3069
ROW = {"a": 0.840, "b": 0.670, "c": 0.500, "d": 0.320, "e": 0.140}
H_WAVE, H_OUT = 0.115, 0.125

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["SimSun", "Songti SC", "Noto Serif CJK SC", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "axes.unicode_minus": False,
        "svg.fonttype": "none",
        "font.size": 13,
    }
)

fig = plt.figure(figsize=(9.6, 9.6), dpi=150)
SHARP = ArrowStyle("-|>", head_length=1.0, head_width=0.20)


def add_panel(row: str, left_index: float, right_index: float, height: float):
    left = F0 + left_index * S
    width = (right_index - left_index) * S
    ax = fig.add_axes([left, ROW[row], width, height])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_xlim(left_index, right_index)
    ax.set_xticks([])
    ax.set_yticks([])
    return ax


def draw_axes(ax, y_bottom: float, y_tip: float, x_tip: float, x_axis_y: float) -> None:
    common = dict(color=AXIS, lw=1.4, mutation_scale=11, shrinkA=0.0, shrinkB=0.0)
    ax.annotate("", xy=(0.0, y_tip), xytext=(0.0, y_bottom),
                arrowprops=dict(arrowstyle=SHARP, **common),
                annotation_clip=False, zorder=5)
    ax.annotate("", xy=(x_tip, x_axis_y), xytext=(ax.get_xlim()[0], x_axis_y),
                arrowprops=dict(arrowstyle=SHARP, **common),
                annotation_clip=False, zorder=5)


def y_ticks(ax, values, labels) -> None:
    for value, label in zip(values, labels):
        ax.annotate("", xy=(0.0, value), xytext=(TICK_PT, 0.0), textcoords="offset points",
                    arrowprops=dict(arrowstyle="-", color=AXIS, lw=1.3),
                    annotation_clip=False, zorder=9)
        ax.annotate(label, xy=(0.0, value), xytext=(LABEL_PT, 0.0),
                    textcoords="offset points", color=INK, fontsize=12,
                    ha="right", va="center", annotation_clip=False, zorder=9)


def x_ticks(ax, values, labels, y_level: float) -> None:
    for value, label in zip(values, labels):
        ax.annotate("", xy=(value, y_level), xytext=(0.0, TICK_PT), textcoords="offset points",
                    arrowprops=dict(arrowstyle="-", color=AXIS, lw=1.3),
                    annotation_clip=False, zorder=9)
        ax.annotate(label, xy=(value, y_level), xytext=(0.0, LABEL_PT),
                    textcoords="offset points", color=INK, fontsize=12,
                    ha="center", va="top", annotation_clip=False, zorder=9)


def y_label(ax, text: str) -> None:
    ax.annotate(text, xy=(0.0, 0.5), xycoords="axes fraction",
                xytext=(YLABEL_PT, 0.0), textcoords="offset points",
                rotation=90, ha="center", va="center", color=INK,
                fontsize=12.5, annotation_clip=False)


def title(ax, text: str) -> None:
    ax.set_title(text, loc="left", x=0.012, color=INK, fontsize=13.5,
                 fontweight="bold", pad=5)


def width_arrow(ax, x0: float, x1: float, y: float, label: str, y_label_pos: float) -> None:
    ax.annotate("", xy=(x1, y), xytext=(x0, y),
                arrowprops=dict(arrowstyle="<|-|>", color=MUTED, lw=1.1, mutation_scale=9,
                                shrinkA=0.0, shrinkB=0.0),
                annotation_clip=False, zorder=9)
    ax.text((x0 + x1) / 2.0, y_label_pos, label, color=MUTED, fontsize=11,
            ha="center", va="center")


# 脉冲内波形（centered chirp 实部）：局部坐标 j = 0..N_R-1
x_pulse = np.linspace(0.0, N_R - 1.0, 16000)
phase = np.pi * (BETA / N_R) * (x_pulse - (N_R - 1) / 2.0) ** 2
y_pulse = np.cos(phase)

# —— (a) 一行回波：整行都有采样，脉冲外为 0 ——
ax_a = add_panel("a", 0.0, N_F - 1.0, H_WAVE)
ax_a.set_ylim(-Y_LIM, Y_LIM)
draw_axes(ax_a, -Y_TIP, Y_TIP, N_F - 1.0, 0.0)
y_ticks(ax_a, [-1.0, 0.0, 1.0], ["$-1$", "0", "$+1$"])
y_label(ax_a, "幅度（归一化）")
title(ax_a, "(a) 一行回波")
x_echo = np.linspace(0.0, I_TAIL + 30.0, 24000)
y_echo = np.zeros_like(x_echo)
sel = (x_echo >= I_K) & (x_echo <= I_TAIL)
y_echo[sel] = np.interp(x_echo[sel] - I_K, x_pulse, y_pulse)
ax_a.axvspan(I_K, I_TAIL, color=BAND, zorder=1)
ax_a.plot(x_echo, y_echo, color=BLUE, lw=2.2, zorder=6, solid_capstyle="butt")
ax_a.axvline(I_MID, color=INK, lw=1.2, ls=(0, (1.6, 3)), zorder=8, alpha=0.55)
x_ticks(ax_a, [0.0, I_K, N_F - 1.0], ["0", "$i_k$", "$N_f-1$"], 0.0)
for x_pos, label in ((I_K, "$f=-\\frac{B}{2}$"), (I_MID, "$f=0$"),
                     (I_TAIL, "$f=+\\frac{B}{2}$")):
    ax_a.text(x_pos, 1.04, label, color=MUTED, fontsize=11,
              ha="center", va="bottom", zorder=9)
ax_a.text(I_K - 6.0, -1.40, "回波前沿", color=RED, fontsize=11, ha="right",
          va="center", zorder=9)

# —— (b) 参考模板：真实长度 N_R，左沿在纵轴处 ——
ax_b = add_panel("b", 0.0, N_R - 1.0, H_WAVE)
ax_b.set_ylim(-Y_LIM, Y_LIM)
draw_axes(ax_b, -Y_TIP, Y_TIP, N_R - 1.0, 0.0)
y_ticks(ax_b, [-1.0, 0.0, 1.0], ["$-1$", "0", "$+1$"])
y_label(ax_b, "幅度（归一化）")
title(ax_b, "(b) 参考模板")
ax_b.axvspan(0.0, N_R - 1.0, color=BAND, zorder=1)
ax_b.plot(x_pulse, y_pulse, color=BLUE, lw=2.2, zorder=6, solid_capstyle="butt")
ax_b.axvline((N_R - 1) / 2.0, color=INK, lw=1.2, ls=(0, (1.6, 3)), zorder=8, alpha=0.55)
ax_b.text(N_R - 1.0, 1.04, "只定义在 $N_r$ 个样点上", color=BLUE, fontsize=11,
          ha="right", va="bottom", zorder=9)

# —— (c) 翻折模板沿 m 滑动：模板右沿位置从 0 走到 L+i_k ——
C_LEFT, C_RIGHT = -(N_R - 1.0), 300.0
ax_c = add_panel("c", C_LEFT, C_RIGHT, H_WAVE)
ax_c.set_ylim(-Y_LIM, Y_LIM)
draw_axes(ax_c, -Y_TIP, Y_TIP, C_RIGHT, 0.0)
y_ticks(ax_c, [-1.0, 0.0, 1.0], ["$-1$", "0", "$+1$"])
y_label(ax_c, "幅度（归一化）")
title(ax_c, "(c) 翻折模板沿 $m$ 滑动")
pos_flip = np.linspace(C_LEFT, 0.0, 16000)
y_flip = np.interp(-pos_flip, x_pulse, y_pulse)   # 关于纵轴 n=0 翻折
for shift, label, color, alpha, lw in (
    (0.0, "$m=0$", BLUE, 1.0, 2.2),
    (80.0, "", AXIS, 0.55, 1.3),
    (160.0, "", AXIS, 0.55, 1.3),
    (float(M_PEAK), "$m=L+i_k$", BLUE, 0.85, 2.0),
):
    ax_c.plot(pos_flip + shift, y_flip, color=color, alpha=alpha, lw=lw,
              zorder=6 if color == BLUE else 4, solid_capstyle="butt")
    if label:
        ax_c.text(shift + C_LEFT / 2.0, 1.12, label, color=color, alpha=max(alpha, 0.75),
                  fontsize=10.5, ha="center", va="bottom", zorder=9)
ax_c.annotate("", xy=(C_RIGHT - 4.0, 1.62), xytext=(C_LEFT + 4.0, 1.62),
              arrowprops=dict(arrowstyle=SHARP, color=MUTED, lw=1.1, mutation_scale=9,
                              shrinkA=0.0, shrinkB=0.0),
              annotation_clip=False, zorder=9)
ax_c.text(70.0, 1.80, "模板随 $m$ 增大向右滑动", color=MUTED, fontsize=11,
          ha="center", va="center", zorder=9)
ax_c.text(200.0, -1.45, "滑到 $m=L+i_k$ 时与回波脉冲完全重合", color=MUTED,
          fontsize=11, ha="center", va="center", zorder=9)

# —— (d) 完整卷积：跨 [0, N_F+N_R-2] ——
ax_d = add_panel("d", 0.0, M_FULL, H_OUT)
ax_d.set_ylim(-0.02, Y_OUT_TOP)
draw_axes(ax_d, 0.0, Y_OUT_TOP * 0.95, M_FULL, 0.0)
y_ticks(ax_d, [0.0, 1.0], ["0", "$N_r$"])
y_label(ax_d, "$|y[m]|$")
title(ax_d, "(d) 完整卷积结果")
x_full = np.linspace(0.0, M_FULL, 20000)
y_full = np.abs(np.sinc((x_full - M_PEAK) / 5.0)) * np.exp(-np.abs(x_full - M_PEAK) / 55.0)
ax_d.axvspan(0.0, L_LAG, color=SHADE, zorder=1)
ax_d.plot(x_full, y_full, color=BLUE, lw=2.0, zorder=6)
ax_d.axvline(L_LAG, color=INK, lw=1.2, ls=(0, (1.6, 3)), zorder=8, alpha=0.7)
x_ticks(ax_d, [0.0, L_LAG, M_PEAK, M_FULL],
        ["0", "$L$", "$L+i_k$", "$N_f+N_r-2$"], 0.0)
ax_d.text(L_LAG / 2.0, 0.60, "切片丢弃", color=MUTED, fontsize=11, ha="center", va="center")
ax_d.text(M_PEAK + 8.0, 1.02, "峰在 $L+i_k$", color=INK, fontsize=11, ha="left",
          va="center")
width_arrow(ax_d, 12.0, M_FULL - 12.0, 1.20, "长 $N_f+N_r-1$", 1.29)
ax_d.annotate("$m$（完整相关下标）", xy=(0.5, 0.0), xycoords="axes fraction",
              xytext=(0.0, -28.0), textcoords="offset points", ha="center", va="top",
              color=INK, fontsize=12, annotation_clip=False)

# —— (e) 切片输出：与 (a) 同刻度 ——
ax_e = add_panel("e", 0.0, N_F - 1.0, H_OUT)
ax_e.set_ylim(-0.02, Y_OUT_TOP)
draw_axes(ax_e, 0.0, Y_OUT_TOP * 0.95, N_F - 1.0, 0.0)
y_ticks(ax_e, [0.0, 1.0], ["0", "$N_r$"])
y_label(ax_e, "$|\\chi[k,i]|$")
title(ax_e, "(e) 切片后的输出")
x_out = np.linspace(0.0, I_TAIL + 30.0, 8000)
y_out = np.abs(np.sinc((x_out - I_K) / 5.0)) * np.exp(-np.abs(x_out - I_K) / 55.0)
ax_e.plot(x_out, y_out, color=BLUE, lw=2.2, zorder=6)
ax_e.fill_between(x_out, 0.0, y_out, where=np.abs(x_out - I_K) <= 5.0,
                  color=LIGHT, zorder=4)
x_ticks(ax_e, [0.0, I_K, N_F - 1.0], ["0", "$i_k$", "$N_f-1$"], 0.0)
ax_e.text(I_K + 10.0, 1.02, "相关峰", color=INK, fontsize=11, ha="left", va="center")
ax_e.annotate("$i$（行内样点下标，快时间）", xy=(0.5, 0.0), xycoords="axes fraction",
              xytext=(0.0, -28.0), textcoords="offset points", ha="center", va="top",
              color=INK, fontsize=12, annotation_clip=False)

# —— 两条贯穿全图的红色竖虚线：回波前沿与后沿 ——
band_top = ROW["a"] + H_WAVE + 0.012
band_bottom = ROW["e"] - 0.004
for index in (I_K, I_TAIL):
    x_fig = F0 + index * S
    fig.add_artist(Line2D([x_fig, x_fig], [band_bottom, band_top],
                          transform=fig.transFigure, color=RED, lw=1.5,
                          ls=(0, (6, 4)), alpha=0.9, zorder=20))

OUT.mkdir(parents=True, exist_ok=True)


def text_overlaps(figure) -> list[tuple[str, str]]:
    """列出互相重叠的文字对——用于替代肉眼检查标注碰撞。"""

    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    boxes = []
    for ax in figure.axes:
        for item in list(ax.texts) + [ax.title, ax.xaxis.label, ax.yaxis.label]:
            if not item.get_text().strip():
                continue
            label = item.get_text().replace("\n", " ")[:18]
            boxes.append((label, item.get_window_extent(renderer)))
    hits = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if boxes[i][1].overlaps(boxes[j][1]):
                hits.append((boxes[i][0], boxes[j][0]))
    return hits


for suffix in ("svg", "png"):
    path = OUT / f"{NAME}.{suffix}"
    fig.savefig(path)
    print(f"写出 {path}  ({path.stat().st_size} 字节)")
collisions = text_overlaps(fig)
print(f"文字重叠检查：{len(collisions)} 对")
for left, right in collisions:
    print(f"  ! {left!r}  ×  {right!r}")
plt.close(fig)

svg_path = OUT / f"{NAME}.svg"
svg_text = svg_path.read_text(encoding="utf-8")
chain = "'SimSun', 'Songti SC', 'Noto Serif CJK SC', 'DejaVu Serif', serif"
for family in ("'SimSun'", "'DejaVu Serif'", "'DejaVu Sans'", "'Times New Roman'"):
    svg_text = re.sub(rf"font-family: {re.escape(family)}(?!,)", f"font-family: {chain}",
                      svg_text)
svg_path.write_text(svg_text, encoding="utf-8")
print(f"位图元素 {svg_text.count('<image')} 个，文本元素 {svg_text.count('<text')} 个，"
      f"最终 {svg_path.stat().st_size} 字节")
