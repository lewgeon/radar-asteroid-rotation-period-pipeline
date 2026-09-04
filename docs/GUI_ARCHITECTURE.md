# GUI 工程架构

PySide6 界面实现位于 `rotation_gui/` 包中。顶层 `pyside_gui.py` 仅作为兼容启动入口，
因此原有的 `python pyside_gui.py` 命令仍然有效；也可以使用 `python -m rotation_gui`。

## 目录职责

```text
rotation_gui/
├── __init__.py              # 小型公共接口：PipelineWindow、样式配置、main
├── __main__.py              # python -m rotation_gui
├── app.py                   # QApplication 创建和启动预热
├── qt_compat.py             # PySide6/PyQt6 选择、Qt 常量、WebEngine 探测
├── schema.py                # 阶段、字段、单位、选项、默认值和本地化文本
├── storage.py               # 项目路径、JSON 和嵌套配置读写
├── styling.py               # 全局 QSS 与原生控件样式
├── widgets/
│   ├── inputs.py            # 数值、单位、布尔、向量、方向输入控件
│   ├── layout.py            # 响应式卡片和子模块关系线
│   └── preview.py           # 静态图片预览控件
└── window/
    ├── main.py              # 主窗口状态和界面外壳
    ├── configuration.py     # 配置载入、保存、校验与迁移
    ├── execution.py         # 子进程、进度、取消和结束状态
    ├── previews.py          # 各流水线阶段的结果预览
    ├── history.py           # 历史、日志、打开结果和窗口关闭
    └── forms/
        ├── rendering.py     # 卡片、字段和控件构造
        └── state.py         # 动态字段状态机与配置同步
```

## 模块接口与依赖方向

外部调用者只需要认识 `rotation_gui.PipelineWindow`、`configure_gui_style()` 和
`main()`。窗口内部使用按职责划分的 mixin；这些 mixin 是实现细节，不属于稳定公共接口。
这种结构在不重写成熟界面行为的前提下，将不同变化原因隔离开来。

依赖方向保持为：

```text
app → window → widgets / schema / storage / styling → qt_compat
```

`pipeline.py` 仍然拥有业务配置生成和计算流程。GUI 只编排已有入口，不复制观测、回波或
反演算法。

## 常见扩展位置

### 增加普通参数

1. 在 `schema.py` 增加标签、单位或选项元数据。
2. 若现有字段工厂可以表达该参数，无需创建新控件。
3. 在 `forms/rendering.py` 调整可视分组或顺序。
4. 增加配置往返和多语言布局测试。

### 增加动态子模块

1. 在 `forms/state.py` 定义状态转换和模型更新。
2. 在 `forms/rendering.py` 使用统一的 `SubsectionPanel` 渲染。
3. 先更新模型，再重建最小区域；不要在控件销毁期间从旧控件保存状态。
4. 测试重复切换、焦点恢复、文本选区以及延迟删除事件。

### 增加流水线执行行为

计算命令、进度协议、停止策略和进程结束处理放在 `execution.py`。具体算法继续位于原业务
模块中。新增进度消息应沿用 `__PROGRESS__`、`__WARNING__`、`__ERROR__` 行协议。

### 增加结果预览

在 `previews.py` 增加阶段预览生成器，并同时保留静态图或外部打开回退。预览失败不得覆盖
计算成功状态。

## 验证

```powershell
conda activate pytorch
python -m unittest tests.test_gui_architecture tests.test_gui_layout
```

布局测试会覆盖三种窗口宽度、中英文、所有阶段、条件字段、配置往返、焦点与控件生命周期。
截图位于 `tmp/gui-layout-after/`，测试通过后仍应人工检查这些截图。
