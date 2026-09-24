# 自转周期测量流水线：代码审计报告

审计范围：仓库根目录 `pipeline.py`、`observation/`、`echo/`、`inversion/`、`rotation_gui/`、`tests/`、`configs/`、`docs/`。
审计方式：全量阅读源码 + 在 `pytorch` 环境运行真实数值实验 + 运行现有测试套件。
所有实验脚本与输出写在 `runs/audit_probe/`（已被 `.gitignore` 忽略），**未修改任何受版本控制的文件**。

审计时的基线状态：

| 测试集 | 命令（含正确 cwd） | 结果 |
|---|---|---|
| 根契约/物理 | `pytest tests/test_physics_regressions_v4.py tests/test_schema_v4_contract.py -q` | 27 passed |
| 根 GUI | `pytest tests/test_gui_schema_v4.py -q` | **7 failed**, 50 passed |
| observation | `cd observation; pytest tests -q` | 37 passed |
| echo | `cd echo; pytest tests -q` | 13 passed, 4 failed（沙箱 tempfile 权限，非代码问题） |
| inversion | `cd inversion; PYTHONPATH=src pytest tests -q` | 17 passed, 3 skipped |

> 本报告不复述"已核实为正确"的部分，集中列出缺陷。凡标注"实测"的结论都有可复现证据。

---

# 第一部分 阻断级问题（按文档操作直接跑不通）

## B1. 自带示例配置 `configs/campaign_v4_example.json` 无法运行

**状态：已知，暂不处理（保留供后续重新设计）**

`observation.receiver_sampling.fast_sample_rate_hz = 5000`，而 `echo.waveform.bandwidth_hz = 100000`。流水线在 `pipeline.py:340-343` 直接拒绝：

```
ValueError: 复基带 chirp 要求 receiver_sampling.fast_sample_rate_hz 大于 bandwidth_hz
```

该文件由 CW 改成 chirp 时（见 `git diff configs/campaign_v4_example.json`）只加了 `bandwidth_hz`，没有同步提高采样率；同时保留了 `point_target` 散射模型和 `period_min_s/max_s = 100/1000`（无真值可用）。

**待办**：程序跑通后重新设计一份正确且典型的配置，并替换文档中所有引用该文件的位置：

- `README.md:19`（快速运行）、`README.md:44`、`README.md:130-131`、`README.md:142`
- `docs/PROJECT_OVERVIEW.md` §4 示例、§6 命令
- `inversion/README.md:108`（在完整链路中运行）
- `rotation_gui/storage.py:12` 的 `DEFAULT_CONFIG_PATH`
- 提示：`PROJECT_OVERVIEW.md` 还引用了 `configs/chirp_mesh_target_test.json`（未跟踪文件）

## B2. CW（连续波）链路在反演入口 100% 失败——**已经确认，需要修**

### 是不是"echo 的仿真结果无法提取周期"？——不是

echo 的仿真本身是成功的。失败发生在**读回阶段**：`inversion/scripts/estimate_period.py:49` 调用 `load_echo`，在 `inversion/src/dataset.py:169` 抛错。

我构造了一份最小 CW 配置（`runs/audit_probe/probe_cw.json`，SW 点目标、240 s、64 Hz、SNR 20 dB）跑完整流水线，observation 与 echo 都成功，inversion 立刻失败：

```
[inversion] ... estimate_period.py --echo ...\cwprobe\echo\echo.npz ...
File "inversion/src/dataset.py", line 271, in load_echo
File "inversion/src/dataset.py", line 169, in _validate_echo_dataset
ValueError: run_id 长度必须等于 iq 第 0 维
```

### 原因：CW 分支根本不写那些逐脉冲字段，但校验不区分波形

三层各自都没错，合起来就崩：

1. `echo/src/echo.py:784-791`（CW mesh 路径）与 `echo/src/point_target.py:113-152`（CW 点目标路径）构造 `EchoDataset` 时**不传** `run_id`、`track_id`、`row_start_sample`、`row_fast_time_offset_s`、`centroid_fractional_offset_s`、`rx_adc_start_elapsed_s`、`rx_adc_stop_elapsed_s`、`signal_echo_overlap`、`window_overlap`、`common_path_rate_m_s`，它们全部落到 `echo/src/dataset.py:61-72` 的空数组默认值 `np.array([], dtype=...)`。
2. `echo/src/dataset.py:75-102` 的 `save_echo` **无条件**把这些空数组写进 `echo.npz`。所以文件里这些键**存在，但长度为 0**。
3. `inversion/src/dataset.py:150-169` 的 `_validate_echo_dataset` 对这批字段统一要求形状 `(sample_count,)`，于是长度为 0 的数组必然抛错。

关键细节：`inversion/src/dataset.py:217-250` 里 `data["run_id"] if "run_id" in data else ...` 的兜底分支**永远不会触发**，因为键存在。这套兜底是为"旧文件缺键"设计的，对"键在但为空"无效。

### 是不是"缺少 CW / chirp 两套接口"？——不是，接口本来就是两套，缺的是数据填充

代码里 CW 与 chirp 的**处理路径是分开的**，且分流依据是数据形状而不是配置：

