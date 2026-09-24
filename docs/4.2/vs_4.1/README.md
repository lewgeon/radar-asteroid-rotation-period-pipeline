# 4.1 → 4.2 修改说明

本目录存放 **4.2 版相对 4.1 版**的已实现变更、历史审计和未实施方案。三类材料按状态分目录存放，避免把计划误读成已经完成的功能，也避免把审计当时的状态误读成当前状态。
本版通用文档（描述 4.2 现状的权威副本）在上一层目录 [../](..) 中。

## 已实现变更

| 文档 | 内容 |
|---|---|
| [changes/OBSERVATION_RECEPTION_WINDOW.md](changes/OBSERVATION_RECEPTION_WINDOW.md) | 观测解算的接收窗原点改为与保存行整数网格对齐，并说明它对 `rx_adc_start_elapsed_s`、`row_start_sample` 的影响 |
| [changes/GUI_LOG_AND_OUTPUT.md](changes/GUI_LOG_AND_OUTPUT.md) | GUI 日志渲染与产物输出改造：HTML 实体、协议控制行、运行状态收尾、产物路径和结果摘要 |
| [changes/ECHO_SIMULATION_PERFORMANCE_PHASE_A.md](changes/ECHO_SIMULATION_PERFORMANCE_PHASE_A.md) | Chirp 网格回波阶段 A 加速：缓存旋转常量、减少同步、过滤跨 Run 空循环，并为当前测试网格使用实测 chunk |
| [changes/ECHO_SIMULATION_PERFORMANCE_PHASE_B.md](changes/ECHO_SIMULATION_PERFORMANCE_PHASE_B.md) | Chirp 网格回波阶段 B 加速：跨脉冲向量化、确定性 Run 级归并、显存退避与完整 60000 脉冲实测 |
| [changes/ECHO_SIMULATION_PERFORMANCE_PHASE_C.md](changes/ECHO_SIMULATION_PERFORMANCE_PHASE_C.md) | Chirp 网格回波阶段 C：本体系视线重排、float64 包络与分块默认值 |
| [changes/CW_LAYOUT_AND_CONFIG_GUARDRAILS.md](changes/CW_LAYOUT_AND_CONFIG_GUARDRAILS.md) | CW 行轴契约、选时校验与示例配置清理 |
| [changes/CHIRP_ROW_CONTRACT_2026-09-21.md](changes/CHIRP_ROW_CONTRACT_2026-09-21.md) | Chirp 末列与 observation↔echo 行宽契约 |
| [changes/RUNTIME_LOGIC_FIXES_2026-09-21.md](changes/RUNTIME_LOGIC_FIXES_2026-09-21.md) | 可见性语义、单脉冲批处理退避与 09-21 文档勘误 |
| [changes/CONFIG_FINGERPRINT_AND_GUI_SEAM_2026-09-21.md](changes/CONFIG_FINGERPRINT_AND_GUI_SEAM_2026-09-21.md) | 阶段化 `prepare_run`、产物指纹复用与 GUI/CLI 统一入口 |
| [changes/WAVEFORM_OWNERSHIP_2026-09-21.md](changes/WAVEFORM_OWNERSHIP_2026-09-21.md) | `observation.transmit` 承载 PRF/脉宽；射频类型只写 `echo.waveform.type` |
| [changes/DATE_LOG_2026-09-21.md](changes/DATE_LOG_2026-09-21.md) | 2026-09-21 当日修改总录：问题与对应改法 |
| [changes/DATE_LOG_2026-09-22.md](changes/DATE_LOG_2026-09-22.md) | 2026-09-22：CLI 复用判定顺序、阶段预检、IERS 与空产物 |
| [changes/RANGE_GATE_2026-09-23.md](changes/RANGE_GATE_2026-09-23.md) | Chirp 采集路径窗取代秒制保护，两侧半采样补偿，网格试例改为约 1 m 分辨 |
| [changes/DATE_LOG_2026-09-24.md](changes/DATE_LOG_2026-09-24.md) | 2026-09-24：前沿半采样、文档口径、只读行视口 |

## 审计与未实施方案

| 目录 | 状态约定 | 内容 |
|---|---|---|
| [changes/](changes/) | 已实现 | 已在 4.2 代码中落地并具有验收证据的行为变化 |
| [audits/](audits/) | 历史快照 | 审计、复核和死代码扫描；其中状态只代表审计当时 |
| [plans/](plans/) | 4.2 当时的方案 | 已实施或已被 changes 取代的方案留在这里。ADC 职责迁移和仍开放的问题已迁到 `docs/4.3/vs_4.2/plans/` |

## 通用文档的更新

4.2 中更新或新增的通用文档（相对 4.1 快照）：

- `PROJECT_OVERVIEW.md`：按当前模块边界修订（见该文件自身内容）。
- `GUI_USER_MANUAL.md`：补充运行目录、日志与产物路径、阶段复用的操作说明。
- `OBSERVATION_TIME_SELECTION.md`：**新增**，观测选时与接收窗口生成的完整规范（4.1 时期该内容只散落在代码与审计报告中）。
- `GLOSSARY.md`：采集路径窗取代秒制 `pre_guard_s` / `post_guard_s`。
- `ARCHITECTURE_V4.md`、`GUI_ARCHITECTURE.md`：与 4.1 相同。

## 阅读约定

1. 本目录中的路径引用一律写作**仓库根相对路径**（如 `docs/4.2/PROJECT_OVERVIEW.md`），便于跨版本检索；在 Markdown 预览中不保证可点击。
2. 审计报告中的行号、文件名对应**修改前（4.1）**的代码状态，属于历史记录，不随 4.2 代码回改。其中写作 `docs/<文件名>` 的引用指 [../../4.1/](../../4.1/) 中的同名快照。
3. 版本差异只写在这里；通用文档只描述当前版本的行为，不写「4.1 曾如何」。
4. `plans/` 中的文档不得写成已经交付的功能；方案实施并完成测试后，应在 `changes/` 中整理实际变更和验收结果。
