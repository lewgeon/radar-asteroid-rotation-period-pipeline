# Chirp 网格回波本体系视线重排与分块默认值（阶段 C）

> 状态：已在 4.2 实现，完成完整 60000 脉冲交叉验证、实测，以及一轮独立复审后的修正（见第 7 节）。阶段 A、阶段 B 见同目录 `ECHO_SIMULATION_PERFORMANCE_PHASE_A.md`、`ECHO_SIMULATION_PERFORMANCE_PHASE_B.md`。

## 1. 范围与语义边界

本文只改变 `echo/src/echo.py::_generate_chirp_echo()` 所走网格 Chirp 回波路径的**计算组织**，不改变观测计划、物理模型与输出契约：

- 每个 Run 仍然只建立一条 Run 级连续 ADC 窗，按唯一的全局 ADC 整数索引 `q_values` 累加所有相关脉冲贡献，再按 `row_start_sample` 映射成二维 `[pulse, fast_time]` 脉冲保存行；
- `signal_echo_overlap` 为真时，同一 ADC 样点仍包含全部相交脉冲的贡献；`window_overlap` 只是保存行共享同一 Run 级信号与噪声的视图，不参与是否叠加的判断；
- `centroid_compensated`、`raw_baseband`、`per_pulse_linear`、`frozen` 的时延与相位公式不变；
- **包络相位与载波相位都在 `float64` 计算**，`complex64` 只出现在最终贡献与输出上（第 3 节记录了为什么放弃把包络降到 `float32`）。

## 2. 改动一：姿态旋转从面元侧搬到视线侧

### 2.1 符号与配置映射

| 符号 | 含义 | 来源 |
| --- | --- | --- |
| $c$ | 光速 | `src/echo.py` 常量 `C` |
| $k$ | 一个「脉冲 × ADC 样点」对 | `observation_info.row_start_sample` + `fast_sample_count` + Run 级 ADC 窗 |
| $f$ | 面元索引 | `model_path` 指向的网格 |
| $\mathbf x_f,\mathbf n_f$ | 本体系面元质心、单位法向 | 同上 |
| $M_k$ | 第 $k$ 对的姿态旋转矩阵 | `target.rotation_period_s`、`spin_pole_frame`/`spin_pole_icrs_deg`、`scatter_elapsed_s` 与 `scatter_receive_rate` |
| $\mathbf u_{\mathrm{tx},k},\mathbf u_{\mathrm{rx},k}$ | 收发视线单位向量 | `observation_info.tx_los_icrs` / `rx_los_icrs` |
| $\mathbf p_k$ | 双站远场投影向量 | $\mathbf p_k=\mathbf u_{\mathrm{tx},k}+\mathbf u_{\mathrm{rx},k}$ |
| $a_f$ | 归一化面元面积权重 | 面元面积与 `scattering` |
| $p_{\mathrm{tx}},p_{\mathrm{rx}}$ | 照明/接收余弦指数 | `scattering_power` |

### 2.2 推导

远场一阶展开把面元双站路径写成质心公共路径加投影项。旋转后的质心是 $M_k\mathbf x_f$，于是

$$
R_{f,k}\;\approx\;R_{\mathrm{tx},k}+R_{\mathrm{rx},k}+\mathbf p_k\cdot\left(M_k\mathbf x_f\right).
$$

姿态矩阵是正交矩阵，$M_k^{\mathsf T}M_k=I$，所以投影项可以整体改写：

$$
\mathbf p_k\cdot\left(M_k\mathbf x_f\right)=\mathbf x_f\cdot\left(M_k^{\mathsf T}\mathbf p_k\right).
$$

照明与接收余弦同理，用旋转后的法向 $M_k\mathbf n_f$ 表示：

$$
\cos\theta^{(f,k)}_{\mathrm{tx}}=\mathbf n_f\cdot\left(-M_k^{\mathsf T}\mathbf u_{\mathrm{tx},k}\right),\qquad
\cos\theta^{(f,k)}_{\mathrm{rx}}=\mathbf n_f\cdot\left(-M_k^{\mathsf T}\mathbf u_{\mathrm{rx},k}\right).
$$

