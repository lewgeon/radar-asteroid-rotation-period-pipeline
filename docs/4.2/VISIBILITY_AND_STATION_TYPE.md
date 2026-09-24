# 可见性字段与测站坐标类型（4.2）

> 状态：**已实施**。设计背景仍保留在下文；当前代码行为以本节开头的规则为准，验收见 [vs_4.1/changes/RUNTIME_LOGIC_FIXES_2026-09-21.md](vs_4.1/changes/RUNTIME_LOGIC_FIXES_2026-09-21.md)。

当前规则：

- 自定义直角坐标（`static` / `linear`）不定义本地地平。两端都是这类测站时，配置不得携带 `visibility` 段；campaign 直接使用完整观测窗口，`visibility_applicable=false`，`visibility_computed=true`。
- 大地坐标测站才应用高度角约束。混合测站只约束有本地地平的一侧；笛卡尔一侧出现对应的 `min_*_elevation_deg` 会报错。
- GUI：直角坐标下隐藏可见性字段，保存时删除该段；切回大地坐标时补入默认可见性字段。预览里灰色斜纹只表示“本应计算但失败”（`visibility_computed=false`），不是直角坐标的默认画法。
- 几何计算失败仍降级为警告 + `visibility_computed=false`，预览不硬中断。这与早期“失败即抛错、不兜底”的草案不同，以代码为准。

## 1. 背景：两种测站坐标

观测配置的 `transmitter` / `receiver` 支持两类 `state`：

| `state` | 坐标字段 | 含义 |
|---|---|---|
| `static` / `linear` | `position_m` / `position0_m` + `velocity_m_s` | 用户自定义的三维直角坐标，可直接选任意原点与任意天体 |
| `astropy_geodetic` | `lat_deg` / `lon_deg` / `height_m` | 地球表面真实大地坐标，位置由 Astropy 通过 `EarthLocation.get_gcrs_posvel()` 给出 |
| `geodetic_fixed` | 同上 | 静态 ECEF，不能与真实 Horizons 惯性向量混用 |

"可见性"（`min_tx_elevation_deg` / `min_rx_elevation_deg`）的定义是本地地平高度角，需要"哪里是本地天顶"。因此它只有在测站位于一个真实天体表面时才有物理含义。

## 1.1 星历中心固定为地心

观测站中心确定为地心，因此星历链路只支持一种组合：

- Horizons 目标向量的查询中心固定为地心 `@399`，参考平面固定为地球赤道 `earth`；
- `astropy_geodetic` 测站由 Astropy 给出 GCRS 位置，与之同属一个地心参考系。

`ephemeris.location` 与 `ephemeris.refplane` **不是可配置字段**：配置校验会把它们当作未知字段拒绝（见 `observation/src/config_normalize.py` 的 `ephemeris: {"query_step_s"}` 白名单）。原先 `_validate_reference_frame_config` 里"必须是地心 / 必须是 earth"的两条校验因此永远不可达，已在 4.2 删除。若将来需要地心以外的观测中心，那是独立功能，需要一并改动测站坐标语义、高度角定义与光行时链路。

## 2. 当前行为

### 2.1 几何可见性对自定义直角坐标测站无法定义

`observation/src/visibility.py::geometric_visibility` 用测站位置向量作为本地天顶方向：

```
local_up = station_position / ||station_position||
```

测站位于坐标原点时 `||station_position|| = 0`，函数直接抛错：

```
位于坐标原点的测站无法定义本地地平坐标系
```

这不是缺陷本身——原点确实没有天顶方向。问题在于上层的处理方式。

### 2.2 异常被吞掉，随后走"全部可见"的兜底

`observation/src/campaign_planning.py::resolve_campaign_run_plan` 把几何可见性计算包在 `try/except ValueError` 中：

- 计算失败 → `elevation_deg` 全为 `NaN`、`visible` 全为 `False`、`windows = ()`，并追加一条警告"无法计算几何可见性：……"；
- 随后若 `visibility.allow_unobservable_for_simulation = true`，候选区间退回整段任务时间：
  `candidate_windows = (VisibilityWindow(0, campaign_duration_s),)`。

也就是说：**先报一条警告，然后按"整段时间都可见"继续解算**。用户看到的是警告，看不到的是"最小高度角约束被整体跳过了"这一后果。

### 2.3 由此连带失效的两项检查

1. **高度角阈值**：配置里写了 `min_tx_elevation_deg = 20`，但因 `visible` 全假且候选区间被兜底，这个阈值从未参与判断。
2. **单站可行性检查**：`resolve_campaign_run_plan` 中"一个 Run 最多能放几个脉冲"的检查需要几何量 `path_s`，而 `path_s` 只在"有可见性窗口"分支里计算。窗口为空时 `has_pulse_timing` 为假，检查被整体跳过，因此"Run 不可行"这类配置错误在这种几何下不会报出。

