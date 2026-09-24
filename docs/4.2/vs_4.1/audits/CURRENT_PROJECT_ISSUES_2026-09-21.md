# 4.2 当前项目潜在问题总审计（2026-09-21）

> 审计对象：2026-09-21 当前工作区，而不是任一已提交版本。根仓库及三个子模块均存在大量未提交修改，因此本文中的行号、测试结果和 Git 可交付性判断只对当前工作区成立。
>
> 审计目标：复核 `changes/DATE_LOG_2026-09-18.md`、`changes/DATE_LOG_2026-09-19.md` 和 `plans/REVIEW_2026-09-21_OPEN_ISSUES.md`，并补充后者没有覆盖的功能、科学正确性、数据契约、测试和交付问题。本文只做诊断，不修改业务代码。

## 1. 结论

当前项目尚不适合宣称“4.2 已完成”或把反演结果用于科学结论。观测计划、全局 ADC 回波生成、CW/chirp 文件契约和 GUI 的大量修复已经真实落地，四组现有测试也全部通过；但这套回归网没有证明“已知真值的旋转目标能够被正确恢复”，而当前反演共识算法、重叠行计权和输入校验仍有已复现缺陷。更直接的交付阻断是：流水线正式调用的 `inversion/scripts/estimate_period.py` 被 `inversion/.gitignore` 忽略且未被 Git 跟踪，按当前索引提交、归档或重新克隆后会缺少反演入口。

本轮共整理出 5 项阻断/高优先级问题、9 项中优先级问题，以及一组文档、测试与卫生问题。`REVIEW_2026-09-21_OPEN_ISSUES.md` 的 D1–D5、T1–T2、L1–L3 基本都仍成立，但它只覆盖最近一次接收窗复核，没有覆盖早期审计中尚未解决的反演科学性、配置契约和交付问题。

## 2. 审计范围与基线

### 2.1 阅读范围

本轮检查了根流水线、`rotation_gui/`、`observation/src/`、`echo/src/`、`inversion/src/`、正式脚本、现有测试、三份用户指定文档、4.2 的通用文档、既有审计报告、配置夹具及 Git 忽略/跟踪状态。仓库中约有 147 个主要文本与代码文件；`runs/`、`outputs/`、`tmp/` 中的大型生成物只按需要抽查，没有把第三方临时代码当作项目源代码审计。

### 2.2 当前测试结果

| 范围 | 命令 | 结果 |
|---|---|---|
| 根契约、物理与 GUI | `conda run -n pytorch python -m pytest -q` | 75 passed |
| observation | `conda run -n pytorch python -m pytest observation/tests -q` | 58 passed，1 条 NumPy 二进制兼容警告 |
| echo | 在 `echo/` 中运行 `conda run -n pytorch python -m pytest tests -q` | 36 passed |
| inversion | `conda run -n pytorch python -m pytest inversion/tests -q` | 21 passed，3 skipped |
| 语法编译 | `conda run -n pytorch python -m compileall -q pipeline.py rotation_gui observation echo inversion` | 通过 |

根目录的 `pytest -q` 只收集根 `tests/`，不会自动覆盖三个子模块。显式在根目录执行 `pytest echo/tests` 会因 `src.*` 和 `scripts.*` 的工作目录依赖而在收集阶段失败；4.2 `PROJECT_OVERVIEW.md` 已如实记录 echo 必须切换工作目录，因此这是测试架构债务，不是新发现的文档错误。

## 3. 阻断与高优先级问题

### P0-1 正式反演入口被 Git 忽略，当前工作区不可完整交付

**证据**：`inversion/.gitignore:24` 忽略整个 `scripts/`；`git check-ignore -v scripts/estimate_period.py` 命中该规则；`git ls-files scripts` 没有输出；但根流水线在 `pipeline.py:459` 固定调用 `scripts/estimate_period.py`，4.2 项目总览和 inversion README 也把它列为正式入口。

**影响**：当前本机因为忽略目录仍存在而能运行，提交后新克隆、`git archive`、发布包或另一台机器会缺失反演脚本，完整流水线在第三阶段直接失败。脚本中的共识选择、结果文件、图形输出和 GUI 协议也都不会进入版本历史，后续修改无法审查。

