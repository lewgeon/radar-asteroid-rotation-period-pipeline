# 自转周期测量流水线

[English](README_EN.md)

本项目现在由三个相互独立的子模块组成：

1. `observation/`：根据观测配置解算视线向量和三事件光行时，输出 `observation_info.npz`。
2. `echo/`：读取 `observation_info.npz` 和小行星形状/雷达配置，输出 `echo.npz`。
3. `inversion/`：读取 `echo.npz`，估计自转周期候选值。

顶层 `pipeline.py` 负责把三个模块串联起来。模块之间通过文件交换，不互相导入业务代码。
流水线同时读取旧三段式配置和 schema v3 campaign 配置。中间路径由流水线自动生成
并注入下游模块，不需要手工配置。

## 快速运行

GUI 详细使用方法见 [自转周期测量 GUI 用户手册](docs/GUI_USER_MANUAL.md)。

```powershell
conda activate pytorch
python pipeline.py --config configs\pipeline_example.json
```

新的 chirp 发射驱动模式请使用 schema v3 campaign 配置：

```powershell
python pipeline.py --config configs\campaign_v3_example.json
```

该模式由 `schedule.runs[].tx_start_utc` 定义真实发射起点，PRF 只属于发射波形，
`receiver.fast_sample_rate_hz` 只属于接收 ADC。观测模块为每个脉冲向前求解
“发射—质心散射—接收”事件，并把二维 I/Q 的每一行映射到同一个 run 的全局均匀
ADC 整数栅格。反演模块进行脉冲压缩、单相干组滑动 CPI、距离—多普勒特征提取和
带逐 run 基线的多谐波周期搜索，并聚合多个独立特征的候选形成共识结果。不同
`coherence_id` 之间不进行相位拼接。

接收机在每个 run 的接收区间内只有一条采样率为 `fast_sample_rate_hz` 的连续 ADC
时间轴；“快时间/慢时间”只是后续二维处理坐标，PRF 不是第二个接收采样率。为节省
脉冲间空白存储，程序先对需要保留的全局 ADC 整数索引生成唯一的一维信号和噪声，
再按 `row_start_sample` 组织为二维窗口。同一个全局样点即使出现在多行中也保持完全
相同；若相邻脉冲回波重叠，程序会警告并在该样点叠加全部相关脉冲，而不会静默丢失。

schema v3 的回波模型支持两种输出参考系：默认 `centroid_compensated` 用于先验证
自转周期算法，直接输出理想质心平动补偿后的数据；`raw_baseband` 保留公共传播时延
和载波多普勒，用于部署前的真实性验证。二者共享每脉冲三事件星历锚点及默认的
`per_pulse_linear` 脉内运动模型；传统 `frozen` 走–停模式仅在误差门限允许时使用。
实现约定见 [schema v3 架构](docs/ARCHITECTURE_V3.md)。旧 `receive.acquisitions`
仅作为兼容路径保留，不应用于新的 chirp 实验。

也可以启动图形化界面逐步执行：

```powershell
conda activate pytorch
python pyside_gui.py
```

也可以通过模块入口启动：

```powershell
python -m rotation_gui
```

GUI 源码已按职责拆分到 `rotation_gui/` 包中，顶层 `pyside_gui.py` 仅保留兼容入口。
目录职责、依赖方向和扩展方法见 [GUI 工程架构](docs/GUI_ARCHITECTURE.md)。

GUI 会从 `configs/campaign_v3_example.json` 读取新的 chirp 初始参数；既有旧配置仍可
手动载入。观测页顶部直接显示 Run 计划卡片，可计算可见性、自动选择并回填发射时刻。
点击“执行下一步”会按
`observation`、`echo`、`inversion` 的顺序逐阶段运行；修改后的参数会保存到
`.gui_state/pipeline_gui_state.json`，下次打开时自动沿用，并在界面左侧保留最近运行历史。
执行阶段时，窗口底部会显示当前子模块的粗略百分比进度和正在处理的步骤。
如果需要放弃当前计算，可以点击“中止”；PySide6 主界面会优先在结果面板中嵌入
Plotly 交互预览，缺少 Qt WebEngine 时则退回静态图和外部浏览器打开。
旧版 Tkinter 入口仍保留为 `python gui_app.py`，主要用于回退。

