# GUI 产物状态与轻量复用检查

2026-10-12实施GUI状态与根pipeline轻量复用检查；当时同时修改echo来源字段的范围扩大已于2026-10-23复核并撤回。当前echo沿用4.2提交`7309781`，GUI与根流水线的响应优化保留。本专题不涉及科学算法、回波数值或内存分块定义。下方原始测量及阶段验收保留其日期和作用域，原材料位于忽略的`tmp/gui_responsiveness/`。

## 问题与输入范围

用户报告切换阶段和点击运行卡顿。旧 GUI 的 `_refresh_saved_run_status` 在主线程调用 `prepare_run`，每次完整读取 3,540,199,624 字节回波及 419,434,476 字节观测产物算 SHA256。实际启动反演前，配置校验、准备、上游复用及结构检查共请求 3 次回波摘要和 3 次观测摘要，约重复扫描 11.9 GB。旧结构检查还为了形状读入整份 IQ 和观测掩码。表单重建约几十毫秒，不能据此把十几秒卡顿归因于布局。

当前改动仅作用于GUI与根`pipeline.py`的CW／Chirp状态、阶段成功记录和复用判断，不要求echo改变来源字段。直接反演算法、IQ生成计算及参数定义没有变化。GUI状态、根流水线准备和复用不扫描信号文件内容；小配置JSON的`canonical_fingerprint`／`config_sha256`仍是参数编码，不是信号文件完整性校验。echo独立生成阶段保留4.2的输入SHA检查，不把后台生成任务的检查等同于GUI主线程卡顿。

## 当前策略与兼容

根流水线的新成功记录保存参数投影及`output_identity={path,size_bytes,mtime_ns}`；其echo阶段参数投影保存`observation_info_identity`，反演阶段保存`echo_identity`。这些字段由根流水线自己生成，不要求echo NPZ使用同名字段。4.2 echo仍在读取观测文件前后计算SHA，并在回波中保存`observation_info_sha256`。根流水线支持该产物格式，同时保留对历史属性身份字段的兼容。根复用判断只需`stat`；路径、大小或修改时间改变时按新文件处理，内容变化但这些信息全部保持不变不在属性检查的检测保证内。

结构检查仍保留脉冲数、行宽、整数元数据、快时间坐标长度及逐行 ADC 起点匹配。IQ 和 `valid_plan` 形状从 ZIP 内 NPY 头取得，不物化完整数组；小规模坐标及元数据仍正常读取。CW 沿用原无二维行轴契约的分支，回波来源身份和阶段记录由上层复用策略负责。

观测重跑成功后，回波和反演记录带 `invalidated_by=observation`；回波重跑成功后，反演带 `invalidated_by=echo`。旧下游文件保留，GUI 明确显示需重跑，复用开关也不能绕过失效标记。重新成功生成该下游时才写入新的有效记录。只删除旧记录会被 GUI 的无记录兼容分支误认成新基线，此缺陷由独立审查发现并用 tombstone 修复。

根流水线不追加核验既有SHA来源字段的文件内容，这是原兼容策略，不代表echo独立生成时取消SHA检查。旧echo／inversion记录按保存的配置投影兼容，已有上游记录的参数必须匹配，且上游生成时间不能晚于旧下游；缺少历史时间证据时不自动认定依赖有效。旧参数不匹配仍阻断。缺少参数指纹的历史产物沿用已有确认／`--allow-legacy-reuse`流程；明确失效产物不接受这一开关。CLI全流程结束时使用刚生成的回波身份重算反演指纹，不使用启动前旧回波的身份。

<a id="验收"></a>

## 2026-10-12阶段验收（历史，echo字段修改已撤回）

| 操作，实际 `seperate_observation_2` 文件 | 修改前单次测量 | 修改后单次测量 |
| --- | ---: | ---: |
| 构造同配置窗口 | 8.993 s | 0.068 s |
| 切换回波阶段 | 11.849 s | 0.038 s |
| 切换反演阶段 | 12.628 s | 0.024 s |
| 阶段状态刷新 | 13.903 s | 0.013 s |

诊断阶段同一份配置以本次已测出的相同摘要作对照，切换用时 0.023–0.047 s，确认旧耗时由内容摘要读取导致。修改后所有切换和刷新调用文件摘要次数为零。实际 Run 按钮路径拦截子进程 `start` 和生成配置写入，保留真实校验及结构检查，成功请求启动一次，约 0.027 s、文件摘要请求零次；没有重跑算法。表中是单次响应证据，测量时点和系统负载不同，不提供性能倍数或任意硬件延迟上界。