- `inversion/src/dataset.py:61-70` 的 `echo_layout()`：`iq.ndim == 2` → `"chirp"`，`iq.ndim == 1` → `"cw"`。
- `inversion/src/dataset.py:73-116` 的 `normalize_inversion_policy()`：CW 只接受 `stft_window_samples` / `stft_overlap_fraction` / `translation_coefficients_hz`，chirp 只接受 `harmonics` / `period_time_role` / `motion_compensation` / `cpi_duration_s` / `cpi_hop_duration_s`，混写即报错。
- `inversion/src/inversion.py:295-347` 是 CW 分支（STFT → 频谱特征 → Lomb–Scargle），`:350-518` 是 chirp 分支（匹配滤波 → 滑动 CPI → 距离–多普勒特征 → 多谐波回归）。

所以两套算法接口是齐的。**真正的问题是 echo 侧对 CW 输出"少填了字段"，而 inversion 侧的字段校验对两种波形一视同仁。** 换句话说：这是生产者与消费者之间的字段契约缺口，不是算法接口缺口。

### 影响

`.gitmodules`、`README.md:22`、`PROJECT_OVERVIEW.md` 都把 CW 列为受支持波形，但任何 CW 实验都拿不到周期结果。

### 修复方向（任选其一，建议第一种）

- **A. 让 CW 也填满行轴字段**：在 `echo/src/echo.py` 与 `echo/src/point_target.py` 的 CW 分支里，用 `np.zeros`/`np.full` 生成与样本数等长的字段（`run_id=0`、`track_id=0`、`row_start_sample=-1`、`row_fast_time_offset_s=nan` 等），与 `inversion/src/dataset.py:217-250` 的兜底默认值保持一致。
- **B. 让 `save_echo` 为空数组时省略键**：CW 分支未填充的字段不写盘，让 inversion 的 `if "x" in data` 兜底生效。
- **C. 让 `_validate_echo_dataset` 按布局放宽**：CW（一维 `iq`）只校验真正使用到的字段。

另外建议补一条 CW 全链路回归测试——当前 `inversion/tests/` 里没有任何真实 CW `echo.npz` 的端到端用例，这正是它长期没被发现的原因。

## B3. GUI 默认启动加载坏配置

**状态：不是"GUI 启动即崩溃"，已澄清**

`rotation_gui/storage.py:12` 的 `DEFAULT_CONFIG_PATH` 指向 B1 那个坏配置，`main.py:88-89` 在"无有效会话"时加载它。加载本身能过（`_load_config` → `canonical_pipeline_config` 不校验采样率/带宽关系），所以窗口能正常打开；只有点到"运行回波/运行完整 pipeline"才会撞上 B1 的报错。你日常运行时没报错，说明 `.gui_state/pipeline_gui_state.json` 里有有效会话（`main.py:76-89` 优先恢复会话）。

**待办**：与 B1 一起做——等新配置就绪后把 `storage.py:12` 指向它即可。

## B4. `model_path` 相对路径基准不一致——**已经确认，需要修**

### 你的理解基本正确，但根因比"两套配置"更具体

不是"echo 独立运行和 pipeline 模式下需要不同的配置"，而是**同一个 `model_path` 字符串在两种运行方式下被解析到不同的基准目录**，而且文档只写明了其中一种。

代码路径：

| 运行方式 | 子进程 cwd | 配置里的 `model_path` | 实际解析结果 |
|---|---|---|---|
| 独立运行 `echo/simulate_echo.py` | `echo/` | `models/ellipsoid.obj` | `echo/models/ellipsoid.obj` ✅ |
| `pipeline.py` / GUI | `echo/`（`pipeline.py:452`、`main.py:612`） | 由仓库根目录的三段式配置提供，**原样透传** | 同名文件被写成 `models/ellipsoid.obj`，但用户若按 echo 的约定再补 `echo/` 前缀，就变成 `echo/models/ellipsoid.obj`，在 cwd=`echo/` 下解析为 `echo/echo/models/...` ❌ |

我的实测：在根目录配置里写 `"model_path": "echo/models/ellipsoid.obj"`（按仓库根目录的直觉写），echo 阶段失败：

```
ValueError: string is not a file: `echo/models/ellipsoid.obj`
```

改成 `"models/ellipsoid.obj"`（按 echo 模块目录的约定写）才成功。

而 `docs/GUI_USER_MANUAL.md:222` 明确写"相对路径按 `echo/` 模块目录解析"，`echo/AGENTS.md` 也以 `echo/` 为基准。所以文档描述的是"独立运行"的语义，**而 pipeline/GUI 路径下用户实际面对的是"相对 `echo/` 目录"，但配置文件本身位于仓库根而看起来应该相对根**——这个基准没有任何地方对用户讲清楚，写错就是"文件不存在"。

对比：`observation_info_path` 和 `output_path` 在 `pipeline.py:388-397` 里被**主动改写成绝对路径**，唯独 `model_path` 没有。这就是不一致的来源。

### 同时存在的第二处不一致：`validate_echo_waveform`

