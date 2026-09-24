# 复核报告：codex 对观测/规划层的修改 + 死代码清单

本文件是对 `docs/CODE_AUDIT_REPORT.md` 中**第二部分（观测/规划层）**的复核结果，外加全仓库死代码清单。

复核对象：`observation/src/campaign_planning.py`（codex 于 2026-09-16 10:26 修改）、`observation/tests/test_planning_regressions.py`（10:25 修改）。
复核方式：逐行阅读改动 + 用独立探针脚本重跑原审计的每一条判定（`runs/audit_probe/recheck_planning.py`）。

## 0. 结论速览

| 编号 | 问题 | 状态 |
|---|---|---|
| O1 | 自动选时上限与布局用两套长度 | ✅ 已修复 |
| O2 | `select_run_start_offsets` 的容量判据语义 | ⚠️ 数值上已一致，但形参名与内部判据仍错位 |
| O3 | 每个 Run 最后一个脉冲少一个采样点 | ❌ 未修 |
| O4 | `selection` 取值无白名单 | ❌ 未修 |
| O5 | 手写的 `runs` 被静默忽略 | ❌ 未修 |
| O6 | `duration_s` 与 ADC 窗跨度不一致 | ❌ 未修 |
| O7 | `ephemeris.location` / `refplane` 校验不可达 | ❌ 未修 |
| O8 | 可见性时间网格重复末点 | ✅ 已修复 |
| O9 | 自动模式缺字段抛 `KeyError` | ❌ 未修 |
| O10 | NaN 保护时间逃逸 | ❌ 未修 |
| O11 | `run["pulse_count"]` 死特性 | ❌ 未修 |
| O12 | `target_extent_path_m` 校验可被跳过等 | ❌ 未修 |

另有 **4 个新问题**由这次改动引入（N1–N4），其中 N1、N2 需要处理。

---

# 一、已修复（逐条给出证据）

## O1 自动选时上限与布局的两套长度 ✅

**原问题**：`campaign_planning` 用调度预留长度 $H$ 算 `max_run_count`，却把 $H$ 当成"Run 本身时长"传给 `select_run_start_offsets`，而后者内部用 `w.duration_s >= run_duration_s` 与 `floor(w.duration_s / run_duration_s)` 判定容量——两个不同的数。

**现在的代码**（`campaign_planning.py:261-287`）：

```python
layout_capacity = int(sum(
    np.floor(window.duration_s / occupied_duration_s + 1e-12)
    for window in candidate_windows
))
max_run_count = layout_capacity if run_feasible else 0
...
offsets = select_run_start_offsets(
    candidate_windows,
    occupied_duration_s,          # ← 传入的就是 H
    selection_count,
    ...
)
```

上限与布局现在用同一个数。实测（单程 10 光秒、窗口 25 s、`run_duration_s=1`、单站）：

```
max_run_count=1   layout_capacity=1   occupied=21.22   runs=1
```

手算校验：$H = 1 + 20 + 0.1 + 0.1 + 0.01 + 0 + 0.01 = 21.22$；窗口 25 s；`floor(25/21.22) = 1`。两个字段相等于 `occupied_duration_s = 21.22` 处，可复现（`runs/audit_probe/recheck_planning.py` 的 `o1_o2`）。

## O8 可见性时间网格重复末点 ✅

**原问题**：`elapsed[-1]` 是 $D-step$ 时 `isclose(elapsed[-1], D)` 为假，于是追加 $D$，末尾出现 `D, D`。

**实测**：`step=60, D=100` → 现在的网格是 `[0.0, 60.0, 100.0]`（原为 `[0, 60, 100, 100]`）。

---

# 二、本次改动引入的新问题

## N1 `run_feasible` 误判：把"Run 时长"当成"整个 Run 的脉冲数可行性"（需处理）

**位置**：`campaign_planning.py:206-246`

新增的可行性检查逻辑是：用"首个回波到达前可用于发射的时间"反推出最多能放几个脉冲 `safe_pulse_count`，再判断 `pulse_count_per_run <= safe_pulse_count`。

