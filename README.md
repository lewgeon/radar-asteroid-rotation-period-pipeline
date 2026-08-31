# 自转周期测量流水线

[English](README_EN.md)

本项目现在由三个相互独立的子模块组成：

1. `observation/`：根据观测配置解算视线向量和三事件光行时，输出 `observation_info.npz`。
2. `echo/`：读取 `observation_info.npz` 和小行星形状/雷达配置，输出 `echo.npz`。
3. `inversion/`：读取 `echo.npz`，估计自转周期候选值。

顶层 `pipeline.py` 负责把三个模块串联起来。模块之间通过文件交换，不互相导入业务代码。
实验配置只包含三段业务配置：`observation`、`echo` 和 `inversion`。`observation_info.npz`
和 `echo.npz` 这类中间路径由流水线自动生成并注入下游模块，不需要手工配置。

## 快速运行

GUI 详细使用方法见 [自转周期测量 GUI 用户手册](docs/GUI_USER_MANUAL.md)。

```powershell
conda activate pytorch
python pipeline.py --config configs\pipeline_example.json
```

也可以启动图形化界面逐步执行：

```powershell
conda activate pytorch
python pyside_gui.py
```

GUI 会从 `configs/pipeline_example.json` 读取初始参数。点击“执行下一步”会按
`observation`、`echo`、`inversion` 的顺序逐阶段运行；修改后的参数会保存到
`.gui_state/pipeline_gui_state.json`，下次打开时自动沿用，并在界面左侧保留最近运行历史。
执行阶段时，窗口底部会显示当前子模块的粗略百分比进度和正在处理的步骤。
如果需要放弃当前计算，可以点击“中止”；PySide6 主界面会优先在结果面板中嵌入
Plotly 交互预览，缺少 Qt WebEngine 时则退回静态图和外部浏览器打开。
旧版 Tkinter 入口仍保留为 `python gui_app.py`，主要用于回退。

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
