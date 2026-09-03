# Chirp/ISAR 观测与长时自转周期反演的三级时间架构

## 1. 设计结论

当前 Chirp 实现的根本问题不是某个参数取值不佳，而是数据接口把不同物理含义的时间压成了同一个 `elapsed_s`：

- `observation` 只生成一条覆盖整个接收时长的均匀时间轴；
- `echo.generate_echo` 要求该时间轴均匀，并用同一个采样率同时约束 Chirp 带宽和长时观测；
- `EchoDataset.iq` 只有一维，无法表达脉冲内采样和脉冲序列；
- `inversion` 假定整个数据集只有一个 `sample_rate_hz`，随后对整条 IQ 做 STFT；
- `coherence_id` 虽已预留，但当前仿真全部写成 0，反演也没有用它阻止跨观测相干处理。

因此，不能通过简单提高 `sample_rate_hz`、延长 STFT 窗口或补一个匹配滤波函数修复。应先重构采集数据模型，再实现波形专用的前端处理。

## 2. 三种时间变量

对于“多次 ISAR 成像的副产物用于自转周期测量”，需要明确区分三个尺度。

### 2.1 脉内快时间

记为 \(\tau_n=n/f_{\mathrm s,fast}\)，描述单个 Chirp 脉冲内部的采样位置。它决定可处理基带带宽和距离分辨能力：

\[
f_{\mathrm s,fast}\gtrsim B,
\qquad
\Delta R\approx \frac{c}{2B}
\]

以上写法针对复基带采样；实际设计还应留出滤波过渡带和过采样余量。快时间只存在于有效接收窗内，不应覆盖两个脉冲之间的空闲时间。

### 2.2 成像批次内的相干慢时间

记第 \(j\) 次成像的第 \(m\) 个脉冲时刻为 \(\eta_{j,m}\)。均匀脉冲序列下，

\[
\eta_{j,m}=\eta_{j,0}+mT_{\mathrm r},
\qquad
f_{\mathrm{PRF}}=\frac{1}{T_{\mathrm r}}.
\]

这条轴用于脉冲压缩后的慢时间多普勒处理、距离—多普勒成像和 ISAR 相干积累。PRF 是这一级的采样率，而不是整个小行星飞越期间的统一采样率。

一次 ISAR 图像也不是严格的“单时刻测量”，而是在有限相干处理区间（CPI）内合成的。CPI 必须在多普勒分辨率与转动引起的模型失配/散焦之间折中；必要时应拆成多个子孔径。

### 2.3 跨成像批次的观测历元

记不同成像批次或子孔径的代表时刻为 \(T_j\)。这些时刻可以相隔数分钟到数小时，通常不均匀，且不同批次之间未必保持载波相位相干。周期反演要求

\[
\max_j T_j-\min_j T_j \gtrsim P
\]

并且自转相位覆盖足够丰富。该轴适合 Lomb–Scargle、广义 Lomb–Scargle、多特征联合周期图或物理前向模型反演。

最终数据不是一条被物理采样率统一约束的平坦 IQ，而是

\[
y_j[m,n]
=y\!\left(T_j+\eta_{j,m}+\tau_n\right),
\]

即“观测批次 × 脉冲慢时间 × 脉内快时间”的分层结构。

## 3. 推荐的数据处理链

```text
观测计划（多个成像批次）
        │
        ├─ 批次 0：pulse time × fast time ─┐
        ├─ 批次 1：pulse time × fast time ─┤
        └─ 批次 J：pulse time × fast time ─┘
                         │
                  逐脉冲匹配滤波
                         │
                 距离像序列 z_j[m,r]
                         │
             CPI/子孔径内慢时间多普勒处理
                         │
              距离—多普勒图或 ISAR 图像
                         │
            每批次/子孔径提取周期观测特征
                         │
       {T_k, feature_k, uncertainty_k, geometry_k}
                         │
       Lomb–Scargle / 多特征融合 / 物理模型反演
```

不能在不同 `coherence_id` 之间直接做复数相干叠加或统一 STFT。跨批次应传递功率、RCS、距离展宽、多普勒质心/带宽、轮廓相似度、图像嵌入等对相位重置较稳健的观测量。

