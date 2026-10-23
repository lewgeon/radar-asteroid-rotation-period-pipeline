# 4.3 实验导航

先看[项目现状总览](../../PROJECT_OVERVIEW.md)了解当前效果与缺口；需要核对数值时，再打开下面对应报告。实验设计与验收口径见根[EXPERIMENTS.md](../../../../EXPERIMENTS.md)。

## 文件怎么放

```text
experiments/
├── README.md     阅读入口与归档约定
├── reports/      5份实验正文，按主题合并、内部保留阶段
├── data/         冻结JSON/CSV统计与诊断结果
├── configs/      已核对身份的完整实验配置快照
└── figures/      按实验分组的PNG/SVG配图
```

报告与数据使用 `YYYY-MM-DD_TOPIC`，日期统一放在开头。报告日期表示首次纳入的实验阶段；同主题后续结果追加带日期章节，不因追加重新命名。数据和配置沿用原批次日期，正文另记实际执行时间：例如EV5附件的批次是2026-10-16，正式结果完成于2026-10-17；2026-10-18只是本次整理日期。通用原理示意图仍在版本根 `images/`。

<a id="reports"></a>

## 按问题读报告

| 报告 | 主要问题与阅读边界 |
| --- | --- |
| [2026-10-09 回波特征诊断](reports/2026-10-09_ECHO_FEATURE_ANALYSIS.md) | 距离宽度、插值与历史撤销分支；用于理解诊断过程，当前定义回到算法正文 |
| [2026-10-09 信号形成与积分成本](reports/2026-10-09_SIGNAL_FORMATION_AND_INTEGRATION_COST.md) | 教学控制、面元求积、CPI相干、离散误差及CPU/CUDA验收 |
| [2026-10-11 周期方法与几何研究](reports/2026-10-11_PERIOD_METHOD_RESEARCH.md) | 多谐波、视线补偿、已知形状模板、样条/核和分层控制；主要为2000个单脉冲Run的早期研究 |
| [2026-10-14 周期误差、稳定性与融合](reports/2026-10-14_PERIOD_UNCERTAINTY_AND_FUSION.md) | 100Run保存特征稳定性、覆盖率、有界控制、旧共识负结果与共同预测融合 |
| [2026-10-16 接收噪声与EV5](reports/2026-10-16_RECEIVER_SNR_AND_EV5.md) | 椭球6200次扩扫、70m EV5负结果、400m EV5名义参数及各9100次搜索；三个场景独立解释 |

## 当前效果直接看这里

| 要核实的内容 | 阶段入口 |
| --- | --- |
| EV5名义参数全链路与噪声门限 | [400m、13410秒正式实验](reports/2026-10-16_RECEIVER_SNR_AND_EV5.md#ev5-real-plan-20261017) |
| 换用EV5网格后为什么失败 | [70m、10800秒控制](reports/2026-10-16_RECEIVER_SNR_AND_EV5.md#ev5-70m-snr-20261017) |
| 70m误选与400m高SNR误差为何回升 | [2026-10-18评分、偏差与噪声特征诊断](reports/2026-10-16_RECEIVER_SNR_AND_EV5.md#ev5-bias-diagnosis-20261018) |
| 现有EV5数据怎样提高周期精度 | [2026-10-20—23原数据上的方法比较](reports/2026-10-16_RECEIVER_SNR_AND_EV5.md#ev5-precision-20261020)；多谐波融合、有限球面响应及完整轮廓负结果 |
| 噪声校正与可辨识性推导的作用域 | [2026-10-20前阶段数学推导](../../research/RADAR_PERIOD_ESTIMATION.md#period-math-20261020)、[最小算例](data/2026-10-20_EV5_MATH_CHECKS.json)；公式核验不等于EV5精度验收 |
| 椭球重复半周期的噪声门限 | [6200次扩扫](reports/2026-10-16_RECEIVER_SNR_AND_EV5.md#receiver-snr-extension-20261016)；其中包含早期2600次范围，不能相加 |
| 最终融合规则与生产输入 | [100Run/500CPI收尾](reports/2026-10-14_PERIOD_UNCERTAINTY_AND_FUSION.md#predictive-real-input-20261016) |
| 多普勒单通道仍有哪些问题 | [无噪声谱尾诊断](reports/2026-10-09_SIGNAL_FORMATION_AND_INTEGRATION_COST.md#doppler-tail-diagnosis-20261016) |

## 配置、数据与复现

[data/](data)中的JSON/CSV都是结果证据，含配置字段的汇总JSON仍归为数据；不能直接当作流水线配置载入。[configs/](configs)保存两份与历史启动记录的SHA256一致的完整配置副本：[70m EV5](configs/2026-10-16_EV5_70M.json)、[400m EV5长CPI](configs/2026-10-16_EV5_400M_LONG_CPI.json)。它们分别复制自根 `configs/ev5_snr_20261016_70m.json` 和 `configs/ev5_snr_longcpi_20261016_400m.json`，原运行文件保留。快照包含当时机器的路径，作用是核对实验身份；在另一台机器运行前应另存并调整路径，不能修改冻结副本后仍沿用原哈希。

每份报告在对应阶段直接链接数据、图像和复现命令。早期实验未归档完整输入的情况仍按原记录说明；原始大体积IQ及部分中间产物位于被忽略的 `runs/`、`tmp/`，本目录不宣称包含全部原始实验数据。辅助生成脚本的默认输出或自动配图路径已移出固定归档位置；显式输出参数仍由使用者选择，请指定新的临时目录，审查后再追加权威报告。冻结JSON内的历史路径、`csv_records`等字段保留原样，用于追溯；对应附件以本目录日期在前的新文件名为准。

原周期汇编按“方法与几何”“误差与融合”“接收噪声与EV5”拆分；Chirp教学验证并入信号形成报告，回波诊断中的重复解释和等价公式已合并。不同输入、先验、失败结果、哈希和测量时间保留，整理不代表重新运行实验。下一步见[开放问题](../../../4.4/vs_4.3/plans/OPEN_ISSUES.md#current-issues)和[改进计划](../plans/PERIOD_INVERSION_IMPROVEMENT_PLAN.md#current-stage)。
