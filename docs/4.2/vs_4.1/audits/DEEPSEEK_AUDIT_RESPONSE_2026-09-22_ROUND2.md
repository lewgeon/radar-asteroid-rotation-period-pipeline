# 对 2026-09-22 两轮 DeepSeek 质检的回执

> 对象：[`deepseek_audit_2026-09-22_1.md`](deepseek_audit_2026-09-22_1.md)、[`deepseek_audit_2026-09-22_2.md`](deepseek_audit_2026-09-22_2.md)。第一份另写了 [`DEEPSEEK_AUDIT_RESPONSE_RECHECK_2026-09-22.md`](DEEPSEEK_AUDIT_RESPONSE_RECHECK_2026-09-22.md)，并在 [`../plans/REVIEW_2026-09-21_ROUND2.md`](../plans/REVIEW_2026-09-21_ROUND2.md) 的 B2、B11 两节加了更正块。
> 本文是回执：说明我们如何核对这两份「修复是否正确」的质检、哪些是误判、哪些是真实遗留、随后改了什么。条目级只读核实见 [`DEEPSEEK_AUDIT_2026-09-22_RECHECK.md`](DEEPSEEK_AUDIT_2026-09-22_RECHECK.md)；R2 落地见 [`../changes/DATE_LOG_2026-09-22.md`](../changes/DATE_LOG_2026-09-22.md) 第 10 节。
> 上一轮（针对 09-21 质检）的回执仍以 [`DEEPSEEK_AUDIT_RESPONSE_2026-09-22.md`](DEEPSEEK_AUDIT_RESPONSE_2026-09-22.md) 为准，本文不重复那七项修复的细节。
> 环境：Windows + conda `pytorch`，本机仓库根 `tmp/` **可写**。不修改 inversion 估计算法，不实施 ADC 布局迁移，不批量删除历史 `tmp/`。

两份质检都同意：**09-22 针对 B1 / B3 / B5 / B11 / B12 / B7–B9 的功能修复是真的。** 我们同意。分歧在「还剩什么」：一份抓住了 leftover generated 仍能静默复用（R2），这是真洞；一份把回执里引用的乱码样例当成文档编码缺陷，这是误判。根组 68 条失败出在他们沙箱里 `tmp/` 不可写，不是复用或回波计算错误。

---

## 1. 我们怎样核查

没有按质检原文立刻改代码。先对照当时工作区把每条说成「还没修好 / 新缺陷」的机制走一遍，能复现的才进修改。

1. **把「修复是否落地」和「是否还有洞」拆开。** 两份都实测了 B1 三步序列、缺带宽按阶段拒绝、残缺 transmit、空 npz、IERS 后观察组不再挂起。这些与当时代码相符，当作已修项，不再重做。
2. **对 leftover generated 做只读探针，不依赖他们沙箱里的坏解释器。** 合法 stub npz、无 `stage_manifest.json`：尚未写 generated 时 `reusable=False` 且要确认；写入与当前配置一致的 `observation.generated.json` 后变成 `reusable=True`、「复用已有观测信息」。这与第一份用坏解释器跑一次再 `--skip-observation --skip-echo` 的路径同类。
3. **核对 CLI 写入点。** 当时判定虽已移到写入之前，但全流程仍会在任何 `run_step` 之前写齐三份 generated。观测还没跑完，回波 generated 已经落盘。B1 的三步序列测的是「跳过时不写观测/回波 generated」，测不到这条失败残留。
4. **把本机 `tmp/` 可写与沙箱 `tmp/` 不可写分开。** 本机 `tmp/` 可建目录，根组能跑完。质检沙箱仓库根可写、`tmp/` 没有那条写 ACE，68 条失败全在 `mkdir` 的 WinError 5。echo / observation / inversion 三组不依赖根 `tmp/`，数字与回执一致。
5. **对「澶辫触」做字节对照，不信启发式。** 上一轮回执里恰好两处「澶辫触」，上下文是在引用质检屏幕上的乱码显示。`失败`.encode('utf-8').decode('gbk') 正是 `澶辫触`。正文其余中文是正常 UTF-8。
6. **不把 PowerShell `Select-String` 的显示当成「当时源文件写坏」。** 无 BOM 的 UTF-8 用系统 ANSI 去读，会把本来正确的「失败」打成「澶辫触」。`run_all_tests.py` 本轮功能修复没有改过；契约测试变大是因为加了无指纹复用等用例。
7. **缺失解释器。** `--python` 指向不存在的可执行文件时，CLI 抛 `FileNotFoundError`，不会走进「退出码非 0 → 中文 SystemExit」。GUI 对启动失败已有中文收尾。
8. 核实结论先交给维护者。维护者确认此前 `runs/` 都是测试、没有论文级结果需要靠 leftover generated 自动复用后，才改复用门。落地后用 `conda run -n pytorch python scripts/run_all_tests.py` 跑四组测试，并对复用门做了对抗性复查。

