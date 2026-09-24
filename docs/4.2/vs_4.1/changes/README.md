# 4.2 已实现变更

本目录只存放已经在 4.2 代码中落地、并且具有测试或运行证据的行为变化。文档应描述“改了什么、当前行为是什么、如何验收”，不得把未实施方案放入本目录。

| 文档 | 状态 | 内容 |
|---|---|---|
| [OBSERVATION_RECEPTION_WINDOW.md](OBSERVATION_RECEPTION_WINDOW.md) | 已实现 | Run 级 ADC 原点与脉冲保存行整数网格对齐，以及 4.2 当前接收窗行为 |
| [GUI_LOG_AND_OUTPUT.md](GUI_LOG_AND_OUTPUT.md) | 已实现 | GUI 日志协议、运行状态收尾、产物路径与结果摘要 |
| [ECHO_SIMULATION_PERFORMANCE_PHASE_A.md](ECHO_SIMULATION_PERFORMANCE_PHASE_A.md) | 已实现 | Chirp 网格回波低风险性能优化、数值等价验证和阶段 A 基准 |
| [ECHO_SIMULATION_PERFORMANCE_PHASE_B.md](ECHO_SIMULATION_PERFORMANCE_PHASE_B.md) | 已实现 | Chirp 网格回波跨脉冲批处理、确定性归并、显存退避与完整作业基准 |
| [ECHO_SIMULATION_PERFORMANCE_PHASE_C.md](ECHO_SIMULATION_PERFORMANCE_PHASE_C.md) | 已实现 | 姿态旋转搬到视线侧（本体系重排）、Chirp 包络保持 float64、分块默认值重算与完整作业基准 |
| [CW_LAYOUT_AND_CONFIG_GUARDRAILS.md](CW_LAYOUT_AND_CONFIG_GUARDRAILS.md) | 已实现 | CW 行轴字段按布局分流（契约重构）、选时白名单、自动模式剥离残留 runs、删除不可用示例配置 |
| [CHIRP_ROW_CONTRACT_2026-09-21.md](CHIRP_ROW_CONTRACT_2026-09-21.md) | 已实现 | Chirp 末列纳入半开 ADC 窗，以及 observation↔echo 行宽/来源契约 |
| [RUNTIME_LOGIC_FIXES_2026-09-21.md](RUNTIME_LOGIC_FIXES_2026-09-21.md) | 已实现 | 可见性语义、单脉冲批处理退避、metadata 整数守卫与 09-21 文档勘误 |
| [CONFIG_FINGERPRINT_AND_GUI_SEAM_2026-09-21.md](CONFIG_FINGERPRINT_AND_GUI_SEAM_2026-09-21.md) | 已实现 | 配置静态校验、阶段指纹复用、零回波警告、GUI/CLI 统一 `prepare_run` 与全仓测试入口 |
| [WAVEFORM_OWNERSHIP_2026-09-21.md](WAVEFORM_OWNERSHIP_2026-09-21.md) | 已实现 | 观测不再拥有 `waveform`；PRF/脉宽归 `transmit`，射频类型归 `echo.waveform.type` |
| [DATE_LOG_2026-09-18.md](DATE_LOG_2026-09-18.md) | 已实现 | 按主题记录 2026-09-18 全部改动：核对与文档订正、git 职责分离、可见性设计记录、死代码清理、行轴契约重构、复核收尾 |
| [DATE_LOG_2026-09-19.md](DATE_LOG_2026-09-19.md) | 已实现 | 按时间线复盘契约重构后的两轮外部复核与收尾：问题核实、修法、未采纳项、改动汇总与基线 |
| [DATE_LOG_2026-09-21.md](DATE_LOG_2026-09-21.md) | 已实现 | 按问题→修改整理 2026-09-21 全部落地项：行宽契约、运行逻辑收尾、批次 A–F、停写 `experiment.json`、波形从属 |
| [DATE_LOG_2026-09-22.md](DATE_LOG_2026-09-22.md) | 已实现 | 已核实问题落地：CLI 复用顺序、Chirp 带宽与 transmit 预检、IERS、空产物、测试 scratch；R2 起 generated 不再当复用证据 |
| [RANGE_GATE_2026-09-23.md](RANGE_GATE_2026-09-23.md) | 已实现 | Chirp 只保留采集路径窗，删除秒制 ADC 保护；网格试例改为约 1 m 分辨的短脉冲 |
| [DATE_LOG_2026-09-24.md](DATE_LOG_2026-09-24.md) | 已实施 | 前沿半采样、文档口径和只读行视口；同日稍后补上脉宽可选单位、保存入口说明和观测计划卡片高度 |
| [GUI_UNIT_CONTROLS_2026-09-24.md](GUI_UNIT_CONTROLS_2026-09-24.md) | 已实施 | 统一脉宽单位顺序，收窄可选和固定单位框 |

尚未落地的设计统一放在 [../plans/](../plans/)；历史检查材料统一放在 [../audits/](../audits/)。