结论：**姿态只作用在三个视线向量上**，面元侧的 $\mathbf x_f$ 与 $\mathbf n_f$ 始终是本体系常量。代码新增 `Spin.rotate_inverse()` 计算 $M_k^{\mathsf T}\mathbf u$，面元侧只剩三个点积。

### 2.3 为什么更快

改前每个「脉冲 × 样点」都要旋转整张网格：物化 $(K,F,3)$ 的 `float64` 质心与法向张量，再对每个面元块做一次 $3\times3$ 矩阵乘法，这就是 profiler 里 `aten::mm` / `aten::bmm` 占 CUDA 时间约 70% 的原因。改后姿态旋转次数从「样点对 × 面元」降到「样点对 × 3 个视线向量」，面元侧退化成三个规整的 $(K,3)\times(3,F)$ GEMM。

同一块 10.49 M 面元-样点（$K=8192$、$F=1280$）的实测对比：

| 项 | 改前 | 改后 |
| --- | ---: | ---: |
| 姿态旋转 | 144.6 ms | 0.45 ms（只需旋转视线） |
| 差分路径点积 | 35.5 ms（`einsum("kfc,kc->kf")`） | 1.0 ms（GEMM） |

这是等价的代数重排，不是近似：改前算 $(M\mathbf x)\cdot\mathbf u$，改后算 $\mathbf x\cdot(M^{\mathsf T}\mathbf u)$，实数域完全相同，浮点上只差乘积的结合顺序。

## 3. 已评估并放弃：把 Chirp 包络降到 float32

包络相位是 $\pi k\,t^2$，其中 $k=\texttt{bandwidth\_hz}/\texttt{pulse\_width\_s}$，$t$ 是脉内局部时间，峰值相位为

$$
\phi_{\max}=\pi\,\frac{B}{T}\,T^{2}=\pi\,B\,T=\pi\cdot\mathrm{TBP}.
$$

配置只约束 `fast_sample_rate_hz > bandwidth_hz`，**没有任何地方约束时间带宽积** $B\cdot T$。用 float32 计算相位时，误差随 TBP 线性增长：

| B (Hz) | T (s) | TBP | 峰值相位 (rad) | float32 包络最大误差 | 先模 $2\pi$ 再转 float32 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1e3 | 1e-2 | 10 | 3.1e1 | 0.0000 | 2.98e-07 |
| 1e6 | 1e-3 | 1e3 | 3.1e3 | 0.0006 | 2.98e-07 |
| 1e6 | 1.6e-2 | 1.6e4 | 5.0e4 | 0.0102 | 2.98e-07 |
| 1e8 | 1e-2 | 1e6 | 3.1e6 | 0.5375 | 2.67e-07 |
| 1e9 | 1e-2 | 1e7 | 3.1e7 | 2.0000（逐点反相） | 2.27e-07 |

在**目标规模**（完整 60000 脉冲作业）上，收益只有 2.5%；裁剪计划上曾测到 12%，属于小规模上固定开销占比不同造成的失真：

| 包络写法 | 完整作业耗时 | 相对 fp64 | 与 fp64 的 `clean_iq` 最大差 |
| --- | ---: | ---: | ---: |
| **float64（当前实现）** | 24.73 s | 1.000× | 0 |
| float32 相位 | 24.13 s | 1.025× | 7.92e-08 |
| 先模 $2\pi$ 再 float32 | 23.76 s | 1.041× | 3.33e-08 |

结论：为了 2.5% 引入一个依赖 $B\cdot T$、且没有任何门限的精度策略不值得，**默认路径保持 float64**。若将来确实需要这一点收益，应采用"float64 算相位 → 对 $2\pi$ 取模 → float32 取指数"的写法（误差与 TBP 无关，恒在 3e-7 量级），并同时提交上表与一个大 TBP 的边界用例。

## 4. 改动二：分块默认值与参数校验

阶段 B 之后一个块已经是「样点对 × 面元」，但默认值仍是 `facet_chunk_size=256`、`fast_sample_chunk_size=256`，一块只有 6.5 万项，远小于设备高效区间。新增 `_resolve_chirp_chunks()`：

1. `facet_chunk_size` 未显式给出时取 $\min(F,\;1280)$，即小网格一次算完所有面元；
2. `fast_sample_chunk_size` 未显式给出时取 $\mathrm{clamp}\left(\lfloor 2\times10^6 / \texttt{facet}\rfloor,\;64,\;4096\right)$，使一块约含 $2\times10^6$ 个面元-样点，单个 `float64` 中间量约 16 MB；
3. 显式配置永远优先。