```python
earliest_return_delay_s = float(np.min(path_s)) - extent_delay_s
available_transmit_span_s = earliest_return_delay_s - switch_s - safety_s
pulse_capacity_argument = (available_transmit_span_s - pulse_width_s) * prf_hz
safe_pulse_count = max(0, int(np.ceil(pulse_capacity_argument - 1e-12)))
...
run_feasible = bool(pulse_count_per_run <= safe_pulse_count)
```

**这个条件与 `plan_reception` 的真实约束不等价。** `plan_reception`（`planning.py:227-246`）的约束是：

$$t_{\text{tx,end}} + T_{\text{switch}} + T_{\text{safety}} < t_{\text{echo,earliest}}$$

其中 $t_{\text{tx,end}}$ 是**本次 Run 最后一个脉冲的发射前沿 + 脉宽**。而新检查比较的是"脉冲数"，只有在"脉冲列必须整体塞进首个回波到达之前"时才等价——但真实约束允许后续脉冲的回波落在下一批发射期间吗？不允许，但**允许 Run 的尾部脉冲发射晚于首个回波的到达**吗？也不允许。两者的差别在于：

- 新检查用 `np.min(path_s)`（整段选时范围里的**最小**传播时延）算 `earliest_return_delay_s`，然后与**每一个 Run** 的脉冲数比较；
- 真实约束用的是**该 Run 自己的**传播时延。

当单站、目标静止时两者相等，检查保守且正确。当目标在选时范围内运动（多 Run 场景）时，用全局最小传播时延会让所有 Run 都用最严格的门限——**偏保守，不会漏判**，但会把本来可行的 Run 判为不可行，直接抛错（`campaign_planning.py:245-246`）。

**更关键的是**：`run_duration_s` 在 `planning.build_transmit_schedule` 里只决定"能放几个脉冲"（`count = floor((D - pw)·PRF) + 1`），它**不能**被 `max_run_duration_exclusive_s` 这样简单地上界约束。GUI 文档 `docs/GUI_USER_MANUAL.md:59` 承诺"单次 Run 自身不可行时数量上限直接显示为 0，并给出建议的 `run_duration_s` 上界"——这个承诺现在有了实现，但上界公式（`:230`）是 `safe_pulse_count / prf + pulse_width`，与 `build_transmit_schedule` 的 `floor((D - pw)·PRF) + 1 <= N` 反解出来的上界并不严格一致（差一个 `1/PRF` 量级）。

**实测**（`test_preview_reports_zero_capacity_when_one_monostatic_run_is_infeasible` 的配置，`run_duration_s=600`、目标 1 光秒、单站）：`max_run_duration_exclusive_s = 1.61`，而手算 `floor((D-pw)·PRF)+1 = floor(599.99×20)+1 = 12000` 个脉冲，首个回波在 1 s 后到达，切换+安全 0.4 s，所以可用发射时长约 0.6 s，能放 `floor((0.6-0.01)×20)+1 = 12` 个脉冲……**这里 `safe_pulse_count` 的计算与 `max_run_duration_exclusive_s` 的展示值都对不上**（1.61 s 对应 32 个脉冲）。

**建议**：把这个检查改成与 `plan_reception` 同一判据的"正向试算"——用 `build_transmit_schedule` 生成该 Run 的脉冲列，再用该 Run 的传播时延直接验算 `t_tx_end + switch + safety < t_echo_earliest`，而不是用 `np.min(path_s)` 反推脉冲容量。这样两个阶段共用一条公式，不会再出现"GUI 说可行、解算报错"或反之。

## N2 `select_run_start_offsets` 的形参名与内部判据仍然错位（建议改，非功能缺陷）

**位置**：`planning.py:346-361`

```python
def select_run_start_offsets(
    windows, run_duration_s, run_count, *, random=False, seed=0,
):
    usable = sorted([w for w in windows if w.duration_s >= run_duration_s], ...)
    capacities = [int(np.floor(w.duration_s / run_duration_s + 1e-12)) for w in usable]
```

函数参数名叫 `run_duration_s`，但调用方（`campaign_planning.py:281-287`）传的是 $H$。数值上现在一致，**但同一个函数里 `run_duration_s` 现在同时表示两件事**：

