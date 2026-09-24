# Chirp 网格回波仿真低风险加速（阶段 A）

> 状态：已在 4.2 实现。本文记录性能诊断与低风险代码修改；随后完成的跨脉冲批处理及完整实测见 `docs/4.2/vs_4.1/changes/ECHO_SIMULATION_PERFORMANCE_PHASE_B.md`。

## 1. 范围与正确性边界

本文只讨论 `echo/src/echo.py::_generate_chirp_echo()` 所走的网格目标 Chirp 回波路径。优化必须保持当前物理语义：每个 Run 先在唯一的全局 ADC 整数索引上计算并累加所有相关脉冲贡献，再按 `row_start_sample` 映射为二维 `[pulse, fast_time]` 保存行；若真实回波重叠，同一全局 ADC 样点必须包含全部相关脉冲贡献。不得把算法改成彼此独立的逐行生成，也不得用裁剪保存行代替真实物理叠加。

数值等价验收应分别覆盖 `centroid_compensated`、`raw_baseband`、`per_pulse_linear`、`frozen`、无重叠和有物理重叠场景。相同配置与随机种子下，优化前后的 `clean_iq`、有效掩码、行轴字段和元数据应一致；`complex64` 路径允许的误差只能来自运算重排造成的浮点舍入，不能出现样点位置、相位约定或贡献数量变化。

## 2. 当前作业规模

诊断对象为 `configs/chirp_mesh_target_test.json` 及 `runs/chirp_mesh_target_test/echo/summary.json`。该产物记录 `compute_device=cuda:0`、60000 个脉冲、每行 153 个样点、9179950 个有效保存样点、1280 个面元和约 944.06 s 的端到端运行时间，因此“没有使用 GPU”不是本次慢速的根因。

配置包含 50 个 Run、每 Run 60 s、PRF 20 Hz；每个脉冲的有效 Chirp 支撑约为 `pulse_width_s × fast_sample_rate_hz = 0.01 × 5000 = 50` 个采样间隔，候选集合约 51 点。主要算术规模约为：

$$60000\times51\times1280\approx3.92\times10^9$$

个“面元—样点”组合。153 列保存行中的前后保护区影响输出存储量，但当前核函数只对脉冲及目标路径支撑范围内的候选样点做面元计算，所以减小 `pre_guard_s` 或 `post_guard_s` 不会按比例降低核心算术量。

## 3. 可复现性能反馈环

性能基准位于 `echo/tmp/perf/`。这些脚本是诊断工具，不属于正式库；应从 `echo/` 目录运行，以便相对 `model_path=models/ellipsoid.obj` 正确解析。推荐命令为：

```powershell
conda activate pytorch
cd echo
python tmp/perf/profile_chirp2.py
python tmp/perf/bench_sync.py
python tmp/perf/bench_rotate.py
```

`profile_chirp2.py` 使用真实观测计划的裁剪副本，能够捕获“同一有效计算被拆成大量小 CUDA 调用”的症状。2026-09-16 在 NVIDIA GeForce RTX 2060 Max-Q、PyTorch CUDA 环境上的复测结果如下；绝对时间受 WDDM、预热和 profiler 影响，优化判断应以同一进程内的 A/B 比值为主。

| 基准 | 结果 |
|---|---:|
| GPU，默认 `facet_chunk_size=256`、`fast_sample_chunk_size=256`，预热后最小值 | 11.06 ms/脉冲 |
| GPU，`facet_chunk_size=1280`、`fast_sample_chunk_size=1024`，预热后最小值 | 4.68 ms/脉冲 |
| CPU，1280/1024，预热后最小值 | 6.82 ms/脉冲 |
| 默认 chunk 的 profiler kernel 调用数 | 约 1064 次/脉冲 |
| 1280/1024 的 profiler kernel 调用数 | 约 358 次/脉冲 |
| `.item()` 微基准 | 0.174 ms/次；相同算术不取标量为 0.064 ms/次 |
| 当前每脉冲两次 `Spin.rotate` | 约 2.62–2.75 ms/脉冲 |
| 缓存旋转基底后的两次旋转 | 约 1.07 ms/脉冲 |

这些数据验证了“小张量调用和同步开销显著”以及“旋转基底重复构造显著”两个判断。它们不支持未经实现便宣称完整作业会降到数十秒；跨脉冲批处理后的端到端时间必须实测。

## 4. 已确认的瓶颈

### 4.1 面元分块过小

当前默认 `facet_chunk_size=256`，1280 面元会被拆成 5 块；候选样点通常只有约 51 个，因此 `fast_sample_chunk_size=256` 已经能一次容纳一个脉冲的候选点，但面元循环仍把 `einsum`、可见性、局部时延、两个复指数和累加拆成大量小算子。把面元块增至 1280 后，同一 A/B 基准从 11.06 ms/脉冲降至 4.68 ms/脉冲，说明默认值不适合当前小网格。

### 4.2 面元块内部存在设备同步

`echo/src/echo.py` 在每个面元块中执行 `torch.max(torch.abs(relative_path)).item()`。`.item()` 会迫使 CPU 等待此前排队的 CUDA 工作完成；当前默认分块下每个脉冲最多发生 5 次。微基准确认同步本身有可测成本，但其端到端收益不能简单用单次微基准乘调用次数估算，因为 `.item()` 还会承担此前异步算子的等待时间。

