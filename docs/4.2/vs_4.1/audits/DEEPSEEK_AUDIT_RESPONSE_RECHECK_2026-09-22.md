# 对《对 DeepSeek 两轮质检的回执》的复核（2026-09-22）

> **状态：只记录核查结论，未改动业务代码或既有文档**（仅在 [`../plans/REVIEW_2026-09-21_ROUND2.md`](../plans/REVIEW_2026-09-21_ROUND2.md) 的 B2、B11 两节加了"2026-09-22 更正"块，说明我上一轮写错的部分）。
> **对象**：[`DEEPSEEK_AUDIT_RESPONSE_2026-09-22.md`](DEEPSEEK_AUDIT_RESPONSE_2026-09-22.md) 的 §2–§8 判定与 §5 的七项修复。
> **方法**：读代码定位 + 真实 CLI 复现（含三步对抗序列）+ 四组测试；全部在本机受限令牌、无网络环境下实测。
> **环境**：Windows + conda `pytorch`；无网络；仓库根可写，而仓库根 `tmp/` 与 `tests/` 在当前令牌下不可写（见 R1）。

---

## 1. 判定总表

| 回执条目 | 我的核对结论 |
|---|---|
| §5.1 B1 CLI 复用判定顺序 | **属实、修复正确**（三步序列实测，见 §2.1） |
| §5.2 B12 Chirp 缺 `bandwidth_hz` | **属实、修复正确**；"运行观测仍不检查回波带宽"也成立（见 §2.2） |
| §5.3 B11 残缺 `transmit` | **属实、修复正确**；`through_stage=inversion` 不查，符合"选型单测/占用预览需要不完整配置"的取舍 |
| §5.4 B5 观测侧 IERS | **属实、有效**：不加任何补丁跑 `pytest -q observation/tests` → **69 passed**，不再挂起 |
| §5.5 B3 空产物记成功 | **属实**：`require_stage_artifact`（`pipeline.py:143-162`）在记成功与判定复用前要求非空、可打开、含 `elapsed_s`/`valid_plan`/`iq` |
| §5.6 B6 临时目录 | **修法在本环境失效** → R1 |
| §5.7 B7/B8/B9 | **属实**：`DATE_LOG_2026-09-21` 文首勘误 §4；`CHIRP_ROW_CONTRACT` §7 已加勘误；`rotation_gui/qt_compat.py` 的 WebEngine 占位已删除 |
| §4 B2「单独不成立」 | **他们对，我上一轮写重了**（见 §4.1） |
| §3.3 B11「`KeyError` 说法不成立」 | **他们对，我上一轮写错了**（见 §4.2） |
| §3.1 / §3.2 / §3.4 | 反驳的三条（源文件乱码、`capture_output` 管道死锁、metadata 列三项）**不是 ROUND2 的结论**，来自 [`deepseek_audit_2026-09-21_1.md`](deepseek_audit_2026-09-21_1.md)，因此不构成对本轮 B1–B13 的回应；其中 §3.2 把挂起归因到 astropy IERS 与我的栈证据一致（细节差异见 §5） |
| §8 验收数字 | observation 69 / echo 44 / inversion 24+3 与我实测**完全一致**；**"根 118 passed"在本环境不成立**（实测 50 passed / 68 failed，原因见 R1） |

---

## 2. 已核实为正确的修复（含复现）

### 2.1 B1：三步对抗序列（真实 CLI）

run 目录只放 251 列旧 observation/echo（自洽、形状相容）、无 `stage_manifest.json`：

| 步骤 | 命令 | 实测结果 |
|---|---|---|
| 1 | `--skip-observation --skip-echo`（不给开关） | 退出码 1，`无法复用观测产物：观测信息缺少可核对的阶段指纹；GUI 需确认，CLI 需 --allow-legacy-reuse`；**`configs/` 里 0 个文件**（旧版会先写下三份 generated） |
| 2 | 同上 + `--allow-legacy-reuse` | `按兼容开关复用缺少阶段指纹的历史观测信息` / `…历史回波数据`；`configs/` 里**只有** `inversion.generated.json`（观测/回波的 generated 未被覆盖，历史证据保留） |
| 3 | 再执行步骤 1 | **仍然拒绝**（退出码 1，同一条理由）——"允许一次之后不能靠刚写的 generated 静默过门"成立 |

### 2.2 B11 / B12：分阶段预检

`prepare_run` 实测（同一夹具改字段）：

