# 4.3 项目现状总览

核对日期：2026-10-23。本文是当前状态的首读正文，回答“已经实现什么、实验达到什么效果、还缺什么”。EV5参数、三维模型及星历驱动的全链路仿真和噪声实验已经完成，属于4.3成果。生产能力仍以4.3实现和原冻结实验为准；10月20—23日新增的EV5精度改进研究原型尚未接入正式反演、CLI和GUI，该算法接入工作留到4.4。操作、算法推导和历史证据分别链接到原正文，不需要先通读日志或全部改进计划。

**4.3 已跑通“视线解算 → 回波仿真 → 自转周期反演 → 结果查看”的完整链路，并完成 EV5 形状及名义自转参数的仿真验证。当前可以支持受控场景的算法研究；跨目标、跨几何的稳健精度、最终周期误差区间和实测雷达验证仍未完成。**

<a id="capabilities"></a>

## 1. 已经实现什么

下图以本轮主要验证的Chirp路径为例；CW共用三阶段架构，反演处理方法另见下文。

```text
三段式配置：observation / echo / inversion
  → 观测解算：视线、发射—散射—接收三事件、Run与ADC计划
  → observation_info.npz
  → 回波仿真：形状/点目标、运动、Chirp、接收噪声
  → echo.npz
  → 周期反演：补偿、脉压、CPI或逐脉冲特征、周期搜索与融合
  → summary.json、特征/周期图、融合及可选误差诊断
```