分块、批量都是**元素计数**，必须是正整数。`int(1.9)` 会静默变成 1，把一次分块计算变成逐元素循环，因此新增 `_positive_integer()`：非整数（`1.9`）、非数字（`"many"`）、非正数（`0`、`-1`）都报错，而表示整数的字符串（`"64"`）仍被接受，与 GUI 的整数校验口径一致。

此外，照明/接收权重 `cos^n` 在 $n=1$ 时直接用余弦值、$n=0$ 时直接给 1，跳过 `pow`。这是纯代数等价（`x**1.0` 在 IEEE 下即 `x`），对应配置 `scattering_power = [1, 1]` 的常见情形。

对本例 1280 面元模型，默认解析结果是面元块 1280、样点对块 1562。CUDA OOM 的两级退避仍然保留（先缩样点对块，再缩面元块，最后缩脉冲批量），元数据新增：

| 字段 | 含义 |
| --- | --- |
| `chirp_pair_chunk_size` / `chirp_facet_chunk_size` | 本次作业解析后的分块 |
| `facet_geometry_frame` | 面元几何所处参考系，当前为 `body_fixed_look_vectors` |
| `chirp_pulse_batch_size_min_effective` | **实际使用过的最小批量**（不再只是请求值） |
| `chirp_batch_accumulation` | 归并方式，仍为脉冲主序确定性累加 |

## 5. 数值验收

### 5.1 与改前实现逐点对比

改前整包（用 `git archive HEAD` 从 echo 子模块取出的阶段 A 之前实现）与当前实现，在相同计划、配置与随机种子下逐点对比：

| 场景 | `clean_iq` 最大绝对差 | 相对峰值 | 改前 → 改后耗时 |
| --- | ---: | ---: | ---: |
| 小样本计划，float64 网格 | $5.93\times10^{-17}$ | $3.85\times10^{-16}$ | 1.19 s → 0.73 s |
| 4 Run × 100 脉冲，`centroid_compensated`，float32 | $3.07\times10^{-8}$ | $1.99\times10^{-7}$ | 5.07 s → 0.92 s |
| 4 Run × 100 脉冲，`raw_baseband`，float32 | $3.07\times10^{-8}$ | $1.99\times10^{-7}$ | 5.37 s → 0.82 s |
| 保存行窗口重叠计划（`window_overlap` 为真） | $3.07\times10^{-8}$ | $1.99\times10^{-7}$ | 1.90 s → 0.91 s |

所有场景的 `valid`、`row_start_sample`、`signal_echo_overlap`、`window_overlap` 完全相同，`max_actual_bistatic_path_offset_m` 逐位相同。剩余偏差只来自本体系重排导致的乘积结合顺序变化，量级为 `complex64` 的 2 个 ULP。

**为什么"等价重排"仍会有末位差异**：$(M\mathbf x)\cdot\mathbf u$ 与 $\mathbf x\cdot(M^{\mathsf T}\mathbf u)$ 在实数域严格相等，但浮点上经过的舍入步骤不同——前者先算 $M\mathbf x$（每个分量一次舍入）再点乘，后者先算 $M^{\mathsf T}\mathbf u$ 再点乘。实测单个面元的差异：float64 输入时 $5.7\times10^{-14}$（相对 $2.5\times10^{-16}$），float32 输入时 $1.8\times10^{-5}$（相对 $8.2\times10^{-8}$），即都在输入精度的最后一个 ULP 量级；再叠加 1280 个面元的 `complex64` 复求和（每个面元贡献仅差 1e-7 rad 量级时，和值就可差 $1.3\times10^{-6}$），最终落到 $3.3\times10^{-8}$ 的绝对差。这类差异与"改动面元分块大小"产生的差异同量级（后者实测也是 $3.07\times10^{-8}$），因此它是输出精度的量化噪声，不是模型误差。若需要逐位一致，只能保留"旋转网格"的写法，代价是慢 5 倍以上。

完整作业交叉验证（同会话，先跑改前整包、再跑当前实现，逐点比较整份 `clean_iq`）：

