证据齐了。汇总核查结果。

---

# 一、核对结论：**它这一轮的修改总体是正确的**

我按功能面逐项复现，关键项全部通过：

| 核对项 | 方法 | 结果 |
|---|---|---|
| 波形归属重构 | 读三个夹具 + 直接调 `normalize_observation_config` | 夹具已改为 `observation.transmit`（无 `waveform`）、`echo.waveform.type` 保留；旧 `observation.waveform` **被拒**且给出迁移指引；`transmit` 被接受 ✅ |
| 自动选时带手写 `runs` | 直接调规范化 | 被拒："仅用于手动选时…请删除 runs，改用 run_count / run_duration_s" ✅ |
| 双直角坐标带可见性字段 | 直接调规范化 | 被拒并**逐字段点名**：`visibility.min_tx_elevation_deg, visibility.sample_step_dir` ✅ |
| 契约校验 `validate_observation_echo_contract` | 四种配对实测 | 同代次 252/252 通过；**252 vs 251 被拒**（"检测到不同代次的 chirp 产物"）；脉冲数不符被拒；CW 走一维分支不误判 ✅ |
| 端到端 | 点目标夹具跑完整 pipeline | 跑通；`valid_sample_count = 2016`、`iq_shape = [8, 252]`；新 metadata 已写：`artifact_contract_version=1`、`observation_info_sha256=…`、`fast_sample_count=252` ✅ |
| 停写 `experiment.json` | 全仓搜索 + 看 run 目录 | 代码里已无引用；run 目录只剩 `*.generated.json` + `stage_manifest.json` ✅ |
| echo / inversion 两组测试 | 实跑 | `echo 43 passed`、`inversion 24 passed, 3 skipped` —— **与日志完全一致** ✅ |
| 既有产物向后兼容 | 扫 `runs/*/echo/echo.npz` | 四个全部可加载，含未修复的 251 列旧产物（它缺新 metadata，故不被新校验卡住）✅ |

---

# 二、发现的问题（按严重性）

## 🔴 1. 根测试套件跑不完：卡在 28%

**证据（三次复现，每次同一位置）**：

```
tests/test_gui_schema_v4.py::...test_mesh_from_point_target_restores_target_and_scattering_cards PASSED [28%]
tests/test_gui_schema_v4.py::...test_mixed_stations_show_only_horizon_side_visibility_fields   ← 卡住
```

- 111 条已正确收集（与日志一致），但**超过 10 分钟不结束**（此前基线 ~9 秒）；
- **单独跑 `tests/test_gui_schema_v4.py` 连跑三次全部通过**（26 条）；
- **二分结果**：`tests/test_artifact_contract.py` + `test_gui_schema_v4.py` 组合也卡住；两个文件各自单独跑都通过（5 条 / 26 条）。

**最可疑的点**：`tests/test_artifact_contract.py::test_root_cli_stops_before_inversion_for_stale_chirp_pair` 用

```python
subprocess.run([...pipeline.py...], capture_output=True, text=True, ...)
```

在**受限沙箱下的管道死锁模式**——这正是我 09-18 那次后台作业卡死三小时的同一个原因（子进程输出填满管道缓冲，父进程在等它结束）。而且注意它用 `capture_output=True` 时子进程 pipeline 会再 spawn 三个子进程，多层管道。

> 这条是**测试基建缺陷**（在能跑完的环境里不显现），不是产品代码缺陷。但它让"统一入口 `run_all_tests.py`"和"根组测试"在本机无法作为验收手段——**本轮最该修的一条**。

## 🔴 2. observation 组卡在 `test_ephemeris.py`

逐文件跑观察组的结果：

```
test_ephemeris.py              （无输出 → 卡住）
test_light_time.py             4 passed in 0.13s
test_observation_info.py      12 passed in 0.18s
test_planning.py               6 passed in 0.13s
test_planning_regressions.py   （27 点后卡住）
test_visibility.py             3 passed in 0.13s
```

`test_ephemeris.py` 全部用例都 `patch("astroquery.jplhorizons.Horizons")`，即**不真的联网**，但其中几条构造 `astropy.time.Time(...).tdb.jd` 会触发 **astropy 的 IERS/sidereal 数据获取（联网且无明显超时）**，在禁网环境里无限等待。该文件的 mtime 是 09-10（本轮没改），所以这是**既有隐患本轮暴露**，不是本轮引入。

`test_planning_regressions.py` 的 27 点后卡住我单独查过：把新网格断言的 144 组循环抽出来跑，**0.04 秒完成**（最坏 gap `+0.0385`），所以不是那段逻辑；卡点在它之后的某条用例。考虑到它的 mtime 是今天 17:07，这条需要作者再查。

## 🟠 3. 新增的 `scripts/run_all_tests.py` 有两个问题

**(a) 中文输出已乱码**（写进文件的就是乱码，不是显示问题）：

```python
print("\n澶辫触锛?, flush=True)          # 应为「失败：」
print("\n鍥涚粍娴嬭瘯鍏ㄩ儴閫氳繃銆?, flush=True)   # 应为「四组测试全部通过。」
```

