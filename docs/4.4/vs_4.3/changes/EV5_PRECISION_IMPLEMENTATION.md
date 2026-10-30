# EV5精度策略生产接入与验收

实施日期：2026-10-23（北京时间）。本专题记录A/B的工程移植，保留旧`predictive_joint`默认及`legacy_consensus`对照。没有重新仿真、生成ISAR图像或按真周期选择策略。当前使用说明见[精度策略手册](../../PERIOD_PRECISION_OPTIONS.md)，迁移合同见[接手说明](../plans/EV5_PRECISION_IMPLEMENTATION_HANDOFF.md)。源代码改动尚未提交；`inversion/`是独立Git子模块，需要和根仓库分别保存提交。

## 1. 实施范围

新增`inversion/src/predictive_energy.py`：严格五特征、Run内归一权重、按平均特征时刻五折、固定H1/2/4/8、float64带权SVD、正预测增益平方和及固定dense8搜索协议。新增`spherical_response.py`：显式极轴、严格100Run×5CPI/近单站合同、原LOS分量插值、单位CPI权重、中心化SVD岭回归、整Run留出、固定L/α及全部局部极小细化。共享ADC、真实回波重叠、缺样、重复和不支持输入明确拒绝。

新增`precision_selection.py`统一分派，在`inversion.py`复用原特征和几何；`dataset.py`扩展枚举及首版限制，固定阶数不受旧单值H覆盖。新选择器当前运行在CPU；前端或独立特征使用CUDA不改变该事实。`period_uncertainty.py`显式返回新策略重采样尚不可用，不进入旧投票分支。CLI保存实际策略、自动阶数、先验、候选、通道诊断和失败状态。GUI增加显式选项和B必需的极轴输入，保留配置、焦点和滚动行为；球面响应不显示无效的半转补偿约定。

新增`scripts/verify_ev5_precision.py`用于已有噪声缓存的工程回归。它使用共享设计、多右端QR及SVD秩保护的批量同数学实现，可选CPU/CUDA，胜点再由生产SVD独立核对评分。这种验收不能单独声称800次直接调用生产完整搜索；其桥接证据是独立目标函数对照、区分分支的合成完整搜索及生产无噪完整金值。

## 2. 输入身份与无噪完整搜索

历史金值来自冻结的干净特征缓存，而`period_observables.npz`中的`value`来自微小差异的重提取。两种输入不能混称字节相同；400m原value与缓存的J差约1.1037×10⁻⁸，略超过严格金值评分容差。因此严格金值使用对应缓存，原value另列完整搜索结果，不放宽容差、不修改历史金值。两例LOS及搜索域沿用交接规定。

| 输入 | 策略/阶数 | 本次周期(s) | 本次评分 | 验收意义 |
| --- | --- | ---: | ---: | --- |
| 70m干净缓存 | A/H2 | 10806.327573135564 | J=0.13921082529224485 | 同身份冻结金值，周期差<0.01s、评分差≤10⁻⁸ |
| 400m干净缓存 | A/H8 | 13408.502628465269 | J=1.0193027834601618 | 同身份冻结金值，周期差<0.01s、评分差≤10⁻⁸ |
| 70m原value | A/H2 | 10806.327576569362 | J=0.1392108246217193 | 生产原输入完整搜索，不冒充缓存同身份评分 |
| 400m原value | A/H8 | 13408.50262634556 | J=1.0193027944973916 | 同上 |
| 70m冻结研究输入+原LOS | B/L4 | 10801.701662129739 | CV=0.9073085912889667 | 最终稳定缩放源码完整搜索，周期/评分容差通过，α逐通道相同 |
| 400m冻结研究输入+原LOS | B/L6 | 13405.246840937803 | CV=0.5397977099705364 | 同上 |

表中A的J越大越好，历史方案A的CSV/JSON `score`为−J；B的CV损失越小越好。0.01s只用于移植一致性，不是测量精度保证。原输入路径为`runs/ev5_snr_20261016_70m/`和`runs/ev5_snr_longcpi_20261016_400m/`，缓存为对应`tmp/receiver_snr_ev5_*_20261016/`。SHA256、执行时间、源码身份与机器可读比较归入本专题`data/`附件。

无噪附件为[A三次已完成搜索及输入身份](data/2026-10-23_EV5_ENERGY_GOLDEN_STAGE.json)、[A最终400m干净缓存及CLI工程验收](data/2026-10-23_EV5_ENGINEERING_ACCEPTANCE.json)和[B最终源码两例完整搜索](data/2026-10-23_EV5_SPHERICAL_GOLDEN.json)。A阶段记录原计划顺序执行四次搜索，并发资源失败后保留前三次结果；第四次以独立pytest重新完成，不将部分JSON误称为四次全部完成。

