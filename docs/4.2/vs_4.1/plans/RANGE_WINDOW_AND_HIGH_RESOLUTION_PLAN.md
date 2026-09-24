# 高距离分辨回波：问题、内存账与距离门方案

> 状态：核心字段改动已实施，见 [../changes/RANGE_GATE_2026-09-23.md](../changes/RANGE_GATE_2026-09-23.md)。正文保留为设计记录。旧时间保护的合并用的是 $\max(D_{\mathrm{extent}},\,c T_{\mathrm{pre}},\,c T_{\mathrm{post}})$；两者都为正时，这比原先相加的行宽短一个较小项，载入时会警告。调度预留去掉了单独的 $T_{\mathrm{post}}$，路径窗只计一次，因此 $H$ 变短。  
> 读者：不熟悉本仓库的协作者或其它模型。请按正文顺序讲解，不要跳过第 3 节的三种字节数。  
> 本文不是已落地变更说明。现行行为以 [docs/4.2/OBSERVATION_TIME_SELECTION.md](../../OBSERVATION_TIME_SELECTION.md) 和 [docs/4.2/GLOSSARY.md](../../GLOSSARY.md) 为准。

本文要回答三件事：

1. 为什么用网格目标仿真 Chirp 回波，二维矩阵仍像点目标？
2. 若要把距离分辨率做到约 $1\,\mathrm{m}$，为什么按现有试例参数会得到 TB 级数据？
3. 准备怎样改配置字段和试例参数？哪些先做，哪些明确不做？

---

## 1. 讨论是怎么来的

试例 [`configs/chirp_mesh_target_test.json`](../../../../configs/chirp_mesh_target_test.json) 使用 `echo/models/ellipsoid.obj`：顶点包络约 $140\times 100\times 80\,\mathrm{m}$，外接半径 $70\,\mathrm{m}$。这与近地小行星直径中位数同量级，作为形体尺寸是合理的。

该配置当前射频参数是：

| 符号 | 配置字段 | 试例值 |
| --- | --- | ---: |
| $B$ | `echo.waveform.bandwidth_hz` | $1000\,\mathrm{Hz}$ |
| $f_s$ | `observation.receiver_sampling.fast_sample_rate_hz` | $5000\,\mathrm{Hz}$ |
| $f_0$ | `echo.radar.carrier_frequency_hz` | $1\,\mathrm{MHz}$ |
| $T_{\mathrm{pulse}}$ | `observation.transmit.pulse_width_s` | $0.01\,\mathrm{s}$ |
| $\mathrm{PRF}$ | `observation.transmit.prf_hz` | $20\,\mathrm{Hz}$ |
| $D$ | `observation.schedule.run_duration_s` | $60\,\mathrm{s}$ |
| $N_{\mathrm{run}}$ | `observation.schedule.run_count` | $50$ |
| $T_{\mathrm{pre}},T_{\mathrm{post}}$ | `pre_guard_s`,`post_guard_s` | 各 $0.01\,\mathrm{s}$ |
| $D_{\mathrm{extent}}$ | `observation.target.extent_path_m` | $300\,\mathrm{m}$ |

单站双程距离分辨单元为

$$
\delta R=\frac{c}{2B}\approx 150\,\mathrm{km}.
$$

$70\,\mathrm{m}$ 级形体只占约 $\delta R$ 的千分之一，全部落在同一个距离单元里。压缩前的二维 $|\mathrm{IQ}|$ 看起来就是每个脉冲自己的 chirp 包络沿快时间重复，和点目标无法区分。这不是网格求和算错，也不是「体尺度路径展宽只有 $300\,\mathrm{m}$ 把目标设小了」：$300\,\mathrm{m}$ 是规划采集窗用的路径上限，不是显示用的直径。

若希望压缩后看见约 $70$ 个距离单元，需要 $\delta R\sim 1\,\mathrm{m}$，即 $B\sim 150\,\mathrm{MHz}$。复基带采样率满足 $f_s>B$ 即可；讨论中仍按偏保守的 $f_s=2B=300\,\mathrm{MHz}$ 估账。载频必须远大于带宽，现试例 $f_0=1\,\mathrm{MHz}$ 带不动 $150\,\mathrm{MHz}$ 带宽，以后要把载频升到 S/X 波段。这与内存账独立，但和「真要 1 m 分辨」配套。

