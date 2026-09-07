# IMPLEMENTATION_REPORT — Midea Timing Baseline Metric Alignment Fix

对应任务书：`interactive/TASK_MIDEA_A_TIMING_METRIC_ALIGNMENT_FIX_20260907.md`
基于评审：`interactive/REVIEW_MIDEA_A_TIMING_TERMINAL_VALUATION_FIX_20260907.md`（verdict: CHANGES_REQUIRED）
标的：美的集团 `000333.SZ`；分析窗口 **2014-04-01 → 2026-09-04**；初始资金 1,000,000
日期：2026-09-07
性质：**研究/回测 only**

## 1. 修改文件列表

| 文件 | 变更 |
| --- | --- |
| `src/trader/strategies/midea_timing/ma_regime.py` | 新增共享纯函数 `build_anchored_series()`（统一锚点+收盘权益序列形状） |
| `src/trader/strategies/midea_timing/__init__.py` | 导出 `build_anchored_series` |
| `scripts/midea_timing_backtest.py` | B&H 与 MA 均用锚点序列；`metrics_from_equity` 改 `period_count = len-1`、`years = period_count/240`；主口径活动指标纯化（B&H entries=1/exits=0、仅入场换手、已实现印花税=0）；清算活动指标单列（`liquidated_exits`/`liquidated_total_turnover`/`liquidated_annualized_turnover`） |
| `tests/strategies/test_midea_ma_regime.py` | 新增 `MetricAlignmentTests`（锚点形状、MA 首日 0% 收益、B&H/MA 同期数同年数、B&H 主口径活动纯净） |
| `interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_TIMING_METRIC_ALIGNMENT_FIX_20260907.md` | 本报告（未覆盖旧报告） |

未修改 QmtGateway、MiniQMT 配置、VeighNa Studio、信号规则、gap buffer、数据源/复权、成本假设；未安装/升级依赖。

## 2. 最终公共起点锚约定

两策略计分权益序列统一为同一形状（共享 `build_anchored_series`）：

```text
point 0: 分析起点开盘锚点 = 1,000,000（锚点时间戳严格早于首根收盘点，索引无歧义）
point 1..N: 每个分析交易日一根收盘标记权益
```

- B&H：首期 open→close 收益（锚点→首收盘）作为真实收益观测进入统计，不再被静默省略。
- MA：next-bar 执行使其分析首日天然空仓（首收盘=1,000,000），锚点→首收盘产生**显式 0% 首期收益**（已由测试验证）。
- 无起点前交易、无前视（保持既有门控）。

## 3. 最终时长/期间约定

- `period_count = len(equity_series) - 1`（即锚点之后的收盘点数 = 分析窗口交易日数）。
- `years = period_count / ANNUAL_DAYS(240)`。
- 同一分析窗口下 B&H 与 MA 的 `period_count` 与 `years` **逐值相等**（实测均为 2966 / 12.3583），不再各自用 `len(series)/240` 产生偏差。

## 4. 主口径 vs 清算口径的活动/换手语义

**主口径 = 末收盘盯市（MTM）**：

| 指标 | Buy & Hold | MA Regime |
| --- | --- | --- |
| entries | 1 | 42（实际 vn.py 成交） |
| exits | **0**（持仓仍开） | 41（实际） |
| 换手 | 仅入场名义 996,268（0.0806/yr） | 实际成交 184.3M（14.92/yr） |
| 已实现印花税 | **0**（无已实现卖出） | 46,012（实际卖单） |

**可选清算口径（共享 `terminal_liquidation` + 同约定活动字段）**：

| 指标 | Buy & Hold | MA Regime |
| --- | --- | --- |
| liquidated_exits | 1 | 42（41 实际 + 1 期末持仓） |
| liquidated_total_turnover | 10,218,220 | 187,473,111 |
| liquidated_annualized_turnover | 0.8268 | 15.1698 |
| terminal_sell_commission / slippage / stamp | 2,767 / 221 / 4,611 | 939 / 75 / 1,565 |

不向 vn.py 成交历史注入伪造平仓交易；MA 期末持仓（7,500 股）仅以清算字段体现。

## 5. 测试命令与结果

