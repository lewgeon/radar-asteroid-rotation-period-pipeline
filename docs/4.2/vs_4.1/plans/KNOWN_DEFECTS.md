# 已知缺陷与暂缓修改项

> 状态：第 1 节已在 4.2 实施；§3 已停写 `experiment.json`；§4.2b 的 `echo.npz` 行轴契约已按布局区分；§4.1/§4.4 的死代码已删除。第 2 节 inversion 重叠计权仍暂缓。审查 inversion 子模块时从第 2 节开始。

## 1. 每个 Run 最后一列 ADC 样点被半开区间丢掉（已修）

### 修复前的实现（历史记录，代码已不存在）

`observation/src/planning.py::plan_reception` 曾这样定义窗尾：

- 保存行宽 `fast_count = n_pre + n_after + 1`，行尾全局索引是 `centroid_index + n_after`（含端点）。
- Run 级窗 `q_off = ceil((desired_rx_off - rx_on) * fs)`，有效掩码 `sample_index < q_off`。
- `desired_rx_off` 取的是"最后那个样点所在的时刻"，不是"该样点之后的下一个栅格"。

echo 用同一约定：`sample_times < adc_stop`。

### 会出现什么问题

行宽 \(N\) 个样点的首末时刻跨度是 \((N-1)/f_s\)。半开区间 `[t_on, t_off)` 若把 `t_off` 设成最后一个样点的时刻，该样点恰好落在右端点上，被排除。

双站连续、8 脉冲、\(f_s=1000\,\mathrm{Hz}\)、保护 20 ms 的最小例子：前 7 行 51 个有效点，**最后一行 50 个，末列全 False**。每个 Run 固定少 \(1/f_s\) 的后置保护。计划与回波一致地少存，不是两侧失配。

### 4.2 已实施的修法

窗尾不再由"最晚回波尾沿 + `post_guard`"这一物理时刻向上取整，而是直接由行网格给出（在算完 `starts` 之后）：

```text
q_off = int(np.max(starts)) + fast_count      # 末格索引 + 1
rx_off = rx_on + q_off / fs
```

原来的 `desired_rx_off`（只被 `q_off` 使用）连同 `-1e-12` 浮点微调与 `max(1, …)` 一并删除。

行宽本身负责覆盖物理需求。后置格数按

```text
n_after = ceil((post_guard + max(after_by_pulse)) · fs + 0.5)
```

计算：`+0.5` 是**栅格补偿**。只用 `ceil` 时，质心的 `rint` 亚样点残差会让末格时刻比"最晚回波尾沿 + `post_guard`"早，实测缺口最大约 0.46 个采样；补半个采样后该不等式恒成立。守护它的测试是 `test_post_guard_margin_is_never_negative`（参数取在无补偿时确实为负的点上），`test_reception_window_covers_echo_and_post_guard` 继续守住行宽对物理需求的覆盖。

断言："每一行的末列 `row_valid` 为真"（未被切换截短时），见 `test_reception_window_keeps_every_row_fully_valid`。

### 效果与副作用

- 每个 Run 的 ADC 连续轴变化至多 δ 个样点，其中 δ = `rint(a) + ceil(b + 0.5) + 1 - ceil(a + b)`（`a`、`b` 见 [../changes/OBSERVATION_RECEPTION_WINDOW.md](../changes/OBSERVATION_RECEPTION_WINDOW.md) §5；`+0.5` 为栅格补偿）。在 $S_i$ 恒定时 **δ ∈ {1, 2}**，新窗尾至少比旧规则晚 1 个采样周期；行宽增量 $\lceil b+0.5\rceil-\lceil b\rceil$ 才是 $\{0,1\}$，二者不要混用。
- 行宽比无补偿时最多增加 1 格，触发条件是 `frac((post_guard + max(after_by_pulse))·fs) = 0 或 > 0.5`：默认点目标夹具 `after_s·fs = 150.0`（frac=0）→ 251 变 252；mesh 夹具 `after_s·fs = 100.005`（frac≈0.005，落在 (0, 0.5]）→ 保持 153。
- 二维行末列重新有效；`rx_adc_stop_elapsed_s` 不变或推迟。
- 已有 `observation_info.npz` / `echo.npz` 与新计划不再按样点逐位可比，需重跑观测与回波（迁移成本，不是语义副作用：观测、echo 与反演共用同一套半开约定，单次实验内自洽）。
- `window_overlap` 的**判据不变**（只由 `starts` 与 `fast_count` 决定，与 `q_off` 无关），但**行宽 +1 会改变它的结果**：原本"行宽恰好等于行距、因而无重叠"的配置会开始标记重叠。例：`fs=5000`、`pre=0.01`、`post=0.0298`、`脉宽=0.01`、`prf=20`（行距 250 索引）——旧行宽 250 无重叠，新行宽 251 → 全部相邻行标记重叠并触发"旧版逐行回波生成器必须拒绝该计划"警告。此处更正本文早先"`window_overlap` 不受影响"的说法。

