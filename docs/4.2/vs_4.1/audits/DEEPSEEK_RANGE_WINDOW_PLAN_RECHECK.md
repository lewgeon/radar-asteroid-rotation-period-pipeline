# 对 DeepSeek 关于距离门方案文档的核实

> 核实对象：外部模型对 [../plans/RANGE_WINDOW_AND_HIGH_RESOLUTION_PLAN.md](../plans/RANGE_WINDOW_AND_HIGH_RESOLUTION_PLAN.md) 的审阅。  
> 对照代码：当前工作区 `observation/src/planning.py`、`echo/src/echo.py`、`observation/src/config_normalize.py`、`observation/src/campaign_planning.py`、`rotation_gui/`、`configs/chirp_mesh_target_test.json`。  
> 本文件只下判断，不改方案正文、不改业务代码。

外部审阅把诊断和策略方向评为正确，并列出 P1–P7。下面按「成立 / 部分成立 / 不成立」核实。外部读到的方案稿仍含「$2.9\times 10^{15}\,\mathrm{B}$」一句；**当前方案稿已改成 3000–4800 GB 对照表**，P1 对旧稿成立、对现行稿过时。

## 成立

### P4 生成器在 unique 之前就按二维全尺寸分配

`echo/src/echo.py` 在进入 Run 循环之前构造：

- `global_q`（int64，`row_start[:, None] + columns`）
- `sample_times`（float64）
- `valid`（bool）
- `clean`（复 float32/64，形状与 `global_q` 相同）

尺寸都是 $N_{\mathrm{pulse}}\times N_{\mathrm{fast}}$。观测阶段 `planning.py` 的 `row_valid` 同样是这个形状。

按「60000 脉冲 × $10\,\mathrm{ms}$ × $300\,\mathrm{MHz}$ → $N_{\mathrm{fast}}\approx 3\times 10^{6}$」：仅 `global_q` 约 $1.4\,\mathrm{TB}$，再加上时间和二维 `clean`，在 `np.unique` 之前就会 OOM。方案 §3 的三本账只覆盖「外包络 / unique 求和缓冲 / 落盘」，漏了这第四本：**二维索引与回填数组**。

对方案 §7 的短脉冲、几百个脉冲，这一项大约是 GB 级以下，不是新瓶颈；对「只改 $B,f_s$、仍保留 60000 个 $10\,\mathrm{ms}$ 脉冲」则是比 38 GB 外包络更硬的失败点。实施前应写入方案。

### P6 旧键不能只从白名单里删掉

`normalize_observation_config` 先 `_reject_deprecated_keys`，再 `validate_observation_config` → `_reject_unknown`。`receiver_sampling` 白名单目前是 `fast_sample_rate_hz`、`pre_guard_s`、`post_guard_s`。

从白名单删除后，旧 JSON 会报「未知配置字段」，不会自动走方案 §4.3 第 8 条的 $\max$ 合并。现有 `_reject_deprecated_keys` 的先例是**拒绝并提示新键名**，不是静默改写（文件头写明 deprecated keys are rejected instead of being silently migrated）。方案写「迁移后丢掉」与这条模块政策冲突，实施时必须二选一写清：一次性合并，或拒绝旧键并要求手改 `extent_path_m`。

§9 清单应补 `docs/4.2/PROJECT_OVERVIEW.md`、`observation/README.md`（约 418–423 行仍列前置/后置保护）。`GLOSSARY.md`、`GUI_USER_MANUAL.md` 方案已点名。

### P7 试例反演周期窗盖不住 $7200\,\mathrm{s}$

`configs/chirp_mesh_target_test.json` 里 `echo.target.rotation_period_s=7200`，`inversion.period_min_s=100`、`period_max_s=1000`。这是**现试例已有**的缺口，不是字段合并引入的。若改完参数后还要用这个 JSON 跑通周期搜索，必须把搜索窗扩到覆盖 $7200\,\mathrm{s}$。只谈 CPI 回退不够。

