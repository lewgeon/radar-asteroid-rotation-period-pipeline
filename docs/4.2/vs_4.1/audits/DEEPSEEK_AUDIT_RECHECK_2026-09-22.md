# DeepSeek 两轮核查的核实（2026-09-22）

> 对象：[`deepseek_audit_2026-09-21_1.md`](deepseek_audit_2026-09-21_1.md)、[`deepseek_audit_2026-09-21_2.md`](deepseek_audit_2026-09-21_2.md)，以及第二份所引用的 [`../plans/REVIEW_2026-09-21_ROUND2.md`](../plans/REVIEW_2026-09-21_ROUND2.md)（B1–B13 的完整论述在 ROUND2，不在 audit_2 短文里）。
> 方法：对照当时代码路径，并对 B1/B2/B3/B11/B12/B13、空 `type`、中文字符串、现有 `runs/` 产物做了只读探针。本文件只记录核实结论，**未改业务代码**。落地后的回执见 [`DEEPSEEK_AUDIT_RESPONSE_2026-09-22.md`](DEEPSEEK_AUDIT_RESPONSE_2026-09-22.md)。
> 环境：Windows + conda `pytorch`（与仓库约定一致）。

## 1. 总判

两份审核对 **09-21 实质改动（波形从属、契约校验、停写 `experiment.json`、阶段指纹设计）** 的肯定成立。

需要分开看的是后半段「新问题」：

| 性质 | 条目 |
|---|---|
| **成立，且与当日日志声称相反** | **B1**（CLI 先写 `*.generated.json` 再做复用判定，无指纹产物被静默复用） |
| **成立，但是预检缺口，不是日志写反** | B11（残缺 `transmit` 能过 `prepare_run`）、B12（缺 `bandwidth_hz` 能过预检） |
| **成立，严重度低于原文** | B2、B3、B4、B5、B6、B7、B8、B9、B10、B13 |
| **不成立或归因错误** | 第一份的「源文件中文乱码」、第一份的「管道死锁导致根套件卡在 28%」、B11 所说的「缺单字段会 `KeyError`」、B11 把 DATE_LOG §6「明确未做」读成「已经做到」 |
| **环境相关，本机未必复现** | 第一份 / B5 / B6 的整组挂起、`tempfile` ACL、`run_all_tests.py` 强依赖 conda |

上一轮 D1–D5 / T1 / T2 / L1–L3「已落实且修法正确」这一段，与当前文档和测试守卫一致，不再重复展开。

## 2. 第一份审核（基建 / 可验收性）

### 2.1 修改本身正确 — 同意

夹具已改为 `observation.transmit`；旧 `observation.waveform` 被拒；自动选时带 `runs` 被拒；双直角坐标可见性字段被逐项点名；252/251 契约会拒；CW 走一维分支；代码侧已无 `experiment.json` 写入。这些与 [`../changes/DATE_LOG_2026-09-21.md`](../changes/DATE_LOG_2026-09-21.md) 一致。

### 2.2 「根测试卡在 28% / 管道死锁」— 归因不成立

卡住的用例是 `test_mixed_stations_show_only_horizon_side_visibility_fields`，排在 GUI 套件中后段，**不是** `test_root_cli_stops_before_inversion_for_stale_chirp_pair`。

该 CLI 用例即使用 `capture_output=True` 且无超时：它会在 inversion 启动前走契约校验，252 vs 251 应立刻失败，通常走不到「子进程灌满管道」的路径。把它说成「本轮最该修的产品缺陷」过重。

更吻合的机制是第二份 **B5**：把发射站改成大地坐标后，日程反馈会调用 `resolve_campaign_run_plan` → `astropy.time.Time` → IERS/闰秒自动下载。`inversion` 已设 `iers.conf.auto_download=False`，**observation 与 GUI 侧没有**。无网或临时目录 ACL 受限时，这里会长时间无输出，看起来像「卡住」。

