# GUI 日志与产物输出改造（4.2）

> 状态：已在 4.2 实现。本文记录相对 4.1 的已落地行为变化，不是待实施计划。

本文说明 4.2 中 GUI 日志区与阶段产物输出的行为约定、机器协议格式，以及相应的实现位置。相关代码：

| 文件 | 职责 |
|---|---|
| `rotation_gui/schema.py` | 协议前缀常量：`PROGRESS_PREFIX`、`WARNING_PREFIX`、`ERROR_PREFIX`、`SUMMARY_PREFIX` |
| `rotation_gui/window/main.py` | `_append_log`（渲染）、`_handle_output_line`（协议解析）、`_process_finished`/`_process_error`（状态收尾）、`_run_next_pending_stage`（上游产物检查与复用提示） |
| `echo/simulate_echo.py` | 回波阶段的 `__PROGRESS__` / `__SUMMARY__` 生产者 |
| `inversion/scripts/estimate_period.py` | 反演阶段的 `__PROGRESS__` / `__WARNING__` / `__SUMMARY__` 生产者 |
| `observation/solve_observation_info.py` | 观测阶段的 `__PROGRESS__` / `__WARNING__` 生产者 |

## 1. 背景

4.1 的日志区把子进程输出逐行追加到 `QTextEdit`，但对每行先做 `html.escape` 再按「有无严重程度颜色」分两路插入：

- 带颜色的行把转义结果包在 `<span>` 里，`QTextEdit.append()` 判定其为富文本并按 HTML 解析，实体被还原；
- 不带颜色的行直接追加**转义后的字符串**，而 `append()` 只在参数「看起来像富文本」时才按 HTML 解析，于是按字面插入，日志中出现 `&quot;` 这类实体。

回波与反演阶段结束时会打印整段结果 JSON，正好落在第二条路径上，因此用户在日志里看到的是 `{&quot;runtime_s&quot;: …}`。同一处逻辑还带来若干次生问题：空行被填入不换行空格、无法解析的协议行被原样显示、用户主动中止被记成失败、进程启动失败后界面停在「执行中」、阶段完成后不报告产物位置。4.2 逐一处理，并把「结果摘要」提升为一等协议，避免大段 JSON 直接进入日志。

## 2. 渲染层不变量

`_append_log(text, level=None)` 是写入日志区的唯一入口，必须满足：

1. **逐行处理**：入参按 `\n` 拆分为多个段落，空行也是一个段落。
2. **转义一次**：行文本经 `html.escape` 后**始终**包在 `<span>` 中插入，不再依赖 `QTextEdit.append()` 的富文本探测。
3. **保留缩进**：包裹用的 `span` 带 `white-space:pre-wrap`，使结果摘要与 JSON 的缩进可见；因此**空行不得插入 `&nbsp;`**，否则复制日志时会带出不可见字符。
4. **严重程度只表达一次**：级别由行首徽标（成功 / 警告 / 错误）表达，消息正文不再重复「警告」「错误」字样。
5. **长度有界**：日志文档的 `maximumBlockCount` 设为 5000 块。批量 campaign 的逐 Run 警告可达上千条，超过上限时从最早的行开始丢弃；完整信息仍保留在各阶段的日志与产物文件中。

级别判定规则：显式传入 `level` 时以传入值为准；否则按内容猜测——含「警告」「warning」「中止」判为警告，含「失败」「错误」「error」判为错误，含「 完成。」「已保存：」「已载入配置：」「已恢复上次会话：」「校验通过」「预览已就绪」判为成功，其余保持中性。

## 3. 机器协议

子进程通过标准输出发送四类控制行，格式为 `前缀 + 单行 JSON`，JSON 一律 `ensure_ascii=True`（GUI 侧解码，因此中文照常显示）。

| 前缀 | 载荷 | 消费者行为 |
|---|---|---|
| `__PROGRESS__ ` | `{"stage", "percent", "message"}` | 更新进度条数值与格式文本，不写日志 |
| `__WARNING__ ` | `{"stage", "message"}` | 以警告级别写入一行：`[时间] 阶段名：消息` |
| `__ERROR__ ` | `{"stage", "message"}` | 以错误级别写入一行，格式同上 |
| `__SUMMARY__ ` | `{"stage", "title", "items": [[标签, 值], …]}` | 先写标题行，再逐个写缩进两格的「标签：值」 |

