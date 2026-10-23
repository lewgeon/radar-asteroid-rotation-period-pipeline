# 系统架构、Schema v4 与 GUI 工程接口

本文说明当前可保存配置、观测—回波—反演之间的数据契约，以及 GUI 如何组织这些业务入口。字段与术语见[术语表](GLOSSARY.md)，操作与参数释义见[GUI 用户手册](GUI_USER_MANUAL.md)。

<a id="schema-v4"></a>

## 配置与业务边界

用户 JSON 只描述场景与少量策略，不重复同一物理量。配置只保存为 schema v4 的 `observation`、`echo`、`inversion` 三段式，加载时由 `pipeline.normalize_config` 统一规范化。`pipeline.py` 拥有业务配置生成和计算流程；GUI 编排已有入口，不复制观测、回波或反演算法。

observation 产出类型化的 ObservationPlan（`observation_info.npz`），echo 的时序与 ADC 只读该计划。inversion 只读回波产物与周期搜索策略，射频与布局从数据派生。Chirp 的 CPI 以物理时长表达，`cpi_duration_s` 与 `cpi_hop_duration_s` 在反演入口依据回波元数据中从 ObservationPlan 继承的 `prf_hz` 换算为整数脉冲数。Horizons 查询 padding 是内部光行时安全余量，不属于用户场景契约。

<a id="pipeline-data-flow"></a>

## 数据流

```text
用户 v4 配置
  → normalize_config
  → observation（stations + schedule/receive 事件源）
  → observation_info.npz（ObservationPlan）
  → echo（波形律 + 散射体；时序来自 plan）
  → echo.npz
  → inversion（PeriodSearchPolicy）
```

<a id="station-and-event-contract"></a>

## 测站与事件源约定

