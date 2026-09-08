# TASK: Midea A — vnpy.alpha Challenger Execution Timeline Fix

Date: 2026-09-08
Based on review: `interactive/REVIEW_MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER_FIX_20260908.md`
State: **AUTHORIZED**
Target: 美的集团 A股 `000333.SZ`
Nature: **research/backtest only**

## 1. Goal

Fix the remaining execution-timeline and validation-boundary defects in the existing vnpy.alpha / LightGBM challenger **without changing the model, features, threshold, walk-forward windows, baseline rules, or dependencies**.

The current numerical challenger results are provisional until this task passes.

## 2. Frozen items — do not change

Keep exactly:

```text
10 frozen price/volatility features
y20 = close[t+20]/close[t]-1
LightGBM fixed configuration / nearest official LgbModel mapping
LONG iff predicted_y20 > 0
3Y annual walk-forward schedule
5Y annual walk-forward robustness schedule
100-share lot
commission/slippage assumptions
gap_buffer = 1.20
buy limit = signal_close × 1.15
long-only
1,000,000 start equity per evaluation window
```

Do not tune or add features/models/thresholds.

Do not modify:

```text
scripts/midea_timing_backtest.py
src/trader/strategies/midea_timing/ma_regime.py
scripts/midea_history_regime_study.py
src/trader/gateways/qmt/**
D:\veighna_studio
MiniQMT configuration
```

Do not install/upgrade/downgrade packages.

## 3. P0 — make the simulator strictly chronological

Current bug: a transition detected at signal bar `t` mutates cash/position using bar `t+1` before the equity row for `t` is recorded.

Refactor `simulate_ml()` to an explicit pending-order timeline.

Required chronological order for each bar `t`:

```text
A. BAR OPEN / INTRABAR
   process only an order already pending from a prior signal bar
   determine fill/no-fill using the current bar
   mutate cash/position only at this point

B. BAR CLOSE
   mark equity for date t using the position actually held at t close

C. AFTER CLOSE
   read prediction/state for t
   decide desired target state
   create/update/cancel an order that cannot execute before the next tradable bar
```

Hard invariant:

```text
no bar t equity value may depend on bar t+1 open/high/low/close
```

Initial LONG behavior:

```text
first evaluation bar close: still flat, equity = 1,000,000
if first signal is LONG: create order after first close
second tradable bar or later: earliest possible fill
```

## 4. P0 — pending/no-fill semantics

A desired-state transition is not complete until the position matches the target state.

Implement one single pending order at a time.

### LONG target

After a LONG signal while flat:

```text
size at signal close using:
max_price = signal_close × gap_buffer

buy limit = signal_close × 1.15
```

The pending buy may fill on a later bar only when that bar crosses the limit.

Recommended deterministic bar rule:

```text
if bar.low <= buy_limit:
    fill_price = min(bar.open, buy_limit)
else:
    remain pending
```

If the desired state changes back to CASH before fill, cancel the pending buy with no trade.

Do not stack duplicate pending buy orders.

### CASH target / exit

When long and a CASH signal occurs, create a pending sell after that close using:

```text
sell limit = signal_close × 0.85
```

Recommended deterministic bar rule:

```text
if bar.high >= sell_limit:
    fill_price = max(bar.open, sell_limit)
else:
    remain pending
```

If desired state changes back to LONG before the sell fills, cancel the pending sell and remain long.

Do not create duplicate exit orders.

The policy must be documented and deterministic.

## 5. Required execution tests

Add deterministic tests proving at least:

```text
[ ] signal-day equity is unchanged by a next-day fill
[ ] initial LONG first bar -> earliest fill is next tradable bar
[ ] before fill, position remains zero
[ ] after fill, position appears starting on the fill date, not one day earlier
[ ] one-bar no-fill followed by later crossing -> one eventual fill
[ ] no-fill LONG then state returns CASH -> pending buy cancelled, no entry
[ ] no duplicate stacked entry orders while pending
[ ] exit signal does not change signal-day equity/position
[ ] sell-limit no-fill persists correctly
[ ] sell fill occurs only on/after a bar crossing the sell limit
[ ] no duplicate stacked exit orders
[ ] cash remains non-negative under modeled fills
[ ] all trade dates match the actual fill bars
```

## 6. P1 — make early-stopping validation label-clean

The current fit/valid row ranges are disjoint, but late-fit `y20` labels may use target prices from the validation year because purge is based on the declared training-window end.

Required containment:

