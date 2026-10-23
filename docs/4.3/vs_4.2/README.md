# 4.2 → 4.3 过程材料索引

了解现在做到哪一步，请先读[项目现状总览](../PROJECT_OVERVIEW.md)。本目录用于追溯改动与实验依据；这里的阶段性结论不能脱离当时输入、配置和估计目标使用。

| 查阅目的 | 入口 |
| --- | --- |
| 当前问题及完成条件 | [开放问题页首](../../4.4/vs_4.3/plans/OPEN_ISSUES.md#current-issues) |
| 4.3历史路线及4.4实施范围 | [4.3历史记录](plans/PERIOD_INVERSION_IMPROVEMENT_PLAN.md)、[4.4计划](../../4.4/vs_4.3/plans/PERIOD_INVERSION_IMPROVEMENT_PLAN.md#current-stage) |
| 交给下一位AI实施EV5精度改进 | **[独立接手说明](../../4.4/vs_4.3/plans/EV5_PRECISION_IMPLEMENTATION_HANDOFF.md)**；已含必需合同，旧长文无需通读，原型已有实际结果，生产算法未改变 |
| EV5与其他实验数值、负结果、哈希和命令 | [实验导航](experiments/README.md) |
| 已落地功能的行为与验收 | [生产变更](changes/README.md) |
| 某天发生了什么 | [每日日志](logs/README.md) |
| 4.3收尾、逐文件提交清单与源码归档验证 | [收尾审查](audits/RELEASE_READINESS.md) |
| 迁入4.4的工程方案及4.3历史依据 | [ADC职责迁移](../../4.4/vs_4.3/plans/ADC_PLANNING_REFACTOR_PLAN.md)、[插值方案](plans/2026-10-10_INTERPOLATION_REPAIR_PLAN.md)、[结果查看方案](plans/GUI_RESULT_VIEW_PLAN.md) |

## 如何区分现状与历史

`changes/`是已落地专题，`experiments/`是按阶段冻结的研究/验收证据，`plans/`只保留4.3历史方案和决策，当前路线已迁4.4，`logs/`只做按日索引。历史段落的“本次”“未实施”不自动代表当前状态；操作与算法回到[4.3正文导航](../README.md)。

共同截距、可选周期方法、Fourier距离对齐、共同周期预测融合、CPI完整相关支撑、只读结果查看与CUDA搜索已有实现。研究脚本、条件性误差控制和单场景结果仍需按各自作用域阅读，不能据此推定跨场景或实测精度已验收。

## 文档整理沿革

2026-10-12起将生产专题、实验、计划和日志分层；2026-10-18进一步合并重复手册与研究正文，将周期实验按三类问题拆分，教学验证并入信号形成报告。实验区按 `reports/`、`data/`、`configs/`、`figures/` 分开；4.3日志改为 `YYYY-MM-DD_LOG.md`，实验报告与附件使用日期前缀。已冻结数值、先验、失败、哈希和测量时间保留，4.1/4.2不改；未重跑科学实验。详情见[当日记录](logs/2026-10-18_LOG.md)，后续维护遵循[AGENTS.md](../../../AGENTS.md)。
