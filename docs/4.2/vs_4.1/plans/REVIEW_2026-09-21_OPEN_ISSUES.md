# 4.2 当前版本遗留问题（2026-09-21 复核）

> **状态：文档与守卫项已处理；L3 临时目录清理仍暂缓。** 落地结果见 `../changes/RUNTIME_LOGIC_FIXES_2026-09-21.md` 与 `../changes/CHIRP_ROW_CONTRACT_2026-09-21.md`。本文保留原复核记录，行号对应当时快照。
>
> **复核对象**：工作区当前版本（`observation/`、`echo/`、`inversion/`、`rotation_gui/`、`docs/4.2/`）。
> **范围**：只列**当前仍然存在**的问题。已修项、已接受为近似或已明确暂缓的项见 §5。
> **方法**：读代码定位，再用 §4 的命令复现；数值均为本轮实测。

---

## 1. 问题清单

| 编号 | 类型 | 严重度 | 位置 | 一句话 |
|---|---|---|---|---|
| D1 | 文档·行为错误 | 中 | `../../OBSERVATION_TIME_SELECTION.md:172` | 仍称行宽 +1 后 `window_overlap` "判定不受影响" |
| D2 | 文档·结论错误 | 中 | `../changes/OBSERVATION_RECEPTION_WINDOW.md:94`（两份 DATE_LOG 同错） | "$\delta=0$ 仍可能出现"不成立；用文档自己的公式即可证 $\delta\in\{1,2\}$ |
| D3 | 文档·前后冲突 | 低 | `../changes/OBSERVATION_RECEPTION_WINDOW.md:116` | 仍写"$S_i$ 恒定时 $\delta\in\{0,1,2\}$"，与 §5 的结论冲突 |
| D4 | 文档·公式过期 | 低 | `../changes/OBSERVATION_RECEPTION_WINDOW.md:31` | 符号表仍写 $n_{\mathrm{after}}=\lceil T_{\mathrm{after}}f_s\rceil$，缺栅格补偿 |
| D5 | 文档·计数过期 | 低 | `KNOWN_DEFECTS.md:145` | 仍写 CW 被迫写"10 个"行轴字段（实为 12） |
| T1 | 测试·守护强度不足 | 中 | `observation/tests/test_planning_regressions.py:280` | 网格断言只挡得住约 $\ge 0.16$ 采样的破坏；$0.013\sim0.063$ 采样的破坏仍全绿 |
| T2 | 缺守卫 | 低 | `inversion/`、`rotation_gui/` 载入侧 | observation 的行宽与 `echo.npz` 的行宽不一致时静默通过 |
| L1 | 记录·与现状不符 | 低 | `../changes/DATE_LOG_2026-09-19.md:177` | 声称删除 4 个 `echo/tmp/cli_smoke_*`，工作区仍有 2 个 |
| L2 | 记录·命名 | 低 | 引用的 `DATE_LOG_2026-09-21.md` | 该文件不存在；09-21 的两轮复核记在 `DATE_LOG_2026-09-19.md` 里 |
| L3 | 卫生 | 低 | `observation/tmp/`、通用文档 | 7 个历史残留未清理；`adc_window_duration_s` 未进任何通用文档 |

---

## 2. 逐条说明

### D1 `window_overlap` 的"不受影响"是行为性错误（文档未改）

**现状**：`OBSERVATION_TIME_SELECTION.md:172` 写：

> 代价是行宽最多增加 1 格；本例（0.03 s @ 5000 Hz）由 150 变为 151，故 $N_{\mathrm{fast}}=252$。相邻行因此共享 2 个而不是 1 个 ADC 索引，`window_overlap` 的判定不受影响（它只比较行起点与行宽）。

**为什么错**：判据（`starts[i+1] < starts[i] + fast_count`）确实没改，但**行宽是该判据的输入之一**，行宽 +1 会翻转结论。同一批改动在 `KNOWN_DEFECTS.md §1` 与 `DATE_LOG_2026-09-18.md` §6c 里已经承认这一点并附了最小算例（`fs=5000`、`pre=0.01`、`post=0.0298`、脉宽 `0.01`、`prf=20`：旧行宽 250 = 行距、无重叠；新行宽 251 → 相邻行全部标记重叠）。通用文档里这一句没有同步，读者会得到相反结论。

