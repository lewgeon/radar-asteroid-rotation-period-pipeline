# 周期反演第一批：共同截距与搜索诊断

日期：2026-10-11。范围是 Chirp 周期搜索的基线、预期失败分类和实际处理路径导出。生产搜索保留原始特征时间戳，不按 Run 聚合；未修改波形生成、特征定义、CPI 相干边界、谐波默认阶数、候选别称或跨特征共识算法。本文件记录本次最终实现和验证，不把此前工作区改动归为本轮成果。

## 1. 问题与最终行为

旧生产路径将 `run_id` 或 CPI `coherence_id` 传入多谐波搜索，每组生成一条自由截距。每 Run 一个观测时，单谐波参数数为观测数加二，无法搜索；短 Run 内的慢周期变化很小，自由截距会吸收主要跨 Run 调制。本项目单 Run 发射时长受光行时约束，不能以 CPI 能形成作为启用逐组截距的依据。

`inversion/src/inversion.py::_estimate_chirp_rotation` 的逐脉冲 fallback 和 CPI 两条路径均省略 `groups`，底层搜索只使用一个共同截距。保留各自原始脉冲时刻／CPI 帧时刻，搜索内部排序仅同步重排时刻、值和权重。逐脉冲特征继续使用此前交付的完整原生相关输出。Run／相干组仍限制 CPI 的构造，并用于追溯；底层显式分组接口保留作为研究对照，不进入生产配置。

共同截距的适用前提是跨 Run 标量参考与标定一致。真实独立 Run 偏置或增益需要独立校准或受约束模型；本次不宣称这些条件下周期准确，也不认为相位不相干自动意味着标量存在加性偏置。

本次没有采用 9 月 29 日旧计划的 Run 聚合、经验阈值自动切换或 CPI 豁免。当前算法正文与旧计划状态已同步。

## 2. 失败分类与诊断契约

`PeriodSearchUnavailable` 是 `ValueError` 子类，携带 `reason` 和 `diagnostics`。只捕获这类预期数据限制，未知配置、无效搜索区间、非整数谐波／网格或数组形状错误继续传播。

| reason | 条件 |
|---|---|
| `insufficient_samples` | 有效点数不足；共同截距、H=1 至少六点，保留三个残差自由度 |
| `constant_feature` | 足够有效样本但特征严格恒定 |
| `degenerate_time_axis` | 不同有效时刻数不大于 2H+1，重复时刻不能制造周期信息 |
| `no_baseline_variation` | 特征在基线扣除后没有变化；显式分组时各组内部恒定也明确拒绝 |
| `rank_deficient_design` | 整个频率网格的周期设计矩阵均秩退化 |
| `no_estimable_features` | 所有特征均被跳过，异常携带各项真实原因与完整路径诊断 |

非有限时刻、特征和权重及非正权重被排除；有效、排除与输入点数分别记录。先作统一特征和权重缩放再平方，避免极大／极小尺度造成上溢或下溢。候选拟合检查矩阵秩，局部退化格点记 NaN 且不参与峰选择。参数计数和上述检查只针对回归可估计性，不代表相关样本的统计独立自由度。

`InversionResult.search_diagnostics` 包含实际 `processing_path`（`pulse_fallback`／`cpi`）、`baseline_model=shared_constant`、`aggregation=none`、时间轴角色、输入脉冲数、Run 数、特征观测数、权重来源与逐特征状态。每项搜索诊断另含有效／排除样本数、参数数、基线数、谐波阶数与不同有效时刻数；完成网格计算的特征另含秩退化格点数，提前跳过的特征不携带该字段。

CLI 将完整路径诊断写入 `best_summary.json` 及 `period_observables.npz` 的元数据，`summary.json` 的每项结果保留对应搜索诊断。部分特征跳过时通过既有可读警告协议输出原因；全部失败时不再谎报“特征均为常量”。

仅更正显著性报告语义：新 `significance_status=not_evaluated` 表示尚未校准，GUI 协议摘要显示“未评估”；兼容的 `significant=false` 与 FAP=null 保留。本次没有新增显著性校准。

## 3. 当前保存回波的结果

本次重跑使用 `runs/paras_for_70m_3h/echo/echo.npz` 和同作业 `configs/inversion.generated.json`。2000 个脉冲、2000 个 Run；散射时刻跨度约 33735.378073 s。实际搜索范围为 1800～14400 s、4000 个频率格点、H=1、CPI=16 s、PRF=10 Hz。每 Run 只有一个脉冲，无法形成需要 160 个脉冲的 CPI，因此实际路径为逐脉冲 fallback。每项特征有效点数均为 2000，共同基线参数数为 3，排除点数与秩退化格点数均为 0。

同一保存特征显式传旧分组标签时，三项均因 2000 点／2002 参数而拒绝；这是旧基线模型的可复现对照，不是运行旧版完整 CLI 所得的另一份产物。

| 特征 | 第一候选周期 / s | 回归改善得分 |
|---|---:|---:|
| 总功率 | 5406.235776 | 0.527276110 |
| 距离质心 | 5404.493480 | 0.911967465 |
| 中央 90% 能量宽度 | 5420.226405 | 0.590867254 |

沿用现有共识规则得到调制周期 5406.235776 s，相对已知对称模型的 5400 s 半周期偏差约 0.11548%。二倍周期 10812.471551 s 仍只是别称。输出中的 `relative_error` 继续按完整真周期 10800 s 计算，约 49.94226%；本轮没有改变这个旧字段的定义。三特征来源相同，支撑数不等于三份独立统计证据。结果只证明这份理想补偿、现有散射模型输入恢复了可搜索性，不能宣称完整自转周期已辨明或误检率已验收。

最终结果位于 `runs/paras_for_70m_3h/inversion_batch1_20261011_final/`。此前首次运行的 `inversion_batch1_20261011/` 是边界检查及报告语义修正前的中间产物；以 `_final` 为准。原回波与旧实验输出没有覆盖。

## 4. 输入与源码冻结标识

测量记录时间为 2026-10-11 09:45:49 +08:00。以下 SHA-256 对应本次最终源码和实际输入；工作区含其他既有改动，不能用当前 Git HEAD 替代工作区代码版本。

反演子仓库 HEAD 为 `079291a38b8496b593f68685bba4a136decb2ce5`；本轮直接依赖的 `radar_signal.py` 含此前未提交修改，因此另列工作区哈希，`dataset.py` 也单独锚定。运行环境为 Conda `pytorch`，Python 3.9.23、NumPy 1.24.3、SciPy 1.13.1。

| 文件 | SHA-256 |
|---|---|
| `runs/paras_for_70m_3h/echo/echo.npz` | `add62990c10ab7c4d74f5e2e5d50611cd9201d967399b3b2ed26ee195ee6ba3a` |
| `runs/paras_for_70m_3h/configs/inversion.generated.json` | `40128460853bf02107bd691a4971c6157e1db7264e42480809089c852a38f970` |
| `inversion/src/inversion.py` | `c67bc4a4075b9f745a3e97f2c8dce486d03732fb77761bd2160b63ff56f33c9e` |
| `inversion/scripts/estimate_period.py` | `da900d95058da807446f53a57cdc2c7e365d557e2b9459db214d56fc1351fe0c` |
| `inversion/src/radar_signal.py` | `983fc0dae821dba77b499880631099c6537f291b7152b26e257c30d37f5c445e` |
| `inversion/src/dataset.py` | `7000b7892aabe99a14e0580e19b45b0fdafc37f85405eea20e26ea702301b18a` |

