# 项目概况

本文描述当前项目的架构、配置契约、入口与已知遗留项。
详细字段释义见 [GLOSSARY.md](GLOSSARY.md)，架构细节见 [ARCHITECTURE_V4.md](ARCHITECTURE_V4.md)，

## 1. 定位

小行星雷达**自转周期测量**流水线：给定观测场景与雷达参数，生成复基带 I/Q 回波（带真值标注），
再从中反演自转周期。项目由三个相互独立的子模块、一个顶层调度器和两个 GUI 入口组成。

## 2. 架构与数据流

```text
用户 v4 配置（observation / echo / inversion）
  → pipeline.normalize_config()         顶层规范化
  → observation/solve_observation_info.py
        → observation_info.npz          ObservationPlan（时序 + ADC 权威来源）
  → echo/simulate_echo.py
        → echo.npz                      复基带 IQ 回波
  → inversion/scripts/estimate_period.py
        → summary.json                  周期候选与共识结果
```

关键约定：**每个物理量只有一个权威归属，下游只读、不再重复配置。**
`observation_info.npz`（ObservationPlan）是 echo 的时序与 ADC 唯一权威来源。

## 3. 三个子模块

| 子模块 | git 仓库 | 职责 | 独立入口 |
|--------|----------|------|----------|
| `observation/` | asteroid-observation | 读观测配置，解"发射—散射—接收"三事件光行时几何，输出 ObservationPlan | `solve_observation_info.py` |
| `echo/` | asteroid-echo | 读 ObservationPlan + 回波配置，生成复基带 IQ 回波 | `simulate_echo.py`（可独立运行） |
| `inversion/` | asteroid-rotation-period-measurement | 读 echo.npz + 周期搜索策略，估计自转周期 | `scripts/estimate_period.py` |

echo 保留独立运行能力，但 chirp 时序只来自 `observation_info.npz`。可先运行
`echo/scripts/make_simple_chirp_plan.py` 生成最小脉冲 ADC 计划，再运行 echo；echo JSON
只描述射频和散射参数。

## 4. 当前配置契约（schema v4）

顶层只有三个段，**无 `schema_version` 字段**：

```text
observation
  target          state/position/velocity/extent_path_m（Chirp 采集路径窗；仅 Horizons 需要 id + object_type）
  transmitter     发射站（省略 receiver 表示单站）
  receiver        仅双站填写
  visibility      sample_step_s、min_tx/rx_elevation_deg
  radar_system    mode、switch_time_s、safety_margin_s
  transmit        prf_hz、pulse_width_s（仅 Chirp）
  receiver_sampling  fast_sample_rate_hz
  schedule        start_utc、end_utc、selection、runs
  ephemeris       仅 Horizons：query_step_s

echo
  scattering_model  mesh | point_target
  model_path / target / scattering_power / scattering_spot（mesh）
  point_target.amplitude_scale（point_target）
  radar.carrier_frequency_hz
  waveform        type、bandwidth_hz、amplitude、baseband_convention
  echo_output_reference、intrapulse_motion_model、compute、snr_db、seed

inversion
  period_min_s、period_max_s、period_grid_size
  CW：stft_window_samples、stft_overlap_fraction
  chirp：harmonics、period_time_role、motion_compensation、cpi_duration_s、cpi_hop_duration_s
```

事件源二选一，不能并存：

- chirp 脉冲序列：`schedule` + `transmit` + `radar_system` + `receiver_sampling`
- CW 连续波：`receive`（`start_utc` + `duration_s` + `sample_rate_hz`）

射频类型只写 `echo.waveform.type`（`chirp_pulse_train` 或 `continuous_wave`），必须与观测事件源一致。独立运行 observation 时不要写 `waveform`。旧 JSON 里的 `observation.waveform` 会报中文路径错误，不会静默改写。

开发验证配置：`configs/chirp_point_target_test.json`、`configs/chirp_mesh_target_test.json`、`configs/point_target_debug.json`。正式示例配置待流水线完全跑通后重新设计。

`observation_info.npz` 的 metadata 除脉冲/ADC 行映射外，还包含：

| 字段 | 含义 |
|------|------|
| `adc_window_duration_s` | 各脉冲保存行共用的 Run 级连续 ADC 窗时长（取最大）。它不是 `schedule.run_duration_s`，也不是射频连续开启时间 |
| `receive_centroid_span_s` | 本 Run 内质心回波接收时刻的跨度 |
| `visibility_windows_elapsed_s` | 实际用于选时的可见时间段；自定义直角坐标测站上这就是完整 campaign 区间 |

## 5. 废弃字段

`receiver_sampling.pre_guard_s` 与 `post_guard_s` 在载入时并入 `target.extent_path_m`（取路径长度与 $c$ 乘保护时间中的较大值）后删除，并给出警告。其余下列字段出现即报错：

- `schema_version`（配置版本号；配置边界只保留用于给出明确拒绝错误的检测逻辑）
- 旧 campaign 文档结构：`campaign`、`sites`、`echo_model`、`processing`、`period_estimation`
- `solver`（光行时收敛策略改为实现内部常量）
- `ephemeris_step_s`（→ `visibility.sample_step_s`）
- `fs_hz`（→ `receiver_sampling.fast_sample_rate_hz`）
- `pulse_fiducial`（调度固定为脉冲前沿）
- 测站 `id` / `same_as`
- `target.id`（仅 Horizons 目标保留）
- `max_bistatic_path_offset_m`（→ `target.extent_path_m`）
- `rcs`（→ `point_target.amplitude_scale`）
- `cpi_pulses` / `cpi_hop_pulses`（→ 物理时长）
- `receive.acquisitions`（第三条兼容事件源路径）
- `lfm_chirp`（→ `chirp_pulse_train`）
- `cross_run_phase_coherent`（从未实现）
- ephemeris 传输/重试键：`padding_s`、`query_mode`、`query_chunk_size`、`min_query_chunk_size`、`query_retries`、`cache`

echo 与 inversion 的独立入口使用同一份严格契约，不再保留旧字段直跑兼容。

## 6. 入口与测试

```powershell
conda activate pytorch

# 命令行全链路
python pipeline.py --config configs\chirp_point_target_test.json
python pipeline.py --config configs\point_target_debug.json      # 另一份点目标夹具

# GUI（无会话时加载 configs/chirp_point_target_test.json）
python pyside_gui.py            # 或 python -m rotation_gui
```

回归测试（以当前工作树实测为准）：

| 范围 | 说明 |
|------|------|
| 根契约/物理/GUI（`tests/`） | `pytest -q` |
| observation（`observation/tests/`） | `pytest -q observation/tests` |
| echo（`echo/tests/`） | 需以 `echo/` 为工作目录：`cd echo` 后 `pytest -q tests`（在仓库根直接 `pytest echo/tests` 会因 `src` 不在导入路径而全部收集失败） |
| inversion（`inversion/tests/`） | `pytest -q inversion/tests`（部分 GPU 测试按环境跳过） |

## 7. 配置边界

未知字段、废弃字段、错误层级以及当前波形/散射模型不适用的字段一律报错，不再静默裁剪或迁移。
GUI 在切换波形或散射模型时会改写**当前编辑会话**里的适用字段集合，然后按同一契约校验；
它不会把 `campaign`、`cpi_pulses`、`lfm_chirp` 等历史键翻译成新键。

独立 CLI（`observation/solve_observation_info.py`、`echo/simulate_echo.py`、
`inversion/scripts/estimate_period.py`）与根 `pipeline.py` 使用同一套规范化入口。
