# Chirp 脉冲雷达的高精度自转周期测量算法与观测策略

本文整理一种适用于 chirp 脉冲序列雷达的高精度小行星自转周期测量路线。核心思想是：雷达仍按 ISAR 体制发射等间隔 chirp 脉冲序列，但处理时区分三个时间尺度，在短相干窗口内提取微多普勒特征，在长时间、可间断的观测历元上进行不均匀采样周期估计，最后用物理模型做全局精修。

这条路线不要求雷达能够发射正弦连续波。只要 chirp 脉冲之间具有稳定时间戳和足够的相干性，就可以利用脉冲压缩后的距离像序列构造距离-多普勒-时间数据，并从中测量自转周期。

## 1. 总体结论

对于只能发射 chirp 脉冲序列的雷达系统，ISAR 成像和自转周期测量的发射形式可以相同：

```text
等间隔 chirp 脉冲序列
```

区别不在于发射信号必须完全不同，而在于处理时间尺度不同：

| 任务 | 主要处理目标 | 关键时间尺度 |
|---|---|---|
| ISAR 成像 | 在一个有限相干处理区间内形成距离-多普勒图像 | CPI，不能过长，否则散焦 |
| 自转周期测量 | 在长时间跨度上观察微多普勒特征的周期变化 | 总观测跨度，最好覆盖尽可能多的自转相位 |

因此，周期测量并不要求 PRT 变长。PRT 主要决定慢时间采样率、多普勒无模糊范围和数据量。周期测量真正需要的是更长的总观测跨度，以及对间断观测的正确建模。

推荐处理链为：

```text
原始 chirp 回波
  -> 逐脉冲匹配滤波 / dechirp / 距离压缩
  -> 距离像序列 X(r, n)
  -> 平动补偿与距离徙动校正
  -> 滑动 CPI 形成 range-Doppler-time cube
  -> 提取微多普勒特征 y(t)
  -> 不均匀采样多谐波周期搜索
  -> 带物理约束的全局非线性最小二乘 / 最大似然精修
```

## 2. 三个必须分开的时间轴

### 2.1 脉内快时间

单个 chirp 脉冲内部的采样时间记为 \(\tau\)。它决定距离压缩和距离分辨率。

线性调频脉冲可写为：

$$
s_n(t)=\operatorname{rect}\left(\frac{t-nT_r}{T_p}\right)
\exp\left[j2\pi\left(f_c(t-nT_r)+\frac{K}{2}(t-nT_r)^2\right)\right],
$$

其中：

- \(f_c\)：载频；
- \(T_p\)：脉冲宽度；
- \(B\)：chirp 带宽；
- \(K=B/T_p\)：调频斜率；
- \(T_r\)：PRT；
- \(f_{\mathrm{PRF}}=1/T_r\)：PRF。

距离分辨率近似为：

$$
\Delta R \approx \frac{c}{2B}.
$$

快时间只描述一个脉冲内部的采样，不应把整个观测时长当成一条连续快时间轴来做 STFT。

### 2.2 相干慢时间

第 \(n\) 个脉冲的发射时刻为：

$$
t_n=t_0+nT_r.
$$

每个脉冲经过匹配滤波后得到一维距离像：

$$
x_n(r).
$$

把多个脉冲沿慢时间排列，得到二维回波矩阵：

$$
X(r,n).
$$

这正是 ISAR 和微多普勒处理共同使用的基础数据结构。慢时间用于多普勒处理、相干积累、ISAR 成像和微多普勒特征提取。

### 2.3 跨观测段历元

实际小行星观测常常是间断的。由于地球自转、目标可见性、雷达站几何和任务排程限制，观测会分成多个不连续段：

$$
\mathcal{S}_1,\mathcal{S}_2,\dots,\mathcal{S}_J.
$$

不同观测段之间的间隔通常不相等，也不应强行补零拼成均匀序列。每个观测段或每个短 CPI 都应保留真实时间戳：

$$
T_j.
$$

周期估计的后端应处理不均匀采样数据：

$$
\{T_j, y_j, \sigma_j, s_j\},
$$

其中 \(y_j\) 是从微多普勒图中提取的特征，\(\sigma_j\) 是特征不确定度，\(s_j\) 是观测段编号。

## 3. 距离-多普勒-时间立方体如何形成

单幅 ISAR 图像通常使用一个 CPI 内的二维矩阵：

$$
X_m(r,\ell)=X(r,n_m+\ell),\quad \ell=0,1,\dots,L-1,
$$

其中 \(L\) 是该 CPI 内的脉冲数。对慢时间 \(\ell\) 做 FFT，可得到短时距离-多普勒图：

$$
C(r,f_D,t_m)=\mathcal{F}_{\ell}\{w(\ell)X_{\mathrm{mc}}(r,n_m+\ell)\},
$$

