# Chirp 末列与产物行宽契约修复证据（2026-09-21）

## 1. 结论与作用域

当前 `observation/src/planning.py::plan_reception` 已采用修复后的行宽与半开 ADC 窗公式：后置格数为 `ceil(after_s * fs + 0.5)`，每个 Run 的半开右端为 `q_off = max(row_start_sample) + fast_sample_count`。在该前提下，当前代码生成的每一行最后一列都位于 `[0, q_off)` 内；本次没有再次改写这两个数值公式，而是补上它们缺失的变异区分测试和 observation→echo→inversion 产物契约，阻止修复前 251 列产物与当前 252 列计划静默混用。

该结论只适用于由当前 `plan_reception` 生成、并通过当前 echo 入口保存的 chirp 产物。CW 是一维连续接收轴，不使用脉冲×快时间行宽，本次只为其记录来源 observation 的哈希，不增加 chirp 行宽约束。

## 2. 为什么旧版最后一行少一个采样点

旧实现先按“最晚物理回波尾沿 + 后置保护”向上取整得到 `q_off`，同时把 ADC 窗解释成半开区间 `[0, q_off)`。最后一行最后一格的整数索引在边界配置中恰好等于 `q_off`，于是被条件 `index < q_off` 排除；默认点目标旧产物表现为前七行 251 个有效点、最后一行 250 个有效点。当前实现让 `q_off` 直接覆盖行网格的末格后一位，并用半采样补偿保证行网格自身不早于物理尾沿，因此当前点目标产物为 8×252 且逐行全有效。

## 3. 本次修改

- `pipeline.validate_observation_echo_contract` 同时读取 observation 与 echo：对 chirp 核对脉冲数、行宽、`fast_time_s`、`row_start_sample`、metadata 行宽和可用时的 observation SHA-256；CW 不走二维行宽检查。
- 根 pipeline 在启动 inversion 前执行上述契约；发现 252↔251 或来源哈希不一致时以非零状态停止。
- GUI 在启动 inversion 和生成 echo 预览前执行同一契约；不兼容时不启动进程、不打开预览，并给出“请重跑 echo”的明确原因。
- GUI 每次打开预览都从当前选中的 run 重新校验 NPZ 并重建派生 HTML，不能再用旧缓存绕过 252↔251 检查；“全部运行”在 observation 完成后进入 echo 校验失败时也会恢复运行按钮，不会停在假运行状态。
- 新 echo 在加载 observation 前后各计算一次 SHA-256，加载期间文件变化则失败；metadata 写入固定在加载时的 `artifact_contract_version=1`、`observation_info_sha256`，chirp 额外写入 `fast_sample_count`。
- inversion 的 echo 加载器在新 metadata 存在时验证 `fast_sample_count == iq.shape[1]`，防止单个文件内部自相矛盾。
- `test_post_guard_margin_is_never_negative` 现在实际使用原先闲置的 `expected_gap`，按旧无补偿公式重算并确认负裕量；新增小数位密扫证明 `+0.5` 正确而削弱成 `+0.4` 会失败。

## 4. 红绿证据

新增 GUI 回归测试先在旧实现上失败：它构造 252 列 observation 与 251 列 echo，旧 GUI 仍调用了 inversion 的 QProcess。失败摘要为 `Expected 'start' to not have been called. Called 1 times`。加入契约后，同一命令通过：

```powershell
conda run -n pytorch python -m pytest -q tests/test_gui_schema_v4.py::GuiSchemaV4Tests::test_inversion_rejects_echo_with_stale_chirp_row_width
```

结果：`1 passed`。该测试还确认 GUI 预览拒绝同一对不兼容产物。

另有根 CLI 入口回归测试真实执行 `pipeline.py --skip-observation --skip-echo`，构造 252 列 observation 与 251 列 echo，断言进程在 inversion 启动前以非零状态退出，且输出同时包含“上游产物不兼容”和两侧实际列数；这避免只测辅助函数而遗漏入口接线。