PySide6 参数页采用固定双栏，各卡片按内容定高。schema v3 观测页将 Run 调度与实时
时间轴横跨顶部，右栏集中显示可见性、工作体制、发射波形与接收 ADC；最大化窗口仍保持模块双栏，
结果预览位于可关闭的右侧栏；
完成阶段后侧栏自动打开，也可用左侧按钮随时显示或关闭。下方区域只保留执行日志。
数值与紧凑单位框等高显示，可选单位带下拉箭头。
同级字段使用一致字体，卡片标题使用浅蓝标题带；自转轴、位置、速度及散射方向等
复合字段使用统一的浅色纵向关系线标示下属条目。
schema v3 的采集参数只有观测页这一处可编辑来源。回波页顶部显示只读采集摘要，
并在执行前从观测配置生成回波执行快照；回波页只编辑“计算设置、仿真与噪声、
目标参数、散射特性”。旧三段式配置仍保留原有雷达参数编辑器。反演参数分为
“Chirp 信号处理”和“周期搜索”；schema v3 chirp 不显示仅供 CW 使用的 STFT 字段。这些分组只影响
界面展示，不改变 JSON 配置字段。参数区与日志/预览区之间的分隔条可拖动调整。
滚动条滑块和勾选状态使用高对比度颜色；下拉列表恢复控件下方展开，原生动画遵循
Windows 的界面效果支持情况（屏幕下方空间不足时仍可向上展开）。

观测解算结果自动保存为 `runs/<实验名>/observation_info.npz`。观测页可选择并校验已有
文件来跳过重复解算，也可把本次视线向量另存到其他位置。接收时长支持 h/min/s，
初始相位支持 ° 或 π rad 输入；保存 JSON 时仍换算为原有标准单位。

界面布局和交互回归检查（不修改已保存的 GUI 参数，截图写入 `tmp/`）：

```powershell
conda activate pytorch
python tests/test_gui_layout.py
```

如需同时运行真实短示例流水线，先设置 `$env:GUI_SMOKE_PIPELINE='1'` 再运行上述测试；
这仅用于功能冒烟验证，不代表正式实验复现。旧版 Tkinter 界面不包含本次布局更新。

GUI 和 `pipeline.py` 使用同一套配置生成规则：运行前会先在
`runs/<run-name>/configs/` 生成 `experiment.json`、`observation.generated.json`、
`echo.generated.json` 和 `inversion.generated.json`，再逐阶段调用各子模块脚本。
如果运行报错，先看 GUI 日志中的“当前参数来源”和“生成配置”路径。

输出默认写入：

```text
runs/pipeline_example/
├── observation_info.npz
├── echo/
│   ├── echo.npz
│   └── summary.json
├── inversion/
│   ├── summary.json
│   ├── dynamic_spectrum.png
│   └── periodogram.png
└── configs/
    ├── echo.generated.json
    └── inversion.generated.json
```

## 串联方式

`configs/pipeline_example.json` 只写三段配置：

```text
observation  观测时刻、目标编号、测站、光行时求解参数
echo         形状模型、雷达、波形、自转真值、散射与噪声参数
inversion    STFT参数、周期搜索范围和网格密度
```

运行时，`pipeline.py` 会自动生成：

```text
runs/<run-name>/observation_info.npz
runs/<run-name>/echo/echo.npz
runs/<run-name>/inversion/summary.json
```

同时会在 `runs/<run-name>/configs/` 中保存本次实际使用的 `*.generated.json`，
方便复查和复现实验。

如果只想重跑下游，可复用已有中间结果：

```powershell
python pipeline.py --config configs\pipeline_example.json --skip-observation
python pipeline.py --config configs\pipeline_example.json --skip-observation --skip-echo
```

可以用 `--run-name` 指定实验目录名：

```powershell
python pipeline.py --config configs\pipeline_example.json --run-name smoke_001
```

## 自定义真实实验

通常只需要复制 `configs/pipeline_example.json`，然后在三个业务段中替换：

- `observation`：真实测站、目标编号、观测起点、观测时长和采样率。
- `echo`：形状模型、自转真值、载频、波形、信噪比等字段。
- `inversion`：STFT 窗长、周期搜索范围和网格密度。

示例配置为了快速跑通链路，把反演搜索范围设得较短；正式实验应根据观测时长和预期自转周期重新设置。
