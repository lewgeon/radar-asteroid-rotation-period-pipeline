# 对 DeepSeek 两轮质检的回执（2026-09-22）

> 对象：[`deepseek_audit_2026-09-21_1.md`](deepseek_audit_2026-09-21_1.md)（基建与可验收性）、[`deepseek_audit_2026-09-21_2.md`](deepseek_audit_2026-09-21_2.md)（波形从属补遗），以及第二份所引用的完整 B1–B13 论述 [`../plans/REVIEW_2026-09-21_ROUND2.md`](../plans/REVIEW_2026-09-21_ROUND2.md)。
> 本文是回执：说明我们如何核对、哪些是误判、哪些是真实缺陷、随后改了什么。条目级只读核实见 [`DEEPSEEK_AUDIT_RECHECK_2026-09-22.md`](DEEPSEEK_AUDIT_RECHECK_2026-09-22.md)；代码落地见 [`../changes/DATE_LOG_2026-09-22.md`](../changes/DATE_LOG_2026-09-22.md)。
> 环境：Windows + conda `pytorch`。不修改 inversion 估计算法，不实施 ADC 布局迁移，不批量删除历史 `tmp/`。

两份质检对 **2026-09-21 实质改动**（波形从属、行宽契约、停写 `experiment.json`、阶段指纹设计）的肯定，我们同意。分歧出在后半段「新问题」：一部分是审核环境把显示问题当成仓库缺陷，一部分把预检缺口写成了日志撒谎，还有几条是真的。

---

## 1. 我们怎样核查

没有按质检原文逐句改代码。先对照当时工作区把每条说成「缺陷」的机制走一遍，能复现的才进修改方案。

1. **读 UTF-8 源文件，不信控制台 mojibake。** 质检里贴出的「澶辫触」「瑙傛祴璁″垝」对照 `scripts/run_all_tests.py`、`tests/test_artifact_contract.py` 的字节，确认仓库里仍是「失败：」「观测计划为 252 列，回波为 251 列」。
2. **看卡住的真实用例名，不看进度百分比。** 根套件停在 GUI 的「混合测站可见性」用例，不是 CLI 的 252 vs 251 契约用例。观察组后半才碰到 `astropy_geodetic` / `Time`。
3. **把「当前保存路径」和「磁盘上的旧 run」分开。** 工作区 `runs/chirp_point_target_test/observation_info.npz` 仍是旧产物（含 `echo_overlap`）；当前 `save_npz` 已不写该数组，metadata 只列 `signal_echo_overlap` 与 `window_overlap`。
4. **对声称的静默复用做只读探针。** 在没有 `stage_manifest.json` 的目录里放占位 npz：按当时 CLI 顺序先写 `observation.generated.json` 再判定，会得到「可复用」；先判定则要求 `--allow-legacy-reuse`。GUI 代码路径是先判定后写入，与 CLI 当时不一致。
5. **拆开「规范化」「执行预检」「子进程报错」。** 残缺 `transmit`、缺 `bandwidth_hz` 能过哪一层、真正失败在哪一层，分别调用 `normalize_observation_config`、`prepare_run(..., through_stage=...)` 和对照 `build_observation_info` / `_chirp_fast_time_axis`。
6. **读 DATE_LOG 的「明确未做」表，不把它当成「已经声称做到」。** B11 把「规范化与解算同一时刻失败」写成日志撒谎；那一行本来就在未做清单里。
7. 核实结论交给维护者，批准 [`../plans/VERIFIED_FIX_PLAN_2026-09-22.md`](../plans/VERIFIED_FIX_PLAN_2026-09-22.md) 后再改代码。落地后用 `conda run -n pytorch python scripts/run_all_tests.py` 跑四组测试，并对复用写入顺序做了对抗性复查。

---

## 2. 总表

