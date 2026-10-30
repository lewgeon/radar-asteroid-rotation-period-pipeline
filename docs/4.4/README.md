# 4.4周期反演改进

4.4提供多谐波正预测增益融合（A）和已知极轴球面响应（B）两个显式选项，默认使用4.3的留出预测融合。GUI在“可选反演功能→周期融合方法”中选择算法；配置、输入限制、设备和误差输出见[精度策略手册](PERIOD_PRECISION_OPTIONS.md)。

A/B复用已有五项雷达特征，在两份固定EV5输入上降低了无噪周期误差；A在70m低信噪比仍有退化，B的带噪验证有限。跨场景精度、未知极轴和最终误差区间尚未校准，实际结果见[阶段报告](vs_4.3/experiments/reports/2026-10-24_STAGE_EXPERIMENT_REPORT.md)及[工程验收](vs_4.3/changes/EV5_PRECISION_IMPLEMENTATION.md)。

| 查阅目的 | 入口 |
| --- | --- |
| 已有链路、GUI和观测时序 | [4.3文档](../4.3/README.md) |
| 版本工作、验证和分支归档 | [4.4工作索引](vs_4.3/README.md) |
| 既有方法精度及不确定度定义 | [文献研究](research/PERIOD_PRECISION_BENCHMARKS.md) |
| 同目标、同窗口光学／雷达比较 | [对照计划](vs_4.3/plans/OPTICAL_RADAR_BENCHMARK_PLAN.md)，待实施 |
| 理论精度与物理反演研究 | [精度计划](vs_4.3/plans/PERIOD_PRECISION_LIMITS_PLAN.md)，待实施 |
| 当前缺口与实施顺序 | [开放问题](vs_4.3/plans/OPEN_ISSUES.md)、[改进计划](vs_4.3/plans/PERIOD_INVERSION_IMPROVEMENT_PLAN.md) |