一个具体例子：默认开发夹具 `configs/chirp_point_target_test.json`

| 量 | 值 |
|---|---|
| 目标位置 | `(c, 0, 0) m`，单程 1 s，双程 2 s |
| 测站位置 | 原点（发射与接收相同） |
| 选时范围 | `start_utc` 到 `end_utc` 共 5 s |
| 平均高度角（几何可见性失败前的检查） | 测站位于原点 → 无法定义 |

5 s 的选时范围比 2 s 的双程时延还短，因此在这段范围内根本不存在"某个脉冲的回波已经收到"的时刻。程序仍然解出 1 个 Run、8 个脉冲并生成回波——它算的不是错的，但也不是任何真实雷达能做出来的观测。

## 3. 设计判断（已确认）

**可见性字段只在测站使用真实坐标时才有意义。** 具体地：

- 测站为 `astropy_geodetic`（地球表面真实坐标）+ 目标为真实星历（`horizons_vectors`）时，计算可见时间段才有意义，`min_*_elevation_deg`、`sample_step_s`、`allow_unobservable_for_simulation` 这些字段才应出现；
- 测站为自定义直角坐标（`static` / `linear`）时，"可见时间段"这个概念不成立，应默认整段时间可见，且不要求用户填写最小入射角等字段。

这条判断解释了当前配置为什么自相矛盾：既要求填高度角阈值，又给了算不出高度角的几何，于是只能靠"允许不可观测"兜底。

## 4. 已落地的改法

实施时相对本节早期草案收紧了一处、放宽了一处：两端都是自定义直角坐标时 **整个 `visibility` 段都被拒绝**（包括 `allow_unobservable_for_simulation` 和 `sample_step_s`）；真实坐标几何计算失败时预览仍降级为警告 + `visibility_computed=false`，不硬中断。

### 4.1 GUI

字段显隐由测站坐标类型决定：

| 测站类型 | "只保留可见时间段"选项 | 最小入射角、可见性采样步长 | "允许落在不可观测时段" |
|---|---|---|---|
| 真实大地坐标 | 显示，可选 | 选择包含可见时间段时显示 | 选择包含时显示 |
| 自定义直角坐标 | 不显示（等价于全部时间可见） | 不显示 | 不显示 |

要点：

- 保存/载入时必须把界面状态映射回既有配置字段：直角坐标下如果残留了可见性字段，应在规范化阶段丢弃（与当前"自动选时丢弃残留 `schedule.runs`"同一处理方式）；
- 切换测站类型时按 AGENTS.md 的动态字段规则处理焦点与滚动位置。

### 4.2 配置校验

`observation/src/config_normalize.py`：两端都是自定义直角坐标时，**整个 `visibility` 段都拒绝**（包括 `sample_step_s` 和 `allow_unobservable_for_simulation`）。混合测站只拒绝笛卡尔一侧的 `min_*_elevation_deg`。GUI `collect()` 会在直角坐标下删除该段，因此界面保存与 CLI 对旧文件的行为不同：前者静默去掉字段，后者报错。

### 4.3 观测解算

`campaign_planning.py` 的显式分支：

- 测站为自定义直角坐标 → 直接构造整段候选区间，不进入 `geometric_visibility`；`visibility_applicable=false`，`visibility_computed=true`（位置查询失败时仍可能是 false，但预览不把直角坐标画成灰色斜纹）。
- 测站为真实坐标但几何计算失败 → 警告 + `visibility_computed=false`，预览不硬中断。

单站可行性检查只依赖几何量，不以“存在可见性窗口”为前提。

## 5. 影响面与风险

- **已实施**：GUI 字段显隐、配置校验与 campaign 分支出发的可见性语义已经落地；旧夹具已改为不再给自定义直角坐标塞 `visibility`。
- **与早期草案的差异**：直角坐标下不再保留 `allow_unobservable_for_simulation`；几何失败仍可预览。
- **不影响回波生成**：可见性只决定"哪些时间段安排 Run"，不进入回波计算公式。当前默认夹具在整段候选时间上解出的 Run 与脉冲是自洽的。

## 6. 当前默认夹具的已知后果（与本节相关，另案记录）

当前默认开发夹具仍使用自定义直角坐标原点测站，因此：

- 配置中没有 `visibility` 段；campaign 使用完整观测窗口，`visibility_applicable=false`，`track_id` 落在该整段窗口上（为 0，不再是 -1）。
- 高度角字段不会出现，也不会生效。
- mesh 夹具的真值自转周期 `rotation_period_s = 7200 s` 落在反演搜索区间 `100–1000 s` 之外，无法用于验证反演。

这些属于“夹具参数尚未定稿”，等流水线整体跑通后再重新设计正式示例配置。