## 3. 工程回归与边界

方案A的800份冻结带噪输入已完成同数学批量全搜索回归，并逐输入用生产CPU SVD复核胜点评分；周期容差0.01s、H必须相同、J及CPU复核差均不大于10⁻⁸。800条全部满足上述条件，未修改金值或缩窄搜索域；保留低SNR错峰结果，不按真周期删行。全体最大周期差为2.122×10⁻⁵s，最大J差为2.084×10⁻¹⁴，最大生产SVD胜点评分差为1.111×10⁻¹⁵。此处“通过”指移植回归，不能解释为800次测量都达到物理精度要求。

| 输入批次 | 原协议SNR与重复数 | 回归通过/不一致 | 本次运行时长(s) | 逐次证据 |
| --- | --- | --- | ---: | --- |
| 70m | 0/10/20/30dB，各100次 | 400/0 | 949.597 | [70m逐次结果及身份](data/2026-10-23_EV5_ENERGY_NOISE_70M.json) |
| 400m | 0/10/20/30dB，各100次 | 400/0 | 1593.336 | [400m逐次结果及身份](data/2026-10-23_EV5_ENERGY_NOISE_400M.json) |

两批使用同一目标函数和协议；70m批量块为128、400m为32，均使用CUDA QR、SVD秩检查与直接残差。它们是不同规模和资源状态下的运行记录，不是同会话性能A/B；不据此声称速度提升。70m执行期间验收工具的极轴读取仍是固定值代码，但该例关闭LOS；后续400m改为从反演配置读取RA/Dec/周期约定，各自源码身份保存在附件。生产CPU选择器源码不因这项验收工具调整改变。

数值测试以独立`numpy.linalg.lstsq`对照A多右端SVD，以实际逐Run删除、增广最小二乘重拟合对照B的平滑矩阵块残差。夹具断言对LOS、周期、H、α及不同输入扰动确实敏感；搜索协议测试独立核对A前三峰/端点与B全部极小/端点。非有限/缺样、非正权、常数、重复、秩亏、无正增益、LOS外推、零方向、极点、双站夹角与不支持组合均有对应检查。

本次最终相关组合回归为65项通过、4项显式跳过，79.73s；命令是第5节首条pytest，原实验数组的完整金值和固定候选噪声检查需要另设环境变量执行，跳过不计通过。之后仅将误差页教学展开说明明确为旧策略实现，新策略本次未计算该诊断；对应两策略页面断言重新执行2项通过，不与组合数量相加。结构化命令、源码身份及结果见上述工程验收附件，原始日志留在`tmp/`。

GUI在650×500与1100×850窗口实际运行事件循环，重复切换新旧策略，核对极轴显隐、焦点、滚动位置、控件可达、保存及重载；截图已查看。70m真实CLI复用原回波的有效前端缓存，A/B分别返回约10806.327576s及10801.701662s，实际策略、HTML、JSON和完成标志均保存成功。它证明真实入口和原前端缓存衔接，不表示本次重算了全量IQ。另用真实CLI构造不支持逐脉冲输入，确认新策略错误退出、保存失败原因且不生成完成认证。

资源恢复后按当前源码再次运行70m A与400m B的真实CLI，分别返回H2约10806.327576s和L6约13405.246841s，策略、自动阶数、先验、未校准状态与完成认证核对通过。两份自生成结果的误差页再用最终说明文字重新渲染，数值及选择报告未变，工程附件保存对应配置、命令、来源回波身份和结果哈希。

本轮一次混合测试曾出现Qt全局字体注册影响后续标题高度的失败；新增GUI测试已恢复字体资源，组合回归重新通过。另一次根测试与子模块同名`tests`包导致收集失败，改用`--import-mode=importlib`执行；收集失败不计为通过。

并发完整搜索与旧大数组回归曾耗尽系统内存，产生NumPy分配失败及CUDA资源错误；对应CLI重跑和混合测试未计入成功。停止并发大作业后，旧算法冻结回归单独执行通过（1项，10.85s）；400m批量噪声回归改为独占GPU运行。耗时仅是本次资源状态记录，不用于声称性能收益。

## 4. 对抗性审查

按验证技能使用全新上下文代理审查实现、输入空间和验收强度。审查发现并修复：B被不参与自身模型的旧LOS阈值提前拒绝；A未传递用户`refine_period=False`导致元数据失真；B摘要误显示Run不足且把五项响应特征称为正增益通道。另将新策略首版限制为`spectral_moments`，避免把低频有效带宽误作冻结RMS带宽合同。复查未发现其他确定代码阻断问题，并明确800批量验收的证据边界。