## 4. 推荐的模块与 seam

CW 和 Chirp 原始数据具有不同维度和处理约束，不应继续强制共用一个一维 `EchoDataset`。建议让两条波形链在“周期观测序列”处汇合。

### 4.1 波形专用原始数据

#### `CWWindowDataset`

- `sample_receive_elapsed_s: [N]`
- `iq: [N]`
- `window_id: [N]`
- `coherence_id: [N]`
- `valid: [N]`
- 与采样点或窗口对应的几何量

#### `ChirpAcquisitionDataset`

- `fast_time_s: [N_fast]`
- `pulse_receive_elapsed_s: [N_pulse]`
- `iq: [N_pulse, N_fast]`
- `acquisition_id: [N_pulse]`
- `coherence_id: [N_pulse]`
- `valid: [N_pulse, N_fast]`
- 每个脉冲中心对应的三事件几何

若不同成像批次使用不同快时间网格或波形，初版可采用“一个批次一个 NPZ + campaign manifest”，避免在 NPZ 中存放对象数组；不必为了兼容可变形状而把数据补成巨大的三维数组。

### 4.2 共同的周期反演接口

定义深模块 `PeriodObservableSeries`：

- `epoch_elapsed_s: [N_epoch]`
- `values: [N_epoch, N_feature]`
- `uncertainty: [N_epoch, N_feature]`
- `valid: [N_epoch, N_feature]`
- `acquisition_id: [N_epoch]`
- `geometry`：视线、距离、波长及其他必要元数据
- `feature_names`

Chirp 前端在内部完成匹配滤波、距离门选择、CPI/子孔径处理和特征提取；CW 前端完成窗口化和谱特征提取。反演模块只学习一个小接口，不需要知道快时间、PRF 或匹配滤波细节。

该 seam 能阻止当前最危险的错误：把 Chirp 原始快时间 IQ 直接交给长周期 STFT/周期图。

## 5. 观测计划配置建议

旧配置：

```json
"receive": {
  "start_utc": "...",
  "duration_s": 14400.0,
  "sample_rate_hz": 16.0
}
```

只能表达一条均匀时间轴。建议改为显式观测批次：

```json
"campaign": {
  "start_utc": "...",
  "acquisitions": [
    {
      "start_offset_s": 0.0,
      "pulse_count": 128,
      "prf_hz": 20.0,
      "fast_time_start_s": 0.0,
      "fast_time_duration_s": 0.001,
      "fast_sample_rate_hz": 10000000.0,
      "coherence_id": 0
    },
    {
      "start_offset_s": 1800.0,
      "pulse_count": 128,
      "prf_hz": 20.0,
      "fast_time_start_s": 0.0,
      "fast_time_duration_s": 0.001,
      "fast_sample_rate_hz": 10000000.0,
      "coherence_id": 1
    }
  ]
}
```

这些数值仅展示字段层级，不是本项目推荐的真实雷达参数。真实脉宽、带宽、PRF、接收窗和脉冲数必须由距离模糊、多普勒模糊、信噪比和成像需求共同确定。

波形参数应保留在 `waveform` 中；采集计划只描述何时发射/接收和如何采样，避免把信号定义与调度混合。

## 6. 三事件时间与快时间的处理

几何求解没有必要对每个快时间采样点重复执行完整星历计算。建议：

1. 对每个脉冲的中心接收时刻求解质心的发射—散射—接收三事件几何；
2. 在单个脉冲/接收窗内冻结视线与姿态，或使用一阶局部展开；
3. 各面元相对质心的路径差决定其脉压后的距离单元和相位；
4. 只有当脉宽或接收窗长到足以产生显著姿态变化时，才启用脉内运动模型。

当前 `pulse_start_s` 与 `receive_elapsed_s` 共用同一参考轴的做法也应拆开。发射脉冲时刻、散射时刻和返回接收窗时刻必须通过质心光行时显式关联，不能用“接收轴上是否处于发射脉冲门内”判断是否有回波。

## 7. 长周期反演的观测量

每个成像批次可产生一个或多个子孔径观测点。建议优先保留：

