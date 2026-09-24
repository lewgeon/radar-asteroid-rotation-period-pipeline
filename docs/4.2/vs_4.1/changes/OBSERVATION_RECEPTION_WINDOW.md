# 观测解算：接收窗两端与保存行网格对齐（4.2）

> 状态：已在 4.2 实现。本文记录相对 4.1 的已落地行为变化，不是待实施计划。

本文说明 4.2 对 `observation/src/planning.py::plan_reception()` 的修改：Run 级连续 ADC 窗的**起点与终点**都改为按**保存行的整数网格**定义。相关配置字段与术语见 `docs/4.2/OBSERVATION_TIME_SELECTION.md` 与 `docs/4.2/GLOSSARY.md`。

## 1. 现象

4.1 的 chirp 计划上有三类与"窗边界 vs 行边界"有关的表现：

1. 逐 Run 警告 `存在保存窗/ADC 整数索引重叠；旧版逐行回波生成器必须拒绝该计划`；
2. 逐 Run 警告 `首行因接收机开启时刻被截短`；
3. **没有任何警告**：每个 Run 最后一行的末尾 δ 个格子被 `row_valid` 判为无效（δ = 0、1 或 2）。chirp 设计草稿配置上表现为 `row_valid.sum(axis=1) = [251×7, 250]`。

三者都不是物理回波重叠（`signal_echo_overlap` 始终为假），而是窗边界的**计数单位**与行的**计数单位**不一致：行按采样**点**计数，窗的两端原本按"物理时刻 + 向上取整"给出。

## 2. 量的定义

| 符号 | 含义 | 配置字段 / 代码 |
|---|---|---|
| $T_{\mathrm{pre}}$ | 前置保护时间 | `receiver_sampling.pre_guard_s` |
| $T_{\mathrm{post}}$ | 后置保护时间 | `receiver_sampling.post_guard_s` |
| $T_{\mathrm{pulse}}$ | 脉冲宽度 | `transmit.pulse_width_s` |
| $D_{\mathrm{extent}}$ | 目标相对质心参考路径的最大额外双程路径 | `target.extent_path_m` |
| $c$ | 光速 | 常量 |
| $f_s$ | 快时间采样率 | `receiver_sampling.fast_sample_rate_hz` |
| $S_i$ | 第 $i$ 个脉冲的时标伸缩因子，$S_i=1/(1-v_{L,i}/c)\ge 1$ | 几何求解 |
| $t_{\mathrm{rx},i}$ | 第 $i$ 个脉冲**质心回波**的接收时刻 | `receive_elapsed_s` |
| $W_{\mathrm{pre},i},W_i$ | 最早回波提前量、回波尾沿 | `before_by_pulse`$=\frac{D}{c}S_i$、`after_by_pulse`$=(T_{\mathrm{pulse}}+\frac{D}{c})S_i$ |
| $T_{\mathrm{before}},T_{\mathrm{after}}$ | 行前/后侧总长（含保护） | `before_s`$=T_{\mathrm{pre}}+\max_i W_{\mathrm{pre},i}$、`after_s`$=T_{\mathrm{post}}+\max_i W_i$ |
| $n_{\mathrm{pre}},n_{\mathrm{after}}$ | 质心左/右格数 | `n_pre`$=\lceil T_{\mathrm{before}}f_s\rceil$、`n_after`$=\lceil T_{\mathrm{after}}f_s+0.5\rceil$ |
| $M$ | 每行格数 | `fast_sample_count`$=n_{\mathrm{pre}}+n_{\mathrm{after}}+1$ |
| $t_{\mathrm{on}},t_{\mathrm{off}}$ | 窗打开/关闭时刻 | `rx_adc_start_elapsed_s`、`rx_adc_stop_elapsed_s` |
| $Q$ | 窗内样点个数，有效索引为 $0\dots Q-1$ | `q_off` |
| $k_i$ | 第 $i$ 个质心在窗内第几格 | `centroid_index`$=\mathrm{rint}\big((t_{\mathrm{rx},i}-t_{\mathrm{on}})f_s\big)$ |
| $s_i$ | 第 $i$ 行第一格的全局索引 | `row_start_sample`$=k_i-n_{\mathrm{pre}}$ |

