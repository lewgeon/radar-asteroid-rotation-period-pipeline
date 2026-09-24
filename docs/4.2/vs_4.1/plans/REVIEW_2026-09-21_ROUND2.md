# 2026-09-21 修改核查报告（第二轮外部复核）

> **状态：报告本身只记录核查结论，未改动任何代码或既有文档。** 待处理项应按 `plans/README.md` 的约定，落地后整理进 `../changes/` 并从索引移除。
>
> **核查对象**：`DATE_LOG_2026-09-21.md` 与四份专题文档（`CHIRP_ROW_CONTRACT`、`RUNTIME_LOGIC_FIXES`、`CONFIG_FINGERPRINT_AND_GUI_SEAM`、`WAVEFORM_OWNERSHIP`）所声称的改动；以及上一轮 `REVIEW_2026-09-21_OPEN_ISSUES.md` 的 D1–D5 / T1 / T2 / L1–L3。
> **方法**：逐条读代码定位 → 构造能变红的实验（变异、判别分支、真实 CLI 调用）→ 跑四组测试与 `scripts/run_all_tests.py`。所有数字为本轮实测。
> **环境**：Windows + conda `pytorch`（`E:\anaconda3\envs\pytorch\python.exe`）、无网络、文件访问受限（`tempfile`/`mkdtemp` 建出的目录带受限 ACL，清理时报 `WinError 5`）。

---

## 1. 结论摘要

**上一轮的 10 项全部落实，且修法正确**（详见 §2）。其中 T1、T2 修得比我建议的更强。

**新发现 13 项**（详见 §3、§4），按严重度：

| 编号 | 严重度 | 位置 | 一句话 |
|---|---|---|---|
| B1 | **高** | `pipeline.py:905-907` / `check_reusable_artifact` 兜底 `:451-463` | 无指纹的历史产物被 CLI **静默复用**，`--allow-legacy-reuse` 形同虚设，与 `DATE_LOG` §3.2 的声称相反 |
| B2 | 中 | `pipeline.py:416-420` | manifest 有条目但缺 `fingerprint` 时同样静默复用 |
| B3 | 中 | `pipeline.py:375`、`:413-426` | 阶段"成功"只看文件是否存在，0 字节产物也记为成功并可复用 |
| B4 | 中 | `pipeline.py:319-330`、`:282-283` | echo 指纹只含 `model_path` 字符串，不含模型文件内容；契约版本是手写常量 |
| B5 | 中 | 测试入口 | 本机（受限 tmp / 无网）根套件**挂起**、`scripts/run_all_tests.py` 无超时；observation/GUI 侧未设 `iers.conf.auto_download=False`（inversion 已设） |
| B6 | 中 | `tests/test_schema_v4_contract.py:485/508/553/598` | 新批次 4 条测试用 `tempfile.TemporaryDirectory()`，在受限 ACL 环境清理失败（该仓库其它测试早已统一改用工作区 `scratch` 助手） |
| B7 | 低·文档 | `DATE_LOG` §4 | 声称运行目录"只保留 `*.generated.json` 与 `stage_manifest.json`"，实际仍写 `run_dir/manifest.json`（`pipeline.py:1007`、`main.py:713`） |
| B8 | 低·文档 | `DATE_LOG` §3.5 | 声称删除了"未使用的 Qt 常量与 WebEngine 占位"，实际 `rotation_gui/qt_compat.py:34,97` 仍在且无引用 |
| B9 | 低·文档 | `CHIRP_ROW_CONTRACT` §7 | 列出的两个 P3 点（`int()` 截断、`fast_time_s` 只查长度）在当天后续已被修掉，文档没有勘误 |
| B10 | 低 | `observation_info.py:62/369`、`inversion/scripts/estimate_period.py` | `echo_overlap` 已成无用字段；直接调用 inversion 脚本会绕过 observation↔echo 契约 |
| B11 | 中 | `observation/src/config_normalize.py:277-293`、`pipeline.py:801-806` | `observation.transmit` 只做"部分字段"校验：缺一个字段能通过预检，空块被静默删除；与 `DATE_LOG:207` 的措辞不符 |
| B12 | 中 | `pipeline.py:817-834`、`echo/src/config_normalize.py:268-269` | Chirp 的 `echo.waveform.bandwidth_hz` 没有必填校验，直到 echo 核心才 `KeyError` |
| B13 | 低 | `observation/src/config_normalize.py:256-261` | CW 分支对 Chirp 专属块（`radar_system`/`receiver_sampling`）静默保留、不参与计算，与 Chirp 分支对外来字段的严格拒绝不对称 |