## 5. 合成输入扫描

同会话使用固定种子 19、60 个随机 Run 起点（0～1800 s）、真调制周期 300 s、搜索范围 200～500 s、240 个频率格点、H=1。基准信号为单位振幅余弦；多脉冲 Run 内时刻均匀铺在指定首末跨度上。残差为标准差 sigma 的独立高斯实现，无真实 Run 标定偏置。此扫描比较同一输入的共同截距与显式旧分组模型，不给出通用失效门槛或多次实验恢复率。

| 每 Run 脉冲数 | 首末跨度 / s | sigma | 共同截距周期 / s | 分组截距周期 / s |
|---:|---:|---:|---:|---:|
| 1 | 0 | 0 | 300.000000 | 样本／参数不足 |
| 1 | 0 | 0.12 | 300.444839 | 样本／参数不足 |
| 5 | 0.4 | 0 | 300.000000 | 300.000000 |
| 5 | 0.4 | 0.12 | 299.913879 | 219.373401 |
| 5 | 20 | 0 | 300.000000 | 300.000000 |
| 5 | 20 | 0.12 | 299.910028 | 299.494246 |
| 5 | 100 | 0 | 300.000000 | 300.000000 |
| 5 | 100 | 0.12 | 299.829890 | 299.725745 |

0.4 s 带噪声输入下共同截距得分为 0.972457487，旧分组得分为 0.018125268；测试明确断言两者差异，避免夹具退化。无噪声短 Run 的旧模型也能恢复周期，因此不能把短 Run 的统计失效说成所有条件下数学上必然失败。

该表可将下列 Python 内容保存为仓库 `tmp/rebuild_batch1_scan.py` 后，以 `conda run -n pytorch python tmp/rebuild_batch1_scan.py` 重建；在仓库根运行，必要时将根路径加入导入路径。

```python
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path.cwd()))
from inversion.src.inversion import multi_harmonic_lomb_scargle, PeriodSearchUnavailable
for count, span in ((1, 0.), (5, .4), (5, 20.), (5, 100.)):
    for sigma in (0., .12):
        rng = np.random.default_rng(19)
        starts = np.sort(rng.uniform(0., 1800., 60))
        t = (starts[:, None] + np.linspace(0., span, count)).ravel()
        y = np.cos(2*np.pi*t/300.) + sigma*rng.normal(size=len(t))
        for label, groups in (("shared", None), ("grouped", np.repeat(np.arange(60), count))):
            try:
                r = multi_harmonic_lomb_scargle(t, y, 200., 500., 240, groups=groups)
                print(count, span, sigma, label, r.best_period_s, r.candidates[0].score)
            except PeriodSearchUnavailable as exc:
                print(count, span, sigma, label, exc.reason)
```

## 6. 验收与独立审查

最终组合运行反演全测试及根入口、产物契约、特征预览消费测试：66 项通过、3 项跳过。CPI、fallback、CW 均由实际 CLI 子进程验证。当前版本 Markdown 公式围栏检查通过；冻结 4.1／4.2 的 39 处历史违规只汇总。常规合并 pytest 收集最初遇到多个 `tests` 包重名，使用 `--import-mode=importlib` 后完成，不将收集失败当作通过。

全新上下文对抗性审查发现极端特征平方溢出／下溢、少量重复时刻饱和拟合，以及显式分组纯偏置被舍入残差误认为变化；均修复并补充可复现回归。审查最终复核 23 项相关测试，无阻塞问题。共同截距对真实未知 Run 偏置的敏感性、重叠 CPI 的统计相关性、显著性和论文级盲搜性能明确留待后续。本轮无性能加速声称。

```powershell
conda activate pytorch
python -m pytest -q inversion/tests tests/test_inversion_entry.py tests/test_artifact_contract.py tests/test_inversion_feature_preview.py --import-mode=importlib -p no:cacheprovider
python scripts/check_doc_math.py
python inversion/scripts/estimate_period.py --echo runs/paras_for_70m_3h/echo/echo.npz --config runs/paras_for_70m_3h/configs/inversion.generated.json --output runs/paras_for_70m_3h/inversion_batch1_reproduction
```

重建时使用一个新的输出目录，避免覆盖旧产物；核对输入和配置 SHA-256 后再比较结果。一次性探针和 JSON 放仓库忽略的 `tmp/`，因为推荐的 E 盘缓存不在本次可写范围；该目录不是冻结证据来源，主要计算可按上面命令和源码重建。

<a id="legacy-proposal"></a>

## 旧截距方案（2026-09-29，未全部采用）

以下保存旧阶段的独立诊断与方案，不表示这些建议全部实施；共同截距现已交付，Run聚合、CPI逐组截距与自动阈值未采用。

> 状态：历史方案，2026-10-11 已由第一批实现替代。两条 Chirp 路径均采用共同截距，保留原始特征时刻，不按 Run 聚合；不采用本计划的自动阈值或 CPI 逐组截距豁免。以下保留当时诊断和设想，不作为当前实施要求。当前行为与证据见 [共同截距修改记录](PERIOD_INVERSION_BASELINE.md)。

### 1. 问题

配置 `configs/paras_for_70m_600s.json` 的真自转周期为 600 s，反演实际输出 208.63 s，相对误差 65%。

回波数据本身正常：把 500 个逐脉冲观测量按 Run 取平均成 100 个数后，单频正弦在 299.669 s 处能解释 0.8379（`total_power`）与 0.5398（压缩峰值）的起伏，即半周期 300 s 的调制清晰存在。

### 2. 根因

`inversion/src/inversion.py` 的 chirp 兜底路径调用 `multi_harmonic_lomb_scargle(..., groups=run_id)`，其设计矩阵含**每个 Run 一条自由截距**。当 Run 内目标几乎不转动时，该 Run 内各脉冲的观测量近似相等，截距项与"给每个观测配一个专属参数"在数值上无法区分，于是把周期调制本身吸收掉。

本次观测的采样量：

| 量 | 数值 | 说明 |
|---|---|---|
| Run 发射段跨度 $S_{\mathrm{tx}}$ | $0.400000\ \mathrm{s}$ | 首末脉冲之间的时间 |
| 真自转周期 $P_0$ | $600\ \mathrm{s}$ | 数据里的周期是半周期 $300\ \mathrm{s}$ |
| $S_{\mathrm{tx}}/P_0$ | $0.0667\%$（折合自转 $0.2400^\circ$）| 一次 Run 内目标转过的角度 |
| $A$ | $2208.53$ | Run 级 `total_power` 均值的标准差 |
| $\sigma$ | $1177.43$ | 逐脉冲噪声（方差分解，见 A5.5）|
| $\Delta_{\mathrm{in}}/\sigma$ | $\approx 0.0025$ | 判定量，代入 $P=300\ \mathrm{s}$，见式 (A5.6) |

