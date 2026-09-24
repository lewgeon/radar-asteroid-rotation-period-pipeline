# 4.2 代码逻辑与运行稳定性修改方案（2026-09-21）

> 状态：批次 A–F 已在当前工作区落地（不含 inversion 周期估计算法）。验收见 [`../changes/CONFIG_FINGERPRINT_AND_GUI_SEAM_2026-09-21.md`](../changes/CONFIG_FINGERPRINT_AND_GUI_SEAM_2026-09-21.md)。本文件保留原设计说明，不再作为待办清单。

> 本方案基于 `../audits/CURRENT_PROJECT_ISSUES_2026-09-21.md`，但主动排除 inversion 的反演算法、周期搜索策略、科学正确性和最终参数设计。本阶段只保证 observation、echo、GUI 与 pipeline 的逻辑自洽、边界闭合、阶段产物不串用、错误可解释，以及当前生产入口能够被完整交付。

## 1. 本阶段目标与不做事项

### 1.1 要完成的目标

1. 同一个字段在 GUI、根 CLI 和子模块 CLI 中具有相同语义，但校验时点服从入口职责：GUI 与子模块 CLI 只在执行某一阶段时校验该阶段所需内容，根 pipeline 在启动第一阶段前完成全流程预检。
2. observation 与 echo 的输入、输出和复用条件形成闭合契约，旧产物不能在来源不一致时被静默混入新实验。
3. GUI 的阶段运行、保存、复用、取消、失败恢复和动态字段切换不留下隐藏生效字段或错误状态。
4. 自动选时、ADC 行宽、保护时间、Run 数量等边界条件有能区分错误实现的测试。
5. 删除已确认无调用的死代码，迁移冗余字段，保留仍有生产用途或产品归属尚未确认的工具。
6. 在不评价反演算法的前提下，保证 pipeline/GUI 能找到并启动 inversion 入口；入口失败时状态与日志正确收尾。

### 1.2 本阶段明确不做

- 不修改 `inversion/src/inversion.py`、`inversion/src/radar_signal.py` 的周期估计算法、CPI、共识、显著性和计权策略。
- 不确定最终 inversion 配置字段、默认值和搜索范围；pipeline 本阶段只把 inversion 配置当作待后续收紧的透传段。
- 不建立论文级周期反演精度结论，不用当前 mesh 夹具证明周期恢复正确。
- 不删除用途尚未确认的独立研究工具，仅把它们列入后续确认清单。

## 2. 总体设计：把 pipeline 配置与阶段运行做成一个深模块

当前复杂度分散在 `pipeline.py`、GUI、observation/echo normalizer 和三个 CLI 中：每个调用方都知道一点“哪些字段此时该校验、路径相对哪里、旧产物能不能复用”。修改后应把这部分复杂度集中在根 pipeline 模块的一个小接口后面，GUI 与 CLI 都只调用该接口。

建议保留 `pipeline.py` 作为模块入口，不急于拆出多层抽象；新增两个稳定接口即可：

```python
prepare_run(config, *, config_path, run_dir, through_stage) -> PreparedRun
check_reusable_artifact(prepared, *, artifact_stage) -> ReuseDecision
```

`PreparedRun` 隐藏字段归属、阶段化校验、输入路径解析、输出路径、规范化配置和指纹计算；`ReuseDecision` 返回可复用或不可复用及结构化原因，不直接弹窗或写日志。GUI 是界面 adapter，根 CLI 是命令行 adapter，二者经过同一 seam，不再分别猜测规则。

`through_stage` 使用明确枚举 `observation`、`echo`、`inversion`、`full_pipeline`，替换当前语义模糊的 `validate_echo_waveform: bool`。它表示“本次准备要执行到哪里”，不是“所有入口必须得到同一组错误”：GUI 执行 `observation` 时只验证观测解算需要的 observation 字段，带宽大于采样率不能阻止第一阶段；GUI 执行 `echo` 时才验证 observation + echo 及采样率/带宽交叉约束；根 CLI 一口气执行时使用 `full_pipeline`，必须在任何子进程启动前完成全流程预检；observation/echo 子模块 CLI 分别执行与自身阶段相同的校验。选择 `inversion` 时本阶段只检查入口、上游产物与字段段类型，反演参数细则留到后期。