| 实现 | 计算耗时 | `clean_iq` 最大绝对差 | 相对峰值 | 不一致元素占比 | 最大单点相对差 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 阶段 A 之前整包 | 670.9 s | 基准 | — | — | — |
| 当前实现（默认分块） | 27.9 s | $3.33\times10^{-8}$ | $2.16\times10^{-7}$ | 20.97% | $2.57\times10^{-7}$ |

### 5.2 自动化测试

`echo/tests/` 35 项全部通过，根目录 `tests/` 75 项全部通过。本阶段新增或加强的用例：

- **四组 golden 值**（`test_body_frame_kernel_matches_pre_body_frame_values`）：倾斜自转轴 + 偏轴面元，覆盖 `centroid_compensated`/`raw_baseband` × `per_pulse_linear`/`frozen`，直接与改动前实现产生的 `clean_iq` 比较（`float64`，`atol=1e-12`）。
- **收发幂次归属 golden**（`test_bistatic_kernel_assigns_tx_and_rx_powers_correctly`）：双站夹具（`rx_icrs` 与 `tx_icrs` 不同方向）+ 非对称 `scattering_power=(2.0, 0.5)`。单站夹具下照明与接收余弦相等，两个指数可交换，因此内核里把 `-tx` 与 `-rx` 弄反也不会被发现；这条用例是唯一能把"照明用 `p_tx`、接收用 `p_rx`"钉住的检查。已用变异测试验证有效性：临时把 `body_look_vectors` 里的 `-tx_pairs` 与 `-rx_pairs` 对调，该用例立即失败（2 个 subTest），恢复后通过。
- **夹具非退化断言**（`test_fixture_separates_the_branches_it_claims_to_cover`、`test_bistatic_fixture_separates_the_two_scattering_powers`）：断言四个"参考系 × 运动模型"组合的结果确实互不相同，且交换两个散射幂次会改变结果。初版夹具是 z=0 平面上质心在原点、法向沿自转轴的三角形，且双站路径恰好是 2,000,000 个整载波周期、公共路径率为零，四个组合的结果逐位相同——即"两参考系 × 两运动模型"其实只测了一个格子。
- **CLI 冒烟测试**（`test_cli_smoke.py`）：用真实子进程对 CW 与 chirp 各跑一次 `simulate_echo.py`，断言退出码为 0、`echo.npz` 维数正确、`summary.json` 与之一致。
- `Spin.rotate_inverse()` 与 `Spin.rotate()` 的伴随关系；`_resolve_chirp_chunks()` 的默认值、显式值优先级与整数校验；`_scattering_weight()` 与普通幂运算一致。

## 6. 性能验收

环境：NVIDIA GeForce RTX 2060 Max-Q、PyTorch 2.3.1、CUDA 11.8、`compute.dtype=float32`、1280 面元。完整作业为 `runs/chirp_mesh_target_test` 的 50 Run × 1200 脉冲计划（60000 脉冲 × 153 个快时间样点，9,179,950 个有效保存样点，约 3.92 G 面元-样点）。

| 版本 | 计算耗时 | 同会话加速比 |
| --- | ---: | ---: |
| 阶段 A 之前（交叉验证会话） | 670.9 s | 1.0× |
| **阶段 C，默认（批量 32，分块自动 1562/1280）** | **27.9 s** | **24.1×** |
| 阶段 A 之前（另一会话） | 721.7 s | 1.0× |
| 阶段 C，默认（同一会话） | 25.5 s | 28.3× |
| 阶段 C，批量 256，1280/8192（同一会话） | 18.2 s | 39.6× |
| 阶段 B，默认分块（批量 32，256/256，历史记录） | 171.4 s | 4.2× |
| 阶段 B，调优分块（批量 256，1280/8192，历史记录） | 109.2 s | 6.6× |

两种阶段 C 配置的 `clean_iq` 互相逐位相同，峰值设备内存分别为 215 MB 与 1034 MB。表里保留了两次独立会话，是因为绝对耗时本身不稳定（见下段），只有同一会话内的比值才有意义。

