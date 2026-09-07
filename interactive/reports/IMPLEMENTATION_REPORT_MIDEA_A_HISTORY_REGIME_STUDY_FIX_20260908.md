# IMPLEMENTATION_REPORT — Midea Historical Regime Study Boundary/Report Fix

对应任务书：`interactive/TASK_MIDEA_A_HISTORY_REGIME_STUDY_FIX_20260908.md`
基于评审：`interactive/REVIEW_MIDEA_A_HISTORY_REGIME_STUDY_20260908.md`（verdict: CHANGES_REQUIRED）
标的：美的集团 `000333.SZ`；日期：2026-09-08
性质：**研究/回测 only**（锁定基线零改动）

## 1. 修改文件列表

| 文件 | 变更 |
| --- | --- |
| `src/trader/strategies/midea_timing/research.py` | 新增 `regime_contained_sample()` 区间包含判定纯函数 |
| `scripts/midea_history_regime_study.py` | `forward_diagnostic` 改为**区间包含**采样（t 与 t+h 均须落在同一区间）；`forward_diagnostic` 支持注入 regimes（便于测试）；特征漂移分位数改用 `statistics.quantiles(..., method="inclusive")` 统一口径 |
| `tests/strategies/test_midea_history_regime.py` | 新增 `ForwardContainmentTests`（6 项边界包含测试） |
| `interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_HISTORY_REGIME_STUDY_FIX_20260908.md` | 本报告（未覆盖旧报告） |

**未修改**（git diff 核验）：`scripts/midea_timing_backtest.py`、`src/trader/strategies/midea_timing/ma_regime.py`、`__init__.py`、`src/trader/gateways/qmt/**`。未动 QmtGateway、MiniQMT 配置、VeighNa Studio；未装/升依赖。

## 2. 边界包含实现（阻断项修复）

- 新增纯函数 `regime_contained_sample(dates, idx, horizon, start, end)`：当且仅当
  ```text
  state date t   ∈ [start, end]
  target date t+h ∈ [start, end]
  ```
  才把该样本归入该区间。
- `forward_diagnostic` 对每个 (区间, 水平) 调用它；因此：
  - 晚-OLD 的 t+20/t+60 落在 RECENT → **排除**；
  - R1→R2、R2→R3、R3→R4 的跨区间目标 → **排除**；
  - RECENT 尾部无 t+20/t+60 落在 RECENT 内 → **排除**。
- 状态计算仍只用 ≤t 收盘信息（无前视）；不截断/前向填充/回填/替换目标（`ForwardReturnTests` 保持）。
- 特征漂移 Q25/Q75 改用标准库 `statistics.quantiles(n=4, method="inclusive")`，五个特征统一口径。

## 3. 新增测试与结果

`ForwardContainmentTests`：
- R20 目标跨区间终点 → 排除；R60 同样 → 排除；
- t+h 恰为区间最后一个纳入交易日 → 接受；
- OLD 诊断绝不消费 RECENT 目标日（区间终点 2020-12-31，目标为 2021 即排除）；
- 状态计算不依赖 t 后数据（既有 `StateDiagnosticTests`）；
- 全局末尾 20/60 根仍排除（既有 `ForwardReturnTests`）；
- 端到端：注入两个不相交区间跑 `forward_diagnostic`，R1 样本目标绝不落入 R2。

```powershell
python -B -m unittest discover -s tests -t . -v
```
**`Ran 103 tests ... OK`**（基线 12 + QMT 加固 48 + 择时基线 27 + 研究 16），QMT/基线回归全通过。

## 4. 完整绩效/区间表（主口径 MTM；JSON 与 Markdown 同源）

每区间三比较器完整字段（`actual_start/end`、`start_equity`、`period_count/years`、`final_equity`、CAGR、vol、Sharpe、MaxDD、Calmar、e/x、年化换手、已实现印花税、`time_in_market`；BSC=BH_STATIC_CONSERVATIVE 另有 `initial_deployed_fraction`；MA 另有 `avg_deployed_while_long`/`overall_avg_gross_exposure`）。