| 环节 | 当前能力 | 使用边界与详细说明 |
| --- | --- | --- |
| 观测解算 | 星历或自定义状态、单/双站、可见性选时、三事件光行时、Chirp发射与采样计划 | 时序和ADC以观测产物为权威来源；[观测选时](OBSERVATION_TIME_SELECTION.md)、[测站与可见性](OBSERVATION_TIME_SELECTION.md#station-visibility) |
| 回波仿真 | 网格或点目标、Chirp/CW、质心补偿或原始复基带、脉内运动、CPU/GPU路径 | 当前EV5验证使用理想质心平动补偿；离散散射模型与实测校准仍有边界，见[架构](ARCHITECTURE_V4.md) |
| Chirp信号处理 | 脉压、保相位Fourier距离对齐、同相干组内CPI；CPI不足时回退逐脉冲处理 | CPI可提取五项标量，逐脉冲回退为三项距离相关标量；不跨不相干Run拼接复相位，见[链路说明](CHIRP_INVERSION_WALKTHROUGH.md) |
| Chirp周期估计 | 共同截距、原始特征时刻、单/多谐波、可选视线相位补偿、局部细化 | Chirp默认 `predictive_joint` 共同周期留出预测融合，旧 `legacy_consensus` 保留对照；[算法](INVERSION_ALGORITHM.md)、[可选方法](GUI_USER_MANUAL.md#optional-period-methods) |
| Chirp计算与诊断 | CPU默认、可选CUDA预处理和周期网格/Run重采样；单通道、融合、采样窗及误差诊断 | 局部细化与共同融合仍在CPU；预测评分不是概率，条件性误差报告尚不是最终精度保证，见[设备与误差设置](GUI_USER_MANUAL.md#compute-and-uncertainty) |
| 操作与复用 | GUI与CLI分阶段/全链路运行、配置保存、会话恢复、已有结果只读查看 | 脉压、特征、CPI及周期图读取已完成反演产物；缺少产物时需正式执行计算，见[GUI手册](GUI_USER_MANUAL.md) |

CW路径另用STFT与逐特征Lomb–Scargle，不能把下述Chirp融合或误差功能直接套到CW。

当前Chirp融合在同一候选周期上拟合各可用通道，使用整Run五折留出预测改善的通道中位数选周期；有效Run少于10个时退回共同拟合评分。留出折参与周期选择，因此这些评分本身不是最终独立测试，也不能把五个相关通道看成五份独立证据。[实现契约与控制实验](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/changes/PERIOD_INVERSION_BASELINE.md#predictive-joint-20261016)

Chirp生成器先在每个Run的唯一全局ADC索引上计算脉冲贡献并叠加，再映射为二维脉冲保存行；共享物理样点的信号和噪声保持一致。“保存行共享样点”和“有效回波真实重叠”是两个问题。前端已有全局采样机制，下游对共享ADC的统计计权和真实重叠信号处理仍未完成完整验收。[数据流说明](CHIRP_INVERSION_WALKTHROUGH.md)、[当前缺口](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.4/vs_4.3/plans/OPEN_ISSUES.md#current-issues)

<a id="validated-results"></a>

## 2. 实验已经达到什么效果

三组实验的形状、尺寸、观测安排和评价周期不同，下面逐项列出作用域；它们不构成只改变一个因素的性能排名。完整原始统计、输入/源码身份、失败结果及复现命令保留在[实验专题](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/experiments/README.md#reports)。

| 实验与评价对象 | 无噪声或固定输入基线 | 接收IQ加噪结果 | 当前能支持的结论 |
| --- | --- | --- | --- |
| 椭球，完整自转10800秒，主要评价5400秒特征重复半周期；100Run/500CPI | 历史生产CLI为5399.833177秒，相对重复周期偏差−0.166823秒 | 62档×100次；误差≤10%/1%/0.1%的经验95%成功门限为−25/−22/−15dB | 该固定椭球作业能高精度恢复重复半周期；完整自转的半周歧义仍在。[基线](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/experiments/reports/2026-10-14_PERIOD_UNCERTAINTY_AND_FUSION.md#predictive-real-input-20261016)、[噪声扫描](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/experiments/reports/2026-10-16_RECEIVER_SNR_AND_EV5.md#receiver-snr-extension-20261016) |
| EV5网格最大尺寸70m控制，完整自转10800秒；复用原Apophis观测计划 | 5754.032520秒；整周误差46.72%，相对固定5400秒别名仍偏6.56% | 91档×100次；三个误差等级均无持续高SNR门限，30dB均0/100 | 这是明确负结果：椭球效果不能直接迁移到该网格作业。尺寸也改变了，不能将差异全归因于形状。[证据](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/experiments/reports/2026-10-16_RECEIVER_SNR_AND_EV5.md#ev5-70m-snr-20261017) |
| EV5名义参数，400m体积等效直径，完整自转13410秒；独立观测计划 | 13423.578975秒；偏差+13.578975秒，误差0.1012600675% | 91档×100次；误差≤10%和≤1%的经验95%成功门限均−7dB，≤0.1%无持续高SNR门限 | 此固定仿真达到1%等级；无噪声尚未达到0.1%，更不能宣称稳定亚秒。[证据](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/experiments/reports/2026-10-16_RECEIVER_SNR_AND_EV5.md#ev5-real-plan-20261017) |

这里的“经验95%成功门限”指该SNR及全部更高已扫描档，各100次中至少95次满足对应误差要求，且无噪声基线通过；不是以95%置信度证明总体成功率达到95%，也不是每次都成功。SNR定义为唯一有效保存ADC样点的平均干净IQ功率与期望噪声功率之比，不是脉压后SNR。噪声试验固定干净仿真输入并重复加入接收复高斯白噪声，不是重新生成全部系统误差的独立观测。[事前协议](../../EXPERIMENTS.md)

**研究进展（尚未列装）：** 使用同500CPI、原五特征和原LOS设置，改为多谐波正预测增益融合后，70m无噪误差从46.72%降到0.058588%，400m从0.101260%降到0.011166%。70m在20／30dB各100次达到0.1%以内，但0／10dB的全样本RMSE比旧方法更差，因此新增显式选项，不无条件替换默认。已知极轴的有限球面响应也取得改善，但70m需额外极轴先验，另组报告。带噪结果、数值搜索协议和失败统一见[同数据实验](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/experiments/reports/2026-10-16_RECEIVER_SNR_AND_EV5.md#ev5-precision-20261020)，后续生产移植归入[4.4交接](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.4/vs_4.3/plans/EV5_PRECISION_IMPLEMENTATION_HANDOFF.md)。没有重生成回波或要求形状反演；这些是已见场景回测，不能替换上表生产基线或证明一般目标精度。

椭球5399.833177秒来自历史CLI；其后在冻结源码下分别完成500窗前端与保存特征搜索/重采样核对，并未重新跑一遍冻结源码的完整端到端流程。70m作业复用了原Apophis观测，运行回波→反演；400m作业独立完成观测→回波→反演。三者的执行范围与耗时不能互换。

### EV5名义参数验证的具体含义

正式EV5作业使用用户提供的形状网格居中并缩放为400m体积等效直径，采用13410秒（3.725小时）自转、赤道极轴RA105°/Dec−66°和JPL星历；观测计划为2039年12月26日至30日、100个16秒Run、20Hz PRF、10μs脉宽、8秒CPI/2秒步长，实际生成32000脉冲和500CPI。快时间采样率200MHz、Chirp带宽150MHz、载频1GHz。这里16秒是每Run的调度时长，脉冲间歇发射；每Run累计射频开启时间只有3.2ms。[配置快照](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/experiments/configs/2026-10-16_EV5_400M_LONG_CPI.json)

反演预先启用视线相位补偿，并显式给定名义极轴；形状和周期用于生成回波，周期真值仅用于事后评价，没有按真值挑选更近通道或事后乘2。该实验支持的是“已知极轴、名义物理参数与星历驱动的仿真”，尚未验证真实雷达IQ、绝对链路预算、未知极轴联合反演或真实目标的系统总误差。网格+Z轴与自转轴对齐、均匀密度、当前散射模型及远期地球定向信息均有假设。[物理输入与来源核对](research/RADAR_PERIOD_ESTIMATION.md#ev5-physical-inputs-20261016)

0.1%对应13.41秒，因此13.578975秒的偏差严格不达标。噪声扫描中0.1%只在10—27dB整数档满足经验95%，到30dB下降为76/100；无噪声也失败。提高SNR没有消除当前处理链的偏差，具体来源仍需控制实验分解，不能只凭曲线归因于某一通道。

![EV5 400m名义参数仿真的接收噪声误差与成功率](vs_4.2/experiments/figures/2026-10-16_EV5_400M/period_error_vs_snr.png)

图示对应上述固定EV5配置；0.1%的有限达标区间不能读成“只要SNR更高就稳定达标”。逐档数值见[完整扫描](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/experiments/reports/2026-10-16_RECEIVER_SNR_AND_EV5.md#ev5-real-plan-20261017)。

<a id="remaining-gaps"></a>

## 3. 4.3适用范围与4.4交接

4.3于2026-10-23结束本轮修改。它已打通观测、回波、反演和查看链路，并在声明的固定仿真场景获得相应精度；没有认证跨目标通用精度、未知极轴、实测雷达输入或最终系统总误差。70m原生产误选、400m无噪偏差和多普勒谱尾等负结果作为4.3证据保留，不因收尾改写为成功。共享ADC计权、真实回波重叠、缺样和面片积分等未验收输入仍遵守原有限制。

未完成的算法移植、误差校准、工程事项与完成条件已迁[4.4开放问题](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.4/vs_4.3/plans/OPEN_ISSUES.md#current-issues)，执行次序见[4.4计划](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.4/vs_4.3/plans/PERIOD_INVERSION_IMPROVEMENT_PLAN.md)。五特征多谐波融合与已知轴球面响应仍是研究原型，后续从[独立接手说明](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.4/vs_4.3/plans/EV5_PRECISION_IMPLEMENTATION_HANDOFF.md)移植；4.3生产默认没有因此改变。已执行实验、文献与历史决策继续留在本版本，不复制为4.4新结果。

<a id="reading-path"></a>

## 4. 接下来按什么顺序读

| 阅读目的 | 推荐正文 | 可以暂时跳过 |
| --- | --- | --- |
| 只把握项目状态 | 本文第1—3节 | 每日日志、全部路线表、历史实验推导 |
| 核实EV5效果 | [400m正式实验](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/experiments/reports/2026-10-16_RECEIVER_SNR_AND_EV5.md#ev5-real-plan-20261017)，再对照[70m负结果](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/experiments/reports/2026-10-16_RECEIVER_SNR_AND_EV5.md#ev5-70m-snr-20261017) | 实验专题前面的早期2000个单脉冲Run阶段 |
| 理解为什么这样反演 | [完整链路](CHIRP_INVERSION_WALKTHROUGH.md) → [算法正文第0节起](INVERSION_ALGORITHM.md) | 研究方法大全与工程日志 |
| 实际运行和查看结果 | [根README快速运行](../../README.md#快速运行) → [GUI手册](GUI_USER_MANUAL.md)；精确字段查各模块README | 把旧计划当操作手册 |
| 确定下一轮研究 | [当前开放问题](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.4/vs_4.3/plans/OPEN_ISSUES.md#current-issues) → [4.4改进计划](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.4/vs_4.3/plans/PERIOD_INVERSION_IMPROVEMENT_PLAN.md#current-stage) → 对应实验/文献 | 一次实现全部候选方法 |

完整文件分类见[4.3文档导航](README.md)。`vs_4.2/changes/`保存已落地专题，`experiments/`保存阶段证据，`plans/`保存4.3历史方案，当前待办归入4.4，`logs/`仅用于追踪何时改过；4.1/4.2是冻结历史。

<a id="interfaces"></a>

## 5. 实现与配置速查

三个模块可独立运行：观测入口[solve_observation_info.py](../../observation/solve_observation_info.py)、回波入口[simulate_echo.py](../../echo/simulate_echo.py)、反演入口[estimate_period.py](../../inversion/scripts/estimate_period.py)；顶层[pipeline.py](../../pipeline.py)负责配置和串联，两个GUI启动入口最终调用同一应用。字段表分别见[观测README](../../observation/README.md)、[回波README](../../echo/README.md)、[反演README](../../inversion/README.md)，术语见[GLOSSARY.md](GLOSSARY.md)。

保存契约为schema v4，但用户JSON不写 `schema_version`。顶层只有 `observation`、`echo`、`inversion`；Chirp使用 `schedule` 事件源，CW使用 `receive`，与 `echo.waveform.type` 对应。未知、废弃或不适用字段通常拒绝；旧 `pre_guard_s/post_guard_s` 有显式警告迁移到 `target.extent_path_m` 的兼容特例，详见[术语与废弃字段](GLOSSARY.md)。不应把GUI切换当前字段集合当成任意旧JSON迁移工具。

时序metadata中，`adc_window_duration_s`表示Run级连续ADC窗时长（取最大），不是Run调度长度或射频开启时长；`receive_centroid_span_s`表示质心接收事件跨度；`visibility_windows_elapsed_s`表示选时实际使用的可见区间，自定义直角坐标测站下为完整campaign区间。echo独立测试可用[最小Chirp计划生成器](../../echo/scripts/make_simple_chirp_plan.py)，仍由观测产物提供时序/ADC。

开发夹具与EV5研究配置的用途不同：前者用于接口与快速功能检查，后者绑定明确场景、网格与本地资源，尚未整理为可直接搬到任意机器的通用示例。根测试、观测测试和反演测试可从根目录按各自路径运行；echo测试需在 `echo/` 目录运行，避免 `src` 导入冲突。验收范围与证据规则以[验证策略](VERIFICATION_POLICY.md)和[EXPERIMENTS.md](../../EXPERIMENTS.md)为准，本文不把历史测试通过数当作本次重跑结果。