关于基线：`runs/chirp_mesh_target_test/echo/summary.json` 是会被重跑覆盖的产物，它在 2026-09-16 15:00:57 记录 761.5 s、在 15:29:56 被同一作业的另一次运行覆盖为 944.06 s。同一作业在同机上出现过 670.9 / 721.7 / 761.5 / 944.06 四个值，说明绝对耗时受 GPU 热状态影响可达 30%，**加速比只在同会话 A/B 之间比较**。

设备调用次数（40 脉冲裁剪计划，profiler 统计 CUDA kernel 调用）：阶段 B 在默认 256/256 分块下约 344 次/脉冲；阶段 C 批量为 1 时约 191 次/脉冲，批量 32 时约 20 次/脉冲。`aten::mm` / `aten::bmm`（姿态旋转）已从耗时榜首消失，剩余 CPU 时间主要花在每批一次的贡献回传上。

## 7. 交付后复审与修正

一轮独立复审（外部模型，针对本阶段初版）指出以下问题，已全部处理：

| 复审发现 | 处理 |
| --- | --- |
| float32 包络对合法配置不安全（TBP 无上界） | 默认改回 float64，评估数据写入第 3 节；给出将来若要用 fp32 时的正确写法与边界用例 |
| CW 入口在保存后崩溃（`iq.shape[1]` 对一维数组越界），而交付说明称"CLI 正常" | `simulate_echo.py` 的摘要按 `iq.ndim` 分支；新增 CW/chirp 双入口 CLI 冒烟测试。该崩溃来自上一轮加入的摘要代码，本轮验收只跑了 chirp 入口，未能发现 |
| 性能证据不可复现（诊断脚本目录被误删、基线引用会被覆盖的产物） | 恢复脚本；文档改用同会话基线并记录产物被覆盖的时间线；建立证据分层策略（`docs/4.2/VERIFICATION_POLICY.md`） |
| 测试项数记录为"26 项通过"（实为 35 项，其中 4 项在受限环境失败） | 修复那 4 项的环境相关问题（`tempfile.mkdtemp` 在 Windows 受限令牌下创建的目录不可写，改用仓库内 `tmp/` 下的 mkdir 目录），现在 35 项在各环境均通过 |
| 测试盲点：golden 只覆盖一组组合、`raw_baseband`/`frozen` 夹具退化、无 CLI 用例、测试文件未被 Git 跟踪 | 补四组 golden + 非退化断言 + CLI 冒烟；`echo/tests/` 与 `echo/scripts/` 纳入跟踪，并用 `.gitattributes` 的 `tests/** export-ignore` 把测试排除在发布归档之外 |
| 元数据 `chirp_pulse_batch_size_min_effective` 在候选脉冲少于请求批量时仍记请求值 | 改为记录实际使用过的最小批量 |
| `1.9` 等非整数分块被 `int()` 静默截断（文档却称"非正整数报错"） | 新增 `_positive_integer()`，非整数报错；测试覆盖 `1.9`、`"many"`、`0`、`-1` 与整数串 `"64"` |
| 文档称"中间量保持 float64"与包络转 float32 矛盾 | 随包络改回 float64 一并消除，并在第 1 节明确写出 |

尚未处理（保留为后续可选项）：`Spin` 的缓存不随 `period_s`/初相位/自转轴变更而失效（当前没有代码路径修改已构造的 `Spin`）、`torch.cuda.reset_peak_memory_stats` 重置设备级统计（仅在多进程共享 GPU 时有影响）。两项都是潜在风险而非现存缺陷，处理方式见第 8 节。

## 8. 后续可选项