硬件能实现的最短脉冲定为 $T_{\mathrm{pulse}}=40\,\mu\mathrm{s}$（$20\,\mu\mathrm{s}$ 做不到）。

---

## 2. 现行数据流里，三个「窗」不是一回事

解释内存和字段时必须沿这条链，不要把最终二维数组当成「每个脉冲独立采样一段连续 16 秒」：

```text
观测计划生成
  → 按 PRF 排出发射脉冲，求解发射—散射—接收时刻
  → 按脉宽、路径窗、保护时间得到每脉冲保存行，再取并集得到 Run 级连续 ADC 窗
回波仿真
  → 只对保存行里出现过的全局 ADC 整数索引求唯一集合并计算
  → 映射回二维 [脉冲, 快时间] 写入 echo.npz
反演
  → 读取该二维原始 IQ，再做匹配滤波得到距离像
```

三个术语：

| 术语 | 它是什么 | 它不是什么 |
| --- | --- | --- |
| 有效回波范围 | 脉宽展宽后的物理回波支撑，外加目标相对质心的路径差 | 不含 ADC 保护；前后保护不是物理信号 |
| 脉冲保存行 | 每个脉冲从全局 ADC 轴上切出的固定宽度快时间视图 | 不是接收机按行开关；多行可以引用同一物理样点 |
| Run 级连续 ADC 窗 | 本 Run 所有保存行的时间外包络 | 不是 `schedule.run_duration_s`；也不是射频一直开着 |

`schedule.run_duration_s` 只是允许安排一列完整脉冲的**调度时长**。脉冲数由能完整放入该区间的脉冲决定；射频累计开启时间是 $N_{\mathrm{pulse,run}}\times T_{\mathrm{pulse}}$，通常远小于 $D$。

当前行宽公式（静止、时标伸缩 $S=1$）为

$$
T_{\mathrm{before}}=T_{\mathrm{pre}}+\frac{D_{\mathrm{extent}}}{c},\qquad
T_{\mathrm{after}}=T_{\mathrm{post}}+T_{\mathrm{pulse}}+\frac{D_{\mathrm{extent}}}{c}.
$$

$D_{\mathrm{extent}}$ 的口径是「相对质心的最大额外**双程路径**」，换算时延是 $D_{\mathrm{extent}}/c$，不是 $2D_{\mathrm{extent}}/c$。它已经加在参考回波两侧。

单站椭球半径 $70\,\mathrm{m}$ 时，最大额外双程路径大约是 $2\times 70=140\,\mathrm{m}$。试例 $D_{\mathrm{extent}}=300\,\mathrm{m}$ 已经盖住形体。网格真实差分路径若超过规划值，回波生成器报错，不会悄悄截断。

$T_{\mathrm{pre}}=0.01\,\mathrm{s}$ 按同一口径换成路径是 $c\times 0.01=3000\,\mathrm{km}$ 双程（单程 $1500\,\mathrm{km}$）。相对百米级小行星，这两段时间保护过宽；GUI 又只显示秒，看不出对应多少公里。

---

## 3. 三种字节数（讲解第 2、3 点前必读）

同一组参数会冒出三个完全不同的「多大」。把它们当成同一个数，就会得到「16 秒接收 = 38 GB」这种吓人对账。

记：

| 符号 | 含义 |
| --- | --- |
| $N_{\mathrm{pulse}}$ | 整个试验的脉冲总数，约 $N_{\mathrm{run}}\times\lfloor(D-T_{\mathrm{pulse}})\mathrm{PRF}\rfloor+N_{\mathrm{run}}$ |
| $N_{\mathrm{fast}}$ | 每个脉冲保存行的样点数 `fast_sample_count` |
| $f_s$ | 快时间采样率 |
| $T_{\mathrm{row}}$ | 一行覆盖的时长，约 $T_{\mathrm{before}}+T_{\mathrm{after}}$ |
| $T_{\mathrm{env}}$ | 一个 Run 里从最早保存行左端到最晚保存行右端的外包络时长，约 $D+T_{\mathrm{row}}$ |
| $8$ | 一个复 `float32` 样点的字节数 |