**判定量是 $\Delta_{\mathrm{in}}(P)/\sigma$，不是 $S_{\mathrm{tx}}/P_0$**：Run 内信号变化约 $A\,(S_{\mathrm{tx}}/P)$，它必须能与噪声 $\sigma$ 分辨，周期才可能被检出。判断"该不该启用逐组截距"时代入 $P_{\max}$（区间内最长的候选周期给出最小的 $\Delta_{\mathrm{in}}$）。

判决性对照（同一份数据、同一观测量、同一条 200–2000 s 网格）：

| 处理方式 | 观测点数 / 自由参数 | 得分最大值位置 | 299.669 s 处得分 |
|---|---|---|---|
| 500 点 + 100 条自由截距（现状）| 500 / 102 | 409.20 s（0.03882）| 0.00397 |
| 100 个分箱平均值 + 1 条正弦 | 100 / 3 | **299.80 s（0.83959）** | 0.83635 |
| 500 点 + 1 条正弦（无截距）| 500 / 3 | 299.80 s（0.65388）| 0.65137 |

**本次失败的成因是 Run 内信号变化与噪声之比过低，不是 Run 间隔取了一个特殊值。** 两个轴的作用不同，须分开说（A5.4 联合扫描表）：

- **Run 内跨度是第一位**：跨度 $0.4\ \mathrm{s}$ 时任何间隔都是 0/6 命中；$10\ \mathrm{s}$ 时最好也只有 1/6（间隔 $144.2\ \mathrm{s}$）。本观测是 $0.4\ \mathrm{s}$。
- **间隔是次要条件**：跨度足够后（$30$、$60\ \mathrm{s}$）间隔才开始起作用，需给出约 2–4 个采样点/半周期（$75$、$37.5\ \mathrm{s}$ 处 $6/6$），过疏（$\le144\ \mathrm{s}$）或过密（$18.8\ \mathrm{s}$ 时峰跑到 $600\ \mathrm{s}$）都会变差。

**因此不能写成"间隔无关紧要"**，也不能写成"间隔是主因"。§3.1 的判定量只覆盖第一位因素；间隔是否足够属于观测计划的约束，不在本计划的模型改动范围内，但应在 §3.4 的输出里一并给出每半周期采样点数。

判定量（`docs/4.3/INVERSION_ALGORITHM.md` 式 A5.6）：

$$
\frac{\Delta_{\mathrm{in}}(P)}{\sigma} \approx \frac{A}{\sigma}\cdot\frac{S_{\mathrm{tx}}}{P}
$$

$A$ 为 Run 之间的信号幅度，$\sigma$ 为逐脉冲噪声，$S_{\mathrm{tx}}$ 为一次 Run 的发射段跨度，$P$ 为候选周期。带噪声的恢复实验（A5.4 表）给出本组参数下的经验分界：该比值 $0.1$ 以下不可靠、$0.25$ 以上稳定。本次观测 $A/\sigma = 1.876$、$S_{\mathrm{tx}}/P = 0.4/300$，得 $0.0025$，比"不可靠"还低一个半数量级。

> 早期版本曾用一组**无噪声**合成实验定出"Run 内相位跨度需占周期 3%–10%"的门槛。该实验不能用，但原因不是模型饱和（$500$ 个观测点对 $102$ 个参数还有 $398$ 个残差自由度）——在无噪声数据上真周期在每个跨度上都是得分最高的周期，**检测根本不会失败，因此量不出失效边界**。表上约 $0.45\%$ 的差距是 $0.5\ \mathrm{s}$ 步长网格的相邻格（$299.5$ 或 $300.5\ \mathrm{s}$），不是远处周期也拟合得差不多；Gram 表里 $200\ \mathrm{s}$、$500\ \mathrm{s}$ 的得分约为 $10^{-4}$。加噪声后截距模型失败，是因为 Run 内信号远低于噪声。更正过程与实测见 A5.4。**不要使用那组门槛。**

### 3. 改动清单

#### 3.1 模型选择：只对逐脉冲兜底路径按判定量决定是否启用逐组截距

位置：`inversion/src/inversion.py` 的 `_estimate_chirp_rotation`。

现行行为：兜底路径与 CPI 路径都传 `groups`（分别为 `run_id` 与 `coherence_id`），即始终启用逐组截距。

目标行为：**判定量只作用于逐脉冲兜底路径；CPI 路径保持现状。**

理由：CPI 路径的一个 Run 内部已经形成多帧，逐组截距在那里只扣除整段电平，帧与帧之间的起伏仍然保留在搜索里。若把同一个开关也套到 CPI 路径上，长 Run 方案会被抵消——按 $P_{\max}=7200\ \mathrm{s}$、$A/\sigma\approx1.9$，即使把 Run 加到单站上限附近的 $100\ \mathrm{s}$，判定量也只有

$$
\frac{\Delta_{\mathrm{in}}}{\sigma} \approx 1.9\times\frac{100}{7200} = 0.026
$$

低于 $0.1$，截距会被关掉，CPI 的多帧还会被收成每 Run 一个点。这与"加长 Run 以启用 CPI"的意图相反。

兜底路径的目标行为：

1. 估计判定量

$$
\frac{\Delta_{\mathrm{in}}(P_{\max})}{\sigma} \approx \frac{A}{\sigma}\cdot\frac{S_{\mathrm{tx}}}{P_{\max}}
$$

$A$ 取该特征在 Run 级聚合后的标准差，$\sigma$ 取 Run 内残差的标准差，$S_{\mathrm{tx}}$ 取组内首末脉冲时刻之差，$P_{\max}$ 取 `period_max_s`。
2. 当该比值低于检出阈值时，**不传 `groups`**（或传全同标签，使截距退化为一个全局常数），改用 §3.2 的聚合观测量，并在输出里写明走了哪一行；
3. 否则保持现状。

**参照周期必须用 $P_{\max}$ 而不是 $P_{\min}$。** 一套截距要对整个搜索区间共用，最容易被吃掉的是最长候选周期。搜索区间 $200$–$7200\ \mathrm{s}$、$S_{\mathrm{tx}}=20\ \mathrm{s}$ 时：用 $P_{\min}$ 判会得到 $10\%$ 而保留截距，但待测周期若为 $600\ \mathrm{s}$，Run 内跨度只有 $3.3\%$，信号仍会被吸收。

阈值应作为具名常量写在代码里并附注释指向 A5.4，首版取 $0.1$（实验里"不可靠"的上界）。该值出自一组特定参数（100 个 Run、每 Run 5 个脉冲、8 次实现），随噪声与采样点数变化，因此必须把 $A/\sigma$、$S_{\mathrm{tx}}/P_{\max}$ 与实际判定结果一并写入输出，便于用真实数据校准。

**实施次序**：本计划的可交付部分只有 §3.2（兜底路径按 Run 加权聚合后用单一全局常数搜索），它单独就能让本次配置输出 $299.8\ \mathrm{s}$。§3.1 的自动开关需等阈值在真实数据上校准后再加；在此之前，兜底路径直接采用 §3.2 的行为即可。