**建议**：改为"判据不变，但行宽是它的输入，+1 会把'行宽恰好等于行距'的配置翻成重叠"，并指向 `KNOWN_DEFECTS.md §1` 的算例。

### D2 "$\delta=0$ 仍可能出现"不成立（结论错误，两份 DATE_LOG 沿用）

**现状**：`OBSERVATION_RECEPTION_WINDOW.md:94` 写"例如 `after_s·fs` 的 frac 恰为 0.5 或落在 (0, 0.5] 时 $\delta=0$，frac=0 或 > 0.5 时 $\delta=1$"；`DATE_LOG_2026-09-19.md:107-111` 与 §4 的表、`DATE_LOG_2026-09-18.md:222` 用同样的算例得出"$\delta=0$ 仍可能出现"，并把值域放宽成 $\delta\ge 0$。

**为什么错**：那两个算例算的是 `ceil(b+0.5)` 与 `ceil(b)` 的差，也就是**行宽（$n_{\mathrm{after}}$）的增量**，而 $\delta$ 的定义是**窗尾相对旧规则的推迟量**，还要加上质心锚定项。用文档 §5 自己的式子（`OBSERVATION_RECEPTION_WINDOW.md:92`）：

$$\delta=\mathrm{rint}(a)+\lceil b+0.5\rceil+1-\lceil a+b\rceil,\qquad a=m+f,\ b=n+g,\ f,g\in[0,1)$$

$m,n$ 为整数，记 $\rho=\mathrm{rint}(m+f)-m\in\{0,1\}$（$f<0.5$ 取 0；$f>0.5$ 取 1；$f=0.5$ 按 `rint` 的偶数舍入取 0 或 1，两种情形结论相同），则

$$\delta=\rho+\lceil g+0.5\rceil+1-\lceil f+g\rceil .$$

- $\rho=0$（即 $f<0.5$）：$f+g<g+0.5\Rightarrow\lceil f+g\rceil\le\lceil g+0.5\rceil$，故 $\delta\ge 1$；
- $\rho=1$（即 $f>0.5$）：$f+g>g+0.5$。若 $f+g\le 1$ 则 $\lceil f+g\rceil=1$ 且 $\lceil g+0.5\rceil=1$（因 $g\le0.5$），$\delta=2$；若 $f+g>1$ 则 $\lceil f+g\rceil\ge2=\lceil g+0.5\rceil$（因 $g>0.5$），$\delta\le2$ 且 $\ge1$，实际只能是 2。

**结论**：$\delta\in\{1,2\}$，**下界是 1，不可能是 0**；两个算例（$b=150.5$ 与 $b=150.2$）正确结果是 $\delta=1$。可用代码侧交叉验证：新窗尾 $=$ `rx_adc_start + (rint(a) + n_after + 1)/fs`（`observation/src/planning.py:257-270` 的 `centroid_index`/`starts`/`q_off`），与文档 §5 的 4.2 侧一致；用 4 组真实参数（`post` = 0.0198 / 0.0199 / 0.02004 / 0.02014 s）实测 $\delta$ = 2 / 2 / 1 / 2，与上式相符。

**影响**：`DATE_LOG_2026-09-19.md` §4 的"未采纳"表把"复核说 $\delta\in\{1,2\}$"判为不成立，这一条判断是错的，作者据此把值域从 $\{1,2\}$ 改成了更弱的 $\delta\ge0$，方向相反。