- `:358` 的窗口可用性判定 `w.duration_s >= run_duration_s`：这里语义是"Run 本身至少要多长的窗口"，用 $H$ 判是**过严**的（窗口只要 ≥ $D$ 就可能容纳，只是容纳不下整段预留）；
- `:397` 的重叠回退判据 `np.diff(starts) < run_duration_s - 1e-9`：这里用 $H$ 判是**正确**的。

建议把形参改名为 `reservation_s`（或 `per_run_reservation_s`）并在 docstring 里明确"这是每次 Run 的调度预留长度，不是发射时长"，同时把 `:358` 的过滤条件与 `:376-380` 的 `feasible` 计算改为用真正的发射时长。否则下一个改动的人极容易再次搞混。

## N3 `run_duration_s` 的真实可行性仍未被 `plan_reception` 之外的地方校验（低）

新增的 `run_duration_s >= pulse_width_s` 检查（`:207-208`）与 `build_transmit_schedule` 的检查重复，无害。但 `run_count` 仍然只做 `int()` 转换（`:194`），非数字或负数会在 `select_run_start_offsets` 里以"run_duration_s 和 run_count 必须为正"报错——报错信息指向了错误的字段名。

## N4 `layout_capacity` / `adc_preview_intervals_elapsed_s` 与正式解算的口径差异（低，需确认）

- `adc_preview_intervals_elapsed_s`（`:308-322`）用 `np.interp(offset, elapsed, approximate_receive_elapsed - elapsed)` 估算 ADC 窗，这是"质心近似 + 线性插值"，而正式解算在 `plan_reception` 里用逐脉冲三事件几何 + 时标伸缩 + 对齐到整数格点。GUI 图例（`parameter_form.py:368`）写的是"紫色：近似 ADC 窗"，措辞上已经说明是近似，**可接受**，但预览与正式结果在极端情况下会有肉眼可见的差异，建议在图例里再点明"仅相对关系"。
- `layout_capacity` 用的是 `floor(window / H)`，而正式解算的 `plan_reception` 还会受单站跨 Run 收发冲突检查（`planning.py:289-304`）约束，后者更严。也就是说**预览说"最多 N 次"仍然可能在实际解算时因跨 Run 冲突而失败**。建议把跨 Run 冲突检查也提前到 `resolve_campaign_run_plan`，或在预览里加一句"未包含跨 Run 收发冲突检查"。

---

# 三、仍未修复的问题（复现证据）

以下每条都有 `runs/audit_probe/recheck_planning.py` 的实测输出。

## O3 每个 Run 最后一个脉冲少一个采样点 ❌

```
last valid index 9/10, t_last=2.000900000, adc_stop=2.001000000, gap=1.000 samples
```

`planning.py:200-202 / 252-253 / 268-269` 未改动。`observation/tests/test_planning_regressions.py:123` 的 `assert not plan.row_valid[0, -1]` 仍在把该行为固化。

## O4 `selection` 取值无白名单 ❌

```
'garbage' 被接受; 'unform_visible_time' 被接受; '' 被接受
```

`campaign_planning.py:180` 仍是 `selection = str(schedule.get("selection", "manual"))`，`if selection != "manual"` 即进入自动分支，没有任何合法值校验。

## O5 手写的 `runs` 被静默忽略 ❌

```
未报错；自动生成 2 个 run，tx_duration_s=[1.0]（手写 30 s 被忽略）
```

配置里同时给 `selection=equal_visible_time` 和 `runs=[{tx_duration_s: 30}]` 时，`runs` 被完全丢弃且无警告。`campaign_planning.py:181` 仍是 `runs = manual_runs` 然后被覆盖。

## O6 `duration_s` 与 Run 级 ADC 窗跨度不一致 ❌

`observation_info.py:296-300` 未改动：chirp 的 `metadata["duration_s"]` 仍是"脉冲质心接收事件的首末跨度"（实测 0.35 s），而不是 ADC 窗长度（0.40 s）。

## O7 `ephemeris.location` / `refplane` 校验不可达 ❌

