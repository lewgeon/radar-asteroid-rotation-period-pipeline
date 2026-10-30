# EV5精度改进算法的生产接入说明

本页保留2026-10-23交接时的数学合同和历史状态；当日后续已接入的实现与实际验收以[生产接入证据](../changes/EV5_PRECISION_IMPLEMENTATION.md)为准，当前用户行为见[精度策略手册](../../PERIOD_PRECISION_OPTIONS.md)。下文“尚未实施”均指交接编写时，不覆盖后续状态。

EV5目标本身已经用于4.3的参数仿真、周期反演及蒙特卡洛实验。本文只交接后续精度研究原型的生产接入，不是接入EV5参数、模型或观测实验的计划。

整理日期：2026-10-23。状态：**数学模型、研究原型及固定数据验证已完成；生产代码、CLI和GUI接入尚未实施。** 本文是下一位AI的实施入口，汇总本次编码所需规则。阅读本文、仓库[AGENTS.md](../../../../AGENTS.md)及待修改代码即可开始，不必通读两份长文档；原始推导、历史方案和全部实验只在第7节按需查证。本次整理没有重新运行科学实验，也没有改变冻结结果。

## 1. 要做什么，已经做到什么

优先把方案A“多谐波正预测增益融合”接入既有反演。它保留五项CPI特征、原观测与LOS设置，通过改变拟合模型和选峰评分改善周期精度。新增显式策略`predictive_skill_energy`，保留旧`predictive_joint`默认；这两个名称中前者是待实现配置。方案B`spherical_response`是已知极轴时的独立选项，先完成A，再实现B，不依B完成A。不要按已知真值或本次SNR结果自动切换算法。

本轮不要求重新仿真、生成ISAR图像、估计三维形状、补形状反演接口、实现噪声底／迹校正或建立总误差保证。原计划第1—11节的研究路线不是此次编码依赖。实现者需要完成工程回归，不需要重新选择数学路线或重复一轮方法研究。

| 固定仿真输入 | 原生产无噪误差 | 方案A统一搜索协议的无噪结果 | 方案B无噪结果 |
| --- | ---: | --- | --- |
| 70m，完整周期10800s | 46.721921% | H2，10806.327574596s；0.058589% | L4，10801.701662s；0.015756%，**新增已知极轴先验** |
| 400m，完整周期13410s | 0.101260% | H8，13408.502629383s；0.011166% | L6，13405.246841s；0.035445%，沿用已知极轴 |

还完成了800份历史带噪输入的配对比较、独立CPU评分复核及网格对照。上述真值只作评价，不进入搜索或选阶。方法族是在这两份数据上探索确定的，结果属于同场景回测，不是对未见目标的精度保证。噪声校正趋零时不能消除无噪目标自身的偏差；本轮因此直接改模型与评分，并已取得同数据改善。

## 2. 方案A：完整实施规则

### 输入和固定设置

从`period_observables.npz`读取`value`、`time_elapsed_s`、`run_id`、`effective_sample_count`及`feature_names`。通道固定为总功率、多普勒质心、RMS多普勒带宽、距离质心、90%距离能量宽度，按名称映射，不凭列号猜测。保留全部500CPI及100个Run，不先平均成100点。每个Run内将原有效样本权重归一为和1。

以各Run的**平均特征时刻**排序，从0编号，以编号模5分折；同Run全部CPI在同折。这与原型一致，本批按中位时刻排序也得到相同次序。采用float64；每折带权QR／SVD求解五个右端，不显式求正规方程逆，不增加每Run自由截距或自由相位。

相位沿用`effective_look_phase`，70m关闭LOS补偿，400m开启并从反演配置读取RA105°、Dec−66°及`phase_period_convention="full_rotation"`。函数返回的相位偏移$o_i$已经有负号；完整自转用乘数1，不能再乘2。下面$t_i$是原散射特征时刻，参考计算直接取原`time_elapsed_s`，不重排或重置每Run时标。

### 唯一目标函数

设$y_{ic}$为CPI $i$的通道$c$，$g_i$为Run，$w_i$为原权重，$f=1/P$为待估频率，$H\in\{1,2,4,8\}$。定义：

$$
\widetilde w_i=\frac{w_i}{\sum_{j:g_j=g_i}w_j},\qquad \psi_i(f)=2\pi f t_i+o_i,\qquad X_H(f)_{i,:}=[1,\cos\psi_i,\sin\psi_i,\ldots,\cos(H\psi_i),\sin(H\psi_i)].
$$