后续边界检查还修复了原始有效样本数被旧预处理epsilon截断隐藏，以及B极端幅度的标准差溢出/下溢。B通过安全非零通道缩放修正；两例×5阶×18频率×3幅度共540次修正前后扫描的最大目标差约1.11×10⁻¹⁵、α无失配，并在最终源码重新完整搜索通过。B首版的正α岭正则允许非截距设计秩不足；不能把A的满秩拒绝条件误写成B也拒绝全部秩亏。

[稳定缩放扫描附件](data/2026-10-23_EV5_SPHERICAL_SCALE_SCAN.json)保留阶段记录及可恢复源码；其`record.scope`中的“完整搜索属于此前源码”只描述扫描发生时，最终源码后续完整搜索已独立写入上面的B金值附件。恢复`reproduction_source.utf8_source`到`restore_path`并核对SHA256后可重建扫描，原始数组身份沿用B金值附件。验收脚本`verify_ev5_precision_clean.py`的SHA计算另改为分块读取，避免一次加载数GB回波；1MiB以上夹具与整文件SHA256结果一致，该修改不改变搜索。

## 5. 可复现命令

Python使用Conda `pytorch`环境；NumPy/SciPy/PyTorch均由该环境提供。为避免CPU BLAS多线程调度开销，完整数值验收在独立进程启动前设置以下环境变量，不改生产数值策略：

```powershell
conda activate pytorch
$env:OMP_NUM_THREADS="1"
$env:MKL_NUM_THREADS="1"
$env:OPENBLAS_NUM_THREADS="1"
python -m pytest --import-mode=importlib tests/test_precision_integration.py tests/test_predictive_energy.py tests/test_spherical_response.py inversion/tests/test_joint_period.py inversion/tests/test_period_uncertainty.py tests/test_optional_period_precision.py tests/test_period_uncertainty_experiment.py -q
$env:EV5_FULL_REGRESSION="1"
python -m pytest tests/test_predictive_energy.py -k frozen_clean_full_search -q -s
$env:EV5_SPHERICAL_GOLDEN="1"
python -m pytest tests/test_spherical_response.py -k frozen -q -s
python scripts/verify_ev5_precision.py --case 70m --device cuda:0 --batch-size 128 --output tmp/ev5_precision_implementation_20261023/a_noise_70m_full.json
python scripts/verify_ev5_precision.py --case 400m --device cuda:0 --batch-size 32 --output tmp/ev5_precision_implementation_20261023/a_noise_400m_full.json
python scripts/check_doc_math.py
```

完整金值测试依赖原本机研究数组，默认跳过不能算通过；缺数组时须按历史实验入口恢复原输入身份，不构造替代数据。噪声脚本保留每次周期、H、评分、CPU胜点评分差、失败记录和输入/源码SHA，不改变历史CSV。CPU回退将`--device`改为`cpu`。

## 6. 结论边界与剩余工作

本轮只证明声明输入上的移植一致性和接口行为，保留70m低SNR错峰、400m残余偏差及B噪声证据有限等负结果。B在400m trial0的10/20/30dB另完成全部已有L候选处评分及α对照，这只是固定候选目标函数复核，不是带噪完整搜索。未知轴、大双站角、未见形状/计划、实测校准、共享ADC计权、最终误差覆盖率和连续全域最优认证均未完成；不承诺普适0.1%精度，不自动切换默认，不输出总误差保证。

<a id="independent-review-20261024"></a>

## 7. 2026-10-24独立审查：核心移植一致，误差展示仍有缺陷

审查基线为根仓库`7446059`及`inversion`子模块`3082666`，范围为当前未提交的4.4精度接入，包含新增未跟踪文件。按规格与规范两轴使用全新上下文代理，未修改被审生产源码。前述2026-10-23记录原样保留，本节是后续独立阶段，不覆盖历史结果。

规格轴：未发现已复现的核心数学违约。A的权重、均值时刻分折、H集合、J及完整搜索协议与合同一致；B的岭权重、整Run删除、标准差归一和独立搜索协议通过针对性核对。另从原始y/w独立重算A的4个H×3周期，归一数值差最大4.87×10⁻¹²；错误权重和错误分折对照会产生明显差异，夹具能够区分目标分支。未发现利用生成真周期或隐藏极轴先验的选峰路径。