### R1 20140401..20171229（900 期 / 3.75 年）

| 字段 | BH_100 | BH_STATIC_CONSERVATIVE | MA_FIXED |
| --- | ---: | ---: | ---: |
| start_equity | 1,000,000 | 1,000,000 | 1,000,000 |
| period_count / years | 900 / 3.75 | 900 / 3.75 | 900 / 3.75 |
| final_equity | 4,845,598 | 4,201,765 | 2,672,390 |
| CAGR | 52.32% | 46.64% | 29.97% |
| 年化波动 | 35.77% | 32.36% | 25.61% |
| Sharpe | 1.3556 | 1.3449 | 1.1513 |
| MaxDD | 39.63% | 36.50% | 33.04% |
| Calmar | 1.3201 | 1.2776 | 0.9070 |
| entries/exits | 1/0 | 1/0 | 13/12 |
| 年化换手 | 0.2657 | 0.2212 | 7.2639 |
| 已实现印花税 | 0 | 0 | 6,650 |
| time_in_market | 1.0 | 1.0 | 0.6922 |
| initial_deployed_fraction | — | 0.8295 | — |
| avg_deployed_while_long | — | — | 0.8623 |
| overall_avg_gross_exposure | — | — | 0.5969 |

### R2 20180102..20201231（690 期 / 2.875 年）

| 字段 | BH_100 | BH_STATIC_CONSERVATIVE | MA_FIXED |
| --- | ---: | ---: | ---: |
| start_equity | 1,000,000 | 1,000,000 | 1,000,000 |
| period_count / years | 690 / 2.875 | 690 / 2.875 | 690 / 2.875 |
| final_equity | 1,782,554 | 1,643,433 | 1,559,090 |
| CAGR | 22.27% | 18.86% | 16.70% |
| 年化波动 | 30.58% | 25.06% | 19.61% |
| Sharpe | 0.8103 | 0.8147 | **0.8856** |
| MaxDD | 37.91% | 31.68% | **14.83%** |
| Calmar | 0.5875 | 0.5953 | **1.1263** |
| entries/exits | 1/0 | 1/0 | 10/9 |
| 年化换手 | 0.3472 | 0.2855 | 5.4954 |
| 已实现印花税 | 0 | 0 | 3,745 |
| time_in_market | 1.0 | 1.0 | 0.5986 |
| initial_deployed_fraction | — | 0.8207 | — |
| avg_deployed_while_long | — | — | 0.8423 |
| overall_avg_gross_exposure | — | — | 0.5042 |

### R3 20210104..20231229（727 期 / 3.0292 年）

| 字段 | BH_100 | BH_STATIC_CONSERVATIVE | MA_FIXED |
| --- | ---: | ---: | ---: |
| start_equity | 1,000,000 | 1,000,000 | 1,000,000 |
| period_count / years | 727 / 3.0292 | 727 / 3.0292 | 727 / 3.0292 |
| final_equity | 639,034 | 711,228 | 764,567 |
| CAGR | −13.74% | −10.64% | −8.48% |
| 年化波动 | 27.16% | 20.10% | 12.21% |
| Sharpe | −0.4086 | −0.4592 | −0.6645 |
| MaxDD | 55.41% | 44.96% | 29.64% |
| Calmar | −0.2480 | −0.2366 | −0.2861 |
| entries/exits | 1/0 | 1/0 | 9/9 |
| 年化换手 | 0.3281 | 0.2625 | 3.9004 |
| 已实现印花税 | 0 | 0 | 2,896 |
| time_in_market | 1.0 | 1.0 | 0.2985 |
| initial_deployed_fraction | — | 0.7950 | — |
| avg_deployed_while_long | — | — | 0.8121 |
| overall_avg_gross_exposure | — | — | 0.2424 |

### R4 20240102..20260904（649 期 / 2.7042 年）