### 小项：调度预留 $H$ 会变短

`campaign_planning.py` 现在把 `post_guard_s`、$D_{\mathrm{extent}}/c$、$T_{\mathrm{pulse}}$ **三项相加**。删掉时间保护后，等价于从 $T_{\mathrm{post}}+D/c$ 变成只有 $T_{\mathrm{gate}}=D/c$，预留变短。方案应写明，避免被理解成「把 post_guard 改个名字」。

### 小项：压缩存储的距离轴

若将来只存匹配滤波后的距离像，`inversion.py` 用 `row_fast_time_offset_s` 与 `centroid_fractional_offset_s` 构造 `delay_axes`。另立项时必须一起落盘。方案把它留在 §8 合理，边界值得记下。

### 小项：1 m 分辨下网格看上去像什么

1280 面元、半径 $70\,\mathrm{m}$ 的椭球，面元尺度与 $1\,\mathrm{m}$ 分辨同量级，凸光滑体回波还偏镜面。压缩后更可能是亮点加展宽，而不是均匀 70 个距离单元。这是预期说明，不是策略错误。

## 部分成立

### P1 $2.9\times 10^{15}\,\mathrm{B}$

算术：

$$
2\times 60000\times 3\times 10^{6}\times 8=2.88\times 10^{12}\,\mathrm{B}\approx 2.9\,\mathrm{TB}\ \text{（约 }2880\,\mathrm{GB}\text{）}.
$$

旧稿写成 $10^{15}$（PB）大了 1000 倍。方向（「长行 × 60000 脉冲才是硬盘问题」）仍对；用户的 4800 GB 对应「每行约 $10^{7}$ 点、一份数组 $80\,\mathrm{MB}$」，与 $2\times$ 落盘的 $10\,\mathrm{ms}$ 账（约 2.9 TB）本就不是同一行宽。

**现行方案稿已删除 $10^{15}$ 那句**，改成 3000–4800 GB 对照表。对现行稿 P1 已不成立。

### P5 只读换算

参数表单里确实没有通用的「派生只读字段」控件；`setReadOnly` 只出现在日志框。但同表单已有 `ScheduleFeedbackWidget` 和字段 `setToolTip`。换算可以做成标签或提示，不必先做一套新控件。工作量有，方案写成一行 bullet 偏短，说「完全没有承载机制」过重。

### P3 数据流措辞

方案写：先对保存行出现过的全局 ADC 索引 `unique`，再「映射回二维写入」。实现是 `echo.py` 在一维 `run_signal` 上求和，再按行 `searchsorted` 填进二维 `clean`。仓库 `AGENTS.md` 用的就是「唯一全局 ADC 索引求和，再按 `row_start_sample` 映射回二维」。二维落盘是**物化后的重叠视图**，不是「逐行独立生成」。

外部认为这违背术语规则，过严。可补半句「二维是重叠视图，但 `echo.npz` 仍按完整二维数组保存」，不是必须推翻 §2。

### P2 $M_{\mathrm{unique}}$ 与外包络

方案 §3.2 比较的是 **unique 对 $M_{\mathrm{envelope}}$**：行宽 $\ll$ PRT 时 unique 远小于外包络；行把外包络铺满时 unique 才接近外包络。这与 `np.unique` 一致，也解释「38 GB 为什么不是落盘」。

外部把比较对象换成 **unique 对二维 $N_{\mathrm{pulse}}N_{\mathrm{fast}}$**：重叠时 unique 更小，所以「重叠省内存」。两句话都对，对象不同。方案没有把不等式写反。外部写的

$$
M_{\mathrm{unique}}\le 8 f_s(N_{\mathrm{pulse,run}}T_{\mathrm{row}}+D_{\mathrm{env}})
$$

把两项相加，比 $\min(N_{\mathrm{pulse}}N_{\mathrm{fast}},\,T_{\mathrm{env}}f_s)$ 更松，不宜当作更精确的公式。

