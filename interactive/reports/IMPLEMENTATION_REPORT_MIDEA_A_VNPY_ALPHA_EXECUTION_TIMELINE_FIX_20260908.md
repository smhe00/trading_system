# IMPLEMENTATION_REPORT — Midea vnpy.alpha Challenger Execution Timeline Fix

对应任务书：`interactive/TASK_MIDEA_A_VNPY_ALPHA_EXECUTION_TIMELINE_FIX_20260908.md`
基于评审：`interactive/REVIEW_MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER_FIX_20260908.md`（verdict: CHANGES_REQUIRED，P0×2 + P1×2）
标的：美的集团 `000333.SZ`；日期：2026-09-08
性质：**研究/回测 only**

## 1. 修改文件列表

| 文件 | 变更 |
| --- | --- |
| `src/trader/strategies/midea_timing/ml_research.py` | `simulate_ml` 重写为**严格时间序挂单状态机**（A 开盘处理既有挂单 → B 收盘标记 → C 盘后决定目标态并管理挂单）；买入/卖出**对称限价**成交（buy: `low≤limit`→`min(open,limit)`；sell: `high≥limit`→`max(open,limit)`）；`BoundaryPurgeProcessor` 改**分段感知**标签包含（fit/valid 各自目标日上界） |
| `scripts/midea_vnpy_alpha_lightgbm_challenger.py` | `run_fold` 传 `fit_end/valid_end` 给 purge；逐折报告 `fit_range/valid_range/test_range/max_fit_label_target_date/max_valid_label_target_date` |
| `tests/strategies/test_midea_vnpy_alpha_challenger.py` | 新增 `MlTimelineTests`（10 项时间线/挂单/成交测试）+ 更新 purge 分段感知测试 |
| `interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_VNPY_ALPHA_EXECUTION_TIMELINE_FIX_20260908.md` | 本报告 |

锁定基线、QmtGateway、依赖声明零改动；**未安装/升级/降级任何包**。

## 2. 严格时间序执行状态机（P0 修复）

每根 bar `t` 严格按序：

```text
A. BAR OPEN / INTRABAR —— 只处理来自前一信号 bar 的挂单（仅此处变动 cash/pos）：
     BUY  : bar.low  <= buy_limit  → 按 min(bar.open, buy_limit) 成交；否则保持挂单
     SELL : bar.high >= sell_limit → 按 max(bar.open, sell_limit) 成交；否则保持挂单
B. BAR CLOSE —— 用 t 收盘时实际持有仓位标记权益 rows.append((t, cash + pos*close_t))
C. AFTER CLOSE —— 读 t 状态（LONG iff pred>0），创建/取消唯一挂单（最早 t+1 可成交）
```

**硬不变量**：任何 bar-t 权益不依赖 bar-t+1 的开/高/低/收。首根 bar 即使信号 LONG，其收盘权益仍 = 1,000,000（空仓），最早 t+1 成交。

## 3. 挂单 / no-fill / 取消语义（P0 修复）

- 任意时刻**至多一个挂单**；不重复堆叠。
- **目标态未达成前挂单保持**：LONG 信号且空仓 → 建买挂单（`signal_close×1.20` 定股数、`limit=signal_close×1.15`），不成交则持续挂起，直到成交或目标态改变。
- **目标态回退即取消**：买挂单未成交时状态回到 CASH → 取消（不成交）；卖挂单未成交时状态回到 LONG → 取消（保持持仓）。
- 卖出对称：`sell_limit = signal_close×0.85`，`bar.high ≥ sell_limit` 才成交、价 `max(open, sell_limit)`；不成交则持续挂起。
- 全部确定性、可测；与锁定 MA 的 vn.py bar-crossing 语义一致。

## 4. fit/valid 标签包含（P1 修复）

`BoundaryPurgeProcessor` 现为**分段感知**：

```text
FIT row   (t <= fit_end)   : 保留 iff  t+20 目标日 <= fit_end
VALID row (t >  fit_end)   : 保留 iff  t+20 目标日 <= valid_end
```

