# 采集路径窗取代 Chirp 时间保护

> 2026-09-24 的前沿补偿、字节数和只读行措辞已写入本文。当日核对与未采纳项见 [DATE_LOG_2026-09-24.md](DATE_LOG_2026-09-24.md)。

Chirp 的快时间余量改成一个以米为单位的采集路径窗。秒制的 `pre_guard_s` / `post_guard_s` 不再是配置字段。反演算法、`echo.npz` 的二维 IQ 契约、以及 ADC 整数网格仍留在观测阶段，这三件事都不在本次范围内。

## 行宽

静止时标下，相对质心参考回波：

$$
T_{\mathrm{before}}=T_{\mathrm{gate}},\qquad
T_{\mathrm{after}}=T_{\mathrm{pulse}}+T_{\mathrm{gate}},\qquad
T_{\mathrm{gate}}=\frac{D_{\mathrm{extent}}}{c}.
$$

$D_{\mathrm{extent}}$ 是 `observation.target.extent_path_m`。它已经是额外双程路径，时延用 $D_{\mathrm{extent}}/c$，不是 $2D_{\mathrm{extent}}/c$。有路径变化率时，两侧再乘 $S_i=\max(1,\,1/(1-v_L/c))$。前后格数是

$$
n_{\mathrm{pre}}=\left\lceil T_{\mathrm{before}}f_s+0.5\right\rceil,\qquad
n_{\mathrm{after}}=\left\lceil T_{\mathrm{after}}f_s+0.5\right\rceil.
$$

半个采样用来盖住质心被 `rint` 挪动最多半步的残差。只补偿后沿时，后续脉冲的质心若被舍入到更晚的网格点，首样点会晚于 $t_{\mathrm{rx}}-T_{\mathrm{gate}}$，最多略小于半个采样；回波核只计算保存行里的全局索引，补不回这个前沿。两侧都加 0.5 后，每一侧最多多 1 列。前沿覆盖的仍是整个路径窗 $T_{\mathrm{gate}}$，再加最多 1 个采样的取整余量。$1\,\mathrm{km}$、$200\,\mathrm{MHz}$ 时 $n_{\mathrm{pre}}=668$，这段余量约 $4.4\,\mathrm{ns}$，不是全部前置保护，也不是 $0.5/f_s$。以秒计的前置保护不再单独存在。连续波不使用这个路径窗。

## 旧 JSON

载入时若仍有 `pre_guard_s` 或 `post_guard_s`，先取

$$
D_{\mathrm{extent}}\leftarrow\max(D_{\mathrm{extent}},\,c\,T_{\mathrm{pre}},\,c\,T_{\mathrm{post}}),
$$

再删掉这两个键，并发出以「采集路径窗已合并」开头的警告。负数或非有限值直接报错，不会被折进去。`plan_reception` 本身不读这两个键；调用方若仍传入，会直接报错，避免窗口在无人知晓的情况下变窄。

这个 $\max$ 避免只留下三者中较小的一个。旧行宽是每一侧的保护时间与路径展宽相加。前置和后置不相等时，较短的一侧会变长、较长的一侧可能变短；警告按前侧和后侧分开写，不把整行说成一律变短。仓库里的试例是直接改写的，不靠这次合并。`configs/point_target_debug.json` 仍是 $3000\,\mathrm{m}$ 路径窗，原先各 $1\,\mathrm{ms}$ 的时间保护被去掉，保存行因此变短。

## 调度预留

单站自动选时的占用长度改为

$$
H=D+\tau_{\mathrm{path,max}}+T_{\mathrm{switch}}+T_{\mathrm{safety}}+T_{\mathrm{gate}}+T_{\mathrm{pulse}}.
$$

路径窗只加一次。相对改前的公式，少了单独的 $T_{\mathrm{post}}$。近似 ADC 预览的两端也只留 $T_{\mathrm{gate}}$，不再另减前置保护、另加后置保护。

## 试例

`configs/chirp_mesh_target_test.json` 用来在压缩后分辨百米级形体，同时把一次试验的脉冲数从约 60000 降到 96：