1. **面元侧点乘改用 `float32`**。网格本身是 `float32`，本体系视线若仍用 `float64`，点积会按类型提升为 `float64`；改为 `float32` 后实测点积吞吐由 0.30 G/s 升到 3.58 G/s。代价是相对路径误差约 $10^{-5}$ m，对应 1 MHz 载波相位误差约 $10^{-4}$ rad。属于需要显式敏感性核对的精度取舍，未纳入本阶段。
2. **`Spin` 缓存失效保护**。`Spin` 是可变 dataclass，`_basis_icrs` 在构造时算一次，按设备的 `(phase0, rate, basis)` 张量缓存在 `_tensor_cache` 里，构造之后修改 `period_s`/`initial_phase_rad`/`axis_icrs` 不会让缓存失效。实测：构造后把 `period_s` 从 300 s 改成 100 s 再调用 `rotate`，返回值与改前**逐位相同**（100 s 与 300 s 的真实姿态差为 0.75），且不报任何错；修改 `axis_icrs` 同样继续使用旧基底。当前仓库只在 `echo/src/echo.py` 与测试里各构造一次 `Spin`，没有任何代码路径修改已构造的实例，所以这是潜在风险而非现存缺陷。修法：把缓存键改为包含姿态参数（例如 `functools.lru_cache` 包一个纯函数，键为 `period_s, initial_phase_rad, axis_icrs.tobytes(), device`），或把 `Spin` 改为不可变对象。改与不改对当前结果没有影响。
3. **峰值显存统计改为进程内统计**。`_generate_chirp_echo` 开头的 `torch.cuda.reset_peak_memory_stats(device)` 重置的是**设备级**峰值计数，`max_memory_allocated` 由 PyTorch 缓存分配器按进程维护。单个进程只跑一个回波作业时它正好表示"本次作业的峰值"；同一进程里并发跑多个作业（线程/协程/notebook）时，后启动的作业会把先启动的峰值清零，两个作业报告的 `chirp_peak_device_memory_bytes` 都会失真。**不同进程之间互不影响**（分配器统计不跨进程），而当前 pipeline 与 GUI 都是每个阶段起一个子进程，所以现在没有实际影响；它影响的只是元数据准确性，不影响任何物理量或结果。修法：去掉重置、改成记录进程启动以来的峰值并在文档里说明，或改为按作业采样 `memory_allocated()` 求最大值。
4. **`torch.compile` / CUDA Graph**：批处理与本体系重排之后，每次设备调用的张量已达百万量级，图捕获或编译缓存带来的收益有限，暂不建议引入。

按当前需求（回波生成已在 20 秒量级）**第 1、4 项明确不做**。第 2、3 项经确认**本轮暂不修改**：两者都不影响任何现有结果（前者当前没有触发路径，后者只影响一个元数据的语义），改动属于健壮性整理，留待下次触碰 `motion.py` 或 GPU 元数据时一并处理；届时若要处理，按上面给出的修法即可，并有本节记录的行为分析作为验收依据。

## 9. 本阶段改动清单与复核方法

### 9.1 改动清单

| 文件 | 改动 |
| --- | --- |
| `echo/src/motion.py` | 新增 `_pose_tensors()`（按设备缓存姿态常量）与 `rotate_inverse()`（把姿态作用于视线向量） |
| `echo/src/echo.py` | `_chirp_complex_terms()` 保持包络与载波都在 float64；新增 `_scattering_weight()`、`_positive_integer()`、`_resolve_chirp_chunks()` 与分块常量；`_generate_chirp_echo()` 重构为 `body_look_vectors()` / `accumulate_pairs()` / `check_path_limit()` 三个共享闭包（逐脉冲参考路径与批处理路径共用同一份面元数学）；新增分块与参考系元数据；`chirp_pulse_batch_size_min_effective` 改为记录实际使用过的最小批量 |
| `echo/simulate_echo.py` | 结果摘要按 `iq.ndim` 分支：CW 输出接收采样点数与采样率，chirp 输出脉冲数、快时间样点数等 |
| `echo/tests/scratch.py` | 新增：测试用可写临时目录（替代在受限令牌下不可写的 `tempfile.mkdtemp`） |
| `echo/tests/test_cli_smoke.py` | 新增：CW 与 chirp 各跑一次真实 `simulate_echo.py` 子进程并断言退出码为 0 |
| `echo/tests/test_chirp_batching.py` | 夹具改为非退化（倾斜姿态 + 非整周期载波 + 非零路径率）；新增四组 golden 值用例、双站非对称幂次 golden 与两条"夹具非退化/可区分"守护断言；批量/参考路径对比同时覆盖轴对齐与倾斜网格；新增 `_bistatic_observation()` 与 `powers` 配置参数 |
| `echo/tests/test_echo.py` | 新增 `rotate_inverse` 伴随关系、分块解析与整数校验、散射权重特例用例 |
| `echo/tests/test_dataset.py`、`test_geometry.py`、`test_light_time.py` | 临时目录改用 `scratch_directory`，使用例在受限环境下也能通过 |
| `echo/.gitignore` | 取消忽略 `tests/`、`scripts/`（只保留忽略 `__pycache__`） |
| `echo/.gitattributes` | 新增：`tests/** export-ignore` |
| `echo/README.md`、`echo/README_EN.md` | 更新分块默认值解析规则与本体系换算说明 |
| `echo/docs/implementation_and_timing.md` | 新增"姿态进入公式的位置"一节，给出 $(M\mathbf x)\cdot\mathbf u=\mathbf x\cdot(M^{\mathsf T}\mathbf u)$ 的推导 |
| `echo/docs/configuration_and_visualization.md` | 补充 `chunk_size`/`facet_chunk_size`/`fast_sample_chunk_size`/`pulse_batch_size` 的默认值与语义 |
| `docs/4.2/GUI_USER_MANUAL.md` | 分块与批量一行的默认值说明改为与代码一致 |
| `docs/4.2/VERIFICATION_POLICY.md`、`docs/4.2/README.md` | 新增验证与证据留存策略并登记入口 |
| `docs/4.2/vs_4.1/changes/ECHO_SIMULATION_PERFORMANCE_PHASE_C.md` | 本文件 |
| `.gitattributes`（仓库根） | 新增：`docs/4.2/vs_4.1/** export-ignore` |
| 仓库外：`C:\Users\35168\.codex\AGENTS.md` | 追加"变更验证纪律（通用）"一节（全局常驻规则，任何项目生效） |
| 仓库外：`C:\Users\35168\.agents\skills\change-verification-discipline\SKILL.md` | 新增用户级技能：验证流程、检查清单、对抗性审查提示词模板 |