对留出折$V_k$，仅在其余折用$\widetilde w_i$拟合系数$\widehat\beta_c^{(-k)}$，同时计算训练折带权常数均值$\overline y_c^{(-k)}$。五折累计：

$$
E_c(f,H)=\sum_{k=0}^{4}\sum_{i\in V_k}\widetilde w_i[y_{ic}-X_H(f)_{i,:}\widehat\beta_c^{(-k)}]^2,\qquad D_c=\sum_{k=0}^{4}\sum_{i\in V_k}\widetilde w_i[y_{ic}-\overline y_c^{(-k)}]^2.
$$

$$
s_c(f,H)=1-\frac{E_c(f,H)}{D_c},\qquad J(f,H)=\sum_{c=1}^{5}[\max(s_c(f,H),0)]^2,\qquad (\widehat f,\widehat H)=\operatorname*{argmax}_{f,H}J(f,H).
$$

返回$\widehat P=1/\widehat f$。$D_c$不随频率或H改变；周期与H均由同一J选择，不选完H后改用全数据RSS定频。含截距的$E_c/D_c$对每通道非零仿射变换不变，可作数值缩放。J是描述性评分，不是概率、逆方差似然或无偏定理；五个特征也不是五份独立观测。证据CSV中的方案A `score`保存的是**−J**，回归时必须核对符号。

### 数值搜索和边界

1. 在配置完整频率域`[1/period_max_s, 1/period_min_s]`取均匀频率网格，点数`8*(period_grid_size-1)+1`。70m为1800—14400s／31993点，400m为1800—28800s／63993点；不是均匀周期网格。
2. 每个H计算全格J，以`scipy.signal.find_peaks`对应规则识别局部极大，选格点评分最高的3个不同局部候选，并加入两个端点；不足3个则全部保留。在相邻格点形成的**周期P区间**做42轮黄金分割，端点用单侧区间，保留原格点与细化结果中较优者。不同H按同一J排序；精确同分时先取较小H，再取较短P。
3. 输出`search_protocol="dense8_top3_endpoints"`、所选H、候选P、各通道E/D、s、正增益平方、总J、括区和细化状态。4倍网格与无噪全峰搜索只是已有数值对照，不替换最终协议，也不声称连续全域认证。
4. 首版要求Chirp CPI、五项完整有限特征、正权重、至少10个有效Run及每折满秩可估。常数／近常数、仿射重复通道、缺样、秩亏、不支持的输入或全域无正增益要明确拒绝／标记，不按候选临时删通道，不静默回退到旧算法后继续标新策略。沿用旧通道预处理与去重判断；若处理后不足固定五通道则不支持。共享ADC或真实回波重叠不在本次精度证据内。

GPU可复用设计矩阵并批量求解；必须有相同算法的CPU回退。原研究加速器在设计条件数超过10³时改用QR并检查SVD秩，困难候选不能跳过。生产移植优先保证稳定求解和金值一致，不需要复刻研究加速器的所有优化。

## 3. 方案B：可选的已知轴响应模型

它拟合特征随体固观测方向的响应，不输出形状。仅在显式已知极轴、100Run且每Run5CPI、最大双站夹角小于0.000155°的首版范围开放。不得从生成配置、OBJ或真周期反推极轴。LOS插值须在原记录覆盖范围内；拒绝零LOS、零合成向量、极轴横向投影范数≤10⁻¹²、缺样及其他不支持组合。这个范围是本批证据合同，不是物理可测性的阈值。

在特征时刻对原始`scatter_elapsed_s`上的收发LOS分量插值，再分别单位化。已知单位轴$a$确定右手正交基$B=[e_1,e_2,a]$：当$|a_z|>0.9$取辅助向量$(1,0,0)$，否则取$(0,0,1)$；令$e_1=\operatorname{unit}(\mathrm{helper}\times a)$，$e_2=a\times e_1$。用$v_i=\operatorname{unit}(\ell_{T,i}+\ell_{R,i})$、$z_i=(B^Tv_i)_3$、$\lambda_i=\operatorname{atan2}((B^Tv_i)_2,(B^Tv_i)_1)$及$\psi_i=2\pi f(t_i-\overline t)-\lambda_i$构造各列：

$$
\frac{N_{lm}P_l^m(z_i)}{l(l+1)}\cos(m\psi_i),\qquad \frac{N_{lm}P_l^m(z_i)}{l(l+1)}\sin(m\psi_i),\qquad N_{lm}=\sqrt{(2l+1)\frac{(l-m)!}{(l+m)!}}.
$$

