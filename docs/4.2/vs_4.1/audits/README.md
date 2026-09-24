# 4.2 审计材料

本目录保存针对特定代码快照的检查记录。审计文档中的“已修复”“未修复”和行号表示审计当时的状态，不能直接当作当前 4.2 的功能清单；当前状态应以代码、测试和 [../changes/](../changes/) 为准。

| 文档 | 性质 |
|---|---|
| [CODE_AUDIT_REPORT.md](CODE_AUDIT_REPORT.md) | 4.1 基线及早期 4.2 工作区的综合审计，包含问题、证据和当时建议 |
| [AUDIT_RECHECK_AND_DEADCODE.md](AUDIT_RECHECK_AND_DEADCODE.md) | 后续复核与死代码扫描，状态同样是历史快照 |
| [CURRENT_PROJECT_ISSUES_2026-09-21.md](CURRENT_PROJECT_ISSUES_2026-09-21.md) | 2026-09-21 功能/契约问题清单（当时诊断，不是当前功能表） |
| [deepseek_audit_2026-09-21_1.md](deepseek_audit_2026-09-21_1.md) | 外部会话对 09-21 修改的第一份核查（含测试基建） |
| [deepseek_audit_2026-09-21_2.md](deepseek_audit_2026-09-21_2.md) | 外部会话补充：波形从属 B11–B13；完整 B1–B13 见 plans 下 ROUND2 |
| [DEEPSEEK_AUDIT_RECHECK_2026-09-22.md](DEEPSEEK_AUDIT_RECHECK_2026-09-22.md) | 对上述两份及 ROUND2 的逐条核实（当时未改业务代码）：B1 成立；乱码/管道死锁不成立 |
| [DEEPSEEK_AUDIT_RESPONSE_2026-09-22.md](DEEPSEEK_AUDIT_RESPONSE_2026-09-22.md) | 对两轮质检的回执：核查方法、误判、真实错误与 09-22 已做修改 |
| [deepseek_audit_2026-09-22_1.md](deepseek_audit_2026-09-22_1.md) | 外部会话对 09-22 回执与修复的复核：七项功能修复实测通过；遗留 R1–R4 |
| [deepseek_audit_2026-09-22_2.md](deepseek_audit_2026-09-22_2.md) | 另一外部会话：功能修复通过；认为回执有编码缺陷、乱码归因不准；scratch 为可移植性项 |
| [DEEPSEEK_AUDIT_RESPONSE_RECHECK_2026-09-22.md](DEEPSEEK_AUDIT_RESPONSE_RECHECK_2026-09-22.md) | 第一份会话自行整理的复核正文（含 ROUND2 B2/B11 更正）；§7 为对第二轮回执（R2 修复）的复核：R2 已正确关闭、R1 仍未处理、新增仅 API 层的 R5 |
| [DEEPSEEK_AUDIT_2026-09-22_RECHECK.md](DEEPSEEK_AUDIT_2026-09-22_RECHECK.md) | 对上述两份的核实：R2 成立；回执「澶辫触」不是编码缺陷；R1 环境相关 |
| [DEEPSEEK_AUDIT_RESPONSE_2026-09-22_ROUND2.md](DEEPSEEK_AUDIT_RESPONSE_2026-09-22_ROUND2.md) | 对 09-22 两轮质检的回执：核查方法、误判、R2 真实错误与随后修改 |
| [DEEPSEEK_RANGE_WINDOW_PLAN_RECHECK.md](DEEPSEEK_RANGE_WINDOW_PLAN_RECHECK.md) | 对距离门方案文档外部审阅的核实：P4/P6/P7 成立；P1 对旧稿成立；P2/P3 过严；脉冲数 321 与伪 PRF 约束不成立 |

审计中尚未实施、但决定继续推进的事项，应另写成 [../plans/](../plans/) 下的独立计划；已经完成并需要对外说明的事项，应整理到 [../changes/](../changes/)。