`test_planning_regressions.py`「27% 之后」也不是新网格循环本身：该文件前半是纯数值守卫，后半才出现 `astropy_geodetic` / Horizons 配置用例；与 `test_ephemeris.py` 同属既有 astropy 联网面，不是 09-21 引入的计算错误。

### 2.3 「`run_all_tests.py` 和测试里的中文已乱码」— 不成立

`scripts/run_all_tests.py` 源文件是 UTF-8，含「失败：」「四组测试全部通过。」。`tests/test_artifact_contract.py` 的断言是「观测计划为 252 列，回波为 251 列」「上游产物不兼容」。第一份看到的 mojibake 是审核环境用错编码读文件，不是仓库被写坏。正则因此「假通过」的担心不适用于当前树。

脚本写死 `conda run -n pytorch` **属实**，也符合本仓库 `AGENTS.md` 的运行约定。在没有 conda 的沙箱里不可用，不是产品逻辑错误。

### 2.4 `echo_overlap` — 半对

当前 `ObservationInfo.save_npz` **不写** `echo_overlap` 数组；`observation/tests/test_planning_regressions.py` 的闭环测试断言文件中无该键。`metadata["overlap_fields"]` 在当前代码里只列 `signal_echo_overlap` 与 `window_overlap`。

第一份说「metadata 仍列出三项」与**当前写入路径**不符。工作区里 `runs/chirp_point_target_test/observation_info.npz` 仍是旧产物（文件里还有 `echo_overlap`，metadata 仍列三项），不能拿它证明新代码还在写。

数据类字段 `ObservationInfo.echo_overlap` 和 `ReceptionPlan.echo_overlap` 属性仍在，与 DATE_LOG / 计划书里「停写、兼容期保留计算属性」一致，不是漏改。

### 2.5 `.tmp_*` 临时目录 — 成立（卫生项）

GUI / 契约测试把 scratch 建在仓库根，`.gitignore` 只有 `tmp/`、`runs/`。`rmtree(..., ignore_errors=True)` 在中断或 ACL 失败时会留下 `.tmp_gui_state__*`。不参与计算结果。

## 3. 第二份审核（B1–B13）

### B1（高）无指纹历史产物被 CLI 静默复用 — **成立**

`pipeline.py` 的 CLI `main()` 在调用 `check_reusable_artifact` **之前**写入三份 `*.generated.json`。`check_reusable_artifact` 在没有阶段指纹时，会把这份刚写下的 generated 配置重建指纹，与当前配置比较——必然相等，于是 `reusable=True`。

本机探针（run 目录只有占位 npz、无 `stage_manifest.json`）：

- 先判定：`reusable=False`，`requires_confirmation=True`，原因要求 `--allow-legacy-reuse`
- 按 CLI 顺序先写 `observation.generated.json` 再判定：`reusable=True`，不再要求确认

这与 DATE_LOG §3.2「无指纹历史产物……CLI 需 `--allow-legacy-reuse`」**直接相反**。GUI 顺序是对的：`main.py` 先 `_reuse_upstream`，通过后再写 generated。`--allow-legacy-reuse` 在这条 CLI 路径上确实被绕过。

`tests/test_artifact_contract.py::test_root_cli_stops_before_inversion_for_stale_chirp_pair` 用的是 **252 列 observation + 251 列 echo**，靠契约校验拦下，走不到「形状自洽的旧 251↔251 对 + 当前 252 配置被当复用」这条路。ROUND2 说现有测试掩盖了 B1，这一点成立。

### B2（中）manifest 缺 `fingerprint` — **部分成立**

`recorded_fp and current_fp` 为假时不会走指纹比较，落入 generated / legacy 兜底。这是真的。

单独造一条「只有 `output_sha256`、没有 generated.json」的 manifest 时，本机得到的是 `reusable=False` 且仍要求确认，**不会**静默复用。ROUND2 写的 `reusable=True` 需要兜底路径上已经有一份与当前配置一致的 `*.generated.json`（典型就是 B1 的写入顺序，或同 run 里上次执行留下的文件）。B2 本身不是独立的静默复用漏洞，而是「指纹门被跳过」；危害要叠在 B1 或旧 generated 上才显现。