其中：

- \(w(\ell)\)：慢时间窗函数；
- \(X_{\mathrm{mc}}\)：经过平动补偿和距离徙动校正后的距离像序列；
- \(t_m\)：该 CPI 的中心时刻；
- \(f_D\)：多普勒频率。

滑动 CPI 后，每隔一个 hop 得到一帧短时距离-多普勒图。所有帧沿时间堆叠，即得到：

$$
C(r,f_D,t).
$$

这就是距离-多普勒-时间立方体。

如果把目标所在距离门积分掉：

$$
S(f_D,t)=\sum_{r\in\Omega} C(r,f_D,t),
$$

就得到常见的微多普勒水瀑图。保留 \(r\) 维可以分离不同散射中心；积分掉 \(r\) 维可以提高信噪比并简化周期估计。

## 4. 与“多次 ISAR 成像”的关系

可以把距离-多普勒-时间立方体直观理解为：

```text
连续滑动地做很多次短时距离-多普勒处理
```

但不一定要把每一帧都做成完整 ISAR 图像。完整 ISAR 成像通常还需要更复杂的聚焦、横向定标和相位补偿。周期测量更关心的是随时间变化的微多普勒特征，因此很多情况下只需要短时距离-多普勒图或微多普勒谱。

因此：

- 如果每个短时窗口只做慢时间 FFT，得到的是 range-Doppler-time cube；
- 如果每个短时窗口进一步完成 ISAR 聚焦，得到的是多帧 ISAR 图像序列；
- 周期测量不要求第一幅和最后一幅完整 ISAR 图像相隔超过一个周期；
- 周期测量要求跨多个观测段的微多普勒特征覆盖足够丰富的自转相位。

## 5. 微多普勒特征提取

从 \(C(r,f_D,t)\) 中可以提取多种一维特征序列。常用特征包括：

### 5.1 多普勒质心

$$
\bar f_D(t)=
\frac{\sum_{r,f_D} f_D |C(r,f_D,t)|^2}
{\sum_{r,f_D}|C(r,f_D,t)|^2}.
$$

它反映目标整体散射能量在多普勒方向上的中心位置。

### 5.2 多普勒展宽

$$
B_D(t)=f_{D,\max}(t)-f_{D,\min}(t).
$$

对旋转目标，展宽通常与目标投影尺度、转轴方向和自转角速度有关，是周期测量中很有价值的特征。

### 5.3 RMS 多普勒带宽

$$
\sigma_f(t)=
\sqrt{
\frac{\sum_{r,f_D}(f_D-\bar f_D(t))^2 |C(r,f_D,t)|^2}
{\sum_{r,f_D}|C(r,f_D,t)|^2}
}.
$$

相比硬阈值的 \(B_D(t)\)，RMS 带宽对噪声更平滑。

### 5.4 强散射点脊线

$$
f_{\mathrm{ridge}}(t)=\arg\max_{f_D}|C(r_0,f_D,t)|^2.
$$

如果某个距离门内有稳定强散射点，脊线跟踪可以提供很高精度的周期信息。

### 5.5 回波强度包络

$$
A(t)=\sum_{r,f_D}|C(r,f_D,t)|^2.
$$

对非球形小行星或具有镜面反射结构的目标，强度包络也可能随自转显著变化。

## 6. 间断观测下的周期估计

小行星自转周期通常为数小时，而单日可观测时长有限。观测间断不会使算法失效，但会改变周期估计后端：不能使用普通均匀 FFT，也不能在缺测处补零后直接处理。

正确做法是保留真实时间戳，构造不均匀采样特征序列：

$$
\{t_i,y_i,\sigma_i,s_i\}.
$$

其中：

- \(t_i\)：第 \(i\) 个特征点的绝对时间；
- \(y_i\)：微多普勒特征；
- \(\sigma_i\)：该特征的不确定度；
- \(s_i\)：观测段编号。

### 6.1 广义 Lomb-Scargle 粗搜索

对近似单峰正弦变化的特征，可使用广义 Lomb-Scargle：

$$
y_i=c+a\cos(2\pi f t_i)+b\sin(2\pi f t_i)+\epsilon_i.
$$

它适合不均匀采样，并且允许引入测量权重：

$$
w_i=\frac{1}{\sigma_i^2}.
$$

### 6.2 多谐波周期模型

真实小行星形状和散射通常不是正弦。更稳健的粗搜索模型是多谐波形式：

$$
y_i=c+\sum_{k=1}^{K}
\left[
a_k\cos(2\pi k f t_i)+b_k\sin(2\pi k f t_i)
\right]+\epsilon_i.
$$

对于具有 180 度对称性的目标，微多普勒展宽或亮度包络可能表现出半周期重复，因此需要同时检查：

$$
P,\quad \frac{P}{2},\quad 2P.
$$

