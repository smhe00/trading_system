# TASK: Midea A Historical Regime Study — Boundary/Report Fix

Date: 2026-09-08
Based on review: `interactive/REVIEW_MIDEA_A_HISTORY_REGIME_STUDY_20260908.md`
State: **CHANGES_REQUIRED**
Target: 美的集团 A股 `000333.SZ`
Nature: research/backtest only

## 1. Goal

Fix the historical-regime study without changing the locked trading baseline.

Two things are required:

1. eliminate cross-regime contamination in the forward R20/R60 diagnostic;
2. complete the mandatory report fields that were omitted from the first submission.

Do not optimize MA parameters, add ML, or change the accepted Midea timing baseline.

## 2. Allowed files

Implementation may modify only:

```text
scripts/midea_history_regime_study.py
src/trader/strategies/midea_timing/research.py
tests/strategies/test_midea_history_regime.py
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_HISTORY_REGIME_STUDY_FIX_20260908.md
```

Do not overwrite the previous implementation report.

Do not modify:

```text
scripts/midea_timing_backtest.py
src/trader/strategies/midea_timing/ma_regime.py
src/trader/strategies/midea_timing/__init__.py
src/trader/gateways/qmt/**
```

No dependency installation or upgrade is authorized.

## 3. Mandatory forward-diagnostic fix

The evaluation sample for each regime/horizon must be regime-contained.

For every sample used in R1/R2/R3/R4/OLD/RECENT:

```text
state date t    must be inside [start, end]
target date t+h must also be inside [start, end]
```

where `h` is 20 or 60 trading bars.

Examples:

```text
OLD sample at 2020-12-xx whose t+20 lands in 2021 -> EXCLUDE
R2 sample whose t+60 lands in R3 -> EXCLUDE
RECENT tail without t+20/t+60 inside RECENT -> EXCLUDE
```

The state at `t` must continue to use only information available through `t` close.

Do not truncate the horizon to the regime end, forward-fill, backfill, or substitute a nearer target.

## 4. Required tests for boundary containment

Add deterministic tests that prove at least:

```text
[ ] R20 sample whose target crosses a regime end is excluded
[ ] R60 sample whose target crosses a regime end is excluded
[ ] a sample with t+h exactly on the regime's last included trading date is accepted
[ ] OLD diagnostic never consumes a target date in RECENT
[ ] state calculation at t is unchanged by data after t
[ ] global final 20/60 bars remain excluded as before
```

Keep all existing regime/QMT/baseline regression tests passing.

## 5. Recompute the signal tables and conclusions

After fixing containment, recompute for every R1/R2/R3/R4/OLD/RECENT period:

```text
R20 LONG: count / mean / median / P(>0)
R20 CASH: count / mean / median / P(>0)
R20 mean and median spread

R60 LONG: count / mean / median / P(>0)
R60 CASH: count / mean / median / P(>0)
R60 mean and median spread
```

Then re-evaluate, rather than copy, these conclusions:

```text
A. STABLE_ACROSS_REGIMES / RECENTLY_STRONGER / HISTORICALLY_STRONGER /
   REGIME_DEPENDENT / NO_STABLE_TIMING_EDGE

B. whether drawdown reduction survives exposure matching

C. old-data recommendation:
   KEEP_FULL_HISTORY_EQUAL_WEIGHT
   KEEP_FULL_HISTORY_WITH_RECENCY_WEIGHT
   ROLLING_3Y_TO_5Y_PRIMARY_WITH_OLD_HISTORY_FOR_ROBUSTNESS
   RECENT_ONLY
   INSUFFICIENT_EVIDENCE
```

The performance backtests need not change unless the fix reveals another genuine accounting defect. The forward-diagnostic tables and conclusions must be regenerated.

## 6. Complete the Markdown report

The new report must explicitly include the fields required by the original task, not only leave them in JSON.

For every regime and all three comparators, report:

```text
actual_start
actual_end
start_equity
period_count
years
final_equity
CAGR
annualized_volatility
Sharpe
MaxDD
Calmar
entries/exits
annualized_turnover
realized_stamp_duty
time_in_market
```

For `BH_STATIC_CONSERVATIVE`, additionally report:

```text
initial_deployed_fraction
```

For `MA_FIXED`, additionally report:

```text
avg_deployed_while_long
overall_avg_gross_exposure
```

The forward table must include sample counts for **both R20 and R60**, LONG and CASH.

## 7. Feature-drift report completeness

For every R1–R4 and every requested feature:

```text
20D trailing return
60D trailing return
20D realized volatility
close / MA120 - 1
MA20 / MA60 - 1
```

report:

```text
median
Q25
Q75
```

Use one documented standard quantile convention consistently. Prefer an existing standard-library or already-installed pandas quantile implementation; do not add dependencies.

## 8. Verification

Run:

```powershell
python -B -m unittest discover -s tests -t . -v
python -B scripts\midea_history_regime_study.py --fetch --json work\midea_history_regime_summary.json
python -B scripts\midea_history_regime_study.py --csv work\midea_000333_daily_back.csv --json work\midea_history_regime_summary.json
```

The `--fetch` and `--csv` summaries must agree.

Also verify by repository diff that the locked baseline and QMT gateway files are unchanged.

## 9. Safety / scope

This remains research-only.

Do not:

- add or enable `send_order` / `cancel_order`;
- place real or simulation orders;
- modify MiniQMT configuration;
- optimize MA20/60/120 or `gap_buffer`;
- add LightGBM/Qlib/RL;
- change regime boundaries;
- add external data sources;
- modify VeighNa Studio.

## 10. Report

Write a new report:

```text
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_HISTORY_REGIME_STUDY_FIX_20260908.md
```

Include:

1. exact changed files;
2. boundary-containment implementation;
3. tests added and exact results;
4. complete performance/regime tables;
5. recomputed R20/R60 tables with counts;
6. complete feature-drift median/Q25/Q75 table;
7. re-evaluated three-part conclusion;
8. `--fetch` vs `--csv` reproducibility;
9. remaining limitations;
10. explicit zero-live-side-effect statement.

## Definition of Done

```text
[ ] no forward target crosses the evaluated regime boundary
[ ] OLD forward diagnostic contains no RECENT target price
[ ] R20/R60 boundary tests pass
[ ] all mandatory performance fields are present in Markdown
[ ] R20/R60 counts are present for LONG and CASH
[ ] all five drift features include median/Q25/Q75
[ ] conclusions are recomputed after censoring
[ ] locked baseline remains unchanged
[ ] all tests pass
[ ] --fetch and --csv agree
[ ] no live trading side effects
```
