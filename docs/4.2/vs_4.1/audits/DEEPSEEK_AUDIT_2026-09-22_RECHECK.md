# 对 2026-09-22 两轮 DeepSeek 质检的核实

> 对象：[`deepseek_audit_2026-09-22_1.md`](deepseek_audit_2026-09-22_1.md)、[`deepseek_audit_2026-09-22_2.md`](deepseek_audit_2026-09-22_2.md)。第一份另写了 [`DEEPSEEK_AUDIT_RESPONSE_RECHECK_2026-09-22.md`](DEEPSEEK_AUDIT_RESPONSE_RECHECK_2026-09-22.md)，并在 [`../plans/REVIEW_2026-09-21_ROUND2.md`](../plans/REVIEW_2026-09-21_ROUND2.md) 的 B2、B11 两节加了更正块。
> 本文只记录核实结论。R2 随后已落地，见 [`../changes/DATE_LOG_2026-09-22.md`](../changes/DATE_LOG_2026-09-22.md) 第 10 节；对外说明见 [`DEEPSEEK_AUDIT_RESPONSE_2026-09-22_ROUND2.md`](DEEPSEEK_AUDIT_RESPONSE_2026-09-22_ROUND2.md)。上一轮回执仍以 [`DEEPSEEK_AUDIT_RESPONSE_2026-09-22.md`](DEEPSEEK_AUDIT_RESPONSE_2026-09-22.md) 为准。

两份都同意：**09-22 针对 B1 / B3 / B5 / B11 / B12 / B7–B9 的功能修复是真的。** 本机此前 `conda run -n pytorch python scripts/run_all_tests.py` 为根 118、observation 69、echo 44、inversion 24+3，与第二份在 pytorch 环境直跑 observation/echo/inversion 的数字一致。根组不再因 IERS 挂死，两份都复现了这一点。

需要分开看的是「还剩什么」和「回执有没有写错」。

---

## 1. 总表

| 条目 | 来源 | 判定 |
|---|---|---|
| B1 三步序列（不给旗标拒绝且不写观测/回波 generated；给旗标只写 inversion generated；再去掉旗标仍拒绝） | 两份 | **成立，修复正确** |
| B12 缺带宽：observation 过、echo/full 拒；0 带宽拒；CW 无带宽过 | 两份 | **成立，修复正确** |
| B11 残缺 transmit：observation/echo 拒、inversion 不查；失败句是字段路径，不是 `KeyError` | 两份 | **成立，修复正确** |
| B5 IERS：observation 组不再挂起 | 两份 | **成立，修复有效** |
| B3 空 npz 不可复用 | 两份 | **成立，修复正确** |
| WebEngine 占位已删；`.gitignore` 有 `.tmp_*/`；`manifest.json` 仍写、无 `experiment.json` | 第 2 份 | **成立** |
| 上一轮 B2 写重、B11 `KeyError` 写错 | 两份自我更正 | **同意**（与 09-22 早先核实一致） |
| 上一轮「28% = 管道死锁」归因错误；旧 run 不能证明仍写 `echo_overlap` | 第 2 份自我更正 | **同意** |
| **R2** 失败运行留下 generated，随后可静默复用陈旧 npz | 第 1 份（第 2 份未单列，但机制与 leftover generated 相同） | **成立**，是 09-22 修复未覆盖的洞 |
| **R1** scratch 建在 `tmp/`，该目录不可写时根组 68 条 `WinError 5` | 两份 | **机制成立，环境相关**；本机 `tmp/` 可写，故测不到 68 失败 |
| **R3** `--python` 指向不存在的解释器时 CLI 抛 `FileNotFoundError` 栈 | 第 1 份 | **成立**，低；GUI 已有启动失败分支 |
| **R4** 「根 118 passed」是可写 `tmp/` 环境下的数字 | 两份 | **成立作为口径**，不是产品逻辑错误 |
| 回执里两处「澶辫触」是文档编码缺陷，应改回「失败」 | 第 2 份 | **不成立**。那是在引用质检原文的乱码显示，启发式会误判 |
| 回执 §3.1「源文件从来没乱码」与字节证据不符；当时写坏、后来重写修好 | 第 2 份 | **不能据此改判**。`Select-String` 用系统代码页读无 BOM 的 UTF-8，本来就会把「失败」显示成「澶辫触」；`run_all_tests.py` 本轮未改、现文是正确 UTF-8；契约测试变大是因为 09-22 加了用例，不是「编码修复」 |
| conda 入口写死 `pytorch` | 第 2 份 | **属实，已记录为取舍**，不是新缺陷 |
| 卡住的 GUI 用例名在相邻用例间漂移 | 第 1 份 | **可接受**。机制仍是 IERS，`.gui_state` 缓存会使卡点略有移动 |