当时新增`tests/test_artifact_identity.py`验证无内容扫描、契约检查不访问IQ／掩码数组数据、mtime变化拒绝、回波参数变化拒绝、只改反演参数允许、旧哈希忽略但旧参数仍校验、旧下游不能绑定新上游记录、上游成功使下游显式失效，以及真实GUI刷新／切换不得把失效echo重新标成已运行。现有schema和GUI复用测试同步采用身份字段；原“匹配参数但缺哈希必须确认”测试改为可复用。当时echo CLI检查新来源字段的实现已于10月23日撤回，当前echo保留4.2的SHA字段；最终回退及本次验收见[收尾复核第5节](../audits/RELEASE_READINESS.md#5-用户复核后撤回echo的43改动)与[当日日志](../logs/2026-10-23_LOG.md)。

最终根目录四个相关测试文件合跑 133 项通过（包含 identity 的 6 项，不重复相加）；echo CLI 小规模测试 2 项通过，实际生成和回波来源记录正常。全新上下文审查复跑 identity 的 6 项通过，确认上游显式失效和 GUI 无记录兼容之间的交付阻断已解决。当前版本 Markdown 公式验收通过。

验收命令使用 Conda `pytorch` 环境；根测试和 echo 子仓库测试分开运行，不重复计算科学任务。

```powershell
conda activate pytorch
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:QT_QPA_PLATFORM = 'offscreen'
python -m pytest tests/test_artifact_identity.py tests/test_artifact_contract.py tests/test_schema_v4_contract.py tests/test_gui_schema_v4.py -q -p no:cacheprovider
Push-Location echo
python -m pytest tests/test_cli_smoke.py -q -p no:cacheprovider
Pop-Location
python scripts/check_doc_math.py
```

独立审查使用全新上下文，指出旧下游兼容和 CLI 执行后指纹问题，均已处理，并补上 GUI 失效标记回归。该修改解决已定位的切换与启动前校验卡顿；“查看回波”及回波成功后的同步预览仍需完整读取及处理信号，不在本专题中宣称后台化或响应保证。

<a id="result-popup-responsive-20261016"></a>

## 2026-10-16 图像结果卡片的首次响应与切换关闭

用户反馈首次展开卡顿、重复点击同一按钮反而重新打开。先用真实事件循环复现两项失败：旧入口在主线程调用Run目录与已保存结果状态检查；重复调用会隐藏并销毁旧弹窗后立即新建。卡片排版本身不是主要耗时，冷状态模块首次导入和检查CPI／检查文件发生在显示之前。

现将目录、CPI、完成标记、报告与缓存可用性读取放到单后台执行器，主线程只创建控件并通过Qt定时器接收当前请求结果。首次显示时暂用读取状态，完成后更新；新请求取代旧请求，关闭／切换实验时丢弃过期结果。数据读取仍保留原身份与完成检查，不通过少查文件来制造响应收益。原始回波的文件存在检查也在后台；卡片显示不加载IQ或执行脉压／FFT。

同一按钮可切换展开／收起，Popup禁止关闭鼠标事件重放，防止外部按下按钮关闭后又触发一次打开。Esc、外点和关窗仍能关闭。初始化占位CPI时阻塞信号，避免弹窗尚未赋给窗口时触发状态请求；回归把Qt槽中被吞掉的异常也作为失败。

同次会话、同本地100Run／500CPI作业、独立冷进程的同步／后台查询对照：同步入口返回2.869384秒、首次事件泵完成2.890921秒；后台入口返回0.019829秒、首次事件泵完成0.046476秒，状态全部就绪2.933218秒。最后一项表明检查工作没有消失，只移出阻塞绘制的路径；这些是该机器与作业在Monte Carlo负载下的一次测量，不作通用时延保证或科学计算加速承诺。

复建：Conda pytorch环境执行 `python -m pytest tests/test_result_popup_interaction.py tests/test_readonly_result_contract.py tests/test_result_workflow.py tests/test_result_service.py -q -p no:cacheprovider`。本阶段先前相关41项通过；补充后台阻塞时的心跳／Esc／外点／关窗与主线程文件stat拦截后，专门3项通过，不能相加成一次总数。计时脚本及JSON为 `tmp/benchmark_result_popup_20261016.py`、`tmp/result_popup_sync_20261016.json`、`tmp/result_popup_async_20261016.json`；带微软雅黑的真实结果菜单截图为 `tmp/result_popup_async_20261016.png`，已实际查看。最终全量与独立复核另记本日日志。

计时与源码身份冻结于[结果卡片证据](data/2026-10-16_RESULT_POPUP_TIMING.json)。最终根tests完整执行322通过／1可选浏览器引擎跳过，其中包含本卡片测试和新增Monte Carlo测试，不与先前41／3项累加。对抗审查已复核后台查询、关闭切换及原结果读取契约；科学计算没有移入该状态查询任务。