| 字段 | BH_100 | BH_STATIC_CONSERVATIVE | MA_FIXED |
| --- | ---: | ---: | ---: |
| start_equity | 1,000,000 | 1,000,000 | 1,000,000 |
| period_count / years | 649 / 2.7042 | 649 / 2.7042 | 649 / 2.7042 |
| final_equity | 1,639,362 | 1,524,605 | 1,182,956 |
| CAGR | 20.06% | 16.88% | 6.41% |
| 年化波动 | 18.07% | 15.47% | 12.04% |
| Sharpe | 1.1022 | 1.0859 | 0.5763 |
| MaxDD | 13.42% | 11.63% | **19.20%** |
| Calmar | 1.4941 | 1.4513 | 0.3338 |
| entries/exits | 1/0 | 1/0 | 12/11 |
| 年化换手 | 0.3652 | 0.2997 | 7.8749 |
| 已实现印花税 | 0 | 0 | 5,131 |
| time_in_market | 1.0 | 1.0 | 0.6271 |
| initial_deployed_fraction | — | 0.8104 | — |
| avg_deployed_while_long | — | — | 0.8143 |
| overall_avg_gross_exposure | — | — | 0.5107 |

### OLD 20140401..20201231（1590 期 / 6.625 年）与 RECENT 20210104..20260904（1376 期 / 5.7333 年）

| 区间/比较器 | final | CAGR | 年化波动 | Sharpe | MaxDD | Calmar | e/x | 年化换手 | 已实现印花税 | time_in_market | (BSC dep / MA dl / MA gross) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OLD BH_100 | 8,750,168 | 38.74% | 33.63% | 1.1418 | 39.63% | 0.9774 | 1/0 | 0.1504 | 0 | 1.0 | — |
| OLD BSC | 7,452,629 | 35.42% | 31.10% | 1.1305 | 36.58% | 0.9683 | 1/0 | 0.1252 | 0 | 1.0 | dep=0.8295 |
| OLD MA_FIXED | 4,235,786 | 24.35% | 23.28% | 1.0523 | 33.04% | 0.7368 | 22/21 | 10.3001 | 16,935 | 0.6522 | dl=0.8572 / gross=0.5590 |
| RECENT BH_100 | 1,049,097 | 0.84% | 23.35% | 0.1524 | 55.41% | 0.0152 | 1/0 | 0.1733 | 0 | 1.0 | — |
| RECENT BSC | 1,039,278 | 0.67% | 17.47% | 0.1258 | 44.96% | 0.0150 | 1/0 | 0.1387 | 0 | 1.0 | dep=0.7950 |
| RECENT MA_FIXED | 909,160 | −1.65% | 12.17% | −0.0755 | 29.64% | −0.0556 | 21/20 | 4.9090 | 6,828 | 0.4535 | dl=0.8163 / gross=0.3702 |

### Delta（MA_FIXED − 比较器，主口径）

| 区间 | ΔCAGR vs BH100 | ΔSharpe vs BH100 | ΔMaxDD vs BH100 | ΔCAGR vs BSC | ΔSharpe vs BSC | ΔMaxDD vs BSC |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | −22.35pp | −0.2043 | −6.59pp | −16.67pp | −0.1936 | −3.46pp |
| R2 | −5.57pp | +0.0753 | −23.08pp | −2.16pp | +0.0709 | −16.85pp |
| R3 | +5.26pp | −0.2559 | −25.77pp | +2.16pp | −0.2053 | −15.32pp |
| R4 | −13.65pp | −0.5259 | **+5.78pp** | −10.47pp | −0.5096 | **+7.57pp** |
| OLD | −14.39pp | −0.0895 | −6.59pp | −11.07pp | −0.0782 | −3.54pp |
| RECENT | −2.49pp | −0.2279 | −25.77pp | −2.32pp | −0.2013 | −15.32pp |

## 5. 重算后的前向 R20/R60 表（区间包含后；含 LONG/CASH 样本数；描述性，重叠样本不宣称显著性）

