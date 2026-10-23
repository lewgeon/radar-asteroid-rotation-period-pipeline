# 变更验证与证据留存策略（4.3）

本文件说明本仓库对"改了代码并要声称它对/更快"这类工作的最低要求，以及验收证据放在哪里。它不替代 `docs/4.3/vs_4.2/changes/` 下逐次变更的记录，而是约束这些记录怎么写、产物放哪里。研究实验独立存放在 `experiments/`，每日日志放 `logs/`，命名与整合规则以根目录 AGENTS.md 为准。

## 结论必须带作用域

每个对外声称的结论都要写清前提，并指出哪个配置项或代码路径保证了这个前提。例如"该精度在 $B\cdot T=10$ 时误差 1e-7"不能推导出"可以写成默认值"——必须给出误差随配置的上界，并确认配置确实约束了它。

## 性能结论必须同会话 A/B

绝对耗时在同机上也可能有 30% 量级波动（笔记本 GPU 热状态）。因此：

- 加速比只在**同一次会话内**的 A/B 之间比较；
- 记录基线来源（哪个运行目录/哪份产物、测量时间）与测量方式（重复次数、取最小值还是中位数）；
- 裁剪规模上测得的相对收益必须在目标规模上复核后才能写进结论。

## 测试矩阵必须能区分分支

写"两参考系 × 两运动模型"这类矩阵时，要有一条断言证明各格结果确实不同（`echo/tests/test_chirp_batching.py::test_fixture_separates_the_branches_it_claims_to_cover` 就是这个用途）。夹具退化时必须让测试变红，而不是让矩阵默默退化成单格。

批处理路径与逐脉冲路径的互比只能证明批处理没写错；物理正确性由改动前实现产生的 golden 值（`_TILTED_GOLDEN`）覆盖。

## 用户入口逐个分支验证

配置判别器的每个分支都要实际执行一次，例如波形（CW / chirp）、散射模型（mesh / point target）。`echo/tests/test_cli_smoke.py` 用真实子进程跑 `simulate_echo.py` 覆盖这两条波形；新增判别维度时应同步扩展。

## 证据分层

| 类别 | 内容 | 位置 | 架构大改时 |
| --- | --- | --- | --- |
| 不变量 | 测试与断言 | `echo/tests/`、`tests/`（仓库内，CI 运行） | 过时的删除，不保留 |
| 证据 | 变更说明、结论、命令、误差表 | 生产证据放 `changes/`、研究证据放 `experiments/`，均在 `docs/<版本>/vs_<上一版>/` 下；`logs/` 只作索引 | 旧数值／前提不改，后续追加独立阶段；用户授权整合时可迁移合并并维护引用 |
| 原始材料 | 日志、大文件、一次性脚本 | 仓库外（发布附件或临时目录） | 不保留，靠文档命令重建 |

发布归档用 `.gitattributes` 的 `export-ignore` 排除测试与内部证据目录：`echo/.gitattributes` 排除 `tests/**`，根目录 `.gitattributes` 排除各版本 `vs_<上一版>/**`（包括logs、changes、experiments和plans）。注意 gitattributes 的目录模式不会递归生效，必须写成 `dir/**`。

## 破坏性操作

递归删除、批量覆盖、通配符清理执行前必须先列出命中路径；重复执行同一条删除命令前要重新列目录确认当前状态。

## 交付前对抗性审查

交付前用全新上下文的子代理跑一轮"只负责挑错"的审查（提示词见用户级技能 `change-verification-discipline`），并把它的发现作为交付门槛。实现者不会自发否证自己，这一步是性价比最高的防线。

全局规则与技能的位置（在本仓库之外，供复核者了解上下文）：

- `C:\Users\35168\.codex\AGENTS.md` 中的"变更验证纪律（通用，任何项目都适用）"一节：每次会话都进上下文的硬规则。
- `C:\Users\35168\.agents\skills\change-verification-discipline\SKILL.md`：完整流程、交付前检查清单与对抗性审查提示词模板。

<a id="inversion-contracts"></a>

## 事前协议：契约实验

此段由原实验协议归入相应专题，记录当时设计及追加验证条件；不表示本次重新执行。

1. 配置只接受当前字段；废弃字段以及重复且冲突的物理量必须明确报错。
2. Chirp 的 ADC 时序、脉宽和路径支撑只由 ObservationPlan 提供给 echo。
3. Chirp CPI 使用秒数配置，并按回波元数据中的 PRF 转为整数脉冲数。
4. 点目标与 mesh 配置互斥裁剪，点目标幅度只使用 `amplitude_scale`。
5. 一维/二维 IQ 与所有行轴字段必须通过严格形状校验。

<a id="protocol-9"></a>

## 事前协议：全模块契约验收

此段由原实验协议归入相应专题，记录当时设计及追加验证条件；不表示本次重新执行。

### 可选反演功能验收

使用 `conda activate pytorch` 后执行 `python -m pytest -q tests/test_optional_period_methods.py tests/test_optional_period_gui.py --import-mode=importlib -p no:cacheprovider`（仓库根目录）。验收包括独立加权回归对照、八种可区分分支、显式极轴与一倍／两倍补偿、CW 拒绝新配置、真实 CPI 与逐脉冲路由、旧冻结结果、开关隐藏参数及比较报告防止陈旧结果。GUI 检查真实事件循环、两种窗口宽度、反复切换、焦点和滚动范围、配置 JSON 往返与非法子字段关闭。此验收证明功能与路由，不是未知形状高精度研究；一般形状精度收益仍待后续实验。

```powershell
conda activate pytorch
python -m pytest -q tests
python -m pytest -q inversion\tests
Push-Location observation; python -m pytest -q tests; Pop-Location
Push-Location echo; python -m pytest -q tests; Pop-Location
```

快速 smoke 只能证明链路可运行，不能冒充论文级复现。论文级实验还需要固定数据、参数、随机种子、硬件与误差指标，并记录训练或计算耗时。