#### 3.2 观测量聚合：按相干组把逐脉冲特征合成为每组一个点

位置：`inversion/src/inversion.py` 兜底路径（`range_features` 之后）。

现行行为：把 500 个逐脉冲特征直接送进搜索。

目标行为：在"不启用逐组截距"的分支下，先按组把特征聚合成每组一个点：

$$
\bar y_g = \frac{\sum_{k\in g} w_k y_k}{\sum_{k\in g} w_k},\qquad
\bar t_g = \frac{\sum_{k\in g} w_k t_k}{\sum_{k\in g} w_k},\qquad
\bar w_g = \sum_{k\in g} w_k
$$

$w_k$ 沿用现行的逐脉冲有效样点占比（§5.2 式 (7) 的退化形式）。聚合后样本数由 $N_p$ 降为 $G$，需同时检查 §5.4 式 (11) 的自由度条件仍然满足（$G \ge \max(5,\ 2H_\omega+3)$）。

**聚合之后不得再给每个 Run 一条截距**：那样是 $G$ 个观测对 $2H_\omega+G$ 个参数，自由度检查直接失败。

实测依据（A5.3 表）：按 Run 聚合后只加 2 个参数，输出 $299.80\ \mathrm{s}$，与半周期 $300\ \mathrm{s}$ 相差 $0.067\%$，得分 $0.83959$。

**采样限度（必须写入文档与输出）**：收成 1 点/ Run 之后，慢时间序列的可分辨最短周期约为**两倍 Run 间隔**。本次 Run 间隔 $144.233\ \mathrm{s}$，故可分辨下限约

$$
2 \times 144.233\ \mathrm{s} = 288.467\ \mathrm{s}
$$

