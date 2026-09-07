# TASK: Midea A Timing Baseline — Metric Alignment Fix

Date: 2026-09-07
Based on review: `interactive/REVIEW_MIDEA_A_TIMING_TERMINAL_VALUATION_FIX_20260907.md`
State: **CHANGES_REQUIRED**
Target: 美的集团 A股 `000333.SZ`
Nature: research/backtest only

## 1. Goal

Finish the remaining metric-accounting alignment so Buy & Hold and the conservative-capital MA regime can be frozen as the formal Midea timing baseline.

This task is intentionally narrow. Do not change the signal rule, optimize parameters, add ML, or add live trading capability.

## 2. Allowed files

Implementation may modify only:

```text
src/trader/strategies/midea_timing/ma_regime.py        # only if a shared pure helper is useful
src/trader/strategies/midea_timing/__init__.py         # only if helper export is needed
scripts/midea_timing_backtest.py
tests/strategies/test_midea_ma_regime.py
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_TIMING_METRIC_ALIGNMENT_FIX_20260907.md
```

Do not modify QmtGateway, MiniQMT configuration, VeighNa Studio, unrelated modules, or previous task/review/report files.

## 3. Mandatory fixes

### 3.1 One common explicit start anchor for both equity series

Both scored equity series must follow the same shape:

```text
point 0: analysis-start-open anchor = 1,000,000
point 1: first analysis trading day's close-marked equity
point 2: second trading day's close-marked equity
...
point N: last analysis trading day's close-marked equity
```

For MA, because it is flat on the analysis-start day under next-bar execution, point 1 will normally remain 1,000,000, giving an explicit 0% first-period return.

Requirements:

- B&H and MA must have the same number of scored return periods for the same analysis window;
- the first-period return must exist for both;
- do not introduce pre-start trading or look-ahead;
- prefer an unambiguous anchor timestamp strictly before the first close point (for example a synthetic start-open timestamp) rather than relying on duplicate datetime indexes.

### 3.2 One common duration/CAGR basis

Do not use raw `len(series) / ANNUAL_DAYS` when one point is an anchor.

Use a common duration basis such as:

```text
period_count = len(equity_series) - 1
years = period_count / ANNUAL_DAYS
```

or an equivalent explicit common trading-period count.

B&H and MA for the same analysis window must report identical `years` / period count.

### 3.3 Separate primary MTM activity metrics from optional liquidation metrics

Primary convention remains **last-close mark-to-market**.

For B&H primary MTM path:

```text
entries = 1
exits = 0
primary turnover = entry notional only
primary realized stamp duty = 0
```

because the position remains open at the primary endpoint.

For MA primary MTM path:

- entries/exits/turnover reflect actual vn.py trades only;
- no artificial terminal exit is added to actual trade history.

Optional liquidation may expose separate fields, for example:

```text
liquidated_exits
liquidated_total_turnover
liquidated_annualized_turnover
terminal_sell_commission
terminal_sell_slippage
terminal_stamp_duty
```

If liquidated turnover/activity fields are added, apply the same convention to both B&H and MA.

### 3.4 Clean report labeling

The final comparison must not place incomparable values in one row.

Separate at minimum:

```text
Primary MTM:
- start_equity
- primary_final_equity
- CAGR
- annualized_vol
- Sharpe
- MaxDD
- Calmar
- actual entries/exits
- actual annualized turnover
- actual realized stamp duty (if separately tracked)

Optional liquidation:
- liquidated_final_equity
- liquidated_CAGR
- terminal sell commission
- terminal sell slippage
- terminal stamp duty
- optional liquidated turnover/activity if reported
```

## 4. Preserve all prior fixes

The following must remain true:

- pre-start bars warm indicators but cannot trade;
- next-bar execution;
- no same-close look-ahead;
- long-only;
- 100-share board lots;
- cost-aware strategy cash ledger;
- B&H sizing reserves buy costs;
- no synthetic negative cash in tested scenarios;
- shared terminal liquidation helper/convention;
- conservative-capital disclosure remains explicit (`gap_buffer=1.20`, typical deployment ≈83%);
- no QMT write path.

## 5. Tests required

Add/update tests proving at least:

```text
[ ] B&H equity series has explicit 1,000,000 start-open anchor
[ ] MA equity series has the same explicit 1,000,000 start-open anchor
[ ] B&H and MA have identical scored period count for the same bar window
[ ] B&H and MA report identical years for the same bar window
[ ] MA first analysis-day flat period is represented as an explicit 0% return
[ ] B&H first open->close return is represented
[ ] primary B&H entries=1 and exits=0
[ ] primary B&H turnover excludes optional terminal sale
[ ] primary B&H realized stamp duty excludes optional terminal sale
[ ] optional terminal liquidation remains symmetric and correct
[ ] previous cost/no-lookahead/start-gate tests still pass
[ ] all QMT regression tests still pass
```

## 6. Recompute baseline

Run:

```powershell
python -B -m unittest discover -s tests -t . -v
python -B scripts\midea_timing_backtest.py --fetch --json work\midea_timing_summary.json
python -B scripts\midea_timing_backtest.py --csv work\midea_000333_daily_back.csv --json work\midea_timing_summary.json
```

`--fetch` and `--csv` results must agree.

Do not copy previous metrics; recompute them after the alignment fix.

## 7. Report

Write a new report:

```text
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_TIMING_METRIC_ALIGNMENT_FIX_20260907.md
```

Report must include:

1. exact changed files;
2. final common start-anchor convention;
3. final duration/period convention;
4. primary vs liquidated activity/turnover semantics;
5. tests added and exact results;
6. fully recomputed comparison table;
7. remaining limitations;
8. explicit zero-live-trading side-effect statement.

Do not overwrite prior reports.

## Definition of Done

```text
[ ] same explicit start-open equity anchor for B&H and MA
[ ] same scored return-period count for B&H and MA
[ ] same duration/CAGR basis for B&H and MA
[ ] primary MTM activity metrics do not contain artificial terminal exits
[ ] optional liquidation metrics remain symmetric
[ ] previous safety/cost/no-lookahead fixes remain intact
[ ] all tests pass
[ ] baseline is recomputed
[ ] no live trading side effects
```