| 字段 | 值 |
| --- | ---: |
| `bandwidth_hz` | $150\,\mathrm{MHz}$（$\delta R=c/(2B)\approx 1.00\,\mathrm{m}$） |
| `fast_sample_rate_hz` | $200\,\mathrm{MHz}$（大于带宽；账面上的 $300\,\mathrm{MHz}$ 没有写进试例） |
| `carrier_frequency_hz` | $2.38\,\mathrm{GHz}$ |
| `pulse_width_s` | $40\,\mu\mathrm{s}$ |
| `extent_path_m` | $1000\,\mathrm{m}$ |
| `prf_hz` | $2\,\mathrm{Hz}$ |
| `run_duration_s` | $2\,\mathrm{s}$（$N_{\mathrm{pulse,run}}=\lfloor(D-T_{\mathrm{pulse}})\mathrm{PRF}\rfloor+1=4$） |
| `run_count` | $24$ |
| `period_min_s` / `period_max_s` | $3600$ / $14400\,\mathrm{s}$，盖住 $7200\,\mathrm{s}$ 自转 |

`inversion.cpi_duration_s` 仍是 $16\,\mathrm{s}$。$2\,\mathrm{Hz}$、每次 Run 只有 4 个脉冲时，相干处理会走现行的逐脉冲回退。本次不改反演算法。

静止时标下，$1\,\mathrm{km}$、$40\,\mu\mathrm{s}$、$200\,\mathrm{MHz}$ 的保存行是 9337 列（$n_{\mathrm{pre}}=668$，$n_{\mathrm{after}}=8668$）。24 次 Run、每次 4 个脉冲，共 96 个脉冲。`iq` 与 `clean_iq` 各一份复 float32 时，二维数组是

$$
2\times 96\times 9337\times 8=14341632\,\mathrm{B}=14.341632\times 10^{6}\,\mathrm{B},
$$

十进制约 $14.34\,\mathrm{MB}$。这是按行宽公式作的算术，不是一次实际写出的 `echo.npz`；文件里还有元数据，会比这个数组更大。进入 `unique` 之前的二维索引数组仍然按 $N_{\mathrm{pulse}}\times N_{\mathrm{fast}}$ 分配；这个试例上它大约是数 MB。若把 60000 个 $10\,\mathrm{ms}$ 脉冲配上 $300\,\mathrm{MHz}$，那些二维数组会在去重之前先耗尽内存。本次没有改存储契约，也没有去掉这层分配。

点目标夹具 `configs/chirp_point_target_test.json` 和 `configs/point_target_debug.json` 只删掉时间保护，不改成上面的高分辨参数。点目标试例的路径窗是 0；5000 Hz、10 ms 脉宽下，前沿半采样补偿使 $n_{\mathrm{pre}}=1$，每行 53 点。

## 界面

「接收采样」卡片上的字段是快时间采样率和「采集路径窗」（m/km）。下面一行只读文字给出静止时标的门时延、前沿取整后的样点数 $n_{\mathrm{pre}}$（写在门时延后面的括号里）、整行样点数 $N_{\mathrm{fast}}$，以及 $c/(2B)$。$n_{\mathrm{pre}}=\lceil T_{\mathrm{gate}}f_s+0.5\rceil$，比 $T_{\mathrm{gate}}f_s$ 最多多 1，不是门内物理样点数。运动时标伸缩会使实际行宽不小于这个静止估计。

## 明确没做

- 不把 `echo.npz` 改成只存匹配滤波后的距离像。
- 不把 ADC 整数网格从观测阶段迁到回波阶段。
- 不改周期搜索算法，也不为了短 Run 去补距离–多普勒立方。

## 复现

在仓库根目录：

```text
conda run -n pytorch python -m pytest tests/test_range_gate.py tests/test_physics_regressions_v4.py tests/test_schema_v4_contract.py tests/test_gui_schema_v4.py -q
```

在 `observation/` 目录：

```text
conda run -n pytorch python -m pytest tests -q
```

在 `echo/` 目录：

```text
conda run -n pytorch python -m pytest tests/test_simple_chirp_plan.py -q
```

半采样补偿的区分力在 `observation/tests/test_planning_regressions.py`：去掉补偿时，记录中的负裕量夹具会失败；$\lceil x+0.4\rceil$ 的最小裕量比 $\lceil x+0.5\rceil$ 低 0.09 个采样以上。解析下界是 $N_{\mathrm{fast}}\ge n_{\mathrm{pre}}+T_{\mathrm{after}}f_s+1.5$。