**建议**：只改**行为文档**（`OBSERVATION_RECEPTION_WINDOW.md` §5/§6.3 与 D3 的 §116），把结论写回 $\delta\in\{1,2\}$，并同时说明"行宽增量 $\lceil b+0.5\rceil-\lceil b\rceil\in\{0,1\}$，触发条件是 $\mathrm{frac}(b)=0$ 或 $>0.5$"——两个量分开写，避免再次混淆。两份 `DATE_LOG` 是历史记录，按版本目录"快照不重写"的约定**不必回改**，但其 $\delta$ 结论以本文与行为文档为准（可在文首加一行"$\delta$ 的结论已被后续复核更正"）。

### D3 同一文件里 $\delta$ 的值域仍有一处是旧的

**现状**：`OBSERVATION_RECEPTION_WINDOW.md:116`（§6.3 代价 1）写"右端推迟量为 $\delta$（见 §5，$S_i$ 恒定时 $\delta\in\{0,1,2\}$）"，而 §5(:94) 已改成 $\delta\ge0$，:96 又说"$\delta$ 的表达式不变但上界不再是 2"——三处互相矛盾。

**建议**：统一为 D2 的结论 $\delta\in\{1,2\}$（$S_i$ 恒定），并删掉残留的 `0`。

### D4 符号表里的 $n_{\mathrm{after}}$ 缺栅格补偿

**现状**：`OBSERVATION_RECEPTION_WINDOW.md:31` 的符号表写 `n_after`$=\lceil T_{\mathrm{after}}f_s\rceil$，而 §5(:83)、§6(:106)、§8(:129) 与代码（`observation/src/planning.py:203`）都是 $\lceil (T_{\mathrm{post}}+\max_iW_i)f_s+0.5\rceil$。

**建议**：符号表补 `+0.5`，否则读者会按缺补偿的公式复算行宽（默认点目标夹具 251 vs 实际 252）。

### D5 CW 行轴字段数仍写 10

**现状**：`KNOWN_DEFECTS.md:145` 写"CW（一维 `iq`）被迫写出 10 个它从不读取的行轴字段"。实际 `_ROW_AXIS_FIELDS`（`inversion/src/dataset.py`）是 **12** 个：`coherence_id`、`acquisition_id`、`run_id`、`track_id`、`row_start_sample`、`row_fast_time_offset_s`、`centroid_fractional_offset_s`、`rx_adc_start_elapsed_s`、`rx_adc_stop_elapsed_s`、`signal_echo_overlap`、`window_overlap`、`common_path_rate_m_s`。同一错误在两份 `DATE_LOG` 里已经订正过（10 → 12），此处漏改。

**建议**：改为 12，并说明 CW 的 `echo.npz` 键数因此是 24 − 12 = 12。

### T1 网格守护测试的守护强度不足（不是"有没有扫一片参数"的问题，而是"扫得够不够密"）

**现状**：`test_post_guard_margin_grid_never_negative`（`observation/tests/test_planning_regressions.py:280`）对 `fs × pre × post × prf = 4×3×4×3` 共 144 组取最坏后置裕量，断言非负。它对 `+0.5 → +0.25` 这类大变异确实变红，因此 `DATE_LOG_2026-09-19.md` §3.7 把它记为已解决。

**问题**：这 144 组里 `post_guard·fs` 只取 4 个值（`0/0.0007/0.0019/0.02` 乘 4 个 $f_s$），它把 $b=T_{\mathrm{after}}f_s$ 的小数位钉在少数几个点上。把补偿常量 `+0.5` 换成 $c$ 后逐个测同一套网格与"小数位密扫"（$f_s=1000$、`prf`=20.5、`pre`=0，把 `post_guard·fs` 的小数位扫到 0.001）：

| 补偿常量 $c$ | 144 组网格最坏 | 网格外密扫最坏 | 网格断言 |
|---|---|---|---|
| 0.50（现实现） | $+0.0385$ | $+0.0366$ | 绿，且确实无缺口 |
| 0.49 | $+0.0385$ | $+0.0266$ | 绿，确实无缺口 |
| 0.45 | $+0.0385$ | $-0.0134$ | **绿（漏报）** |
| 0.42 | $+0.0385$ | $-0.0434$ | **绿（漏报）** |
| 0.40 | $+0.0385$ | $-0.0634$ | **绿（漏报）** |
| 0.30 | $-0.1634$ | $-0.1634$ | 红（能发现） |
| 0.25 | $-0.1634$ | $-0.2134$ | 红（能发现） |