| 质检条目 | 我们的判定 | 处理 |
|---|---|---|
| 09-21 波形从属、契约、停写 `experiment.json`、自动选时带 `runs` 被拒 | **同意，属实** | 不改（已是 09-21 行为） |
| 源文件中文乱码；断言正则会假通过 | **误判** | 不改源文件编码 |
| 根测试卡在 28% = CLI `capture_output` 管道死锁 | **归因错误** | 不改那条 CLI 测试的管道方式 |
| `run_all_tests.py` 必须用 conda `pytorch` | **属实，但合仓库约定** | 不增加非 conda 解释器开关 |
| B1 CLI 先写 generated 再复用判定 | **真实错误**，且与 09-21 日志声称相反 | 已改 |
| B12 Chirp 缺 `bandwidth_hz` 能过回波预检 | **真实错误**（预检缺口） | 已改 |
| B11 残缺 `transmit` 能过 `prepare_run` | **行为属实**；失败点与日志读法不属实 | 已改预检；不收紧占用预览用的规范化 |
| B5 observation/GUI 未关 IERS 自动下载 | **机制属实**，比「管道死锁」更能解释挂起 | 已改 |
| B3 空文件记阶段成功 | **属实**，危害是状态撒谎，不是算出假周期 | 已改 |
| B6 指纹测试用系统临时目录；根目录 `.tmp_*` | **属实**（卫生 / 受限环境） | 已改 |
| B7 仍写 `manifest.json` | **文档过满，不是漏删 experiment.json** | 勘误；保留该文件 |
| B8 WebEngine 占位未删 | **属实**（死符号） | 已删 |
| B9 行宽专题 P3 过时 | **属实**（文档） | 勘误 |
| B2 manifest 缺指纹就静默复用 | **单独不成立**；要叠在 B1 或旧 generated 上 | 随 B1 消除主要危害 |
| B4 指纹不含 `.obj` 文件内容 | **现象属实，09-21 未承诺** | 不改 |
| B10 `echo_overlap` 内存字段；单独跑 inversion 脚本无契约 | **已知取舍** | 不改 |
| B13 连续波 JSON 留下未用的 `radar_system` | **属实，不对称，不参与计算** | 不改 |
| 第一份：`echo_overlap` 仍写入 metadata 三项 | **拿旧产物当新代码** | 不改保存路径 |
| 空字符串 `echo.waveform.type` | **未构成 GUI 与 pipeline 语义相反** | 不改 |
| Chirp↔连续波切换丢掉上一侧 PRF | **09-21 已列为未做** | 不改 |

---

## 3. 误判

### 3.1 源文件被写成乱码

第一份把 `run_all_tests.py` 和契约测试里的中文断言说成「写进文件的就是乱码」，并担心正则永远匹配不上。

仓库文件是 UTF-8。审核会话若用系统默认代码页打开，会把「失败：」「上游产物不兼容」显示成「澶辫触」「涓婃父浜х墿」。那是阅读环境的编码，不是 09-21 把源文件写坏。因此没有把断言改成 `"252"` 这类 ASCII 子串——真实错误信息本来就应该是中文路径句。

### 3.2 根套件卡在 28% = 管道死锁

卡住的用例是 `test_mixed_stations_show_only_horizon_side_visibility_fields`（GUI、改测站类型后刷新计划预览），排在 GUI 套件后段。把它归到 `test_root_cli_stops_before_inversion_for_stale_chirp_pair` 的 `capture_output=True` 不成立：那条 CLI 在 inversion 启动前就会因 252 vs 251 列失败，通常走不到「子进程灌满管道、父进程干等」的路径。

第一份称这是「本轮最该修的产品缺陷」。它首先不是产品计算错误；其次连测试基建的主因也指错了。更吻合的是 B5：预览构造 `astropy.time.Time` 时默认可能下载 IERS 闰秒表，无网或临时目录权限差时长时间无输出。观察组 `test_ephemeris.py`、`test_planning_regressions.py` 后半同样会碰到 `Time`，不是新网格循环本身（质检已发现把 144 组循环抽出来很快结束，这一点我们同意，但卡点不在网格断言）。

### 3.3 B11：缺单字段会在 `planning.py` `KeyError`；日志声称已经「同一时刻失败」

残缺 `transmit` 能过 `normalize_observation_config` 和当时的 `prepare_run`，这一点属实。

真正解算时，无论整块缺失还是只缺 PRF/脉宽之一，当前生产入口 `build_observation_info` 都会给出带字段路径的中文错误。不是 `planning.py` 里对缺失键做下标访问。ROUND2 把失败点写成 `KeyError`，与代码不符。

`DATE_LOG_2026-09-21.md` §6 把「规范化与 `build_observation_info` 同一时刻失败」放在 **明确未做** 表，原因是占用预览和选时单测需要不完整配置。质检把它读成「日志写了已经做到」，是读表错误。预检缺口本身仍要修，见第 5 节。

### 3.4 用旧 run 证明新代码仍写 `echo_overlap`

第一份说 metadata 仍列出三项。当时磁盘上的开发 run 确实还有旧数组。当前写入路径已经停写 `echo_overlap` 数组，metadata 只列两个可反推字段。数据类上仍留计算属性，与「停写、兼容期保留」一致，不是漏改保存格式。

