# 已核实问题与修改策略（2026-09-22）

> 状态：**已实施**。落地说明见 [`../changes/DATE_LOG_2026-09-22.md`](../changes/DATE_LOG_2026-09-22.md)。依据 [`../audits/DEEPSEEK_AUDIT_RECHECK_2026-09-22.md`](../audits/DEEPSEEK_AUDIT_RECHECK_2026-09-22.md)。
> **同日后续：** DeepSeek 复核的 R2 已落地——`*.generated.json` 不再参与复用判定，只给子进程当输入。
> 本轮仍不修改 inversion 算法，不实施 ADC 布局迁移，不批量删除历史 `tmp/`。

本文先解释三个容易混在一起的概念（指纹、复用、预检），再逐条写要不要改、改什么。不使用「盖章」这类比喻。

---

## 1. 先把三个词说清楚

### 1.1 运行目录里的几类文件

假设实验名是 `chirp_point_target_test`，目录是 `runs/chirp_point_target_test/`：

| 文件 | 谁写的 | 干什么 |
|---|---|---|
| `observation_info.npz` | 观测子进程 | 视线几何和 ADC 行，给 echo 用 |
| `echo/echo.npz` | 回波子进程 | I/Q，给 inversion 用 |
| `configs/observation.generated.json` 等 | **根 pipeline / GUI 在启动该阶段之前**写出 | 子进程真正读的配置快照 |
| `stage_manifest.json` | 某一阶段**成功结束之后**写出 | 记录「这份 npz 是按哪一套有效参数算出来的」 |

用户在 `configs/` 里编辑的 JSON、GUI 里正在改的参数，都**不是**子进程的直接输入。子进程只读 `*.generated.json`。

### 1.2 「指纹」是什么

指纹不是文件密码，也不是 git 提交号。它是：把**真正会影响这一阶段产物**的字段做成一份规范化 JSON，再算 SHA-256。

- **观测指纹**：规范化后的 `observation`（去掉输出路径；单站时收发几何相同则不算一份独立 receiver）+ 产物契约版本。改 echo 的带宽、载频、反演搜索范围，**观测指纹不变**。改 PRF、脉宽、采样率、测站、目标位置、选时，观测指纹会变。
- **回波指纹**：规范化后的 `echo` + 当时那份 `observation_info.npz` 的文件哈希 + 契约版本。只改 inversion 参数，回波指纹不变。

`stage_manifest.json` 里会记下：成功跑完时的指纹、产物文件自己的哈希。下次要「跳过这一阶段、接着用已有 npz」时，拿**现在的配置**算出当前指纹，和记录里的指纹比：

- 相同 → 输入没变，可以复用已有 npz（还要核对产物文件哈希）。
- 不同 → 指出哪些字段变了，要求重跑。
- 记录里根本没有指纹（很早以前的 run）→ GUI 弹确认、CLI 要 `--allow-legacy-reuse`。**不再**用 leftover `*.generated.json` 重建指纹（R2）。

设计目的：先解算一次观测，然后反复改带宽/载频只重跑回波，不必每次重跑视线。

### 1.3 「预检」和 GUI 的关系

预检就是调用 `pipeline.prepare_run(..., through_stage=...)`。它**不是**「任何时候都用完整流水线字段卡死界面」。`through_stage` 表示「这次准备跑到哪一步」，检查范围跟着变。

当前 GUI **实际接线**如下。

| 你点的按钮 | 会不会调用 `prepare_run` | `through_stage` | 缺回波带宽会不会在这里失败 |
|---|---|---|---|
| 切换左侧阶段、改表单、观测计划预览 | 否 | — | 否。预览走 `normalize_observation_config` + `resolve_campaign_run_plan` |
| 保存 / 另存为 | 否 | — | 否。只把当前界面写进你的 JSON |
| **运行：观测解算** | 是 | `observation` | **否**（现在和拟议修改后都否） |
| **运行：回波仿真** | 是 | `echo` | 现在：否，子进程里才 `KeyError`；拟议：是，启动前报「缺 bandwidth_hz」 |
| **运行：周期反演** | 是 | `inversion` | 否（不查回波必填） |
| **运行完整 pipeline** | 是 | `full_pipeline` | 同「运行回波」：现在漏检，拟议在启动第一阶段前报缺带宽 |
| 顶部「校验」 | 是 | 未传阶段时默认 `full_pipeline` | 与「运行全部」同一套（这是现有按钮语义，不是本轮新加的） |