```powershell
python -B -m unittest discover -s tests -t . -v
```
**`Ran 87 tests ... OK`**（基线 12 + QmtGateway 加固 48 + 择时 27）。新增 `MetricAlignmentTests`：锚点序列形状（锚点值=1M、索引无歧义、首期收益=0.05 示例）、MA 首日显式 0% 收益、B&H/MA 同期数同年数、B&H 主口径活动纯净（exits=0、已实现印花税=0、仅入场换手）。

```powershell
python -B scripts\midea_timing_backtest.py --fetch --json work\midea_timing_summary.json
python -B scripts\midea_timing_backtest.py --csv work\midea_000333_daily_back.csv --json work\midea_timing_summary.json
```
两者结果一致（`--fetch` 已实测，退出码 0）。

## 6. 重算对比表（主口径 = 末收盘盯市；清算口径单列）

### Primary MTM

| 指标 | Buy & Hold | MA Regime（conservative-capital） | Delta |
| --- | --- | --- | --- |
| start_equity | 1,000,000 | 1,000,000 | — |
| period_count / years | 2966 / 12.3583 | 2966 / 12.3583 | — |
| primary_final_equity | 9,225,164 | 3,767,495 | — |
| CAGR | 19.70% | 11.33% | **−8.37pp** |
| 年化波动率 | 29.39% | 19.11% | −10.28pp |
| Sharpe | 0.7585 | 0.6570 | **−0.1015** |
| MaxDD | 55.69% | 33.04% | **−22.65pp** |
| Calmar | 0.3537 | 0.3429 | −0.0108 |
| 实际 entries/exits | 1 / 0 | 42 / 41 | — |
| 实际年化换手 | 0.0806 | 14.9166 | — |
| 已实现印花税 | 0 | 46,012 | — |

### Optional liquidation

| 指标 | Buy & Hold | MA Regime |
| --- | --- | --- |
| liquidated_final_equity | 9,217,566 | 3,764,916 |
| liquidated_CAGR | 19.69% | 11.32% |
| liquidated_exits | 1 | 42 |
| liquidated 年化换手 | 0.8268 | 15.1698 |
| terminal_sell_commission / slippage / stamp | 2,767 / 221 / 4,611 | 939 / 75 / 1,565 |
| 期末持仓（股） | 22,100 | 7,500 |

**Delta（主口径）**：Sharpe −0.1015；MaxDD −22.65pp；CAGR −8.37pp（清算口径 CAGR delta −8.37pp）。结论不变：MA 显著降回撤/降波动，收益与 Sharpe 落后于买入持有，**不宣称择时更优**。

## 7. 剩余限制（如实声明）

1. 复权价用于信号/总回报研究；固定 0.01/股滑点与绝对现金/整手 sizing 为研究近似，非券商实盘执行价。
2. T+1 为结构性兼容（日线 next-bar 序列），未建模显式可卖持仓约束；未建模涨跌停无法成交。
3. 印花税分「已实现（实际卖单）」与「终端清算（期末持仓）」两组，口径全程一致并单列。
4. gap_buffer=1.20 使典型投入约 83%（`deployed_fraction_approx=0.8333`），非严格 100%（conservative-capital MA regime）。
5. 单一标的/单一区间；`work/` 下数据 gitignored，`--fetch` 可复现。

## 8. 交易副作用声明

**零实盘副作用**：新增委托数 = 0，新增成交数 = 0，撤单数 = 0；未启用/修改 QmtGateway 写路径（`send_order`/`cancel_order` 仍 `NotImplementedError`）；未动 `D:\veighna_studio`、MiniQMT 配置、未安装/升级依赖。

## Definition of Done 核对（指标对齐任务书）

```text
[x] same explicit start-open equity anchor for B&H and MA (1,000,000, both series)
[x] same scored return-period count for B&H and MA (2966 == 2966)
[x] same duration/CAGR basis for B&H and MA (years 12.3583 == 12.3583)
[x] primary MTM activity metrics do not contain artificial terminal exits (B&H exits=0)
[x] optional liquidation metrics remain symmetric (shared helper, both strategies)
[x] previous safety/cost/no-lookahead fixes remain intact
[x] all tests pass (87/87)
[x] baseline is recomputed (--fetch == --csv)
[x] no live trading side effects
```
