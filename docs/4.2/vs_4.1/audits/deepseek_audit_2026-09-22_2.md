核查完毕。这份回执的**功能修复是真的、我已逐条复现**；但它的"误判"判定里有一条与字节证据不符，另有一处新的编码缺陷。

---

# 一、它的修复：逐条验证通过 ✅

| 回执声称 | 我的独立验证 |
|---|---|
| B5 新增 `observation/src/iers_policy.py` 关 IERS 自动下载 | 文件存在且实现正确（`auto_download=False`、`auto_max_age=None`）；在 `ephemeris.py`、`campaign_planning.py` 导入时调用，`observation/tests/conftest.py` 与 `tests/conftest.py` 各再设一次。**效果实测：observation 组从"卡死"变成 `69 passed in 1.12s`**（与回执数字一致），根组从"10 分钟不结束"变成 **14 秒跑完** |
| B1 CLI 复用判定顺序 | 用 09-18 留下的无 `stage_manifest.json` 旧 run 复现：**不带 `--allow-legacy-reuse` → 退出码 1**，报"观测信息缺少可核对的阶段指纹；GUI 需确认，CLI 需 --allow-legacy-reuse"；带旗标 → 退出码 0 并提示"按兼容开关复用"。**且跳过观测时不写 `observation.generated.json`**（历史证据未被覆盖）✅ |
| B12 chirp 缺 `bandwidth_hz` | 规范化实测：缺键 → 拒（"Chirp 回波需要 echo.waveform.bandwidth_hz"）；`bandwidth_hz=0` → 拒（"必须大于 0.0，收到 0.0"）；CW 无带宽 → 通过 ✅ |
| B3 空产物不算成功 | 0 字节 npz 实测：`reusable: False`，理由写明"观测产物为空或不存在" ✅ |
| B7 `manifest.json` 保留、只是日志写满 | 代码里仍在写；run 目录实际含 `manifest.json` + `stage_manifest.json` + 三份 generated，**无 `experiment.json`** ✅ |
| B8 WebEngine 占位已删 | 全仓搜索 `QT_WEBENGINE_AVAILABLE` / `QWebEngineView` → 0 命中 ✅ |
| B6 `.gitignore` 加 `.tmp_*/` | 已加 ✅ |
| 可见性字段拒绝范围 | 实测：双直角坐标下 `allow_unobservable_for_simulation`/`sample_step_s`/`min_tx_*`/`min_rx_*` **四个字段全部被拒并点名**；混合测站（TX=geodetic_fixed）**只拒没有地平那一侧的 `min_rx_elevation_deg`**，另一侧通过 ✅ |
| 夹具同步 | 三个夹具的 `observation.visibility` **已整块删除**，端到端仍跑通（`valid_sample_count = 2016`、`iq_shape = [8, 252]`）✅ |

**四组测试现状**（我用 pytorch 环境直跑，绕开它的 conda 入口）：

```
echo        44 passed            （回执称 44）✅
inversion   24 passed, 3 skipped （回执称 24+3）✅
observation 69 passed            （回执称 69）✅
root        50 passed, 68 failed ← 见下文，全是环境原因，非代码缺陷
```

**根组不再卡死**这一点我确认了：14.3 秒跑完（此前 >10 分钟）。

---

# 二、仍存在的问题

## 🟡 1. 它自己的回执文档有编码缺陷（唯一真正的编码问题）

我用**决定性判据**（把中文串按 `GBK 编码 → UTF-8 解码` 还原；真乱码能还原出正常中文，正常文本不能）扫了 67 个文件（`docs/4.2` 全部 + `scripts` + `tests` + `rotation_gui` + `pipeline.py`）：

```
存在编码异常的文件（1 个）：
  docs/4.2/vs_4.1/audits/DEEPSEEK_AUDIT_RESPONSE_2026-09-22.md
        乱码: 澶辫触  ->  还原: 失败
```

范围很小：该文 587 个中文串里只有 **2 处**，都是 `澶辫触`（=失败），落在 §3.1 引用我原文的那两处。其余正文正常。**建议把那两个串改回"失败"**——否则将来有人用工具过滤"失败"字样会漏掉这两处。

## 🟡 2. 它对我"源文件乱码"的判定，与字节证据不符

它把这条列为**误判**，并说"没有把断言改成 ASCII 子串"。但字节证据是：

| 证据 | 事实 |
|---|---|
| 我 09-21 的实测输出 | `Select-String` 直接打印文件内容，显示 `"瑙傛祴璁″垝涓?252 鍒楋紝鍥炴尝涓?251 鍒?"` 与 `"涓婃父浜х墿涓嶅吋瀹?` |
| `tests/test_artifact_contract.py` 大小/时间 | 09-21 是 **5617 字节**；现在是 **9862 字节**、mtime **09-22 10:39** |
| 现在的断言 | 全部是正确中文：`"观测计划为 252 列，回波为 251 列"`、`"上游产物不兼容"` ✅ |