## 2. inversion 把重叠保存行当作独立脉冲（待 inversion 重新设计时处理）

> 决定（4.2 期间）：本项不在 4.2 修，留到 inversion 模块重新设计时一并处理；下列结论作为设计输入保留。

### 当前代码

生成器在 Run 级唯一 `global_q` 上只计算一次信号和噪声，再按 `row_start_sample` 映射到二维行。`window_overlap` 只表示保存行共享索引。

`inversion/src/radar_signal.py::matched_filter_chirp` 与 `inversion/src/inversion.py::_estimate_chirp_rotation` 不读 `row_start_sample`、`window_overlap`、`signal_echo_overlap`。权重是 `mean(valid, axis=1)`。

### 会出现什么问题

行宽大于 PRT 时，同一全局样点（含同一份噪声）进入多个 CPI 脉冲，周期估计偏乐观。物理回波重叠时还有 `centroid_compensated` 的逐脉冲理想化语义，与“每行=独立脉冲”不一致。

### 若要修改

优先读取 `run_id` + `row_start_sample` 做 CPI 去重，或在 `window_overlap` 为真时拒绝/降权并写进摘要。不要改 echo 生成器来“切掉”真实物理叠加。

### 效果与副作用

去重后重叠计划上的有效独立脉冲数下降，信噪比和周期不确定度会更诚实；与旧 inversion 产物不可比。

## 3. GUI `experiment.json` 不是 canonical 快照（已停写）

运行目录不再生成 `configs/experiment.json`。阶段实际输入是 `observation.generated.json` / `echo.generated.json` / `inversion.generated.json`；来源核对走 `stage_manifest.json`。用户编辑的仍是仓库 `configs/` 下的顶层 pipeline JSON。

### 历史问题（代码已不写该文件）

AGENTS.md 要求会话快照不得悄悄覆盖用户 JSON；“保存”写的是当前表单，运行时才生成 `*.generated.json`。旧实现额外写一份 `experiment.json`，既不是用户配置，也不是阶段权威输入，还可能与 generated 不一致。

### 当前行为

`rotation_gui/window/main.py` 与 `pipeline.py` 只写三个 `*.generated.json`。复用比较阶段有效依赖投影，不读取 `experiment.json`。

## 4. 其它暂缓项（改动面大或缺少验收夹具）

| 项 | 当前行为 | 风险 | 改法要点 |
|---|---|---|---|
| ~~自动选时容量 \(H\) vs \(D\)~~ | 已核对（代码 + 回归测试）：`layout_capacity` 与传给 `select_run_start_offsets` 的参数现在都用 `occupied_duration_s`，两处同一把尺子 | — | **该项作废** |
| 预览窗与正式 ADC 窗口径差异（审计 N4） | 预览用近似双程时延 + 线性插值，正式解算用逐脉冲三事件 + 时标伸缩 + 整数格对齐 | 极端几何下两者可差到肉眼可见；单站模式若近似占用时长偏小，正式阶段会直接报"跨 run 收发冲突" | **已评估：接受为近似，不追求精确对应**。GUI 时间轴只表示 Run 的相对分布（秒级精度、无交互），追求精确对应会让实时预览的算量暴增。若将来真被触发，代价最小的是给预览加固定小裕量，而不是改成精确解算 |
| 可见性网格重复末点 | 当前 `np.arange(0, duration, step)` 不含右端，仅在末值不等于 duration 时追加终点 | 已用 `test_sampling_never_extends_past_end` 断言严格递增 | **已核对：当前代码不再重复末点** |
| `Spin` 缓存 | 缓存键含设备、初相位、周期和自转轴 | 修改已有实例字段会重算 | **已修**，见 `../changes/RUNTIME_LOGIC_FIXES_2026-09-21.md` |
| `pulse_batch_size=1` 的 CUDA OOM | 网格路径在存在 `batch_kernel` 时即使批量为 1 也走该内核，pair/facet 仍可缩块 | 点目标路径仍无 `batch_kernel` | **网格路径已修**；点目标不适用该退避 |
| Horizons `location` / `refplane` | **已删除**（见 §4.1）：中心固定为地心、参考平面固定为地球赤道，链路只支持这一种组合 | — | **该项作废** |