```
仍被字段白名单先拦下：未知配置字段：observation.ephemeris.location, observation.ephemeris.refplane
```

`config_normalize.py:38` 的 `_NESTED_KEYS["ephemeris"] = {"query_step_s"}` 未改；`observation_info.py:374-400` 的 `_validate_reference_frame_config` 仍是死分支。注意 codex 只改了该文件的 docstring（"schema-v4" → "current"）。

## O9 自动模式缺字段抛 `KeyError` ❌

```
仍是 KeyError: 'run_duration_s'
```

`campaign_planning.py:193-194` 仍是 `schedule["run_duration_s"]` / `schedule["run_count"]` 直接下标。

## O10 NaN 保护时间逃逸 ❌

```
cannot convert float NaN to integer
```

`planning.py:182-187` 仍是 `float()` + `< 0` 检查，没有有限性校验；错误仍发生在 `:200` 的 `np.ceil`。

## O11 `run["pulse_count"]` 死特性 ❌

```
仍被拒绝：未知配置字段：observation.schedule.runs[0].pulse_count
```

`config_normalize.py:40` 的 `_RUN_KEYS` 未改，`planning.py:129-138` 的分支仍不可达。

## O12 其它未修项

- `echo/src/echo.py:585-599` 的 `target_extent_path_m` 校验仍写在 `if relative_path.numel():` 之内，候选样点为空时可被整体跳过。
- `planning.py:272-277` 的掩码广播写法未改（语义隐晦，非缺陷）。

---

# 四、死代码清单

`inversion/src/dataset.py` 的兜底分支、`planning.py` 的 `pulse_count` 分支属于"契约上不可达"，列入下表第 1 类。

## 4.1 契约上不可达的分支（条件恒为真/假）

| 位置 | 代码 | 为什么不可达 | 处理建议 |
|---|---|---|---|
| `inversion/src/dataset.py:150-169` | `_validate_echo_dataset` 里对 12 个字段的形状校验 | 这些键**总是**被 `echo/src/dataset.py:75-102` 写出，所以形状校验永远会执行；出错是必然的，不是"偶发" | 保留校验，但**删掉** `load_echo` 里与之重复的 `if "x" in data` 兜底（见下） |
| `inversion/src/dataset.py:198-201` | `if "sample_rate_hz" not in metadata and iq.ndim == 1:` | CW 分支**总是**写 `sample_rate_hz`（`echo/src/echo.py:797`、`point_target.py:133`），该推断分支不可达 | 删除；或在 `echo_layout == "cw"` 且确实缺失时保留并加注释 |
| `inversion/src/dataset.py:206` | `clean_iq` 的 `if ... else iq` | `save_echo` 总是写 `clean_iq` | 条件恒真，可简化为直接读取 |
| `inversion/src/dataset.py:210-215` | `coherence_id` / `acquisition_id` 的 `else` 兜底 | 同上（CW 也写这两个键） | 可简化 |
| `inversion/src/dataset.py:217-250` | `run_id` / `track_id` / `row_*` / `rx_adc_*` / `*_overlap` / `common_path_rate_m_s` 的 10 处 `if "x" in data` 兜底 | `save_echo` 无条件写全部键，**这些 `else` 分支永远不会执行**；而 CW 场景下键存在但为空数组，恰好绕过兜底并触发形状错误（就是 B2 那个 bug） | **建议删除全部兜底**，改为"键必须存在且形状正确"，并在 `save_echo` 侧修好 CW 的字段填充 |
| `observation/src/config_normalize.py:40` + `observation/src/planning.py:129-138` | `run["pulse_count"]` 支持 | `_RUN_KEYS` 不含 `pulse_count`，该键在规范化阶段就被拒绝 | 二选一：加进 `_RUN_KEYS` 并做整数校验，或删掉 `planning.py` 的分支 |
| `observation/src/observation_info.py:374-400` | `_validate_reference_frame_config` 的 location/refplane 检查 | `_NESTED_KEYS["ephemeris"]` 只允许 `query_step_s`，配置里根本进不来这两个键 | 二选一：把 `location`/`refplane` 加进 `_NESTED_KEYS`，或删掉整段校验与相关 metadata 文案 |
| `rotation_gui/schema.py:155-159` + `rotation_gui/window/main.py:660,671` | `PROGRESS_PREFIX` / `WARNING_PREFIX` / `ERROR_PREFIX` | 三个常量定义了却没人用；`main.py` 硬编码了 `"__WARNING__ "` / `"__PROGRESS__ "`，并且**没有** `__ERROR__` 的处理分支 | 让 `main.py` 改用这三个常量，并补上 `__ERROR__` 分支 |