GUI 的“保存配置”与“执行阶段”也不能混为一谈：保存可以保留用户正在编辑的草稿；点击某一阶段时校验该阶段；点击“运行全部”时才做与根 pipeline 等价的全流程预检。这样 GUI 仍承担逐步生成正确配置的职责，不会因为尚未进入 echo 阶段就阻断 observation。

### 2.1 修改后关键工作流推演

| 用户操作 | 修改后的结果 | 对现有功能的影响 |
|---|---|---|
| GUI 中 echo 带宽高于 observation 采样率，单独运行 observation | observation 正常启动，不读取也不校验带宽 | 保留 GUI 分阶段编辑与执行能力 |
| 同一配置随后运行 echo | 在启动 echo 子进程前给出带字段路径的错误 | 更早失败，不产生半成品 echo |
| GUI 点击“运行全部”或根 CLI 不带 `--skip-*` 执行 | 第一阶段启动前完成全流程预检；配置不闭合则一个阶段都不启动 | 避免运行很久后才在下游失败 |
| 根 CLI 使用 `--skip-observation` | 校验当前 echo 配置，并验证已有 observation 产物与当前 observation 有效配置兼容 | 不因跳过计算而跳过来源检查 |
| 根 CLI 同时跳过 observation 和 echo | 不重新用当前 echo 参数判断旧 echo 是否能生成，只验证旧 echo 的阶段记录、文件哈希和 inversion 启动条件 | 避免只跑下游时被无关的待编辑 echo 字段阻断 |
| 生成一次 observation 后反复修改带宽、载频、幅度、散射和计算参数 | 继续复用同一 observation，每次只重跑 echo | 保留参数扫描工作流 |
| 修改 PRF、脉宽、采样率、观测时段、站点或目标状态 | 旧 observation 被判不兼容，要求重跑第一阶段 | 防止脉冲时刻、ADC 行或视线几何与配置不一致 |
| 将一次输入另存为新配置文件 | 文件名不参与产物兼容判定；若“实验名/运行目录”仍指向原 run，可继续复用 | 配置归档不使产物失效；GUI 现有“另存为后同步实验名”会切换到新 run，若要复用旧产物需把实验名重新指向旧 run，除非以后另增“上游来源 run”选择器 |
| 在同一 run 中重复运行 echo | 默认仍覆盖该 run 的最新 echo 输出，同时更新 echo 阶段来源记录；observation 来源记录保持不变 | 保持现有用法，但不会自动保留每次 echo 结果；需要对比历史结果时仍应使用不同 run 名 |
| 打开旧版、没有 manifest 的 observation/echo 文件 | 能从 generated config 重建来源时自动核对；否则进入明确的兼容确认流程 | 旧数据不会被一刀切丢弃，也不会静默冒充同源 |
| 子进程退出码为 0 但主产物缺失 | 阶段记为失败，不写成功 manifest，不继续下游 | 修复 GUI/pipeline 假成功 |

这里的关键限制是：当前 `observation_info.npz` 不只是“纯视线”，还包含脉冲事件、接收窗和 ADC 行映射，所以 PRF、脉宽、采样率等 observation 所有字段变化后不能安全复用。如果以后希望这些发射时序也能在同一份几何数据上扫描，需要把“纯几何星历”和“接收计划”拆成两个产物；本轮不做这种架构扩张。

## 3. 修改批次与依赖关系

```text
A 配置与路径契约
        │
        ├── B 阶段产物指纹与复用
        │        │
        │        └── D GUI/CLI 统一接入
        │
        └── C observation→echo 数据契约
                 │
                 └── D GUI/CLI 统一接入

E 死代码/死字段清理 ── 在 A–D 通过后执行
F 文档与全仓验收 ───── 最后执行
```

不能先做 E：有些看似无调用的字段承担旧产物兼容职责，只有 C 建立新契约后才能安全迁移。

## 4. 批次 A：配置、数值与路径契约

### A1 完整化 observation 静态校验