### 3.5 空字符串 `type` 使 GUI 与 pipeline 语义相反

`prepare_run` 把空 `echo.waveform.type` 当未填，按观测事件源补齐。单独调用 `normalize_echo_config` 时空串会被拒。GUI 运行阶段走 `prepare_run`，不会出现「界面允许空串、流水线当成另一种波形」那种相反语义。独立 echo CLI 若绕过 pipeline 填充，才会碰到规范化拒绝。未当作本轮缺陷。

---

## 4. 现象成立、但不按原文严重度或原文读法处理的项

**B2。** manifest 里有条目却没有指纹时，不会走指纹比较，会落到 generated / `--allow-legacy-reuse` 兜底。单独造「只有文件哈希、没有 generated」时，当时探针得到的是不可复用、需要确认，并不是静默复用。真正让兜底变成「必然相等」的，是 B1 先写入当前配置。修 B1 后，这条不再构成独立的静默复用漏洞。

**B4。** 回波指纹只含解析后的模型路径字符串。同路径替换 `.obj` 内容不会变指纹。09-21 日志没有承诺哈希模型字节。属以后增强，本轮不改。

**conda 入口。** `run_all_tests.py` 写死 `conda run -n pytorch` 属实。这是仓库约定，不是产品逻辑错误。质检沙箱没有该环境，不能据此否定「当日四组测试」在约定环境里的数字。本轮不为它增加 `--python` 覆盖。

**B13。** 连续波配置里留下未使用的 `radar_system` / `receiver_sampling` 能通过规范化、不参与计算。与 Chirp 拒绝 `transmit` 上的射频字段不对称。GUI 切换波形时已经去掉这些块。收紧规范化容易误伤「先填再切波形」的界面草稿，按计划不改。

---

## 5. 真实错误，以及做了什么修改

下列修改不改变合法完整配置的数值结果。「运行观测」仍然不检查回波带宽。细节与区分测试见 [`../changes/DATE_LOG_2026-09-22.md`](../changes/DATE_LOG_2026-09-22.md)。

### 5.1 B1：CLI 复用判定顺序（质检标为高，我们同意）

当时 CLI 先把当前配置写进 `*.generated.json`，再做「已有 npz 能不能代表当前配置」的判定。没有阶段指纹的旧实验会去读 generated——读到的已经是刚写上去的当前配置，于是打印「复用已有观测信息」，实际送进 inversion 的仍是旧 npz。形状碰巧相同（例如都是 8×4）时，行宽契约也拦不住。GUI 点「运行反演」本来就是先判定后写，没有这个问题。质检指出 252 vs 251 那条测试测的是契约、掩盖了 B1，这一点成立。

修改：CLI 先判定，失败则退出且尚未写入观测/回波 generated。通过后再写。跳过观测或回波时**不覆盖**这两份历史证据，只给即将启动的子进程写对应文件；倒推阶段始终写 `inversion.generated.json`。GUI 启动某一阶段时也只写该阶段的 generated，避免「运行反演」把当前配置覆盖进上游证据。无指纹时必须 `--allow-legacy-reuse`；允许一次之后，下次不带旗标仍不能靠刚写的 generated 静默过门。

### 5.2 B12：Chirp 缺带宽仍能过回波预检

当时 `normalize_echo_config` 只在键存在时检查带宽。`prepare_run(through_stage="echo"|"full_pipeline")` 因此放行，直到快时间轴计算 `KeyError`。观测解算不用带宽，「运行观测」本来就不该因此失败。

修改：Chirp 的 `echo.waveform.bandwidth_hz` 在 echo 规范化里改为必填正有限数。该规范化只在回波/全流程预检时调用。JSON 缺键得到字段路径错误。GUI 在回波页清空输入框时，收集表单会先报「必须是有限数字」，同样在启动子进程之前失败。

### 5.3 B11：残缺 transmit 能过执行预检

即将跑 Chirp 观测时，PRF 与脉宽必须齐全。当时预检先说通过，子进程里再失败。

修改：只在 `prepare_run` 的 observation / echo / full_pipeline 路径要求两个字段都在。占用预览、选时单测继续用较松的 `normalize_observation_config`。`through_stage=inversion` 不查这两项。空 `transmit` 字典仍会被所有权整理删掉，随后按缺 transmit 失败，不再假装校验通过。

### 5.4 B5：观测侧 IERS 自动下载