| 区间 | R20 LONG (n/mean/med/Ppos) | R20 CASH | R20 spread(mean/med) | R60 LONG | R60 CASH | R60 spread(mean/med) |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | 604 / 4.09% / 3.62% / .67 | 276 / 3.48% / 4.56% / .71 | +0.61 / −0.94pp | 564 / 12.17% / 13.97% / .79 | 276 / 13.11% / 10.22% / .79 | −0.94 / +3.75pp |
| R2 | 394 / 2.49% / 2.90% / .64 | 276 / 0.39% / −0.65% / .47 | **+2.10 / +3.55pp** | 354 / 5.17% / 5.83% / .66 | 276 / 5.19% / 5.13% / .58 | −0.02 / +0.70pp |
| R3 | 217 / −2.87% / −1.71% / .32 | 490 / −0.46% / −0.93% / .43 | **−2.41 / −0.78pp** | 217 / −6.36% / −3.87% / .32 | 450 / −1.64% / −1.71% / .41 | **−4.72 / −2.16pp** |
| R4 | 388 / 0.85% / −0.05% / .49 | 241 / 2.76% / 2.76% / .69 | **−1.91 / −2.81pp** | 357 / 2.36% / 1.51% / .62 | 232 / 6.58% / 6.04% / .93 | **−4.22 / −4.53pp** |
| OLD | 1018 / 3.58% / 3.47% / .67 | 552 / 1.93% / 2.47% / .59 | **+1.65 / +1.00pp** | 978 / 9.56% / 10.76% / .75 | 552 / 9.15% / 7.82% / .68 | +0.41 / +2.94pp |
| RECENT | 605 / −0.49% / −0.61% / .43 | 751 / 0.77% / 0.56% / .53 | **−1.26 / −1.17pp** | 574 / −0.94% / 0.14% / .51 | 742 / 2.03% / 2.70% / .61 | **−2.97 / −2.56pp** |

**修正说明**：censoring 后 R1 R60 LONG 564（原 624）、OLD R60 LONG 978（原 1038）等样本被剔除（目标跨入下一区间/近年）。方向性结论**不变**：R2/OLD 中 LONG 前向收益为正（R20 spread +2.10 / +1.65pp），R3/R4/RECENT 中为负（R60 spread −4.72 / −4.22 / −2.97pp）；R60 旧期 spread 较此前弱化但仍非负，RECENT 明确为负。

## 6. 特征漂移表（median / Q25 / Q75，全部五特征，统一 inclusive 分位数）

| 特征 | R1 | R2 | R3 | R4 |
| --- | --- | --- | --- | --- |
| 20D 收益 | 0.0435 [−0.0136, 0.0987] | 0.0197 [−0.0416, 0.0718] | −0.0118 [−0.0456, 0.0295] | 0.0092 [−0.0174, 0.0494] |
| 60D 收益 | 0.1255 [0.0124, 0.2215] | 0.0608 [−0.0514, 0.1591] | −0.0187 [−0.0914, 0.0451] | 0.0382 [0.0011, 0.0803] |
| 20D 已实现波动 | 0.2847 [0.2260, 0.3911] | 0.2858 [0.2181, 0.3604] | 0.2480 [0.1906, 0.3032] | 0.1507 [0.1221, 0.1872] |
| close/MA120−1 | 0.1013 [0.0372, 0.1905] | 0.0603 [−0.0372, 0.1406] | −0.0262 [−0.0822, 0.0348] | 0.0329 [0.0108, 0.0701] |
| MA20/MA60−1 | 0.0403 [0.0038, 0.0719] | 0.0169 [−0.0229, 0.0585] | −0.0092 [−0.0334, 0.0208] | 0.0110 [−0.0037, 0.0326] |

## 7. 重新评估的三部分结论（基于 censoring 后数值）

### A. 固定 MA 规则跨区间稳定性 → **REGIME_DEPENDENT**