`pipeline.py:381` 的 `prepared_configs(..., validate_echo_waveform=True)` 默认开启采样率/带宽校验，而 GUI 在运行观测阶段时传 `validate_echo_waveform=False`（`main.py:549`），pipeline 的 `main()` 则**始终为 True**（`pipeline.py:417`）。后果：

- GUI 里"只跑观测阶段"可以成功；
- 命令行 `python pipeline.py --skip-observation --skip-echo`（**只跑反演**）也会先经过 `prepared_configs` 并因 echo 采样率不符而失败，即使 echo 根本不会被执行。

### 修复方向

- **A（推荐）**：在 `pipeline.prepared_configs` 里把 `model_path` 也解析成绝对路径，基准取仓库根目录（与 `observation_info_path` 一致），并在文档里写明"pipeline/GUI 模式下 `model_path` 相对仓库根目录；独立运行 echo 时相对 `echo/`"。更好的做法是**统一为仓库根目录**并同步修改 `echo/configs/echo.json`。
- **B**：在 `echo/src/echo.py` 或 `simulate_echo.py` 里解析 `model_path`：若是相对路径，先按 cwd 试，失败再按 `Path(__file__).parents[1]`（echo 目录）试，并在成功时把实际路径记进 `metadata["model_path"]`。这样两种运行方式都能工作。
- **C**：把 `validate_echo_waveform` 的语义与阶段绑定下沉到 `pipeline.py`，让 CLI 的 `--skip-*` 与 GUI 行为一致。

---

# 第二部分 观测/规划层问题（当前优先处理）

## 术语对照：GUI 字段 ↔ 配置字段 ↔ 代码变量

先把你问的名词对齐。观测解算阶段左侧"发射计划"卡片（`parameter_form.py` `CARD_ORDER["observation"]` 中的 `"plan"`）里：

| GUI 显示 | 配置字段 | 物理意义 |
|---|---|---|
| 选时方式 | `schedule.selection` | `manual` = 按"Run 时刻表"手填；其余 = 程序自动在发射选时范围内挑 Run 起点 |
| Run 数量 | `schedule.run_count` | 自动模式下希望安排几次 Run |
| **单次 Run 时长** | `schedule.run_duration_s` | **一次 Run 的发射调度时长 $D$**。它限定"一列完整脉冲可以占据多长的时间区间"，不等于射频连续开启时间，也不包含回波传播/接收时间 |
| Run 时刻表 | `schedule.runs` | 手动模式的 `tx_start_utc` + `tx_duration_s` 列表 |
| 发射选时范围结束 | `schedule.end_utc` | 自动模式的搜索范围右端（左端是 `schedule.start_utc`） |
| 包含非可见时段 | `visibility.allow_unobservable_for_simulation` | 允许把整段范围当候选，仅供算法仿真 |

而 `occupied_duration_s` **不是配置字段，没有对应的输入框**。它是程序内部算出来的"调度预留长度 $H$"，即"从 Run 开始时刻起，必须独占多久才不会再撞上下一次 Run"。它的定义在 `observation/src/campaign_planning.py:156-169`：

$$H = D + \tau_{\text{path,max}} + T_{\text{switch}} + T_{\text{safety}} + T_{\text{post}} + \frac{D_{\text{extent}}}{c} + T_{\text{pulse}}$$

（`run_duration_s` + 最大双程传播时间 + 收发切换 + 安全余量 + 后置保护 + 目标路径展宽 + 脉冲宽度）

你只会在**观测计划预览的摘要文字**里看到它：`parameter_form.py:351` 把它显示成"每次调度占用 X s"，时间轴的**浅蓝色段**就是它（深蓝 = $D$ 的发射段，见 `parameter_form.py:368` 的图例）。文档对应 `docs/OBSERVATION_TIME_SELECTION.md` §3 的"调度预留长度"。

**"为什么会有这种矛盾"——一句话**：预览/上限用 $H$ 判断"还能塞几次 Run"，真正挑起点用的是 $D$。两个函数对"一次 Run 要占多久"给出了不同答案。

## O1. 自动选时用两套长度判定：上限按 $H$，布局按 $D$

**位置**：`observation/src/campaign_planning.py:156`、`:177-180`、`:193-196`；`observation/src/planning.py:346-401`

**机理**：

- `campaign_planning.py:156` 令 `occupied_duration_s = H`；
- `:177-180` 用 $H$ 算上限：`max_run_count = Σ floor(窗口长度 / H)`；
- `:193-196` 把 $H$ **当作 `run_duration_s` 形参**传给 `select_run_start_offsets`；
- 但 `planning.py:358-360` 内部做容量判定时用的是 `floor(窗口长度 / run_duration_s)`，也就是 $D$，不是 $H$。

所以 `select_run_start_offsets` 里"能放下几次 Run"的判据（除以 $D$）和调用方算给用户看的 `max_run_count`（除以 $H$）**是两个不同的数**。

**实测复现**（`run_duration_s=1.0`、单程 10 光秒、窗口 25 s、单站切换）：