| 配置 | `observation` | `echo` | `inversion` |
|---|---|---|---|
| `transmit` 完整 | OK | OK | OK |
| 缺 `pulse_width_s` | **ValueError**：Chirp 脉冲序列需要 observation.transmit.prf_hz 与 observation.transmit.pulse_width_s | 同左 | OK |
| 缺 `prf_hz` | 同上 | 同上 | OK |
| `transmit = {}` | 同上 | 同上 | OK |
| chirp 缺 `bandwidth_hz` | **OK**（运行观测本不该因回波字段失败） | **ValueError**：Chirp 回波需要 echo.waveform.bandwidth_hz | — |

### 2.3 B5：IERS 与测试入口

`observation/src/iers_policy.py` 在导入时设 `auto_download=False`、`auto_max_age=None`，并被 `campaign_planning.py:12/23`、`ephemeris.py:9/13` 导入（GUI 通过 `campaign_planning` 也受保护）；根与 observation 的 `conftest.py` 再设一次。实测：不加任何补丁，observation 套件 **69 passed**（6 条 IERS 表范围警告），不再挂起。

---

## 3. 仍然存在的问题

### R1（高，环境相关）scratch 移到根 `tmp/` 后，受限令牌下根套件 68 条失败

`tests/scratch.py:23` 把 scratch 建在 `ROOT / "tmp" / f"{name}_{pid}"`。在本机受限令牌下，**仓库根可写、`tmp/` 不可写**：

```
New-Item tmp\_wtest_mine   → Access to the path '_wtest_mine' is denied
New-Item _wtest_root       → 成功（仓库根可写）
icacls .   → . S-1-4-509851513-450554086:(OI)(CI)(W,D,DC)   ← 沙箱令牌的写权限 ACE 在仓库根
icacls tmp → 只有继承 ACE，且不含该 S-1-4-… 条目            ← tmp/ 没有这条写权限
```

实测 `pytest -q tests`：**50 passed / 68 failed**（57 条 GUI + 6 条 artifact_contract + 5 条 schema_v4_contract），全部失败栈都在 `tests/scratch.py:23 path.mkdir(...)` → `PermissionError: [WinError 5]`；即"为绕开受限 ACL 而做的迁移"在当前令牌下**把失败面从 4 条扩大到 68 条**（迁移前同一环境实测为 107 passed + 4 failed，那 4 条是 `tempfile`）。

**建议**：`scratch_directory` 先探测可写性——优先 `tmp/`，`PermissionError` 时回退到仓库根的 `.tmp_<name>_<pid>`（`.gitignore` 已有 `.tmp_*/`），或直接固定用仓库根；不要假定 `tmp/` 一定可写。

### R2（中）失败的运行仍会留下 `*.generated.json`，随后可"为陈旧产物作证"

B1 修掉的只是"CLI 在判定前先写当前配置"这一条；三份 generated 现在仍在**阶段真正执行之前**写好（`pipeline.py:965-969` 早于 `run_step`），失败时也不清除。实测：

1. run 目录放入**与当前配置不同几何**的合法 252 列产物（`metadata.transmitter_config.position_m = [0,0,0]`），配置里把测站改成 `[1e6, 0, 0]`；
2. 用坏解释器跑一次（模拟子进程启动失败/中断/崩溃）：退出码非 0，但 `configs/` 里留下了 `observation.generated.json`、`echo.generated.json`、`inversion.generated.json`（后两者对应的阶段根本没跑）；
3. 再跑 `--skip-observation --skip-echo`（**不给** `--allow-legacy-reuse`）：打印 `复用已有观测信息` / `复用已有回波数据`，并直接进入 inversion。

产物里的测站位置仍是 `[0.0, 0.0, 0.0]`，当前配置是 `[1000000.0, 0.0, 0.0]`——行宽契约不会发现（形状同代、echo 记录的 observation SHA-256 也自洽）。回执 §5.1 说的"允许一次之后不能靠刚写的 generated 静默过门"在**跳过阶段**这条路径上成立（我已实测），但**失败运行**这条路径没被覆盖。

**建议**：每个阶段的 generated 文件在该阶段启动前才写（echo 的 generated 不要在 observation 之前写），失败/中止时删除；或只承认"`stage_manifest.json` 里存在同 `output_sha256` 的指纹记录"时的 generated 为凭据。

### R3（低）子进程启动失败时 CLI 抛原始 traceback

`--python` 指向不存在的解释器时，`pipeline.py` 以 `Traceback … line 1069, in <module> main()` 结束（`FileNotFoundError` 未被 `run_step` 转成中文错误），而 GUI 有 `FailedToStart` 分支。建议与 GUI 对齐给出一句可读错误（顺带在失败时清掉 R2 的 generated）。

### R4（低，口径）"根 118 passed"是环境相关数字