启动 GUI 时并不是一张空白表。没有上次会话时，默认载入 `configs/chirp_point_target_test.json`，里面已经有 PRF、脉宽、带宽。从 Chirp 切到连续波时，界面会写入 `receive` 默认值并去掉 `transmit`；再切回 Chirp 时会补上 `transmit` 的默认 PRF/脉宽。因此「一开始没有初始配置文件」在当前 GUI 里不会出现一张缺字段的空表。

结论：

- **分阶段执行的预检，只检查这一阶段真正要启动的子进程所需要的字段。** 这正是 09-21 引入 `through_stage` 的原因：带宽大于采样率不能挡住观测解算。
- 本轮拟议的 B12 / B11 **不把**「缺带宽」提前到「运行观测」。缺带宽只应在「运行回波」或「运行全部」时成为错误。
- 若把规范化函数收成「有 `schedule` 就必须有完整 `transmit`」，才会伤到占用预览和部分单测。所以 B11 **不改** `normalize_observation_config`，只改 `prepare_run` 在即将执行观测/回波时的检查。

CLI 默认一次跑三阶段，等价于 GUI 的「运行完整 pipeline」，用 `full_pipeline` 预检是合理的。`--skip-observation` 时改走 `echo` 或 `inversion`，也不会用尚未编辑的回波草稿去否定已经存在的观测产物（那是另一条已实现的规则）。

---

## 2. CLI 先写 generated 再判定复用：会出什么事（B1）

### 正确顺序（GUI 已经是这样）

1. 用**当前界面/当前 JSON**算出指纹。
2. 拿 `stage_manifest.json` 判断已有 `observation_info.npz` 能不能代表**当前**配置。`*.generated.json` 不是复用证据。
3. 能复用 → 不重跑观测；不能 → 报错或请你确认。
4. **判定结束之后**，才把当前配置写成新的 `*.generated.json` 给接下来要启动的子进程。

第 4 步必须在第 2 步之后，避免尚未判定就覆盖即将交给子进程的输入文件。generated 只给子进程当输入，不参与复用判定。

### 现在 CLI 的错误顺序

`python pipeline.py --config 新配置.json --run-name 某个旧实验 --skip-observation --skip-echo` 时：

1. 先把**新配置**写进 `runs/某个旧实验/configs/observation.generated.json`（覆盖上次留下的那份）。
2. 再做复用判定。旧实验往往没有 `stage_manifest.json`（09-21 之前的产物），于是判定去读 generated——读到的已经是刚才写上去的新配置，和「当前配置」当然一致，于是打印「复用已有观测信息」。
3. 实际拿去反演的，仍是目录里那份**旧的** `observation_info.npz` / `echo.npz`。

### 具体后果

你改了 PRF、测站或目标，以为 `--skip-observation` 会发现旧 npz 对不上、让你重跑观测。CLI 却认为可以复用，把旧几何送进 inversion。

- 若旧回波和新计划的脉冲数、行宽碰巧还能对上（例如都是 8×252，只是 PRF 不同），**契约校验也不会拦**，反演在错误几何上跑完，表面上成功。
- 若只是 251 列旧回波对 252 列新计划，现有契约会拦住。所以「252 vs 251」那条测试仍然绿，但测不到「形状一样、物理配置已经变了」这种复用错误。

GUI 点「运行反演」时先判定、后写 generated，没有「先覆盖再判定」这个问题。B1 修的是 CLI 写入顺序。R2 之后：没有指纹时 CLI 必须加 `--allow-legacy-reuse`；leftover generated 不能证明同源。有指纹、文件哈希与当前配置都对得上时，仍然自动复用（改带宽只重跑回波的工作流保持不变）。

---

## 3. Chirp 缺 `bandwidth_hz` 算不算问题（B12）