**修改文件**：`observation/src/config_normalize.py`、`observation/tests/test_observation_info.py`、`observation/tests/test_planning_regressions.py`、根 `tests/test_schema_v4_contract.py`。

`normalize_observation_config()` 应成为 observation 配置的唯一公共接口，在不联网、不计算星历的前提下完成以下静态检查：

- `target`、`transmitter` 必填；receiver 省略表示单站，不再由调用方自行补。
- 各 `state` 所需向量/大地坐标字段必填，向量长度必须为 3，所有数值必须有限。
- chirp 必须同时具有 `schedule`、`waveform`、`radar_system`、`receiver_sampling`；CW 必须具有 `receive`，二者不能混用。
- `prf_hz`、`pulse_width_s`、采样率、保护时间、路径展宽、切换时间和安全余量做有限性与正负范围检查；脉宽不得大于 PRT。
- manual 模式只接受 `runs`；自动模式禁止 `runs`，要求 `run_count`、`run_duration_s`、`end_utc`。
- `run_count`、`random_seed`、`track_id`、`coherence_id` 必须是真正整数，拒绝布尔值和小数，不使用 `int(1.9)` 之类静默截断。
- `random_seed` 只允许出现在 `random_visible_time`；equal 模式不保存无效种子；manual 模式不保存自动选时字段。
- 自动配置若带手写 `runs` 直接报带完整路径的 `ValueError`，不再静默 `pop()`。

配置错误统一包含字段全路径，例如 `observation.schedule.run_count 必须是正整数，收到 1.9`，不得把普通输入错误暴露为 `KeyError`、`TypeError` 或 NumPy 转换异常。

### A2 完整化 echo 静态校验

**修改文件**：`echo/src/config_normalize.py`、`echo/tests/test_echo.py`、`echo/tests/test_cli_smoke.py`、根 `tests/test_schema_v4_contract.py`。

`normalize_echo_config()` 按散射模型检查必填字段和数值域：mesh 要求 `model_path`、`compute`、`target`、`radar`、`waveform`、`scattering_power`；point_target 要求 `point_target.amplitude_scale` 且禁止 mesh 专属字段。设备、dtype、波形类型、输出参考、脉内运动模型、载频、带宽、幅度、SNR 和所有分块大小都要做类型、整数性、有限性和范围检查。

采样率与 chirp 带宽的跨阶段约束仍在执行 echo 阶段时检查；只运行 observation 时不得触发。GUI 不再维护另一份业务校验，只负责把控件文本转换为值并展示深模块返回的错误。

### A3 收紧 pipeline 顶层接口但暂不收紧 inversion 参数

**修改文件**：`pipeline.py`、`tests/test_schema_v4_contract.py`、`tests/test_gui_schema_v4.py`。

`prepare_run()` 先检查顶层容器形状，再按 `through_stage` 调用相应公共 normalizer，而不是无条件规范化三个阶段。`observation` 不得因 echo 的带宽、模型路径或尚未填写字段失败；`echo` 才检查 echo 及 observation→echo 交叉约束；`full_pipeline` 检查所有当前可确定的运行条件。inversion 本阶段只检查是对象并保留原值，不再借机修改算法参数；已有废弃字段提示可以保留，但新参数白名单推迟到反演测试阶段。

删除 `require_sections()`，因为它只是 `canonical_pipeline_config()` 的无人调用转发，没有形成有价值的接口。原 `canonical_pipeline_config()` 可保留为兼容包装，但所有生产调用应逐步切换到 `prepare_run()`；包装在一个版本周期后再决定是否删除。

### A4 统一相对路径语义

**修改文件**：`pipeline.py`、`echo/simulate_echo.py`、`rotation_gui/window/main.py`、根与 echo 配置夹具、README/GUI 手册。

目标规则为：用户配置中的相对输入路径相对“该配置文件所在目录”解析；生成给子进程的配置一律写绝对路径。该规则不能无迁移地切换：解析器先尝试配置目录语义；旧配置只有按既有模块工作目录才能找到文件时，继续兼容并给出一次迁移警告；两处都存在且指向不同文件时拒绝猜测。等仓库内置配置和用户保存配置完成迁移后，再删除旧解析分支。