### 4.3 姿态旋转重复构造常量

`echo/src/motion.py::Spin.rotate()` 每次调用都通过 NumPy 重建 `body_basis`，并重新创建设备上的 `basis`、`phase0` 和 `rate` 张量；网格 Chirp 内核又对质心和法向分别调用一次。实测缓存基底后，两次旋转由约 2.75 ms/脉冲降至约 1.07 ms/脉冲；把质心和法向堆叠成一次调用在当前实现上没有进一步可测收益，所以“缓存常量”是已验证优化，“强行合并两次旋转”不是当前优先项。

### 4.4 Run 与脉冲形成笛卡尔空循环

`_chirp_framework()` 对每个 Run 建立唯一 ADC 轴后，又遍历全部脉冲并调用候选区间搜索。当前作业因此执行 50 × 60000 = 3000000 次 Python 层迭代，而绝大多数跨 Run 脉冲与当前 ADC 窗没有交集。修正后的诊断脚本可测量该循环；仅 `searchsorted` 空跑在本机约为十几秒量级。该项不是 944 s 的唯一主因，但可无损消除，并会让后续批处理逻辑更清楚。

### 4.5 计算形状没有充分利用 GPU

即使把面元块增到 1280，一个脉冲也只有约 `51 × 1280` 个面元—样点组合，却触发数百个算子。GPU 1280/1024 仅比 CPU 快约 1.46 倍，说明当前形状仍受 Python 派发、张量构造、设备同步和小 kernel 启动限制。真正提高 GPU 利用率需要把多个脉冲组成批次，而不是继续微调单脉冲内部的小块。

## 5. 不改算法即可采用的配置策略

对于当前 1280 面元模型，可显式设置：

```json
{
  "facet_chunk_size": 1280,
  "fast_sample_chunk_size": 1024
}
```

`fast_sample_chunk_size=1024` 大于本例约 51 个候选样点，本质上表示一次处理完整候选集合；真正产生收益的主要是 `facet_chunk_size=1280`。更大的网格不能盲目沿用 1280，应根据显存以“候选样点数 × 面元块数 × 中间张量数量”估算并实测。GUI/手册不应笼统建议“运行慢就减小 chunk”，因为在显存足够时，过小 chunk 会显著增加 Chirp 路径的调用开销。

实验规模还有三个近似线性杠杆：`run_count`、`run_duration_s` 和 `prf_hz` 决定脉冲总数。减少它们会线性减少有效脉冲计算，但会同时改变观测覆盖、相干处理和周期反演能力，必须由实验设计决定，不能作为保持实验等价的代码优化。

## 6. 已实施修改

1. `Spin` 在初始化时只计算一次 ICRS 旋转基底，并按设备缓存 `phase0`、角速度和基底张量，避免每脉冲两次重复构造 NumPy 基底和设备常量。
2. 网格核在设备端跨全部面元块累计最大差分路径，每个脉冲结束后只执行一次 `.item()` 和路径上限校验，替代原来的每面元块一次同步。
3. `_chirp_framework()` 根据每个脉冲的保守时间支撑与当前 Run 的实际 ADC 轴范围筛选候选脉冲；筛选不只比较 `run_id`，因此仍保留特殊计划中跨 Run 的真实贡献。
4. `configs/chirp_mesh_target_test.json` 显式采用 `facet_chunk_size=1280` 和 `fast_sample_chunk_size=1024`。这只是当前 1280 面元测试模型的实测配置，不是所有网格的全局默认值。

## 7. 数值与性能验收

阶段 A 实施时的单元与物理回归覆盖旋转缓存、候选脉冲筛选、网格 Chirp 真实生成、路径时标伸缩和预览链路。阶段 B 收尾时已把关键回归纳入版本控制，并重新执行 `echo/tests/` 26 项和根目录 `tests/` 75 项，全部通过。真实计划 2 Run × 3 脉冲的逐脉冲参考与批处理路径比较中，`clean_iq`、`iq` 最大复数差均为 0。

真实计划比例的 50 Run × 24 脉冲 A/B 基准结果如下：

| 4.2 阶段 A 实现 | 最小稳定时间 | 单脉冲时间 |
|---|---:|---:|
| 默认 256/256 chunk | 10.61 s | 8.84 ms |
| 当前测试配置 1280/1024 | 4.58 s | 3.82 ms |

这组裁剪基准相对同一份阶段 A 代码表明，大 chunk 仍提供约 2.31 倍收益。阶段 A 当时没有用线性外推冒充完整结果；阶段 B 已使用完整 60000 脉冲配置实测计算与保存耗时 126.48 s，详见 Phase B 文档。

## 8. 诊断工具修正与限制

`echo/tmp/perf/profile_chirp2.py` 和相关脚本依赖 `echo/` 作为当前工作目录，直接从仓库根运行会因相对 `model_path` 找不到模型。`bench_chirp_perf.py` 的空循环基准原先只把每行起始索引当成 ADC 轴，导致“真正命中 0 次”的统计错误；4.2 工作区已把轴修正为每行全部 `fast_sample_count` 列的唯一全局索引。诊断脚本输出用于定位性能结构，不应作为正式实验结果或论文数据。