算，但**只在你真要跑回波（或一次跑完全流程）时**算。

带宽属于 `echo.waveform`，观测解算不用它。GUI 在观测页可以完全不管带宽——现在如此，改完也应如此。

问题出在：**已经点了「运行回波」或「运行完整 pipeline」**，预检仍然认为配置合法，然后 `simulate_echo.py` 在算快时间轴时 `KeyError: 'bandwidth_hz'`。进程退出码 1，日志不如字段路径错误好读。GUI 默认配置和切波形时的 `setdefault` 会带上带宽；用户若把带宽输入框清空，就可以走到这条路径。

拟议修改：仅当 `through_stage` 是 `echo` 或 `full_pipeline` 时，Chirp 必须有正有限 `bandwidth_hz`。`through_stage=observation` 不检查这一项。

不会发生的事情：

- 不会「还没执行视线解算就因为缺带宽报错」（除非你点的是「运行全部」或顶部「校验」；「运行全部」本来就应在启动前确认三阶段都能跑）。
- 不会让空白 GUI 无法打开。打开 GUI 不走这条预检；默认 JSON 里已有带宽。

---

## 4. 残缺 `transmit`（B11）和分阶段 GUI

`observation.transmit` 的 PRF、脉宽是 **Chirp 观测解算**要用的，不是回波专属字段。点「运行观测」时若缺它们，子进程里的 `build_observation_info` 现在也会失败，只是预检先说「通过」，再在子进程里报错。

拟议：只在 `prepare_run` 即将执行观测或回波时要求两个字段齐全。占用预览、选时单测继续调用较松的 `normalize_observation_config`，可以没有完整 `transmit`。

从 Chirp 切到连续波会去掉 `transmit`；连续波观测不需要它。默认开发夹具是完整 Chirp。不会出现「空工程一打开就因为缺 PRF 不能编辑」——编辑和预览不走 `prepare_run`。

---

## 5. 应当修的几项（详细）

这几项都不改变合法配置的数值结果，也不改变「观测页可以暂不填回波参数」。

### 5.1 无网时界面或测试像死机（B5）

**现象**：把测站改成「Astropy 大地坐标」后，观测页会刷新计划预览。预览要用 `astropy.time.Time` 做时间运算。astropy 默认可能去网上更新闰秒表（IERS）。电脑没网、或临时目录权限差时，这个下载会一直等，窗口或 pytest 长时间没有新输出，看起来像卡住。外部审核里根测试停在「混合测站」GUI 用例、观察组后半卡住，更符合这条，而不是管道死锁。

** inversion 侧已经关了**：`inversion/src/ephemeris.py` 里有 `iers.conf.auto_download = False`。observation 和 GUI 引用的 astropy 路径没有这句。

**拟议**：在 observation 里同样关闭自动下载（`campaign_planning.py` / `ephemeris.py` 导入时设置，测试 `conftest` 再设一次）。真要查 Horizons 星历仍按现有「更新预览」按钮走，不把预览改成后台线程。

**改完**：无网时改测站类型、跑 GUI 测试不应再挂死。有网时行为与现在一致（用本地 IERS 表，不强制刷新）。

### 5.2 空文件也被当成「这一阶段成功了」（B3）

**现象**：子进程退出码是 0，但写出的 `observation_info.npz` / `echo.npz` 是 0 字节（磁盘满、中途被截断等）。代码只判断「文件在不在」，于是写入 `stage_manifest.json` 表示成功。下次复用会认为这份空文件可用，直到有人 `np.load` 才爆。

**不会**：把空文件当成正确科学结果送进反演还能算出一个「看起来正经」的周期——加载会失败。问题是状态撒谎：界面/manifest 说成功，下一步才失败，不好查。

**拟议**：记成功之前要求文件大小 > 0，npz 至少能打开并带有约定键（观测：`elapsed_s` 或 `valid_plan`；回波：`iq`）。不做科学内容检查。

**改完**：空壳文件 → 本阶段失败，不写成功记录，不能被当成可复用产物。

### 5.3 四条指纹测试仍用系统临时目录（B6）+ 仓库根留下 `.tmp_*`

