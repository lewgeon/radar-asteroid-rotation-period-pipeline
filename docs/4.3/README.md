# 4.3 通用文档

本目录存放 **4.3 版**的通用技术文档（当前工作版本）。4.2 已宣告完成，其通用文档冻结在 [../4.2/](../4.2/README.md)，不再回改。

4.3 的通用文档从 4.2 快照复制而来，描述的仍是 4.2 完成时的代码现状。后续只改本目录。

## 目录结构约定

```
docs/
├── 4.3/                 ← 当前版本的通用文档（唯一权威副本）
│   ├── README.md
│   ├── PROJECT_OVERVIEW.md
│   ├── ARCHITECTURE_V4.md
│   ├── GLOSSARY.md
│   ├── GUI_USER_MANUAL.md
│   ├── GUI_ARCHITECTURE.md
│   ├── OBSERVATION_TIME_SELECTION.md
│   ├── VERIFICATION_POLICY.md
│   ├── VISIBILITY_AND_STATION_TYPE.md
│   ├── images/
│   └── vs_4.2/          ← 相对 4.2 仍开放的问题与未实施方案
│       └── plans/
├── 4.2/                 ← 4.2 完成时的通用文档快照，含 vs_4.1 过程材料
├── 4.1/                 ← 4.1 版通用文档快照
└── _not_for_commit/     ← 未标版本、已废弃或不宜提交的文档（见 .gitignore）
```

约定：

1. **一个版本一个文件夹**。通用文档只写在当前版本的文件夹里。
2. **仍要做的事写在 `vs_4.2/plans/`**。已经在 4.2 落地的修改、当时的审计和已完成的计划留在 [../4.2/vs_4.1/](../4.2/vs_4.1/README.md)，不搬进本目录。
3. **路径引用一律写仓库根相对路径**（如 `docs/4.3/PROJECT_OVERVIEW.md`）。
4. 旧版本文件夹是**快照**：发现旧版本描述与代码不符时不回改旧版本，而是在新版本的 `vs_<上一版>/` 中说明。

## 本版入口

- 项目全貌与运行方式：[PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)
- schema v4 架构与字段归属：[ARCHITECTURE_V4.md](ARCHITECTURE_V4.md)
- 字段释义表：[GLOSSARY.md](GLOSSARY.md)
- GUI 操作手册：[GUI_USER_MANUAL.md](GUI_USER_MANUAL.md)
- GUI 工程架构：[GUI_ARCHITECTURE.md](GUI_ARCHITECTURE.md)
- 观测选时与接收窗口生成规范：[OBSERVATION_TIME_SELECTION.md](OBSERVATION_TIME_SELECTION.md)
- 可见性与测站类型：[VISIBILITY_AND_STATION_TYPE.md](VISIBILITY_AND_STATION_TYPE.md)
- 变更验证与证据留存策略：[VERIFICATION_POLICY.md](VERIFICATION_POLICY.md)
- 相对 4.2 仍开放的问题与未实施方案：[vs_4.2/README.md](vs_4.2/README.md)