**建议**：把正式 CLI 移出被忽略目录，或把 `.gitignore` 改成只忽略一次性脚本并显式纳管 `scripts/estimate_period.py`；随后用 `git ls-files`、子模块归档和干净克隆做三向验证。此项应在任何代码提交或发布前先解决。

### P0-2 跨特征共识仍可把弱伪峰判为最终周期

**位置**：`inversion/scripts/estimate_period.py:193-248`，特别是 `:245-247` 的排序键 `(-support, spread, period)`。

**现状**：算法先按支持特征数排序，再按簇内离散度排序，完全不使用候选峰分数。早期审计已经用真值 12.5 s 的网格回波复现：5 个高分特征在 12.5 s 附近一致，另一个 5.0 s 弱伪峰簇的分数只有约 0.0003–0.0316，却因离散度更小胜出。当前代码与该复现对应的排序逻辑未变。

**影响**：`best_summary.json` 可能把错误弱峰写成推荐周期，同时给出高特征支持和很小离散度，看起来比真实强峰更可信。多谐波路径的假警报概率又固定不可用，因此当前推荐值缺少独立置信校准。

**建议**：先定义候选证据量，再重写共识排序；至少把每个特征的归一化峰值质量、有效样本数和混叠关系纳入，不得只按“支持数 + 展宽”决胜。修复前先把旧审计的 12.5 s 失败案例固化为端到端回归测试。

### P0-3 保存行重叠仍被当作独立观测重复计权

**位置**：`inversion/src/inversion.py:448-493`、`inversion/src/radar_signal.py:326-384`、`inversion/scripts/estimate_period.py:118-124`。

**现状**：echo 正确地在每个 Run 的唯一全局 ADC 样点上生成一次信号和噪声，再映射到二维重叠行；但 inversion 仍按二维行形成距离像和 CPI，`effective_pulse_weight` 只取每行有效比例。`window_overlap` 和 `signal_echo_overlap` 只被写入结果质量标志，没有进入去重、协方差或权重计算。`radar_signal.py` 的“重叠 multiplicity”只处理滑动 CPI 之间的重复脉冲，不处理多个保存行共享同一全局 ADC 样点。

**影响**：同一信号与同一噪声可被多次计权，导致特征、周期峰和显著性随保存行宽/PRT 比例变化；早期审计的合成数据已出现 4 倍视图重叠把 3.0 s 估计推到 2.801 s、另一个特征推到 5.533 s 的结果。`window_overlap` 不是单纯的显示信息，而是反演统计模型尚未处理的相关性。

**建议**：在 observation/echo 契约中传递可重建全局样点身份的信息，或在 inversion 前先还原唯一 ADC 时间轴/构造去重权重；若必须保留二维行，应显式建立共享样点协方差。修复必须对 1×、2×、4× 保存行重叠做同真值不变性测试。

### P0-4 当前没有一份能验证“从旋转回波恢复真值”的正式夹具

**证据**：`configs/chirp_mesh_target_test.json:76` 的真值周期为 7200 s，而 `:100-101` 的搜索区间是 100–1000 s，真值结构上不可能被找到；`chirp_point_target_test.json` 使用静止点目标，不提供可供周期恢复的旋转形状信息。`inversion/tests/test_chirp_contracts.py` 主要守接口和近 DC 行为，没有断言端到端恢复真值。

**影响**：所有测试全绿也无法发现 P0-2、P0-3 这类“程序正常结束但科学答案错误”的问题。现有 `runs/chirp_mesh_target_test/inversion/best_summary.json` 不能作为正确性证据，因为配置本身排除了真值。

**建议**：新增小规模、可在 CPU 上稳定运行的旋转非对称目标夹具，真值位于搜索区间内部，并同时守住主周期、P/2 对称混叠、多个 Run、保存行重叠和噪声重复。快速烟雾测试与论文级复现必须分开命名和记录。

### P1-1 “规范配置”校验只检查键名，不检查大量必填字段与数值域

**位置**：`pipeline.py:142-272`、`observation/src/config_normalize.py:51-81`、`echo/src/config_normalize.py:38-91`、`inversion/src/dataset.py:91-134`。