### 3.1 规划器口头说的「连续 ADC 字节」

观测规划写入 `estimated_continuous_iq_bytes`，算法是

$$
M_{\mathrm{envelope}}\approx T_{\mathrm{env}}\times f_s\times 8.
$$

这是把外包络当成**中间没有空隙的一段连续录音**。若脉冲很短、脉冲间隔 $1/\mathrm{PRF}$ 比 $T_{\mathrm{row}}$ 大得多，这段「录音带」里大部分时间没有任何保存行覆盖。这个数会严重偏大，**不是**回波核分配的数组，也**不是** `echo.npz` 的大小。

先前把方案 B 说成「$16\,\mathrm{s}\times 300\,\mathrm{MHz}\times 8=38\,\mathrm{GB}$」，用的就是这个外包络公式。那是错把空隙算进去了。

### 3.2 回波核真正计算的唯一样点

实现是：先得到每行的全局 ADC 整数索引，再 `unique` 去重后计算。脉冲之间若没有保存行覆盖，那些索引根本不进集合。

当 $T_{\mathrm{row}}\ll 1/\mathrm{PRF}$（短脉冲、不太高的 PRF）时，行与行几乎不共享样点，

$$
M_{\mathrm{unique}}\approx N_{\mathrm{pulse,run}}\times N_{\mathrm{fast}}\times 8.
$$

只有当行宽接近或超过脉冲间隔、保存行把外包络几乎铺满时，$M_{\mathrm{unique}}$ 才接近 $M_{\mathrm{envelope}}$。

### 3.3 真正写到硬盘的二维矩阵

`echo.npz` 存的是二维视图，并且同时写 `iq` 和 `clean_iq`：

$$
M_{\mathrm{disk}}\approx 2\times N_{\mathrm{pulse}}\times N_{\mathrm{fast}}\times 8.
$$

规划器的 `estimated_window_iq_bytes` 只计一份 $N_{\mathrm{pulse}}\times N_{\mathrm{fast}}\times 8$，落盘大约再乘 2。

用户最初的 4800 GB 对的就是这一本账，而且和 38 GB 外包络不是同一件事。现试例 $N_{\mathrm{run}}=50$、$D=60\,\mathrm{s}$、$\mathrm{PRF}=20\,\mathrm{Hz}$，脉冲总数就是

$$
N_{\mathrm{pulse}}\approx 50\times 60\times 20=60000.
$$

若按每段接收 $0.02\,\mathrm{s}$、$f_s=300\,\mathrm{MHz}$ 估，每行约 $10^{7}$ 点，一份数组约 $80\,\mathrm{MB}$/脉冲，则

$$
60000\times 80\,\mathrm{MB}=4800\,\mathrm{GB}.
$$

这是「行很长 × 脉冲很多」的乘积。把其中一行压到 70 MB 再乘 60000，仍然是数千 GB，解决不了。下文 70 MB 从来不是每个脉冲的大小。

### 3.4 用同一组数把三本账算完

共同设定：$f_s=300\,\mathrm{MHz}$，路径窗 $D_{\mathrm{extent}}=1\,\mathrm{km}$（时延 $1\,\mathrm{km}/c\approx 3.3\,\mu\mathrm{s}$），忽略现有 $0.01\,\mathrm{s}$ 时间保护。

**短脉冲** $T_{\mathrm{pulse}}=40\,\mu\mathrm{s}$：

$$
N_{\mathrm{fast}}\approx\bigl(40\,\mu\mathrm{s}+2\times 3.3\,\mu\mathrm{s}\bigr)\times 300\times 10^{6}\approx 1.4\times 10^{4}.
$$

一次 Run：$D=16\,\mathrm{s}$，$\mathrm{PRF}=20\,\mathrm{Hz}$，约 $320$ 个脉冲。