行内第 $n_{\mathrm{pre}}$ 格（从 0 数）是该脉冲的质心，所以第 $i$ 行覆盖全局索引 $s_i\dots s_i+M-1$，末格索引为 $k_i+n_{\mathrm{after}}$。

注意 $T_{\mathrm{pre}}$、$T_{\mathrm{post}}$ 不乘 $S_i$；体尺度展宽在参考回波两侧各出现一次。

## 3. 两个锚点，原来只有一个对齐

4.1 的窗两端定义如下（`t_{\mathrm{earliest}}=\min_i(t_{\mathrm{rx},i}-W_{\mathrm{pre},i})$）：

$$t_{\mathrm{on}}=t_{\mathrm{earliest}}-T_{\mathrm{pre}},\qquad
t_{\mathrm{off}}\ \text{由}\ t_{\mathrm{off}}^{\mathrm{req}}=\max_i(t_{\mathrm{rx},i}+W_i)+T_{\mathrm{post}}\ \text{向上取整得到}.$$

两端都锚在**连续时间的物理需求**上，而保存行锚在**质心 + 整数格**上。于是：

- 左端：$\mathrm{rint}$ 与 $\lceil\cdot\rceil$ 对同一个实数取整，方向相反，$\mathrm{frac}\ne0$ 时相差 1 → 首行起点为 $-1$，被截断（现象 2）；
- 右端：行的末格时刻恰好等于 $t_{\mathrm{off}}^{\mathrm{req}}$（因为 $n_{\mathrm{after}}=\lceil(T_{\mathrm{post}}+\max_i W_i)f_s\rceil$，而行尾相对质心正好走 $n_{\mathrm{after}}$ 格），而掩码是半开区间 $\text{index}<Q$ → 末格被判无效（现象 3）。

## 4. 修改一：窗起点按行网格（左端）

$$t_{\mathrm{on}}=\min_i t_{\mathrm{rx},i}-\frac{n_{\mathrm{pre}}}{f_s}.$$

窗起点定义成"第一个质心之前 $n_{\mathrm{pre}}$ 个**采样步**"，于是 $(t_{\mathrm{rx},0}-t_{\mathrm{on}})f_s$ 恰为 $n_{\mathrm{pre}}$ 个整数栅格量，首行起点恒为 0：

$$s_0=\mathrm{rint}\big((t_{\mathrm{rx},0}-t_{\mathrm{on}})f_s\big)-n_{\mathrm{pre}}=0 .$$

对齐不再依赖数值巧合，而是构造性的。同时保证前置保护不小于请求值：对第 $i$ 个脉冲，

$$\big(\min_j t_{\mathrm{rx},j}-W_{\mathrm{pre},i}\big)-t_{\mathrm{on}}-T_{\mathrm{pre}}
=\underbrace{\Big(\frac{n_{\mathrm{pre}}}{f_s}-T_{\mathrm{before}}\Big)}_{\in[0,1/f_s)}
+\underbrace{\big(\max_j W_{\mathrm{pre},j}-W_{\mathrm{pre},i}\big)}_{\ge 0}\ \ge\ 0 .$$

第二项在 $S_j$ 随脉冲变化（运动目标）时可以超过一个采样周期，所以"前置保护只多一个采样周期"只在 $S_j$ 恒定时成立；不变的是它**永远不小于** $T_{\mathrm{pre}}$。

注意这里必须锚在**质心**（$\min_i t_{\mathrm{rx},i}$）而不是"最早回波"（$t_{\mathrm{earliest}}$）：$n_{\mathrm{pre}}$ 已经包含 $T_{\mathrm{pre}}$ 与展宽，从最早回波再减 $n_{\mathrm{pre}}/f_s$ 会把展宽重复计入一次。

## 5. 修改二：窗尾按行网格（右端）

半开窗必须覆盖每一行的每一格，而末格索引为 $\max_i s_i+M-1$，因此

$$Q=\max_i s_i+M=\big(\text{末格索引}\big)+1 .$$

4.2 删除了原先用于计算 $Q$ 的物理量 `desired_rx_off`（它只被 $Q$ 使用），窗尾不再经过 $\lceil\cdot\rceil$，也不再有 `-1e-12` 浮点微调。

**物理需求仍被覆盖**，但改由行宽公式隐含。注意后置格数带 **0.5 个采样的栅格补偿**：

$$M=n_{\mathrm{pre}}+n_{\mathrm{after}}+1,\qquad
n_{\mathrm{after}}=\Big\lceil (T_{\mathrm{post}}+\max_i W_i)f_s+0.5\Big\rceil
\ \Longrightarrow\ \text{末格时刻}\ \ge\ \max_i(t_{\mathrm{rx},i}+W_i)+T_{\mathrm{post}} .$$

补偿的来历：行宽右端只按"质心之后 $n_{\mathrm{after}}$ 格"延伸，而质心在采样栅格上带 $\mathrm{rint}$ 的亚样点残差。只做 $\lceil\cdot\rceil$ 时末格时刻可能比需求早最多约 0.46 个采样（实测最坏值，参数 $f_s=1000$、$\mathrm{PRF}=20.5$、前后保护为 0）；补 0.5 点后不等式恒成立。

守护它的测试是 `test_post_guard_margin_is_never_negative`——它专门取在**无补偿时确实为负**的参数点（实测缺口 $-0.4634$、$-0.3634$、$-0.3333$、$-0.2619$ 个采样），因此对"删掉补偿"这一步有区分力；`test_reception_window_covers_echo_and_post_guard` 继续守住行宽对物理需求的覆盖（它从配置与几何独立重算，不依赖被删除的 `desired_rx_off`）。

**窗尾因此比旧定义晚 δ 个采样周期**。在 $S_i$ 为 Run 内常数（静止或各脉冲伸缩相同）时，记 $a=(t_{\mathrm{rx,last}}-t_{\mathrm{on}})f_s=m+f$、$b=T_{\mathrm{after}}f_s=n+g$（$f,g\in[0,1)$），带补偿时

$$\delta=\mathrm{rint}(a)+\lceil b+0.5\rceil+1-\lceil a+b\rceil .$$

需要把两个量分开写，不能混用：

- **行宽增量** $\lceil b+0.5\rceil-\lceil b\rceil\in\{0,1\}$。触发条件是 $\mathrm{frac}(b)=0$ 或 $>0.5$；$\mathrm{frac}(b)\in(0,0.5]$ 时行宽与无补偿公式相同。
- **窗尾推迟量** $\delta$ 还要加上质心锚定项 $\mathrm{rint}(a)$。记 $a=m+f$、$b=n+g$（$f,g\in[0,1)$），$\rho=\mathrm{rint}(m+f)-m\in\{0,1\}$，则 $\delta=\rho+\lceil g+0.5\rceil+1-\lceil f+g\rceil$。在 $S_i$ 为 Run 内常数时 **$\delta\in\{1,2\}$，下界是 1，不可能是 0**。质心正好落在采样栅格上且保护时间对齐到整数格（$f=0$，$g=0$）时 $\delta=2$，所以“把保护时间对齐成采样间隔整数倍”并不能避免旧定义丢格，反而是最常见的触发形态。

$S_i$ 随脉冲变化时，$n_{\mathrm{after}}$ 取 Run 内最大 $W$，窗尾取 $t_{\mathrm{rx},i}+W_i$ 的最大值点，$\delta$ 的表达式形式上仍按该最大值点计算，但不再保证上界为 2。

上面的 $\delta$ 只描述**窗尾规则**的差异（固定 $t_{\mathrm{on}}$）。新旧计划的**实际窗长差**还包含左端位移（§4 的 $t_{\mathrm{on}}$ 提前量），两者不可混用。

## 6. 保证与代价

**保证**

1. 首行起点恒为 0，不再有「首行被截短」（单站切换推迟开窗的情形除外，见代价 3）。
2. 每一行的每一格都在窗内：$\max_i s_i+M=Q$，`row_valid` 不再有恒为假的末列。
3. 窗尾不早于物理需求：末格时刻 $\ge\max_i(t_{\mathrm{rx},i}+W_i)+T_{\mathrm{post}}$（由 $n_{\mathrm{after}}$ 的 $\lceil\cdot+0.5\rceil$ 栅格补偿保证，见 §5；由 `test_post_guard_margin_is_never_negative` 守住）。
4. 行格式统一：所有保存行相对质心的偏置一致，`row_fast_time_offset_s` 不再出现首行与其余行不同。
5. `centroid_fractional_offset_s` 仍为亚样点残差（绝对值不超过半个采样周期）。

**代价**

1. 窗长相对 4.1 变化：左端提前量为

$$t_{\mathrm{on}}^{4.1}-t_{\mathrm{on}}=\underbrace{\Big(\frac{n_{\mathrm{pre}}}{f_s}-T_{\mathrm{before}}\Big)}_{\in[0,1/f_s)}+\underbrace{\big(\max_j W_{\mathrm{pre},j}-W_{\mathrm{pre},0}\big)}_{\Delta_S\ \ge 0},$$

$\Delta_S$ 在 $S_j$ 随脉冲变化时可以超过一个采样周期（静止或 $S_j$ 恒定时 $\Delta_S=0$，此时提前量严格不到一个采样周期）；右端推迟量为 $\delta$（见 §5，$S_i$ 恒定时 $\delta\in\{1,2\}$）。`rx_adc_start_elapsed_s` 只会提前或不变，`rx_adc_stop_elapsed_s` 只会推迟或不变，Run 级内存估算（`estimated_continuous_iq_bytes`）随之变化，量级为每 Run 数个样点。
2. `row_start_sample` 相对 4.1 整体平移（左端修复带来的 +1）。**绝对采样时刻不变**：回波生成按 $\text{adc\_start}+\text{global\_q}/f_s$ 还原时刻，并以 Run 内唯一全局索引为计算基准。
3. 若单站收发切换约束把开窗时刻推迟（$t_{\mathrm{on}}=\max\big(t_{\mathrm{ready}},\ \min_i t_{\mathrm{rx},i}-n_{\mathrm{pre}}/f_s\big)$），首行仍可能被截短；此时「前置纯噪声保护窗受切换时间限制而缩短」才是真实原因，该警告保留。
4. 已生成的 `observation_info.npz` / `echo.npz` 与新计划不可按样点逐位比较，需重跑这两个阶段。这是迁移成本，不是语义副作用：观测计划、echo 生成器与反演在同一次实验内共用同一套半开约定，结果自洽。

## 7. 与实测流程的对应

保存行锚定在质心上，并不要求事先知道真实回波时刻。真实系统中「质心时刻」由**发射触发时刻加上预测的双程时延**给出，即接收机的距离门延迟设定；预测偏差表现为回波在快时间轴上平移（距离迁移），不会造成数据丢失。4.1 的两端声明都需要窗外的样点或放弃末格，是硬件不易直接产生的表示；4.2 让程控窗与行格式一致。

echo 模块自己的独立计划脚本 `echo/scripts/make_simple_chirp_plan.py` 一直采用同一约定（`adc_stop = adc_start + (row_start[-1] + fast_count)/fs`，且 `row_valid` 全为真），本修改使观测解算与它统一。

## 8. 对其他语义的影响

- `fast_sample_count`：**比无补偿时最多增加 1 格**（§5 的 0.5 点栅格补偿）。这是行宽增量 $\lceil b+0.5\rceil-\lceil b\rceil\in\{0,1\}$，触发条件是 `frac((T_post+max_i W_i)·f_s) = 0 或 > 0.5`；`frac ∈ (0, 0.5]` 时行宽不变。默认点目标夹具 `after_s·fs = 150.0`（frac=0）→ 行宽 251 → 252；mesh 夹具 `after_s·fs = 100.005`（frac≈0.005）→ 保持 153。它与窗尾推迟量 $\delta$ 不是同一个量：恒定 $S_i$ 时 $\delta\in\{1,2\}$。
- `window_overlap` / `signal_echo_overlap`：判据公式不变。`window_overlap` 只由 $s_i$ 与 $M$ 决定（`starts[i+1] < starts[i] + fast_count`），与 $Q$ 无关；但 $M$ 是该判据的输入，行宽 +1 会把“行宽恰好等于行距”的配置翻成重叠。`signal_echo_overlap` 仍表示相邻脉冲物理回波支持区间相交。若 $T_{\mathrm{pre}}+T_{\mathrm{post}}+T_{\mathrm{pulse}}+2D_{\mathrm{extent}}/c\ge\mathrm{PRT}$，相邻行仍会共享 ADC 整数索引。
- 亚样点字段：`row_fast_time_offset_s`、`centroid_fractional_offset_s` 语义不变。
- echo 侧：`valid = sample_times < adc_stop` 不变；由于 $Q$ 变大，被计入的连续样点每 Run 增加 $\delta$ 个。

## 9. 验收

```powershell
# 观测解算（真实 mesh 配置）
python observation\solve_observation_info.py `
  --config runs\chirp_mesh_target_test\configs\observation.generated.json `
  --output runs\chirp_mesh_target_test\observation_info.npz
