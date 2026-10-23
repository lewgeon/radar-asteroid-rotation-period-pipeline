# 4.3 文档导航

**第一次阅读从[项目现状总览](PROJECT_OVERVIEW.md)开始。** 它集中说明已实现的通路、三组仿真效果、EV5验证边界和未解决问题。4.3于2026-10-23收尾，已实现说明与历史证据保留本版；未实施方案与当前问题由[4.4](../4.4/README.md)接续。

## 按目的选择

| 目的 | 主入口 | 需要时再深入 |
| --- | --- | --- |
| 了解做到哪一步 | [项目现状总览](PROJECT_OVERVIEW.md) | [当前开放问题](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.4/vs_4.3/plans/OPEN_ISSUES.md#current-issues) |
| 核实实验效果与EV5结果 | [实验导航](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/experiments/README.md) | 按报告中的阶段链接查看数据、配置和配图 |
| 理解信号与算法 | [Chirp完整链路](CHIRP_INVERSION_WALKTHROUGH.md) → [周期反演算法](INVERSION_ALGORITHM.md) | [术语](GLOSSARY.md)、[候选与可选方法](INVERSION_ALGORITHM.md#optional-method-contract) |
| 运行GUI或配置实验 | [GUI手册](GUI_USER_MANUAL.md)、[根README](../../README.md#快速运行) | [观测选时与测站约束](OBSERVATION_TIME_SELECTION.md)、[可选方法操作](GUI_USER_MANUAL.md#optional-period-methods) |
| 研究精度与误差声明 | [不确定度算法](INVERSION_ALGORITHM.md#period-uncertainty) | [误差与融合实验](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/experiments/reports/2026-10-14_PERIOD_UNCERTAINTY_AND_FUSION.md) |
| 接手现有EV5数据的精度改进 | **[独立接手说明](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.4/vs_4.3/plans/EV5_PRECISION_IMPLEMENTATION_HANDOFF.md)** | 已含必需公式、参数、代码入口和验收值；[实验依据](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/experiments/reports/2026-10-16_RECEIVER_SNR_AND_EV5.md#ev5-precision-20261020)、旧研究和计划只按需查证，研究原型尚未接入生产 |
| 修改实现 | [系统与GUI架构](ARCHITECTURE_V4.md) | [验证策略](VERIFICATION_POLICY.md)、仓库协作规则 |

## 资料分类

| 位置 | 阅读用途 |
| --- | --- |
| 当前目录的正文 | 当前能力、算法、配置与操作；以总览统领 |
| [research/](research) | [雷达周期估计](research/RADAR_PERIOD_ESTIMATION.md)、[跨领域估计](research/CROSS_DOMAIN_PERIOD_ESTIMATION.md)、[信号处理与宽度定义](research/SIGNAL_PROCESSING_LIMITS.md)；记录文献适用范围和迁移依据 |
| [vs_4.2/changes/](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/changes/README.md) | 已落地功能的契约与阶段验收 |
| [vs_4.2/experiments/](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/experiments/README.md) | 正文、数据、配置、配图分目录；报告与附件日期在前 |
| [vs_4.2/plans/](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/plans/README.md) | 已发挥作用的历史方案与阶段决策；当前缺口和实施交接已迁[4.4](../4.4/README.md) |
| [vs_4.2/logs/](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/logs/README.md) | 按日期追踪改动，不代替当前状态正文 |
| [4.2及更早文档](../4.2/README.md) | 冻结快照，仅用于追溯 |

过程材料总入口见[4.2→4.3索引](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/README.md)。同一主题保持一份主正文，日志和索引只链接证据。历史章节中的“当前”“未实施”只指该阶段，4.3交付范围以总览为准，后续问题和验收由4.4管理。
