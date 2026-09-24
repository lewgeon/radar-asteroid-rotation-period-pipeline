# 波形从属：PRF/脉宽归 observation.transmit，类型归 echo.waveform.type（2026-09-21）

> 状态：已在当前工作区落地。不改 inversion 周期估计算法，也不实施 ADC 布局迁移。

## 1. 结论

GUI 把「发射波形」放在全局按钮，并不表示该字段属于观测阶段。观测解算只需要事件源（`schedule` 或 `receive`）以及 Chirp 的 PRF/脉宽；射频类型、带宽、幅度属于回波。独立运行 observation 时，`waveform` 不再是合法字段。

当前落盘：

- Chirp 事件源：`observation.schedule` + `observation.transmit.{prf_hz,pulse_width_s}` + `radar_system` + `receiver_sampling`
- CW 事件源：`observation.receive`；不得出现 `observation.transmit`
- 射频类型：只写 `echo.waveform.type`，必须与事件源一致（Chirp↔`schedule`，CW↔`receive`）
- 旧 JSON 的 `observation.waveform` 直接报错，说明应把 PRF/脉宽移到 `transmit`、类型移到 `echo.waveform.type`，不做静默改写

GUI 顶部「发射波形」只写 `echo.waveform.type`，并切换观测事件源。观测页「发射时序」卡片绑定 `observation.transmit.*`。

流水线在观测阶段若 echo 尚未填写 `type`，可按事件源补上；两边都有值但不一致时失败。只跑 observation 子模块时不要求 echo 段。

## 2. 验收

- `normalize_observation_config` 拒绝 `observation.waveform`，路径出现在中文错误里。
- `prepare_run(..., through_stage="observation")` 不因缺少 `echo.waveform.type` 失败，并按 `schedule` 补成 `chirp_pulse_train`；调用方内存中的配置不会被改写。
- `through_stage="echo"` 时 `echo.waveform.type` 与 `schedule`/`receive` 不一致会失败。
- GUI 载入含 `observation.waveform` 的 JSON、或表单 `collect` 遇到该块，都会报中文废弃错误，不会把 PRF 迁到 `transmit`。
- GUI 切换到连续波后配置无 `observation.waveform` / `observation.transmit`，`echo.waveform.type` 为 `continuous_wave`。

```powershell
conda run -n pytorch python scripts/run_all_tests.py
```