保证：**fit 标签不消费 valid 期价格**、**valid 标签不消费 OOS 期价格**（valid_end = 声明训练窗末日，严格早于 OOS）。同时剔除特征/标签 null/NaN 行。逐折证据（3Y，全部折 `overlap=False`）：

| OOS年 | fit | valid | fitRows | validRows | max FIT 目标日 | max VALID 目标日 |
| --- | --- | --- | ---: | ---: | --- | --- |
| 2018 | 15-01-01..16-12-31 | 17-01-01..17-12-31 | 455 | 224 | 2016-12-30 ≤ fit_end ✓ | 2017-12-29 ≤ valid_end ✓ |
| 2019 | 16-01-01..17-12-31 | 18-01-01..18-12-31 | 458 | 194 | 2017-12-29 ✓ | 2018-12-28 ✓ |
| 2020 | 17-01-01..18-12-31 | 19-01-01..19-12-31 | 438 | 213 | 2018-12-28 ✓ | 2019-12-31 ✓ |
| 2021 | 18-01-01..19-12-31 | 20-01-01..20-12-31 | 427 | 223 | 2019-12-31 ✓ | 2020-12-31 ✓ |
| 2022 | 19-01-01..20-12-31 | 21-01-01..21-12-31 | 456 | 223 | 2020-12-31 ✓ | 2021-12-31 ✓ |
| 2023 | 20-01-01..21-12-31 | 22-01-01..22-12-31 | 466 | 222 | 2021-12-31 ✓ | 2022-12-30 ✓ |
| 2024 | 21-01-01..22-12-31 | 23-01-01..23-12-31 | 465 | 222 | 2022-12-30 ✓ | 2023-12-29 ✓ |
| 2025 | 22-01-01..23-12-31 | 24-01-01..24-12-31 | 464 | 222 | 2023-12-29 ✓ | 2024-12-31 ✓ |
| 2026 | 23-01-01..24-12-31 | 25-01-01..25-12-31 | 464 | 223 | 2024-12-31 ✓ | 2025-12-31 ✓ |

## 5. 新增/更新测试（`MlTimelineTests` + purge）

- 信号日权益不被次日成交改变（首根 LONG bar 收盘 = 1,000,000）；
- 初始 LONG 最早 t+1 成交；成交前 pos=0、成交日起 pos 出现；
- 一根 no-fill 后越过限价 → 恰好一次最终成交；
- no-fill LONG 后状态回 CASH → 挂单取消、不成交；
- 不重复堆叠入场/出场挂单；
- 卖出信号不改变信号日权益/仓位；卖限价 no-fill 持续、越过才成交；成交日 = 实际成交 bar；
- 模型化成交下现金恒非负；
- purge 分段感知（fit 越界入 valid 剔除、valid 越界入 OOS 剔除、各段目标日上界）。

## 6. 重算的 OOS 绩效（主口径 MTM；每窗口 1,000,000 空仓起算；已全部重算）

