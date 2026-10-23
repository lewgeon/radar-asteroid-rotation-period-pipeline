# 小行星雷达自转周期测量

[English](README_EN.md)

**4.3已完成本轮收尾**；进一步算法优化与尚未完成的事项归入[4.4](docs/4.4/README.md)。项目已连接视线/光行时解算、回波仿真和自转周期反演，并提供GUI与命令行入口。已完成椭球、EV5网格控制及EV5名义参数的仿真实验；真实雷达观测验证、跨场景精度和最终误差校准仍在后续范围内。

## 先读哪份

| 想了解什么 | 推荐阅读 |
| --- | --- |
| 已实现效果、EV5结果、仍存在的问题 | **[4.3项目现状总览](docs/4.3/PROJECT_OVERVIEW.md)** |
| 文档如何分类、下一步读什么 | [4.3文档导航](docs/4.3/README.md) |
| 如何操作与查看结果 | [GUI用户手册](docs/4.3/GUI_USER_MANUAL.md) |
| 信号如何变成周期 | [Chirp完整链路](docs/4.3/CHIRP_INVERSION_WALKTHROUGH.md)、[反演算法](docs/4.3/INVERSION_ALGORITHM.md) |
| 实验数值、负结果与复现 | [按阶段查证据](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/experiments/README.md#reports)、[事前实验协议](EXPERIMENTS.md) |
| 下一步研究与实现缺口 | [当前开放问题](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.4/vs_4.3/plans/OPEN_ISSUES.md#current-issues) |
| 接手EV5精度改进编码 | **[独立接手说明](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.4/vs_4.3/plans/EV5_PRECISION_IMPLEMENTATION_HANDOFF.md)**，无需通读历史研究与计划 |

项目包含三个独立子模块：`observation/`生成 `observation_info.npz`，`echo/`生成 `echo.npz`，`inversion/`提取特征并估计周期；`pipeline.py`串联三者。配置与保存契约为schema v4，字段和数据归属见[架构](docs/4.3/ARCHITECTURE_V4.md)。旧版本记录从[4.2快照](docs/4.2/README.md)进入。

## 快速运行

首次获取请使用 `git clone --recurse-submodules https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline.git`；已有克隆执行 `git submodule update --init --recursive`。GitHub源码ZIP和根仓库`git archive`不包含三个子模块的内容，不能将根ZIP当成完整安装包。下方默认配置随仓库提供，适合接口和启动检查，不是自转精度实验。

测试、研究脚本及内部过程证据保留在Git仓库，但从源码归档排除；手册中对应证据链接指向仓库的`chirp-pulse`分支，离线阅读使用完整克隆。本文档引用的是待提交的同一版本内容，在线页面需随对应提交发布后才可访问。

GUI 详细使用方法见 [自转周期测量 GUI 用户手册](docs/4.3/GUI_USER_MANUAL.md)，自动发射 Run 的选择、路径变化率时标伸缩和 ADC 窗生成规则见[观测时刻选取与接收窗口生成规范](docs/4.3/OBSERVATION_TIME_SELECTION.md)。

```powershell
conda activate pytorch
python pipeline.py --config configs\chirp_point_target_test.json
```

chirp 脉冲序列模式由 `schedule.runs[].tx_start_utc` 定义真实发射起点，PRF 只属于发射波形，`receiver_sampling.fast_sample_rate_hz` 只属于接收 ADC。观测模块为每个脉冲向前解算“发射—质心散射—接收”事件，将二维 I/Q 行映射到同一 Run 的全局 ADC 整数栅格。反演进行脉冲压缩、单相干组滑动 CPI 和特征提取；逐脉冲 fallback 与 CPI 的周期搜索均采用共同截距，保留原始特征时刻，不按 Run 聚合。不同 `coherence_id` 之间不拼接复相位，多特征默认使用共同周期留出预测融合，相关性校准尚未完成。此搜索假定跨 Run 标量参考与标定一致，未知偏置需独立校准；导出包含实际处理路径、有效样本数与跳过原因，未校准显著性显示“未评估”。

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

GUI 源码位于 `rotation_gui/` 包中；顶层 `pyside_gui.py` 与 `python -m rotation_gui` 都调用 `rotation_gui.app.main()`。目录职责、依赖方向和扩展方法见 [GUI 工程架构](docs/4.3/ARCHITECTURE_V4.md#gui-architecture)。

GUI 优先恢复上次退出时的有效会话；没有有效会话时读取 `configs/chirp_point_target_test.json`（开发用点目标夹具，正式示例配置待重新设计）。左侧选择观测、回波或反演阶段；顶部可载入、保存和校验配置，设置实验名、输出目录与发射波形，并运行当前阶段或完整流水线。散射模型只在回波阶段显示，进度条位于顶部操作行，日志位于参数区下方；回波完成后可通过“图像结果 ▾ → 原始回波”在系统浏览器中打开 Plotly 预览。详细操作与各字段说明见 [GUI 用户手册](docs/4.3/GUI_USER_MANUAL.md)。

滚动条滑块和勾选状态使用高对比度颜色；下拉列表恢复控件下方展开，原生动画遵循Windows 的界面效果支持情况（屏幕下方空间不足时仍可向上展开）。

观测解算结果自动保存为 `runs/<实验名>/observation_info.npz`。观测页可选择并校验已有文件来跳过重复解算，也可把本次视线向量另存到其他位置。接收时长支持 h/min/s，初始相位支持 ° 或 π rad 输入；保存 JSON 时仍换算为原有标准单位。

GUI 回归测试（离屏运行，需要 PySide6）：

```powershell
conda activate pytorch
python -m pytest tests/test_gui_schema_v4.py -q -p no:cacheprovider
```

测试覆盖默认配置无废弃字段、字段 v4 路径、配置同步、另存为、三种窗口宽度与完整保存/重载往返。

GUI 和 `pipeline.py` 使用同一套配置生成规则：运行前会先在 `runs/<run-name>/configs/` 生成 `observation.generated.json`、`echo.generated.json` 和 `inversion.generated.json`，再逐阶段调用各子模块脚本。如果运行报错，先看 GUI 日志中的“当前参数来源”和“生成配置”路径。

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

顶层流水线 JSON 为三段式：`observation` / `echo` / `inversion`。开发验证使用随仓库提供的 `configs/chirp_point_target_test.json`；网格实验需自行准备模型路径与场景配置，本地未提交的网格配置不是发行示例。完整字段表见各子模块 README：

- [observation/README.md](observation/README.md)（观测）
- [echo/README.md](echo/README.md)（回波）
- [inversion/README.md](inversion/README.md)（反演）

顶层结构概览（详细字段表见各子模块 README）：

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

同时会在 `runs/<run-name>/configs/` 中保存本次实际使用的 `*.generated.json`，方便复查和复现实验。

如果只想重跑下游，可复用已有中间结果：

```powershell
python pipeline.py --config configs\chirp_point_target_test.json --skip-observation
python pipeline.py --config configs\chirp_point_target_test.json --skip-observation --skip-echo
```

可以用 `--run-name` 指定实验目录名：

```powershell
python pipeline.py --config configs\chirp_point_target_test.json --run-name smoke_001
```

## 自定义仿真实验

以现有开发配置为底稿复制后，按上表三段替换：观测几何与时间轴、回波散射/射频、反演搜索范围（Chirp 另设 CPI 时长）。开发夹具的反演区间往往偏短；正式实验应按观测时长与预期自转周期重设。全链路已跑通；EV5研究配置绑定具体场景与本地模型资源，可移植的正式示例仍待单独整理。