即：**保证被破坏到 0.013～0.063 个采样时，这条断言仍然全绿**；它实际守住的是"缺口 $\ge$ 约 0.16 采样"。（顺带：`DATE_LOG_2026-09-19.md:123` 记的 $-0.1644$ 与本次密扫的 $-0.1634$、$-0.2134$ 只是扫描点不同，不是矛盾。）

另外两处作用域限制（方向没错，但覆盖不到就守不住）：

1. 它的需求侧写的是 `max(receive) + 脉宽 + post_guard`（:314），而不是 $\max_i(t_{\mathrm{rx},i}+W_i)$；只有各行 $W_i$ 相同时两者才相等，即**逐脉冲伸缩不同、或含目标路径展宽时它不成立**。
2. 几何固定为 `_solution(schedule, 1.0)`（恒定时延、`target_extent_path_m=0`、单 Run），因此**不覆盖** `target_extent_path_m>0` 与多 Run 情形。

**建议**（任选，建议 1+2 一起）：

1. 断言改成直接用解析下界，而不是靠参数网格撞：对任意参数都有 `n_after >= after_s*fs + 0.5`（即 `fast_sample_count >= n_pre + after_s*fs + 1.5`），一条不等式就能守住全部小数位；
2. 需求侧改用 $\max_i(t_{\mathrm{rx},i}+W_i)+T_{\mathrm{post}}$，并把 `target_extent_path_m>0`、多 Run 加进网格；
3. 若仍保留网格版本，至少把 `post_guard·fs` 的小数位按 0.05 或更细扫一遍（成本很低，144 组现在约 1 秒）。

### T2 缺"observation 行宽 ↔ echo 行宽"的一致性守卫

**状态（2026-09-21）**：已修复。根 pipeline、GUI inversion 入口和 GUI echo 预览现统一调用 observation↔echo 契约校验；新 echo 还记录 observation 文件 SHA-256 与自身 `fast_sample_count`。实现、红绿证据和兼容边界见 `../changes/CHIRP_ROW_CONTRACT_2026-09-21.md`。

**现象**：`observation_info.npz` 的 `fast_sample_count` 与 `echo.npz` 里 `iq` 的行宽没有任何一处做交叉校验。用仓库里的两个真实产物混搭即可复现：

- `runs/chirp_point_target_test/`：observation `fast_sample_count = 252`，`iq.shape = (8, 252)`；
- `runs/chirp_test/`：observation `fast_sample_count = 251`（修复前产物），`iq.shape = (8, 251)`；
- 把前者的 `observation_info.npz` 与后者的 `echo/echo.npz` 一起交给 `echo.src.geometry.load_observation_info` 与 `inversion.src.dataset.load_echo`：**两个加载器都成功返回，无任何异常或警告**。

**为什么值得补**：`echo.npz` 的 `metadata` 里**没有** `fast_sample_count`（`echo/src/dataset.py::save_echo` 不写该键），所以这层校验只能放在读 `observation_info` 的消费者侧；而行宽 +1 恰恰是本次改动唯一会改变数据形状的副作用，`runs/` 下同时存在 251 与 252 两代产物，正是最容易踩的场景。目前只有文档（`OBSERVATION_RECEPTION_WINDOW.md` §6.3 代价 4）说明"不可按样点逐位比较，需重跑"，没有机器检查。

**建议**：在回波→反演、以及 GUI 预览的载入路径上，一旦同时拿到 observation 与 echo，就断言 `int(obs.metadata["fast_sample_count"]) == int(np.asarray(echo.iq).shape[1])`（chirp 布局），失败时给出"产物代次不一致，请重跑 observation/echo"的明确报错。

### L1 `DATE_LOG_2026-09-19.md` 的清理声明与工作区不符