规范／集成轴发现一个确定P2：`inversion/scripts/estimate_period.py:493`把新策略尚未实现重采样的`unavailable`译为“观测不足或不可识别”；`inversion/src/period_uncertainty.py:191`附近把缺失统计显示为Run数量0、0%命中率，启用重采样时还写“未通过单峰条件”。两策略500CPI/100Run输入均已复现。它没有改变周期计算，却把“没有计算”误报成观测或统计结论，必须在发布前修复；本次审查未替实现者改代码。建议按`reason`区分未实现／未执行／输入不可用，缺失统计显示“未计算”，仅真正运行过单峰检验后才显示通过／失败。

本次重新执行第5节相关组合测试：65通过、4跳过，80.11秒。随后显式启用`EV5_FULL_REGRESSION=1`，另外执行两份A生产CPU SVD完整搜索：2通过，212.69秒；70m为H2、10806.327573135564秒、J=0.13921082529224485，400m为H8、13408.502628465269秒、J=1.0193027834601618，同身份金值容差均满足。未把跳过算通过，也不将不同命令的通过项累加成单次结果。

本轮没有重新执行800份噪声全搜索、B两份完整金值搜索或完整真实GUI人工检查；不能把2026-10-23的这些记录说成本轮重验。新增[短观测实验](https://github.com/lewgeon/radar-asteroid-rotation-period-pipeline/blob/codex/short-arc-research/docs/4.4/vs_4.3/experiments/reports/2026-10-24_SHORT_ARC_IDENTIFIABILITY.md)进一步证明原合同不能直接当实测可靠性保证：A按合同因个别候选数值退化整体拒绝，默认也可返回错误候选。移植符合合同与合同适用于短观测是两个不同结论。

[本轮冻结审查证据](data/2026-10-24_EV5_PRECISION_REVIEW.json)保存源快照／哈希、独立复算和展示复现源码、组合与完整金值日志。复现展示缺陷使用`conda run -n pytorch python tmp/20261024_precision_review/standards/reproduce_uncertainty.py`；临时源码缺失时可从附件`sources[path].utf8_source`恢复并核对哈希。短观测数据和新推导归入实验专题，不混入本节生产金值。

<a id="short-arc-branch-split"></a>

## 8. 2026-10-30工作线拆分与恢复

用户决定在4.4保留A/B，短跨度实验保存为研究支线。主仓库研究快照为`a7d3be9`，其`inversion`子模块指向`c4399c8`，两仓库分支均命名为`codex/short-arc-research`。当前`chirp-pulse`保留`predictive_joint`默认、`legacy_consensus`、A及B；`profile_confidence_set`和`profile_confidence`配置明确拒绝，GUI仅提供前述四项。A/B的数值组件与分派模块保持研究快照中的实现，未调整数值搜索、评分或默认策略。

研究分支保存集合算法、MPFR依赖、专属运行器与测试、冻结配置和结果，以及含短跨度章节的原综合报告／Word版。当前综合报告保留基线与A/B部分，其他主题的文献研究与待实施计划保留。外部IQ、缓存和日志未迁移或删除；分支只保存代码与仓库内证据，切换分支不启动计算。两个分支均为本地保存，尚未推送GitHub；归档网页链接需在推送研究分支后才能在线访问。

在两个仓库工作区均干净时，从项目根目录查看研究快照：

```powershell
git switch codex/short-arc-research
git submodule update --init inversion
```

上述命令将反演子模块检出至快照提交。需要继续修改研究代码时，在`inversion`内执行`git switch codex/short-arc-research`。返回当前工作线：

```powershell
git switch chirp-pulse
git submodule update --init inversion
```

本次验证只针对工作线隔离与既有A/B实现保留，不声称精度或性能改善。相关回归命令如下，实测67项通过、4项跳过，67.11秒；跳过的完整数据回归未在本次执行。GUI测试运行真实Qt事件循环，检查四项选择、展开极轴、焦点、滚动、保存和重载，截图已查看；CLI测试实际执行A/B不支持输入的失败路径。全新上下文审查独立执行集成测试14项通过，并核对三个核心模块与研究快照归一化换行后相同。结构化证据见[拆分验收](data/2026-10-30_SHORT_ARC_BRANCH_SPLIT.json)。

```powershell
$env:TEMP = Join-Path (Get-Location) 'tmp'
$env:TMP = $env:TEMP
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:OPENBLAS_NUM_THREADS = '1'
conda run --no-capture-output -n pytorch python -m pytest --import-mode=importlib tests/test_precision_integration.py tests/test_predictive_energy.py tests/test_spherical_response.py inversion/tests/test_joint_period.py inversion/tests/test_period_uncertainty.py tests/test_optional_period_precision.py tests/test_period_uncertainty_experiment.py --basetemp=tmp/split_precision_pytest_recheck -q
conda run --no-capture-output -n pytorch python scripts/check_doc_math.py
```