全新上下文对抗性审查额外构造了两条 GUI 状态路径。第一条让“全部运行”先成功完成 observation、再以超带宽配置进入 echo，旧代码会留下“运行/全部运行禁用、停止启用”的死锁状态；新增测试在修复前得到 `run=False, run_all=False, stop=True`，修复后得到 `run=True, run_all=True, stop=False`。第二条先放置旧预览 HTML，再把 observation 更新为 252 列而保留 251 列 echo；旧代码会直接打开缓存，修复后打开动作不会发生，预览状态被清空并记录契约错误。

## 5. 真实产物核对

以下命令读取仓库现有产物的实际形状：

```powershell
conda run -n pytorch python -c "import numpy as np; from pathlib import Path; paths=[Path('runs/chirp_point_target_test/observation_info.npz'),Path('runs/chirp_point_target_test/echo/echo.npz'),Path('runs/chirp_test/observation_info.npz'),Path('runs/chirp_test/echo/echo.npz')]; [(lambda d,p: print(p,'shape=',d['valid_plan'].shape if 'valid_plan' in d else d['iq'].shape,'valid=',d['valid_plan'].sum(axis=1).tolist() if 'valid_plan' in d else None))(np.load(p,allow_pickle=False),p) for p in paths]"
```

当前同源点目标产物是 observation `(8, 252)`、逐行有效数均为 252，echo 为 `(8, 252)`；修复前 `runs/chirp_test` 是 observation `(8, 251)`、逐行有效数 `[251, 251, 251, 251, 251, 251, 251, 250]`，echo 为 `(8, 251)`。`validate_observation_echo_contract` 接受当前 252↔252 对，拒绝当前 observation 与旧 251 列 echo 的组合。

## 6. 回归命令与结果

```powershell
conda run -n pytorch python -m pytest -q tests
conda run -n pytorch python -m pytest -q observation/tests
Push-Location echo; conda run -n pytorch python -m pytest -q tests; Pop-Location
conda run -n pytorch python -m pytest -q inversion/tests
```

结果分别为：根测试 `81 passed`；observation `59 passed, 1 warning`；echo `36 passed`；inversion `22 passed, 3 skipped`。observation 的唯一 warning 是当前环境中 NumPy 扩展的二进制兼容性提示；所有测试均通过。其中 echo 的真实子进程 smoke 同时执行 CW 与 chirp，确认新 metadata 两种布局都能保存，chirp 的 `fast_sample_count` 等于 `iq` 第二维，来源 SHA-256 等于实际 observation 文件。

## 7. 已知限制

旧 echo 没有 `observation_info_sha256`，因此只能用同一 run 中的 observation 行宽、脉冲数和行起点做兼容检查；如果用户只提供一个孤立的旧 echo 而没有对应 observation，无法证明其来源。现有 `runs/chirp_test` 文件没有被覆盖或删除，仍可作旧版对照，但与当前 observation 混用时会被 GUI/pipeline 拒绝。

当前跨产物检查到 inversion 子进程再次打开文件之间没有文件锁，外部进程若恰好在该间隙替换文件，仍存在标准 TOCTOU 风险。当前 echo 入口会对 observation 做两次流式 SHA-256，pipeline/GUI 契约还会读取数组；正确性回归已通过，但尚未在目标规模上量化额外 I/O、耗时和峰值内存。

**勘误（2026-09-22）：** 上文关于 P3 的表述已过时。当天后续已拒绝非整 `fast_sample_count`（含 `4.9`、布尔）以及非一维 `fast_time_s`：`echo/src/geometry.py` 的 `_metadata_fast_sample_count` 要求非负整数；`pipeline.validate_observation_echo_contract` 用精确整数核对 metadata 行宽，并要求 `fast_time_s` 为一维且长度等于 `iq` 行宽。合法生产者本来就不会写出这些值；加固针对的是手工伪造与错代产物，不再当作未做项。检查与再次打开文件之间的 TOCTOU 仍存在，没有文件锁。