解析规则：

1. **控制行绝不原样进入日志区**。任何以四个前缀之一开头的行都必须被消费；载荷无法解析为 JSON 对象时，退化为显示「去掉前缀后的剩余文本」（进度行则静默丢弃载荷），前缀本身不得出现在日志里。
2. `percent` 无法转为整数时保持进度条当前值，不抛异常。
3. `stage` 缺失时使用当前执行阶段；阶段名按 `STAGE_LABELS` 去掉序号前缀后显示（如 `observation` → `观测解算`）。
4. 其余普通行按内容改写后写入：`Wrote <路径>` → `已写入：<路径>`（若该路径正是本阶段主产物则跳过，因为阶段完成行会报告）、`samples=<N>` → `样本数：<N>`、`start_utc=<T>` → `观测起点：<T>`。

日志形态示意（`…` 表示省略）：

```
成功 [15:47:11] 已载入配置：…\configs\chirp_mesh_target_test.json
[15:47:12] 启动 2. 回波仿真
[15:47:12] 命令：…python.exe simulate_echo.py --config … --output …
成功 [16:01:36] 2. 回波仿真 完成。
成功 [16:01:36] 回波数据：…\runs\chirp_mesh_target_test\echo\echo.npz
成功 [16:01:36] 回波摘要：…\runs\chirp_mesh_target_test\echo\summary.json
[16:01:36] 回波仿真结果
    脉冲数：60000
    快时间样点数：153
    有效样点数：9179950
    物理回波重叠：无
    信噪比：无噪声
```

## 4. 运行状态收尾

| 情形 | 判定 | 日志与界面 |
|---|---|---|
| 正常结束且未被中止 | `exit_code == 0` 且未请求中止 | 阶段状态「完成」，进度条置满；依次报告该阶段每个产物的路径（成功级别）；回波阶段随后尝试重建回波预览 |
| 用户点击「中止」 | `_stop_pipeline` 先置中止标志再 `kill()` | 阶段状态「已中止」，进度条格式「已中止」，日志一条警告级「已中止：<阶段>」，**不续跑后续阶段、不弹错误对话框**；`kill` 引发的 `errorOccurred` 被中止标志忽略 |
| 子进程返回非零 | 未请求中止 | 阶段状态「失败」，进度条显示退出码，日志一条错误级记录，并弹出「运行失败」对话框；清空待执行阶段 |
| 子进程无法启动 | `QProcess` 报 `FailedToStart` | 该情形下 `QProcess` **不会**发 `finished`，因此在其错误回调中收尾：清空阶段与进程引用、恢复按钮、阶段状态「失败」、日志与对话框报告 `errorString()` |

按钮状态由 `_reset_run_buttons()` 统一恢复（运行/运行全部可用、中止不可用），避免任何一条失败路径把界面留在「执行中」。

## 5. 产物定位与阶段复用

每个阶段的子进程命令都以 `runs/<实验名>/…` 为约定路径，因此单个阶段可以复用上游已有的产物（例如已有 `echo.npz` 时只跑反演，无需重跑观测与回波）。

| 阶段 | 上游产物 | 缺失时的提示 |
|---|---|---|
| 回波仿真 | `runs/<实验名>/observation_info.npz` | 提示先运行「1. 观测解算」，或把实验名/运行目录指向已包含该文件的目录 |
| 周期反演 | `runs/<实验名>/echo/echo.npz` | 提示先运行「2. 回波仿真」，或把实验名/运行目录指向已生成该回波文件的目录（文件存在且阶段指纹一致时才自动复用） |

规则：

1. 启动阶段前检查上游产物是否存在。缺失时**不启动子进程**，清空待执行阶段、恢复按钮、写一条错误级日志并弹对话框；不再让用户看到子进程的 `FileNotFoundError` 回溯。
2. 上游产物并非本次运行生成时，写一条中性日志 `复用已有<产物>：<路径>`；本次刚生成时不写，避免冗余。
3. 复用旧产物时，比较该阶段的有效依赖指纹（观测：规范化 observation；回波：规范化 echo + `observation_info.npz` 哈希），而不是整份流水线 JSON。不一致则**阻断**并要求重跑上游阶段；缺少可核对指纹时弹出确认框，CLI 则需要 `--allow-legacy-reuse`。
4. 阶段完成时报告产物路径（第 4 节）。观测阶段子进程的 `Wrote` 行与完成行指向同一文件，重复的一次被抑制。退出码为 0 但主产物缺失时记为失败，不写成功 `stage_manifest.json`。