---

## 2. 两份都确认正确的修复（本机未再跑四组，只核代码与探针）

与 [`DEEPSEEK_AUDIT_RESPONSE_RECHECK_2026-09-22.md`](DEEPSEEK_AUDIT_RESPONSE_RECHECK_2026-09-22.md) §2 一致，不重复命令。代码现状：

- CLI：`check_reusable_artifact` 在 `write_json(*.generated.json)` 之前；跳过观测/回波时不写这两份；无指纹且无可用 generated 时必须 `--allow-legacy-reuse`。
- `normalize_echo_config`：Chirp 缺 `bandwidth_hz` 或 `<= 0` 失败。
- `_require_complete_chirp_transmit` 只挂在 `observation` / `echo` / `full_pipeline`。
- `require_stage_artifact` 在 `write_stage_success` 与 `check_reusable_artifact` 之前。
- `iers_policy.disable_iers_auto_download` 由 `ephemeris`、`campaign_planning` 和两处 conftest 调用。

这些与回执声称相符。

---

## 3. 成立的新问题

### 3.1 R2：失败运行留下的 generated 仍能为陈旧产物作证（真）

09-22 只堵住了「判定**之前**写入」和「**跳过**阶段时覆盖历史 generated」。当前 CLI 在判定通过之后、`run_step` **之前**仍会写 generated（`pipeline.py` 约 965–969 行）。全流程且不 skip 时，观测尚未跑完就会写下 `observation.generated.json` 和 `echo.generated.json`。

`check_reusable_artifact` 在没有阶段指纹时，只要磁盘上的 `*.generated.json` 能重建出与**当前**配置相同的指纹，就打印「复用已有…」，不再要 `--allow-legacy-reuse`。这份 generated 证明的是「上次启动时打算用什么配置」，不是「npz 确实按该配置算完」。

本机探针（合法 stub npz、无 `stage_manifest.json`）：

| 步骤 | 观测复用 |
|---|---|
| 尚未写 generated | `reusable=False`，`requires_confirmation=True`（缺少阶段指纹） |
| 写入与当前 `prepare_run` 一致的 `observation.generated.json` | `reusable=True`，理由「复用已有观测信息」 |

这与第一份用坏解释器跑一次再 `--skip-observation --skip-echo` 的路径同类：子进程没成功，generated 已是新配置，旧 npz 形状仍与契约相容（例如都是 8×252），就会进 inversion。回执 §5.1 的三步序列测的是「跳过时不写观测/回波 generated」，**测不到**这条失败残留。

GUI 已改为只写**当前阶段**的 generated，比 CLI 全流程一次写观测+回波略窄，但该阶段启动失败后，那一份 generated 同样会留下。

这不是 B1 回退，是 generated 双重身份（历史证据 / 子进程输入）还没拆干净。

### 3.2 R1：`tmp/` 不可写时根测试整片失败（真，但是环境）

`tests/scratch.py` 与 GUI `_workspace_tmp` 都在 `ROOT/tmp/` 下 `mkdir`。本机探针：`tmp/` 存在且可建目录，故维护者会话里根组能到 118 passed。

质检沙箱：仓库根可写、`tmp/` 没有那条写 ACE，于是 68 条在 `mkdir` 上 `WinError 5`（57 GUI + 6 artifact + 5 schema，与第一份拆分相符）。把 scratch 从仓库根 `.tmp_*` 迁到 `tmp/`，在**那种**令牌下失败面比「只有 4 条 tempfile」更大。echo/observation/inversion 的 `tmp/` 在他们环境仍可写，所以那三组数字仍与回执一致。

这不是回波或复用逻辑错误。严重度「高」只相对「该沙箱里根组不能当验收」；对约定环境（conda `pytorch` 且 `tmp/` 可写）不成立。回退到仓库根 `.tmp_*`（已 gitignore）或先探测可写性，属于测试基建可移植性，不是 09-22 功能修复失败。

### 3.3 R3：缺失解释器时 CLI 原始 traceback（真，低）

`run_step` 直接 `subprocess.run(...)`。本机对不存在的可执行文件得到 `FileNotFoundError`（WinError 2），不会走进「退出码非 0 → 中文 SystemExit」。GUI `_process_error` 对 `FailedToStart` 已有中文收尾。CLI 对齐一句中文错误是体验项；与 R2 一起在失败时删 generated 才有产品含义。

