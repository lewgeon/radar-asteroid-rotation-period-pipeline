# CW 行轴契约、选时校验与示例配置清理

> 状态：已在 4.2 实现。未改 inversion 算法；重叠保存行的重复计权见 `../plans/KNOWN_DEFECTS.md` 第 2 节。

## 1. CW `echo.npz` 可被 inversion 加载

CW 一维 `iq` 以前不填 `run_id`、`row_start_sample` 等行轴字段，`save_echo` 仍写入长度为 0 的数组。inversion 按 `iq.shape[0]` 校验这些键，加载立即失败。

**4.2 后续修正（行轴契约按布局区分）**：真正的问题不是"CW 没填占位"，而是加载校验用同一个字段清单校验两种布局。现在：

- `inversion/src/dataset.py::_validate_echo_dataset` 按 `iq.ndim` 分流：一维（CW）只要求逐样本字段，行轴字段可以缺席（`load_echo` 用兜底值），若提供则校验长度；二维（chirp）要求行轴字段齐备且长度等于脉冲数。
- `echo/src/dataset.py::save_echo` 只在 `iq.ndim > 1` 时写行轴字段，一维文件不再含这些键。
- 原先为 CW 补占位的 `continuous_receive_axis_fields` 已删除。

因此 CW 文件不再带无物理含义的占位值；旧文件（带占位）仍可加载。详见 `../plans/KNOWN_DEFECTS.md` §4.2b。

网格 CW 的 `snr_db` 改为 `config.get("snr_db")`，缺键时与 chirp 一样视为无噪声。

点目标 chirp 打开与网格相同的 `frozen` 门限（`do_frozen_check=True`）。点目标无自转，只约束公共路径率引起的载波/距离迁移。

## 2. 选时字段

`observation.schedule.selection` 只允许 `manual`、`equal_visible_time`、`random_visible_time`。自动模式下若仍携带手写 `schedule.runs`，规范化直接报错；GUI 保存只写出当前选时方式的活动字段（手动只留 `runs`，等间隔留 `run_count`/`run_duration_s`，随机才写种子）。用户源 JSON 在未保存前可以仍含草稿，真正用于解算或再次载入的规范配置不能自相矛盾。

Chirp 观测元数据增加：

- `receive_centroid_span_s`：质心接收事件首末差（与写入 `receive.duration_s` 的量相同）
- `adc_window_duration_s`：各脉冲保存行共用的 Run 级 ADC 窗时长（取最大）

`receive.duration_s` 的旧含义不变，避免下游把 ADC 窗当成质心跨度时再静默改数。

## 3. 示例配置

已删除无法运行的 `configs/campaign_v4_example.json`。无 GUI 会话时默认载入 `configs/chirp_point_target_test.json`（开发夹具）。正式示例待流水线完全跑通后另写。