### 4.1 本轮已删除的死代码

| 项 | 处理 |
|---|---|
| `planning.py` 的 `run["pulse_count"]` 分支 | **删除**。`_RUN_KEYS` 不含该键，任何配置携带它都会被拒，分支不可达。 |
| `planning.py` 的 `max_window_iq_bytes` 保护 | **删除**。接收机内存上限按"实际足够大"处理，不再提供该配置项。 |
| `echo.py::_positive_integer` 的 `isinstance(value, bool)` | **删除**。JSON/GUI 不会产生布尔值（JSON `true` 解析为 `bool` 而非数字），该检查不可达；`np.True_` 与 `True` 现按普通整数处理。 |

注：`receiver.get("complex_sample_bytes", 8)` 保留，但没有任何配置文件能设置它；它只影响 `estimated_window_iq_bytes` 这一信息字段，不参与物理计算。

**Horizons 星历中心与参考平面（同批删除）。** 观测站中心确定为地心，链路只支持"地心 `@399` + 地球赤道 `earth`"这一种组合，因此删除了：

- `observation_info.py::_validate_reference_frame_config` 中对 `ephemeris.location` / `ephemeris.refplane` 的两条校验（该函数只保留 horizons_vectors + geodetic_fixed 的互斥检查）；
- `_metadata_source` / `_metadata_frame` 里对这两个键的读取（改为直接写明固定值）；
- `ephemeris.py::horizons_vectors_state_from_config` 中重复的字段白名单（该键的拒绝由 `config_normalize.py` 统一负责）。

若将来需要地心以外的观测中心，那是独立功能（测站坐标语义、高度角定义、光行时链路、GUI 测站卡片都要改），不以上述校验的形式预留。

### 4.2 修末列 ADC 与清理死代码时带出的问题（已处理）

| 项 | 处理 |
|---|---|
| 自动选时缺 `end_utc` 时窗口静默塌成 1 秒 | **已修**。`resolve_campaign_run_plan` 在自动模式下要求 `end_utc`，缺了就明确报错；不再退回按残留 `runs` 推算。自动模式若仍携带手写 `runs`，规范化也会直接拒绝。回归测试 `test_automatic_selection_requires_end_utc`、`test_automatic_selection_rejects_leftover_manual_runs`。 |
| 预览里三次 `positions_many` 在 `try` 外 | **已修**。位置查询与几何可见性一样降级为警告 + `visibility_computed=False`，预览不再因 Horizons/网络失败硬中断；两处 `except` 口径统一为 `(ValueError, RuntimeError)`。 |
| 两个开发夹具的 `schedule.runs` 与 `selection=equal_visible_time` 并存的无效表 | **已删除**。自动模式下该表本来就被规范化丢弃，留着只会让人以为手动表生效。 |
| `OBSERVATION_RECEPTION_WINDOW.md` §6 代价 3 仍写旧的 $t_{\mathrm{on}}$ 公式 | **已改**为与 §4/代码一致的 $\max(t_{\mathrm{ready}},\min_i t_{\mathrm{rx},i}-n_{\mathrm{pre}}/f_s)$。 |
| `plans/README.md` 把本文件标成"尚未实施" | **已改**为"部分实施"。 |

### 4.3 仍未处理的同类小项

| 项 | 说明 |
|---|---|
| GUI 与 CLI 对 chirp 带宽的校验时机 | 两处**用的是同一个** `pipeline.py::prepared_configs`：GUI 传 `validate_echo_waveform=False`（只跑观测阶段时），CLI 走默认 `True`。echo 自己在 `echo/src/echo.py::_chirp_fast_time_axis` 也有同一条件的校验，所以**没有"一个严一个松"的后果**，差异只在报错早晚。清理方向：删掉 pipeline 里这份重复校验，或让 GUI 的早校验与 echo 保持一致；需先定策略再动。 |
| 根仓库 `.gitignore` 忽略 `tests/`、`pytest.ini` | **已修**：两行已删除，根 `.gitattributes` 补 `tests/** export-ignore`。根目录 4 个回归测试与 pytest 配置现在可提交，发布归档仍不含测试。 |
| `runs/chirp_test/observation_info.npz` 是修复前产物 | 最后一行仍少一格；若要作为新旧对照基准，应按当前代码重新生成。 |

已在本轮一并处理的小项：`select_run_start_offsets` 里不可达的第二个 `if random:`（已删，等距与随机两条路径都实测通过）；`continuous_receive_axis_fields` 的 `common_path_rate_m_s` 占位由 `0` 改为 `NaN`，与缺键回退语义一致。

