# 自转周期测量 GUI 用户手册

[English README](../README_EN.md) | [项目首页](../README.md)

本文面向第一次使用本项目 GUI 的用户，说明项目原理、界面操作、参数含义、配置注意事项和常见问题。当前 GUI 入口为 `pyside_gui.py`，旧版 `gui_app.py` 仅作为回退入口保留。

## 1. 项目原理概览

本项目用于构造一条“小行星雷达回波仿真到自转周期反演”的端到端流水线。流水线由三个相互独立的子模块组成，模块之间通过文件交换数据：

1. `observation/`：根据目标、发射站、接收站和接收时间轴，解算三事件光行时几何，输出 `observation_info.npz`。
2. `echo/`：读取观测几何和目标形状模型，计算旋转小行星的复基带 I/Q 回波，输出 `echo/echo.npz`。
3. `inversion/`：读取仿真回波，计算动态频谱和特征序列，用 Lomb-Scargle 周期搜索估计自转周期，输出 `inversion/summary.json`、`best_summary.json` 和图像。

GUI 不改变流水线物理模型。它负责编辑配置、逐阶段启动脚本、显示进度、记录日志、管理运行历史和预览结果。运行前 GUI 会在 `runs/<实验名>/configs/` 下生成本次实际使用的配置快照，便于复查。

## 2. 启动方式

推荐在 Conda 的 `pytorch` 环境中启动：

```powershell
conda activate pytorch
python pyside_gui.py
```

旧版 Tkinter 回退入口：

```powershell
conda activate pytorch
python gui_app.py
```

如果 PySide6 的 Qt WebEngine 组件完整可用，主 GUI 会在结果区域内嵌 Plotly 交互图。如果缺少 WebEngine 辅助文件，GUI 会自动退回静态图预览和外部浏览器打开交互图。

## 3. 界面区域说明

窗口顶部是配置和运行设置：

- `配置文件`：要载入的顶层流水线 JSON。默认是 `configs/pipeline_example.json`。
- `打开`：从文件对话框选择配置文件。
- `载入`：按输入框路径重新读取配置。
- `实验名`：输出目录名。结果写到 `runs/<实验名>/`。
- `输出目录`：运行结果根目录。相对路径会按项目根目录解析。
- `Python`：用于执行各子模块脚本的 Python 解释器。通常保持为当前 Conda 环境解释器。

左侧是阶段和历史：

- `流水线阶段`：显示 `观测解算`、`回波仿真`、`周期反演` 的当前状态。
- `执行下一步`：执行当前阶段。成功后自动切换到下一阶段。
- `中止`：终止当前阶段的子进程树。适合发现参数设置不合适或运行时间过长时使用。
- `保存参数`：把当前界面参数保存到 `.gui_state/pipeline_gui_state.json`。
- `另存 JSON`：把当前参数另存为新的顶层流水线配置。
- 历史表：显示最近运行阶段、时间和状态。

中间是阶段参数编辑区。点击左侧阶段按钮可以切换当前编辑的模块参数。每次执行阶段前，GUI 会把当前页面字段同步回配置。

参数区使用固定语义分栏，各卡片只占用自身内容需要的高度，不再把同一行的短卡片
拉高。观测页常规窗口中，左栏从上到下为“目标参数、发射站、接收站”，右栏为
“接收设置、星历查询、求解器”；勾选单基站后只隐藏接收站，其他卡片不换栏或重排。
配置中没有星历查询字段时，不显示空的星历卡片。

参数区可用逻辑宽度达到约 1320 px 时启用宽屏方案：观测页按“目标／测站／观测与求解”
三栏组织；回波页按“模型与计算／目标与散射热点／雷达波形”三栏组织。
反演页保留两组参数，并把更多垂直空间让给结果预览；宽屏结果预览比日志更宽。
布局依据实际可用宽度而非最大化按钮状态，因此高 DPI 缩放下仍优先保证可读性。
极窄参数区会回退单列。窗口缩放不会重建输入框或提交尚未输入完的数值。
需要更多编辑空间时，可拖动参数与日志/预览之间的分隔条；同一阶段、同一宽窄布局
下保留手动调整，仅跨布局断点或切换阶段时重新分配空间。