| 窗口 | 比较器 | final | CAGR | 年化波动 | Sharpe | MaxDD | Calmar | e/x | 年化换手 | 已实现印花税 | 在场时长 | 均毛敞口 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL_3Y 18-26 | ML_ROLLING | 1,123,537 | 1.36% | 19.1% | 0.166 | 43.6% | 0.031 | 18/17 | 3.87 | 8,249 | 0.67 | 0.542 |
| | BH_100 | 1,879,272 | 7.60% | 26.1% | 0.411 | 55.7% | 0.137 | 1/0 | 0.12 | 0 | 1.00 | 1.000 |
| | BH_STATIC_CONS | 1,722,957 | 6.52% | 22.0% | 0.398 | 50.1% | 0.130 | 1/0 | 0.10 | 0 | 1.00 | 0.833 |
| | MA_FIXED | 1,387,149 | 3.87% | 15.3% | 0.325 | 31.4% | 0.123 | 30/29 | 6.77 | 14,382 | 0.50 | 0.420 |
| | 匹配敞口诊断 | 1,468,290 | 4.56% | 15.0% | 0.373 | 38.3% | 0.119 | 1/0 | 0.06 | 0 | 1.00 | 0.581 |
| RECENT_3Y 21-26 | ML_ROLLING | 715,427 | −5.67% | 14.5% | −0.325 | 41.6% | −0.136 | 16/15 | 3.31 | 4,927 | 0.51 | 0.400 |
| | BH_100 | 1,049,097 | 0.84% | 23.4% | 0.152 | 55.4% | 0.015 | 1/0 | 0.17 | 0 | 1.00 | 1.000 |
| | BH_STATIC_CONS | 1,039,278 | 0.67% | 17.5% | 0.126 | 45.0% | 0.015 | 1/0 | 0.14 | 0 | 1.00 | 0.833 |
| | MA_FIXED | 909,160 | −1.65% | 12.2% | −0.075 | 29.6% | −0.056 | 21/20 | 4.91 | 6,828 | 0.45 | 0.370 |
| | 匹配敞口诊断 | 1,017,413 | 0.30% | 7.8% | 0.083 | 23.1% | 0.013 | 1/0 | 0.07 | 0 | 1.00 | 0.331 |
| R4_3Y 24-26 | ML_ROLLING | 1,074,270 | 2.68% | 6.5% | 0.440 | 7.5% | 0.358 | 2/1 | 0.91 | 413 | 0.24 | 0.194 |
| | BH_100 | 1,639,362 | 20.06% | 18.1% | 1.102 | 13.4% | 1.494 | 1/0 | 0.37 | 0 | 1.00 | 1.000 |
| | BH_STATIC_CONS | 1,524,605 | 16.88% | 15.5% | 1.086 | 11.6% | 1.451 | 1/0 | 0.30 | 0 | 1.00 | 0.833 |
| | MA_FIXED | 1,182,956 | 6.41% | 12.0% | 0.576 | 19.2% | 0.334 | 12/11 | 7.87 | 5,131 | 0.63 | 0.511 |
| | 匹配敞口诊断 | 1,114,757 | 4.10% | 4.0% | 1.017 | 3.2% | 1.290 | 1/0 | 0.07 | 0 | 1.00 | 0.224 |
| ALL_5Y 20-26 | ML_ROLLING | 1,518,097 | 6.38% | 20.4% | 0.406 | 48.9% | 0.131 | 19/19 | 5.36 | 8,899 | 0.91 | 0.764 |
| | BH_100 | 1,724,002 | 8.41% | 24.4% | 0.453 | 55.3% | 0.152 | 1/0 | 0.15 | 0 | 1.00 | 1.000 |
| | BH_STATIC_CONS | 1,600,392 | 7.22% | 20.8% | 0.439 | 49.5% | 0.146 | 1/0 | 0.12 | 0 | 1.00 | 0.833 |
| | MA_FIXED | 1,209,101 | 2.85% | 14.4% | 0.268 | 31.2% | 0.091 | 22/21 | 5.82 | 9,612 | 0.49 | 0.411 |
| | 匹配敞口诊断 | 1,522,287 | 6.69% | 19.7% | 0.433 | 46.8% | 0.143 | 1/0 | 0.11 | 0 | 1.00 | 0.790 |
| RECENT_5Y 21-26 | ML_ROLLING | 1,061,762 | 1.05% | 18.5% | 0.148 | 45.2% | 0.023 | 19/19 | 4.40 | 6,040 | 0.89 | 0.715 |
| | MA_FIXED | 909,160 | −1.65% | 12.2% | −0.075 | 29.6% | −0.056 | 21/20 | 4.91 | 6,828 | 0.45 | 0.370 |
| | 匹配敞口诊断 | 1,057,512 | 0.99% | 15.4% | 0.112 | 38.5% | 0.026 | 1/0 | 0.12 | 0 | 1.00 | 0.645 |
| R4_5Y 24-26 | ML_ROLLING | 1,469,542 | 15.30% | 14.6% | 1.050 | 11.6% | 1.316 | 7/7 | 5.80 | 3,875 | 0.87 | 0.732 |
| | BH_100 | 1,639,362 | 20.06% | 18.1% | 1.102 | 13.4% | 1.494 | 1/0 | 0.37 | 0 | 1.00 | 1.000 |
| | BH_STATIC_CONS | 1,524,605 | 16.88% | 15.5% | 1.086 | 11.6% | 1.451 | 1/0 | 0.30 | 0 | 1.00 | 0.833 |
| | MA_FIXED | 1,182,956 | 6.41% | 12.0% | 0.576 | 19.2% | 0.334 | 12/11 | 7.87 | 5,131 | 0.63 | 0.511 |
| | 匹配敞口诊断 | 1,464,740 | 15.00% | 13.9% | 1.076 | 10.5% | 1.426 | 1/0 | 0.26 | 0 | 1.00 | 0.763 |