根 `configs/chirp_mesh_target_test.json` 的模型路径应相对根 `configs/` 调整为 `../echo/models/ellipsoid.obj`；echo 独立配置中的模型路径相对 `echo/configs/` 写为 `../models/ellipsoid.obj`。`simulate_echo.py` 独立运行时也使用配置文件目录解析，不再靠 `cwd=echo/` 恰好找到文件。

**A 批次必须先红后绿的测试**：缺 transmitter、缺 mesh compute、缺 run_duration、`run_count=1.9/true/0`、equal 带 runs、equal 带 random_seed、NaN/Inf、相对模型路径从仓库根和其他 cwd 启动、observation 阶段不检查 echo 带宽、echo 阶段必须检查带宽。

## 5. 批次 B：阶段产物指纹、复用与原子写入

### B1 建立阶段指纹

**修改文件**：`pipeline.py`、`rotation_gui/window/main.py`、`observation/src/observation_info.py`、`echo/simulate_echo.py`，新增根级契约测试。

为每个阶段计算“有效依赖投影”的指纹，不能比较整个 `experiment.json`：

- observation 指纹 = 规范化 observation 配置中实际影响观测产物的字段 + observation 产物契约版本；echo 和 inversion 的任何修改都不能使已有视线数据失效。
- echo 指纹 = 规范化 echo 配置中实际影响回波的字段 + 实际复用的 `observation_info.npz` 文件 SHA-256 + echo 产物契约版本；只修改 inversion 参数不能使已有回波失效。
- inversion 指纹本阶段只记录，不据此评价算法参数。

阶段成功后再写 `stage_manifest.json` 或等价阶段记录，至少包含阶段名、该阶段有效配置快照及指纹、上游文件指纹、输出文件指纹、创建时间和该阶段契约版本。不要使用整个仓库提交号直接使所有上游产物失效；如果需要记录代码提交号，它只作追溯信息，兼容性由阶段契约版本决定。根 `manifest.json` 只汇总已经成功的阶段，不能在子进程启动前宣称产物已经对应当前配置。

### B2 复用不一致默认阻断

`check_reusable_artifact()` 应在启动下游阶段前执行，但只比较上游阶段的有效依赖投影。典型合法流程必须保持可用：先生成一次 observation，随后反复修改 echo 的带宽、载频、幅度、散射或计算参数并重跑 echo；也可以把其中一次完整输入另存为新配置，只要 GUI 仍指向原 run，其 observation 投影一致就允许复用。只有修改了真正影响 observation 的字段（例如时序、采样率、站点、目标状态或接收窗）时，旧 observation 才判为不兼容；同理，只有 observation 产物或 echo 有效配置变化时，旧 echo 才对 inversion 失效。

上游文件不存在、相关阶段指纹不同、上游文件哈希不同或契约版本不兼容时返回不可复用，并明确指出是哪一组上游相关字段变化；不能因为无关的下游字段或配置文件改名而阻断。对没有阶段记录的历史产物，优先从同目录的 `observation.generated.json` / `echo.generated.json` 重建可核对的旧投影；证据不足时 GUI 要求用户显式确认，根 CLI 则要求显式兼容开关，不能把所有历史产物一刀切为不可用，也不能静默假定兼容。

`configs/experiment.json` 可以继续表示当前 GUI/CLI 使用的完整配置快照，允许正常更新；准确来源由每个阶段成功后写入的阶段配置快照和 manifest 保存。重复生成 echo 时更新 echo 阶段记录，不得改写 observation 阶段记录。用户不需要因为只改下游参数就新建 run。

### B3 配置、状态和 manifest 原子写入

**修改文件**：`pipeline.py::write_json`、`rotation_gui/storage.py::write_json`，或让二者共享一个实现。

写 JSON 时先在同目录创建临时文件，flush/关闭后用 `os.replace()` 原子替换；失败则保留旧文件。GUI 会话快照、用户显式保存、生成配置和 manifest 都走同一实现。测试模拟序列化失败和替换失败，断言旧文件未被截断。

**B 批次验收**：只修改 echo 参数时 observation 仍可复用；只修改 inversion 参数时 echo 仍可复用；修改 observation 有效字段后旧 observation 被阻断；改配置文件名但有效投影不变不影响复用；历史产物进入明确兼容流程；子进程失败不会生成“成功”阶段记录；配置写入失败不改变 GUI 当前路径。