卡片标题使用浅蓝标题带与深蓝加粗字；“形状模型、散射指数、信噪比”等同级字段
使用一致的字体，自转轴作为多个字段的二级分组保留分隔线。经纬度/赤经赤纬并排显示；可能包含大数值的三维位置与速度按
x、y、z 分行显示，保证输入宽度。数值与单位共用等高边框，可选单位以右侧箭头
区分，固定单位沿用相同配色。单位选择仍表示当前输入数值的单位，保存时换算为标准单位。

滚动条采用深色滑块与浅色轨道，勾选框选中时为蓝底白勾，未选中时为白底深边框。
下拉列表按控件位置展开，不再以当前选项作为弹出位置锚点；只有屏幕底部空间不足时
才向上展开。Windows 下优先使用原生样式及其展开动画，系统不支持该效果时直接显示列表。

回波页将“载频”和“波形参数”合为“雷达与波形”卡片；随机种子和分块大小
（配置中存在时）移到“计算设置”。反演页分为“时频分析”和“周期搜索”。
这些都是显示分组，另存 JSON 时仍使用原有字段路径，不新增 `signal` 等业务配置段。

底部是日志、结果预览和进度：

- `执行日志`：显示命令、配置快照路径、进度摘要、错误信息和最终反演结果。
- `结果预览`：显示当前阶段的静态图或 Plotly 交互图。
- `打开结果`：打开当前阶段的主要输出文件。
- `打开 3D/交互图`：在系统浏览器中打开 Plotly HTML。
- 底部进度条：显示当前子模块的粗略百分比和正在执行的子步骤。

## 4. 推荐使用流程

第一次运行建议先用示例配置跑通：

1. 启动 `python pyside_gui.py`。
2. 保持默认配置和实验名，点击 `执行下一步`。
3. 等待 `观测解算` 完成，查看视线/距离预览。
4. 再点击 `执行下一步`，运行 `回波仿真`，查看 I/Q、幅度和相位预览。
5. 再点击 `执行下一步`，运行 `周期反演`，查看周期图和日志中的最终结果。
6. 在 `runs/<实验名>/configs/` 中检查 `*.generated.json`，确认本次实际参数。

正式实验建议复制示例配置后再修改：

```powershell
Copy-Item configs\pipeline_example.json configs\my_experiment.json
python pyside_gui.py
```

在 GUI 中载入 `configs\my_experiment.json`，修改参数后使用 `另存 JSON` 保存版本。不要直接改 `runs/<实验名>/configs/*.generated.json`，这些是每次运行生成的快照。

## 5. 顶层配置结构

顶层 JSON 只有三个业务段：

```json
{
  "observation": {},
  "echo": {},
  "inversion": {}
}
```

`observation_info.npz`、`echo.npz`、`summary.json` 等中间路径不需要手动填写。GUI 和 `pipeline.py` 会自动生成并注入下游模块。

## 6. 观测解算参数

`observation` 决定接收时间轴、目标状态、发射站/接收站状态和三事件光行时求解设置。

### 6.1 `target`

`target` 表示小行星质心状态。

| 字段 | 含义 | 注意事项 |
| --- | --- | --- |
| `id` | 目标编号或自定义标识 | `horizons_vectors` 模式下是 Horizons 查询目标编号。 |
| `name` | 显示和元数据名称 | 可读即可。 |
| `state` | 状态模型 | 目标建议使用 `linear`、`static` 或 `horizons_vectors`。 |
| `position_m` | 静态位置，单位 m | `state=static` 时使用。 |
| `position0_m` | 初始位置，单位 m | `state=linear` 时使用。 |
| `velocity_m_s` | 匀速速度，单位 m/s | `state=linear` 时使用。 |
| `object_type` | Horizons 目标类型 | 可为 `null` 或 `smallbody`。 |

常用选择：

- `static`：目标固定不动，适合最小测试。
- `linear`：目标匀速直线运动，适合离线仿真和快速验证。
- `horizons_vectors`：从 JPL Horizons 查询目标相对参考位置的星历表，再本地插值，适合真实天体实验。

### 6.2 `transmitter` 和 `receiver`

发射站和接收站支持：

| `state` | 含义 | 需要字段 |
| --- | --- | --- |
| `static` | 用户直接给 Cartesian 坐标 | `position_m` |
| `linear` | 匀速 Cartesian 状态 | `position0_m`、`velocity_m_s` |
| `geodetic_fixed` | 固定经纬高转 ECEF 近似 | `lat_deg`、`lon_deg`、`height_m` |
| `astropy_geodetic` | Astropy 按时间计算 GCRS 测站位置 | `lat_deg`、`lon_deg`、`height_m` |