### B3（中）0 字节产物记成功 — **成立，危害限于记录**

`write_stage_success` 对 `Path.exists()` 为真的文件做 SHA-256，空文件也能写入 manifest。GUI 成功判定同样只看存在。后续 `validate_observation_echo_contract` / `np.load` 会在真正消费时报错。不会静默产出错误周期，但会让「阶段成功」记录说谎。

### B4（中）echo 指纹不含模型文件内容 — **现象成立，不是与日志矛盾**

投影里只有解析后的 `model_path` 字符串；同路径换 `.obj` 内容不会使指纹变化。契约版本也是手写常量。DATE_LOG 从未声称哈希模型字节。这是增强项，不是 09-21 声称未兑现。

### B5（中）astropy 自动下载 / 测试入口挂起 — **机制成立**

observation / GUI 未关闭 `iers.conf.auto_download`。日程反馈在非 manual 且测站为 `astropy_geodetic` 时会同步进入 astropy。无网或临时目录权限差时会挂起。这能同时解释第一份的 GUI 28% 和第二份的根/观察组挂起。是否在维护者本机出现，取决于 IERS 缓存是否已热、网络是否可用。

`scripts/run_all_tests.py` 没有超时、没有「跳过网络」开关，属实。

### B6（中）四条新测试仍用 `tempfile` — **成立**

`tests/test_schema_v4_contract.py` 里原子写入 / 指纹复用四条使用 `tempfile.TemporaryDirectory()`；同目录其它 GUI/契约测试已改工作区 scratch。在受限 ACL 环境这四条会 `WinError 5`，守卫失效。常规 conda 环境通常能跑过。

### B7（低·文档）仍写 `manifest.json` — **成立**

DATE_LOG §4 写运行目录「只保留 `*.generated.json` 与 `stage_manifest.json`」。`pipeline.py` 与 `rotation_gui/window/main.py` 仍写 `run_dir/manifest.json`（整包追溯摘要，不是 `experiment.json`）。「不再写 experiment.json」本身为真。

### B8（低·文档）WebEngine 占位未删 — **成立**

`ALIGN_CENTER` 等未使用常量已不在树中。`QT_WEBENGINE_AVAILABLE = False` 与 `QWebEngineView = None` 仍在 `rotation_gui/qt_compat.py`，全仓无引用。DATE_LOG §3.5 把「WebEngine 占位」写进已删除清单，过满。

### B9（低·文档）CHIRP_ROW_CONTRACT §7 的 P3 已过时 — **成立**

当前 `echo/src/geometry.py::_metadata_fast_sample_count`、`echo/src/echo.py::_positive_integer`、`pipeline.validate_observation_echo_contract` 已拒绝非整 `fast_sample_count` 和非一维 `fast_time_s`。专题文档 §7 与 DATE_LOG §6 仍把它们列为未做 P3，需要勘误，不是代码回退。

### B10（低）无用字段与绕过路径 — **成立，且原先已知**

`echo_overlap` 计算属性仍在；inversion 脚本不经根 pipeline 的 observation↔echo 契约。CHIRP_ROW_CONTRACT 已写明守卫在 pipeline/GUI。单独跑 `estimate_period.py` 本来就不是全流水线入口。

### B11（中）残缺 `transmit` 能过预检 — **行为成立；失败点与日志读法不成立**

本机四种 Chirp 配置：

| `observation.transmit` | `normalize_observation_config` | `prepare_run(through_stage="echo")` | 生成配置里的 transmit |
|---|---|---|---|
| 完整 | 通过 | 通过 | 原样 |
| 只有 `prf_hz` | 通过 | 通过 | `{"prf_hz": …}` |
| 只有 `pulse_width_s` | 通过 | 通过 | `{"pulse_width_s": …}` |
| `{}` | 通过 | 通过 | **被 `pop` 掉** |