| 账本 | 约多少 | 它把空隙算进去了吗 |
| --- | ---: | --- |
| 外包络 $16\times 300\times 10^{6}\times 8$ | $38\,\mathrm{GB}$ | 算进去了，偏大 |
| 唯一样点 $320\times 1.4\times 10^{4}\times 8$ | $36\,\mathrm{MB}$ | 没有 |
| 该 Run 落盘 $2\times 36\,\mathrm{MB}$ | $72\,\mathrm{MB}$ | 没有 |

**长脉冲** $T_{\mathrm{pulse}}=10\,\mathrm{ms}$（现试例）：

$$
N_{\mathrm{fast}}\approx 10\,\mathrm{ms}\times 300\times 10^{6}=3\times 10^{6}.
$$

同样 320 个脉冲：唯一样点约 $7.7\,\mathrm{GB}$，该 Run 落盘约 $15\,\mathrm{GB}$。外包络仍是 38 GB，仍然偏大，但已经和真实落盘同量级，因为每行本身就很长。

上面 72 MB 是**一次** 16 s、320 个短脉冲 Run 的落盘总量，不是每个脉冲 72 MB。每个短脉冲两份数组约

$$
2\times 1.4\times 10^{4}\times 8\approx 0.22\,\mathrm{MB}.
$$

落盘由两个乘数决定，必须分开看：

| 设定 | $N_{\mathrm{pulse}}$ | 每脉冲落盘 | 总落盘 |
| --- | ---: | ---: | ---: |
| 现试例量级：脉宽 $10\,\mathrm{ms}$（或按 $0.02\,\mathrm{s}$ 行宽），60000 个脉冲 | $60000$ | $\sim 48\text{--}80\,\mathrm{MB}$ | **约 $3000\text{--}4800\,\mathrm{GB}$** |
| 只把脉宽改成 $40\,\mu\mathrm{s}$，脉冲数仍为 60000 | $60000$ | $\sim 0.22\,\mathrm{MB}$ | **约 $13\,\mathrm{GB}$** |
| $40\,\mu\mathrm{s}$，一次 16 s、PRF $20\,\mathrm{Hz}$ 的 Run | $320$ | $\sim 0.22\,\mathrm{MB}$ | **约 $70\,\mathrm{MB}$（这一次 Run）** |
| $40\,\mu\mathrm{s}$，整个试验只留几百个脉冲 | $200\text{--}800$ | $\sim 0.22\,\mathrm{MB}$ | **约 $40\text{--}180\,\mathrm{MB}$** |

因此：

1. 4800 GB 是整次试验的二维矩阵，38 GB 是一次 16 s 外包络被误当成连续录音。两本账不要对打。
2. 只缩短脉宽、仍保留 60000 个脉冲，大约从数千 GB 降到十几 GB，还没有小到「随便存」。硬盘更紧就还要减脉冲数。
3. 60000 来自 $50\times 60\,\mathrm{s}\times 20\,\mathrm{Hz}$，不是周期测量的硬性需求。$7200\,\mathrm{s}$ 自转用十几到几十次短 Run 取样，脉冲总数可以是几百而不是六万。

讲解时应先画「节拍器」：每个脉冲只录一小段磁带（保存行），两下滴答之间的空白既不计算也不存盘。只有把每一下滴答录成很长一段、并且滴答很密、把空白填满时，才会接近「整段 16 秒都按 $300\,\mathrm{MHz}$ 录音」。

---

## 4. 字段问题：时间保护 vs 未知尺度

### 4.1 实际观测怎么做

地基行星雷达事先没有「真实直径」。作业上是：星历给出质心距离，再开一扇距离门，门宽盖住预报误差和目标可能的径向尺度。回波落在门外就等于没采到，下次把门加宽。采集裕量用来囊括未知形体，而不是先知道直径再另加一段保护。

### 4.2 本仓库现在怎么配

GUI「接收采样」同时有：

- 「体尺度路径展宽」`target.extent_path_m`（米，已经是路径门）
- 「ADC 前置/后置保护」`pre_guard_s` / `post_guard_s`（秒）