- 总回波功率或经距离积分的 RCS；
- 多普勒质心、RMS 带宽和正负频率边缘；
- 距离展宽、峰值距离与若干距离矩；
- 距离—多普勒图的低维主成分或学习型嵌入；
- 相邻批次图像/轮廓的相关系数；
- 特征的不确定度、SNR 与质量标志。

“10 次成像”不自动意味着足以估计周期。若每次只产生一个标量，10 点可能受到采样窗函数、别名和几何变化严重影响。更好的做法是将每次成像划分为多个仍可聚焦的子孔径，从而得到时密时疏的观测点簇，并检查其谱窗函数。

跨批次几何变化会给功率和带宽引入非周期趋势。普通 Lomb–Scargle 只能处理不均匀时间戳，不能自动消除不同批次的零点、尺度和观测几何偏差。后续应至少提供以下一种处理：

- 带常数项和低阶趋势的广义 Lomb–Scargle；
- 多特征/多批次联合周期图，为每个批次拟合独立零点或尺度；
- 将视线和距离作为协变量；
- 直接用散射前向模型比较不同候选周期。

## 8. 分阶段迁移方案

### M0：冻结错误路径

- 将现有一维 Chirp 模式标记为 legacy/演示用途；
- 当 `chirp_pulse_train` 与一维均匀 `elapsed_s` 同时出现时给出明确警告或拒绝运行；
- CW 路径暂时保持不变。

### M1：建立观测计划和二维 Chirp 数据格式

- `observation` 支持多个 acquisition 和每批次的 pulse times；
- 几何按脉冲中心输出；
- `echo` 输出 `[pulse, fast_time]` 原始回波；
- 使用 `schema_version=2`，不静默改变旧 NPZ 语义。

### M2：实现 Chirp 前端

- 逐脉冲匹配滤波；
- 距离门选择和距离像序列；
- CPI/子孔径内慢时间 FFT；
- 输出 `PeriodObservableSeries`。

### M3：改造长周期反演

- 只消费带真实历元的 `PeriodObservableSeries`；
- 支持不规则、成簇采样；
- 尊重 `coherence_id`；
- 增加广义/多特征 Lomb–Scargle、谱窗与 bootstrap。

### M4：ISAR 产品与周期反演共用前端

- 同一批脉压距离像可分别送入 ISAR 成像和周期特征提取；
- 成像参数和周期反演参数彼此独立；
- 周期估计作为多次 ISAR 观测的联合副产品，而不是把长时观测强行塞进单个 CPI。

## 9. 必要测试

1. 配置生成的 `iq.shape == (pulse_count, fast_sample_count)`；
2. 脉冲间隙不分配快时间 IQ 数组；
3. 单点目标脉压峰位与理论时延一致；
4. 两个距离不同的散射点在距离像中可分辨；
5. 同一 `coherence_id` 内能恢复已知慢时间多普勒；
6. 不同 `coherence_id` 不得被统一 FFT/STFT；
7. 多批次特征的绝对时间戳保持严格递增但允许不均匀；
8. 不规则、成簇采样下 Lomb–Scargle 恢复已知周期；
9. 改变快时间采样率只影响距离处理，不应改变观测历元；
10. 改变 PRF 只影响批次内慢时间处理，不应改变 campaign 总跨度；
11. CW 旧基线结果在重构后保持可复现；
12. schema v1 数据继续由 legacy adapter 读取，不能被误解释为 v2 Chirp 数据。

## 10. 对论文结构的影响

这一重构会让论文原理部分更清晰：

- 雷达信号模型一节区分快时间、相干慢时间和观测历元；
- ISAR 一节说明有限 CPI 内的距离—多普勒形成；
- 周期反演一节说明从多个 CPI/子孔径产品提取时密时疏特征；
- Lomb–Scargle 只作用于观测历元及其特征，不直接作用于 Chirp 快时间回波；
- 后续深度学习可在距离—多普勒图或 `PeriodObservableSeries` 上实现，而不破坏物理时间结构。

这也兑现了 `inversion/EXPERIMENTS.md` 第 5.7 节已经提出、但当前代码尚未实现的 seam：相干脉冲簇内部做距离压缩和多普勒处理，非相干簇之间只通过带真实时间戳的特征进行联合周期反演。