---

## 2. 总表

| 质检条目 | 来源 | 我们的判定 | 处理 |
|---|---|---|---|
| B1 / B12 / B11 / B5 / B3 / B7–B9 功能修复实测通过 | 两份 | **同意，属实** | 不重做 |
| 上一轮 B2 写重、B11 `KeyError` 写错 | 两份自我更正 | **同意** | 不改代码；ROUND2 已有更正块 |
| 上一轮「28% = 管道死锁」归因错误；旧 run 不能证明仍写 `echo_overlap` | 第 2 份自我更正 | **同意** | 不改 |
| **R2** 失败运行留下 generated，随后可静默复用陈旧 npz | 第 1 份（第 2 份未单列，机制相同） | **真实错误** | 已改：generated 不再当复用证据 |
| **R1** scratch 建在 `tmp/`，该目录不可写时根组 68 条 `WinError 5` | 两份 | **机制成立，环境相关** | 不改；约定环境 `tmp/` 可写 |
| **R3** `--python` 指向不存在的解释器时 CLI 抛 `FileNotFoundError` 栈 | 第 1 份 | **属实，低** | 不改 |
| **R4** 「根 118 passed」是可写 `tmp/` 环境下的数字 | 两份 | **成立作为口径** | 文档注明环境；不是产品逻辑错误 |
| 回执两处「澶辫触」是文档编码缺陷，应改回「失败」 | 第 2 份 | **误判** | 不改那两处引用 |
| 回执 §3.1「源文件从来没乱码」与字节证据不符；当时写坏、后来重写修好 | 第 2 份 | **不能据此改判** | 不为 `run_all_tests.py` 补「编码修复」 |
| conda 入口写死 `pytorch` | 第 2 份 | **属实，已记录为取舍** | 不增加 `--python` 覆盖 |
| 卡住的 GUI 用例名在相邻用例间漂移 | 第 1 份 | **可接受** | 机制仍是 IERS，已关自动下载 |

---

## 3. 误判

### 3.1 上一轮回执两处「澶辫触」是编码缺陷

第二份用「中文串 GBK 编码再当 UTF-8 解码」扫描，命中上一轮回执里恰好两处「澶辫触」，还原为「失败」，建议改回「失败」。

那两处上下文是在**引用**质检当时屏幕上的乱码显示，用来说明阅读环境把「失败：」显示成了什么。正文其余中文是正常 UTF-8。若整份回执曾按 GBK 误存，不会只有两处乱码。把这两处改成「失败」，反而没法对照质检原文。因此没有改。

### 3.2 「当时源文件写坏、09-22 重写修好」

第二份根据 09-21 的 `Select-String` 输出、契约测试字节变大、`run_all_tests.py` 的 mtime，推断当时磁盘上的源文件是乱码、后来被就地重写修好，因而上一轮回执 §3.1 归因不准。

对照当时工作区 UTF-8 源文件：`run_all_tests.py` 含「失败：」，不含「澶辫触」，09-22 功能修复**没有改过该脚本**。契约测试变大是因为增加了无指纹复用、legacy 不写 generated 等用例，断言仍是「观测计划为 252 列，回波为 251 列」「上游产物不兼容」。