取$l=1,\ldots,L$、$m=0,\ldots,l$；$m=0$只设余弦列。$P_l^m$采用SciPy `lpmv`含Condon–Shortley相位的约定，**不补$m>0$的$\sqrt2$**。另加不惩罚的截距。固定$L\in\{1,2,3,4,6\}$，每通道$\alpha\in\{10^{-8},10^{-5},10^{-3},0.1,10\}$；内层为单位CPI权重RSS**求和**加$\alpha\|\beta\|^2$，不能改为均值或复用A的权重而保持α不变。

非截距矩阵按列中心化后做SVD $X_c=U\operatorname{diag}(d_j)V^T$，含截距的平滑矩阵为$A_\alpha=\mathbf1\mathbf1^T/n+U\operatorname{diag}(d_j^2/(d_j^2+\alpha))U^T$。同Run索引组$g$的留出残差为：

$$
e_g^{(-g)}=(I-A_{\alpha,gg})^{-1}(y_g-\widehat y_g).
$$

各通道残差除以剔除该Run后的训练标准差（`ddof=0`），再累计500点平方均值；每通道选最小损失的α，五通道取均值。逐L按同一损失搜索频率，最后选L。B使用原4000／8000频率网格，细化**全部**严格局部极小及两端点；以相邻频率格点为括区，执行`scipy.optimize.minimize_scalar(method="bounded", options={"xatol": 1e-14})`，保留格点。不要误套A的8倍／前三候选协议。返回L、各通道α、轴先验、奇异值／有效自由度；频率剩余敏感度仅作诊断，不充当Fisher精度或总误差条。B的完整源码参照见第6节，不能把100×5硬编码reshape当成无须校验的通用分组。

## 4. 修改位置与完成条件

| 文件 | 应实施的工作 |
| --- | --- |
| [joint_period.py](../../../../inversion/src/joint_period.py) | 保留旧选择器，新增A的设计、整Run评分和搜索；B可放独立小模块 |
| [inversion.py](../../../../inversion/src/inversion.py) | 从共同选择分派接入A/B，复用原特征与LOS |
| [dataset.py](../../../../inversion/src/dataset.py) | 扩展策略枚举及输入校验；新固定阶数集合不被旧`harmonics`单值覆盖 |
| [estimate_period.py](../../../../inversion/scripts/estimate_period.py) | 保存真实策略、参数、候选、先验及失败状态，不再为新结果硬写旧策略名 |
| [period_uncertainty.py](../../../../inversion/src/period_uncertainty.py) | 新策略不落入旧投票分支；不提供未经校准的总误差区间；若接重采样，每次完整重选H／L |
| [schema.py](../../../../rotation_gui/schema.py)、[parameter_form.py](../../../../rotation_gui/window/parameter_form.py)及结果界面 | 增加显式选项，读写新枚举，显示自动阶数及轴条件，保持旧配置含义 |

顺序为A数值组件→CLI／结果保存→GUI→独立选项B。数值组件先在第1节两份原数据复现H2／H8及周期，周期容差0.01s、评分差≤10⁻⁸；B应复现L4／L6。该容差仅检验移植一致性，不是物理精度。再按冻结CSV逐输入回归带噪结果并检查H、误选和失败记录，不只比成功率；不修改金值或缩窄搜索域。已有研究已经跑完这些输入，工程回归检查的是移植有没有改变算法。

边界测试必须能分别触发非有限／缺样、非正权、常数、重复通道、秩亏、无正增益、LOS外推与不支持配置。完成CLI／GUI读写和保存后重载核对，保留CPU路径。编写交接时工作树存在未提交改动；实施前应重新检查当前状态，不清理、重置或覆盖与此次任务无关的代码。

## 5. 已知失败与尚未解决的问题

| 问题 | 已取得的结论 | 性质与下一步边界 |
| --- | --- | --- |
| 70m无噪误选、400m无噪0.1%平台 | 同输入方案A分别改善至约0.05859%／0.01117% | 已在两例研究原型解决到上述精度；没有证明完全无偏或普适极限 |
| 70m低SNR | 0dB的A全部100次比旧法差；10dB四次跳到约2430s，RMSE从1.172735%升至15.500409%；20／30dB各100次≤0.1% | **已尝试仍失败／退化**，并非尚未运行；尚无可靠自动拒绝或策略切换规则，不能判为物理无解 |
| 400m非单调误差及残余偏差 | A在10／20／30dB的RMSE为0.005924%／0.065946%／0.007372%，三档各100次≤0.1%；无噪仍约−1.497s偏差 | **部分改善，未消除**；噪声改变特征和评分，选阶也变化；逐项偏差因果分解与进一步消除未完成，不是已证物理下限 |
| 完整功率轮廓替代五特征 | 已从原IQ提取；所试球面轮廓方法在70m仍选半周 | **该方法试验失败**，本轮不列装；不等于原IQ信息不足 |
| B的抗噪性、未知极轴、大双站角、未见目标／计划 | B带噪只算400m trial0的10／20／30dB；其他范围没有完成验证 | **未充分研究／未验证**，不能声称物理不可行，也不能继承A的800份统计 |
| 生产接入、GUI、工程回归 | 目前只有研究原型和确定合同 | **按分工留给下一位AI的工程任务**，不是数学障碍 |
| 实测仪器校准、总误差覆盖率、全域唯一性证明 | 本批仿真和有限网格不能提供这些结论 | **尚未建立模型／验证或证明**；需要独立校准与评估，不能承诺100%误差界 |

