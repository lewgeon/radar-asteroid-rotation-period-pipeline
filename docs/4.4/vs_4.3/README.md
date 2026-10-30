# 4.3 → 4.4工作索引

当前4.4保留默认留出预测融合、A多谐波正预测增益融合、B已知极轴球面响应及旧版投票。算法使用见[精度策略手册](../PERIOD_PRECISION_OPTIONS.md)，数值接入和历史验收见[工程专题](changes/EV5_PRECISION_IMPLEMENTATION.md)。

2026-10-30按用户要求拆分短跨度研究。主仓库和反演子模块分别使用`codex/short-arc-research`保存研究快照；当前`chirp-pulse`只接入A/B。分支身份、恢复命令和本次检查见[当日记录](logs/2026-10-30_LOG.md#short-arc-branch-split)。

2026-10-30阅读全文并核对用户提供的凸反演I／II及ADAM原始论文，区分周期别名间隔、真值误差、形式统计误差和模型敏感性，见[研究第15节](../research/PERIOD_PRECISION_BENCHMARKS.md#original-paper-uncertainty)；后续研究通过重复反演报告周期标准差的直接实例见[第16节](../research/PERIOD_PRECISION_BENCHMARKS.md#later-convex-uncertainty)。[对照计划](plans/OPTICAL_RADAR_BENCHMARK_PLAN.md)以均超过一转的同窗口横向比较为主，并提供[实施合同](plans/OPTICAL_RADAR_BENCHMARK_PLAN.md#implementation-handoff)：算法、数据接口、首配置、±计算与验收；均为待实现内容，未运行科学仿真，见[当日记录](logs/2026-10-30_LOG.md)。

2026-10-29完成两个纯核心源码目录的光变合成检查，并形成[独立光学／雷达对照与改造计划书](plans/OPTICAL_RADAR_BENCHMARK_PLAN.md)。可复用已有亮度核，适配与数值对照尚未实施；重点核对同一OBJ的姿态／几何、凸体与遮挡边界、相对光度分组和短窗口假说。源码审查范围与文档验收见[当日记录](logs/2026-10-29_LOG.md)。

阶段成果已汇总为[综合实验报告](experiments/reports/2026-10-24_STAGE_EXPERIMENT_REPORT.md)，按信号模型、原方法、分级加噪、A/B改进及误差／置信集合串联；历史专题继续保留原始证据。

2026-10-26完成[既有方法精度文献比较](../research/PERIOD_PRECISION_BENCHMARKS.md)：核对光变、凸形反演、雷达形状辅助及ISAR联合方法的周期数值、误差定义和观测条件。当前证据不支持本项目相对成熟方法精度领先；没有恢复计算或修改算法，见[当日记录](logs/2026-10-26_LOG.md)。

同日按用户要求独立编写[精度极限与算法改进研究计划书](plans/PERIOD_PRECISION_LIMITS_PLAN.md)，将研究正文原第10节的方案迁出并扩充，作为该主题唯一计划。首轮围绕400m EV5的理论界、全域难分性、前向拟合参照及20次配对先导设置阶段门槛，尚未启动实验；原短观测作业保持停止。

同日后续完成[生产选择器短窗重放](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/codex/short-arc-research/docs/4.4/vs_4.3/experiments/reports/2026-10-24_SHORT_ARC_IDENTIFIABILITY.md#feature-replay-20261026)，并将五特征自由响应与物理尺度约束缺口、分层改造建议并入[计划第十三节](plans/PERIOD_PRECISION_LIMITS_PLAN.md#architecture-diagnosis-20261026)。仅重用既有无噪特征进行秒级探针，原S0—S5及新算法仍待实施；[追加文献核对](../research/PERIOD_PRECISION_BENCHMARKS.md#radar-short-arc-evidence)说明雷达／光学精度和短弧条件不能脱离先验比较。

同日继续核对相位利用与低维凸外形联合反演，补充光度凸外形／几何凸包、ADAM快速雷达初模、SHAPE低阶流程及计算成本边界，见[研究第12—13节](../research/PERIOD_PRECISION_BENCHMARKS.md#coherent-phase-research-20261026)。外形目标下优先完整功率物理拟合、条件满足后相干精修的[实施建议](plans/PERIOD_PRECISION_LIMITS_PLAN.md#convex-period-first-path)仍未执行，不将此次研究当成已改善周期或恢复真实凸包。

用户进一步澄清当前首要问题是充分观测下周期精度，短于一转后置；非相参功率不排斥形状与自转联合，NeuS旧项目应作为神经联合反演候选评估。当前路线以[研究第14节](../research/PERIOD_PRECISION_BENCHMARKS.md#noncoherent-period-first)和[计划13.7](plans/PERIOD_PRECISION_LIMITS_PLAN.md#noncoherent-route-screening)为准：优先验证共享刚体与雷达正演，比较低维显式形状和受限SDF；原五摘要及258bin经验拟合作基线，不继续预设调权重／增加谐波带来突破。只读核对与一手文献支持可行性，未训练、未改生产、未恢复作业。

随后明确总体优先级为[研究成熟光学精度的机制](../research/PERIOD_PRECISION_BENCHMARKS.md#optical-precision-mechanism)：2007 DX同一Fourier方法的跨段精度改进、DW1／Phaethon的转数基线和全域周期区分，与本项目高SNR稳定偏差分别核对。最新澄清是文献不确定度不能与仿真真值误差直接判胜负；当前按[同目标、同跨度对照](plans/OPTICAL_RADAR_BENCHMARK_PLAN.md)分别评价准确度、重复性和区间覆盖，再决定改进。已有[不确定度推导与实验](../research/PERIOD_PRECISION_BENCHMARKS.md#uncertainty-status)不等于A/B已有最终区间；NeuS仍未被选定，尚无新光学仿真或对照结果。

当前缺口见[开放问题](plans/OPEN_ISSUES.md)，实施次序见[改进计划](plans/PERIOD_INVERSION_IMPROVEMENT_PLAN.md)。4.3冻结实验与历史方案保留在[原版本](../../4.3/vs_4.2/README.md)。