另有一处**记录口径**问题：同一天三份文档给出的测试基线各不相同（`CHIRP_ROW_CONTRACT` §6：81/59/36/22+3；`RUNTIME_LOGIC_FIXES` §5：90/65/41/24+3；`DATE_LOG` §0：111/69/43/24+3）。它们是当天不同时点的快照，但都写成"结果"；建议以 `DATE_LOG_2026-09-21.md` 为准并在另两份注明时点。

---

## 2. 上一轮 D1–D5 / T1 / T2 / L1–L3 的核对结果

| 编号 | 结论 | 证据 |
|---|---|---|
| D1 | **已修且正确** | `OBSERVATION_TIME_SELECTION.md:172` 改为"判据不变，但行宽是该判据的输入之一，+1 会把'行宽恰好等于行距'的配置翻成重叠"，并指向 `KNOWN_DEFECTS.md §1` 的算例 |
| D2 / D3 | **已修且正确** | `OBSERVATION_RECEPTION_WINDOW.md:94-97` 把"行宽增量 $\lceil b+0.5\rceil-\lceil b\rceil\in\{0,1\}$"与"窗尾推迟量 $\delta=\rho+\lceil g+0.5\rceil+1-\lceil f+g\rceil$"分成两条，结论 $\delta\in\{1,2\}$、下界 1，与上一轮推导一致；`:119` 的 $\{0,1,2\}$ 已改为 $\{1,2\}$；两份 `DATE_LOG` 按"快照不重写"只在文首加勘误 |
| D4 | **已修** | 符号表 `:31` 已是 $n_{\mathrm{after}}=\lceil T_{\mathrm{after}}f_s+0.5\rceil$ |
| D5 | **已修** | `KNOWN_DEFECTS.md:137` 已是"12 个"，并保留 24−12=12 的键数说明 |
| T1 | **修得比建议强，实测有区分力** | 新增 `test_post_guard_margin_dense_fraction_and_extent_never_negative`（`plan_reception` + 小数位密扫 + `extent_path_m>0` + 多 Run + 解析下界 `fast_sample_count ≥ n_pre + after_s·fs + 1.5`）。**变异实测**：把 `planning.py` 的补偿常量 0.5 改成 0.45 / 0.4 → 该用例变红；改成 0.3 → 它与旧网格用例一起变红；改回 0.5 → 13 passed。解析下界与 `c ≥ 0.5` 等价，因此不再依赖"网格是否正好撞到危险小数位" |
| T2 | **已修，且覆盖更全** | `pipeline.validate_observation_echo_contract`（`pipeline.py:170-254`）核对脉冲数、行宽（`valid_plan` vs `iq`）、`fast_time_s` 长度、`row_start_sample` 相等、metadata 行宽、以及 echo 记录的 observation SHA-256；根 pipeline（`:982`）、GUI inversion 入口（`main.py:699`）、GUI 预览（`main.py:1054`）三处调用；inversion 载入器另查自身 metadata（`inversion/src/dataset.py:158-175`）。端到端实测：用迁移后的 `transmit` 配置跑观测解算得到 `valid_plan (8, 252)`、逐行有效数全 252 |
| L1 | **已处理且准确** | `DATE_LOG_2026-09-19.md:8` 文首勘误写明"§2.7 写删除 4 个 `echo/tmp/cli_smoke_*` 与工作区残留不一致" |
| L2 | **已处理** | 新建 `DATE_LOG_2026-09-21.md`；`DATE_LOG_2026-09-19.md:7,9` 写明文件名日期与实际记录期的关系 |
| L3 | **部分处理（按声明暂缓）** | `adc_window_duration_s` 已进 `PROJECT_OVERVIEW.md` / `GLOSSARY.md`；`observation/tmp/` 清理在 `DATE_LOG` §6 明确列为"未做（卫生项）" |

---

## 3. 新发现（代码与文档不一致 / 潜在缺陷）

### B1（高）无指纹历史产物被 CLI 静默复用

**声称**（`DATE_LOG` §3.2）："无指纹历史产物被静默当成可复用 → GUI 需确认，CLI 需 `--allow-legacy-reuse`"。