（"匹配敞口诊断" = `BH_STATIC_MATCHED_AVG_EXPOSURE`，ex-post、非可部署基准。）

### ML 相对 MA_FIXED 的 delta（主口径）

| 窗口 | ΔCAGR | ΔSharpe | ΔMaxDD | ΔCalmar |
| --- | --- | --- | --- | --- |
| ALL_3Y | −2.51pp | −0.159 | +12.2pp | −0.092 |
| RECENT_3Y | −4.02pp | −0.250 | +12.0pp | −0.081 |
| R4_3Y | −3.73pp | −0.136 | −11.7pp | +0.024 |
| ALL_5Y | +3.53pp | +0.138 | +17.6pp | +0.039 |
| RECENT_5Y | +2.70pp | +0.223 | +15.6pp | +0.079 |
| R4_5Y | +8.89pp | +0.474 | −7.6pp | +0.982 |

### ML 相对"等均毛敞口静态持有"诊断的 delta（结论 D 依据）

| 窗口 | ΔCAGR | ΔSharpe | ΔMaxDD | ΔCalmar |
| --- | --- | --- | --- | --- |
| ALL_3Y | −3.21pp | −0.207 | **+5.3pp** | −0.088 |
| RECENT_3Y | −6.01pp | −0.408 | **+18.5pp** | −0.151 |
| R4_3Y | −1.42pp | −0.577 | **+4.3pp** | −0.932 |
| ALL_5Y | −0.31pp | −0.027 | **+2.1pp** | −0.012 |
| RECENT_5Y | +0.48pp | +0.036 | **+6.7pp** | +0.008 |
| R4_5Y | +0.31pp | −0.026 | **+1.1pp** | −0.110 |

## 7. 重算的结论 A/B/C/D

### A. ML 是否在样本外战胜锁定 MA 基线？→ **否（NO）**

主评估窗口 ALL_3Y：ML 四项全面落后 MA_FIXED（CAGR −2.51pp、Sharpe −0.159、MaxDD +12.2pp、Calmar −0.092）；RECENT_3Y 亦落后。5Y 各窗口 ML 在 CAGR/Sharpe 反超但 MaxDD 显著更差（+15.6~17.6pp）；R4_5Y 四项反超（CAGR +8.89pp、Sharpe +0.474、MaxDD −7.6pp、Calmar +0.982）——按任务书"不得基于单一有利区段宣布胜利"，且该优势在敞口匹配后基本消失（ΔMaxDD +1.1pp）。**不宣布 ML 战胜锁定基线。**

### B. 滚动 3Y vs 5Y → **5Y_BETTER_RECENTLY**（描述性）

ALL_5Y 6.38% > ALL_3Y 1.36%；RECENT_5Y 1.05% > RECENT_3Y −5.67%；R4_5Y 15.30% > R4_3Y 2.68%。5Y 训练期更长（含 2018-2020），近期 OOS 更有利。

### C. ML 在 2024-2026 是否显示正向方向分离？→ **否（无可靠分离）**