本阶段**未改动**：`echo/src/config_normalize.py`、`echo/src/point_target.py`、`echo/src/mesh.py`、`echo/src/dataset.py`、`echo/src/geometry.py`（其中前两个的改动属于上一轮），以及 `observation/`、`inversion/`、`pipeline.py`、`rotation_gui/`（观察窗与 GUI 的改动属于上一轮，不在本阶段范围）。

### 9.2 复核方法

```powershell
# 单元测试（echo 子模块 35 项；仓库根 75 项）
cd echo; python -m unittest discover -s tests
cd ..; python -m pytest tests -q

# 完整作业耗时（默认分块 / 调优分块，同会话取最小值）
cd echo; python tmp/perf/bench_full_plan.py

# 与改前整包做完整作业交叉验证（约 12 分钟，其中改前实现约 11 分钟）
git -C . archive --format=zip HEAD -o tmp\old\head.zip
Expand-Archive tmp\old\head.zip -DestinationPath tmp\old\pkg -Force
$env:PYTHONPATH="<repo>\echo\tmp\old\pkg"; python tmp\perf\full_plan_crosscheck.py old
$env:PYTHONPATH="<repo>\echo";             python tmp\perf\full_plan_crosscheck.py new
# 然后逐点比较 tmp\perf\out\full_old_clean.npy 与 full_new_clean.npy

# 包络精度写法对比（完整作业三种写法 + TBP 扫描表）
python tmp/perf/bench_envelope.py --plan ..\runs\chirp_mesh_target_test\observation_info.npz --repeat 2

# 裁剪计划上的逐点对比（4 Run × 100 脉冲、重叠保存行计划、小样本计划）
python tmp/perf/build_cmp_plans.py
# 改前整包：在 tmp/old/pkg 目录下 PYTHONPATH 指向该包，运行 run_echo_case.py；
# 当前实现：PYTHONPATH 指向 echo，运行同样的用例；最后 compare_cases.py 汇总

# 剩余算子瓶颈
python tmp/perf/bench_remaining.py
```

`tmp/` 是 git 忽略目录，这些脚本按证据分层策略不进入发布归档；复核时如果需要，可直接按上表重建。脚本清单：`bench_full_plan.py`（复跑完整作业）、`full_plan_crosscheck.py`（与改前整包交叉验证）、`bench_envelope.py`（包络精度写法对比）、`bench_remaining.py`（剩余算子瓶颈）、`build_cmp_plans.py`/`run_echo_case.py`/`compare_cases.py`（裁剪计划逐点对比）、`golden_case.py` 与 `golden_bistatic.py`（重新生成两组 golden 值）、`demo_questions.py`（重排末位差异、整数校验、OOM 退避的现场演示）。