```
max_run_count = 1         ← 预览摘要会显示"最多 1 次 Run"
select_run_start_offsets 收到的容量 = floor(25/1) = 25
请求 run_count = 2 → 先被接受，随后抛 ValueError: 可见区间无法容纳指定数量的互不重叠 run
```

也就是说：`run_count=2` 时预览会说"超出上限（最多 1 次）"，而**实际执行时走进 `select_run_start_offsets` 的是原始的 2，不是被压到 1 的 `selection_count`**（`campaign_planning.py:181-199` 里 `selection_count` 只在 `allow_infeasible_preview=True` 时有意义），于是报错信息（"可见区间无法容纳"）指向的原因与真实原因（按 $H$ 布局不够）不符。

**影响**：错误信息误导；$H$ 与窗口边界之间少一道显式校验；`max_run_count` 与内部容量可以互相矛盾。

**修复方向**：让 `select_run_start_offsets` 明确接受"每次 Run 需要的预留长度"（改名并只按它算容量），或者把 `run_duration_s` 与 `occupied_duration_s` 两个参数都传进去并明确：候选区间长度按 $H$、Run 起点间隔按 $H$、Run 内脉冲列按 $D$。并把 `selection_count` 的取小逻辑统一到两条路径上。

## O2. 自动选时的"等距取点"不做 $H$ 级重叠校验

**位置**：`observation/src/planning.py:376-400`

非随机分支在"每段可行起点区间首尾拼接"的累计长度上等距取点，**取点前不检查相邻起点是否至少相隔 $H$**，只在事后发现重叠时回退到离散槽位（`:397-400`）。同一可见窗内的末段会紧贴窗尾。

**实测**：`windows=[0,11] & [100,111]`、$D=10$ → `starts=[0, 101]`，第二个起点正好落在可行区间端点。

**影响**：与 O1 同源；单独看，这会让 Run 的调度预留区间贴边甚至越界。

## O3. 每个 Run 最后一个脉冲固定少一个采样点

**位置**：`observation/src/planning.py:200-202`、`:252-253`、`:268-269`

- 行宽 `fast_count = n_pre + n_after + 1`，其中 `n_after = ceil((post_guard + pulse_width + D_extent/c)·S·fs)`；
- 行尾索引恰为 `centroid_index + n_after`；
- 而 `q_off = ceil((desired_rx_off − rx_on)·fs − 1e-12)`，`desired_rx_off` 正是"最后一个回波 + 后置保护"，所以行尾索引与 `q_off` 落在**同一格点**；
- `row_valid = (index >= 0) & (index < q_off)` 把它判为无效。

**实测**（`configs/chirp_point_target_test.json`）：`row_valid.sum(axis=1) = [251×7, 250]`——8 个脉冲里最后一个少了 1 个点。`echo/src/echo.py:276-282` 用同样的半开 `< adc_stop`，所以 echo 侧也不采它。这不是"echo 丢点"，而是**规划本身就少给了一个采样周期**。

**为什么值得修**：两侧靠"都采用半开区间"这一巧合对齐；任何一侧改动（例如 echo 改用 `<=`）都会静默产生一个越界样点。而且 `observation/tests/test_planning_regressions.py:123` 的 `assert not plan.row_valid[0, -1]` 把这个实现细节固化成了"正确行为"，`:116` 的 `q_stop == approx(round(q_stop))` 是重言式（`q_off` 定义上就是整数）。

**影响**：每个 Run 后置保护少一个采样周期。物理影响很小，但契约上是"规划给出的有效窗比 ADC 窗少一点"。

## O4. `selection` 取值无白名单

**位置**：`observation/src/campaign_planning.py:149`（`selection != "manual"` 即进自动分支）

**实测**：`"garbage"`、`"unform_visible_time"`、`""` 全部被 `normalize_observation_config` 接受，并静默走自动等距选时。而 `rotation_gui/schema.py:56` 只提供 `manual` / `equal_visible_time` / `random_visible_time`，`planning.py:346-401` 也只区分 `"manual"` 与 `"random_visible_time"`。

**影响**：拼写错误不会被发现，用户以为在手动指定却被自动覆盖。

## O5. 手写的 `runs` 被静默忽略，且与自动参数互相矛盾

**位置**：`observation/src/campaign_planning.py:149-153`（`runs = manual_runs` 之后若非 manual 立刻被覆盖）

`configs/campaign_v4_example.json` 里同时写了 `selection = "equal_visible_time"`、一条 `runs`（`tx_duration_s: 30`）、`run_count: 3`、`run_duration_s: 0.4`。程序只认后三者，手写 `runs` 完全不参与。文档 `docs/OBSERVATION_TIME_SELECTION.md:104` 解释了这个行为，但**配置本身就不该允许这种自相矛盾的组合**。

**修复方向**：自动模式下若同时存在 `runs` 且非空，直接报错（或至少写警告），而不是静默忽略。

## O6. `duration_s` 与 Run 级 ADC 窗跨度不一致

**位置**：`observation/src/observation_info.py:296-300`

chirp 分支把 `metadata["duration_s"]` 定义成"脉冲质心接收事件的`首末跨度`"，而它被写进 npz 的 `duration_s` 键（`observation_info.py:108`），名字会被下游理解成"采集/接收时长"。