本轮没有证明上述任一EV5失败是物理上无解。严格的信息不可辨只在能够证明“不同周期对给定观测产生完全相同的预测／概率分布”等条件下成立，例如特定观测下的精确对称或完全无调制；届时仅靠同类数据不能区分。当前EV5未建立这种证明。模型允许自由相位吸收频率的反例、局部导数退化或经度坐标失定义，也不能直接证明原始IQ无法测周期。不要把“本模型不支持”“我尚未做”写成“物理不可能”。

## 6. 数据、源码与建议技能

所有路径从仓库根解释。70m作业为`runs/ev5_snr_20261016_70m/`，400m为`runs/ev5_snr_longcpi_20261016_400m/`；两者使用`inversion/period_observables.npz`，LOS取`echo/echo.npz`。带噪缓存分别在`tmp/receiver_snr_ev5_70m_20261016/`及`tmp/receiver_snr_ev5_400m_20261016/`，包含`design.npz`、`clean_features.npy`、`features.npy`。原观测`value`与干净缓存有微小重提取差异，已复核周期差<0.000091s，不宣称字节相同。

研究代码在`tmp/ev5_precision_solution_20261020/`：A的CPU参照是`features/verify_skill2.py`（返回−J），它复用`verify_mean_cv.py`的通道E/D底层；**后者默认返回平均CV，属于对照，不是A评分。** 批量评分及细化见`features/noise_mean_cv.py`，带噪统一协议见`features/noise_dense.py`，无噪统一协议见`features/clean_dense_protocol.py`；B参考`geometry/extract_metadata.py`和`geometry/audit_models.py`，模式为`full500_all_train`。移植数学与输入合同，不直接把含硬编码病例的临时脚本当生产模块。

永久证据是[结果和源码JSON](../../../4.3/vs_4.2/experiments/data/2026-10-20_EV5_PRECISION_MODELS.json)与[逐次CSV](../../../4.3/vs_4.2/experiments/data/2026-10-20_EV5_PRECISION_NOISE.csv)。**不要把约10MB的JSON全文装入上下文。** 用Python只读取所需键：`source_snapshots[相对脚本路径].utf8_source`提供源码，`results["features/clean_dense_protocol.json"].data`提供A金值，`results["geometry/70m_full500_all_train.json"].data`及对应400m键提供B，`noise_summary`提供统计。临时目录缺失时，将需要的源码及其导入依赖解到新的`tmp/`目录，使用`write_bytes(utf8_source.encode("utf-8"))`并核对记录的SHA256；不要覆盖原结果。原始大数组并未内嵌在JSON中，缺失时按第7节实验复现入口重建并校验输入身份，不能临时编造替代数据。

Python统一先`conda activate pytorch`，再执行`python ...`。建议技能：编码前使用`change-verification-discipline`，数值移植可使用`scientific-toolkit-skill`，涉及界面时使用`gui-app-builder`。交付前按该验证技能安排全新上下文的对抗性审查。修改Markdown后执行`python scripts/check_doc_math.py`及本地链接／锚点检查。

## 7. 按需查证，不是前置通读清单

- [数学正文最新解法](../../../4.3/research/RADAR_PERIOD_ESTIMATION.md#ev5-precision-models-20261020)：只需这个阶段的第2／3小节核对A／B推导；更早的噪声迹校正和M1/M2不属于本次实施。
- [原计划第12节](../../../4.3/vs_4.2/plans/PERIOD_INVERSION_IMPROVEMENT_PLAN.md#precision-implementation-20261020)：本交接说明的详细来源；第1—11节保留研究历史。
- [EV5实验最新阶段](../../../4.3/vs_4.2/experiments/reports/2026-10-16_RECEIVER_SNR_AND_EV5.md#ev5-precision-20261020)：查全部数值、失败、独立审查及源码恢复／复算命令时阅读。