**复现**：本轮探针同时删除 `observation.transmitter`、`echo.compute` 和 `inversion.period_min_s` 后，`pipeline.prepared_configs(...)` 仍返回成功。自动选时缺少 `run_duration_s` 则在 `campaign_planning.py:209` 抛原生 `KeyError`；`run_count=1.9` 在 `:210` 被 `int()` 静默截成 1；负周期搜索范围被 `normalize_inversion_policy` 接受，直到 SciPy 内部抛 `ZeroDivisionError`。

**影响**：GUI 可以先显示“配置校验通过”，随后子进程才以 `KeyError`、`ZeroDivisionError` 或底层库错误失败；CLI/手写 JSON 更容易进入这一状态。布尔、分数计数、NaN/Inf 和交叉字段关系也没有在统一边界收紧。

**建议**：给三个阶段分别建立真正的完整 schema 校验，明确 required、类型、有限性、整数性、范围和跨字段条件；`prepared_configs` 应完成当前待执行阶段所需的全部验证。运行期函数仍保留防御性检查，但不应成为普通配置错误的第一发现点。

## 4. 中优先级功能与契约问题

### P1-2 自动选时仍静默丢弃手写 `runs`

`observation/src/config_normalize.py:230-236` 在非 manual 模式下直接 `schedule.pop("runs", None)`。本轮实测 `selection=equal_visible_time` 与一条 99 s 手写 Run 并存时，规范化后 `runs` 无声消失。通用文档解释了这一行为，但严格 schema 不应接受自相矛盾的输入后静默改写；应明确拒绝并告诉用户二选一。

### P1-3 自动模式必填字段和计数整数性仍未正确校验

`campaign_planning.py:209-210` 直接下标并转换 `run_duration_s`/`run_count`。缺字段是 `KeyError`，字符串或小数产生底层转换错误/截断，`True` 也会被当作 1。此项对应早期 O9 和 N3，当前仍未修复；应在配置边界给出字段全路径和合法域。

### P1-4 反演搜索域与基线退化没有守卫，错误又会被静默吞掉

`normalize_inversion_policy` 只把 `period_min_s`、`period_max_s`、`period_grid_size` 列为允许键，不检查 `0 < min < max`、网格整数和最小点数；`multi_harmonic_lomb_scargle` 在 `baseline_sse=0` 时于 `inversion.py:160` 除零。本轮对“每个 Run 内恒定”的两组特征直接复现 `ZeroDivisionError: float division by zero`。chirp 路径又在 `inversion.py:500-512` 对每个特征 `except ValueError: continue`，导致参数错误、数值退化和真实常量特征都可能只表现为特征莫名消失或最终统一报“均为常量”。

**建议**：在策略层验证周期范围、网格、谐波数、CPI 参数；在算法层用相对尺度判断 `baseline_sse` 是否可分辨；只捕获带明确类型的“特征不可用”异常，并把每个被丢弃特征的原因写进结果与 GUI 日志。

### P1-5 复用旧产物时只警告不阻断，并会覆盖原始来源记录

**位置**：GUI `rotation_gui/window/main.py:575-591, 621-639`；CLI `pipeline.py:90-91, 418-422`。

GUI 在发现当前配置与旧 run 的 `experiment.json` 不同时只写一条警告，随后仍在 `main.py:635-639` 用当前配置覆盖 `experiment.json` 和 manifest；旧 observation/echo 产物本身没有同步重算。CLI 的 `--skip-observation`/`--skip-echo` 连警告也没有，并在复用前先重写同样的配置记录。

**影响**：运行目录最终可能包含“旧上游二进制产物 + 新配置/新哈希”，原始生产配置被覆盖，事后无法仅凭目录判断结果来源。这不仅是提示不足，而是 provenance 被改写。

**建议**：每个阶段产物写入自身的输入配置哈希、上游文件哈希、代码版本和契约版本；复用时逐项比对，不一致默认阻断，用户显式选择强制复用时也必须保留旧来源记录并另写派生 manifest，不得覆盖原始实验配置。

### P1-6 `model_path` 的相对路径基准仍依赖子进程工作目录

`pipeline.prepared_configs` 只把 observation/output 路径改成运行目录绝对路径，却原样保留 `echo.model_path`；本轮实测准备后的值仍是 `models/ellipsoid.obj`。echo 子进程因 cwd 为 `echo/` 才能找到仓库自带模型，根目录直觉写法 `echo/models/ellipsoid.obj` 或从其他入口直接调用会解析到不同位置。此项对应早期 B4，仍未解决。

