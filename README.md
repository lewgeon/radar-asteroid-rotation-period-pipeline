# 自转周期测量流水线

[English](README_EN.md)

本项目由三个相互独立的子模块组成：

1. `observation/`：根据观测配置解算视线向量和三事件光行时，输出 `observation_info.npz`。
2. `echo/`：读取 `observation_info.npz` 和小行星形状/雷达配置，输出 `echo.npz`。
3. `inversion/`：读取 `echo.npz`，估计自转周期候选值。

顶层 `pipeline.py` 负责把三个模块串联起来。保存契约为 schema v4。字段释义见 [docs/4.3/GLOSSARY.md](docs/4.3/GLOSSARY.md)，架构见 [docs/4.3/ARCHITECTURE_V4.md](docs/4.3/ARCHITECTURE_V4.md)。技术文档按版本归档，目录约定见 [docs/4.3/README.md](docs/4.3/README.md)。4.2 完成快照在 [docs/4.2/README.md](docs/4.2/README.md)。

## 快速运行

GUI 详细使用方法见 [自转周期测量 GUI 用户手册](docs/4.3/GUI_USER_MANUAL.md)，自动发射 Run 的选择、路径变化率时标伸缩和 ADC 窗生成规则见[观测时刻选取与接收窗口生成规范](docs/4.3/OBSERVATION_TIME_SELECTION.md)。

```powershell
conda activate pytorch
python pipeline.py --config configs\chirp_point_target_test.json
```

chirp 脉冲序列模式由 `schedule.runs[].tx_start_utc` 定义真实发射起点，PRF 只属于发射波形，`receiver_sampling.fast_sample_rate_hz` 只属于接收 ADC。观测模块为每个脉冲向前求解“发射—质心散射—接收”事件，并把二维 I/Q 的每一行映射到同一个 run 的全局均匀 ADC 整数栅格。反演模块进行脉冲压缩、单相干组滑动 CPI、距离—多普勒特征提取和带逐 run 基线的多谐波周期搜索，并聚合多个独立特征的候选形成共识结果。不同 `coherence_id` 之间不进行相位拼接。

接收机在每个 run 的接收区间内只有一条采样率为 `fast_sample_rate_hz` 的连续 ADC 时间轴；“快时间/慢时间”只是后续二维处理坐标，PRF 不是第二个接收采样率。为节省脉冲间空白存储，程序先对需要保留的全局 ADC 整数索引生成唯一的一维信号和噪声，再按 `row_start_sample` 组织为二维窗口。同一个全局样点即使出现在多行中也保持完全相同；若相邻脉冲回波重叠，程序会警告并在该样点叠加全部相关脉冲，而不会静默丢失。

schema v4 回波模型支持两种输出参考系：默认 `centroid_compensated` 用于先验证自转周期算法，直接输出理想质心平动补偿后的数据；`raw_baseband` 保留公共传播时延和载波多普勒，用于部署前的真实性验证。二者共享每脉冲三事件星历锚点及默认的 `per_pulse_linear` 脉内运动模型；传统 `frozen` 走–停模式仅在误差门限允许时使用。实现约定见 [schema v4 架构](docs/4.3/ARCHITECTURE_V4.md)。`receive.acquisitions` 已废弃并被拒绝；chirp 请使用 `schedule` 事件源。

也可以启动图形化界面逐步执行：

```powershell
conda activate pytorch
python pyside_gui.py
```

也可以通过模块入口启动：

```powershell
python -m rotation_gui
```

GUI 源码位于 `rotation_gui/` 包中；顶层 `pyside_gui.py` 与 `python -m rotation_gui` 都调用 `rotation_gui.app.main()`。
目录职责、依赖方向和扩展方法见 [GUI 工程架构](docs/4.3/GUI_ARCHITECTURE.md)。