- 仅 R2 相对两比较器都提供风险调整价值（Sharpe 0.8856 > 0.8103/0.8147；Calmar 1.1263 vs 0.5875/0.5953；MaxDD 14.83% vs 37.91%/31.68%）。
- R1/R3 中性偏负（降回撤但 Sharpe/CAGR 落后）；**R4 明确更差**（CAGR 6.41% vs BH100 20.06%，Sharpe 0.5763 vs 1.1022，MaxDD 19.20% 反高于 BH100 13.42%）。
- 故标签维持 **REGIME_DEPENDENT**。

### B. 回撤降低在敞口匹配后是否保留 → **部分保留，但不稳健**

- 对静态 ~83% 敞口（BSC）比较器，MA_FIXED 的 MaxDD 在 R2（−16.85pp）、R3（−15.32pp）、RECENT 聚合（−15.32pp）更低；
- 但 **R4 反转（+7.57pp）**：最近区间 MA 回撤高于等敞口静态持有。全历史回撤优势部分来自 ~83% 保守敞口（MA 毛敞口仅 24–60%），敞口匹配后优势缩水并在 R4 消失/反转。

### C. 旧数据对 ML 阶段的处理建议（临时） → **ROLLING_3Y_TO_5Y_PRIMARY_WITH_OLD_HISTORY_FOR_ROBUSTNESS**

- censoring 后信号方向性证据仍成立：OLD 中 LONG 前向 R20 优于 CASH（+1.65pp mean / +1.00pp med），RECENT 中反为负（−1.26pp / −1.17pp；R60 −2.97pp / −2.56pp）——固定规则的中期信息在旧期为正、近期为负（方向翻转）。
- 特征分布显著迁移（20D 波动 R4 较 R1/R2 近半；收益/MA 状态中位数符号随年代变化）。
- 若全历史等权训练，会把旧时代有效、近期失效的信号行为等权注入。建议以滚动 3–5 年为主训练窗口、旧历史仅作稳健性/区间多样性检查。**临时研究建议，不证明最优训练窗口；禁止据此调参。**

## 8. 可复现性

```powershell
python -B scripts\midea_history_regime_study.py --csv work\midea_000333_daily_back.csv --json work\midea_history_regime_summary.json
python -B scripts\midea_history_regime_study.py --fetch --json work\midea_history_regime_summary.json
```
`--csv` 与 `--fetch` 输出 **MD5 完全一致**（字节级可复现）。已用 `git diff` 核验锁定基线与 QMT gateway 文件零改动。

## 9. 剩余限制（如实声明）

1. 前向 R20/R60 样本重叠，仅作方向性描述，不宣称独立样本显著性。
2. 后复权价格用于研究；绝对滑点/现金 sizing 为近似，非券商执行价。
3. T+1 为结构性兼容；未建模涨跌停无法成交。
4. 区间边界为固定日历区间（未按结果移动）。
5. 单一标的/单一区间集；结论为美的专用、临时性。

## 10. 交易副作用声明

**零实盘副作用**：新增委托数 = 0，新增成交数 = 0，撤单数 = 0；未启用/修改 QmtGateway 写路径；未动 `D:\veighna_studio`、MiniQMT 配置；未安装/升级依赖；锁定基线文件零改动。

## Definition of Done 核对

```text
[x] no forward target crosses the evaluated regime boundary
[x] OLD forward diagnostic contains no RECENT target price
[x] R20/R60 boundary tests pass (ForwardContainmentTests, 6 项)
[x] all mandatory performance fields are present in Markdown (每区间三比较器全字段)
[x] R20/R60 counts are present for LONG and CASH
[x] all five drift features include median/Q25/Q75
[x] conclusions are recomputed after censoring (方向结论不变，R60 弱化已如实报告)
[x] locked baseline remains unchanged (git diff 核验)
[x] all tests pass (103/103)
[x] --fetch and --csv agree (MD5 一致)
[x] no live trading side effects
```