单站配置只写 `transmitter`，省略 `receiver`；observation 入口将接收站深拷贝为发射站，不使用 `id` 或 `same_as` 建立引用。测站坐标与可见性适用条件见[观测选时与测站约束](OBSERVATION_TIME_SELECTION.md#station-visibility)。

| 波形 | 事件源 | 配置归属 |
| --- | --- | --- |
| Chirp | `schedule` + `transmit` + `radar_system` + `receiver_sampling` | PRF 与脉宽写在 `observation.transmit` |
| CW | `receive`，连续采样 | 接收起点、时长与采样率写在 `observation.receive` |

两种事件源不能同时出现。射频类型只写 `echo.waveform.type`，并与事件源对齐。开发验证使用 `configs/chirp_point_target_test.json`；该文件是开发夹具，正式示例配置尚待重新设计。

<a id="gui-architecture"></a>

## GUI 入口与模块职责

PySide6 界面实现位于 `rotation_gui/` 包中，启动逻辑是 `rotation_gui/app.py` 的 `main()`；顶层 `pyside_gui.py` 与 `python -m rotation_gui` 都调用此入口。界面当前为中文，未实现多语言切换；阶段、分组、字段和选项文案来自 `schema.py` 的中文标签表。

```text
rotation_gui/
├── __init__.py              # 公共接口：PipelineWindow、configure_gui_style、main
├── __main__.py              # python -m rotation_gui
├── app.py                   # QApplication 创建、样式应用与启动
├── qt_compat.py             # PySide6/PyQt6 选择与 Qt 常量
├── schema.py                # 阶段、字段、单位、选项、数值类型和中文标签
├── storage.py               # 项目路径、JSON、嵌套配置读写和预览缓存目录
├── styling.py               # 全局 QSS 与原生控件样式
├── widgets/
│   ├── inputs.py            # 数值、单位、布尔、向量和方向输入控件
│   └── layout.py            # 响应式卡片和子模块关系线
└── window/
    ├── main.py              # 窗口外壳、配置、阶段和子进程执行
    ├── parameter_form.py    # ParameterForm：卡片、字段收集和状态归一化
    ├── echo_preview.py      # 回波 Plotly 预览
    ├── inversion_feature_preview.py # 已保存反演特征的预览
    ├── result_service.py    # 已有结果查询与读取服务
    └── __init__.py
```

<a id="gui-module-interfaces"></a>

## GUI 模块接口与依赖方向

外部调用者只需认识 `rotation_gui.PipelineWindow`、`configure_gui_style()` 和 `main()`。`PipelineWindow` 定义在 `window/main.py`，参数表单封装在 `window/parameter_form.py` 的 `ParameterForm`；二者都是自包含实现，不使用 mixin，字段所有权与配置同步路径可以直接追踪。

```text
app → window → widgets / schema / storage / styling → qt_compat
```

发射波形位于窗口顶部的实验设置行，散射模型位于回波参数区顶部且只在该阶段显示；切换会改变后续阶段的适用字段。数值控件通过 `widgets.inputs` 的同一接口验证有限数和整数约束，非法草稿即时标红，收集配置时阻止保存、校验或运行。配置路径和实验名的操作规则集中维护在[用户手册](GUI_USER_MANUAL.md#3-界面区域说明)，这里不再复制一套保存说明。

<a id="artifact-identity"></a>

## 阶段状态、产物身份与存储

阶段状态与产物复用比较生成时记录的相关参数摘要，以及文件绝对路径、大小和纳秒修改时间（`output_identity`、上游 `*_identity`）；不计算信号文件 SHA256，也没有严格内容核验模式。参数摘要可以用 SHA256 编码小 JSON，这不会读取回波。结构检查只读取 NPZ 中 IQ／观测掩码的 NPY 数组头，再核对小规模坐标和元数据，不为核对形状载入完整信号。

上游成功重跑会为下游留下 `invalidated_by` 标记；旧文件即使仍在，也显示需要重跑，不能用历史复用开关绕过。旧文件哈希字段只作为历史记录读取，不触发内容扫描；历史依赖证据不足或上游记录更新时，不自动认定旧下游有效。

`npz_mapping.py` 直接只读映射未压缩 NPZ 成员，压缩输入保留提取回退；`processing_store.py` 分别管理特征身份和独立于估计器的频谱身份，阶段对象按身份引用去重。`cpi_display.py` 读取新版完整网格单精度 dB／双精度距离功率，也兼容旧双精度功率；查看端不反推科学功率、不重做 FFT。

脉压检查将显示矩阵和逐行信息独立压缩保存，载入时恢复悬停元数据。GUI HTML 共享本地版本化脚本，普通导出仍为独立文件。映射不扫描完整成员 CRC；Windows 替换源文件前必须结束读取并释放映射，`EchoDataset.close()` 用于明确释放，关闭后的数组及视图不可再使用。范围、量化界与验收见[存储专题](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/chirp-pulse/docs/4.3/vs_4.2/changes/NATIVE_RANGE_FEATURES.md#compact-storage-20261016)。

<a id="gui-extension-guide"></a>

## 常见扩展位置

### 增加普通参数

1. 在 `schema.py` 增加标签（`FIELD_LABELS`）、单位（`FIELD_UNITS` / `UNIT_CHOICES`）或选项（`CHOICES` / `OPTION_LABELS`）元数据。
2. 若字段工厂 `ParameterForm._field_widget` 已能表达参数，无需创建新控件。
3. 在 `parameter_form.py` 调整分组和顺序常量，例如 `CARD_ORDER`、`ECHO_FIELD_ORDER`。
4. 在 `tests/test_gui_schema_v4.py` 增加字段存在性或配置往返断言。

### 增加动态子模块

1. 在 `parameter_form.py` 定义状态转换（`_on_state_changed` 等）与模型归一化（`_normalize_state_group`）。
2. 使用统一的 `SubsectionPanel` 渲染复合控件。
3. 先更新模型，再重建最小区域；不要在控件销毁期间从旧控件保存状态。
4. 验证重复切换、焦点恢复与配置同步，参考 `test_stage_switch_syncs_edited_observation_value`。

### 增加流水线执行行为

计算命令、进度协议、停止策略和进程结束处理位于 `window/main.py` 的 `_stage_command`、`_start_stages`、`_process_finished`。具体算法继续位于业务模块中；新增进度消息沿用 `__PROGRESS__`、`__WARNING__`、`__ERROR__` 行协议，显示前将协议解析为可读日志。

### 增加结果预览

回波 Plotly 预览生成器位于 `window/echo_preview.py`，使用系统浏览器打开。已保存反演特征及结果读取分别由 `inversion_feature_preview.py`、`result_service.py` 协作完成。预览失败不得覆盖计算成功状态；结果查看消费已保存产物的边界见[用户手册](GUI_USER_MANUAL.md)。

<a id="gui-verification"></a>

## GUI 验证

GUI 回归测试位于 `tests/test_gui_schema_v4.py`，需要 pytorch 环境中的 PySide6，使用 offscreen 平台运行：

```powershell
conda activate pytorch
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest tests/test_gui_schema_v4.py -q -p no:cacheprovider
```

覆盖范围包括默认配置不含废弃字段、实验级模式入口、编辑值同步进 `config_data`、阶段切换同步、非法标量／向量拒绝、模式重复切换、另存为到新路径、三种窗口宽度，以及“编辑→保存→重载”往返。动态控件还应按仓库协作规范核对实际位置、滚动范围和焦点；这些是后续修改的验收要求，不表示本次文档整理重跑了 GUI 测试。
