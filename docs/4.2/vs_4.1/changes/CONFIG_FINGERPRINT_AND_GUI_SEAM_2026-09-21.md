# 配置契约、产物指纹与 GUI 统一入口（2026-09-21）

> 状态：已在当前工作区落地。本文件对应 `../plans/LOGIC_STABILITY_FIX_PLAN_2026-09-21.md` 的批次 A–F，不改 inversion 周期估计算法。
>
> **2026-09-22 勘误：** 09-21 的 CLI 在判定复用之前就把当前配置写入 `*.generated.json`，无指纹的历史 npz 会因此被静默当成可复用。GUI 当时已是先判定后写入。09-22 已把 CLI 顺序与 GUI 对齐，见 [DATE_LOG_2026-09-22.md](DATE_LOG_2026-09-22.md)。随后 leftover generated 也不再当复用证据：自动复用只认 `stage_manifest.json` 指纹。阶段成功记录现在还要求 npz 可加载且含约定键，不只是「文件存在」。测试临时目录改到 git 忽略的 `tmp/`。

## 1. 结论与作用域

- 手写 JSON 里自动选时仍带 `runs`、`run_count=1.9|true|0`、缺 `run_duration_s`，或 equal 模式带 `random_seed`：加载/运行时给出带字段路径的中文错误。
- GUI 只跑观测解算时不读取 echo 带宽与 mesh 必填项；运行回波或“运行全部”才做交叉约束。
- 相对 `model_path` 相对配置文件所在目录解析，生成配置写成绝对路径。旧“相对 echo 工作目录”仅在配置目录找不到、模块目录找得到时警告兼容。
- 产物复用比较阶段有效依赖投影，不比较整份流水线 JSON。observation 投影会去掉同几何接收站；echo 投影会把相对 `model_path` 解析成绝对路径。因此 `through_stage=echo` 写入的指纹与随后 `through_stage=inversion` 的核对使用同一套投影。不一致默认阻断；无指纹的历史产物 GUI 需确认，CLI 需 `--allow-legacy-reuse`。哈希相同但指纹缺失时不得静默复用。运行目录不再写 `experiment.json`；阶段输入以 `*.generated.json` 为准。
- `observation.waveform` 已拒绝。PRF/脉宽写 `observation.transmit`；射频类型只写 `echo.waveform.type`，并与 `schedule`/`receive` 事件源对齐。
- 全零回波始终记录有效区功率并写出警告；`snr_db=null` 不是严格开关，只有 `require_nonzero_echo=true` 或加噪时功率为零才失败。
- `inversion/scripts/estimate_period.py` 被 git 纳管。根目录 `scripts/run_all_tests.py` 按正确 cwd 跑四组测试。

本轮不修改 `inversion/src/inversion.py` 或 `inversion/src/radar_signal.py`。

## 2. 配置与路径

`observation/src/config_normalize.py::normalize_observation_config` 是 observation 静态入口。自动模式禁止 `runs`，要求 `run_count`、`run_duration_s`、`end_utc`；整数字段拒绝布尔和截断小数。GUI 保存只写出当前选时方式的活动字段；载入自相矛盾的 JSON 与 CLI 同一条错误。

`pipeline.prepare_run(..., through_stage=)` 的取值为 `observation` / `echo` / `inversion` / `full_pipeline`。观测阶段组装波形时不检查采样率与 Chirp 带宽。

## 3. 指纹与原子写入

observation 指纹 = 规范化 observation + 契约版本；echo 指纹 = 规范化 echo + `observation_info.npz` SHA-256 + 契约版本。阶段成功且主产物存在后才写 `stage_manifest.json`。JSON 先写临时文件再 `os.replace()`。

区分测试：只改载频时 observation 指纹不变；改 PRF 时变化。GUI 在 echo 带宽与记下该产物的阶段指纹不一致时阻断反演，不因 inversion 搜索上限变化而阻断。

## 4. 零回波与预览

Chirp、网格 CW 和点目标 CW 都记录 `valid_signal_power`。预览摘要区分“近似可排列最多 N 次 Run”与正式计划可行；单站跨 Run 冲突复用 `monostatic_cross_run_conflict`。

## 5. GUI 状态机与入口

阶段状态为 `未运行 → 校验中 → 运行中 → 成功/失败/已中止`。退出码 0 但主产物缺失记为失败。启动失败、用户中止和上游不兼容都会清空 pending 并停进度。

## 6. 回归命令

```powershell
conda run -n pytorch python scripts/run_all_tests.py
```

## 7. 临时目录卫生

清理前清单（未作为功能修复删除）：

- `observation/tmp/`：`echo_verify`、`echo_verify_horizons`、若干 `observation_info_*_check.npz`
- `echo/tmp/`：`cli_smoke_*`、`old`、`perf`、若干 `probe_*`、`adversarial_review_c.py`
- 仓库根 `tmp/`

L3 约定不把删除这些目录写成功能修复。测试过程中的 `.tmp_*` 由各测试自己回收。

```powershell
conda run -n pytorch python -m pytest -q tests
conda run -n pytorch python -m pytest -q observation/tests
Push-Location echo; conda run -n pytorch python -m pytest -q tests; Pop-Location
conda run -n pytorch python -m pytest -q inversion/tests
```
