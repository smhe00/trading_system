# TASK: Midea A Historical Regime / Old-vs-Recent Data Study

Date: 2026-09-07
Based on accepted baseline review: `interactive/REVIEW_MIDEA_A_TIMING_METRIC_ALIGNMENT_FIX_20260907.md`
State: **AUTHORIZED**
Target: 美的集团 A股 `000333.SZ`
Nature: research/backtest only

## 1. Goal

Answer the next research question before adding ML:

> For medium-horizon timing of Midea A, does older history still contain useful information, or is timing behavior materially different in recent years?

This task is **not** an optimization task. Keep the accepted MA baseline fixed and measure regime robustness / signal relevance across time.

The study must distinguish:

1. performance differences caused by timing;
2. performance differences caused merely by lower capital exposure;
3. whether the fixed MA state still separates future 20D/60D returns in old vs recent periods.

## 2. Baseline is frozen

Do not modify the accepted rule:

```text
LONG if:
close > MA120
AND
MA20 > MA60

otherwise CASH
```

Keep:

```text
fast_window = 20
mid_window  = 60
slow_window = 120
gap_buffer  = 1.20
lot_size    = 100
initial capital = 1,000,000
next-bar execution
long-only
```

Do not optimize these values.

## 3. Required study periods

Use fixed calendar regime boundaries; do not move them after seeing results.

```text
R1 early   : 2014-04-01 .. 2017-12-31
R2 middle  : 2018-01-01 .. 2020-12-31
R3 recent1 : 2021-01-01 .. 2023-12-31
R4 recent2 : 2024-01-01 .. 2026-09-04
```

Also report two aggregate views:

```text
OLD    : 2014-04-01 .. 2020-12-31
RECENT : 2021-01-01 .. 2026-09-04
```

For every requested interval:

- use the first/last **available tradable bar** inside the calendar bounds;
- report actual first/last trading dates used;
- reset portfolio state to 1,000,000 and flat at the interval start;
- use at least 120 prior tradable bars only for indicator warm-up;
- warm-up data must never generate pre-period trades.

## 4. Three strategy comparators are mandatory

For every regime compare:

### A. `BH_100`

100% Buy & Hold baseline using the accepted common accounting conventions.

### B. `BH_STATIC_CONSERVATIVE`

A static Buy & Hold comparator with target capital exposure approximately equal to the MA baseline's conservative sizing:

```text
target exposure ≈ 1 / gap_buffer = 83.33%
```

Requirements:

- keep residual capital as cash;
- use board-lot and buy-cost-aware sizing;
- report the actual initial deployed fraction after lot rounding/cost reserve;
- no rebalancing after entry.

Purpose: separate "lower drawdown because only ~83% invested" from actual timing value.

### C. `MA_FIXED`

The accepted fixed MA20/60/120 conservative-capital strategy, unchanged.

## 5. Required performance metrics per regime

For all three comparators report using the accepted common start-anchor / primary MTM convention:

```text
start_equity
actual start/end trading dates
period_count / years
final_equity
CAGR
annualized_volatility
Sharpe (rf=0)
MaxDD
Calmar
entries / exits
annualized_turnover
realized_stamp_duty (disclosed under current baseline convention)
time_in_market
```

For `MA_FIXED`, also report:

```text
average deployed fraction while LONG
overall average gross exposure
```

If these require reconstructing a daily position series from trades, implement it deterministically and test it.

For each regime calculate deltas:

```text
MA_FIXED - BH_100
MA_FIXED - BH_STATIC_CONSERVATIVE
```

for at least:

```text
CAGR
Sharpe
MaxDD
Calmar
```

## 6. Medium-horizon signal relevance diagnostic

This is descriptive research, not a trading backtest.

For each date t after sufficient MA warm-up, compute the fixed MA state using only information available through t close:

```text
LONG_STATE = close_t > MA120_t AND MA20_t > MA60_t
CASH_STATE = otherwise
```

Then calculate forward adjusted-price returns:

```text
R20 = close[t+20] / close[t] - 1
R60 = close[t+60] / close[t] - 1
```

For each R1/R2/R3/R4 and OLD/RECENT period, separately for LONG_STATE and CASH_STATE report:

```text
sample count
mean forward return
median forward return
P(forward return > 0)
```

Also report the discrimination spread:

```text
mean(R20 | LONG) - mean(R20 | CASH)
median(R20 | LONG) - median(R20 | CASH)
mean(R60 | LONG) - mean(R60 | CASH)
median(R60 | LONG) - median(R60 | CASH)
```

Rules:

- no future value may enter the state calculation;
- do not use R20/R60 to tune MA parameters;
- forward-return samples overlap, so **do not claim independent-sample statistical significance** from naive t-tests;
- this diagnostic is meant to show whether the same signal has directionally stable medium-horizon information across eras.

## 7. Basic feature/regime drift summary

For each R1–R4, report median and IQR for these fixed features:

```text
20D return
60D return
20D realized volatility
close / MA120 - 1
MA20 / MA60 - 1
```

This is descriptive only. Do not optimize thresholds.

Purpose: determine whether the input distribution has materially shifted between old and recent Midea history.

## 8. Required conclusion

The report must explicitly answer:

### A. Is the fixed MA rule stable across regimes?

Choose one best-supported label:

```text
STABLE_ACROSS_REGIMES
RECENTLY_STRONGER
HISTORICALLY_STRONGER
REGIME_DEPENDENT
NO_STABLE_TIMING_EDGE
```

### B. Does the drawdown reduction survive exposure matching?

Compare `MA_FIXED` against `BH_STATIC_CONSERVATIVE`, not only against 100% B&H.

### C. What should we do with old data for the later ML stage?

Choose one provisional recommendation and explain it from the measurements:

```text
KEEP_FULL_HISTORY_EQUAL_WEIGHT
KEEP_FULL_HISTORY_WITH_RECENCY_WEIGHT
ROLLING_3Y_TO_5Y_PRIMARY_WITH_OLD_HISTORY_FOR_ROBUSTNESS
RECENT_ONLY
INSUFFICIENT_EVIDENCE
```

Do **not** claim this proves the optimal ML training window; this task only establishes evidence for the next ML experiment.

## 9. Allowed files

Prefer adding a separate study script rather than destabilizing the locked baseline.

Allowed implementation files:

```text
scripts/midea_history_regime_study.py
src/trader/strategies/midea_timing/research.py        # optional, pure research helpers only
src/trader/strategies/midea_timing/__init__.py       # only if exports are needed
tests/strategies/test_midea_history_regime.py
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_HISTORY_REGIME_STUDY_20260907.md
```

You may import/reuse the locked baseline code from:

```text
scripts/midea_timing_backtest.py
src/trader/strategies/midea_timing/ma_regime.py
```

Do not modify those locked baseline files unless a genuine blocking API extraction is impossible. If modification appears necessary, STOP and explain why in the report rather than silently changing the baseline.

Do not modify QmtGateway or any broker write path.

## 10. Data

Reuse the same local MiniQMT / XtQuant daily adjusted data source and adjustment convention as the locked baseline.

Do not install or upgrade dependencies.

The study must work from:

```powershell
python -B scripts\midea_history_regime_study.py --fetch --json work\midea_history_regime_summary.json
```

and, if the baseline CSV already exists:

```powershell
python -B scripts\midea_history_regime_study.py --csv work\midea_000333_daily_back.csv --json work\midea_history_regime_summary.json
```

`--fetch` and `--csv` results must agree.

## 11. Tests

At minimum add deterministic tests for:

```text
[ ] each regime resets to 1,000,000 flat
[ ] pre-regime warm-up cannot trade
[ ] actual bar boundaries stay inside requested calendar interval
[ ] static conservative B&H has no rebalancing
[ ] static conservative exposure is below/equal to full B&H exposure
[ ] MA parameters remain exactly 20/60/120 and gap_buffer=1.20
[ ] daily position/exposure reconstruction is consistent with trades
[ ] forward R20 uses exactly t+20 close and no earlier future data
[ ] forward R60 uses exactly t+60 close and no earlier future data
[ ] final 20/60 bars without a forward target are excluded, not filled
[ ] OLD/RECENT aggregate boundaries are fixed
[ ] all existing QMT and locked-baseline tests still pass
```

Run:

```powershell
python -B -m unittest discover -s tests -t . -v
```

## 12. Prohibited scope expansion

Do not:

- optimize MA windows;
- add LightGBM/Qlib/RL yet;
- fit any predictive model;
- select regime boundaries based on results;
- add external alternative datasets;
- add intraday execution;
- add live send/cancel;
- change QmtGateway;
- modify VeighNa Studio;
- install or upgrade packages.

## 13. Report

Write a new report:

```text
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_HISTORY_REGIME_STUDY_20260907.md
```

Include:

1. exact changed files;
2. data source and actual date coverage;
3. implementation/methodology;
4. R1–R4 and OLD/RECENT performance tables;
5. `BH_100` vs `BH_STATIC_CONSERVATIVE` vs `MA_FIXED` comparison;
6. forward R20/R60 state-conditional tables;
7. feature drift table;
8. required three-part conclusion;
9. tests and exact commands/results;
10. limitations;
11. explicit statement of live trading side effects.

## Definition of Done

```text
[ ] locked baseline is not altered
[ ] R1/R2/R3/R4 are evaluated independently with reset capital
[ ] OLD/RECENT aggregate views are reported
[ ] exposure-matched static comparator is included
[ ] fixed MA state forward R20/R60 diagnostic is complete
[ ] basic feature drift is reported
[ ] old-vs-recent data recommendation is explicit but provisional
[ ] all tests pass
[ ] no live trading side effects
```