# 期望：fast_sample_count 153、q_off = 末格索引 + 1 = 299903、
#       每行有效列恒为 153、window_overlap = 0、metadata warnings 为空

# 端到端（点目标夹具，快速）
python pipeline.py --config configs\chirp_point_target_test.json
# 期望：echo 摘要里「有效样点数」= 8 × 252 = 2016（仅修末列时为 2008，修复前为 2007）

# 回归
python -m pytest -q observation/tests/test_planning.py observation/tests/test_planning_regressions.py
```

改动前的实现可以按版本重建，用于逐位对照（不需要保留旧代码）：

```powershell
# 取改动前的 planning.py（observation 子仓库的 HEAD 版本）到临时目录后按普通模块导入
git -C observation show HEAD:src/planning.py > <临时目录>\planning_old.py
```

对抗审查留下的一次性 A/B 脚本放在 `runs\_adv2_verify.py`（`runs/` 被 git 忽略，**不是** `tests/` 里的测试，不被 pytest 收集，也不被任何代码导入）：它用上面这条命令还原旧模块，再对同一批输入比较旧/新实现的窗长与 `row_valid`。它的结论已由下面两条仓库内测试固定，因此该脚本只是本地证据，可随时删除。

守住该行为的断言：

| 测试 | 锁定 |
|---|---|
| `test_adc_window_covers_last_row_and_stops_on_the_sample_grid` | $Q=\max_i s_i+M$；有效格时刻严格早于 $t_{\mathrm{off}}$；末格有效 |
| `test_reception_window_keeps_every_row_fully_valid` | 每行有效列数恒为 $M$（8 脉冲 / 51 格的算例） |
| `test_reception_window_covers_echo_and_post_guard` | 前置保护 $\ge T_{\mathrm{pre}}$；末格时刻 $\ge\max_i(t_{\mathrm{rx},i}+W_i)+T_{\mathrm{post}}$ |