**建议**：确定唯一语义，优先按配置文件所在目录或仓库根目录解析并在生成配置中固化绝对路径，同时把最终解析路径写入 metadata。独立 echo CLI 与 pipeline/GUI 应共享同一个解析函数。

### P1-7 observation 与 echo 的快时间行宽没有跨阶段一致性守卫

此项对应 `REVIEW_2026-09-21_OPEN_ISSUES.md` 的 T2。本轮用 `runs/chirp_point_target_test/observation_info.npz`（252 列）与 `runs/chirp_test/echo/echo.npz`（251 列）复现：两个加载器都独立成功，没有任何版本、来源哈希或行宽一致性错误。当前 inversion 只知道 echo 自己的形状，GUI 预览也不会证明 echo 与该 run 的 observation 属于同一次计划。

**建议**：echo metadata 至少记录 observation 文件哈希、`fast_sample_count`、采样率、行起点摘要和计划版本；inversion/GUI 在同一 run 同时存在两个产物时校验这些字段。该问题与 P1-5 应合并设计，而不是再加一个孤立的列数断言。

### P1-8 无噪声配置下全零回波可被静默写出

`echo/src/echo.py:609-613` 和 CW 路径 `:1218-1226` 只在 `snr_db is not None` 时检查信号功率是否为零。`snr_db=null` 时，即使没有任何面元被照亮、候选窗完全错位或幅度为零，也可以生成全零 `echo.npz`，错误会延迟到 inversion 的“特征恒定”阶段，丢失真正原因。

**建议**：零信号检查应独立于是否加噪；如果确实允许生成全零诊断数据，需要单独显式开关，并在 metadata/summary 中标明不可反演。

### P1-9 CPI 秒数转脉冲数仍有浮点整数边界偏差

`inversion/src/inversion.py:434-447` 直接用 `ceil(duration * prf_hz)`。例如数学上 `0.28×25=7`，二进制浮点可能得到 `7.000000000000001` 并取成 8；默认 hop 同样受影响。应采用与发射脉冲计数一致的、带明确容差的整数网格换算，并用整数点、整数点两侧和大规模值做边界测试。

## 5. 9 月 21 日开放问题文档逐条核对

| 编号 | 当前状态 | 本轮判断 |
|---|---|---|
| D1 | 仍存在 | `OBSERVATION_TIME_SELECTION.md:172` 仍称行宽变化后 `window_overlap` 判定“不受影响”；输入行宽已变，结果当然可能翻转。 |
| D2 | 仍存在 | `OBSERVATION_RECEPTION_WINDOW.md:90-94` 仍称某些网格可有 $\delta=0$；按文档自己的整数推导，$S_i$ 恒定时应为 $\delta\in\{1,2\}$。 |
| D3 | 仍存在 | 同文件 `:116` 又写 $\delta\in\{0,1,2\}$，与正确推导及同文件前文冲突。 |
| D4 | 仍存在 | 同文件 `:31` 的符号表仍写无 `+0.5` 的旧 `n_after` 公式。 |
| D5 | 仍存在 | `KNOWN_DEFECTS.md:145,157` 仍写 10 个行轴字段/少 10 个键，实际 `_ROW_AXIS_FIELDS` 为 12 个。 |
| T1 | 仍存在 | 网格守护测试和源码自 9 月 21 日复核后未变；现有 144 点矩阵对约 0.013–0.063 个采样的补偿削弱仍无区分力。应增加密扫边界或解析下界守卫。 |
| T2 | 已再次复现 | 252 列 observation 与 251 列 echo 可分别加载成功，见 P1-7。 |
| L1 | 仍有口径问题 | `DATE_LOG_2026-09-19.md:177` 同时声称删除并仍保留两个 `cli_smoke_*`；当前目录确实仍存在这两个目录及多组 `probe_*`。 |
| L2 | 仍存在 | 没有 `DATE_LOG_2026-09-21.md`；9 月 21 日复核被记入 9 月 19 日文件，日期口径容易误导。 |
| L3 | 仍存在 | `observation/tmp/` 仍有 7 个历史条目；`adc_window_duration_s` 仍未进入 4.2 通用字段文档。 |