两套输入对使用者没有观测对应物。时间保护按秒编辑，看不出是 $1500\,\mathrm{km}$ 量级的单程距离。仿真器把「超了就报错的规划支撑」和「只是多采噪声的时间保护」拆开，是实现细节，不是观测流程。

### 4.3 已同意的改法（本方案要实施的核心）

Chirp 下：

1. 从配置和 GUI 删除 `pre_guard_s`、`post_guard_s`。
2. 只保留一个以米为单位的采集路径窗，继续使用 JSON 键 `observation.target.extent_path_m`（避免再引入同义字段）。
3. GUI 标签改为「距离保护」或「采集路径窗」，单位 m/km。含义：相对质心参考回波，两侧各允许的最大额外双程路径。时延 $T_{\mathrm{gate}}=D_{\mathrm{extent}}/c$。未知小行星尺度、星历误差、希望多留的余量，都进这一个数。建议试例用 $1\,\mathrm{km}$。
4. 行宽改为 $T_{\mathrm{before}}=T_{\mathrm{gate}}$，$T_{\mathrm{after}}=T_{\mathrm{pulse}}+T_{\mathrm{gate}}$，后置仍保留现行半个采样的栅格补偿（只影响最多 1 列，与物理门宽无关）。
5. 同一卡片用只读文字显示换算：$T_{\mathrm{gate}}$、前沿取整后的样点数 $n_{\mathrm{pre}}$、整行 $N_{\mathrm{fast}}$、压缩后 $\delta R=c/(2B)$。不要用可编辑框显示派生量。落地后的 $n_{\mathrm{pre}}=\lceil T_{\mathrm{gate}}f_s+0.5\rceil$，含前沿半个采样，见变更说明。
6. 自动选时的调度预留 $H$ 里现在加的 `post_guard_s`，改为加 $T_{\mathrm{gate}}$。相对光行时（试例约百秒）这项可以忽略。
7. 连续波仍走连续 `receive`，不出现该 Chirp 路径窗。
8. 旧 JSON 迁移：$D_{\mathrm{extent}}\leftarrow \max\bigl(D_{\mathrm{extent}},\,c\,T_{\mathrm{pre}},\,c\,T_{\mathrm{post}}\bigr)$，避免静默缩短已有窗；然后丢掉两个时间字段。

脉宽仍单独存在：它是发射波形持续多久，不是小行星有多大。未压缩记录时，它主导 $N_{\mathrm{fast}}$。

网格真实路径超过 $D_{\mathrm{extent}}$ 时继续报错，对应「回波落到距离门外」。

---

## 5. 脉冲重复频率可以降，降的不是距离分辨

PRF 是一次发射 Run **内部** 节拍器的快慢，配置字段 `observation.transmit.prf_hz`。它不是快时间采样率，也不是飞机雷达那种「距离不模糊 PRF」。本项目单站模式是发完一串脉冲再切换接收，约束主要是 $T_{\mathrm{pulse}}\le 1/\mathrm{PRF}$。

把 PRF 从 $20\,\mathrm{Hz}$ 降到 $2\,\mathrm{Hz}$，**不会**让 $\delta R$ 变差，**不会**让 $1\,\mathrm{km}$ 路径窗变窄，**也不会**让每个脉冲的 $N_{\mathrm{fast}}$ 变大。每一拍录多长，由脉宽和路径窗决定；PRF 只决定同一段调度时长 $D$ 里拍多少下。

同一 Run 内脉冲数大约是

$$
N_{\mathrm{pulse,run}}=\bigl\lfloor(D-T_{\mathrm{pulse}})\mathrm{PRF}\bigr\rfloor+1.
$$

PRF 降一倍，脉冲减半。因此：

