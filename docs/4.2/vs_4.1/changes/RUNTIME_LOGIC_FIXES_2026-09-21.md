# 运行逻辑收尾（2026-09-21）

> 后续：批次 A–F 已由 [`CONFIG_FINGERPRINT_AND_GUI_SEAM_2026-09-21.md`](CONFIG_FINGERPRINT_AND_GUI_SEAM_2026-09-21.md) 落地。下文第 6 节里“A–F / leftover runs / model_path”描述的是本文件对应那一轮尚未做的事项，不再表示当前代码。

## 1. 结论与作用域

- 自定义直角坐标测站不再携带或应用地平可见性字段；混合测站只约束有本地地平的一侧。
- `pulse_batch_size=1` 仍走带 pair/facet 缩块的 `batch_kernel`，不再绕开 CUDA OOM 退避。
- 直接加载 `observation_info.npz` 时，`fast_sample_count=4.9` / `true` 会报错，不再截成 `4` 或 `1`。
- 行为文档中的窗尾推迟量 δ 在恒定 $S_i$ 下为 $\{1,2\}$；行宽增量才是 $\{0,1\}$。两份 `DATE_LOG` 正文不回写，只在文首标注勘误。

本轮不修改 inversion 的周期估计算法，也不清理确认中的死代码。

## 2. 可见性与 GUI

- `observation/src/config_normalize.py` 拒绝自定义 `static/linear` 测站上无物理含义的高度角、采样步长和“允许不可观测”字段；混合测站只拒绝笛卡尔一侧的高度角字段。
- `campaign_planning.py` 对两端均为直角坐标的任务使用完整 campaign 区间，并区分 `visibility_applicable` 与 `visibility_computed`。
- 灰色斜纹只用于 `visibility_applicable=true` 且 `visibility_computed=false`。直角坐标即使位置查询失败也不画斜纹。

区分测试：直角坐标不可行预览的详情含“自定义直角坐标：不应用地平可见性约束”、不含“灰色斜纹”；构造 `visibility_computed=false` 的载荷才出现灰色斜纹。混合测站 GUI 显示发射侧高度角，不显示接收侧高度角。

## 3. Chirp 批处理与 metadata

- 网格 `pulse_batch_size=1` 仍走 `batch_kernel`；点目标路径没有该内核。`ECHO_SIMULATION_PERFORMANCE_PHASE_B.md` 里“设为 1 使用逐脉冲参考路径”已被本轮取代。
- T1 在 `plan_reception` 上有解析下界，并用 mock 证明混合测站在 `allow_unobservable=false` 时真能挡住选时。
- `echo/src/geometry.py` 用 `_metadata_fast_sample_count` 构造缺省 `row_valid`，拒绝布尔值和非整浮点。
- 测试：`test_unit_pulse_batch_still_uses_gather_pairs` 断言 batch=1 调用 `_gather_chirp_sample_pairs`；geometry 测试用无 `row_valid` 的 NPZ 拒绝 `4.9` 和 `true`。

## 4. 文档

| 编号 | 处理 |
|---|---|
| D1 | `OBSERVATION_TIME_SELECTION.md`：判据不变，但行宽 +1 会翻转“行宽等于行距”的 `window_overlap` |
| D2/D3 | `OBSERVATION_RECEPTION_WINDOW.md`：恒定 $S_i$ 时 δ ∈ {1,2}；行宽增量单独写 |
| D4 | 符号表 $n_{\mathrm{after}}=\lceil T_{\mathrm{after}}f_s+0.5\rceil$ |
| D5 | `KNOWN_DEFECTS.md`：CW 行轴字段 12 个，键数 24−12=12 |
| T1 | 解析下界保留；新增经 `plan_reception` 的小数位密扫和 `target_extent_path_m` / 多 Run |
| T2 | 此前已由产物行宽契约修复，见 `CHIRP_ROW_CONTRACT_2026-09-21.md` |
| L1 | 不回写 09-19 正文；文首注明临时目录删除记录与工作区残留不一致 |
| L2 | 保持 `DATE_LOG_2026-09-19.md` 文件名，文首写明复盘期覆盖 09-18～09-21 |
| L3 | 补 `adc_window_duration_s` 到 `PROJECT_OVERVIEW.md` / `GLOSSARY.md`；不清理 `observation/tmp/` |

可见性采样网格已有严格递增断言（`test_sampling_never_extends_past_end`）。

## 5. 回归命令

```powershell
conda run -n pytorch python -m pytest -q tests
conda run -n pytorch python -m pytest -q observation/tests
Push-Location echo; conda run -n pytorch python -m pytest -q tests; Pop-Location
conda run -n pytorch python -m pytest -q inversion/tests
```

本轮在 conda 环境 `pytorch` 中的结果：根测试 `90 passed`；observation `65 passed`（1 条 NumPy 二进制兼容警告）；echo `41 passed`；inversion `24 passed, 3 skipped`。

## 6. 明确未做

- inversion 重叠行重复计权、共识伪峰和搜索区间夹具。
- `LOGIC_STABILITY_FIX_PLAN_2026-09-21.md` 的批次 A–F（阶段化 `prepare_run`、产物指纹阻断、死代码删除）。
- 自动选时携带手写 `runs` 时仍 `pop()` 而不是直接拒绝。
- 相对 `model_path` 的工作目录语义迁移。