PowerShell 5 的 `Select-String` 对无 BOM 的 UTF-8 常用系统 ANSI（GBK）去读，会把本来正确的「失败」打成「澶辫触」。这与 09-21 第一份贴出的显示相同，**不能单独当作「磁盘上的源文件曾是乱码」的证据**。上一轮回执 §3.1 仍然成立；也不需要为 `run_all_tests.py` 补一条「编码修复」。

若质检环境曾把文件另存为错误代码页，那是该环境的本地副本，不是当前树能核到的历史。

### 3.3 把 R1 写成功能修复失败

把 scratch 放进 `tmp/` 的动机是：系统 `tempfile` 在部分 Windows 令牌上 ACL 过严，且仓库根 `.tmp_*` 曾进 `git status`。在 `tmp/` 可写的机器上，这个动机成立，根组能跑完。在 `tmp/` 单独不可写的沙箱里，失败面会从少数 tempfile 换成 68 条 `mkdir`。这是测试基建在两种沙箱之间的权衡，不能推翻「B1 / B5 / B12 等功能修复是否正确」。

---

## 4. 现象成立、但不按原文严重度处理的项

**R1。** 机制属实：根测试 scratch 与 GUI `_workspace_tmp` 都在仓库根 `tmp/` 下建目录。质检沙箱该目录不可写，根组 50 passed / 68 failed，拆分 57 GUI + 6 artifact + 5 schema 与第一份相符。observation / echo / inversion 三组数字与回执一致。严重度「高」只相对「该沙箱里根组不能当验收」；对约定环境（conda `pytorch` 且 `tmp/` 可写）不成立。本轮不增加「探测可写性再回退仓库根 `.tmp_*`」。

**R3。** `--python` 指向不存在的解释器时，CLI 抛原始 `FileNotFoundError`。GUI 已有启动失败的中文收尾。这是体验项。维护者未要求本轮包一层中文 `SystemExit`。失败时也不再需要「顺手删 generated」来堵复用洞——R2 已让 leftover generated 不能当证据。

**R4。** 「根 N passed」应读作：在本机可写 `tmp/` 的 pytorch 环境。两份在沙箱里看到的 50/68 描述的是另一套 ACL。observation 69 / echo 44 / inversion 24+3 不依赖根 `tmp/`，两份与本机一致。

**conda 入口。** `run_all_tests.py` 写死 `conda run -n pytorch` 属实。这是仓库约定。质检沙箱没有该环境或该入口挂住，不能据此否定约定环境里的验收数字。本轮仍不为它增加 `--python` 覆盖。

---

## 5. 真实错误，以及做了什么修改

下列修改不改变合法完整配置的数值结果。细节与区分测试见 [`../changes/DATE_LOG_2026-09-22.md`](../changes/DATE_LOG_2026-09-22.md) 第 10 节。

### 5.1 R2：leftover generated 仍能为陈旧产物作证

B1 只堵住了「判定**之前**写入当前配置」。当时 CLI 在判定通过之后、子进程跑完之前仍会写 generated。观测失败时，回波 generated 也可能已经落盘。`check_reusable_artifact` 在没有阶段指纹时，只要磁盘上的 generated 能重建出与**当前**配置相同的指纹，就打印「复用已有…」，不再要 `--allow-legacy-reuse`。

这份文件证明的是「上次启动时打算用什么配置」，不是「npz 确实按该配置算完」。子进程没成功、旧 npz 形状仍与契约相容（例如都是 8×252）时，就会进 inversion。第一份用坏解释器跑一次再 skip 上游、不给旗标，复现了这条路径。上一轮回执 §5.1 的三步序列测不到它。

维护者确认此前测试 run 不再使用、没有论文级结果需要靠 leftover generated 自动复用。因此不保留「generated 一致即可静默复用」这条兼容路径。

修改：

