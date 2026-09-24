# 术语与配置字段释义

本文件是当前项目中用户可见配置与领域术语的唯一权威说明。架构契约见 [ARCHITECTURE_V4.md](ARCHITECTURE_V4.md)；操作步骤见 [GUI_USER_MANUAL.md](GUI_USER_MANUAL.md)。

## 领域术语

**坐标格式**：测站初始坐标的表示方式，分为直角坐标和大地坐标。不要把“坐标格式”叫成“状态”。

**初始坐标**：观测起始时刻的测站位置；可以是三维直角坐标，或 WGS84 经度、纬度和椭球高。

**大地坐标测站**：由初始 WGS84 经度、纬度和椭球高确定的地面测站。

**随地球自转更新位置**：测站的大地坐标保持不变，但其地心惯性系位置随事件时刻变化。

**固定大地坐标位置**：把初始 WGS84 大地坐标转换为一个固定笛卡尔点，不随事件时刻更新。

**匀速直线运动**：从初始直角坐标出发，以恒定三维速度运动。

**观测窗口**：`schedule.start_utc` 到 `schedule.end_utc` 的任务时间范围，也是可见性搜索与时间原点。

**运行周期（run）**：一次完整的硬件运行周期；单站收发切换体制下包含发射段、切换段和接收段。

**脉冲（pulse）**：run 发射段内的一个 chirp，前沿发射时刻按 PRT 等间隔排列。

**相干处理区间（CPI）**：在同一相干分组内选取相邻脉冲形成的短时处理窗口。

**快时间采样率**：接收 ADC 在回波窗内的均匀采样率。不是 PRF。

**脉冲重复频率（PRF）**：相邻 chirp 基准时刻的重复频率。不是接收 ADC 采样率。

**观测计划（ObservationPlan）**：observation 输出的 `observation_info.npz`。它是回波仿真的时序与 ADC 权威来源。

## 配置字段（用户可见）

| 字段 | 含义 |
|------|------|
| `schedule.start_utc` / `end_utc` | 观测窗口起止；也是可见性搜索与 elapsed=0 的原点 |
| `schedule.selection` / `runs` | 手动或自动选取发射 run |
| `visibility.sample_step_s` | 本地几何可见性采样步长（不是 Horizons 查询步长） |
| `radar_system.switch_time_s` | 单站收发切换所需时间 |
| `radar_system.safety_margin_s` | 切换后再留的安全死区，避免最早回波撞上发射占用 |
| `receiver_sampling.pre_guard_s` | ADC 窗相对预期回波前沿多开的前置保护 |
| `receiver_sampling.post_guard_s` | ADC 窗相对预期回波后沿多开的后置保护 |
| `target.extent_path_m` | 相对质心的最大额外双程路径（目标体尺度）。Chirp 规划用它与保护时间一起拉开快时间 ADC 窗；CW 连续接收不用。GUI 把它画在「接收采样」卡片 |
| `target.id` | 仅 Horizons 目标需要的目录编号 |
| `transmitter` | 发射站。单站时省略 `receiver`，几何上接收站=发射站 |
| `receiver` | 仅双站时填写完整接收站状态 |
| `ephemeris.*` | 仅 Horizons 目标需要；HTTP 分块/重试等属于环境默认，不作为常规实验字段 |
| `echo.scattering_model` | `mesh` 或 `point_target` |
| `echo.point_target.amplitude_scale` | 点目标电压幅度比例（旧名 `rcs` 已弃用） |
| `inversion.motion_compensation` | 默认 `auto`：由回波产物是否已质心补偿派生 |
| `inversion.period_time_role` | `scatter_centroid` 或 `receive_centroid` |
| `inversion.cpi_duration_s` / `cpi_hop_duration_s` | Chirp CPI 的物理时长与滑动步长；程序依据 ObservationPlan 的 PRF 换算为脉冲数 |

## 明确删除或不再使用的字段

- `campaign.id`、`campaign.target_id`、站 `id`、`same_as`
- 用户可配的 `pulse_fiducial`（调度固定为前沿）
- `cross_run_phase_coherent`（从未实现）
- 空的 `ephemeris: {}` 占位
- echo 配置中重复的 `fast_sample_rate_hz`（以 observation_info 为准）
- `ephemeris.padding_s`（v4 不再持久化；运行时使用内部光行时安全余量）
- `inversion.cpi_pulses` / `cpi_hop_pulses`（已拒绝；v4 只接受物理时长）