### 6.3 每段独立偏置

不同观测段的信噪比、距离、姿态几何、系统增益和标定状态可能不同。此时应给每个观测段加入独立偏置：

$$
y_i=c_{s(i)}+\sum_{k=1}^{K}
\left[
a_k\cos(2\pi k f t_i)+b_k\sin(2\pi k f t_i)
\right]+\epsilon_i.
$$

这样可以避免观测段之间的幅度基线差异污染周期估计。

### 6.4 观测窗口与 daily alias

由于地球自转和目标可见性，观测窗口常带有接近一天的周期结构。这会在周期图中产生别名峰。应计算窗口函数：

$$
W(f)=\left|\sum_i e^{-j2\pi f t_i}\right|^2.
$$

如果窗口函数在 \(1\,\mathrm{day}^{-1}\) 附近有强峰，则候选频率 \(f_0\) 可能出现：

$$
f_{\mathrm{alias}}=|f_0+n f_{\mathrm{day}}|,
\quad n=\pm1,\pm2,\dots
$$

因此周期搜索不能只取最高峰，而应保留前若干候选，并进行相位折叠和物理模型检验。

## 7. 最高精度的全局物理模型精修

Lomb-Scargle 或多谐波周期图适合粗搜索，但最高精度通常来自全局模型拟合。粗搜索给出候选周期后，应在候选附近做非线性最小二乘或最大似然估计：

$$
\hat P=
\arg\min_P
\sum_i
\frac{
\left[y_i-m(t_i;P,\Theta)\right]^2
}{\sigma_i^2}.
$$

其中 \(m(t_i;P,\Theta)\) 是微多普勒特征的物理或半物理模型，\(\Theta\) 可包含：

- 均值和每段偏置；
- 多谐波幅度与相位；
- 观测几何因子；
- 雷达距离和信噪比权重；
- 散射中心稳定性参数；
- 转轴方向或投影尺度参数。

如果数据质量很高，也可以直接对复距离像做参数化拟合：

$$
X_{\mathrm{obs}}(r,n)
\approx
\sum_q \alpha_q
\exp\left[
j\frac{4\pi}{\lambda}R_q(n;P,\Theta)
\right].
$$

这种方法最接近理论最优，但需要更强的目标散射模型，工程实现难度也最高。

## 8. 雷达观测策略

### 8.1 发射策略

建议发射稳定、等间隔的 chirp 脉冲序列：

```text
chirp_0, chirp_1, chirp_2, ...
```

观测策略的重点不是让 chirp “看起来像连续波”，而是保证：

- 脉冲间时间戳准确；
- 本振和采样时钟稳定；
- 同一 CPI 内相位尽量相干；
- PRF 足够覆盖预期微多普勒范围；
- 总观测跨度尽可能覆盖更多自转相位；
- 每个观测段至少包含足够多脉冲形成短时多普勒谱。

### 8.2 PRT / PRF 选择

PRF 需要满足慢时间多普勒采样要求。若未做其他解模糊处理，脉冲多普勒无模糊范围约为：

$$
|f_D| < \frac{f_{\mathrm{PRF}}}{2}.
$$

因此应使：

$$
f_{\mathrm{PRF}} > 2 f_{D,\max}.
$$

这里 \(f_{D,\max}\) 应包括目标整体残余多普勒和自转微多普勒。若已经做了高质量平动补偿，则主要关注残余微多普勒带宽。

PRT 过短会增加数据量，但通常不会降低周期测量精度；PRT 过长则可能导致微多普勒混叠、脊线不连续或短 CPI 内样本不足。

### 8.3 CPI 长度选择

CPI 时长为：

$$
T_{\mathrm{CPI}}=L T_r.
$$

它同时控制多普勒分辨率和局部相干性：

$$
\Delta f_D \approx \frac{1}{T_{\mathrm{CPI}}}.
$$

若 \(T_{\mathrm{CPI}}\) 太短，多普勒分辨率不足；若 \(T_{\mathrm{CPI}}\) 太长，目标转动和散射中心变化会导致谱线模糊或 ISAR 散焦。

在未知周期时，可先使用多个 CPI 长度并行试验。粗略建议：

```text
短 CPI：用于看清快速变化和避免散焦
中等 CPI：用于稳定提取多普勒带宽和质心
长 CPI：用于提高多普勒分辨率，但只在局部相干条件好时使用
```

### 8.4 总观测跨度

周期测量希望总观测跨度尽量长：

$$
T_{\mathrm{span}}=\max_i t_i-\min_i t_i.
$$

理想情况下应覆盖多个周期；但对数小时自转周期的小行星，单日观测可能做不到。此时可以依赖多日、不均匀观测段，只要真实时间戳保留且相位覆盖足够丰富，仍可估计周期。

### 8.5 多日间断观测