### 3.4 R4：118 的口径（真，低）

「根 118 passed」应读作：在本机可写 `tmp/` 的 pytorch 环境。第一份 50/68 与第二份根组 50 failed 描述的是另一套 ACL。observation / echo / inversion 三组不依赖根 `tmp/`，两份与回执一致。

---

## 4. 不成立或过重的条目

### 4.1 回执两处「澶辫触」是编码缺陷

第二份用「中文串 GBK 编码再当 UTF-8 解码」扫描，命中回执里恰好两处「澶辫触」，还原为「失败」。

那两处上下文是：

- 「质检里贴出的『澶辫触』『瑙傛祴…』对照源文件字节」
- 「会把『失败：』『上游产物不兼容』显示成『澶辫触』『涓婃父…』」

正文其余中文是正常 UTF-8。若整份回执曾按 GBK 误存，不会只有两处乱码。探针：`失败`.encode('utf-8').decode('gbk') 正是 `澶辫触`。启发式把**故意引用的乱码样例**判成文件损坏。把这两处改成「失败」反而没法说明质检当时屏幕上看到的是什么。

### 4.2 「当时源文件写坏、09-22 重写修好」

两份质检讨论的 `scripts/run_all_tests.py` 与 `tests/test_artifact_contract.py` 目前都是 **untracked**，git 里没有 09-21 的已提交副本可对照。

当前字节：`run_all_tests.py` 含 UTF-8「失败：」，不含「澶辫触」，本轮回执对应的代码修改**没有改过该脚本**。契约测试现 9862 字节、断言为「上游产物不兼容」等正确中文；体积变大是因为 09-22 增加了无指纹复用、legacy 不写 generated 等用例，不是「只做了编码修复」。

PowerShell 5 的 `Select-String` 对无 BOM 的 UTF-8 常用系统 ANSI（GBK）去读，会把本来正确的「失败」打成「澶辫触」。这与 09-21 第一份贴出的显示相同，**不能单独当作「磁盘上的源文件曾是乱码」的证据**。因此回执 §3.1 的判断（对照当时工作区 UTF-8 源文件，乱码来自阅读环境）仍然成立；也不需要为 `run_all_tests.py` 补一条「编码修复」记录。

若质检环境曾把文件**另存为**错误代码页，那是该环境的本地副本，不是当前树能核到的历史。

### 4.3 把 R1 写成功能修复失败

09-22 把 scratch 放进 `tmp/` 的动机是：系统 `tempfile` 在部分 Windows 令牌上 ACL 过严，且仓库根 `.tmp_*` 曾进 `git status`。在 `tmp/` 可写的机器上，这个动机成立（根组能跑完）。在 `tmp/` 单独不可写的沙箱里，它会换成另一种失败。两份都建议「探测可写性再回退」，作为增强合理，但不能推翻「功能修复是否正确」。

---

## 5. 两份质检之间

第一份把 R1 标成高、R2 标成中，并承认上一轮 B2/B11 写错。第二份把功能修复全部打勾，把 scratch 写成可移植性可选项，另开「回执编码」和「乱码归因」。对 **R2 的失败残留 generated**，完整复现写在第一份；第二份没有单独成段，但 leftover generated 与 B1 兜底的关系是同一机制。

卡住 GUI 用例名：第一份本轮栈是 `test_mode_switch_does_not_unparent_visible_widgets`，上一轮是 `test_mixed_stations_…`。第二份解释为 IERS + `.gui_state` 使卡点漂移。与「主因是 IERS 不是管道」不冲突。

---

## 6. 建议的后续（尚未实施）

若继续改代码，优先：

1. **R2**：generated 只在该阶段即将 `run_step` 前写入；该阶段失败则删除刚写的那一份；或判定复用时**只**承认 `stage_manifest.json` 里带指纹且 `output_sha256` 对得上的记录，不再把「与当前配置相同的 generated」当作产物来源证明。
2. **R1（可选）**：`scratch_directory` / `_workspace_tmp` 在 `tmp/` 的 `mkdir` 失败时回退到仓库根 `.tmp_*`。
3. **R3（可选）**：`run_step` 捕获 `FileNotFoundError`/`OSError`，改成一句中文退出。
4. 文档：验收数字旁注明「根组依赖仓库根 `tmp/` 可写」。不要把回执里引用的乱码样例改成「失败」。

conda 开关、`.obj` 内容哈希、CW 残留 `radar_system`、`echo_overlap` 内存字段、inversion 脚本契约：两份都同意维持取舍。