## 6. 批次 C：observation→echo 数据契约闭合

### C1 为 observation_info 定义显式契约版本

**修改文件**：`observation/src/observation_info.py`、`echo/src/geometry.py`、两侧测试。

在 metadata 中增加 `artifact_contract_version` 和 observation 配置指纹。echo 加载器按 `data_layout` 分流校验：CW 和 chirp 的必需字段、维度和有限性不同，不再用大量默认数组掩盖当前版本文件的缺键。

chirp 至少守住以下不变量：

- `row_valid.shape == (pulse_count, fast_sample_count)`，metadata 的 `fast_sample_count` 必须等于第二维。
- `row_start_sample`、行偏移、ADC 起止、两类 overlap、路径率的长度都等于脉冲数。
- `fast_sample_rate_hz` 正有限；每个 Run 的 ADC 起止一致且 stop 大于 start。
- 每个有效行索引映射到该 Run 的半开 ADC 区间内；`row_start_sample + column` 不越界。
- `elapsed_s`、`scatter_elapsed_s`、`emit_elapsed_s` 的单调性和事件顺序满足当前三事件几何约束。
- 当前版本的路径率与时标伸缩字段必须有限；只有明确的旧契约适配路径允许缺失后回退。

这会在 echo 入口直接挡住“251 列旧 echo 计划与 252 列新 observation 逻辑混用”一类问题；B 的文件指纹继续负责判断两个不同实验的产物是否来自同一来源。

### C2 把全零回波检查与加噪开关解耦

**修改文件**：`echo/src/echo.py`、`echo/src/point_target.py`、echo 测试。

无论 `snr_db` 是否为 null，生成完成后都计算并记录有效区域信号功率，但不能把“零回波”无条件判为程序错误：无照亮面元、零幅度点目标和诊断性配置都可能是合法输入。默认行为是写入结构化警告和原因线索；只有能证明当前配置承诺非零信号、或用户显式启用严格模式时才失败。该检查不能复用 `snr_db=null` 表达严格性。

### C3 强化接收窗边界守卫

**修改文件**：`observation/tests/test_planning_regressions.py`、接收窗行为文档；通常不需要再改 `planning.py` 的现有补偿公式。

把当前 144 点网格改成能覆盖小数部分临界点的确定性密扫，并加入“守护守护者”断言：同一参数集按故意削弱的补偿常数重算时必须至少出现一个负裕量，证明测试确实能区分错误公式。分别守住前置裕量、后置裕量、末列有效、窗口重叠翻转、单站切换截短和跨 Run 收发冲突。

### C4 收拢预览与正式解算的差异

`resolve_campaign_run_plan` 的预览可以继续用近似传播时延，但返回值和 GUI 必须明确区分“近似可排列数”与“正式计划可行”。对单站跨 Run 冲突，优先在生成候选 runs 后复用正式冲突判据做一次无网络的区间检查；不要让 GUI 显示可行而正式解算立即失败。公共判据抽成 observation 内部函数，由预览和 `plan_reception` 共用，避免复制公式。

## 7. 批次 D：GUI 与 CLI 稳定运行

### D1 GUI 只通过 pipeline 深模块运行

**修改文件**：`rotation_gui/window/main.py`、相关 GUI 测试。

替换 `_validate_config()`、`_warn_if_run_config_differs()` 和 `_run_next_pending_stage()` 中分散的准备逻辑：先按当前待执行阶段调用 `prepare_run()`，再用阶段有效依赖投影调用 `check_reusable_artifact()`，通过后才写生成配置和启动 QProcess。GUI 不比较完整原始 dict，也不自行决定哪些 echo 条件应跳过。运行 observation 时必须继续绕过带宽/采样率交叉检查；运行 echo 或“运行全部”时才执行该检查。

### D2 动态选项不保留隐藏生效字段

**修改文件**：`rotation_gui/window/parameter_form.py`、GUI 测试、两个开发配置。

选时方式切换采用以下保存契约：