也就是说：**当时确实写坏了，后来被重写修好了**——这与"从来没坏过"是两回事。`scripts/run_all_tests.py` 更微妙：mtime 仍是 09-21 14:36，但内容现在是正确的 `失败：`/`四组测试全部通过。`，说明它被就地重写而没有更新时间戳（编辑器常见行为）。

**结论**：现状是好的（我上轮报的问题已消失），但回执的归因不准；这也是为什么它没有为 `run_all_tests.py` 记录一次"编码修复"。

## 🟡 3. 统一入口仍强依赖 conda（它选择不改）

`_python_cmd()` 写死 `conda run -n pytorch --no-capture-output python`。它声明这是仓库约定，我同意不作为缺陷；但只要目标环境没有该 conda 环境，**这个"当日验收入口"就完全不可用**（我在本沙箱里它直接挂住）。哪怕只加一个 `--python` 覆盖开关（默认仍是 conda），也能让验收命令在任何环境复现。这是可选项，不是错误。

## 🟡 4. 根组 68 个失败：纯环境，但暴露一个可移植性权衡

68 个失败全部是同一个原因（日志里 136 次 `PermissionError` = 68×2）：

```
PermissionError: [WinError 5] 拒绝访问。: 'D:\...\tmp\empty_artifact_3180'
```

它把根测试的 scratch 从仓库根（`.tmp_*`，可写）搬到了 **`tmp/`**，而**本沙箱只读 `tmp/`、可写子模块的 `tmp/`**：

```
tmp              存在=True  不可写(PermissionError)   不可建目录(PermissionError)
echo/tmp         存在=True  可写                     可建目录
observation/tmp  存在=True  可写                     可建目录
inversion/tmp    存在=True  可写                     可建目录
```

在正常机器上这个修复是对的（`.tmp_*` 曾污染 `git status`、`tmp/` 已被忽略）。但在"工作区部分只读"的环境里，root scratch 换到 `tmp/` 反而从"能跑"变成"跑不了"。**建议**：`tests/scratch.py` 增加回退——先试 `tmp/`，不可写则退到仓库根 `.tmp_*/`（已在 `.gitignore` 里），这样两种沙箱都能跑。这不是代码缺陷，是测试基建的鲁棒性。

---

# 三、我上一轮两处结论的自我更正

1. **"根组卡在 28% = CLI 管道死锁"——归因错了，它说得对。** 实测卡住的用例是 GUI 的 `test_mixed_stations_show_only_horizon_side_visibility_fields`，而真正机制是 **astropy IERS 自动下载无超时**（同一 `.gui_state` 缓存状态导致卡点在相邻用例间漂移，这也解释了我为什么三次卡在不同位置）。我认出这是 IERS 却把根因归到了子进程管道——**我把"我自己踩过的死锁"当成了这里的原因**。
2. **它指出的"用旧 run 证明新代码仍写 `echo_overlap`"——成立。** 我看到的是仓库里 09-18 的旧产物；当前 `save_npz` 已不写该数组。

---

# 四、总体结论

**它这一轮的修复是正确的，我已全部复现通过**，且它对我上一轮漏报的 **IERS 阻塞**（真正的根因）判断准确——那一条比我报的管道死锁更贴近事实。

**还需要处理的只有三件小事**：

1. **修回执文档里那 2 处 `澶辫触`**（唯一真实的编码缺陷，1 分钟）；
2. **`tests/scratch.py` 加"`tmp/` 不可写则回退仓库根"**，让根组在受限环境也能跑（可选，提升可移植性）；
3. **在回执里更正 §3.1 的归因**——当时确有乱码文件，后来被重写修好（可顺带为 `run_all_tests.py` 补一条"编码修复"记录）。

其余它选择不改的项目（conda 入口、`.obj` 哈希、CW 残留 `radar_system`、`echo_overlap` 内存字段、单独跑反演脚本不做契约）我都同意其理由，属于**有记录的取舍**，不是遗漏。

需要我直接动手改第 1、2 条吗？第 2 条我建议顺带写一条小测试：把 `tmp/` 临时改成不可写不可行，但至少可以把回退逻辑写成"`tmp/` 建目录失败 → 用仓库根 `.tmp_*`"，并在正常环境下断言两个位置都能建。

**本轮我只做核查与探针，未修改任何代码或文档。** 新增探针在 `tmp/audit/`：`verify_b1_reuse_order.py`、`verify_b12_b3.py`、`verify_stage_gate2.py`、`check_tmp_writable.py`、`check_visibility_scope.py`、`check_encoding_roundtrip.py`（这个最有用，可直接复用做编码体检）。