## 6. 与早期审计问题的当前对照

| 早期编号 | 当前状态 | 说明 |
|---|---|---|
| B1 坏示例配置 | 已处理 | 原 `campaign_v4_example.json` 已删除，GUI 无会话时改用开发夹具；但尚无正式科学自检夹具，见 P0-4。 |
| B2 CW 文件契约 | 已修复 | CW 不再被迫写 12 个行轴占位，chirp 缺键会被拒；现有契约测试通过。 |
| B4 `model_path` 基准 | 未修复 | 见 P1-6。 |
| O1/O2 自动选时两套长度 | 主问题已修 | 当前上限与布局都按 `occupied_duration_s`；`select_run_start_offsets` 形参仍叫 `run_duration_s`，语义易误读，属维护债务。 |
| O3 最后一列丢失 | 已修复 | `q_off=max(starts)+fast_count`，当前行全部落在半开 ADC 窗内。 |
| O4 selection 无白名单 | 已修复 | `manual/equal_visible_time/random_visible_time` 已有白名单。 |
| O5 自动模式静默忽略 runs | 未修复 | 见 P1-2。 |
| O6 `duration_s` 语义混淆 | 已缓解 | 新增 `receive_centroid_span_s` 与 `adc_window_duration_s`，但字段说明仍不完整。 |
| O7 不可达 location/refplane 校验 | 已按“固定地心/earth”方案处理 | 不可达分支已删除，未知字段在 schema 层拒绝。 |
| O8 可见性重复末点 | 已修复 | 当前使用半开 `arange` 后仅在需要时追加任务终点。 |
| O9 自动必填字段 KeyError | 未修复 | 见 P1-3。 |
| O10 NaN 保护时间逃逸 | 已修复 | `plan_reception` 统一检查有限性。 |
| O11 `pulse_count` 死特性 | 已删除 | 当前调度只按 Run 时长、PRF 和脉宽计算脉冲数。 |
| O12 路径界等小项 | 部分处理 | 面元差分路径上界检查已抽成 `check_path_limit`；但无噪声全零回波仍可能延迟失败，见 P1-8。 |
| N1 单 Run 可行性公式 | 已实质修复 | 当前先计算完整脉冲数与脉冲列跨度，再与安全脉冲容量比较；旧复核中“1.61 s 对应 32 脉冲”的公式已不再是当前实现。 |
| S1–S7 | 大多仍存在 | S1、S2、S3、S4、S5、S6、S7 分别对应 P0-2、P1-4、P1-1/P1-4、P0-3、P1-4、§7.1、P1-9。 |

## 7. 低优先级但应记录的问题

### 7.1 `period_observables.npz` 的 `uncertainty` 不是统计不确定度

`inversion/scripts/estimate_period.py:125-129` 用相邻帧差的 MAD/√2 生成整列常数，并把零值抬到机器 epsilon。它混合了真实信号变化与噪声，没有估计测量方差、拟合区间或周期不确定度，且当前没有消费者。字段名会误导下游；应改成明确的 `local_difference_scale`，或建立有统计含义的噪声/重采样估计后再称 uncertainty。

### 7.2 动态字段错误仍缺统一机器可读分类

GUI 已正确使用 `PROGRESS_PREFIX`、`WARNING_PREFIX`、`ERROR_PREFIX`，早期“常量未使用”的问题已修复；但各阶段仍主要靠中文异常字符串和少量协议前缀区分错误类型。配置错误、数据契约错误、数值退化、外部网络失败和用户中止没有稳定错误码，导致 GUI 只能展示文本，自动化也难以决定是否重试。

### 7.3 单一全仓测试入口缺失

目前必须记住四条不同命令，且 echo 依赖 cwd。文档已经写清楚，但 CI/维护者仍容易只跑根 75 项后误以为全仓通过。建议提供一个根级测试脚本或 CI workflow，分别以正确工作目录执行四组测试并汇总退出码。

### 7.4 临时目录和历史证据污染仍较重

