# 4.2 通用文档（快照）

本目录是 **4.2 版**通用文档的完成快照。4.2 已宣告完成，这里不再更新。当前工作版本的通用文档、仍开放的问题和未实施方案在 [../4.3/](../4.3/README.md)。

## 目录结构约定

```
docs/
├── 4.3/                 ← 当前工作版本（通用文档、开放问题、未实施方案）
├── 4.2/                 ← 本目录：4.2 完成快照
│   ├── README.md        ← 本文件
│   ├── PROJECT_OVERVIEW.md
│   ├── ARCHITECTURE_V4.md
│   ├── GLOSSARY.md
│   ├── GUI_USER_MANUAL.md
│   ├── GUI_ARCHITECTURE.md
│   ├── OBSERVATION_TIME_SELECTION.md
│   ├── VERIFICATION_POLICY.md
│   ├── VISIBILITY_AND_STATION_TYPE.md
│   ├── images/
│   └── vs_4.1/          ← 4.2 相对 4.1 的已实现变更、审计与当时的计划
│       ├── changes/
│       ├── audits/
│       └── plans/
├── 4.1/                 ← 4.1 版通用文档快照（自 git commit f6f3e16 导出，不再更新）
└── _not_for_commit/     ← 未标版本、已废弃或不宜提交的文档汇总目录（见 .gitignore）
```

约定：

1. **一个版本一个文件夹**。通用文档只写在当时的版本文件夹里。4.2 完成后，继续修改的通用文档在 `docs/4.3/`。
2. **版本差异写在 `vs_<上一版>/` 子目录并按状态分区**。`changes/` 只放已实现修改，`audits/` 只放历史检查材料，`plans/` 只放方案；三类文档不能混放。4.2 结束时仍未实施的计划已迁到 `docs/4.3/vs_4.2/plans/`。
3. **路径引用一律写仓库根相对路径**（如 `docs/4.2/PROJECT_OVERVIEW.md`），便于跨版本比较与全局搜索。
4. 旧版本文件夹是**快照**：发现旧版本描述与代码不符时不回改旧版本，而是在新版本的 `vs_<上一版>/` 中说明。

## 本版入口

- 项目全貌与运行方式：[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)
- schema v4 架构与字段归属：[ARCHITECTURE_V4.md](ARCHITECTURE_V4.md)
- 字段释义表：[GLOSSARY.md](GLOSSARY.md)
- GUI 操作手册：[GUI_USER_MANUAL.md](GUI_USER_MANUAL.md)
- GUI 工程架构：[GUI_ARCHITECTURE.md](GUI_ARCHITECTURE.md)
- 观测选时与接收窗口生成规范：[OBSERVATION_TIME_SELECTION.md](OBSERVATION_TIME_SELECTION.md)
- 变更验证与证据留存策略：[VERIFICATION_POLICY.md](VERIFICATION_POLICY.md)
- 本版改动（相对 4.1）：[vs_4.1/README.md](vs_4.1/README.md)
- 4.2 结束后仍开放的问题：[../4.3/vs_4.2/README.md](../4.3/vs_4.2/README.md)
