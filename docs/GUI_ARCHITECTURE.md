# GUI 工程架构

PySide6 界面实现位于 `rotation_gui/` 包中，启动逻辑在 `rotation_gui/app.py` 的 `main()`。
顶层 `pyside_gui.py` 与 `python -m rotation_gui`（`__main__.py`）都只是调用这个 `main()`。

当前界面为中文界面（未实现多语言切换）；所有界面文案来自 `schema.py` 的中文标签表
（`STAGE_LABELS`、`GROUP_LABELS`、`FIELD_LABELS`、`OPTION_LABELS`）。

## 目录职责

```text
rotation_gui/
├── __init__.py              # 公共接口：PipelineWindow、configure_gui_style、main
├── __main__.py              # python -m rotation_gui
├── app.py                   # QApplication 创建、样式应用与启动
├── qt_compat.py             # PySide6/PyQt6 选择与 Qt 常量
├── schema.py                # 阶段、字段、单位、选项、数值类型和中文标签
├── storage.py               # 项目路径、JSON 和嵌套配置读写、预览缓存目录
├── styling.py               # 全局 QSS 与原生控件样式
├── widgets/
│   ├── inputs.py            # 数值、单位、布尔、向量、方向输入控件
│   ├── layout.py            # 响应式卡片和子模块关系线
└── window/
    ├── main.py              # PipelineWindow：窗口外壳、工具栏、阶段切换、配置载入/保存/校验、子进程执行
    ├── parameter_form.py    # ParameterForm：卡片渲染、字段收集、状态归一化
    ├── echo_preview.py      # 回波 Plotly 预览生成；由系统浏览器打开
    └── __init__.py
```

## 模块接口与依赖方向

外部调用者只需要认识 `rotation_gui.PipelineWindow`、`configure_gui_style()` 和 `main()`。
`PipelineWindow` 定义在 `window/main.py`，参数表单封装在 `window/parameter_form.py` 的
`ParameterForm`；二者都是自包含实现（不再使用 mixin），字段所有权与配置同步路径可以直接
追踪。

依赖方向保持为：

```text
app → window → widgets / schema / storage / styling → qt_compat
```

`pipeline.py` 仍然拥有业务配置生成和计算流程。GUI 只编排已有入口，不复制观测、回波或
反演算法。

发射波形位于窗口顶部的实验设置行；散射模型位于回波仿真参数区顶部，仅在该阶段显示。两者切换后会改写后续阶段的适用字段。所有数值控件通过 `widgets.inputs` 的同一接口
验证有限数/整数约束，非法草稿会即时标红，并在收集配置时阻止保存、校验或运行。

## 常见扩展位置

### 增加普通参数

1. 在 `schema.py` 增加标签（`FIELD_LABELS`）、单位（`FIELD_UNITS` / `UNIT_CHOICES`）
   或选项（`CHOICES` / `OPTION_LABELS`）元数据。
2. 若现有字段工厂（`ParameterForm._field_widget`）可以表达该参数，无需创建新控件。
3. 在 `parameter_form.py` 调整分组/顺序常量（如 `CARD_ORDER`、`ECHO_FIELD_ORDER`）。
4. 在 `tests/test_gui_schema_v4.py` 增加字段存在性或配置往返断言。

### 增加动态子模块

1. 在 `parameter_form.py` 定义状态转换（`_on_state_changed` 等）与模型归一化
   （`_normalize_state_group`）。
2. 使用统一的 `SubsectionPanel` 渲染复合控件。
3. 先更新模型，再重建最小区域；不要在控件销毁期间从旧控件保存状态。
4. 测试重复切换、焦点恢复与配置同步（见 `test_stage_switch_syncs_edited_observation_value`）。

### 增加流水线执行行为

计算命令、进度协议、停止策略和进程结束处理位于 `window/main.py`（`_stage_command`、
`_start_stages`、`_process_finished`）。具体算法继续位于原业务模块中。新增进度消息应沿用
`__PROGRESS__`、`__WARNING__`、`__ERROR__` 行协议。

### 增加结果预览

在 `window/echo_preview.py` 增加回波 Plotly 预览生成器，当前固定通过系统浏览器打开。
预览失败不得覆盖计算成功状态。

## 验证

GUI 回归测试位于 `tests/test_gui_schema_v4.py`，需要 PySide6（pytorch 环境）并以 offscreen
平台运行：

```powershell
E:\anaconda3\envs\pytorch\python.exe -m pytest tests/test_gui_schema_v4.py -q -p no:cacheprovider
```

测试覆盖：默认配置不含废弃字段、实验级模式入口、编辑值同步进 `config_data`、阶段切换同步、
非法标量/向量输入拒绝、模式重复切换、另存为到新路径、三种窗口宽度布局、完整“编辑→保存→重载”往返。
