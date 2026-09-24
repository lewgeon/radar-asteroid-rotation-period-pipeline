# GUI 单位下拉顺序与宽度

脉冲宽度的下拉项现按倍率递减排列为 s、ms、µs，与其他可选单位字段一致。`UnitValueWidget` 仍按数值自动选取适合的初始显示单位，保存和计算继续使用秒。

可选单位框从 76 px 收窄至 64 px，固定单位框从 44 px 收窄至 32 px，左右内边距和下拉箭头区域同步缩小。最长的原显示标签「π rad」缩写为「π」，下拉提示说明其含义；倍率仍是 180°，配置语义未变。

验收命令：`conda run -n pytorch python -m pytest tests/test_gui_schema_v4.py -q`，结果为 73 passed；全仓使用 `conda run -n pytorch python -m pytest -q`，结果为 146 passed。全仓测试前通过临时 `GIT_CONFIG_*` 环境变量将本仓库及 inversion 子模块加入 Git 安全目录，以适应执行账户与仓库所有者不同的环境；没有修改全局 Git 配置。测试覆盖所有可选单位的倍率顺序、脉宽下拉项次序与数值换算、两类单位框的宽度、初始相位 π 倍率和 GUI 配置采集。
