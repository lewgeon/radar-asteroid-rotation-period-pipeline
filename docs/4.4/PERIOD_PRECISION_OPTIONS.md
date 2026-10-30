# 周期精度策略与使用边界

4.4新增显式周期选择选项：`predictive_skill_energy`（方案A）和`spherical_response`（方案B）。默认仍为4.3的`predictive_joint`，`legacy_consensus`保留为候选投票对照。下文第1—4节描述A/B，复用Chirp CPI五项原始特征，不先按Run平均，不利用真周期选择模型。工程验收和输入身份见[接入证据](vs_4.3/changes/EV5_PRECISION_IMPLEMENTATION.md)，历史研究、失败结果与迁移合同见[接手说明](vs_4.3/plans/EV5_PRECISION_IMPLEMENTATION_HANDOFF.md)。

## 1. 输入与配置

两项新策略首版均需要散射质心特征时标、`spectral_moments`多普勒谱矩、五项完整有限特征和正有效样本数。通道为总功率、多普勒质心、RMS多普勒带宽、距离质心、90%距离能量宽度；按名称映射。常数、仿射重复和缺样明确拒绝；A还拒绝纯趋势、训练折秩亏和全域无正预测增益，不静默切换旧策略。逐脉冲回退、CW、共享ADC保存行和真实回波重叠均不在首版支持范围；已知极轴和未知极轴的证据不能混用。

在现有完整配置的`inversion`对象中选择`period_selection`即可。下面只列需要修改的字段，并非可独立运行的完整配置。原有周期范围、网格数、CPI和观测设置保持用户提供的值。

```json
{
  "period_selection": "predictive_skill_energy",
  "doppler_estimator": "spectral_moments",
  "period_time_role": "scatter_centroid",
  "los_phase_compensation": false
}
```

方案A至少需要10个有效Run。若开启`los_phase_compensation`，必须在反演配置显式提供`spin_axis_ra_deg`、`spin_axis_dec_deg`并设置`phase_period_convention="full_rotation"`；返回的相位补偿已带负号，不再乘2。70m历史回测关闭LOS补偿，400m开启并使用RA105°、Dec−66°；这些只是对应回测条件，不是所有输入的默认极轴。

方案B选择`period_selection="spherical_response"`，同样由反演配置显式提供极轴。它首版严格要求100个Run、每Run5个CPI，插值后收发LOS最大夹角小于0.000155°，特征时刻处于原散射几何覆盖范围内。零LOS、零合成方向和极轴横向投影范数不大于10⁻¹²均拒绝。它使用自身的向量插值和完整自转相位，不依赖旧LOS补偿勾选及半转约定；独立方法比较若启用，仍按旧对照方法的条件执行。该模型拟合特征随体固观测方向的响应，不输出三维形状。

GUI在“可选反演功能→周期融合方法”中提供这两个选项，球面响应会显示必需的极轴输入。保存、重载仍使用上述配置枚举。旧“谐波数”“周期局部细化”只控制独立特征对照；它们不覆盖新选择器的自动阶数或固定细化协议。

## 2. 评分与搜索

方案A将每Run有效样本权重归一为和1，按各Run平均特征时刻排序并按编号模5分折。同Run的CPI始终在同一折。每个候选用float64带权SVD同时拟合五个右端；模型只有共享截距和固定阶数集合H∈{1,2,4,8}的正余弦项，没有每Run自由截距或相位。通道预测增益为1减去留出平方误差与训练均值常量基线误差之比，总评分J为五项正增益的平方和。周期和H始终按同一个J选择，J越大越好。

方案A在完整配置频率范围上取`8*(period_grid_size-1)+1`个均匀频率格点。每个H保留评分最高的三个不同局部峰和两个端点，在相邻格点围成的周期区间做42轮黄金分割，并保留格点与细化值中较优者。精确同分先取小H，再取短周期。协议名为`dense8_top3_endpoints`，不构成连续全域最优认证。

方案B固定L∈{1,2,3,4,6}，各通道分别选择α∈{10⁻⁸,10⁻⁵,10⁻³,0.1,10}。采用单位CPI权重、RSS求和与岭惩罚，截距不惩罚；列中心化后以SVD求平滑矩阵，再通过同Run子块得到整Run留出残差。残差按该Run之外训练数据的标准差归一，五通道损失取均值，越小越好。它沿用原网格数，细化全部严格局部极小和端点，使用频率区间的bounded优化及`xatol=1e-14`。不采用A的8倍网格或前三峰限制。

## 3. 输出、设备和失败

`best_summary.json`保存实际推荐策略和选择报告；`period_selection.json`及同名HTML保存候选、逐通道评分、阶数、协议和诊断。A记录E/D、预测增益及正增益平方；B记录L、各通道α、显式轴先验、奇异值和有效自由度。CLI摘要显示自动H或L，球面响应的支撑数表示参与响应拟合的五项特征，并非五项独立证据。选择失败写入`period_selection_failure.json`并以错误退出；不生成伪装为新策略的旧选择结果。

新生产选择器当前使用CPU float64稳定SVD；即使前端或独立特征搜索请求CUDA，新选择器诊断仍如实记CPU。批量验收工具可使用同数学的CPU/CUDA QR多右端实现，其用途和生产完整搜索的证据分别记录。CPU运行耗时受BLAS线程配置影响，可在独立进程启动前设置`OMP_NUM_THREADS=1`、`MKL_NUM_THREADS=1`和`OPENBLAS_NUM_THREADS=1`；这不会修改算法或精度策略。

运行方式沿用现有CLI：

```powershell
conda activate pytorch
python inversion/scripts/estimate_period.py --echo <echo.npz> --config <inversion.json> --output <新结果目录>
```

两项新策略尚未接入每次完整重选阶数的Run重采样。选择`run_bootstrap`时明确输出不可用状态，不进入旧投票分支，不提供新模型的局部区间或总误差3σ保证。评分用于选择，不是概率、似然或无偏保证。

## 4. 精度结论的范围

两份EV5无噪数据上的改善属于固定输入移植和同场景回测，不能推广为未见目标的准确率。方案A在70m低SNR存在已记录退化：0dB全部100次比旧法差，10dB有四次跳至约2430s；不能按真周期或SNR档位自动选择算法。400m仍有残余偏差；方案B的噪声验证远少于A，不能继承A的800份统计。未知极轴、大双站角、仪器校准、跨场景泛化、全域唯一性及总误差覆盖率仍未建立。