`echo/tmp/` 当前包含两个 `cli_smoke_*`、多个 `probe_*`、`old`、`perf` 和 `adversarial_review_c.py`；`observation/tmp/` 有 7 个历史条目。它们在 Git 忽略范围内，不直接影响运行，但会妨碍人工审计、占用空间并让“哪个证据仍有效”不清楚。清理前应先列目标并保留文档可重建命令。

### 7.5 若干零引用/孤岛代码仍待产品决定

早期死代码审计中的 `pipeline.require_sections`、`inversion/src/radar_signal.py::matched_filter_group_delay_s` 等仍缺生产调用；`inversion/src/ellipsoid.py`、`inversion/src/ephemeris.py`、`inversion/src/pointing.py` 仍主要构成旧工具链/测试孤岛。它们不是当前功能故障，删除与否需要先确认兼容目标；不应把“无当前调用”直接等同于“可安全删除”。

## 8. 已核实正确或明显改善的部分

- `plan_reception` 现在基于每个 Run 的唯一全局 ADC 整数索引规划，末列纳入半开窗，前后保护和目标路径展宽有有限性检查，物理回波重叠与保存行重叠分开记录。
- echo 的 chirp 生成器在唯一全局 ADC 样点上叠加所有相关脉冲，再映射回二维行；共享信号/噪声的生成语义与项目文档一致，问题位于下游统计计权而不是回波逐行重复生成。
- CW/chirp `echo.npz` 行轴契约已按布局分流，缺键与形状回归测试有效；本轮四组测试均通过。
- 自动 selection 白名单、自动缺 `end_utc`、可见性网格重复末点、NaN 保护时间、不可达 `pulse_count` 和固定星历中心等早期问题已经处理。
- GUI 的日志协议前缀、动态控件焦点/滚动、会话恢复和阶段化采样率校验都有相应测试；本轮未发现能推翻这些修复的新证据。

## 9. 建议修复顺序

1. 先修 P0-1，把正式反演脚本纳入版本控制，并建立干净克隆/归档烟雾测试；否则后续反演修复仍可能不进入交付物。
2. 同一批修 P1-1、P1-2、P1-3、P1-4：建立完整 schema 和错误分类，避免继续用运行期 `KeyError`/底层异常作为配置校验。
3. 为 P0-4 建立最小真值夹具，再用它修 P0-2 和 P0-3；没有可区分错误答案的端到端测试，不应直接改共识或计权后宣布正确。
4. 合并设计 P1-5、P1-6、P1-7：统一路径解析、阶段产物哈希和 provenance，不再靠目录名或警告维持一致性。
5. 修 P1-8、P1-9 和特征丢弃日志，补数值边界测试。
6. 最后处理 D1–D5、T1、L1–L3、测试入口和临时目录，使文档、证据与代码重新一致。

## 10. 可复现证据

本轮行为探针位于被 Git 忽略的 `tmp/current_audit_probe.py`，它不属于交付代码，只用于重建以下结果：

```text
automatic_runs_present_after_normalize=False
missing_run_duration_exception="KeyError: 'run_duration_s'"
fractional_run_count_resolved_runs=1
negative_period_policy_accepted={...}
negative_period_exception='ZeroDivisionError: ()'
group_constant_exception='ZeroDivisionError: float division by zero'
mesh_truth_in_search_interval=False
prepared_model_path='models/ellipsoid.obj'
prepared_missing_required_fields='accepted'
```

重跑命令：

```powershell
conda run -n pytorch python tmp/current_audit_probe.py
```

跨阶段行宽失配的最小现有产物复现：

```powershell
conda run -n pytorch python -c "from echo.src.geometry import load_observation_info; from inversion.src.dataset import load_echo; o=load_observation_info('runs/chirp_point_target_test/observation_info.npz'); e=load_echo('runs/chirp_test/echo/echo.npz'); print(o.row_valid.shape[1], e.iq.shape[1])"
```

当前输出为 `252 251`，两个加载器均未报错。

## 11. 审计边界

本轮没有联网调用 Horizons，没有在 CUDA 上重跑大规模 mesh 性能实验，也没有把当前未提交工作区复制到全新机器做真实发布安装；因此外部星历服务、GPU OOM 自适应和安装依赖还只能评价代码路径，不能宣称端到端验证通过。反演脚本未跟踪、无真值夹具、配置校验和阶段 provenance 等结论不依赖这些环境，证据充分。