多日观测时应避免以下做法：

- 不要把不同观测段直接拼接成连续 IQ；
- 不要在缺测处补零后做普通 FFT；
- 不要假设不同观测段之间保持载波相位相干；
- 不要只比较第一幅和最后一幅 ISAR 图像。

推荐做法是：

```text
每个观测段独立完成脉冲压缩、运动补偿和短时微多普勒特征提取；
跨段只合并特征、时间戳、不确定度和观测几何；
周期估计后端使用不均匀采样模型。
```

## 9. 代码实现建议

建议将代码分成五层，避免把所有时间尺度压成一条一维采样轴。

### 9.1 数据结构层

建议保存如下结构：

```python
observation = {
    "segment_id": segment_id,
    "pulse_times": pulse_times,      # shape: [num_pulses]
    "fast_time": fast_time,          # shape: [num_fast_samples]
    "raw_iq": raw_iq,                # shape: [num_pulses, num_fast_samples]
    "carrier_hz": carrier_hz,
    "bandwidth_hz": bandwidth_hz,
    "prt_s": prt_s,
}
```

### 9.2 脉冲压缩层

输出距离像序列：

```python
range_profiles = pulse_compress(raw_iq, reference_chirp)
# shape: [num_pulses, num_range_bins]
```

### 9.3 短时距离-多普勒层

滑动 CPI 形成数据立方体：

```python
cube, frame_times, range_axis, doppler_axis = build_range_doppler_time_cube(
    range_profiles,
    pulse_times,
    cpi_len,
    hop_len,
    window="hann",
)
# cube shape: [num_frames, num_range_bins, num_doppler_bins]
```

### 9.4 特征提取层

从每帧中提取微多普勒特征：

```python
features = extract_micro_doppler_features(
    cube,
    frame_times,
    range_axis,
    doppler_axis,
    target_range_gate,
)
```

输出建议包括：

```python
features = {
    "time": frame_times,
    "centroid_hz": centroid,
    "rms_bandwidth_hz": rms_bandwidth,
    "hard_bandwidth_hz": hard_bandwidth,
    "power": power,
    "snr": snr,
    "segment_id": segment_ids,
}
```

### 9.5 周期估计层

跨观测段合并特征：

```python
dataset = merge_feature_segments(feature_segments)
```

先做周期粗搜索：

```python
candidates = multi_harmonic_period_search(
    time=dataset.time,
    y=dataset.rms_bandwidth_hz,
    sigma=dataset.sigma,
    segment_id=dataset.segment_id,
    period_min_s=period_min_s,
    period_max_s=period_max_s,
)
```

再做全局精修：

```python
best = refine_period_global_model(
    candidates=candidates,
    time=dataset.time,
    y=dataset.rms_bandwidth_hz,
    sigma=dataset.sigma,
    segment_id=dataset.segment_id,
    geometry=dataset.geometry,
)
```

## 10. 推荐验证方式

为了确认算法真正有效，建议先用仿真验证：

1. 生成已知自转周期的小行星散射模型；
2. 生成多段间断 chirp 脉冲观测；
3. 加入热噪声、轨道残余多普勒、距离徙动和散射闪烁；
4. 运行完整处理链；
5. 比较估计周期与真实周期；
6. 扫描 SNR、观测段长度、间断分布、CPI 长度和 PRF。

评价指标包括：

$$
\Delta P = \hat P-P_{\mathrm{true}},
$$

$$
\frac{|\Delta P|}{P_{\mathrm{true}}},
$$

以及候选周期是否落入真实周期、半周期或 daily alias。

## 11. 实用优先级

若目标是尽快写出可工作的代码，建议按以下顺序实现：

1. 正确的数据结构：`segment × pulse × fast_time`；
2. 脉冲压缩得到 `pulse × range`；
3. 平动补偿和目标距离门选择；
4. 滑动 CPI 形成 `time × range × doppler`；
5. 提取 `rms_bandwidth`、`centroid`、`power`；
6. 用 generalized Lomb-Scargle 或多谐波最小二乘做不均匀周期搜索；
7. 检查窗口函数和 daily alias；
8. 对前几个候选周期做全局模型精修。

最高精度通常来自最后两步，而不是来自单独提高某一个 FFT 点数。

## 12. 一句话总结

对于 chirp 脉冲 ISAR 雷达，自转周期测量不应被理解为“做几次完整 ISAR 图像然后比较图像”，而应理解为：

```text
在每个短相干窗口内形成微多普勒观测，
在长时间、可间断、不均匀的观测历元上估计周期。
```

发射端仍是等间隔 chirp 脉冲序列；处理端必须区分快时间、相干慢时间和跨观测段历元。最高精度路线是脉冲压缩后的微多普勒特征提取，加上不均匀采样多谐波周期搜索和物理模型全局精修。