2024-2026：pred3 corr −0.052、spread +0.24pp；pred5 corr +0.042、spread +0.88pp——相关性≈0、LONG/CASH 实现均值差≈0。冻结价格/波动特征 + y20 + 固定 LightGBM 无可靠正向方向信息（逐折 corr 亦无稳定符号）。

### D. 敞口匹配后是否仍有回撤改善？→ **否（全部 6 窗口更差）**

对"等均毛敞口静态持有"比较，ML 的 MaxDD 在 6 个窗口**全部更高**（+1.1~+18.5pp）。ML 在 R4 相对 MA 的"回撤更低"基本由更低平均敞口解释；敞口匹配后优势消失/反转。**ML 无稳健回撤优势。**

## 8. 测试与命令结果

```powershell
python -B -m unittest discover -s tests -t . -v
```
**`Ran 132 tests ... OK`**（基线 12 + QMT 加固 48 + 择时 27 + 历史研究 12 + challenger 33）。

```powershell
python -B scripts\midea_vnpy_alpha_lightgbm_challenger.py --csv work\midea_000333_daily_back.csv --json work\midea_vnpy_alpha_lightgbm_summary.json
python -B scripts\midea_vnpy_alpha_lightgbm_challenger.py --fetch --json work\midea_vnpy_alpha_lightgbm_summary.json
```
`--csv` 两次运行与 `--fetch` 输出 **MD5 完全一致**。

## 9. 环境健康披露（诊断性；未做任何包变更）

```powershell
python -m pip check
```
输出（与上轮一致，功能未受影响、全量测试通过）：
```text
vnpy-mysql 1.1.1 has requirement peewee>=3.17.9, but you have peewee 3.17.3.
vnpy-postgresql 1.1.2 has requirement peewee>=3.17.9, but you have peewee 3.17.3.
vnpy-sqlite 1.1.3 has requirement peewee>=3.17.9, but you have peewee 3.17.3.
```
依赖修复需另行授权任务；本任务未变更任何包。既有的用户授权安装（polars 1.44.1 / lightgbm 4.7.0 / alphalens-reloaded 0.4.6 / pyarrow 25.0.1）保持。

## 10. 限制（如实声明）

1. 前向 y20 样本重叠，诊断不做显著性宣称。
2. 冻结特征仅价格/波动技术面；结论不代表其他特征/模型配置。
3. 后复权价用于研究；绝对滑点/现金 sizing 为近似。
4. T+1 结构性兼容；未建模涨跌停无法成交。
5. 官方 `LgbModel` 强制 early-stopping，采用确定非重叠 fit/valid 且标签分段包含（逐折证据 §4）。
6. 挂单成交语义（限价穿越、no-fill 保持/取消）为对锁定基线 vn.py bar-crossing 的确定性复刻，测试固化。

## 11. 交易副作用声明

**零实盘副作用**：新增委托数 = 0，新增成交数 = 0，撤单数 = 0；未启用/修改 QmtGateway 写路径；未动 `D:\veighna_studio`、MiniQMT 配置；锁定基线零改动；未变更任何包。

## Definition of Done 核对

```text
[x] t equity never depends on t+1 execution data（时间序状态机 + 测试）
[x] initial LONG remains next-bar or later（首根 bar 收盘=1M 空仓，最早 t+1 成交）
[x] pending no-fill behavior is deterministic and does not suppress target state（单挂单保持/取消）
[x] buy/sell limit crossing is symmetric and tested（low≤buy_limit / high≥sell_limit）
[x] no duplicate pending orders（单挂单，测试覆盖）
[x] FIT labels do not consume VALID-period prices（分段感知 purge + maxFitTgt≤fit_end 逐折证据）
[x] VALID labels do not consume OOS-period prices（maxValidTgt≤valid_end 逐折证据）
[x] all existing tests plus new tests pass（132/132）
[x] challenger OOS metrics fully recomputed（全部窗口/比较器重算）
[x] no package mutation（pip check 仅诊断）
[x] locked baselines/QmtGateway unchanged（git 核验）
[x] zero live-trading side effects
```
