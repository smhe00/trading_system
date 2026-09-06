# IMPLEMENTATION_REPORT — Midea Timing Baseline Fix

对应任务书：`interactive/TASK_MIDEA_A_TIMING_BASELINE_FIX_20260906.md`
基于评审：`interactive/REVIEW_MIDEA_A_TIMING_BASELINE_20260906.md`（verdict: CHANGES_REQUIRED）
标的：美的集团 `000333.SZ`；分析窗口 **2014-04-01 → 2026-09-04**（12.36 年）
日期：2026-09-07
性质：**研究/回测 only**

## 1. 修改文件列表

| 文件 | 变更 |
| --- | --- |
| `src/trader/strategies/midea_timing/ma_regime.py` | 新增 `analysis_start` 门控（预热可交易前禁止下单）；保守 sizing（`gap_buffer` 预留跳空 + 买入佣金/滑点，杜绝负现金）；新增 `commission_rate`/`slippage_per_share`/`gap_buffer` 参数 |
| `scripts/midea_timing_backtest.py` | 统一指标基准（显式 `start_equity`）；策略传入 `analysis_start` 与成本参数；B&H 日线含闲置现金；`metrics_from_equity(balance, start_equity)` |
| `tests/strategies/test_midea_ma_regime.py` | 新增执行驱动（挂单在次根 bar 开盘成交）；新增预热门控、起点权益、gap-up 无负现金、真实引擎 next-bar 成交测试 |
| `interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_TIMING_BASELINE_FIX_20260906.md` | 本报告（未覆盖旧报告） |

未修改 QmtGateway、MiniQMT 配置、VeighNa Studio；未安装/升级依赖。

## 2. 修复说明（逐项对应评审）

### 1) 公共分析起点（阻断）
- 策略新增 `analysis_start` 门控：`analysis_start` 之前的 bar 只用于预热 MA20/60/120，**不提交、不成交任何订单**。
- 脚本在切片后校验 `balance[analysis_start] == CAPITAL(1,000,000)`，不相等则抛错。
- 测试：`test_prestart_bars_warm_indicators_but_cannot_trade`（预热但不交易）、`test_no_prestart_trade_and_fill_on_next_bar_after_start`（起点前无成交、首个合格信号次根成交）、`test_starting_equity_is_exactly_common_capital`（起点权益=1M）。

### 2) 指标口径一致（阻断）
- `metrics_from_equity(balance, start_equity)` 以**显式公共起点权益**计算 CAGR；两个基线 `start_equity` 均为 1,000,000（输出字段可见）。
- 移除旧的"用首切片余额 vs 固定 CAPITAL"混用；CAGR/Sharpe/MaxDD/Calmar/期末权益均指向同一分析窗口。

### 3) 杜绝合成杠杆/负现金（阻断）
- 入场量按保守价 `close × gap_buffer(1.20)` + 买入佣金 + 每股滑点预留后取整：`shares × (max_price×(1+rate) + slip) ≤ cash`。
- 即使次根 bar 跳空高开（测试用 +10%），现金不为负、仓位 ≤ 可用资金。
- 测试：`test_gap_up_fill_keeps_cash_non_negative`（跳空成交后 cash≥0，pos 不空头）。
- 说明：保守预留使实际投入比例略低于 100%（约 83%，视价格/跳空缓冲），这是"保证不超支"与"100% 满仓"之间的刻意权衡，报告如实披露。

### 4) B&H 日线含闲置现金
- `daily_equity = remaining_cash + shares × close`（买入后剩余现金计入逐日曲线），而非仅持仓市值。

### 5) T+1 表述限定
- 改为："该日线二进制策略在当前 next-bar 执行序列下**与 A 股 T+1 结构性兼容**"；未声称已完整建模券商 T+1 可卖持仓约束（无显式可卖约束实现）。

### 6) 复权价格执行假设分离
- 后复权价格仅用于**信号与总回报研究**；固定 `0.01/股` 滑点与绝对现金/整手 sizing 是**研究近似**，不视为券商实盘执行价。未新增第二条裸价数据管线（任务书允许）。

