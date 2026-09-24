补充核查（一个独立子代理的波形从属专项在结束后回传了结果，我已逐条自测复现，报告已更新为 **B1–B13**）。

## 新增的 3 项问题（均已我用探针复现）

**B11（中）`observation.transmit` 只做"部分字段"校验，空块被静默删除**

| 配置 | `normalize_observation_config` | `prepare_run` | 生成物里的 `transmit` |
|---|---|---|---|
| 完整（prf + 脉宽） | OK | OK | 原样保留 |
| 缺 `pulse_width_s` | OK | **OK** | `{"prf_hz":10.0}` |
| 缺 `prf_hz` | OK | **OK** | `{"pulse_width_s":0.001}` |
| `{}` 空块 | OK | **OK** | **被静默删除** |

原因：`observation/src/config_normalize.py:277-293` 只在两个字段**都存在**时才做 Chirp 结构校验；`pipeline.py:801-806` 对空块直接 `pop`。后果是 GUI/CLI 预检对一个必然失败的 Chirp 说"校验通过"，而真正报错的时机还不一致（整块缺失 → `observation_info.py:406-414`；只缺一个字段 → 拖到 `planning.py:96-97` 的 `KeyError`）。`DATE_LOG:207` 写"规范化与 `build_observation_info` **同一时刻**失败"，实测不成立。

**B12（中）Chirp 的 `echo.waveform.bandwidth_hz` 完全没有必填校验**

删掉该键后 `prepare_run(through_stage="full_pipeline")` 成功、echo 自己的 `normalize_echo_config` 也放行，直到 echo 核心 `echo/src/echo.py:105` 才 `KeyError: 'bandwidth_hz'`（子代理跑真实子进程得到 `simulate_echo.py` 退出码 1）。`pipeline.assemble_echo_waveform:830` 只对"已存在的"带宽与采样率比较。GUI 手动清空带宽输入框即可到达，且没有任何测试会在缺该键时变红。

**B13（低）CW 分支对 Chirp 专属块静默忽略**

`{target, transmitter, receive} + radar_system`（`+receiver_sampling` 同理）能通过规范化并被原样保留、不参与计算；而 Chirp 分支对 `transmit` 里的 `bandwidth_hz`/`amplitude`/`type` 等一律拒绝——两边不对称，属静默残留。

## 独立核查确认正确的部分（补充）

- GUI 切换波形时不会把 `transmit` 与 `receive` 同时写盘（`parameter_form.py:1441-1479`）；
- `collect()` 遇 `observation.waveform` 抛中文废弃错误，且**不会**清掉已填的 PRF；载入含旧字段的 JSON 时抛错并弹"载入失败"，配置保持载入前状态（不半载入）；
- 4.2 正文（概况/架构/术语表/选时/手册）已全部写 `transmit`，没有残留 `waveform.pulse_width_s`；
- 真实 observation CLI 走 `transmit` 落盘（metadata `prf_hz=20.0`、`pulse_width_s=0.01`、`fast_sample_rate_hz=5000.0`）。

## 新增未判定项（写入报告 §7）

1. GUI 与 pipeline 对**空字符串 `echo.waveform.type`** 的语义可能不一致：pipeline 把空串当"未填"并按事件源补齐，而 GUI `collect()` 路径出现"只剩 `type`+`amplitude`、随后报 `type 必须是 continuous_wave 或 chirp_pulse_train`"的迹象；定位探针未完成。
2. GUI 在 Chirp↔连续波来回切换后 `transmit` 回到默认值 4.0/0.001（`DATE_LOG` 已列为已知未做，本轮无 4.1 基线，判不了是否本批引入）。

报告：`docs/4.2/vs_4.1/plans/REVIEW_2026-09-21_ROUND2.md`（224 行，含 B1 的独立复现命令、T1 变异表、测试基线、未判定项）。索引已更新在 `plans/README.md`。核查期间产生的探针脚本已全部删除；`_probe_tmp/`、`_probe_tmp_root/` 两个 ACL 锁死的空壳目录（WinError 5，`takeown`/`icacls`/`rd` 均失败）需要更高权限会话清理，其余无残留。