`DATE_LOG_2026-09-19.md:177` 写"删除 … 4 个旧 `echo/tmp/cli_smoke_*`（`23188_CW`、`23712_CW`、`5qa5zg0j`、`z5nqk4as`）与 `echo/tmp/_dbg_echo.npz`"，但同一份文档 :207 又把 `cli_smoke_*` 列为"仍有残留、因目录写保护删除被拒"，两处自相矛盾。工作区现状：`echo/tmp/` 里 `cli_smoke_5qa5zg0j`、`cli_smoke_z5nqk4as` **仍然存在**（`23188_CW`、`23712_CW`、`_dbg_echo.npz` 已不在），与 :207 的说明一致、与 :177 不符。

**建议**：把 :177 的"删除 4 个"改为"删除 2 个；另 2 个与 `_dbg_echo.npz` 因写保护删除被拒"。这些都是 git 忽略的文件，不影响功能。

### L2 文件名与日期口径

复核方（用户）提到的是 `DATE_LOG_2026-09-21.md`，该文件不存在；09-21 发生的两轮外部复核与收尾记在 `DATE_LOG_2026-09-19.md`（mtime 09-21 09:26）里，其文首标题写的是"2026-09-19 记录"。内容本身完整（见 §5 的覆盖核对），只是**文件名日期与实际记录的工作日期不一致**，容易在引用时找不到。

**建议**：改名为 `DATE_LOG_2026-09-21.md` 并在文首保留"复盘期覆盖 09-18～09-21"的说明；或保持文件名、在文首加一行日期口径。

### L3 残留与字段记录

- `observation/tmp/` 有 7 项长期残留：`echo_verify/`、`echo_verify_horizons/`、`echo_verify.json`、`echo_verify_horizons.json`、`observation_info_example_clean_check.npz`、`observation_info_horizons_clean_check.npz`、`observation_info_review_check.npz`。两份 `DATE_LOG` 的"未处理项"只提了 `echo/tmp/` 与 `runs/__pycache__`，未提这里。均被 git 忽略，属卫生问题。
- `adc_window_duration_s` 这个观测输出字段只出现在 `../audits/CODE_AUDIT_REPORT.md` 与 `../changes/CW_LAYOUT_AND_CONFIG_GUARDRAILS.md`，`docs/4.2/` 的通用文档（含 `PROJECT_OVERVIEW.md` 的字段表）里没有它；同批的 `receive_centroid_span_s` 已经补进变更文档。

**建议**：清掉 `observation/tmp/` 的残留（或明确列为"保留的历史证据"）；在 `PROJECT_OVERVIEW.md` 的 `observation_info.npz` 字段表补 `adc_window_duration_s`。

---

## 3. §D2 的完整推导（便于独立复核）

符号沿用 `OBSERVATION_RECEPTION_WINDOW.md` §5：Run 内 $S_i$ 为常数时，$t_{\mathrm{rx},i}$ 等间隔，$W_i\equiv W$。

- 窗起点（两端同一 $t_{\mathrm{on}}$）：4.2 与 4.1 相同，$\delta$ 只比较**窗尾**。
- 4.2 窗尾：$q_{\mathrm{off}}=\max_i s_i+M$，$s_i=\mathrm{rint}\big((t_{\mathrm{rx},i}-t_{\mathrm{on}})f_s\big)-n_{\mathrm{pre}}$，$M=n_{\mathrm{pre}}+n_{\mathrm{after}}+1$，故
  $\text{stop}_{4.2}=t_{\mathrm{on}}+\big[\mathrm{rint}(a)+n_{\mathrm{after}}+1\big]/f_s$，其中 $a=(t_{\mathrm{rx,last}}-t_{\mathrm{on}})f_s$。