**实测**：`metadata["duration_s"] = 0.35 s`，而 `rx_adc_stop − rx_adc_start = 0.40 s`，短 12.5%。

**修复方向**：改为 ADC 窗跨度，或另加 `adc_window_duration_s` 并明确 `duration_s` 的语义。

## O7. `ephemeris.location` / `refplane` 的校验永远不可达

**位置**：`observation/src/observation_info.py:374-400`（校验）、`:151`、`:165`（metadata 文案）；`observation/src/config_normalize.py:38`、`:68`

`_validate_reference_frame_config` 读 `ephemeris.location` / `ephemeris.refplane`，但 `_NESTED_KEYS["ephemeris"] = {"query_step_s"}`，`_reject_unknown` 会先抛"未知配置字段：observation.ephemeris.refplane"。

**实测**：`{"refplane": "ecliptic"}` → `ValueError: 未知配置字段`；`{"location": "@0"}` 同理。真正生效的是 `observation/src/ephemeris.py:497-498` 硬编码的 `location="@399"`、`refplane="earth"`。

**影响**：那段"防止把非地心中心/黄道参考面的 Horizons 向量与 Astropy GCRS 测站混用"的保护只能走必过分支，等于不存在。`observation/tests/test_planning_regressions.py:126-146` 直接调私有函数、`test_observation_info.py` 用宽松 `assertRaises(ValueError)`，把这个断链掩盖了。

**修复方向**：要么把这几个键加进 `_NESTED_KEYS["ephemeris"]`（真正让校验可达），要么删掉校验与相关文档。二选一，不要留半截。

## O8. 可见性时间网格出现重复末点

**位置**：`observation/src/campaign_planning.py:101-103`

```python
elapsed = np.arange(0.0, campaign_duration_s, step_s)
if len(elapsed) == 0 or not np.isclose(elapsed[-1], campaign_duration_s):
    elapsed = np.r_[elapsed, campaign_duration_s]
```

当 $D$ 是 `step_s` 的整数倍时，`elapsed[-1] = D − step`，`isclose` 为假，于是追加 $D$，末尾变成 `D, D`。

**实测**：`step=60, D=100` → `elapsed = [0, 60, 100, 100]`。

**影响**：`observation/src/ephemeris.py` 的均匀网格判定因此返回 False，Horizons 查询从"range 查询"退化为"逐 epoch list"（联网性能和请求数显著变差），并把重复 epoch 送进查询。`observation/tests/test_visibility.py:49` 只断言 `[-1] == 100`，掩盖了重复点。

## O9. 自动模式的必填字段缺失时抛 `KeyError`

**位置**：`observation/src/campaign_planning.py:154-155`

```python
run_duration_s = float(schedule["run_duration_s"])
run_count = int(schedule["run_count"])
```

缺失时抛 `KeyError: 'run_duration_s'`，`run_count="two"` 抛 Python 原生 `ValueError`。这不是面向用户的配置错误信息。GUI 会自动补默认值（`parameter_form.py:1705-1706`），但独立 CLI / 手写 JSON 会踩到。

## O10. 数值字段只查 `< 0`，NaN 逃逸后报错难懂

**位置**：`observation/src/planning.py:182-187`

`pre_guard_s` / `post_guard_s` / `target.extent_path_m` 只用 `float()` 解析并检查 `< 0`。NaN 通过检查，随后在 `:200` 的 `int(np.ceil(nan))` 抛：

```
ValueError: cannot convert float NaN to integer
```

`campaign_planning.py:162-169` 的占用长度同样未做有限性校验。项目其它位置（如 `ephemeris.py` 的 `_finite_float`）已有统一做法，这里没有沿用。

## O11. `run["pulse_count"]` 是代码支持但配置不可达的死特性

**位置**：`observation/src/planning.py:129-138` 支持 `run["pulse_count"]`；`observation/src/config_normalize.py:40` 的 `_RUN_KEYS = {"run_id","track_id","coherence_id","tx_start_utc","tx_duration_s"}` 不含它。

任何配置携带 `pulse_count` 都会被判"未知配置字段"。另外该分支用 `int()`，浮点会被截断、`True` 会变成 1。

**修复方向**：要么加入 `_RUN_KEYS` 并做整数校验，要么删掉这段分支。

## O12. 其它规划层小缺口

- `observation/src/planning.py:272-277`：`signal_overlap[indices[:-1]] |= local_signal_overlap` 依赖"一维掩码 + 长度 1 数组"的 numpy 广播，恰好正确但语义隐晦，后续改动易出错。
- `observation/src/light_time.py` 的 `_retarded_time_many` 在 `max_delta` 为 NaN 时比较为 False，会静默返回 NaN（位置构造层已挡 NaN 坐标，暂未找到可达路径）。
- `echo/src/echo.py:585-599` 的 `target_extent_path_m` 校验写在 `if relative_path.numel():` 之内。某脉冲候选样点为空时内核在 `:543-549` 提前返回，**校验被完全跳过**，`max_actual_bistatic_path_offset_m` 报 0 而不是真值；`planned_target_extent_path_m = 0` 时 `path_offset_validation_performed` 为 False，也不做任何校验（`echo/scripts/make_simple_chirp_plan.py` 默认 `--target-extent-m 0`）。