真实地面测站优先使用 `astropy_geodetic`。如果目标使用 `horizons_vectors` 且测站使用 `astropy_geodetic`，建议保持 `ephemeris.refplane="earth"`，避免把不同参考平面的向量混用。

`linear` 发射站/接收站用于离线仿真、平台运动或算法验证。它并不表示真实地面站的高精度运动模型；真实固定地面站仍建议使用 `astropy_geodetic`。

观测参数页顶部提供“单基站观测：接收站沿用发射站参数”选项。勾选后接收站分组会隐藏，保存或执行前 GUI 会把发射站配置深拷贝为接收站配置。取消勾选后接收站分组重新出现，可以单独配置双/多站几何。

### 6.3 `receive`

| 字段 | 含义 | 注意事项 |
| --- | --- | --- |
| `start_utc` | 接收起始 UTC | 使用 ISO 格式，例如 `2026-01-01T00:00:00.000`。 |
| `duration_s` | 接收时长，单位 s | 样本数约为 `duration_s * sample_rate_hz`。 |
| `sample_rate_hz` | 接收采样率，单位 Hz | 影响观测几何样本数、回波样本数和反演频谱。 |

采样点为 `np.arange(N) / sample_rate_hz`，最后一个样本通常是 `(N-1)/sample_rate_hz`，不严格等于 `duration_s`。

### 6.4 `ephemeris`

仅当使用 `horizons_vectors` 或 `astropy_geodetic` 等真实星历/测站模式时才重要。

| 字段 | 含义 | 建议 |
| --- | --- | --- |
| `location` | Horizons 参考中心 | 常用 `@399` 表示地心。 |
| `refplane` | Horizons 参考平面 | 当前混合 Astropy 测站时建议用 `earth`。 |
| `padding_s` | 星历查询前后额外覆盖时间 | 要覆盖光行时提前量；不足会导致插值越界。 |
| `query_step_s` | Horizons 状态表间隔 | 越小插值误差越小，查询越多。短时窗口可从 60-300 s 开始。 |
| `query_mode` | 查询模式 | `auto` 通常最稳；可强制 `range` 或 `list`。 |
| `query_chunk_size` | 列表查询每块 epoch 数 | 网络/服务失败时可调小。 |
| `min_query_chunk_size` | 自动拆分下限 | 不建议小于 1。 |
| `query_retries` | 可重试 HTTP 错误重试次数 | 网络不稳定时可增大。 |
| `cache` | 是否使用 astroquery 缓存 | 通常保持 `true`。 |

### 6.5 `solver`

| 字段 | 含义 | 建议 |
| --- | --- | --- |
| `tolerance_s` | 光行时固定点迭代收敛阈值，单位 s | 示例可用 `1e-9`；真实星历链路常用 `1e-7` 到 `1e-9` 做敏感性检查。 |
| `max_iter` | 最大迭代次数 | 32 通常足够。 |

`tolerance_s=1e-9` 对应光程量级约 0.3 m。是否需要这么严取决于你的雷达频率、目标距离、星历精度和后续反演要求。

如果达到 `max_iter` 后仍未满足 `tolerance_s`，程序会报错并停止当前阶段，不会悄悄使用最后一次迭代值继续执行。错误信息会包含最大残差 `max_delta_s`。如果虽然收敛但迭代次数接近上限，GUI 日志会用警告颜色提示，建议检查初始几何、星历覆盖范围和阈值设置。

## 7. 回波仿真参数

`echo` 根据观测几何、形状模型、散射设置和雷达波形生成复基带 I/Q。

GUI 中回波仿真参数按以下分区显示。

### 7.1 模型与散射

| 界面标签 | 配置字段 | 含义 | 注意事项 |
| --- | --- | --- | --- |
| 形状模型 | `model_path` | OBJ 形状模型路径 | 相对路径按 `echo/` 模块目录解析。 |
| 散射指数 | `scattering_power` | 发射照明和接收方向的余弦幂指数 | GUI 拆成“发射照明”和“接收散射”两个输入框；保存时仍写入标准 JSON 数组。 |
| 信噪比 | `snr_db` | 复高斯噪声 SNR，单位 dB | 设为 `null` 表示不加噪声。 |