GUI 优先恢复上次退出时的有效会话；没有有效会话时读取 `configs/chirp_point_target_test.json`（开发用点目标夹具，正式示例配置待重新设计）。左侧选择观测、回波或反演阶段；顶部可载入、保存和校验配置，设置实验名、输出目录与发射波形，并运行当前阶段或完整流水线。散射模型只在回波阶段显示，进度条位于顶部操作行，日志位于参数区下方；回波完成后可通过“查看回波”在系统浏览器中打开 Plotly 预览。详细操作与各字段说明见 [GUI 用户手册](docs/4.3/GUI_USER_MANUAL.md)。
滚动条滑块和勾选状态使用高对比度颜色；下拉列表恢复控件下方展开，原生动画遵循
Windows 的界面效果支持情况（屏幕下方空间不足时仍可向上展开）。

观测解算结果自动保存为 `runs/<实验名>/observation_info.npz`。观测页可选择并校验已有
文件来跳过重复解算，也可把本次视线向量另存到其他位置。接收时长支持 h/min/s，
初始相位支持 ° 或 π rad 输入；保存 JSON 时仍换算为原有标准单位。

GUI 回归测试（离屏运行，需要 PySide6）：

```powershell
conda activate pytorch
python -m pytest tests/test_gui_schema_v4.py -q -p no:cacheprovider
```

测试覆盖默认配置无废弃字段、字段 v4 路径、配置同步、另存为、三种窗口宽度与完整保存/重载往返。

GUI 和 `pipeline.py` 使用同一套配置生成规则：运行前会先在
`runs/<run-name>/configs/` 生成 `observation.generated.json`、
`echo.generated.json` 和 `inversion.generated.json`，再逐阶段调用各子模块脚本。
如果运行报错，先看 GUI 日志中的“当前参数来源”和“生成配置”路径。

输出默认写入：

```text
runs/<run-name>/
├── observation_info.npz
├── echo/
│   ├── echo.npz
│   └── summary.json
├── inversion/
│   ├── summary.json
│   ├── dynamic_spectrum.png
│   └── periodogram.png
└── configs/
    ├── observation.generated.json
    ├── echo.generated.json
    └── inversion.generated.json
```

## 串联方式

顶层流水线 JSON 为三段式：`observation` / `echo` / `inversion`。当前仓库不再附带正式示例配置；开发验证可用 `configs/chirp_point_target_test.json` 或 `configs/chirp_mesh_target_test.json`。完整字段表见各子模块 README：

- [observation/README.md](observation/README.md)（观测）
- [echo/README.md](echo/README.md)（回波）
- [inversion/README.md](inversion/README.md)（反演）

顶层结构概览（详细字段表见各子模块 README；**字段**表头跨两格：左父右子，与说明同行对齐）：

<table>
<thead>
<tr><th>字段</th><th>物理意义</th><th>说明</th></tr>
</thead>
<tbody>
<tr>
  <td><code>observation</code></td>
  <td>目标、测站、CW 连续接收或 Chirp 发射/采样计划</td>
  <td>对象；单站省略 <code>receiver</code>；CW / Chirp 事件源二选一（见 observation README）</td>
</tr>
<tr>
  <td><code>echo</code></td>
  <td>散射模型、载频、波形幅度/带宽、噪声等</td>
  <td>对象；<code>echo.waveform.type</code> 须与观测事件源一致（Chirp↔<code>schedule</code>，CW↔<code>receive</code>）；流水线注入 <code>observation_info_path</code>（见 echo README：mesh / 点目标分表）</td>
</tr>
<tr>
  <td><code>inversion</code></td>
  <td>周期搜索与（按布局）STFT 或 CPI 策略</td>
  <td>对象；CW / Chirp 字段集不同（见 inversion README）</td>
</tr>
</tbody>
</table>

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
python pipeline.py --config configs\chirp_point_target_test.json --skip-observation
python pipeline.py --config configs\chirp_point_target_test.json --skip-observation --skip-echo
```

可以用 `--run-name` 指定实验目录名：

```powershell
python pipeline.py --config configs\chirp_point_target_test.json --run-name smoke_001
```

## 自定义真实实验

以现有开发配置为底稿复制后，按上表三段替换：观测几何与时间轴、回波散射/射频、反演搜索范围（Chirp 另设 CPI 时长）。开发夹具的反演区间往往偏短；正式实验应按观测时长与预期自转周期重设。正式示例配置将在流水线完全跑通后另行设计。