---

# 第三部分 科学正确性问题（周期结果不可信，本轮暂缓）

> 这一部分已完整验证，但按你的要求暂不处理，仅登记。等观测/规划层清理完再回来。

## S1. 跨特征共识按"峰值展宽"排序，会把正确的强峰值判给错误的弱峰值

**位置**：`inversion/scripts/estimate_period.py:218-220`

```python
support, spread, period_s, evidence = sorted(
    ranked, key=lambda item: (-item[0], item[1], item[2])
)[0]
```

排序键是"支持特征数 → 相对离散度 → 周期值"，**完全没有候选分数**。

**实测**（`runs/audit_probe/spin40`，mesh 椭球、真值 12.5 s、单 run 40 s、800 脉冲、无噪声）：

| 特征 | 最佳周期 (s) | 分数 |
|---|---|---|
| total_power | 12.531 | **0.986** |
| range_centroid | 12.455 | **0.985** |
| doppler_centroid | 12.589 | **0.981** |
| doppler_bandwidth | 12.390 | **0.951** |
| range_width | 12.566 | 0.889 |
| 同一份数据里的 5.0 s 候选 | 5.0000 | 0.0003–0.0316 |

聚类结果：

```
support=5  spread=3.995e-07  center=5.000005   分数 {0.0182, 0.0075, 0.0316, 0.0003, 0.0243}
support=5  spread=4.665e-03  center=12.530762  分数 {0.9513, 0.9853, 0.9859, 0.8890, 0.9811}
WINNER: 5.000005358585615
```

12.5 s 那个簇的分数全在 0.89 以上，却因为 `spread=4.7e-3` 比 5.0 s 那个"机器精度级"的 `4.0e-7` 大而被排到第二。`best_summary.json` 于是给出 `best_period_s=5.0`、`relative_error=0.65`、`consensus_feature_support=5`、`consensus_relative_spread=4e-7`——**每个"质量指标"都在为错误答案背书**。

`runs/audit_probe/spinlong`（6 run、1200 s 跨度、真值 12.5 s）同样失败：共识给出 20.6 s 或 35.9 s（取决于配置），而同一批特征的强峰分数都是 0.95 量级。

附加证据：把 5 个特征 × 5 个**纯随机**周期喂进真实的 `_cross_feature_consensus`，`support≥3` 的概率是 **74.4%**。所以 `support` 不是证据量；而 chirp 路径的 `significant` 恒为 `False`（`inversion/src/inversion.py:180` 的多谐波 FAP 恒 `nan`），**`support` 是 chirp 反演唯一的"置信"信号，而它不可靠**。

## S2. 多谐波打分在"每 run 内恒定"的特征上退化成舍入噪声之比

**位置**：`inversion/src/inversion.py:127`（守卫只判 `std()==0.0`）、`:153-160`（`score = 1 − residual/baseline_sse`）

**实测**：两个 group 上 values = −3 / +5，搜索 8–20 s → `baseline_sse = 3.94e-28`，`best = 9.73 s`，产出 5 个候选。这些随机候选会落进真集群的 5% 窗口，抬高 `support`，与 S1 叠加。

## S3. `period_min_s` / `period_max_s` / `period_grid_size` 完全没有校验

**位置**：`inversion/src/dataset.py:87-116`（只列入 `allowed`）、`inversion/src/inversion.py:72,158`（直接使用）

**实测**：`period_min_s = -200` → `best_period_s = -200.0`，退出码 0；`lomb_scargle(min_period=-5)` → `best=-13.003`、`FAP=9.55e-14`、`significant=True`；`period_min_s=0` → `ZeroDivisionError`；`period_grid_size=0` → `argmax` 空序列；`min > max` 静默接受。

## S4. 重叠二维视图被当独立观测重复计权，`overlap` 标志只写不读

**位置**：`inversion/src/inversion.py:459-461`、`:378`；`inversion/src/radar_signal.py:376-384`；`inversion/scripts/estimate_period.py:91-97`、`:113`

`signal_echo_overlap` / `window_overlap` 在 inversion 内只被写进 `period_observables.npz` 的 `quality_flags`，而该文件**全仓没有任何读取方**；`metadata["physical_signal_overlap_present"]` 在 inversion 中 0 次引用。权重只来自 `mean(valid_samples, axis=1)`，与 overlap 无关。

**实测**（合成：全局 ADC 轴切行、真值 3.0 s、PRT 0.05 s）：1× 重叠 → `range_centroid=2.9999`；2× → 2.986 / `total_power=2.914`；4× → 2.801（6.7%）/ `total_power=5.533`（**84%**）。

**噪声侧同源问题**：`echo/src/echo.py:375-384` 每个 run 的噪声按唯一全局 ADC 样点只生成一次再分发到所有行。信号这样共享是对的，但**噪声共享没有被记录或补偿**——下游把行当独立观测时方差被低估、SNR 被高估、显著性虚高。