**现象**：仓库里多数测试已经把临时文件建在项目的 `tmp/`（git 忽略）下，因为 Windows 上系统 `tempfile` 目录有时 ACL 过严，测试进程写不进去。09-21 新加的四条指纹/原子写入测试还在用 `tempfile.TemporaryDirectory()`。在那种受限环境里，这四条会 `PermissionError`，而它们正好是在守护「复用判定」和「JSON 原子写入」。外部审核那台机器上就是 107 passed、这 4 条 failed。

另外，GUI 测试在仓库根创建 `.tmp_gui_state__进程号_时间戳`，中断时 `rmtree(..., ignore_errors=True)` 可能删不掉；`.gitignore` 没有 `.tmp_*/`，会进 `git status`。

**拟议**：这四条改用与 `echo/tests/scratch.py` 相同的做法（建在已忽略的 `tmp/`）。`.gitignore` 增加 `.tmp_*/`。不改测试所断言的行为。

**改完**：指纹测试在受限 Windows 令牌下也能跑；残留目录不再干扰 git。

### 5.4 未使用的 Qt 占位符还在（B8）

**现象**：09-21 日志写「删了未使用的 Qt 常量和 WebEngine 占位」。`ALIGN_CENTER` 那些确实没了，但 `rotation_gui/qt_compat.py` 里仍有 `QT_WEBENGINE_AVAILABLE = False` 和 `QWebEngineView = None`，全项目没有读取它们。当前预览用系统浏览器打开 HTML，不用 Qt WebEngine。

**拟议**：删掉这两个符号。界面、预览、运行逻辑都不变。

### 5.5 文档和代码不一致（B7、B9）

**`manifest.json`**：停写的是 `experiment.json`（整份实验配置再存一份在 run 里，没有读者）。`pipeline.py` 和 GUI **仍会**在 run 根目录写 `manifest.json`，内容是创建时间、配置哈希、Python 版本这类追溯信息，**不参与**复用判定。DATE_LOG 写成「运行目录只保留 generated 和 stage_manifest」，漏了这个小文件。应改日志句子，不是删 `manifest.json`（除非以后明确要删）。

**P3 文档过时**：更早的专题文档写「metadata 里 `fast_sample_count=4.9` 会被 `int()` 截成 4、二维 `fast_time_s` 只查长度」。当天后续已经在 `geometry.py` / `echo.py` / 契约校验里拒绝这些伪造值。应在专题文档和 DATE_LOG §6 加勘误，避免以后按过时 P3 再改一遍。

---

## 6. 本轮明确不修

| 项 | 原因 |
|---|---|
| 回波指纹里加入 `.obj` 模型文件内容 | 日志没承诺；换模型同路径是少见操作，属以后增强 |
| 连续波 JSON 里留下未使用的 `radar_system` | 不参与计算；GUI 切换波形时已经去掉。收紧规范化容易误伤「先填再切波形」的界面草稿 |
| 删除 `echo_overlap` 内存字段 | 新文件已不写该数组；属性留给旧代码一个兼容期 |
| 单独跑 `inversion/scripts/estimate_period.py` 也做 observation↔echo 契约 | 契约在根 pipeline 和 GUI；脚本是 inversion 自己的入口 |
| inversion 算法、ADC 计划书、批量删历史 tmp | 仍搁置 |
| 为 `run_all_tests.py` 增加非 conda 解释器 | 本仓库约定用 conda `pytorch` |

---

## 7. 建议实施顺序

1. B1：CLI 先判定复用，再写 generated（与 GUI 一致），并补「无指纹不得静默复用」测试。
2. B12 + B11：回波预检要求带宽；观测/回波执行预检要求完整 `transmit`。`through_stage=observation` 仍然不查带宽。
3. B5：observation 关闭 IERS 自动下载。
4. B3：空文件不得记阶段成功。
5. B6 / `.gitignore` / B8：测试目录与死符号。
6. 文档勘误。

验收：`conda run -n pytorch python scripts/run_all_tests.py`。另确认：点「运行观测」时缺带宽仍通过预检；点「运行回波」时缺带宽在启动前失败。