`DATE_LOG_2026-09-22` 与回执 §8 记"根 118 passed"。在受限令牌环境实测为 50/68（原因 R1）；在可写 `tmp/` 的环境（维护者自身会话）才应等于 118。建议在该数字旁注明环境前提，或让测试对 `tmp/` 不可写的情况降级跳过而不是整片失败。

---

## 4. 我上一轮报告的两处更正

### 4.1 B2 不是独立的静默复用漏洞（他们对）

独立实测（run 目录放合法产物 + `stage_manifest.json` 内只有 `output_sha256`、`fingerprint: null`）：

| 条件 | reusable | requires_confirmation |
|---|---|---|
| 没有 `configs/observation.generated.json` | **False** | **True**（理由：缺少可核对的阶段指纹） |
| 存在与当前配置一致的 `configs/observation.generated.json` | True | False |

所以 B2 本身只是"指纹门被跳过"，危害要叠在 generated 文件上。ROUND2 已加更正块。

### 4.2 B11 的 `KeyError` 说法不成立（他们对，我的错误）

实测 `build_observation_info`（09-22 之前的代码路径也一样，因为该检查在 09-21 就存在）：

```
transmit={"prf_hz": 10.0} → ValueError: Chirp 脉冲序列需要 observation.transmit.prf_hz 与 observation.transmit.pulse_width_s
transmit={}               → 同一条 ValueError
```

不是 `planning.py` 的下标 `KeyError`。我上一轮引用了子代理未经我复现的结论，而这段代码我在 09-21 当天自己读过（`observation_info.py:411-414`），本应据此否证——这是"未核实的转述"型错误，ROUND2 已加更正块。

---

## 5. 细节差异（不影响结论）

- 回执 §3.2 说卡住的用例是 `test_mixed_stations_show_only_horizon_side_visibility_fields`；我的看门狗栈显示实际卡在紧随其后的 `test_mode_switch_does_not_unparent_visible_widgets`（`test_gui_schema_v4.py:1489` 的 `processEvents` → `parameter_form._refresh_schedule_feedback` → `campaign_planning` → astropy）。机制相同（前一个用例把测站改成 `geodetic` 并留下会话状态），只是用例名不同。
- 回执 §4 提到"单独造只有文件哈希、没有 generated 的 manifest 时…不可复用"——与 §4.1 的实测一致。
- `CHIRP_ROW_CONTRACT` §7 的勘误与 `DATE_LOG_2026-09-22:151` 的对抗审查记录，都只覆盖"跳过阶段仍写 generated"，未覆盖 R2 的"失败运行留下 generated"。

---

## 6. 复现命令

```powershell
# 四组测试（本机受限令牌环境）
python -m pytest -q tests                 # 50 passed / 68 failed（R1）
python -m pytest -q observation/tests     # 69 passed（B5 修好后不再挂起）
cd echo; python -m pytest -q tests        # 44 passed
python -m pytest -q inversion/tests       # 24 passed, 3 skipped

# R1：tmp/ 可写性
New-Item -ItemType Directory tmp\_wtest   # Access denied
New-Item -ItemType Directory _wtest       # 成功

# R2：失败运行留下 generated 后静默复用
#   run 目录放一份合法但几何不同的 252 列产物，配置改 transmitter.position_m，
#   用 --python Z:\nope\nope.exe 跑一次（留下 generated），
#   再 --skip-observation --skip-echo 跑一次（打印"复用已有…"）
```

**本轮核查残留**：复现用的 `runs/_verify_b1_mine`、`runs/_verify_b1b_mine`、`runs/_verify_b2_mine`、`runs/_verify_922_mine`、`_verify_cfg_922.json` 与探针脚本 `_probe_922.py`、`_probe_b2.py` 均已删除；`_probe_tmp/`、`_probe_tmp_root/` 两处 ACL 锁死的空壳来自上一轮，仍在。

---

## 7. 第二轮回执（R2 修复）的复核（同日稍晚）

> 对象：[`DEEPSEEK_AUDIT_RESPONSE_2026-09-22_ROUND2.md`](DEEPSEEK_AUDIT_RESPONSE_2026-09-22_ROUND2.md) §5.1 的 R2 修复与两条相邻收紧。全部为本轮实测。

### 7.1 判定：R2 修复正确、完整，正反两面都验证过