### 7.2 计算设置

| 界面标签 | 配置字段 | 含义 | 注意事项 |
| --- | --- | --- | --- |
| 计算设备 | `device` | 回波面元求和使用的设备 | `auto` 优先使用可用 CUDA；也可指定 `cuda:0` 或 `cpu`。 |
| 浮点精度 | `dtype` | 张量计算精度 | `float32` 更快，`float64` 更稳但更慢。 |
| 随机种子 | `seed` | 噪声随机数种子 | 固定后可重复生成同一组噪声；JSON 中仍为 `echo.seed`，不移入 `compute`。 |
| 分块大小 | `chunk_size` | 可选计算分块样本数 | 配置中存在时显示；JSON 中仍为 `echo.chunk_size`。显存不足时可调小。 |

### 7.3 目标参数

| 界面标签 | 配置字段 | 含义 | 注意事项 |
| --- | --- | --- | --- |
| 自转周期 | `rotation_period_s` | 仿真真值自转周期 | GUI 可用 h 或 s 输入；保存到 JSON 时统一换算为 s。真实反演时它不是已知量；这里是仿真标签。 |
| 初始相位 | `initial_phase_deg` | 观测起点目标初相位，单位 ° | 改变初相位会改变回波初始形态。 |
| 自转轴坐标系 | `spin_pole_frame` | 自转轴角度使用的坐标系 | GUI 显示“赤道坐标系”和“黄道坐标系”；保存值为 `equatorial` 或 `ecliptic`。旧配置中的 `icrs` 会自动按赤道坐标系兼容。 |
| 自转轴赤经/赤纬 | `spin_pole_icrs_deg` | 赤道坐标下的赤经、赤纬，单位 ° | 选择赤道坐标系时显示，GUI 拆成两个输入框。 |
| 自转轴黄经/黄纬 | `spin_pole_ecliptic_deg` | 黄道坐标下的黄经、黄纬，单位 ° | 选择黄道坐标系时显示，程序会转换到赤道方向后计算。 |

### 7.4 散射热点

| 界面标签 | 配置字段 | 含义 | 注意事项 |
| --- | --- | --- | --- |
| 启用 | `enabled` | 是否启用人工强散射斑块 | 关闭后回波仿真跳过强散射斑增强；GUI 会收起斑块方向、半径和强度。 |
| 斑块方向 | `direction_body` | 强散射斑中心在小行星本体系中的方向 | GUI 使用本体系经度/纬度输入，单位 °；保存时转换为内部使用的单位方向向量。 |
| 斑块半径 | `radius_deg` | 强散射斑角半径，单位 ° | 越大，增强区域越宽。 |
| 斑块强度 | `strength` | 强散射斑相对增强系数 | 用于打破几何对称性和测试周期可辨识性，不是完整粗糙度模型。 |

### 7.5 雷达参数

界面中与下节波形参数共用“雷达与波形”卡片，避免单个载频字段独占一块大区域。

| 界面标签 | 配置字段 | 含义 | 注意事项 |
| --- | --- | --- | --- |
| 载频 | `carrier_frequency_hz` | 雷达载波频率 | GUI 可用 GHz、MHz 或 Hz 输入；保存到 JSON 时统一换算为 Hz。 |

### 7.6 波形参数

| 界面标签 | 配置字段 | 含义 | 注意事项 |
| --- | --- | --- | --- |
| 波形类型 | `type` | 发射波形 | GUI 显示“连续波”和“Chirp 脉冲序列”；保存值为 `continuous_wave` 或 `chirp_pulse_train`。 |
| 幅度 | `amplitude` | CW 波形幅度 | 连续波模式下为常数幅度。 |
| 脉冲宽度 | `pulse_width_s` | 线性调频脉冲宽度，单位 s | 脉冲串模式使用。 |
| 带宽 | `bandwidth_hz` | 线性调频带宽，单位 Hz | 脉冲串模式使用。 |
| 脉冲重复间隔 | `pri_s` | PRI，单位 s | 脉冲串模式使用。 |
| 首脉冲起点 | `first_pulse_start_s` | 第一个脉冲起始时刻，单位 s | 脉冲串模式使用。 |

当前回波仿真使用面元中心近似、远场路径展开和相干求和。它适合周期反演算法验证，但还不是完整雷达成像物理模型。

## 8. 周期反演参数