GUI/CLI 预检因此会对随后必然失败的 Chirp 说「校验通过」。真正解算时：

- 整块缺失 → `build_observation_info` 报「需要 observation.transmit」
- 缺一个字段 → **同样在 `observation_info.py` 报路径化错误**（需要 `prf_hz` 与 `pulse_width_s`），**不是** `planning.py` 的 `KeyError`

ROUND2 把失败点写成 `planning.py:96-97` 的 `KeyError`，与当前生产入口不符。

DATE_LOG §6 把「规范化与 `build_observation_info` 同一时刻失败」放在 **「明确未做」** 表里，原因是选时单测和占用预览需要不完整配置。第二份把它读成「日志声称已经同一时刻失败」，是读表错误。日志确实没写清「缺单字段时 `prepare_run` 仍通过」这一预检缺口。

### B12（中）Chirp 缺 `bandwidth_hz` — **成立**

删掉该键后 `prepare_run(through_stage="full_pipeline")` 成功，生成 `echo.waveform` 只剩 `type` / `amplitude` / `baseband_convention`。`normalize_echo_config` 只在键存在时检查；`assemble_echo_waveform` 只在带宽存在时与采样率比较。运行到 `_chirp_fast_time_axis` 才会 `KeyError: 'bandwidth_hz'`。GUI 默认会补该键，用户清空输入框可以走到这条路径。当前没有缺键变红的测试。

### B13（低）CW 静默保留 Chirp 专属块 — **成立**

`{target, transmitter, receive, radar_system, receiver_sampling}` 能通过规范化，两块被原样保留、不参与连续波计算。Chirp 分支会拒绝 `transmit` 上的射频字段。不对称，不是违反已写明的「CW 不得出现 `observation.transmit`」。

### 未判定项

1. GUI 确认对话框：代码有 `QMessageBox.question` 分支，本轮未跑 Qt Yes/No。逻辑上 B1 修掉之前，CLI 比 GUI 更容易静默复用。
2. 空字符串 `echo.waveform.type`：`pipeline._echo_waveform_type` 把空串当未填并按事件源补齐，本机 `prepare_run` 得到 `chirp_pulse_train`。`normalize_echo_config` **单独**遇到 `type=""` 会报「必须是 continuous_wave 或 chirp_pulse_train」。GUI `collect()` 可能把空串写进草稿，但阶段运行走 `prepare_run`，会被补齐。独立 echo CLI 若直接规范化、不经过 pipeline 填充，才会踩到拒绝。不是「GUI 与 pipeline 语义相反」那么强。
3. Chirp↔CW 切换丢失 PRF：DATE_LOG 已列为明确未做。

## 4. 建议的处理顺序（尚未实施）

若继续改代码，优先：

1. **B1**：把 CLI 的 `*.generated.json` 写入移到复用判定之后（与 GUI 对齐）；补「无 `--allow-legacy-reuse` 时拒绝无指纹产物」且**不要**先覆盖 generated 的测试。
2. **B12**：Chirp 的 `echo.waveform.bandwidth_hz` 改为规范化必填，并加缺键变红测试。
3. **B11**：在「即将执行观测解算」的入口要求 Chirp `transmit` 同时具备两个字段；保持选时/预览夹具仍可使用残缺配置（不要把 `normalize_observation_config` 收成与 `build_observation_info` 完全同一套，除非同时改那些夹具）。
4. 文档：DATE_LOG §4 补上仍写 `manifest.json`；CHIRP_ROW_CONTRACT §7 / DATE_LOG §6 的 P3 与 WebEngine 占位勘误；B5 可在 observation 侧关闭 IERS 自动下载，与 inversion 对齐。

B3/B4/B6/B13/临时目录属于健壮性或卫生，不阻断 09-21 那批修复的正确性结论。
