# 带入 4.3 的开放问题

> 状态：4.2 宣告完成时仍未处理。历史诊断、已修项和当时的行号留在 `docs/4.2/vs_4.1/`，不在这里重复。

## 1. 周期反演算法尚未作为 4.2 交付

`docs/4.2/vs_4.1/plans/LOGIC_STABILITY_FIX_PLAN_2026-09-21.md` 第 1.2 节明确不做：

- 不修改 inversion 的周期估计算法、CPI、共识、显著性和计权策略。
- 不确定最终 inversion 配置字段、默认值和搜索范围。
- 不建立论文级周期反演精度结论。

4.2 只保证 pipeline 能找到并启动 inversion 入口。4.3 从这里开始做周期反演。

## 2. inversion 把重叠保存行当作独立脉冲

生成器在 Run 级唯一 `global_q` 上只计算一次信号和噪声，再按 `row_start_sample` 映射到二维行。`window_overlap` 只表示保存行共享索引。

inversion 当前不读 `row_start_sample`、`window_overlap`、`signal_echo_overlap`。行宽大于 PRT 时，同一全局样点进入多个脉冲，周期估计会把重复样点当成独立观测。

处理时优先按 `run_id` + `row_start_sample` 去重，或在 `window_overlap` 为真时拒绝或降权。不要改 echo 生成器来切掉真实的物理叠加。

完整推导和当时的代码位置见 `docs/4.2/vs_4.1/plans/KNOWN_DEFECTS.md` 第 2 节。

## 3. ADC 整数网格仍由观测阶段生成

离散 ADC 布局仍在 `observation/src/planning.py`。迁移步骤、字段归属和验收标准见 [ADC_PLANNING_REFACTOR_PLAN.md](ADC_PLANNING_REFACTOR_PLAN.md)。2026-09-23 起 Chirp 保存行余量只来自 `target.extent_path_m`，计划正文里把 `pre_guard_s` / `post_guard_s` 当作现行输入的句子已经过时。

距离门字段和网格试例已在 4.2 落地，见 `docs/4.2/vs_4.1/changes/RANGE_GATE_2026-09-23.md`。该计划里「改存储契约」和 ADC 职责迁移仍不做。

## 4. 暂缓的卫生项

`docs/4.2/vs_4.1/plans/REVIEW_2026-09-21_OPEN_ISSUES.md` 中的 L3（`observation/tmp/` 历史残留、`adc_window_duration_s` 未写入通用文档）在 4.2 结束时仍暂缓。其余 D/T/L 项已有落地说明，不带入 4.3 待办。