而配置里的 `period_min_s = 200\ \mathrm{s}$ 低于该采样限，即搜索区间下段 $200$–$288\ \mathrm{s}$ 已经欠采样，落在那里的大峰不可信。实测 $299.80\ \mathrm{s}$ 恰在可分辨的一侧。校验时应在本条不满足时给出提示，或建议把 `period_min_s` 提到采样限之上。

#### 3.3 配置校验：CPI 时长不得超过一组的脉冲数

位置：`inversion/src/dataset.py` 的 `normalize_inversion_policy`。

现行行为：只检查 `cpi_duration_s` 是否存在。

目标行为：chirp 布局下增加

$$
\texttt{cpi\_duration\_s}\times\mathrm{PRF} \le \text{每个相干分组的脉冲数}
$$

分组脉冲数无法在配置层得知（取决于观测计划），因此实现方式二选一：

- 在 `normalize_inversion_policy` 只做"必须为正"的基础检查，把跨层检查移到反演入口 `_estimate_chirp_rotation`：那里能读到 `echo.coherence_id`，可算出实际分组脉冲数；
- 或在校验阶段只发出警告，列出 `cpi_duration_s × prf_hz` 与实际分组脉冲数，说明本次将走兜底路径。

推荐后者（警告而非硬失败），因为兜底路径在多数现有夹具里是正常工况。

#### 3.4 输出与日志：说明实际使用的观测量层级

位置：`inversion/src/inversion.py` 的 `except ValueError` 分支与 `InversionResult`。

现行行为：CPI 建不起来时静默降级，`summary.json` 只记录特征名。

目标行为：在 `metadata` 或 `summary` 中新增字段，说明本次实际走的是哪条路径（CPI / 逐脉冲兜底）、是否启用了逐组截距、聚合前后的样本数、判定量 $A/\sigma$ 与 $S_{\mathrm{tx}}/P_{\max}$ 及其乘积，以及每半周期采样点数（$P_{\max}$ 对应值），便于事后判断是"信号被截距吸收"还是"间隔采样不足"。GUI 日志应能显示这一行。

#### 3.5 跨特征共识：本次不改（并说明理由）

位置：`inversion/scripts/estimate_period.py` 的 `_cross_feature_consensus`。

**结论：这一层不是本次故障的成因，改它救不回来，因此不在本计划内。**

实测（A5.7）：胜出簇由**两个**特征支撑——`range_centroid`（$208.027\ \mathrm{s}$）与 `total_power`（$209.230\ \mathrm{s}$），相对离散度 $0.002883$。`range_width` 的近邻是 $219.650\ \mathrm{s}$，未落进该簇的 $5\%$ 容差，因此原文"三个噪声峰凑票"的说法不成立。

更关键的是：在含逐组截距的模型下，真周期连前 5 名候选都进不去（A5.5），共识层没有正确候选可投。把候选强度纳入排序只能减少"噪声峰凑票"，不能恢复被截距吸收掉的峰。去掉截距后真周期直接排到第 1、第 2（A5.5），共识层自然选中它。

排序键的改进可作为独立的稳健性议题，但不属于本次修复。

### 4. 验收标准

本计划的可交付部分只有 §3.2（兜底路径按 Run 加权聚合，搜索只用单一全局常数）。验收按此写：

1. **兜底路径通路验证**：在 `runs/chirp_mesh_target_test/echo/echo.npz` 上，改后 `total_power` 与 `range_centroid` 的候选首位应为半周期附近（实测 $299.85$、$300.04\ \mathrm{s}$），且**不差于**"先把逐脉冲特征按 Run 平均成 100 点、再用普通单频拟合"的结果（后者得 $0.83635$）。**不要把 $600\ \mathrm{s}$ 写成必须输出的周期**：椭球转 $180^\circ$ 后投影相同，数据里的周期是 $300\ \mathrm{s}$；现有代码把估计值的两倍记在 `double_period_s`，那只是候选别名。要求输出 $600\ \mathrm{s}$ 等于事先假定目标具有这种对称性——不对称形体的真周期就是测到的那个周期。
2. **短 Run 配置应当变化（不是"不变差"）**：`configs/paras_for_70m.json` 同样是零点几秒的 Run、自转周期更长（$7200\ \mathrm{s}$），现行截距模型下结果本来就不可靠。实测该数据按 Run 聚合后普通 LS 最强峰为 $3665.1\ \mathrm{s}$、得分 $0.8987$（$P(3600\ \mathrm{s})=0.8846$、$P(7200\ \mathrm{s})=0.0018$）。改后应出现这个半周期附近的峰，而不是维持原值。**不得把"既有结果不变"作为验收条件。**
3. **采样限度检查**：聚合后慢时间序列的可分辨下限约为两倍 Run 间隔（本次 $288.5\ \mathrm{s}$）。应在 $2\times$间隔 $>$ `period_min_s` 时给出提示，或建议抬高 `period_min_s`。
4. **单元测试**：为 §3.2 的加权聚合加一个可区分的测试（同一输入下断言输出样本数由 $N_p$ 变为 $G$、且搜索不再传逐组标签）。
5. **文档一致**：`docs/4.3/INVERSION_ALGORITHM.md` 的 §5.2、§5.4 与 A5 描述与实现一致；§7 的"当前实现的能力边界"表补上本次结论。

§3.1 的自动阈值与 §3.4 的输出字段在阈值校准后再纳入验收（见 §3.1 实施次序）。

### 5. 风险与权衡

1. **去掉逐组截距会重新引入"台阶被当成周期"的风险**。截距项原本的作用是吸收各 Run 的整体标定差。改成按组平均后，台阶变成每组的均值本身，仍可能被慢变周期成分拟合。缓解方式：直接采用 §3.2 的聚合行为时，要求观测跨度覆盖至少 2–3 个最长候选周期；等 §3.1 的阈值校准后再做自动分流。
2. **聚合降低样本数**。$N_p\to G$ 后周期图分辨率下降，可分辨下限升到约两倍 Run 间隔。本次 $G=100$、每半周期约 2.08 个点，属勉强可用；若 $G$ 更小（例如长 Run 导致 Run 数降到 60），需评估是否改用 §4.1 的 CPI 路径。
3. **长 Run 是一个真实的可选方案，但必须在 §3.1 里豁免 CPI 路径**。本次 $S_{\mathrm{tx}}$ 上限为 $119.6\ \mathrm{s}$，配置只用了 $0.5\ \mathrm{s}$。把 Run 加长到约 $100\ \mathrm{s}$ 可让 Run 内相位跨度达到 $600\ \mathrm{s}$ 周期的 $16.7\%$，从而让 §4.1 的 CPI 路径可用；代价是同一调度窗口内 Run 数减少。若把 §3.1 的开关也套到 CPI 路径，长 Run 方案会被抵消（见 §3.1），因此该豁免是必须的。
4. **CW 路径不受影响**：`inversion.py` 的 CW 分支用 STFT 特征做单谐波 Lomb–Scargle，不含逐组截距。本计划只改 chirp 分支。
5. **判定阈值是经验值且依赖 $A/\sigma$**。首版取 $0.1$，出自 A5.4 的带噪声实验（100 个 Run、每 Run 5 个脉冲、8 次实现）。真实数据的噪声结构不同会移动该阈值。注意无噪声数据**不能**用来校准它：无噪声下真周期在每个跨度上都是峰，检测不失败（A5.4 更正一）。
6. **重叠保存行不在本计划范围**。按 Run 平均不会去掉"同一全局 ADC 样点进入多行"的重复计权，该项继续留在 `OPEN_ISSUES.md` 第 2 节。

### 6. 复现与证据

```powershell
python tmp\_q70_appendix_numbers.py   # 本文件第 2 节的主要数值、A5.3 对照表
python tmp\_q70_appendix_extra.py     # A5.2 单频解释比例、A5.4 相位步进
python tmp\_q70_within_run.py         # A5.3 组内散度分解与相关性
python tmp\_q70_verify_critique.py    # A5.4 标度错误证据（|p|^2 vs Gram vs 显式）
python tmp\_q70_noiseless_trusted.py  # A5.4 更正一：无噪声对照，两算法互校
python tmp\_q70_decisive.py           # A5.4 两算法在整条网格上的一致性
python tmp\_q70_noisy_recovery.py     # A5.4 判定量与命中率（阈值来源）
python tmp\_q70_span_gap_sweep.py     # A5.4 Run 内跨度 × Run 间隔联合扫描
python tmp\_q70_gap_effect.py         # A5.4 固定跨度、只改间隔的对照
python tmp\_q70_verify_claims.py      # A5.5 候选表、A5.7 聚类复现
python tmp\_q70_binning_test.py       # 分箱 vs 每箱一个自由参数的判决性对照
python tmp\_q70_scheme.py             # 单站发射段上限与 CPI 所需驻留
python tmp\_q70_verify_critique2c.py  # 聚合后的采样下限、paras_for_70m 的预期结果
```

`tmp/_q70_resonance_test.py` 与 `tmp/_q70_verify_critique2b.py` 结论均已作废（前者定的阈值无效，后者有索引错误），保留仅供追溯。

原始产物：`runs/chirp_mesh_target_test/`（GUI 于 2026-09-28 生成）、`runs/_q600probe/`（本次诊断的中间产物与日志）。

<a id="protocol-5"></a>

## 事前协议：4.3 第一批周期反演验收

此段由原实验协议归入相应专题，记录当时设计及追加验证条件；不表示本次重新执行。

Chirp 的逐脉冲 fallback 与 CPI 搜索统一使用共同截距，保留原始特征时间戳，不按 Run 聚合。此模型适用于跨 Run 标量参考与标定一致的输入；任意未知 Run 偏置、增益及相关残差的统计校准仍需独立实验。底层显式分组接口仅用于研究对照，不是生产策略。

1. 单脉冲 Run：旧分组模型在非恒定输入上因自由度不足失败，新模型保留每个时刻并能搜索。
2. 短多脉冲 Run：带固定随机种子残差的合成周期盲搜恢复；夹具必须证明旧分组得分与共同截距得分不同。
3. CPI 每 Run 一帧：不跨 Run／相干组形成 CPI，搜索仍只拟合一个截距。
4. 用独立加权最小二乘核对整条频率网格；覆盖不规则、逆序时刻、非有限特征和零权重，检查实际有效点数。
5. 常量、样本不足、退化时刻和基线无变化分开报告；配置及形状错误必须传播，部分跳过与全部失败均保留逐特征原因。
6. CLI 的 CPI、fallback、CW 实际执行；`best_summary.json`、逐特征 `summary.json` 与 `period_observables.npz` 中的搜索诊断一致。未校准显著性显示“未评估”，兼容布尔字段不作为否定检出证据。
7. 用现有回波与作业生成配置重跑反演到新目录，冻结输入校验和与配置；结果只证明该输入恢复可搜索性，不构成论文级恢复率或误检率验收。

```powershell
conda activate pytorch
python -m unittest inversion.tests.test_shared_baseline inversion.tests.test_native_pulse_features inversion.tests.test_range_fwhm_cli inversion.tests.test_chirp_contracts inversion.tests.test_inversion inversion.tests.test_signal inversion.tests.test_range_energy_width inversion.tests.test_cw_echo_load
```

<a id="consensus-quality-20261016"></a>

## 2026-10-16 共识同票数排序修复

原问题：单特征的所有孤立候选都是1票、离散度0，原规则最后按周期升序选择18秒边界，即使同次生产搜索的20秒主峰拟合分数接近1、边界仅约0.00027。两个特征时，一个完全重合的弱边界簇也可压过略有差异的高分主峰簇。修复前先运行`python -m pytest inversion/tests/test_period_consensus.py -q`，实际得到2失败／2通过，分别复现单特征与双特征故障，不以“搜索不崩溃”代替回归条件。

修改仅在同支持特征数时增加平均拟合分数降序，之后仍按相对离散度及周期排序；簇内同特征只保留原排名最高候选，合成half／double不投票，5%聚类和中位数输出不变。分数由生产搜索按降序生成，Chirp表示相对基线的加权残差改善。所有CLI布局和整Run重采样调用相同`period_consensus.py`，结果新增`consensus_policy=feature_support_then_mean_fit_score_v2`；旧产物不被自动覆盖。`period_uncertainty.py`的method现明确写current_consensus，局部σ公式、数值精度、搜索域及最终不签发3σ的行为不变。

作用域：修复确定的同票数弱峰优先缺陷，单特征在生产排序候选契约下保留最高分。支持数仍是第一排序项，更多低分特征仍可能压过较少强特征；没有证明通道独立，没有把拟合分数当显著性，也没有解决真实作业的全部系统偏差。未增加默认截断或降低浮点精度。

同会话重新生成旧／新432对固定控制，正确波形200次RMSE由1.985314秒降至0.045914秒，接收端32次由1.977653秒降至0.022285秒；但正确波形“95%经验区间”仅86.5%覆盖，故仍不得称置信保证。真实500CPI／100Run快照共识仍5748.465058秒，100次重采样在基线±5%内仅30%，未提供单峰区间；这是修复不足以解决真实多特征冲突的负结果，未据此删除不利特征或按真值改算法。固定参数、全部逐次结果、旧基线和复现命令见[实验正文](../experiments/reports/2026-10-14_PERIOD_UNCERTAINTY_AND_FUSION.md#consensus-quality-20261016)。

本次验收均在Conda pytorch环境运行：`python -m pytest inversion/tests -q`为128通过／3跳过，`python -m pytest tests -q`为295通过／1跳过，两套测试包分开执行，未累计为一次总数。真实CLI的CW、Chirp CPI、逐脉冲fallback均实际执行并检查策略和输出；GUI配置事件循环由相关既有测试覆盖，未做本轮人工视觉验收。全新上下文对抗审查独立执行13项小检查，并以inversion历史HEAD原函数核对旧算法、以有理数核验极端α概率预算；未发现限定声明内的阻断问题，指出基线哈希对象不明确后已补充文件说明。未改动观测与回波生成代码，未重跑其完整测试。

<a id="predictive-joint-20261016"></a>

## 2026-10-16 共同周期整 Run 留出评分

原问题：旧规则将候选簇的特征支持数放在拟合质量前面，只要弱通道的次级峰聚到一起，就可能压过较少通道的强主峰。此前同票数排序修复保留这一规则，没有解决弱通道多数票。此次新增 `inversion/src/joint_period.py::select_predictive_period`，在同一候选周期上重新拟合全部可用特征，用它们对未参加系数拟合的完整 Run 的预测改善选择共同周期。`period_selection=predictive_joint` 是新的 Chirp 选择路径，`legacy_consensus` 保留原 `_cross_feature_consensus` 以复现旧结果；每项特征的原搜索、候选和特征定义仍保留，不把多普勒两项按真值删掉。

### 计算契约与输出含义

共同搜索使用 `period_min_s`、`period_max_s`、原搜索频率网格、原有效样点权重、显式谐波阶数和可选相位补偿。它重算完整网格的共同目标，细化所有局部极大值及端点后排序，不仅比较各通道已有的前五峰。只收到 JSON 候选摘要、没有原网格的底层调用会明确记录使用重建的 4000 点等频率网格；生产调用传入完整 `PeriodEstimate`。共同评分目前在 CPU 上完成，`compute_device=cpu` 单独记录，不能因前面的逐特征网格使用 CUDA 就把共同评分说成 GPU 运算。

至少有 10 个正权重 Run 时，按各 Run 的有效观测时刻中位数排序，再轮流分到五折；同一 Run 的全部 CPI、重复抽样重数及所有通道始终属于同一折。每次用其余四折拟合波形系数，并预测留出折。原始观测不按 Run 平均，训练基线仅含共同常量。对第 $j$ 个通道，$V_k$ 表示第 $k$ 折留出观测，$w_i$ 是原有效权重，$y_{ij}$ 是特征，$\widehat y_{ij}^{(-k)}(T)$ 是其余四折在候选周期 $T$ 下拟合的波形，$\overline y_j^{(-k)}$ 是其余四折的加权均值；通道预测改善定义为

$$
Q_j(T)=1-\frac{\sum_k\sum_{i\in V_k}w_i\left[y_{ij}-\widehat y_{ij}^{(-k)}(T)\right]^2}{\sum_k\sum_{i\in V_k}w_i\left[y_{ij}-\overline y_j^{(-k)}\right]^2}.
$$

所有留出折的误差先求和，再作一次归一化，避免低方差折取得不成比例的权重。共同评分是可用、非重复通道 $Q_j(T)$ 的中位数；各通道的单位和幅值通过归一化消除，未将多普勒弱峰转成等权投票。留出折仍参与周期选择，所以这个分数并不是最终独立测试集上的性能，也不是似然、概率、FAP 或误差保证。新报告的 `support` 仅计共同周期处预测改善为正的通道数；共享周期拟合不定义旧投票的离散度，`relative_spread=null`，单通道最高峰相对共同周期的偏离另存为诊断。

有限样本、正权重、不同有效时刻和训练折秩检查按通道执行；样本不足、常量、数值精度内的纯线性趋势和训练折不可估计通道在搜索前明确排除，不能在某个候选上临时删除不利通道。纯趋势判定要求加权线性拟合残差范数与加权特征范数之比不超过 $10^{-12}$；这只是数值退化保护，不是一般趋势分离算法。没有剩余可辨识通道或整个共同网格秩退化时抛出 `JointPeriodUnavailable`，非法配置仍作为 `ValueError` 报错。

仿射复制检查仅适用于**有效样本掩码完全相同**的通道：标准化后同号或反号最大差不超过 $10^{-10}$ 才合并，诊断字段明确记录 `duplicate_policy=same_finite_mask_affine_within_1e-10`。不同缺失位置的复制、一般相关通道及同源 IQ 的共同偏差没有被消除，不得宣称自动获得独立证据。少于 10 个 Run 时明确回退为 `shared_fit_fallback`，使用全数据共同拟合改善，不冒称留出预测。

共同分数非正时状态为 `weak`；选中搜索边界、观测跨度不足两个候选周期或远处周期数值上同分时标记 `ambiguous`，保留候选与原因。最大谐波相邻网格相位步长过大时另作粗网格警告。这些状态是数据诊断，`candidate` 也不表示误检率已校准。多谐波阶数继续由配置指定；本次不按真值挑阶数，不把 H 增大作为默认精度改进。

### 固定控制、改善范围与负结果

同会话对 30 个预先固定种子、三档噪声尺度和两种目标／污染通道比例执行 180 组输入相同的旧规则／新规则配对。每组包含 40 个不规则 Run、每 Run 三个观测，目标周期由种子生成于 16～24 秒，强污染周期生成于 10～12 秒；搜索固定为 10～30 秒、240 点、H=1。信号含固定幅度 0.12 的二次谐波、Run 共同误差、通道独有 Run 误差、逐观测误差和约 3% 独立缺失。真值只进入生成器与最后误差评分，不进入周期范围、候选、特征选择或融合参数。

| 目标／污染通道 | 噪声尺度 | 次数 | 旧规则 RMSE(s) | 共同预测 RMSE(s) | 旧规则误差超过 5% | 共同预测误差超过 5% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3／2 | 0.03 | 30 | 5.52912 | 0.02215 | 18／30 | 0／30 |
| 3／2 | 0.20 | 30 | 5.72607 | 0.03882 | 16／30 | 0／30 |
| 3／2 | 0.60 | 30 | 6.14319 | 0.12537 | 16／30 | 0／30 |
| 2／3，负控制 | 0.03 | 30 | 7.60814 | 9.94469 | 26／30 | 30／30 |
| 2／3，负控制 | 0.20 | 30 | 8.14341 | 9.94417 | 27／30 | 30／30 |
| 2／3，负控制 | 0.60 | 30 | 8.95186 | 9.94314 | 29／30 | 30／30 |

前 90 组支持“多数非复制通道含目标调制、少数通道强冲突”的限定改善；后 90 组中，新规则稳定跟随污染多数，表现反而比旧规则更差。这说明重复性不能代替正确性，中位数没有能力自行判断多数周期是不是目标自转。生产配置没有保证多数通道正确，也没有认证特征独立，因此不能把该控制写成对任意形状、几何、噪声或缺失模式的通用精度保证。这些控制直接从合成特征开始，未重新生成面片与接收 IQ，不属于全链路物理校准，也没有测量 95%／99.73% 区间覆盖率。

逐次偏差与失败记录冻结在[180 组配对控制](data/2026-10-16_PREDICTIVE_PERIOD_CONTROLS.csv)，测量时间、协议、参数和源码哈希见[控制摘要](data/2026-10-16_PREDICTIVE_PERIOD_SUMMARY.json)。后续增加重复掩码契约、诊断字段和注释不改变这轮打分公式；冻结文件保留实际控制阶段的来源。较大的原始候选、逐折划分和真实快照重放记录在 `tmp/predictive_period_controls_20261016/result.json`，因为本次沙箱不允许写推荐的 E 盘缓存。耗时仅为运行记录，不构成性能提升声明。

复现时选择不存在的新目录；测试与控制入口如下。最终入口集成和真实作业结果由本日后续验收另行追加，不与历史测试通过数相加。

```powershell
conda activate pytorch
python -m unittest inversion.tests.test_joint_period inversion.tests.test_period_consensus -v
python scripts/experiment_predictive_period.py --trials 30 --grid 240 --observables runs/seperate_observation_2/inversion/period_observables.npz --output tmp/predictive_period_reproduction
python scripts/check_doc_math.py
```

### 2026-10-16 接手收尾验收

最终源码修复了联合评分把全特征缺失Run计入有效Run门槛的问题：9个具有正权可用特征的Run加1个全缺失Run仍为9，明确共同拟合回退。先执行新增回归得到1失败，再修复并验证与删除无效行的参照相等。Run有效性按参与独立搜索的特征有限值并集、有限时刻和正权共同确定，与bootstrap总体一致；不把缺失观测当成预测证据。

最终分开完整执行根tests与inversion/tests，分别304通过／1跳过和158通过／3跳过；日志为 `tmp/period_upgrade_20261016/final_root_tests_verified.log`、`final_inversion_tests_verified.log`。反演跳过项是已迁移到echo的三个历史测试，根跳过项为可选浏览器引擎。NumPy格式3.0兼容提示为非失败警告。根测试用仅本进程环境的safe.directory覆盖根与inversion两个仓库，没有修改用户全局Git配置。最初并行运行曾出现内存／页面文件不足和嵌套Git信任路径遗漏，失败日志保留，不计为通过；改为顺序执行后全量通过，未改变数值精度或测试范围。

全新上下文对抗审查发现全缺失Run及候选追踪缺少对应关系两项，修复后独立复核joint、uncertainty与研究脚本25项通过。研究脚本增加显式融合规则及逐次候选身份，故障注入验证trace不改变两种规则的结果；最终又扩大夹具触发half／double追加，2项通过。JSON或HTML任一身份变化都会禁用融合报告，旧完成标记不能启用遗留报告，新增守护已通过并包含在最终根回归中。只读身份采用既有本地文件身份，并非对抗恶意同尺寸同mtime篡改的内容认证。

GUI在650×500和1100×850加载微软雅黑后实际检查截图：中文可读，新增字段左边缘一致、间距12像素，8个结果按钮无重叠，融合按钮指向保存HTML；切换、保存重载及CW隐藏字段经过实际Qt事件循环。证据为 `tmp/period_upgrade_20261016/*visual_final.png`、`gui_visual_final_geometry.json`；行为通过与视觉通过分开留存。

完整100Run输入的5399.833177秒与30次整Run重采样已整理到[最终实验阶段](../experiments/reports/2026-10-14_PERIOD_UNCERTAINTY_AND_FUSION.md#predictive-real-input-20261016)，前端／融合四格与输入源码哈希独立冻结。30次均同验证模式、失败比例0，经验分位5373.968778／5398.325194／5428.380029秒；不是最终95%或3σ保证。完整500窗复用前端脚本也在稳定源码下通过。跨形状／几何／噪声、污染多数、面元积分和共享ADC计权继续开放，不是本轮收尾已实现的功能。未创建提交或推送。

复建最终测试时先 `conda activate pytorch`，分别执行 `python -m pytest tests -q -p no:cacheprovider` 和 `python -m pytest inversion/tests -q -p no:cacheprovider --import-mode=importlib`。沙箱用户与仓库所有者不同时，在该PowerShell进程设置 `$env:GIT_CONFIG_COUNT='2'`、`$env:GIT_CONFIG_KEY_0='safe.directory'`、`$env:GIT_CONFIG_VALUE_0='D:/Documents/rotation-period-measurement'`、`$env:GIT_CONFIG_KEY_1='safe.directory'`、`$env:GIT_CONFIG_VALUE_1='D:/Documents/rotation-period-measurement/inversion'`；终端退出后不保留这些覆盖。文档验收执行 `python scripts/check_doc_math.py`，本轮当前版本零违规。

<a id="optional-period-methods"></a>

## 可选周期反演功能交付与验证（2026-10-11）

本次把 Chirp 的视线经度相位补偿、多谐波特征拟合与局部周期细化整理成独立开关，接入 GUI、配置校验、诊断与八组合比较。基础模式保留共同截距和正确时标，不恢复每 Run 独立常数。没有接入形状模板，没有研究未知形状的更高精度算法，也不声称开启更多选项必然提高精度。用户操作说明见 [可选方法操作](../../GUI_USER_MANUAL.md#optional-period-methods)。本文在交付后冻结，后续结果另写文件。

### 改动与输入空间

后端改动为 `inversion/src/dataset.py`、`inversion/src/inversion.py`，新增 `period_enhancements.py` 与 `method_report.py`；CLI 改动为 `inversion/scripts/estimate_period.py`。GUI 改动为 `rotation_gui/schema.py`、`rotation_gui/widgets/layout.py`、`rotation_gui/window/parameter_form.py`、`rotation_gui/window/main.py`。新增测试为根目录两个 `test_optional_period_*.py` 文件；旧 GUI 测试的目标 ID 夹具显式构造数字类型，不再假定用户配置文件必须仍保存数字 ID。

开关必须为 JSON 布尔值。Chirp 可选谐波数为正整数，明确开启或比较时至少为 2；剩余自由度不足的特征跳过并记录原因，全部不可估计时明确报错。补偿和比较要求独立的 ICRS 极轴赤经 [0,360]、赤纬 [-90,90]，且仅支持散射质心时标；半周期与完整周期分别使用两倍与一倍有效经度。CW 不接受新配置，GUI 隐藏并裁剪 Chirp 专属参数，CW 计算路径未改。比较使用已经提取的同一组特征、时刻、权重及范围，不读形状或初相位真值。

旧配置省略细化字段且关闭相位补偿时保持原内部峰规则和局部细化。显式开／关细化或相位补偿启用时统一包含边界候选，并检查细化残差不增加；GUI 保存会显式记录开关，因此边界占优时结果可能不同于旧 CLI 省略字段的路径。诊断记录 `candidate_policy`。独立边界用例：真周期在搜索范围外，旧路径返回 7.7863838 秒，而新显式开与关均返回范围上界 9 秒。这项检查验证开关只控制细化，不代表估计得到真实周期。

几何使用收发单位视线和的赤道投影经度，不是完整双站物理模板；CPI 使用中心散射时刻的线性插值。经度解缠要求足够密的方向采样，不能恢复空档内超过半圈的未知绕转。极点、相反视线、缺失几何、超范围外推均报错；未验证一般形状下的精度收益。未修改默认浮点精度、回波生成器、观测计划或原始数据。

### 可复现验收

Python 使用 Conda `pytorch` 环境，命令从仓库根目录执行。临时目录 `E:\Claude-code\cache` 不在当前沙箱可写范围，因此本轮临时配置、截图及 CLI 输出放入已忽略的仓库 `tmp/`，不是发布材料。根 tests 与反演子模块 tests 分开运行，避免不同目录的测试包导入冲突。

```powershell
conda activate pytorch
python -m pytest -q tests --import-mode=importlib -p no:cacheprovider
python -m pytest -q inversion/tests --import-mode=importlib -p no:cacheprovider
python scripts/check_doc_math.py
git diff --check
git -C inversion diff --check
```

本会话最终根目录 195 项通过（41.49 秒），反演子模块 53 项通过、3 项跳过（11.52 秒）。三个跳过项是既有网格、回波和 CPU/CUDA 回波一致性测试的迁移占位，已迁移到 `echo/tests`，不计为通过。GUI 子集 77 项通过（12.50 秒），包含两种窗口宽度、实际事件循环、展开／收起／重复切换、滚动值及最大范围、最后控件可达性、焦点恢复、JSON 往返、有效隐藏参数和非法子字段关闭。截图 `tmp/optional_period_gui/enabled_650.png`、`enabled_1100.png` 及对应关闭截图已检查；Windows offscreen 需在测试中临时注册系统微软雅黑字体，结束后移除，生产样式未改变。耗时仅记录验收成本，不是性能对比。

八种组合的合成夹具包含非恒定经度变化和非正弦特征，逐格与独立加权线性回归计算的网格分数核对，八个返回周期互不相同，补偿与谐波分支的曲线差异均非零。另覆盖排序、跨 π 解缠、一倍／两倍关系、极点与外推拒绝、无效配置、旧谐波语义、关闭功能不被隐藏参数破坏、真实 CPI 与逐脉冲路由、显式细化的边界保护。比较报告关闭后 JSON `enabled=false` 且 `methods={}`，HTML 明确本次未开启，避免陈旧结果。真实 CW、Chirp CPI 和逐脉冲 CLI 由子模块既有回归覆盖。

### 同数据 CLI 对照

输入为已冻结的 `runs/paras_for_70m_3h/echo/echo.npz`，2000 个单脉冲 Run，2000 个原始特征时刻，搜索 1800–14400 秒、4000 个网格。回波 SHA256 为 `add62990c10ab7c4d74f5e2e5d50611cd9201d967399b3b2ed26ee195ee6ba3a`。本轮没有重生成回波，没有读取形状模型；极轴 105°、−66°作为此对照明确给定的已知先验，不代表真实观测可以自动获得它。

复现时，把原作业 `configs/inversion.generated.json` 复制到新的临时 JSON，增加如下字段（`output_path` 可由 CLI 的 `--output` 覆盖）。随后执行命令，新的输出目录由使用者指定，不覆盖源作业。

```json
{
  "los_phase_compensation": true,
  "spin_axis_ra_deg": 105,
  "spin_axis_dec_deg": -66,
  "phase_period_convention": "half_rotation",
  "multi_harmonic_enabled": false,
  "harmonics": 2,
  "refine_period": true,
  "compare_methods": true
}
```

```powershell
python inversion/scripts/estimate_period.py --echo runs/paras_for_70m_3h/echo/echo.npz --config 我的可选反演配置.json --output tmp/optional_period_reproduce
```

本次实际输出为 `tmp/optional_period_validation_20261011/output_reviewed`，已完成完整 CLI、JSON 和 HTML 比较输出。以下为距离质心这一特征的结果，不是跨特征共识周期，误差仅用于检验集成结果，以已知半周期 5400 秒评价，不参与算法选择。

| 相位补偿 | 谐波数 | 局部细化 | 周期（秒） | 偏差（秒） |
|---|---:|---|---:|---:|
| 关 | 1 | 关 | 5404.054054054055 | +4.054054054055 |
| 关 | 1 | 开 | 5404.493479588764 | +4.493479588764 |
| 关 | 2 | 关 | 5407.606348013899 | +7.606348013899 |
| 关 | 2 | 开 | 5406.295616554674 | +6.295616554674 |
| 开 | 1 | 关 | 5400.506424083279 | +0.506424083279 |
| 开 | 1 | 开 | 5401.596767018853 | +1.596767018853 |
| 开 | 2 | 关 | 5404.054054054055 | +4.054054054055 |
| 开 | 2 | 开 | 5403.398213359327 | +3.398213359327 |

旧冻结结果 5404.493479588764 秒与本轮未补偿单谐波细化结果一致，旧经度补偿结果 5401.5967670188475 秒与本轮差约 $5.5\times10^{-12}$ 秒。此表是同数据的功能对照，不是新的高精度方法研究，也不能从偶然接近真值的网格候选推出精度保证；细化提高拟合程度并不必然降低周期偏差，多谐波也不是更高精度的自动等级。没有提供新的真实观测精度、理论极限或性能加速结论。

### 独立审查

全新上下文子代理按 `change-verification-discipline` 技能审查输入空间、分支可区分性、GUI 与 CLI 入口及静默行为。发现并修复了：关闭非法数值草稿无法收起、关闭多谐波仍急切求值隐藏参数、关闭比较后旧文件残留、细化开关同时改变候选端点规则。对应最小复现均补入回归测试。中文 offscreen 字体限制通过测试字体注册解决，布局与文本已检查。最终复核可选方法与 GUI 测试 25 项通过，技术文档符合代码，没有剩余确认缺陷。审查未获得可用 Git 基线，不能独立证明旧版全输入空间等价，因此结论只覆盖保留旧候选路径及已验证的冻结案例；报告交付后不回改。