- manual：保留 `runs`，移除 `run_count`、`run_duration_s`、`random_seed`。
- equal：保留 `run_count`、`run_duration_s`，移除 `runs`、`random_seed`。
- random：保留 `run_count`、`run_duration_s`、`random_seed`，移除 `runs`。

当前 `_on_schedule_selection_changed()` 在所有自动模式都补 `random_seed`，应改正；两个 equal 模式开发配置中的无效 `random_seed` 同步删除。若希望来回切换时记住旧值，可放在 GUI 私有临时状态中，但不能写入当前规范配置或影响计算。这条规则同样适用于 mesh/point_target、CW/chirp、坐标表示等互斥分支：切换回来可以恢复草稿，但交给 pipeline 的配置只包含当前分支字段。现有 mesh 往返恢复测试应保留，不能因严格 schema 而删除正常的 GUI 草稿记忆能力。

继续沿用项目现有动态表单要求：重建前记录触发控件，重建后恢复焦点和滚动位置；展开必须增加真实可滚动范围，收起保留当次交互达到的范围；切换页面或加载新配置时清空临时空白。

### D3 运行状态机闭合

为 GUI 阶段状态定义明确转换：`未运行 → 校验中 → 运行中 → 成功/失败/已中止`。启动失败、进程崩溃、用户停止、上游不兼容和输出缺失都必须清空 pending stages、恢复按钮、停止进度动画并留下一个最终状态；只有确认主产物存在且进程退出码为 0 才记成功和写阶段 manifest。

### D4 反演阶段只做启动级保障

不修改反演算法，但必须修正 `inversion/.gitignore` 对正式入口的误伤：显式纳管 `scripts/estimate_period.py`，或把正式入口移到未忽略位置。增加一个不评价周期结果的启动烟雾测试：准备最小合法上游文件，确认 pipeline 能构造命令、找到脚本、读取协议行，并在脚本主动报错时正确收尾。后续反演模块重构可以替换脚本实现，但不能让入口再次游离在 Git 之外。

## 8. 批次 E：死代码与死字段处理

### E1 死代码判定方法与可删除候选

死代码判定采用“生产可达性”而不是“有没有直接调用”或“测试有没有覆盖”。检查对象是函数、类、字段以及整条模块链，步骤如下：

1. 建立受支持根清单：GUI 两个入口、根 `pipeline.py`、observation/echo/inversion 正式 CLI，以及当前 README/技术文档明确承诺支持的独立工具；测试文件本身不是生产根，但它可能提示一个公开工具仍有契约。
2. 从根建立静态导入/调用图，包含普通调用、别名导入、Qt signal、回调、子进程脚本、`__main__`、字符串分派、`getattr`、注册表和插件式入口。单个符号零引用是最简单情形，但一整座互相调用的孤岛也可能与所有根断开。
3. 建立配置状态空间：以 normalizer 能产生或接受的规范配置为准，为 waveform、scattering model、单/双站、manual/equal/random 等判别字段枚举合法值；对每条条件边给出一个能满足谓词的配置。存在调用链但谓词在当前 schema 下不可满足时，该边仍不可达。
4. 建立产物兼容根：旧 NPZ/JSON 读取器、迁移 adapter 和保存格式字段即使不从新配置产生，只要仍承诺读取历史产物，就属于兼容可达，不能按死代码删除。
5. 用 GUI/CLI 场景矩阵做动态追踪，并为关键分支放置临时哨兵或变异探针，确认预期配置确实进入该分支。动态未命中只能发现测试缺口，不能单独证明死亡；最终结论必须回到根、调用边和分支谓词的联合证明。
6. 为每个候选生成“可达性证书”：生产根、调用链、进入条件、代表配置/产物、是否文档承诺。只有所有生产根均不可达、没有可满足条件、没有兼容职责且不是公开接口时，才标记为死代码；无法证明的标记为“待确认”，不删除。

判定结果分为五类：`生产可达`、`条件可达`、`兼容可达`、`独立工具可达`、`不可达/可删除`。这能识别用户所说的情形：一条链内部调用完整，但如果整条链与生产根断开、条件又不可能由当前配置满足，它仍是死链。

