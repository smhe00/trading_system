# TASK: Midea A Timing Baseline — Terminal Valuation Fix

Date: 2026-09-07
Based on review: `interactive/REVIEW_MIDEA_A_TIMING_BASELINE_COST_FIX_20260907.md`
State: **CHANGES_REQUIRED**
Target: 美的集团 A股 `000333.SZ`
Nature: research/backtest only

## 1. Goal

Fix the remaining boundary-accounting inconsistency in the Midea timing baseline so Buy & Hold and the conservative-capital MA regime use the **same starting and terminal valuation conventions**.

Do not change the MA signal rule, optimize parameters, add ML, or add live trading capability.

## 2. Allowed files

Implementation may modify only:

```text
src/trader/strategies/midea_timing/ma_regime.py
src/trader/strategies/midea_timing/__init__.py
scripts/midea_timing_backtest.py
tests/strategies/test_midea_ma_regime.py
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_TIMING_TERMINAL_VALUATION_FIX_20260907.md
```

Do not modify QmtGateway, MiniQMT configuration, VeighNa Studio, unrelated modules, or previous task/review/report files.

## 3. Required fixes

### 3.1 Use one primary terminal convention

Preferred primary convention: **mark-to-market at the last close**.

For both Buy & Hold and MA:

- start from common equity = 1,000,000;
- end primary equity at last-close mark-to-market;
- do not subtract an artificial terminal exit cost from only one strategy;
- primary `CAGR`, `Sharpe`, `annualized_vol`, `MaxDD`, `Calmar` must all correspond to the same convention.

If you choose liquidation as primary instead, it must be applied identically to both strategies and documented. Do not mix conventions.

### 3.2 Add optional common liquidation metrics

Add a shared helper or equivalent common logic for terminal liquidation accounting.

For a strategy holding shares at the final close, calculate:

```text
liquidated_final_equity
liquidated_cagr
terminal_sell_commission
terminal_sell_slippage
terminal_stamp_duty
```

using the same assumptions already defined by the baseline.

Rules:

- if final position is zero, liquidation adjustment is zero;
- if shares are held, deduct sell commission + per-share slippage + stamp duty;
- do not inject a fake vn.py trade into the actual trade history;
- Buy & Hold must use the same helper/convention as MA.

### 3.3 Add an explicit common starting-equity anchor

The daily equity series used for return statistics must include an explicit common initial equity anchor of exactly:

```text
1,000,000
```

before strategy-specific market movement is scored.

Purpose: the first analysis-period return must not be silently omitted from Buy & Hold while MA begins flat.

Implement this without introducing pre-start trading or look-ahead.

### 3.4 Preserve prior fixes

The following must remain true:

- pre-start data warms indicators but cannot trade;
- next-bar execution remains verified;
- no same-close look-ahead;
- long-only;
- 100-share board lots;
- strategy cash ledger remains cost-aware;
- Buy & Hold sizing reserves buy costs;
- no synthetic negative cash in tested cases;
- conservative-capital disclosure remains explicit (`gap_buffer=1.20`, ~83% typical deployment);
- no QMT write path is added.

## 4. Tests required

Add or update tests for all of the following:

```text
[ ] explicit starting equity anchor = 1,000,000 for B&H
[ ] explicit starting equity anchor = 1,000,000 for MA
[ ] primary terminal convention is identical for both strategies
[ ] MA ending with open position gets correct optional liquidation adjustment
[ ] MA ending flat gets zero terminal liquidation adjustment
[ ] B&H uses the same liquidation helper/convention
[ ] terminal sell commission is deducted correctly
[ ] terminal sell slippage is deducted correctly
[ ] terminal stamp duty is deducted correctly
[ ] existing cost-ledger tests still pass
[ ] existing no-lookahead/start-gate tests still pass
[ ] all existing QMT regressions still pass
```

## 5. Recompute the baseline

Re-run:

```powershell
python -B -m unittest discover -s tests -t . -v
python -B scripts\midea_timing_backtest.py --fetch --json work\midea_timing_summary.json
python -B scripts\midea_timing_backtest.py --csv work\midea_000333_daily_back.csv --json work\midea_timing_summary.json
```

`--fetch` and `--csv` results must agree.

Report a fresh comparison table containing at least:

```text
start_equity
primary_final_equity
primary_CAGR
annualized_vol
Sharpe
MaxDD
Calmar
entries/exits
annualized_turnover
liquidated_final_equity
liquidated_CAGR
terminal liquidation costs
```

Clearly distinguish **primary mark-to-market metrics** from **optional liquidated metrics**.

Do not copy prior numbers without recomputation.

## 6. Do not expand scope

Do not:

- optimize MA20/60/120;
- add volatility filter;
- add LightGBM/Qlib/RL;
- change the target stock;
- add intraday execution;
- implement live send/cancel;
- install or upgrade dependencies.

A later task will separately evaluate historical-regime robustness and recent-vs-old data usefulness.

## 7. Report

Write a new report:

```text
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_TIMING_TERMINAL_VALUATION_FIX_20260907.md
```

Include:

1. exact changed files;
2. chosen common start/end convention;
3. implementation details;
4. tests added;
5. exact test commands/results;
6. recomputed comparison table;
7. remaining limitations;
8. explicit trading side-effect statement.

Do not overwrite any previous report.

## Definition of Done

```text
[ ] Buy & Hold and MA share one explicit start-equity convention
[ ] Buy & Hold and MA share one primary terminal valuation convention
[ ] first-period return is not silently omitted for one benchmark only
[ ] optional liquidation accounting is symmetric
[ ] open MA terminal position is handled correctly
[ ] previous safety/cost/no-lookahead fixes remain intact
[ ] all tests pass
[ ] baseline is recomputed
[ ] no live trading side effects
```
