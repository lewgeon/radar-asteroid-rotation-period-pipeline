核查完了，回执里的七项修复我都逐条实测过。结论：**修复本身基本都正确，但有两处遗留问题（其中一处是我上一轮报告也有责任），另外我上一轮有两个结论确实写错了。**

复核报告写在 `docs/4.2/vs_4.1/audits/DEEPSEEK_AUDIT_RESPONSE_RECHECK_2026-09-22.md`，并在 `ROUND2` 的 B2、B11 两节加了更正块。

## 一、七项修复：实测都正确

| 项 | 我的实测 |
|---|---|
| B1 复用判定顺序 | 三步序列：不给开关 → 退出码 1 且 `configs/` **0 个文件**（旧版会先写三份）；给 `--allow-legacy-reuse` → 复用且只写 `inversion.generated.json`（历史证据没被覆盖）；再不给开关 → **仍然拒绝**。"允许一次后不能靠刚写的 generated 过门"成立 |
| B12 缺 `bandwidth_hz` | `observation` OK / `echo`、`full` 报"Chirp 回波需要 echo.waveform.bandwidth_hz" —— 与"运行观测不该因此失败"的声称一致 |
| B11 残缺 `transmit` | 缺单字段与空块都在 `observation`/`echo` 被拒（同一条字段路径中文错误），`inversion` 不查 —— 符合取舍 |
| B5 IERS | `iers_policy` 被 `campaign_planning`/`ephemeris` 导入 + 两个 conftest；**不加任何补丁**跑 observation → 69 passed，不再挂起 |
| B3 空产物 | `require_stage_artifact` 要求非空、可打开、含 `elapsed_s`/`valid_plan`/`iq`，且在记成功与判复用之前调用 |
| B7/B8/B9 | 09-21 日志文首勘误、`CHIRP_ROW_CONTRACT` §7 勘误、WebEngine 占位已删 |
| B2 / B11 的两处"误判"反驳 | **他们对**（见下） |

## 二、我上一轮写错的两处（已在 ROUND2 加更正）

- **B2**：我写"manifest 缺 fingerprint 就静默复用"太重了。实测：只有 `output_sha256` 而**没有**同配置的 `configs/*.generated.json` 时，判定是 `reusable=False / requires_confirmation=True`；只有那个 generated 文件存在时才 `True`。B2 不是独立漏洞，而是"指纹门被跳过"。
- **B11 的 `KeyError`**：我引用了子代理未经复现的结论。实测 `build_observation_info` 对缺单字段和空块都直接抛字段路径中文错误（该检查 09-21 就在 `observation_info.py:411-414`，我当天还读过这段代码却没据此否证）。这条是我的"未核实转述"错误。

另外，回执 §3.1/§3.2/§3.4 反驳的"源文件乱码 / 管道死锁 / metadata 列三项"**不是我的 ROUND2 里的结论**（来自 `deepseek_audit_2026-09-21_1.md`），所以那三节不构成对我核查的回应；其中 §3.2 把挂起归因到 astropy IERS，与我的栈证据一致。

## 三、仍然存在的问题

**R1（高，最要紧）scratch 移到根 `tmp/` 后，本环境根套件 68 条失败。**
`tests/scratch.py:23` 把目录建在 `ROOT/tmp/`。本机**仓库根可写、`tmp/` 不可写**：`New-Item tmp\_wtest` → Access denied，`New-Item _wtest`（仓库根）→ 成功；ACL 上沙箱写权限 ACE `S-1-4-…:(OI)(CI)(W,D,DC)` 只在仓库根、`tmp/` 没有。实测 `pytest -q tests` = **50 passed / 68 failed**（57 GUI + 6 artifact_contract + 5 schema_v4_contract），失败栈全在 `tests/scratch.py:23 path.mkdir(...)` → WinError 5。也就是说这条"为受限 ACL 而做的迁移"把本环境的失败面从 4 条扩大到 68 条（迁移前同环境是 107/4）。建议 scratch 先探测可写性，`tmp/` 不行就回退到仓库根 `.tmp_*`（`.gitignore` 已有 `.tmp_*/`）。

**R2（中）失败的运行仍会留下 `*.generated.json`，随后能"为陈旧产物作证"。**
三份 generated 现在仍在阶段执行**之前**写好（`pipeline.py:965-969` 早于 `run_step`），失败时不清除。实测：产物测站 `[0,0,0]`、配置改成 `[1e6,0,0]` → 用坏解释器跑一次（留下三份 generated）→ 再 `--skip-observation --skip-echo`（**不给**开关）→ 打印"复用已有观测信息/复用已有回波数据"，直接进 inversion；行宽契约发现不了（形状同代、echo 记录的 SHA 自洽）。建议每个阶段的 generated 在该阶段启动前才写、失败即删，或只承认 manifest 里有同 `output_sha256` 指纹记录的 generated。

**R3（低）** `--python` 指向不存在的解释器时 CLI 抛原始 traceback（GUI 有 `FailedToStart` 分支），建议给中文错误并顺手清掉 R2 的 generated。

**R4（低，口径）** "根 118 passed"是环境相关数字；受限令牌下实测 50/68。observation 69 / echo 44 / inversion 24+3 与我实测完全一致。

两处细节差异另记：卡住的 GUI 用例名（我的栈是紧随其后的 `test_mode_switch_does_not_unparent_visible_widgets`，机制相同）；以及回执的对抗审查只覆盖了"跳过阶段仍写 generated"，没覆盖 R2 的"失败运行留下 generated"。复现残留（4 个 `runs/_verify_*`、配置与探针）已全部清理。