下表当前只表示最简单的“单符号仓库内部零引用候选”，尚不代表全仓死代码审计已经完成。实施时必须把根清单、调用图、分支可满足性和动态场景记录到变更说明；若发现任何生产或兼容可达路径，立即从删除列表移出。

| 位置 | 处理 |
|---|---|
| `pipeline.py::require_sections` | 删除无人调用的浅转发。 |
| `rotation_gui/qt_compat.py::QT_WEBENGINE_AVAILABLE`、`QWebEngineView` | 当前预览使用外部浏览器/HTML，没有读取这两个占位；删除。 |
| `rotation_gui/qt_compat.py::ALIGN_CENTER`、`KEEP_ASPECT`、`SMOOTH_TRANSFORM`、`PREFERRED`、`STYLED_PANEL` | 删除未使用常量；保留确实在用的 `HORIZONTAL`、`VERTICAL`、`EXPANDING`、`FIXED`、`NOT_RUNNING`。 |
| `rotation_gui/schema.py::STAGE_GROUP_ORDER` | 卡片顺序由 `parameter_form.CARD_ORDER` 提供，删除重复来源。 |
| `rotation_gui/schema.py::EPHEMERIS_FIELD_ORDER` | 无读取方，删除；保留实际使用的默认值。 |
| `rotation_gui/storage.py::flatten` | 无调用方，删除。 |

删除前各写一条 AST/`rg` 零引用检查到变更记录；删除后跑全仓测试。不要继续沿用旧审计中“`parse_finite_number` 无调用”的结论：当前它被多个输入控件实际使用，不能删除。

### E2 兼容迁移后删除

`echo_overlap` 是 `signal_echo_overlap | window_overlap` 的旧兼容合并字段，但目前仍有属性调用、文件写入、文件读取、脚本和测试引用，因此按“是否存在调用/读写”准则它不是死字段，只能作为格式迁移项。建议：

1. 新版 `observation_info.npz` 停止写 `echo_overlap`，metadata 的 `overlap_fields` 只列两类明确字段。
2. echo 的旧文件 adapter 在只有 `echo_overlap` 时保留为 `legacy_combined_overlap` 或等价兼容信息并发出一次警告，不能猜测映射成 `window_overlap` 或 `signal_echo_overlap`，因为合并值无法反推出来源；新文件同时出现三字段时可以验证旧字段等于两者并集。
3. 一个兼容周期后删除 `ObservationInfo.echo_overlap` 和相关测试夹具；当前 `ReceptionPlan.echo_overlap` 属性可在迁移期保留为私有兼容计算，不再作为新文件接口。

`random_seed` 本身不是死字段，random 模式会实际读取它；它在 manual/equal 模式下只是非活动字段，由 A1/D2 的条件 schema 从当前规范配置中消除，必要时仅保存在 GUI 私有草稿中。

### E3 本阶段保留，不按死代码删除

- `parse_finite_number`、`_ALL_STATE_FIELD_KEYS`、`LANES_BY_STAGE`、`_write_cw_preview`、`stations.py`、`SUPPORTED_MODES` 均有当前调用。
- `scatter_receive_rate` 被 chirp 脉内运动计算使用，不是死字段。
- `layout_capacity`、`max_run_duration_exclusive_s`、`pulse_count_per_run` 属于观测计划预览接口，虽调用面窄但有 GUI/测试语义，不在本轮删除。
- `transmit_span_s` 当前主要服务诊断与 JSON payload，可在 GUI 摘要是否使用它确定后再决定；本轮不删。
- `receiver_sampling` 传入 `plan_reception()` 后会实际读取 `complex_sample_bytes`；即使当前严格 schema 不能写入它，这个分支仍然有直接调用语义，因此不能按死字段删除。是否把它正式纳入 schema、改成显式函数参数或固定为内部常量，属于接口设计决定，需要单独评审。
- `echo/src/period.py` 由 `echo/check_period.py` 调用，而后者在 `echo/docs/configuration_and_visualization.md` 中明确作为轻量周期检查工具，因此当前属于“独立工具可达”，不能按死代码删除。
- `echo/scripts/make_simple_chirp_plan.py`、`echo/scripts/create_plotly_notebook.py` 和 `echo/visualize_echo.py` 也有当前文档入口，属于独立工具可达。
- `echo/src/light_time.py` 目前只通向 `echo/scripts/make_static_light_time_geometry.py` 和对应测试，后者没有在当前 README/4.2 使用文档中找到承诺入口，并且正式 echo 已消费 observation 生成的三事件几何；这是一条优先审查的疑似旧版孤岛链，但仍需按生产根、历史产物和脚本用途生成可达性证书后再决定删除。
- `observation/src/plan_campaign_cli.py` 与 `observation/src/orbit_preview_cli.py` 是可执行包装器，但当前 GUI 已直接调用 `campaign_planning`，当前 README 也未找到这两个入口；它们同样列为疑似旧包装器，不能仅因含有 `__main__` 就自动视为生产可达，也不能在未核对历史用途前直接删除。
- inversion 内所有孤岛模块和死代码均延后到反演测试阶段。