### 非阻断项处理
- 印花税：仍单列披露（`stamp_duty` / `final_equity_net` / `cagr_net`），未并入逐日 MA 权益曲线（vn.py 引擎不支持单边税），报告明示其影响（MA CAGR ≈ −0.12pp）。
- 宽限价（×1.15 / ×0.85）仅用于回测证明 next-bar 成交，不属生产执行模型（保留在 research 代码内）。

## 3. 新增测试

- `WarmupAndStartGateTests`：历史不足无信号；预 start bar 预热指标但不交易。
- `GapUpCashTests`：次根 bar +10% 跳空成交后现金非负、无空头。
- `NextBarExecutionTests`：起点前无成交；首个合格信号次根 bar 成交；起点权益恰为公共资金。
- 保留既有：CASH→LONG / LONG→CASH / 不做空 / 宽限价 / 真实引擎 next-bar 成交。

## 4. 测试命令与结果

```powershell
python -B -m unittest discover -s tests -t . -v
```
**`Ran 73 tests ... OK`**（基线 12 + QmtGateway 加固 48 + 择时 13），既有 QMT 回归全部通过。

```powershell
python -B scripts\midea_timing_backtest.py --fetch --json work\midea_timing_summary.json
python -B scripts\midea_timing_backtest.py --csv work\midea_000333_daily_back.csv --json work\midea_timing_summary.json
```
两者结果一致（`--fetch` 已实测复现，退出码 0）。

## 5. 修正后的对比表（同一公共起点 1,000,000）

| 指标 | Buy & Hold | MA Regime | Delta (MA − BH) |
| --- | --- | --- | --- |
| 起点权益 | 1,000,000 | 1,000,000 | — |
| CAGR | 19.69% | 11.40%（净 11.28%） | **−8.41pp** |
| 年化波动率 | 29.37% | 19.24% | −10.13pp |
| Sharpe | 0.7475 | 0.6572 | **−0.0903** |
| 最大回撤 | 55.69% | 33.16% | **−22.53pp** |
| Calmar | 0.3537 | 0.3436 | −0.0101 |
| 期末权益 | 9,217,566 | 3,794,786（净 3,748,027） | — |
| 进出场 | 1 / 1 | 42 / 41 | — |
| 年化换手 | 0.83 | 15.16 | — |
| 印花税（卖出） | 4,611 | 46,758 | — |

**结论（与旧数字不同，已重算）**：修正公共起点后，MA Regime 的 CAGR 由原报告 13.37% 降至 **11.40%**（此前可在分析窗口前交易抬高了结果）。MA 仍显著降低回撤（−22.5pp）与波动（−10.1pp），但收益（−8.4pp）与 Sharpe（−0.090）均落后于买入持有，Calmar 基本持平略低。**不宣称择时更优**；其为"降回撤/降波动"取向的保守基线。

## 6. 剩余限制（如实声明）

1. 复权价用于信号/收益，绝对滑点与整手现金为研究近似（见上）。
2. T+1 为结构性兼容，未建模显式可卖约束；未建模涨跌停无法成交。
3. 印花税单列披露，未并入逐日 MA 曲线。
4. 保守 gap_buffer(1.20) 使实际投入比例约 83%，非严格 100%。
5. 单一标的/单一区间；`work/` 下数据 gitignored，`--fetch` 可复现。

## 7. 交易副作用声明

**零实盘副作用**：新增委托数 = 0，新增成交数 = 0，撤单数 = 0；未启用/修改 QmtGateway 写路径（`send_order`/`cancel_order` 仍 `NotImplementedError`）；未动 `D:\veighna_studio`、MiniQMT 配置、未安装/升级依赖。

## Definition of Done 核对（修复任务书）

```text
[x] both strategies start analysis window at exactly 1,000,000 and flat
[x] pre-start bars warm indicators but cannot trade
[x] next-bar execution remains verified
[x] entry sizing cannot create negative cash in tested gap-up case
[x] board-lot constraint remains 100 shares
[x] long-only remains enforced
[x] Buy&Hold daily equity includes idle cash
[x] CAGR basis is consistent
[x] report clearly qualifies T+1 modeling
[x] report clearly qualifies adjusted-price execution assumptions
[x] all existing QMT tests still pass
[x] no live order/cancel path added
```