inversion 早已关闭 astropy 闰秒表自动下载；observation 与 GUI 预览没有。无网时改测站类型或跑 GUI/观察组，会长时间没有新输出。

修改：新增 `observation/src/iers_policy.py`，在 `ephemeris.py`、`campaign_planning.py` 导入时设置 `auto_download=False`。根测试与 observation 测试的 `conftest` 再设一次。Horizons 查询仍按现有「更新预览」按钮，没有改成后台线程。有网时用本地表，不强制刷新。这是对第一份「根组/观察组卡住」的实际处理，而不是去改 CLI 管道。

### 5.5 B3：空产物记成功

子进程退出码 0 但 npz 是 0 字节时，原先只判断文件在不在，于是写入 `stage_manifest.json`。下一步加载才会失败。不会静默算出一个「看起来正经」的周期，但阶段状态在撒谎。

修改：记成功和判定复用前，要求文件非空、npz 可打开；观测产物至少含 `elapsed_s` 或 `valid_plan`，回波至少含 `iq`。空文件即使加了 `--allow-legacy-reuse` 也不能当可复用产物。

### 5.6 B6 / 第一份第 5 点：临时目录

指纹相关测试仍用系统 `tempfile`，在质检那种受限 Windows ACL 下会 `PermissionError`。GUI 测试在仓库根建 `.tmp_*`，中断后 `git status` 看得见。

修改：根测试 scratch 建在已忽略的 `tmp/`；`.gitignore` 增加 `.tmp_*/`。

### 5.7 B7 / B8 / B9：文档与死符号

停写的是 `experiment.json`。run 根目录的 `manifest.json` 仍记录创建时间、配置哈希、Python 版本，**不参与**复用判定。09-21 日志写成「运行目录只保留 generated 和 stage_manifest」，过满。WebEngine 占位 09-21 并未删完。行宽专题把当天后续已拒绝的非整 `fast_sample_count`、非一维 `fast_time_s` 仍写成待做 P3。

修改：09-21 日志文首勘误（不回写冻结正文）；行宽专题改正 P3；用户手册输出树补上 `manifest.json` 与 `stage_manifest.json`；删除 `QT_WEBENGINE_AVAILABLE` / `QWebEngineView`。

---

## 6. 质检里确认正确、因而没有再动的部分

- 夹具已是 `observation.transmit`，旧 `observation.waveform` 被拒并给出迁移说明。
- 自动选时带手写 `runs` 被拒。
- 自定义直角坐标上的无意义可见性字段被拒，错误会点名字段。
- `validate_observation_echo_contract`：同代次 252 列通过，252 vs 251 拒绝，CW 走一维分支。
- 代码侧已无 `experiment.json` 写入。
- GUI 切换波形不会把 `transmit` 与 `receive` 同时写盘；载入含旧 `observation.waveform` 的 JSON 会失败且不半载入。
- 上一轮 D1–D5 / T1 / T2 / L1–L3 的落实，与质检「修法正确」的判断一致，本回执不重复展开。

---

## 7. 明确未按质检建议修改的项

| 建议 | 未改原因 |
|---|---|
| 把契约断言改成 ASCII 子串 | 源文件没有乱码 |
| 改 CLI 测试管道以防死锁 | 卡顿主因不是那条测试 |
| `run_all_tests.py` 增加非 conda 解释器 | 仓库约定用 `pytorch` 环境 |
| 回波指纹哈希 `.obj` 内容 | 未承诺；同路径换模型是少见操作 |
| 连续波拒绝残留 `radar_system` | 不参与计算；收紧易误伤界面草稿 |
| 删除 `echo_overlap` 内存字段 | 新文件已不写数组；属性留给旧代码兼容期 |
| 单独跑 `estimate_period.py` 也做 observation↔echo 契约 | 契约在根 pipeline 与 GUI；脚本是 inversion 自己的入口 |
| 批量删除历史 `tmp/`、实施 ADC 计划书、改 inversion 算法 | 维护者要求本轮不动 |

质检审核环境里未能跑完根组/观察组，不能用来否定约定环境下的 09-21 测试数字；它确实暴露了 IERS 与 `tempfile` 两条环境敏感问题，这两条已经按上面处理。

---

## 8. 当前验收

```powershell
conda run -n pytorch python scripts/run_all_tests.py
```

2026-09-22 落地后：根 118 passed；observation 69 passed；echo 44 passed；inversion 24 passed、3 skipped。较 09-21 日志增加的是本回执对应的守卫，不是科学结果变化。