## 9. 批次 F：文档、测试入口与验收

### F1 修正文档

修复开放问题文档列出的 D1–D5：`window_overlap` 会因行宽改变而翻转；统一 $\delta\in\{1,2\}$ 的正确结论；符号表补 `+0.5`；CW 行轴字段数改为 12。历史 DATE_LOG 不重写结论正文时，至少在顶部加入后续更正链接。

补充通用字段文档中的 `adc_window_duration_s`，明确它与 `receive_centroid_span_s`、Run 调度时长不同。清理 L1/L2 日期与删除记录口径，但不把临时目录清理伪装成功能修复。

### F2 建立一个全仓测试入口

新增根级 `scripts/run_all_tests.py` 或等价命令，依次在正确工作目录运行根、observation、echo、inversion 四组测试并汇总退出码。inversion 仍运行现有契约/启动测试，但本阶段不以其周期精度作为门槛。README 只公布这一条总入口，同时保留分模块命令供定位。

### F3 GUI 实际验收矩阵

自动化测试之外，按项目规范实际检查常用与窄窗口尺寸：manual/equal/random 往返切换、mesh/point_target、CW/chirp、单站/双站、坐标类型、散射热点、噪声开关、保存/改名/另存为、会话恢复、上游不匹配、缺失产物、进程失败与停止。每个动态控件同时断言当前滚动值、最大滚动值、最后控件相对视口位置和重建后焦点。

## 10. 每批交付门槛

每一批都必须满足：

1. 先有能对旧实现变红的最小测试，再改代码。
2. 只通过公共 interface 验证行为，不复制实现公式做重言式断言。
3. 根、observation、echo、inversion 四组现有测试全部通过；新增总入口也通过。
4. 对数值/默认值变化记录输入空间、边界用例和变异区分力。
5. GUI 改动除测试外必须查看实际界面。
6. 交付前用全新上下文做一次对抗性审查，重点检查隐藏字段、旧产物混用、失败后状态和文档措辞。

## 11. 推荐实施顺序与预计改动面

| 顺序 | 批次 | 主要文件 | 风险 | 是否改变数值结果 |
|---|---|---|---|---|
| 1 | A 配置/路径 | pipeline、两个 normalizer、CLI、配置夹具 | 中 | 只让无效配置提前失败；合法配置应等价 |
| 2 | B 产物复用 | pipeline、GUI main、manifest | 中高 | 不改计算；会阻止过去被允许的错误复用 |
| 3 | C 数据契约 | observation_info、echo geometry/echo | 中高 | 合法同源输入等价；零信号和坏文件改为失败 |
| 4 | D GUI/CLI | GUI main、parameter_form、入口跟踪 | 中 | 不改物理数值；改变字段清理和错误流程 |
| 5 | E 清理 | pipeline、qt_compat、schema、storage、planning | 低到中 | E1 不改；`echo_overlap` 是格式迁移 |
| 6 | F 文档/验收 | docs、README、总测试入口 | 低 | 不改 |

建议不要把六批压成一次大修改。A、B、C 都应独立形成可回退的变更点；D 在它们稳定后接入，E 最后清理旧接口。这样一旦 GUI 或产物兼容出现回归，可以定位到明确 seam，而不是在一次大重构里追踪。
