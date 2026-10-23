# 4.4后续工作

4.3于2026-10-23完成收尾，已落地的完整链路、GUI、算法与实验证据保留在[4.3](../4.3/README.md)。4.4目前只有待实施方案与问题清单，没有新增生产算法；不能将研究原型的改善写成已列装功能。

EV5目标参数、三维网格和JPL星历已用于4.3的完整仿真与噪声实验。这里尚未实施的“生产接入”专指后续EV5精度改进算法，即多谐波正预测增益融合与已知极轴球面响应接入正式反演、CLI及GUI；不表示EV5目标尚未接入项目。

| 查阅目的 | 入口 |
| --- | --- |
| 当前缺口、影响和完成条件 | [开放问题](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.4/vs_4.3/plans/OPEN_ISSUES.md#current-issues) |
| 实施次序、暂缓事项与工程边界 | [4.4计划](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.4/vs_4.3/plans/PERIOD_INVERSION_IMPROVEMENT_PLAN.md) |
| 直接接手EV5精度选项 | [独立接手说明](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.4/vs_4.3/plans/EV5_PRECISION_IMPLEMENTATION_HANDOFF.md) |
| 尚未实施的ADC职责调整 | [ADC迁移计划](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.4/vs_4.3/plans/ADC_PLANNING_REFACTOR_PLAN.md) |
| 查证已有数据、数学和失败结果 | [4.3实验导航](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/experiments/README.md)、[4.3研究](../4.3/research/RADAR_PERIOD_ESTIMATION.md) |

已知极轴与未知极轴、固定场景回测与独立场景验证分别验收。4.4保留原默认算法作为对照，新增方法先作为显式选项；不按周期真值选择通道、倍频、模型或运行时阈值。既有暂缓事项不因迁版自动恢复实施。