```text
FIT sample:
state/features date t inside fit range
AND y20 target date t+20 <= fit_end

VALID sample:
state/features date t inside valid range
AND y20 target date t+20 <= valid_end
AND target remains before OOS test start
```

No validation-period price may appear in a FIT label.
No OOS-period price may appear in a VALID label.

Implement this through the official AlphaDataset processor path or another official-compatible mechanism without bypassing vnpy.alpha.

Required tests:

```text
[ ] late-fit row whose t+20 lands in VALID is purged from FIT
[ ] last valid rows whose t+20 lands in OOS are purged from VALID
[ ] retained FIT labels end no later than fit_end
[ ] retained VALID labels end no later than valid_end
[ ] OOS rows/prices never enter fit or valid labels
```

Report per fold:

```text
fit_range
valid_range
test_range
fit_count_after_purge
valid_count_after_purge
max FIT label target date
max VALID label target date
```

## 7. Recompute all challenger results

After the simulator and label-boundary fixes, rerun the full predeclared study from scratch.

Report the same evaluation windows:

```text
ALL_3Y
RECENT_3Y
R4_3Y
ALL_5Y
RECENT_5Y
R4_5Y
```

and the same mandatory comparators:

```text
BH_100
BH_STATIC_CONSERVATIVE
MA_FIXED
ML_ROLLING
BH_STATIC_MATCHED_AVG_EXPOSURE (ex-post diagnostic)
```

Recompute:

```text
CAGR
annualized volatility
Sharpe
MaxDD
Calmar
entries/exits
annualized turnover
realized stamp duty
time_in_market
overall_avg_gross_exposure
```

Do not reuse prior ML performance numbers.

Re-evaluate conclusions A/B/C/D only after recomputation.

## 8. Environment health disclosure only

Do not mutate packages in this task.

The prior report recorded:

```text
peewee installed: 3.17.3
vnpy-sqlite/mysql/postgresql declared requirement: >=3.17.9
```

Run and report, if available:

```powershell
python -m pip check
```

This is diagnostic only. Do not repair dependencies without a separate explicit authorization/task.

## 9. Allowed files

Only modify as needed:

```text
src/trader/strategies/midea_timing/ml_research.py
scripts/midea_vnpy_alpha_lightgbm_challenger.py
tests/strategies/test_midea_vnpy_alpha_challenger.py
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_VNPY_ALPHA_EXECUTION_TIMELINE_FIX_20260908.md
```

Do not overwrite prior reports.

## 10. Required commands

Run:

```powershell
python -B -m unittest discover -s tests -t . -v
python -B scripts\midea_vnpy_alpha_lightgbm_challenger.py --csv work\midea_000333_daily_back.csv --json work\midea_vnpy_alpha_lightgbm_summary.json
python -B scripts\midea_vnpy_alpha_lightgbm_challenger.py --fetch --json work\midea_vnpy_alpha_lightgbm_summary.json
```

`--csv` and `--fetch` must agree for identical source data.

## 11. Safety / prohibited scope

Do not:

- place or cancel real orders;
- enable QmtGateway writes;
- change QMT account/configuration;
- install or alter packages;
- change locked baseline files;
- tune LightGBM;
- change feature set;
- change threshold;
- change 3Y/5Y windows;
- add Qlib/RL/cvxportfolio/skfolio;
- add external datasets.

## 12. Report

Write a new report:

```text
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_VNPY_ALPHA_EXECUTION_TIMELINE_FIX_20260908.md
```

Include:

1. exact changed files;
2. chronological execution state machine;
3. pending-order/no-fill/cancel semantics;
4. tests proving no backward application of fills;
5. fit/valid label-containment implementation and per-fold boundary evidence;
6. complete recomputed OOS tables;
7. recomputed A/B/C/D conclusions;
8. test and reproducibility commands/results;
9. `pip check` diagnostic result without package mutation;
10. explicit statement of zero live-trading side effects.

## Definition of Done

```text
[ ] t equity never depends on t+1 execution data
[ ] initial LONG remains next-bar or later
[ ] pending no-fill behavior is deterministic and does not suppress target state
[ ] buy/sell limit crossing is symmetric and tested
[ ] no duplicate pending orders
[ ] FIT labels do not consume VALID-period prices
[ ] VALID labels do not consume OOS-period prices
[ ] all existing tests plus new tests pass
[ ] challenger OOS metrics fully recomputed
[ ] no package mutation
[ ] locked baselines/QmtGateway unchanged
[ ] zero live-trading side effects
```