- 4.1 窗尾（按物理需求向上取整到采样格）：$\text{stop}_{4.1}=t_{\mathrm{on}}+\lceil a+b\rceil/f_s$，$b=T_{\mathrm{after}}f_s$。
- $n_{\mathrm{after}}=\lceil b+0.5\rceil$，于是 $\delta=(\text{stop}_{4.2}-\text{stop}_{4.1})f_s=\mathrm{rint}(a)+\lceil b+0.5\rceil+1-\lceil a+b\rceil$，与文档 §5 的式子一致。
- 代入 $a=m+f$、$b=n+g$ 得 $\delta=\rho+\lceil g+0.5\rceil+1-\lceil f+g\rceil$，$\rho\in\{0,1\}$，即 $\delta\in\{1,2\}$（见 §D2 的分情形证明）。

**两个量不要混用**：行宽增量 $\lceil b+0.5\rceil-\lceil b\rceil\in\{0,1\}$，触发条件 $\mathrm{frac}(b)=0$ 或 $>0.5$；$\delta$ 是窗尾推迟量，恒 $\ge1$。`DATE_LOG_2026-09-19.md` §3.5 的反例只算了前者。

---

## 4. 复现命令与环境

环境：Windows + conda 环境 `pytorch`（`E:\anaconda3\envs\pytorch\python.exe`），无网络。

```powershell
# 基线测试（本轮实测，见 §5）
python -m pytest -q tests                                        # 75 passed
python -m pytest -q observation/tests --ignore=observation/tests/test_ephemeris.py
                                                                 # 49 passed（被忽略的 9 条需 Horizons 网络）
cd echo; python -m pytest -q tests; cd ..                         # 36 passed（echo 必须以此为工作目录）
python -m pytest -q inversion/tests                               # 21 passed, 3 skipped
```

§D2 的 $\delta$：按 §3 的式子枚举 $f,g$，或对同一 $t_{\mathrm{on}}$ 比较带/不带补偿的 `rx_adc_stop_elapsed_s`。
§T1 的表：把 `observation/src/planning.py` 里 `after_s * fs_hz + 0.5` 的常量改成 $c$ 后，重跑 144 组网格与密扫（本次探针 `_probe_review_20260921.py` 为临时文件，已在整理本文前删除）。
§T2：`load_observation_info(runs/chirp_point_target_test/observation_info.npz)` 与 `load_echo(runs/chirp_test/echo/echo.npz)` 同时成功即复现。

---

## 5. 本轮已核对为正确的部分（不属于问题）

- **0.5 栅格补偿与后置保证**：密扫（$f_s=1000$、`prf`=20.5、`pre`=0、`post_guard·fs` 小数位 0.001 分辨率）最坏 $+0.0366$ 采样，与 `DATE_LOG` 记的 3888 组扫描最坏 $+0.1829$/576 组 $+0.0366$ 同向；零负值。
- **行宽触发条件**：`frac(after_s·fs) = 0 或 > 0.5` 时 +1；点目标夹具 252、mesh 夹具 153 与代码一致。
- **`echo.npz` 布局契约**：CW（1 维 `iq`）不写 12 个行轴键、chirp（2 维）要求全部存在且长度等于脉冲数；`present` 用 `set(data.files)` 判断，缺键报错不被兜底掩盖。
- **§D1/D3/D4/D5 之外的行为改动**：末列纳入窗内（`q_off = max(starts) + fast_count`）、`window_overlap`/`signal_echo_overlap` 判据、`adc_window_duration_s` 语义、预览按 `iq.ndim` 分流等，与变更文档描述一致。
- **两份 `DATE_LOG` 的覆盖核对**：09-18 那一轮我提出的问题（末列、`desired_rx_off` 文档公式、`positions_many` 硬失败、自动选时静默塌成 1 秒、δ 与 `window_overlap` 副作用、CW 测试作用域、`tests/` 的 git 忽略、失效示例配置、内存上限删除、`common_path_rate_m_s` 占位、δ 直方图不可复现、`tmp/audit` 失效脚本）逐条都有对应记录；09-19 那一轮（窗尾保证不成立、键数 10→12、三处未记录的行为收窄、受限 ACL 下契约测试跑不起来、四类测试作用域、未采纳项与暂缓项）同样逐条有记录。除 D5/L1/L2/L3 这几处口径与残留问题外，**没有发现关键遗漏**。