## 4.2 定义了但全仓库零引用（可安全删除）

已用 grep 逐个确认（括号内是唯一的出现位置）：

| 位置 | 符号 | 说明 |
|---|---|---|
| `pipeline.py:134-139` | `require_sections(config)` | 函数体只是转调 `canonical_pipeline_config`，**全仓库无人调用** |
| `rotation_gui/qt_compat.py:34` | `QT_WEBENGINE_AVAILABLE = False` | 赋值后无人读 |
| `rotation_gui/qt_compat.py:97` | `QWebEngineView = None` | 赋值后无人读 |
| `rotation_gui/qt_compat.py:100` | `ALIGN_CENTER` | 无人引用 |
| `rotation_gui/qt_compat.py:103` | `KEEP_ASPECT` | 无人引用 |
| `rotation_gui/qt_compat.py:104` | `SMOOTH_TRANSFORM` | 无人引用 |
| `rotation_gui/qt_compat.py:107` | `PREFERRED` | 无人引用 |
| `rotation_gui/qt_compat.py:108` | `STYLED_PANEL` | 无人引用 |
| `rotation_gui/schema.py:41-45` | `STAGE_GROUP_ORDER` | 无人引用（实际的卡片顺序在 `parameter_form.CARD_ORDER`） |
| `rotation_gui/schema.py:149-151` | `EPHEMERIS_FIELD_ORDER` | 无人引用 |
| `inversion/src/radar_signal.py:163-167` | `matched_filter_group_delay_s` | 只有定义处出现（原审计说它"只被自己的测试引用"，实际连测试都没引用） |
| `inversion/src/light_time.py:366` | `solve_from_receive_epochs = solve_three_event_geometry` | 兼容别名，无人导入；`observation_info.py` 直接调 `solve_three_event_geometry` |
| `inversion/scripts/estimate_period.py:18` | `SRC` | 只在定义处出现（`:19-20` 用的是字面量 `ROOT / "src"`） |
| `rotation_gui/storage.py:58-64` | `flatten(prefix, value)` | 生成器，无调用方 |
| `rotation_gui/widgets/inputs.py:21` | `parse_finite_number` | 无调用方（`parse_value` 与各控件走的是别的路径） |

> 更正说明：初版清单里把 `echo/simulate_echo.py:43` 的 `runtime` 和 `observation/src/stations.py` 列为死代码，**这是错的**。`runtime` 在 `:48` 被写进 `summary["runtime_s"]`；`stations.py` 的 `GeodeticStation` 与 `WGS84_*` 被 `observation/src/ephemeris.py:10,544` 使用。已从清单移除，保留此说明以免后续按错误结论删除。

## 4.3 整个模块/文件已成孤岛（需你确认是否有意保留）

| 位置 | 状态 |
|---|---|
| `inversion/src/ellipsoid.py` | 只有 `inversion/src/ephemeris.py` 导入它，而 `ephemeris.py` 自身只被它导入 → 两个文件构成孤岛；不在 pipeline/GUI/测试链路上（`inversion/README.md:33-35` 也承认"不再参与现行测试或流水线"） |
| `inversion/src/pointing.py` | 只被 `inversion/src/ephemeris.py` 与 `inversion/tests/test_00_pointing.py` 使用。测试是否真的在跑需要你确认（README 说 `test_mesh.py` / `test_echo.py` 已跳过，但 `test_00_pointing.py` 仍在名单里） |
| `echo/src/light_time.py` | 全仓库唯一引用是它自己的内部调用（`LightTimeGeometry` 只在 `:128` 被构造）；`echo/src/geometry.py` 提供的是另一套读取逻辑 → 疑似整模块孤岛 |
| `inversion/tests/test_z_backend.py`、`test_mesh.py`、`test_echo.py` | 空壳占位（`test_z_backend.py` 只有 5 行）。`inversion/README.md:33-35` 说后两个"已跳过" |
| `echo/scripts/create_plotly_notebook.py`、`echo/scripts/make_static_light_time_geometry.py`、`echo/check_period.py`、`echo/visualize_echo.py` | 独立工具脚本，不在流水线链路上。是否算"死代码"取决于你是否还要维护它们 |
| `echo/src/period.py` | 只被 `echo/check_period.py` 使用（同一个孤岛） |

