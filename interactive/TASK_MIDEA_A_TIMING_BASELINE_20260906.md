# TASK: Midea A-share Timing Baseline

Date: 2026-09-06
Target: **美的集团 A股 `000333.SZ`**
State: **AUTHORIZED**

## 1. Goal

Build the first reproducible single-stock timing baseline for Midea A-share using the existing VeighNa/vn.py environment.

This task is **research/backtest only**. It must not enable live trading or modify the read-only QmtGateway boundary.

The purpose is to establish a benchmark before introducing ML, Qlib, cvxportfolio or RL.

## 2. Scope

Implement and compare exactly these baselines on daily data:

1. **Buy & Hold**
2. **MA Regime Timing**

Initial MA regime rule:

```text
LONG/HOLD when:
    close > MA120
    AND MA20 > MA60
otherwise:
    CASH
```

A-share position state for this task is binary:

```text
0% or 100%
```

Do not add parameter mining or complex indicators yet.

## 3. vn.py usage

Prefer the installed official VeighNa stack.

Expected implementation path:

```text
historical daily bars
    -> vn.py / vnpy_ctastrategy backtest infrastructure if available
    -> Midea timing strategy
    -> metrics + trade/equity output
```

First verify whether `vnpy_ctastrategy` is installed and importable in the current `.venv`.

- If available: use it.
- If unavailable: **do not install or upgrade dependencies without authorization**. Report BLOCKED with the exact missing package/version condition.

Do not use Qlib, vnpy.alpha, cvxportfolio, skfolio or RL in this task.

## 4. Data

Target symbol:

```text
000333.SZ
```

Use an existing available data path in the environment where practical, preferably XtQuant if it can provide reliable adjusted daily history.

Requirements:

- record the exact data source
- record date range
- record adjustment mode (前复权/后复权/不复权)
- avoid look-ahead bias
- do not silently fill missing trading days

If corporate-action adjustment cannot be established reliably, stop and report the limitation rather than producing a misleading backtest.

## 5. A-share trading assumptions

The backtest must explicitly model or document:

- T+1 constraint
- 100-share board lot for buys
- commission assumption
- stamp duty on sells
- slippage assumption
- no ordinary short selling

For this first baseline, signal generation may occur on day `t` close and execution must not assume an impossible same-close fill. Use next tradable bar execution or another clearly non-look-ahead convention.

## 6. Metrics

For both Buy & Hold and MA Regime report at least:

```text
CAGR
annualized volatility
Sharpe ratio
maximum drawdown
Calmar ratio
number of entries/exits
annualized turnover or equivalent turnover measure
final equity
```

Primary comparison:

```text
Delta Sharpe = Sharpe_MA - Sharpe_BuyHold
Delta MaxDD  = MaxDD_MA - MaxDD_BuyHold
Delta CAGR   = CAGR_MA - CAGR_BuyHold
```

Do not claim the timing strategy is superior based only on CAGR.

## 7. Suggested project structure

Use the existing repository layout. Suggested additions:

```text
src/trader/strategies/midea_timing/
    __init__.py
    ma_regime.py

scripts/
    midea_timing_backtest.py

tests/strategies/
    test_midea_ma_regime.py
```

Keep implementation small. Do not restructure unrelated modules.

## 8. Safety / prohibited actions

Prohibited:

- real orders
- real cancellations
- enabling QmtGateway write paths
- changing MiniQMT configuration
- modifying `D:\veighna_studio`
- package upgrades/installations without explicit authorization
- parameter grid search
- ML models
- Qlib
- cvxportfolio
- RL

The existing QMT gateway must remain strictly read-only.

## 9. Tests

At minimum test:

- MA20/MA60/MA120 warm-up behavior
- no signal before sufficient history
- transition CASH -> LONG only when both conditions hold
- transition LONG -> CASH when either condition fails
- no same-bar look-ahead execution assumption
- no negative/short position state

Run the existing QMT tests as regression tests as well; this task must not break the accepted gateway baseline.

## 10. Deliverables

Create a new report:

```text
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_TIMING_BASELINE_20260906.md
```

Report must include:

1. changed files
2. vn.py module actually used and installed version
3. data source / range / adjustment mode
4. execution and cost assumptions
5. exact commands run
6. test results
7. Buy & Hold metrics
8. MA Regime metrics
9. direct comparison table
10. remaining limitations
11. explicit statement that no live order/cancel occurred

Do not overwrite prior reports.

## 11. Definition of Done

```text
[ ] target is exactly 000333.SZ
[ ] historical adjusted daily data source is documented
[ ] Buy & Hold baseline is reproducible
[ ] MA20/60/120 timing baseline is reproducible
[ ] execution avoids same-close look-ahead
[ ] A-share costs/constraints are documented or modeled
[ ] required metrics are produced for both baselines
[ ] unit tests pass
[ ] existing QMT regression tests still pass
[ ] no live order submitted
[ ] no live order cancelled
[ ] QmtGateway remains read-only
[ ] implementation report written under interactive/reports/
```
