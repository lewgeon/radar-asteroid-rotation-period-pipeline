# 4.2 方案记录

4.2 已完成。本目录保留当时的方案原文。已经落地的结果在 `../changes/`。4.2 结束时仍未做的 ADC 职责迁移和开放问题在 `docs/4.3/vs_4.2/plans/`。

| 文档 | 状态 | 内容 |
|---|---|---|
| [RANGE_WINDOW_AND_HIGH_RESOLUTION_PLAN.md](RANGE_WINDOW_AND_HIGH_RESOLUTION_PLAN.md) | 字段与试例已实施；存储契约与 ADC 迁移仍不做 | 落地见 [../changes/RANGE_GATE_2026-09-23.md](../changes/RANGE_GATE_2026-09-23.md) |
| [REVIEW_2026-09-21_OPEN_ISSUES.md](REVIEW_2026-09-21_OPEN_ISSUES.md) | 文档与守卫已处理；L3 已移交 4.3 | 原 D1–D5、T1、L2 已写入 `../changes/RUNTIME_LOGIC_FIXES_2026-09-21.md`；T2 见 `CHIRP_ROW_CONTRACT_2026-09-21.md`。L3 见 `docs/4.3/vs_4.2/plans/OPEN_ISSUES.md` |
| [REVIEW_2026-09-21_ROUND2.md](REVIEW_2026-09-21_ROUND2.md) | 未改代码；结论已核实 | 第二轮外部复核 B1–B13。核实见 [../audits/DEEPSEEK_AUDIT_RECHECK_2026-09-22.md](../audits/DEEPSEEK_AUDIT_RECHECK_2026-09-22.md) |
| [VERIFIED_FIX_PLAN_2026-09-22.md](VERIFIED_FIX_PLAN_2026-09-22.md) | 已实施 | 策略原文保留；落地见 [../changes/DATE_LOG_2026-09-22.md](../changes/DATE_LOG_2026-09-22.md) |
| [LOGIC_STABILITY_FIX_PLAN_2026-09-21.md](LOGIC_STABILITY_FIX_PLAN_2026-09-21.md) | 批次 A–F 已落地； inversion 算法仍不做 | 配置契约、产物指纹、GUI/CLI 统一接入与已确认死代码清理；周期估计算法仍见本文件第 1.2 节。当日总录：[../changes/DATE_LOG_2026-09-21.md](../changes/DATE_LOG_2026-09-21.md) |
| [RUNTIME_FIXES_WIP_2026-09-21.md](RUNTIME_FIXES_WIP_2026-09-21.md) | 已由 changes 文档取代 | 中断时的工作备忘；完成后请以 `../changes/RUNTIME_LOGIC_FIXES_2026-09-21.md` 为准 |
| [KNOWN_DEFECTS.md](KNOWN_DEFECTS.md) | 4.2 部分已实施；开放项已移交 | §1、§3、§4.2b 已在 4.2 处理。inversion 重叠计权见 `docs/4.3/vs_4.2/plans/OPEN_ISSUES.md` |

4.2 结束时仍未实施的 ADC 职责迁移计划已迁到 `docs/4.3/vs_4.2/plans/ADC_PLANNING_REFACTOR_PLAN.md`。

Chirp 网格回波跨脉冲批处理已经完成，实际实现与验收见 `../changes/ECHO_SIMULATION_PERFORMANCE_PHASE_B.md`。