## S5. 多谐波路径静默丢特征

`inversion/src/inversion.py:500-512` 的 `except ValueError: continue` 无任何日志。`runs/chirp_test` 反演后 `summary.json` 只有 3 个特征，而 `period_observables.npz` 的 `feature_names` 有 5 个（`total_power`、`doppler_centroid` 被丢），用户看不到提示。

## S6. `estimate_period.py` 的"不确定度"是伪造的

`:98-102` 用相邻帧差的 MAD/√2 当 `uncertainty`，但对周期特征帧差就是信号自身变化（幅度 10、零噪声的数据报 `0.748`），恒定列被抬到 `eps=2.2e-16`，且广播到整列、无消费者。`summary.json` / `best_summary.json` 里没有任何周期不确定度；`relative_error` 依赖 echo 元数据里通常为 `null` 的 `truth_period_s`。

## S7. `ceil(duration × PRF)` 的浮点边界 off-by-one

`inversion/src/inversion.py:434-447`：`cpi_duration_s=0.28`、`prf=25` → `0.28×25 = 7.0000000000000009` → 取 8 个脉冲（用户要 7）。默认 hop（cpi/4）走同一条 `ceil`。

## S8. 其它

- `estimate_period.py:78-82` 用 `np.searchsorted(source_times, times)` 且无单调性检查（隐含假定 `scatter_elapsed_s` 递增）。
- `row_start_sample` 被加载和校验（`inversion/src/dataset.py:227`）却从不使用；它与 `row_fast_time_offset_s` 之间没有一致性校验；`offset` 全 NaN 时 `centroid_delay_axes` 静默退回全零（`radar_signal.py:198-203` 的 `elif` 因 `np.any(np.isfinite(...))` 为 False 而不触发）。
- `matched_filter_group_delay_s` 只被自己的测试引用；`centroid_delay_axes(output_lag_s=...)` 无调用方传参，群时延/前沿修正从未施加，`range_centroid_s` 实际是**前沿时延**（差约 $W/2$ 的常数），与 docstring 不符。
- `inversion/src/radar_signal.py:349-361` 对复慢时间样本线性插值重采样，触发条件很窄，未构造出实际触发算例。

---

# 第四部分 测试与工程治理

## T1. `tests/` 整个目录被 git 忽略——所有回归测试都不在版本控制内

`.gitignore:12` 是 `tests/`，`git ls-files tests` 为空。而 `README.md:52-57`、`docs/PROJECT_OVERVIEW.md` §6、`docs/GUI_ARCHITECTURE.md` §验证 都把 `tests/` 当作项目验收依据。配套的 `pytest.ini` 同样被忽略。任何一次 `git clean -X` 都会删掉全部测试。

## T2. 文档里的测试命令是错的

- `docs/PROJECT_OVERVIEW.md` §6 写 `pytest -q`，但 `pytest.ini` 的 `testpaths = tests` 会显式跳过子模块的 `tests/`（`norecursedirs` 还挡掉 `tmp/runs/outputs`）。
- `pytest tests observation/tests echo/tests inversion/tests` **必然失败**：三处目录都叫 `tests` 且无 `__init__.py`，`import tests.test_mesh` 之类互相冲突；`echo/tests` 要求 cwd=`echo/`（`from src.echo import ...`），`inversion/tests` 要求可导入包名 `inversion`（`from inversion.src.dataset import ...`），而该目录自己就叫 `inversion`。
- 正确做法是分目录运行（见本报告开头的基线表），但文档没有写。

## T3. `test_gui_schema_v4.py` 的 7 个失败是**测试失效**，不是代码回归

这些用例断言默认配置走 `observation.receive.sample_rate_hz`（CW 分支）和 `observation.target.extent_path_m`（CW 下按设计隐藏），而 `configs/campaign_v4_example.json` 已被改成 chirp，`receive` 字段根本不存在。**默认配置一改，这整套测试就整体失效**，又因为它被 git 忽略，没人会看到。

## T4. 若干测试是重言式或锁定实现细节

- `observation/tests/test_planning_regressions.py:92` `assert np.all(plan.window_overlap)` 是对"行宽 > 帧间距"这一实现细节的复述；
- `:116` `q_stop == approx(round(q_stop))` 是重言式；
- `:123` `assert not plan.row_valid[0, -1]` 把 O3 的缺陷固化；
- `observation/tests/test_planning.py:86-92` 用两段等长窗口，无法区分"累计长度等距"与"逐段等距"（改成 30 s / 10 s 才能区分）；
- `inversion/tests/test_chirp_contracts.py:71-99` 三个用例只断言 `abs(peak_hz) < 0.1`（DC 落在原点），**完全没有断言能恢复出周期**——而"恢复周期"正是该模块唯一职责，也是 S1/S4 逃过所有测试的原因。

## T5. 自带配置从未做过自检

`configs/chirp_mesh_target_test.json` 的真值 `rotation_period_s = 20`，但搜索区间是 100–1000 s——**结构上不可能测对**。仓库里没有任何"旋转网格 + 真值落在搜索区间内"的自检配置，所以 S1/S4 这类问题一直没被暴露。