**实际**：`pipeline.py:905-907` 在**任何复用判定之前**就把当前配置写进 `run_dir/configs/*.generated.json`，而 `check_reusable_artifact` 的兜底分支（`:451-463`）会把这份"记录"读回来和当前指纹比较——刚写下的当然相等，于是判定 reusable。

**独立复现**（本次核查执行，残留已清理）：

```powershell
# run 目录只放 251 列旧产物，无 stage_manifest.json、无 configs/
Copy-Item runs\chirp_test\observation_info.npz  runs\_verify_legacy_mine\
Copy-Item runs\chirp_test\echo\echo.npz        runs\_verify_legacy_mine\echo\
python pipeline.py --config configs\chirp_point_target_test.json `
  --runs-dir runs --run-name _verify_legacy_mine --skip-observation --skip-echo
# 实际输出：复用已有观测信息 / 复用已有回波数据 → 直接进入 inversion
```

没有给出 `--allow-legacy-reuse`，也没有要求确认。产物形状恰好相容时（本例 251↔251 自洽）连契约校验都不会拦，直接拿去反演；配置层面的变化（目标、PRF、测站等）在这条路径上完全不可见。

**影响**：过期上游产物被当成当前配置的产物消费，属于"静默错误复用"；`tests/test_artifact_contract.py:113-148` 依赖这条路径才会走到契约校验，因此现有测试掩盖了它。

**建议**：把三份 `*.generated.json` 的写入移到复用判定**之后**（或先读取、判定、再覆写）；补一条"CLI 无 `--allow-legacy-reuse` 时必须拒绝无指纹产物"的测试；GUI 侧顺序相反（`main.py:692` 判定在 `:710-712` 写入之前），但同一会话跑过任一阶段后也会落进兜底路径，建议一并改。

### B2（中）manifest 缺 `fingerprint` 时静默复用

`pipeline.py:416-420`：`recorded_fp = recorded.get("fingerprint")`；只有 `recorded_fp and current_fp` 才进入指纹比较分支。若 manifest 条目只有 `output_sha256`（或为空字典），直接落到 `:451` 的兜底，结果同 B1。实测（子代理核查）：observation 与 echo 两个阶段都返回 `reusable=True / requires_confirmation=False`。

> **2026-09-22 更正**：本条写重了。独立实测（`runs/_verify_b2_mine`，脚本已删）：manifest 只有 `output_sha256`、无 `fingerprint`，且 run 目录里**没有**与当前配置一致的 `configs/*.generated.json` 时，判定是 `reusable=False / requires_confirmation=True`（要求 `--allow-legacy-reuse`），不是静默复用；只有在那个 generated 文件存在且与当前配置一致时才 `reusable=True`。所以 B2 不是独立漏洞，而是"指纹门被跳过"，危害要叠在 generated 文件上——正是 B1 与新增 R2 的路径。核实见 `../audits/DEEPSEEK_AUDIT_RESPONSE_RECHECK_2026-09-22.md`。

### B3（中）阶段成功判定过弱

`write_stage_success`（`pipeline.py:370-384`）只对"存在的文件"取哈希，不做内容/大小校验；`check_reusable_artifact` 也只比较哈希相等。因此 0 字节的 `observation_info.npz` / `echo.npz` 会被记成阶段成功，并被判为可复用。GUI 同判据只看 `exists()`（`main.py:934-935`）。目前真正兜底的是后续的 `validate_observation_echo_contract`（空 npz 会触发 numpy 读取错误），所以危害限于"manifest 与复用判定失真"，不是直接产出错误科学结果。

### B4（中）echo 指纹不含模型文件内容

`echo_dependency_projection`（`pipeline.py:319-330`）只带解析后的 `model_path` 字符串；同一路径替换 `model.obj` 内容后指纹不变 → 不触发重跑。同类：`OBSERVATION/ECHO_ARTIFACT_CONTRACT_VERSION` 是手写常量（`pipeline.py:282-283`），改 echo 代码而不 bump 版本就会复用旧回波。建议至少在 echo 投影里加入模型文件的大小+修改时间或内容哈希，并把"改代码要 bump 契约版本"写进 `VERIFICATION_POLICY.md`。

### B5（中）测试入口在受限环境挂起（含 astropy 联网自动更新）

**现象**：
- `python -m pytest -q tests` 在本机两次未跑完（600 s 超时被杀；单文件运行停在 GUI 第 26 个用例）。
- `scripts/run_all_tests.py` 只打印 `== root ==` 与 conda 命令后被杀，从未输出"四组测试全部通过"——脚本没有超时，也没有跳过网络用例的开关。

**根因（栈已捕获）**：`rotation_gui/window/parameter_form.py:819 _refresh_schedule_feedback` → `resolve_campaign_run_plan`（`observation/src/campaign_planning.py:159`）→ `positions_many` → `astropy.time.Time.__add__` → `_check_leapsec()` → `update_leap_seconds()` → `iers.LeapSeconds.auto_open` → `data.clear_download_cache` → `tempfile.mkdtemp`（本机该目录带受限 ACL → 挂起）。触发条件是配置里出现 astropy 大地测站（GUI 里把测站 state 改成 `geodetic` 后，日程反馈就会同步调用 astropy）。

**关键对比**：`inversion/src/ephemeris.py:18-19`、`inversion/src/pointing.py:13-14` 显式设置了 `iers.conf.auto_download=False`；**observation 与 GUI 侧没有任何设置**（全仓 grep：observation 下 0 处）。

**旁证**：把 astropy 自动更新关掉后，observation 套件 **69 passed**（与日志一致，含 6 条 IERS 表超出范围的降级警告）；根套件 **107 passed + 4 failed**，12.84 s 跑完。也就是说 69/111 这些数字本身是对的，但需要"网络可用或 astropy 缓存已热"。冷缓存 + 无网络时，GUI 编辑日程会长时间卡住（用户体验问题），测试入口会直接挂死。

**建议**：在 observation 侧（或 `conftest.py`）设置 `iers.conf.auto_download=False`、`auto_max_age=None`，与 inversion 保持一致；`scripts/run_all_tests.py` 加超时与"跳过网络用例"的开关；GUI 的日程反馈调用放到后台线程或对 astropy 异常降级（现有 `visibility_computed=False` 降级发生在异常之后，对"卡在下载里"无效）。

### B6（中）新批次 4 条测试仍用 `tempfile`

`tests/test_schema_v4_contract.py:485/508/553/598` 使用 `tempfile.TemporaryDirectory()`。在本机（受限 ACL）4 条全部以 `PermissionError: [WinError 5]` 失败——恰好是原子写入与指纹复用这 4 条新功能的测试。仓库其它测试（`tests/test_artifact_contract.py:21`、`tests/test_echo_preview_panels.py:30`、`tests/test_gui_schema_v4.py:42`）以及三个子模块都已改用"工作区内 scratch 目录"的做法，并写明理由；这 4 条是新批次引入的例外。建议补一个根 `tests/scratch.py` 并统一迁移（否则在受限令牌下这 4 条守护是失效的）。

### B7（低·文档）运行目录仍写 `manifest.json`

`DATE_LOG` §4 写"运行目录只保留 `observation.generated.json` / `echo.generated.json` / `inversion.generated.json` 与 `stage_manifest.json`"，但 `pipeline.py:1007` 与 `rotation_gui/window/main.py:713` 仍在写 `run_dir/manifest.json`。"不再写 `experiment.json`"这条本身成立（全仓无写入点）。

### B8（低·文档）Qt 死常量未删除

`DATE_LOG` §3.5 声称删除了"未使用的 Qt 常量与 WebEngine 占位"，实际 `rotation_gui/qt_compat.py:34`（`QT_WEBENGINE_AVAILABLE = False`）与 `:97`（`QWebEngineView = None`）仍在，全仓除定义处外无引用。

### B9（低·文档）`CHIRP_ROW_CONTRACT` §7 的两个 P3 点已过时

§7 写"metadata 的 `fast_sample_count` 目前通过 `int(value)` 转换，手工伪造的 `4.9` 可能被截断为 `4`；`fast_time_s` 只核对首维长度"。当天下一步已修：`echo/src/geometry.py:230-244 _metadata_fast_sample_count` 拒绝布尔/非整/负数，`echo/src/echo.py:411-428 _positive_integer` 同样拒绝布尔与截断，`pipeline.py:229-234` 已断言 `fast_time_s` 必须是**一维**且长度等于行宽。文档未加勘误，建议补一行。

### B10（低）无用字段与绕过路径

- `echo_overlap`：`observation_info.py` 已不再把它写进 npz（`:70-102` 的 `save_npz` 没有该键，metadata 的 `overlap_fields` 也只列 `signal_echo_overlap` / `window_overlap`），但 dataclass 字段（`:62`）与赋值（`:369`）仍在，成为无用字段。
- `inversion/scripts/estimate_period.py` 直接调用时不做 observation↔echo 契约校验（该守卫只在根 pipeline 与 GUI 里），单独跑反演脚本仍可能消费错代产物；`CHIRP_ROW_CONTRACT` §7 只提了 TOCTOU 与"孤立旧 echo"。

### B11（中）`observation.transmit` 只做部分必填校验，空块被静默删除

`normalize_observation_config` 只在 `prf_hz` **与** `pulse_width_s` **同时存在**时才做 Chirp 结构校验（`observation/src/config_normalize.py:277-293`），`_validate_transmit_fields`（`:339-360`）也只检查已存在的键。实测（本轮，`prepare_run(through_stage="echo")`）：

| 配置 | `normalize_observation_config` | `prepare_run` | 生成物里的 `transmit` |
|---|---|---|---|
| `{"prf_hz":20.0,"pulse_width_s":0.01}` | OK | OK | 原样保留 |
| `{"prf_hz":10.0}`（缺脉宽） | OK | **OK** | `{"prf_hz":10.0}` |
| `{"pulse_width_s":0.001}`（缺 PRF） | OK | **OK** | `{"pulse_width_s":0.001}` |
| `{}`（空块） | OK | **OK** | **被静默删除**（`pipeline.py:801-806`） |

后果：GUI/CLI 预检对必然失败的 Chirp 返回"校验通过"；真正的失败点还不一致——整块缺失时由 `observation/src/observation_info.py:406-414` 报"Chirp 脉冲序列需要 observation.transmit"，只缺一个字段时一直拖到 `observation/src/planning.py:96-97` 的 `KeyError`。

> **2026-09-22 更正（我的错误）**：后半句不成立。独立实测：`build_observation_info` 对"缺 `pulse_width_s`"和"空 `transmit` 块"都直接抛 `ValueError: Chirp 脉冲序列需要 observation.transmit.prf_hz 与 observation.transmit.pulse_width_s`——`observation_info.py:411-414` 的逐字段检查在 09-21 就已存在（我当天自己读过这段代码，却没有据此否证子代理给出的 `KeyError` 说法）。真正成立的只有"预检缺口"这一半。`through_stage=inversion` 不检查这两项，符合"选时单测/占用预览需要不完整配置"的取舍。

`DATE_LOG:207` 写"仅有 `schedule`、没有 `transmit` 的残缺 Chirp：规范化与 `build_observation_info` **同一时刻**失败"——实测规范化通过、只有 build 失败；而且该措辞只覆盖"整块缺失"，不覆盖"缺单个字段"。建议：在规范化里要求 Chirp 的 `transmit` 必须同时给出 `prf_hz` 与 `pulse_width_s`（并拒绝空块），再订正文档措辞。

### B12（中）Chirp 的 `echo.waveform.bandwidth_hz` 没有必填校验

实测（本轮，删掉夹具的 `bandwidth_hz` 与 `baseband_convention`）：`prepare_run(through_stage="full_pipeline")` **成功**，产出 `echo.waveform={'type':'chirp_pulse_train','amplitude':1.0}`；`echo/src/config_normalize.py` 也不报错（它只在键存在时校验），直到 echo 核心 `_chirp_fast_time_axis`（`echo/src/echo.py:105`）才 `KeyError: 'bandwidth_hz'`（独立子代理进一步跑通了真实子进程：`simulate_echo.py` 退出码 1）。GUI 默认值由 `rotation_gui/window/parameter_form.py:115-119,1512-1513` 补齐，手动清空该输入框即可到达。

`pipeline.assemble_echo_waveform`（`:817-834`）只对已存在的 `bandwidth_hz` 与采样率比较大小。建议把"chirp 必须有正有限 `bandwidth_hz`"作为规范化必填项，并补一条会在缺该键时变红的测试（目前没有）。

### B13（低）CW 分支对 Chirp 专属块只是静默忽略

实测：`observation = {target, transmitter, receive} + radar_system`（`+receiver_sampling` 同理）通过规范化并被原样保留；只有 `schedule` 会因"不能同时提供 `schedule` 与 `receive`"报错（`observation/src/config_normalize.py:140-150,256-261` 只禁 `transmit`）。对照 Chirp 分支：`transmit` 里写 `bandwidth_hz`/`amplitude`/`baseband_convention`/`carrier_frequency_hz`/`type` 都会被拒（`pipeline.py:779-797`、`config_normalize.py:343-346`）。属于静默残留，不是违反已写明的声称（`WAVEFORM_OWNERSHIP:12` 只写了"不得出现 `observation.transmit`"）。

---

## 4. 本轮实测的测试基线

| 套件 | 命令 | 结果 |
|---|---|---|
| 根 | `python -m pytest -q tests` | **挂起**（见 B5）；禁用 astropy 自动更新后 12.84 s 完成：**107 passed, 4 failed**（4 条为 B6 的 tempfile 失败） |
| observation | `python -m pytest -q observation/tests` | **挂起**（astropy，见 B5）；`iers.conf.auto_download=False` 后 **69 passed**, 6 warnings（与 `DATE_LOG` 一致） |
| echo | `cd echo; python -m pytest -q tests` | **43 passed**（与 `DATE_LOG` 一致） |
| inversion | `python -m pytest -q inversion/tests` | **24 passed, 3 skipped**（与 `DATE_LOG` 一致） |
| 汇总入口 | `python scripts/run_all_tests.py` | 卡在 root 套件，无超时、无汇总（见 B5） |

### 变异实验（T1 的区分力，本报告直接证据）

把 `observation/src/planning.py` 的 `after_s * fs_hz + 0.5` 常量改成 $c$，跑 `pytest -q observation/tests/test_planning_regressions.py -k post_guard`：

| $c$ | 结果 |
|---|---|
| 0.5 | 13 passed |
| 0.45 | 1 failed（`test_post_guard_margin_dense_fraction_and_extent_never_negative`） |
| 0.4 | 1 failed（同上） |
| 0.3 | 2 failed（同一用例 + `test_post_guard_margin_grid_never_negative`） |

文件已还原（校验 `ReadAllText == 原内容` 为 True）。

---

## 5. 已核对为正确、不属于问题的部分

- **可见性语义**：`config_normalize.py:243` 拒绝自定义直角坐标上的可见性字段（混合测站只拒绝无地平一侧）；`campaign_planning.py:170-194` 区分 `visibility_applicable` / `visibility_computed`；GUI 灰色斜纹只在 `applicable && !computed` 时出现（`parameter_form.py:253-254,372-374`），并有区分测试。
- **批处理与缓存**：`pulse_batch_size=1` 仍走 batch kernel（`echo/tests/test_chirp_batching.py:360` 断言调用 `_gather_chirp_sample_pairs`）；`Spin` 姿态张量缓存键含设备、初相位、周期、自转轴并清理陈旧项（`echo/src/motion.py:73-96`）。
- **配置校验**：`exact_integer` 拒绝布尔/截断/非正（observation `:71-87`、echo `:54-68`）；自动选时带 `runs`、equal 带 `random_seed`、缺 `run_duration_s` 均报路径化错误（子代理逐条实测）。
- **指纹与原子写**：改 `inversion.*` 不影响 echo/observation 指纹，改 `echo.radar` 只影响 echo 指纹，observation 文件内容变则 echo 复用被拒；`pipeline.write_json` / `storage.write_json` 为同目录 mkstemp+fsync+`os.replace`，失败时旧文件完好、无 `*.tmp` 残留（子代理实测）。
- **`through_stage` 分阶段校验**：`fs < bandwidth` 在 `observation`/`inversion` 通过、在 `echo`/`full_pipeline` 报错（实测）。
- **`model_path` 解析**：配置目录优先、仅模块目录时警告、两处不同则拒绝、生成配置写绝对路径（子代理实测）。
- **波形从属（本次自查判别分支）**：旧 `observation.waveform` 报"已废弃…请写 `observation.transmit`"；`echo.waveform.type` 缺失或空串时按事件源补齐；与事件源不一致时报错；CW 带 `observation.transmit` 报错；`prepare_run` 不修改调用方内存（深拷贝）——均实测。端到端：迁移成 `transmit` 的夹具跑观测解算成功，得到 8×252 全有效。
- **GUI 侧（独立子代理核查，逻辑与探针一致）**：切换波形时不会把 `transmit` 与 `receive` 同时写盘（`parameter_form.py:1441-1479`）；`collect()` 遇 `observation.waveform` 抛中文废弃错误且不清掉已填的 PRF；载入含旧字段的 JSON 时抛错并由 `main.py:499-500` 弹"载入失败"，配置保持载入前状态（不半载入）。
- **文档落盘措辞**：`PROJECT_OVERVIEW.md:50/60/71/74`、`ARCHITECTURE_V4.md:34/37`、`GLOSSARY.md:56-57/62`、`OBSERVATION_TIME_SELECTION.md:54`、`GUI_USER_MANUAL.md:44` 均已是 `transmit`，4.2 正文里没有残留的 `waveform.pulse_width_s`。
- **停止写 `experiment.json`**、`inversion/.gitignore` 白名单、`require_sections`/`STAGE_GROUP_ORDER`/`EPHEMERIS_FIELD_ORDER`/`storage.flatten` 删除、`INVERSION_ENTRY` 顺序、`spin_pole` 长度 2、`echo.py` 导入 `C`：均已核实（部分由子代理核实）。

---

## 6. 复现命令

```powershell
# 四组测试（受限环境下先关 astropy 自动更新，否则 observation/root 会挂）
python -m pytest -q tests
python -m pytest -q observation/tests
Push-Location echo; python -m pytest -q tests; Pop-Location
python -m pytest -q inversion/tests

# B1：无指纹历史产物被 CLI 静默复用
#   run 目录只放旧 observation/echo、无 stage_manifest.json，然后
python pipeline.py --config configs\chirp_point_target_test.json `
  --runs-dir runs --run-name <scratch> --skip-observation --skip-echo

# T1 变异：把 observation/src/planning.py 的 "+ 0.5" 改成 "+ 0.45"（跑完还原）
python -m pytest -q observation/tests/test_planning_regressions.py -k post_guard

# B5：astropy 自动更新的影响面
python -c "import astropy.utils.iers as iers; iers.conf.auto_download=False; import pytest,sys; sys.exit(pytest.main(['-q','observation/tests']))"

# B11/B12/B13：在 Python 里构造残缺 transmit / 缺 bandwidth_hz 的 chirp / CW 带 radar_system，
# 调 pipeline.prepare_run(..., through_stage="echo"/"full_pipeline") 与
# echo.src.echo.waveform_bandwidth_hz，观察"预检通过、核心 KeyError"
```

**本次核查留下的残留**：`_probe_tmp/`（12 个 `mkdtemp` 子目录）与 `_probe_tmp_root/`（4 个）——`Remove-Item`、`rd /s /q`、`icacls /reset` 均因 `WinError 5` 失败，无法删除；它们本身就是 B5/B6 所述 ACL 现象的直接证据，并且会让 `git status` / `git add -A` 每次输出 `warning: could not open directory '_probe_tmp/...': Permission denied`（`echo/tmp/` 下的历史残留同理）。其余临时探针、复现目录与一个孤立的 `.tmp_gui_state__*` 目录已删除。

---

## 7. 未判定项

1. GUI 的"需确认"对话框是否真的弹出：只验证到 `ReuseDecision.requires_confirmation=True` 与 `main.py:620-632` 的分支代码，未跑 Qt 事件循环模拟 Yes/No（GUI 侧本机跑不通，见 B5）。
2. "陈旧产物 + 子进程退出 0 但产物损坏"的端到端后果：只证明了判定无内容校验（B3）。
3. `write_json` 在断电/强杀时的 `*.tmp` 残留与目录 fsync：未做注入式测试。
4. 契约版本常量能否覆盖代码演进：需要跨版本产物对比才能定量。
5. GUI 与 pipeline 对"空字符串 `echo.waveform.type`"的语义可能不一致：pipeline 把空串当"未填"并按事件源补齐（实测），而 GUI `collect()` 路径出现"只剩 `type`+`amplitude`、随后 `canonical_pipeline_config` 报 `type 必须是 continuous_wave 或 chirp_pulse_train`"的迹象；定位探针未完成，需要单独核 GUI 的字段剥离步骤。
6. GUI 在 Chirp↔连续波之间来回切换后，`transmit` 回到默认值（4.0/0.001）而不是用户刚才填的值；`DATE_LOG:206/216` 已把它列为"明确未做/已知"，本轮无法判定是否本批引入（需要 4.1 基线对比）。