`inversion` 读取 `echo.npz`，对复基带 I/Q 做频谱分析和周期搜索。

| 字段 | 含义 | 建议 |
| --- | --- | --- |
| `stft_window_samples` | STFT 窗长 | 决定时间/频率分辨率；必须小于或等于样本数。 |
| `stft_overlap_fraction` | STFT 重叠比例 | 常用 0.5-0.75。 |
| `period_min_s` | 搜索最小周期 | 应覆盖预期周期下界。 |
| `period_max_s` | 搜索最大周期 | 应覆盖预期周期上界；不要盲目设太宽。 |
| `period_grid_size` | 周期网格密度 | 越大越慢，峰值定位越细。 |

当前反演流程是：可选平动多普勒补偿、STFT、提取总功率/频谱质心/RMS 带宽三类特征、对特征序列做 Lomb-Scargle 周期搜索。只有当配置或 echo 元数据中包含 `translation_coefficients_hz` 时，才会执行多项式平动多普勒补偿。示例仿真回波是已生成好的复基带 I/Q，可直接用于当前反演模块。

## 9. 输出文件说明

典型输出结构：

```text
runs/<实验名>/
├── observation_info.npz
├── echo/
│   ├── echo.npz
│   └── summary.json
├── inversion/
│   ├── summary.json
│   ├── best_summary.json
│   ├── dynamic_spectrum.png
│   ├── periodogram.png
│   └── periodogram.html
├── logs/
│   ├── observation.log
│   ├── echo.log
│   └── inversion.log
└── configs/
    ├── experiment.json
    ├── observation.generated.json
    ├── echo.generated.json
    └── inversion.generated.json
```

`summary.json` 保存完整候选列表，`best_summary.json` 保存日志中展示的推荐结果。GUI 预览图缓存在 `.gui_state/previews/`，不是科学结果的唯一来源。

## 10. 蒙特卡洛仿真方案

当前 GUI 适合单次实验的交互配置、执行和检查。蒙特卡洛仿真更适合使用命令行批处理：先准备一组 pipeline JSON 文件，每个文件对应一个样本工况，例如不同 SNR、自转周期、初始相位、散射斑位置、形状模型或观测几何。

推荐工作流如下：

1. 用 GUI 调通一个基准配置，并另存为 `configs/mc/base.json`。
2. 用脚本批量生成 `configs/mc/case_0001.json`、`case_0002.json` 等配置文件。每个配置文件只修改需要随机化的参数，并记录随机种子。
3. 对每个 JSON 调用流水线命令：

```powershell
conda activate pytorch
python pipeline.py --config configs\mc\case_0001.json --run-name mc_case_0001
```

4. 每个样本的输出会进入独立目录，例如 `runs/mc_case_0001/`。后续统计脚本读取各目录下的 `inversion/best_summary.json`、`inversion/summary.json` 和 `echo/summary.json`。
5. 统计阶段建议汇总：真值周期、反演周期、相对误差、是否落入容差、SNR、观测时长、波形类型、是否启用强散射点、随机种子。

如果样本很多，可以把第 3 步改成批处理脚本或任务队列。建议先串行跑 3-5 个样本确认输出字段稳定，再并行运行大批量实验。并行时要保证每个 case 的 `run-name` 唯一，避免多个进程写入同一目录。

GUI 和蒙特卡洛并不冲突：GUI 用来设计、检查和解释单个 case，命令行批处理用来做规模化统计。后续如果要实现正式蒙特卡洛模块，比较合适的形态是新增 `monte_carlo.py`：读取一个样本清单或生成规则，批量调用现有 pipeline，最后输出 CSV/Excel 汇总和误差分布图。

## 11. 参数配置注意事项

1. 先用短时长、低采样率和较小周期网格跑通，再逐步增加规模。
2. 不要让 `stft_window_samples` 大于回波样本数。
3. 真实目标使用 `horizons_vectors` 时，先检查 `ephemeris.query_step_s` 的敏感性。
4. 真实地面站优先使用 `astropy_geodetic`，并保持参考平面一致。
5. 载频越高，相同几何误差对应的相位误差越敏感，应相应检查星历、测站和光行时精度。
6. 示例中的 `scattering_spot` 会让周期特征更清晰；真实散射模型可能不会这么理想。
7. `snr_db` 越高，周期图越干净。评估鲁棒性时应降低 SNR 或加入更真实的系统误差。
8. 如果运行时间过长，优先降低 `duration_s`、`sample_rate_hz`、`period_grid_size` 或调小回波 `chunk_size`。
9. 如果要复现实验，保存顶层 JSON，并保留 `runs/<实验名>/configs/experiment.json`。