| 会变什么 | 说明 |
| --- | --- |
| 总脉冲数、落盘 | $M_{\mathrm{disk}}\propto N_{\mathrm{pulse}}$，降 PRF 直接瘦身 |
| 物理回波是否重叠 | PRF 越低，相邻有效回波越不容易相交，更安全 |
| 仿真里配置的 `snr_db` | 不会自动随 PRF 变差；它是加在已生成回波上的 |
| 反演能积累的脉冲 | 脉冲少了，相干/非相干积分变弱。噪声关闭时看不出来 |
| 真实雷达平均功率 | $\propto \mathrm{PRF}\times T_{\mathrm{pulse}}$。$40\,\mu\mathrm{s}\times 20\,\mathrm{Hz}$ 占空比已是 $8\times 10^{-4}$；再降到 $1\,\mathrm{Hz}$ 更低。本仿真不会自动按占空比改 SNR |
| 距离–多普勒是否混叠 | 自转引起的多普勒带宽约 $2\omega R/\lambda$。现试例 $1\,\mathrm{MHz}$ 上可忽略；X 波段约 $2\,\mathrm{Hz}$ 量级，PRF 宜大于该带宽。只做跨 Run 的光变周期搜索时，用的是 Run 之间的间隔，不是 Run 内 PRF |
| 现行 16 s CPI | `inversion.cpi_duration_s` 按 $\lceil 16\cdot\mathrm{PRF}\rceil$ 换成脉冲数。PRF 太低或 Run 太短，组内脉冲不足 2 个时，反演退回逐脉冲距离像特征，周期搜索仍可做，只是没有距离–多普勒立方 |

不要把 PRF 降到在时长 $D$ 里平均排不进一个完整脉冲。为看清距离像并做周期搜索，$1\text{--}5\,\mathrm{Hz}$ 比现在的 $20\,\mathrm{Hz}$ 更省，仍然安全。以后若做 X 波段成像，再把 PRF 抬回去，并让单次 Run 覆盖想要的 CPI 时长。

降低 PRF **不能**替代缩短脉宽：PRF 只减少「拍多少下」，脉宽决定「每一拍磁带有多长」。60000 个 $10\,\mathrm{ms}$ 脉冲的 TB 级落盘，主因是每一拍太长、拍数太多；把 PRF 降到 $1\,\mathrm{Hz}$ 而 $D$ 仍是 $60\,\mathrm{s}$，每个 Run 仍有约 60 拍，每拍若仍是 $10\,\mathrm{ms}\times 300\,\mathrm{MHz}$，单个 Run 仍是 GB 级。

---

## 6. 「改存储契约」能省盘，但解决的不是 38 GB 外包络

反演和 GUI 预览今天都是：读入未压缩二维 IQ，再做匹配滤波。压缩后，一个脉冲的有用长度大约是路径门对应的时延，而不是整段 $T_{\mathrm{pulse}}$。

若改为 `echo.npz` 只存匹配滤波后的距离像：

- 列数大约按门宽，而不是按脉宽。$1\,\mathrm{km}$ 门、$300\,\mathrm{MHz}$ 时约 $2\times 10^{3}$ 列，不是 $40\,\mu\mathrm{s}$ 未压缩的 $\sim 10^{4}$ 列，更不是 $10\,\mathrm{ms}$ 的 $3\times 10^{6}$ 列。
- $40\,\mu\mathrm{s}$ 时大约再省数倍到十倍；$10\,\mathrm{ms}$ 时能省三个数量级。后者才是「15 GB → 几十 MB」。
- **不会**按比例减少回波生成的计算量：核函数仍在未压缩支撑上求和。变的是写盘和反演读入。
- 列的含义从「原始快时间」变成「时延/距离」，反演输入契约要改。周期估计算法可以不动，但已碰到 inversion 边界。

本方案**先不改存储契约**。先靠 $T_{\mathrm{pulse}}=40\,\mu\mathrm{s}$、单一 $1\,\mathrm{km}$ 路径窗、降低 PRF 与 Run 规模。按第 3.4 节，16 s、PRF $=20\,\mathrm{Hz}$ 的短脉冲 Run 落盘约几十 MB，不需要改契约来「消灭 38 GB」——那 38 GB 本来就不是落盘量。

若实施字段修改之后脉宽仍不能短、落盘仍然太大，再单独立项「回波阶段写入压缩距离像」。不要和删时间保护捆在一次提交里。

---

## 7. 建议的试例参数（字段改完后）

目的：压缩后能分辨百米级形体；原始 `echo.npz` 为百 MB 量级或更小；不改反演算法、不改 ADC 模块归属。

