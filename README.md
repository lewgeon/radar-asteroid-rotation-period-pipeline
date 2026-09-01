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

PySide6 参数页采用固定双栏，各卡片按内容定高。观测页左栏为目标、
发射站、接收站，右栏为接收设置、星历查询、求解器；勾选单基站只隐藏接收站，
不会重新排列其他卡片。最大化窗口仍保持模块双栏，结果预览移到可关闭的右侧栏；
完成阶段后侧栏自动打开，也可用左侧按钮随时显示或关闭。下方区域只保留执行日志。
数值与紧凑单位框等高显示，可选单位带下拉箭头。
同级字段使用一致字体，卡片标题使用浅蓝标题带；自转轴、位置、速度及散射方向等
复合字段使用统一的浅色纵向关系线标示下属条目。
回波页左栏为“计算设置、雷达参数”，右栏为“目标参数、散射特性”；反演参数分为
“时频分析”和“周期搜索”。这些分组只影响
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
