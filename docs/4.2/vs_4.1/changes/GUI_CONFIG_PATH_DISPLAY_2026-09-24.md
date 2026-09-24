# 配置路径改为非交互显示

顶部「配置文件」路径由只读 `QLineEdit` 改成无焦点、无文本交互的 `QLabel`。长路径按可用宽度在中间省略，窗口宽度或字体样式变化时重新计算可见文本，悬停提示保留完整路径；外观使用低对比度灰色背景，不再出现输入框的蓝色焦点边框。文件路径仍由「打开」和「另存为」切换，「保存」更新当前文件。

回归测试断言路径显示不是 `QLineEdit`、没有焦点和文字交互、宽度变小时显示省略、再次放宽时恢复更多字符、路径更新时提示同步、点击后不获得焦点。`conda run -n pytorch python -m pytest tests/test_gui_schema_v4.py -q` 得到 73 passed；`conda run -n pytorch python -m pytest tests -q` 得到 146 passed。另用离屏 Qt 在 1280×800 窗口截图并检查灰色路径区，截图位于忽略版本控制的 `tmp/gui_review_2026_09_24/config_path_display.png`；该离屏环境缺少中文字形，因此截图仅用来检查布局和颜色。