## 4.4 需要你确认后再删的（删除有副作用）

| 位置 | 符号 | 副作用 |
|---|---|---|
| `rotation_gui/window/parameter_form.py:169` | `_ALL_STATE_FIELD_KEYS` | 实际在 `:1496` 被使用，**不是死代码**（扫描器误报） |
| `rotation_gui/widgets/layout.py:10` | `LANES_BY_STAGE` | 实际在 `:60` 被使用，**不是死代码** |
| `rotation_gui/window/echo_preview.py:45` | `_write_cw_preview` | 实际在 `:36` 被使用，**不是死代码** |
| `rotation_gui/window/parameter_form.py` 的 `SECTION_META` / `CARD_ORDER` / `ECHO_FIELD_ORDER` / `INVERSION_FIELD_ORDER` / `ECHO_CHIRP_ONLY_FIELDS` / `ECHO_MESH_ONLY` / `*_WAVEFORM_DEFAULTS` | — | 全部在用，**不是死代码** |
| `observation/src/planning.py:20` | `SUPPORTED_MODES` | 在 `build_transmit_schedule` 内用于校验 `mode`，**在用** |
| `observation/src/planning.py:23` | `_utc_datetime` | 在 `utc_offset_s` / `utc_from_offset_s` 内使用，**在用** |
| `observation/src/stations.py:9-10,14` | `WGS84_A_M` / `WGS84_F` / `GeodeticStation` | 被 `observation/src/ephemeris.py:10,544` 使用，**在用** |
| `echo/simulate_echo.py:43` | `runtime` | 在 `:48` 写进 `summary["runtime_s"]`，**在用** |

## 4.5 扫描器说明

自动扫描脚本：`runs/audit_probe/deadcode.py`（粗）与 `runs/audit_probe/deadcode2.py`（精确版）。
第 4.1、4.2 两类的每一条我都用 `grep` 人工复核过；第 4.4 类是扫描器误报，**不要按粗扫描结果批量删除**。

---

# 五、修复顺序建议

1. **先修 N1**（`run_feasible` 判据），否则新增的可行性检查会与 `plan_reception` 给出不同答案，GUI 预览与正式解算会互相矛盾。
2. **O4 + O5 + O9** 一起改（都是配置层校验，位置集中在 `campaign_planning.py:180-196`）。
3. **O7**：决定是让 `ephemeris.location/refplane` 真正可配，还是删掉整段校验。这决定 `_NESTED_KEYS` 与文档要改哪一边。
4. **O10 + O11 + O12**：加有限性校验、决定 `pulse_count` 去留、把 `target_extent_path_m` 校验移出 `if relative_path.numel():`。
5. **O3**：改 `n_after` 与 `q_off` 的对齐约定，并同步改 `test_planning_regressions.py:123` 的断言（它现在锁定的是缺陷）。
6. **O6**：改 `duration_s` 语义，属于数据契约变更，需要同步 echo/inversion 的读取方。
7. **死代码清理**：先做 4.2（零引用，纯删除，风险最低），再做 4.1（不可达分支，需要顺带修 B2 那个 CW 契约），最后决定 4.3 的孤岛模块去留。
8. `tests/` 从 `.gitignore` 移出并提交（`docs/CODE_AUDIT_REPORT.md` 的 T1）——否则上面每一步修复都没有可信的回归网。