### 4.2b `echo.npz` 行轴契约改为按布局区分（本轮实施）

**现象**：CW（一维 `iq`）被迫写出 12 个它从不读取的行轴字段（`coherence_id`、`acquisition_id`、`run_id`、`track_id`、`row_start_sample`、`row_fast_time_offset_s`、`centroid_fractional_offset_s`、`rx_adc_start_elapsed_s`、`rx_adc_stop_elapsed_s`、`signal_echo_overlap`、`window_overlap`、`common_path_rate_m_s`），只是因为 `inversion/src/dataset.py::_validate_echo_dataset` 用同一个字段清单校验两种布局。这些字段是"测站观测"侧的，回波文件里本来没有；占位值毫无物理含义。

**根因**：加载校验不区分 `iq` 维数。`echo_npz` 的键集是固定的，于是 CW 必须补占位才能过校验。

**修法（已实施）**：

- `inversion/src/dataset.py::_validate_echo_dataset(echo, present)` 按 `iq.ndim` 分两条路：
  - **一维（CW）**：只要求逐样本字段（`tx_range_m` / `rx_range_m` / `scatter_elapsed_s` / `emit_elapsed_s` / `tx_los_icrs` / `rx_los_icrs`）。行轴字段**可以缺席**（`load_echo` 用兜底值），若文件提供了则校验长度。
  - **二维（chirp）**：行轴字段必须**齐备**（用 `present` 判断是否真的写在文件里，避免兜底值掩盖缺失）且长度等于脉冲数。
- `echo/src/dataset.py::save_echo` 只在 `iq.ndim > 1` 时写行轴字段；一维文件不再含这些键。
- 删除 `continuous_receive_axis_fields`（它存在的唯一理由就是给 CW 补占位）。

**影响**：CW 的 `echo.npz` 键数因此是 24 − 12 = 12。`inversion` 的 CW 路径本来不读它们；GUI 回波预览用 `required.issubset(data.files)` 做缺键保护，不受影响。旧 CW 文件（带占位）仍可加载——CW 分支对"提供了但不合长度"才报错。

**验收**：`inversion/tests/test_cw_echo_load.py` 覆盖四条（CW 无行轴键可加载 / CW 提供的行轴键长度错要拒 / chirp 缺一个行轴键要拒 / chirp 行轴长度不符要拒）；`echo/tests/test_dataset.py` 覆盖"CW 不写行轴键、chirp 必写"；`echo/tests/test_cli_smoke.py` 对 CW 与 chirp 两个入口分别断言键的存在性。

### 4.4 覆盖率测量后删除的死代码

用 AST 行插桩覆盖率（`tmp/audit/run_coverage2.py`）对四个模块跑完整测试套件，再逐个做调用点核实后删除：

| 项 | 判定依据 |
|---|---|
| `echo/src/dataset.py::ObservationSchedule`（整个类，含 `uniform_receive_samples` / `from_elapsed` / `from_utc`） | **调用点证据**：全仓库搜索只有类定义与一条测试引用；回波链路的时间轴来自 `load_observation_info()` 读 npz，`EchoDataset` 不持有该类。已删类与对应测试。 |
| `continuous_receive_axis_fields` 的 `observation` 参数与内部 `take()` 取值机制 | **逻辑证据**：CW 观测对象按定义不带 `row_start_sample` / `run_id` / `common_path_rate_m_s` 等行轴字段（已实测），取值路径在任何 CW 输入下都返回占位值。已简化为直接返回占位数组，两处调用同步去掉参数。 |

注意两者的证据类型不同：第一类是"全仓库无调用点"，第二类是"存在构造上不可能生效的路径"。**"测试没跑到"不等于死代码**——例如 `GeodeticStation.ecef_position_m()` 只是没有测试覆盖，它有生产调用点（`ephemeris.py:558`），未删。

这些暂缓项都不改变当前默认 Chirp 作业的物理公式；需要改时各自补失败用例，不要和 inversion 审查绑在一起。

## 5. 与可见性字段相关的设计记录

`docs/4.2/VISIBILITY_AND_STATION_TYPE.md` 记录了"可见性字段只在测站使用真实坐标时才有意义"。该改法已实施：自定义直角坐标不得携带 `visibility` 段，混合测站只约束有本地地平的一侧，GUI 按坐标类型显隐字段。验收见 [../changes/RUNTIME_LOGIC_FIXES_2026-09-21.md](../changes/RUNTIME_LOGIC_FIXES_2026-09-21.md)。