| 声称 | 我的实测 |
|---|---|
| `check_reusable_artifact` 不再打开 `*.generated.json` | `pipeline.py:409-496` 全文已无 generated 兜底；判定只读 `stage_manifest.json` |
| 自动复用 = 指纹一致 **且** 记录里有文件哈希并与当前文件一致 | 真跑观测 → `write_stage_success` → `reusable=True`「复用已有观测信息」；改 `transmitter.position_m` → 硬阻断并点名 `observation.transmitter.position_m` |
| 指纹相同但记录缺哈希 → 不静默，要确认/旗标 | 不带旗标 `reusable=False, requires_confirmation=True`；带 `--allow-legacy-reuse` → 复用（理由"按兼容开关复用缺少文件哈希"） |
| 有指纹、当前配置算不出指纹 → 硬阻断，旗标也不过 | `prepare_run(through_stage="inversion")` 且 echo 规范化失败时 `echo_fingerprint=None` → 两种旗标下都 `reusable=False`；对应用例 `test_recorded_fingerprint_without_current_fingerprint_is_hard_block` 已存在 |
| generated 写入挪到各阶段 `run_step` 正前方 | `pipeline.py:960 / 987 / 1031`；端到端复现：坏解释器跑一次后 `configs/` 里**只有** `observation.generated.json`（旧版会写齐三份） |
| R2 端到端洞已关闭 | 失败运行 + `--skip-observation --skip-echo`（不给旗标）→ 退出码 1，`无法复用观测产物：观测信息缺少可核对的阶段指纹…`，不再静默复用 |

守卫测试齐备：`test_root_cli_does_not_reuse_matching_generated_without_fingerprint`、`test_leftover_generated_does_not_silently_reuse_echo`（GUI）、`test_matching_generated_json_is_not_reuse_evidence`、`test_matching_fingerprint_without_output_hash_is_not_silent_reuse`、`test_recorded_fingerprint_without_current_fingerprint_is_hard_block`、`test_missing_echo_fingerprint_does_not_reuse_on_hash_match`。

文档同步已核对：`DATE_LOG_2026-09-22` §10、`CONFIG_FINGERPRINT_AND_GUI_SEAM_2026-09-21.md` 文首 09-22 勘误、`GUI_LOG_AND_OUTPUT.md:98`、`../plans/VERIFIED_FIX_PLAN_2026-09-22.md:37`。

### 7.2 R1 仍未处理，且本环境失败面随用例增加而变大

`tests/scratch.py` 依旧把 scratch 建在仓库根 `tmp/` 下；本机受限令牌实测 **72 failed / 50 passed**（共 122 项，与回执的"根 122 passed"是同一批用例），72 条全部是 `PermissionError`（`tests/scratch.py` 的 `mkdir`）。回执选择不加"探测可写性再回退"，理由是约定环境 `tmp/` 可写——在维护者会话成立，但在受限令牌下根组仍不能作为验收。建议仍保留三行回退（`tmp/` 失败时用仓库根 `.tmp_<name>_<pid>`，`.gitignore` 已有 `.tmp_*/`）。

### 7.3 R5（新，低，仅 API 层）：`through_stage="inversion"` 不补 `echo.waveform.type`

`_fill_echo_type_from_event_source` 只在 observation / echo / full_pipeline 三条路径调用（`pipeline.py:544/559`），`normalize_config` 也会补（`:736`）；`through_stage="inversion"` 分支不补，直接 `normalize_echo_config` 并在失败时吞掉异常（`:569-575`）。实测：省略 `echo.waveform.type` 的**原始**配置在 `through_stage="inversion"` 下 `echo_fingerprint=None`，与 7.1 的硬阻断叠加后会变成"旗标也过不去"的死角。

**但已发布的入口不受影响**：CLI 在 `main()` 里先走 `canonical_pipeline_config`（会补 type），实测省略 `type` 的配置文件 + `--skip-observation --skip-echo` 正常打印"复用已有观测信息 / 复用已有回波数据"；GUI 载入同样经过 `canonical_pipeline_config`。所以这条只是直接调用 `prepare_run` 的 API 使用者的健壮性问题。建议在 inversion 分支也调一次 `_fill_echo_type_from_event_source`（与另两条路径对齐）。

### 7.4 其余

- R3（缺解释器时原始 traceback）仍未处理，但回执说"R2 落地后不再需要顺手删 generated"——这一点成立（失败运行只留一份该阶段 generated，且它已不是复用证据）。
- 回执 §3.1/§3.2 回应的"乱码"两条来自 `deepseek_audit_2026-09-22_2.md`，不是本线程的核查结论；我不对其内容表态，只确认：本机 PowerShell 5.1 直接 `Get-Content`/`Select-String` 读无 BOM 的 UTF-8 确实会把"失败"显示成"澶辫触"，属于阅读代码页问题。
- 本轮四组测试：根 72 failed / 50 passed（R1）；observation 69 passed；echo 44 passed；inversion 24 passed, 3 skipped（后三组与回执一致）。