需要说明的边界：每次**启动某一阶段**时只重写该阶段的 `configs/<stage>.generated.json`，供子进程读取；来源记录在 `stage_manifest.json`，只在阶段成功且主产物存在后更新对应阶段条目。generated 不是复用证据。因此「只跑回波」不会改写 observation 的来源记录。若需要保留历史回波结果，请使用不同实验名。

## 6. 结果摘要协议

大段结果 JSON 直接进日志既不可读，也会把关键数字淹没。4.2 改为由生产者给出紧凑摘要：

- 生产者：回波阶段 `simulate_echo.py` 的 `report_summary("回波仿真结果", items)`、反演阶段 `estimate_period.py` 的 `report_summary("周期反演结果", items)`。
- 载荷：`{"stage", "title", "items"}`，其中 `items` 是 `[标签, 值]` 字符串对的列表，值是生产者已格式化好的可读文本（含单位、百分比、`—` 表示缺项）。
- 完整结果仍然写入 `echo/summary.json`、`inversion/summary.json` 与 `inversion/best_summary.json`；日志只承担「一眼看清结论」的职责。
- 摘要字段：回波侧为脉冲数与快时间样点数、有效样点数、波形与采样参数、面元数、计算设备、规划与实际路径偏移、物理回波重叠、信噪比、真值自转周期、运行时长；反演侧为推荐特征与推荐周期、真值周期、相对误差、显著性、假警报概率与校准方式、共识特征支撑与相对离散度、周期时间轴、半周期/二倍周期别称。

## 7. 未采纳与留待后续

- **未提供「选择任意回波文件」的入口**：复用只认 `runs/<实验名>/echo/echo.npz` 这一约定路径；跨目录复用需要把实验名或运行目录指过去。若需要任意路径复现实验，应作为一个显式的配置字段而非 GUI 临时状态。
- **未阻止覆盖 run 目录的配置快照**：见第 5 节末尾。当前只提示不一致。
- **逐 Run 警告仍未聚合**：观测解算的保存行重叠警告按 Run 逐条给出（见 `docs/4.2/vs_4.1/plans/ADC_PLANNING_REFACTOR_PLAN.md` §8 的警告策略）。日志长度上限只保证界面不被拖慢，不解决刷屏本身。

## 8. 回归测试

`tests/test_gui_schema_v4.py` 中以离屏方式锁定上述行为，主要用例：

| 用例 | 锁定的不变量 |
|---|---|
| `test_log_renders_json_block_without_html_entities` | 日志中不出现 `&quot;`/`<span`，JSON 缩进保留 |
| `test_malformed_protocol_lines_never_reach_the_log_raw` | 坏载荷不外泄控制前缀；坏进度行不改动进度条 |
| `test_warning_line_carries_stage_without_duplicate_severity_word` | 警告行不重复严重程度词 |
| `test_blank_log_lines_insert_no_non_breaking_space` | 空行不含 `\u00a0` |
| `test_summary_protocol_renders_readable_lines` | `__SUMMARY__` 渲染为「标签：值」行，坏载荷不外泄 |
| `test_log_block_count_is_capped` | 日志块数上限生效且默认值为 5000 |
| `test_user_abort_is_reported_as_abort_not_failure` | 主动中止记为「已中止」，无错误对话框，按钮恢复 |
| `test_failed_to_start_clears_running_state` | 启动失败后进程引用清空、按钮恢复、阶段记为「失败」 |
| `test_completed_stage_reports_artifact_paths` | 阶段完成报告产物路径 |
| `test_primary_artifact_write_is_not_logged_twice` | 主产物的 `Wrote` 行不重复显示 |
| `test_inversion_stage_reuses_existing_echo_and_reports_missing_artifact` | 复用提示、缺失预检、进程通道合并模式 |
| `test_reusing_upstream_warns_when_run_config_differs` | 参数不一致时的复用警告，一致时不提示 |
