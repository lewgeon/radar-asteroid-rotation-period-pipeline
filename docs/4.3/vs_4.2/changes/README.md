# 4.3 已实现变更

这里保存已落地生产行为的契约与阶段验收；当日摘要见[日志](../logs/README.md)，实验数值见[实验导航](../experiments/README.md)，未实施方案见[plans/](../plans)。

| 专题 | 内容 |
| --- | --- |
| [原生距离特征](NATIVE_RANGE_FEATURES.md) | 逐脉冲及CPI完整相关支撑、功率/质心/90%宽度、缓存与紧凑存储；保留撤销分支 |
| [周期反演与可选方法](PERIOD_INVERSION_BASELINE.md) | 共同截距、失败分类、时标、共同预测融合，以及[相位补偿、多谐波、细化和比较的验收](PERIOD_INVERSION_BASELINE.md#optional-period-methods) |
| [GUI产物身份与响应](GUI_ARTIFACT_STATUS.md) | 参数与本地身份复用、轻量结构检查及响应验收 |

冻结验收附件统一放在[data/](data)，文件名为 `YYYY-MM-DD_TOPIC`，各专题直接链接对应数据。历史验收记录不表示本次重新执行测试；当前操作和算法定义以[4.3正文](../../README.md)为准。