## T6. 文档漂移

- `inversion/README.md:24` 仍列 `src/signal.py`（实际是 `src/radar_signal.py`）；
- `inversion/README.md:96-99` 的"单独运行"示例用 `configs/inversion.json`（只有 CW 键）跑 chirp，实测 `ValueError: chirp inversion 必须提供 cpi_duration_s`；
- `inversion/pyproject.toml` 声明 torch/astroquery/pytorch3d，漏了 `plotly`（`estimate_period.py:12-15` 可选导入，缺失时 HTML 静默不产出）；
- `observation/README.md:428/433` 把 `pre_guard_s`/`post_guard_s` 描述为"相对最早/最晚回波"的整段窗保护，与 `docs/OBSERVATION_TIME_SELECTION.md:174/184` 的"逐脉冲保存行余量"互相矛盾（后者与代码一致）；
- `observation/README.md:451-452` 只列 `manual` / `random_visible_time`，漏了实际在用的 `equal_visible_time`；`:464` 漏掉自动模式下 `run_duration_s` 必填；
- `estimate_period.py` 把周期除以 3600 当小时、动态谱把秒数除以 3600 当小时，短观测下横轴压成 0.000–0.008 h，并直接产生"共识周期为 0.000 h"这类告警；
- `rotation_gui/schema.py:155-159` 定义了 `PROGRESS_PREFIX` / `WARNING_PREFIX` / `ERROR_PREFIX`，但 `main.py:660-671` 硬编码了 `"__WARNING__ "` / `"__PROGRESS__ "`，源码里没有 `__ERROR__` 的处理分支；
- `docs/GUI_USER_MANUAL.md:299` 要求统计脚本读 `best_summary.json`，而该文件里最关键的 `best_period_s` 目前不可靠（S1）。

## T7. GUI 预览的性能与可用性

`rotation_gui/window/echo_preview.py:145-152` 为画一条"平均距离像"曲线，会对**全量** `iq` 调用 `matched_filter_chirp`（用 `fftconvolve` 对整个二维数组做卷积），而热图已经做过 `pulse_step`/`fast_step` 抽稀。大回波下点"查看回波"会有明显卡顿甚至内存压力。另外 `echo_preview_html_path` 把运行目录名里的空格替换成下划线，`"fixed target"` 与 `"fixed_target"` 会共用同一预览目录。

---

# 第五部分 修复优先级建议

| 优先级 | 项 | 理由 |
|---|---|---|
| P0 | B2（CW 字段契约） | CW 链路 100% 不可用 |
| P0 | B4（`model_path` 基准 + `validate_echo_waveform` 阶段化） | 拓扑网格实验无法通过 pipeline 运行 |
| P1 | O1 + O2（自动选时两套长度） | 上限与布局判据矛盾，报错误导 |
| P1 | O4 + O5 + O9（`selection` 白名单、`runs` 冲突、缺失字段报错） | 配置层静默降级 |
| P1 | O7（`ephemeris.location/refplane` 半截校验） | 保护逻辑形同虚设 |
| P2 | O3（尾沿少一个采样点）、O6（`duration_s` 语义）、O8（重复末点）、O10（NaN 校验）、O11（死特性） | 正确性细项 |
| P2 | T1 + T2 + T3 + T4（测试纳管、命令、失效用例、重言式） | 没有可信的回归网，前面所有修复都无法验证 |
| P3 | S1–S8（反演科学性） | 本轮暂缓；S1 与 S4 一旦处理需连带动 `best_summary.json` 的呈现方式 |
| P3 | T5–T7（自检配置、文档漂移、预览性能） | 与上面各项合并处理 |

---

# 附录 本次审计用到的复现材料

均位于 `runs/audit_probe/`（被 `.gitignore` 忽略，不影响工作树）：

| 文件 | 用途 |
|---|---|
| `probe_moving.json` + `moving/` | `raw_baseband` + 匀速直线点目标全链路 |
| `probe_spin40.json` + `spin40/` | 旋转网格、单 run 40 s、真值 12.5 s（S1 的主要证据） |
| `probe_spin_long.json` + `spinlong/` | 旋转网格、6 run、1200 s 跨度 |
| `probe_cw.json` + `cwprobe/` | CW 全链路（B2 的复现） |
| `diag_inv.py`、`diag_inv2.py`、`diag_inv4.py`、`diag_inv5.py`、`diag_consensus.py` | 反演特征与共识聚类的逐步追踪 |
| `pt/`、`example/` | `point_target_debug.json` 与坏示例配置的运行结果 |

`configs/campaign_v4_example.json` 的失败可直接复现：

```powershell
conda activate pytorch
python pipeline.py --config configs\campaign_v4_example.json
# ValueError: 复基带 chirp 要求 receiver_sampling.fast_sample_rate_hz 大于 bandwidth_hz
```

CW 链路失败可直接复现：

```powershell
python pipeline.py --config runs\audit_probe\probe_cw.json --runs-dir runs\audit_probe --run-name cwprobe
# ValueError: run_id 长度必须等于 iq 第 0 维
```