可在 §3.2 加一句：相对二维矩阵，重叠降低 unique；相对外包络，铺满才是 unique 的上界。不是推倒重写。

## 不成立

### §3 与 §5 的脉冲数公式互相矛盾；16 s 应为 321 个脉冲

§3 的 $N_{\mathrm{pulse}}=N_{\mathrm{run}}\times\lfloor(D-T_{\mathrm{pulse}})\mathrm{PRF}\rfloor+N_{\mathrm{run}}$ 就是 $N_{\mathrm{run}}\times N_{\mathrm{pulse,run}}$。  
§5 的 $N_{\mathrm{pulse,run}}=\lfloor(D-T_{\mathrm{pulse}})\mathrm{PRF}\rfloor+1$ 与 `campaign_planning.py` 一致（另有 `+1e-12`）。

$D=16$、$\mathrm{PRF}=20$、$T_{\mathrm{pulse}}=40\,\mu\mathrm{s}$：

$$
\lfloor(16-4\times 10^{-5})\times 20\rfloor+1=\lfloor 319.9992\rfloor+1=320.
$$

外部的 321 把脉宽从减数里拿掉了。方案用 320 与代码一致。

### 「PRF 上限是 $T_{\mathrm{pulse}}+T_{\mathrm{switch}}+T_{\mathrm{safety}}\le 1/\mathrm{PRF}$」

这不是本项目的单站约束。单站约束是：**整列脉冲发完 + 切换 + 安全余量，必须早于本 Run 最早有效回波**（光行时对 $D$ 的限制），不是每个 PRT 里塞进切换。现试例 $T_{\mathrm{pulse}}=0.01\,\mathrm{s}$、切换与余量各 $0.2\,\mathrm{s}$、PRF $=20\,\mathrm{Hz}$ 已经违反那条伪不等式，但合法。方案 §7「1–5 Hz 有足够余量」不靠这条。

### 「$40\,\mu\mathrm{s}$ 对应 6 m 距离游走」

未压缩 chirp 的单程跨度是 $c T_{\mathrm{pulse}}/2=6\,\mathrm{km}$，不是 $6\,\mathrm{m}$。目标速度 $100\,\mathrm{m/s}$ 时脉内位移约 $4\,\mathrm{mm}$，与门宽无关。

## 外部已确认、本侧同样同意的部分

- 网格像点目标：$\delta R\approx 150\,\mathrm{km}$，$70\,\mathrm{m}$ 形体落在同一距离单元；`extent_path_m` 不是显示直径。
- 三本账的代码位置：`planning.py` 外包络与一份窗口字节、`echo.py` 的 `unique` 与 `iq`/`clean_iq` 双份落盘。
- 降 PRF 不改变 $\delta R$、门宽、$N_{\mathrm{fast}}$；`snr_db` 不随占空比自动变。
- CPI 不足时 `inversion.py` 仅在那句固定中文错误上退回逐脉冲特征。
- 载频相位用 `remainder(path * f0 / c, 1)`，升到 S/X 波段不靠这条炸精度。
- 网格路径超过规划窗继续报错；后置 $+0.5$ 格应保留。
- 先改字段口径和参数、存储契约另立项、不与 ADC 职责迁移捆绑：方向仍对。

## 建议（仍先改文档，再写代码）

1. 把 P4 写成第四本账，并写明：保留 60000 个长行时，二维索引会先于 unique 把内存打满。
2. 写清旧 `pre_guard_s`/`post_guard_s`：合并还是拒绝；补文档清单。
3. 若更新 `chirp_mesh_target_test.json`，同步 `period_min_s`/`period_max_s`。
4. 明写 $H$ 去掉 $T_{\mathrm{post}}$ 后变短。
5. §3.2 补一句比较对象，不必按「推反了」整段推翻。
6. 不要采用外部的 321 脉冲伪不等式和「PRF 受切换时间限制」那条。