## 12. 关于光行时加速与精度

早期实现按接收采样点逐个求解三事件光行时。每个采样点都要在 Python 层调用多次 `retarded_time()`、状态查询、范数计算和单位向量计算。样本数一大，主要耗时来自 Python 循环和重复函数调用，而不是光行时固定点迭代本身。

当前实现把整条接收时间轴作为数组批量处理：

1. 一次性批量求接收时刻对应的散射时刻。
2. 一次性批量求散射时刻对应的发射时刻。
3. 一次性批量计算目标、发射站、接收站位置。
4. 一次性批量计算距离和视线单位向量。

这仍然是同一个固定点方程、同一个 `tolerance_s`、同一个 `max_iter`，只是把逐点 Python 循环换成 NumPy 向量化数组运算。对 `static`、`linear`、`horizons_vectors` 插值状态和 `astropy_geodetic` 批量状态，数学结果应与逐点算法一致。开发验证中，线性/静态小样本与旧逐点算法逐项对比最大差异为 0。

为什么能快很多：以前每个样本都单独进入 Python 循环；现在每轮迭代用底层 C/NumPy 对整批样本计算，函数调用次数从“样本数 × 迭代次数”量级降为“迭代次数”量级。半小时到一分钟以内的提升在这种瓶颈结构下是合理的。

需要注意的边界：

- 向量化不是降低精度，也不是减少迭代阈值。
- 如果状态模型内部本身是低精度插值，最终精度仍受 `query_step_s` 和星历源限制。
- 如果真实实验要求更严，应对 `tolerance_s`、`query_step_s`、`sample_rate_hz` 做敏感性检查。
- 当前解的是小行星质心三事件几何；每个面元的精细路径在回波模块中近似处理，不等同于逐面元精确光行时解。

## 13. 常见问题

### 13.1 GUI 启动时提示 Qt WebEngine 文件缺失

当前 GUI 会自动查找 PySide6/PyQt6 wheel 中的 `QtWebEngineProcess.exe`、`resources` 和 `qtwebengine_locales`。如果仍然失败，说明当前环境的 WebEngine 安装不完整。此时可先使用静态图和外部浏览器预览，或重新安装 PySide6 WebEngine 相关包。

### 13.2 点击中止后为什么输出目录还存在

中止只停止计算进程，不删除已生成的配置快照、日志或部分输出。这样可以保留错误现场，便于检查参数和日志。

### 13.3 为什么示例周期图只有真值附近一个明显峰

示例配置是干净、短链路、已知真值的仿真实验，且强散射斑会增强周期可辨识性；这不代表真实数据一定同样理想。真实雷达数据通常还需要下变频、匹配滤波或距离门、标定、平动补偿、异常点处理和误差建模。

### 13.4 能直接拿真实回波进反演吗

不能把未经处理的真实原始雷达数据直接等同于当前 `echo.npz`。当前反演输入假设已经是统一时间轴上的复基带 I/Q，并且具备必要元数据。真实数据需要先转换成与 `echo.npz` 兼容的数据格式，并完成相应预处理。

### 13.5 星历 padding 不足会怎样

如果 `padding_s` 没有覆盖光行时提前量，插值状态在求解发射或散射时刻时会越界。当前程序会报错并停止观测解算，不会继续给出可能不可靠的结果。遇到这类错误时，应增大 `padding_s`，或检查目标距离、接收时长和时间起点是否合理。

### 13.6 `query_chunk_size` 和 `min_query_chunk_size` 的区别

程序会先生成星历查询时间网格，范围大致从 `-padding_s` 到 `duration_s + padding_s`，步长为 `query_step_s`。在 `query_mode=list` 时，这些 epoch 会按 `query_chunk_size` 分块向 JPL Horizons 查询。

`min_query_chunk_size` 只在请求失败后的自动二分重试中使用。例如某个 80 点分块因为 URL 过长、网关错误或服务临时失败而失败，程序会把它拆成更小的块继续重试，直到块大小达到 `min_query_chunk_size`。正常查询成功时，它不会改变时间网格，也不会改变光行时计算精度。