同样是乱码出现在**测试文件里**，而且更危险——它让断言永远不会匹配真实输出或匹配错：

```python
# tests/test_artifact_contract.py
with self.assertRaisesRegex(ValueError, "瑙傛祴璁″垝涓?252 鍒楋紝鍥炴尝涓?251 鍒?"):
self.assertIn("涓婃父浜х墿涓嶅吋瀹?, combined_output)
```

这些字符串本该是"观测计划为 252 列，回波为 251 列""上游产物不兼容"。**正则里带 `?` 和乱码字节，会在真实错误信息变化时给出假通过/假失败**。建议全部改成 ASCII 子串（如 `"252"`、`"251"`、`"artifact_contract"`）或统一用 UTF-8 重写。

**(b) 强依赖 conda**：`_python_cmd()` 写死 `["conda", "run", "-n", "pytorch", ...]`，在非 conda 环境（我这个沙箱）会挂住/失败。建议允许 `--python` 覆盖，或退回 `sys.executable`（同时提示环境要求）。

## 🟡 4. `scripts/run_all_tests.py` 与已废止的文档/字段

- **`echo_overlap` 仍在 observation 侧**：日志 §3.3 说"新 observation 产物停止写 `echo_overlap`"，实测 `observation_info.npz` 已不写（`save_npz` 里没了），但 `ObservationInfo` 数据类仍保留该字段、`metadata["overlap_fields"]` 也仍列出三项——属于"停写但未清理"，与 `KNOWN_DEFECTS §4` 的"死字段"同类。
- 被删符号无残留引用：`require_sections` / `STAGE_GROUP_ORDER` / `EPHEMERIS_FIELD_ORDER` 搜索均为 0 命中 ✅（`flatten` 的 3 处命中是 echo 里同名的局部概念，不是被删的 `storage.flatten`）。

## 🟡 5. 测试会往工作区根扔临时目录且清理不干净

```
.tmp_gui_state__11688_1789986318716
.tmp_gui_state__24976_1789986309551
... 共 6 个
```

来自 `tests/test_gui_schema_v4.py::_workspace_tmp`（`mkdir` 在工作区根、`shutil.rmtree(ignore_errors=True)`）。进程被中断时目录就留下；`ignore_errors=True` 也会把真实清理失败静默掉。它们没被 git 忽略规则覆盖（`.gitignore` 里是 `tmp/`、`runs/`，不是 `.tmp_*`）。建议改用 `tmp/` 下（已被忽略），或在 `.gitignore` 增加 `.tmp_*/`。

---

# 三、日志本身的核对

| 日志声明 | 核对 |
|---|---|
| "根 111 passed" | 111 条**收集**正确；但**跑不完**（见问题 1） |
| "observation 69 passed" | 未能整组跑完（问题 2）；逐文件累计：4+12+6+3 = 25 加 `test_planning_regressions` 的部分与 `test_ephemeris` 未完成 |
| "echo 43 passed" | ✅ 一致（43 passed, 11.9s） |
| "inversion 24 passed、3 skipped" | ✅ 一致 |
| "入口 `conda run -n pytorch python scripts/run_all_tests.py`" | 脚本存在但见问题 3，且在我环境不可用 |
| 停写 `experiment.json` / 波形归属 / 契约校验 | ✅ 全部核实为真 |

---

# 四、结论与建议

**修改本身：正确。** 契约校验、波形归属、指纹、停写 experiment.json 这些实质改动我都复现通过，端到端也能跑；echo 与 inversion 两组测试数字与日志吻合。

**但"当日收尾实测通过"这个结论在本机不成立**，原因是两类测试基建问题，**与产品代码正确性无关，却直接影响可验收性**：

1. **先修根组卡顿**（问题 1）。我怀疑是 `test_artifact_contract.py` 的 `subprocess.run(..., capture_output=True)` 管道死锁；建议先把它改成输出重定向到文件（或 `stdout=PIPE` 配合读取线程），再跑整组确认。
2. **再修 observation 组卡顿**（问题 2）。`test_ephemeris.py` 的 astropy 联网获取要么 mock 掉 IERS 数据，要么设超时；`test_planning_regressions.py` 27 点后的卡点需作者定位。
3. **修 `run_all_tests.py`**：乱码字符串 + 允许指定解释器（问题 3）。
4. 顺手清理：`.tmp_*` 忽略规则、`echo_overlap` 残留字段（问题 4/5）。

需要我直接动手修其中哪几条吗？我建议先做 1 和 3（改动小、能让统一入口真正可用），2 里的 `test_planning_regressions.py` 卡点我可以继续二分定位。

**本轮我只做了核查（只读探针 + 实跑），没有修改任何代码或文档。** 我新增的探针脚本在 `tmp/audit/`：`verify_waveform_ownership.py`、`verify_contract_validator.py`、`check_grid_loop_timing.py`；临时日志在 `runs/_root_tests*.log`、`runs/_combo.log`（可删）。