1. `check_reusable_artifact` **不再打开** `*.generated.json`。自动复用只认 `stage_manifest.json`：指纹一致，且记录里有文件哈希并与当前文件一致。
2. 没有指纹、或有指纹但缺哈希：GUI 确认，CLI 要 `--allow-legacy-reuse`。指纹不一致：硬阻断。
3. CLI 把各阶段 generated 的写入挪到该阶段 `run_step` 正前方。观测失败不会预先写下回波 generated；行宽契约失败不会预先写下反演 generated。GUI 本来就只写当前阶段。
4. 原先靠「只写 generated、不写指纹」假装可复用的 GUI / schema 测试，改为 `write_stage_success`。另补：leftover generated + 合法 stub、无指纹 → 不得静默复用；CLI 同样路径不得启动 inversion。

对抗性复查还指出两个相邻缺口，一并收紧（质检原文未单列，但是同一扇门）：

- 记录里**有**指纹，当前配置却算不出指纹（例如 `through_stage=inversion` 吞掉 echo 规范化错误）时，旧实现落到「缺指纹」兼容路径。现改为硬阻断，兼容开关也不过。
- 指纹相同但记录里**没有** `output_sha256` 时，旧实现仍自动复用，改写 npz 也拦不住。现改为要确认 / `--allow-legacy-reuse`。有哈希且对不上则仍硬阻断。

### 5.2 文档口径

用户手册、指纹专题勘误、GUI 日志专题：自动复用只认阶段指纹；generated 是子进程输入，不是复用证据。上一轮策略书里「没有指纹时退而求其次用 leftover generated」的句子已改成与现行规则一致。核实文档文首注明 R2 随后已落地，不回写当时的只读探针表。

---

## 6. 质检里确认正确、因而没有再动的部分

- B1 三步序列：不给旗标拒绝且不写观测/回波 generated；给旗标只写 inversion generated；再去掉旗标仍拒绝。
- Chirp 缺 `bandwidth_hz`：`through_stage=observation` 通过，echo / full_pipeline 拒绝；0 带宽拒绝；连续波无带宽通过。
- 残缺 `transmit`：observation / echo 给出字段路径中文错误；inversion 不查。不是 `KeyError`。
- 观察组关闭 IERS 自动下载后不再挂起。
- 空 npz 不可复用，`--allow-legacy-reuse` 也不能把空文件当成功产物。
- WebEngine 占位已删；`.gitignore` 有 `.tmp_*/`；仍写 `manifest.json`，不写 `experiment.json`。
- 可见性字段拒绝范围、夹具已去掉 `observation.visibility`：两份已复现，本回执不重复展开。

---

## 7. 明确未按质检建议修改的项

| 建议 | 未改原因 |
|---|---|
| 把上一轮回执里的「澶辫触」改回「失败」 | 那是引用质检显示，不是文件损坏 |
| 为 `run_all_tests.py` 补「编码修复」记录 | 该脚本本轮未改；乱码来自阅读代码页 |
| `tmp/` 不可写时回退仓库根 `.tmp_*` | 约定环境可写；属测试基建可移植性 |
| CLI 缺失解释器改成一句中文并删除 leftover generated | 体验项；R2 已使 leftover generated 不能当证据 |
| `run_all_tests.py` 增加非 conda 解释器 | 仓库约定用 `pytorch` 环境 |
| 回波指纹哈希 `.obj` 内容、连续波拒绝残留 `radar_system`、删除 `echo_overlap` 内存字段、单独跑 `estimate_period.py` 也做契约 | 上一轮已记录的取舍，两份本轮也同意维持 |
| 批量删除历史 `tmp/`、实施 ADC 计划书、改 inversion 算法 | 维护者要求本轮不动 |

质检审核环境里根组 68 条失败，不能用来否定约定环境下的功能修复；它确实暴露了 leftover generated 这条产品洞，这条已经按上面处理。

---

## 8. 当前验收

```powershell
conda run -n pytorch python scripts/run_all_tests.py
```

口径：conda `pytorch`，仓库根 `tmp/` 可写。落地 R2 后：根 122 passed；observation 69 passed；echo 44 passed；inversion 24 passed、3 skipped。较上一轮回执的根 118，增加的是 leftover generated / 缺哈希 / 当前指纹算不出等守卫，不是科学结果变化。