| 字段 | 建议 | 用意 |
| --- | ---: | --- |
| `bandwidth_hz` | $150\,\mathrm{MHz}$ | $\delta R\approx 1\,\mathrm{m}$ |
| `fast_sample_rate_hz` | $180\text{--}200\,\mathrm{MHz}$；对账可用 $300\,\mathrm{MHz}$ | 复基带 $f_s>B$ 即可 |
| `carrier_frequency_hz` | $\ge 2.3\,\mathrm{GHz}$ | 带宽必须远小于载频 |
| `pulse_width_s` | $40\,\mu\mathrm{s}$ | 硬件下限；主导未压缩 $N_{\mathrm{fast}}$ |
| `extent_path_m` | $1\,\mathrm{km}$ | 唯一采集路径窗（未知尺度 + 余量） |
| `pre_guard_s` / `post_guard_s` | 删除 | 并入上一行 |
| `prf_hz` | $1\text{--}5\,\mathrm{Hz}$（成像再升高） | 减少脉冲数；不改变 $\delta R$ |
| `run_duration_s` | 亚秒到数秒（看是否还要 16 s CPI） | 控制单次 Run 脉冲数 |
| `run_count` | 十几到几十，覆盖约 2 个 $7200\,\mathrm{s}$ 自转周 | 周期搜索靠 Run 间距，不靠 Run 内高 PRF |

`inversion.cpi_duration_s` 若仍为 $16\,\mathrm{s}$，则每个相干组需要足够脉冲。短 Run 或很低 PRF 时会走逐脉冲回退；这是现行反演行为，本方案不改算法去「补上」多普勒立方。

---

## 8. 明确不做

- 不实施 [ADC_PLANNING_REFACTOR_PLAN.md](ADC_PLANNING_REFACTOR_PLAN.md)（ADC 整数网格从观测迁到回波）。
- 不改 inversion 周期估计算法，不把 `echo.npz` 改成只存压缩距离像（可另立项）。
- 不把路径窗和脉宽合并成一个数。
- 不把本方案写成已经交付的功能。

---

## 9. 以后改代码时会动到的位置

- 行宽与内存估算：`observation/src/planning.py`
- 调度预留 $H$：`observation/src/campaign_planning.py`
- 配置校验：`observation/src/config_normalize.py`
- GUI：`rotation_gui/schema.py`、`rotation_gui/window/parameter_form.py`（接收采样卡片）
- 试例：`configs/chirp_mesh_target_test.json` 以及仍含时间保护的 Chirp 配置
- 术语与手册：`docs/4.2/GLOSSARY.md`、`docs/4.2/OBSERVATION_TIME_SELECTION.md`、`docs/4.2/GUI_USER_MANUAL.md`
- 现有 `pre_guard_s` / `post_guard_s` 回归测试改为等价的 $D_{\mathrm{extent}}/c$，后置 $+0.5$ 格补偿的物理保证不变

---

## 10. 给讲解者的两段话

用户已经认同第 4.3 节「一个路径窗、删掉时间保护」。下面两段对应讨论里没看懂的部分。

**PRF：** 把它说成「一次开启发射时，节拍器每秒响几下」。响得慢，同样 60 秒里脉冲少，文件小，积分弱；每一响录多长、距离单元多细，由脉宽和带宽决定，跟节拍快慢无关。小行星转一圈要两小时，看周期主要靠多次 Run 之间隔多久，不靠 Run 里面拍得有多密。

**38 GB 与 4800 GB：** 38 GB 是一次 16 s Run 的外包络被当成连续录音。4800 GB 是 60000 个长行的二维矩阵。70 MB 是「$40\,\mu\mathrm{s}$ 脉宽、320 个脉冲」那一次 Run 的总和，约 $0.22\,\mathrm{MB}$/脉冲，不是 $70\,\mathrm{MB}$/脉冲。60000 个短脉冲大约仍有 13 GB；要再小，必须把 $50\times 60\,\mathrm{s}\times 20\,\mathrm{Hz}$ 也砍掉。改存储契约是下一步，不是用来解释 38 GB 的。
