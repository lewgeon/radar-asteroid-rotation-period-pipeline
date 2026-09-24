# Schema v4：最小场景配置与 ObservationPlan 缝

本文件描述当前可保存配置与三个子模块之间的契约。字段释义见 [GLOSSARY.md](GLOSSARY.md)。

## 原则

1. 用户 JSON 只描述场景与少量策略，不重复同一物理量。
2. observation 产出类型化的 ObservationPlan（`observation_info.npz`），echo 的时序与 ADC 只读该计划。
3. inversion 只读回波产物与周期搜索策略；射频与布局从数据派生。
4. 配置只保存为 schema v4 三段式；加载时由 `pipeline.normalize_config` 统一规范化。

5. Chirp 的 CPI 以物理时长表达，`cpi_duration_s` 与 `cpi_hop_duration_s` 在反演入口依据
   ObservationPlan 的 PRF 换算为整数脉冲数。
6. Horizons 查询 padding 是内部光行时安全余量，不属于用户场景契约。

## 数据流

```text
用户 v4 配置
  → normalize_config
  → observation（stations + schedule/receive 事件源）
  → observation_info.npz（ObservationPlan）
  → echo（波形律 + 散射体；时序来自 plan）
  → echo.npz
  → inversion（PeriodSearchPolicy）
```

## 单站约定

配置中只写 `transmitter`，省略 `receiver`。observation 入口将接收站深拷贝为发射站。不要使用 `id` 或 `same_as`。

## 事件源

- Chirp：`schedule` + `waveform` + `radar_system` + `receiver_sampling`
- CW：`receive`（连续采样）
- 二者不能同时出现

## 示例

见 `configs/campaign_v4_example.json`。
