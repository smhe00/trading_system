# TASK: Midea A — vnpy.alpha / LightGBM Walk-Forward Challenger

Date: 2026-09-08
Based on accepted review: `interactive/REVIEW_MIDEA_A_HISTORY_REGIME_STUDY_FIX_20260908.md`
State: **AUTHORIZED**
Target: 美的集团 A股 `000333.SZ`
Nature: **research/backtest only**

## 1. Goal

Build the first leakage-safe ML timing challenger for the locked Midea baseline using the **official VeighNa Alpha capability** and LightGBM, then compare it against the accepted deterministic baselines under the same execution/cost/accounting conventions.

This task is intended to deepen the project's actual use of VeighNa rather than bypass it with a separate ML framework.

The accepted evidence from the regime study is:

```text
fixed MA rule: REGIME_DEPENDENT
OLD forward signal direction: broadly positive
RECENT forward signal direction: negative
feature distribution: materially shifted
provisional training recommendation:
ROLLING_3Y_TO_5Y_PRIMARY_WITH_OLD_HISTORY_FOR_ROBUSTNESS
```

This task must test that recommendation out-of-sample. It must **not** optimize the recommendation after seeing test results.

## 2. Capability gate — mandatory first step

Before implementation, inspect the existing Studio/.venv environment and report the exact installed capability:

```text
VeighNa Alpha import path
VeighNa Alpha package/module version
LightGBM availability/version
relevant public API/classes actually used
```

Use the official VeighNa Alpha module available in the installed environment (`vnpy.alpha` or the exact official import path provided by this Studio version).

Rules:

- **Do not install or upgrade anything.**
- Do not modify `D:\veighna_studio`.
- Do not silently replace VeighNa Alpha with Qlib, sklearn-only, a home-grown framework, or another package.
- If the official VeighNa Alpha capability required for this task is not importable/usable, write the report with state **BLOCKED** and the exact import/API failure, then stop.
- If LightGBM is unavailable, likewise report **BLOCKED**; do not install it.

Using LightGBM as the estimator beneath an official VeighNa Alpha workflow is acceptable. The report must make clear exactly which parts are provided by VeighNa Alpha and which by LightGBM.

## 3. Locked artifacts — do not modify

The following remain frozen:

```text
scripts/midea_timing_backtest.py
src/trader/strategies/midea_timing/ma_regime.py
scripts/midea_history_regime_study.py
src/trader/gateways/qmt/**
```

Do not alter the accepted MA20/60/120 baseline or its accounting conventions.

## 4. Data

Use exactly the same data source/convention as the locked baseline:

```text
symbol: 000333.SZ
source: local MiniQMT / XtQuant
period: daily
adjustment: back-adjusted / 后复权
latest end: 2026-09-04
```

Use older bars only when needed for feature warm-up/training.

Do not add external alternative datasets in this task.

Do not silently fill missing/suspended trading days.

## 5. Frozen feature set

Use the following features only. They are selected **before** seeing ML test results and must not be optimized or pruned in this task.

All features at date `t` must use information available through `t` close only:

```text
ret_5          = close[t] / close[t-5]   - 1
ret_20         = close[t] / close[t-20]  - 1
ret_60         = close[t] / close[t-60]  - 1
vol_20         = annualized std of trailing 20 daily returns
vol_60         = annualized std of trailing 60 daily returns
close_ma20     = close[t] / MA20[t]  - 1
close_ma60     = close[t] / MA60[t]  - 1
close_ma120    = close[t] / MA120[t] - 1
ma20_ma60      = MA20[t] / MA60[t]   - 1
ma60_ma120     = MA60[t] / MA120[t]  - 1
```

No fundamental, valuation, northbound-flow, market-index, sentiment, or volume features yet.

Purpose: first establish a clean price/volatility ML baseline.

## 6. Frozen target

Primary target:

```text
y20[t] = close[t+20] / close[t] - 1
```

This is a regression target.

Rules:

- use exactly trading-bar `t+20`;
- no interpolation/fill for missing target;
- samples lacking `t+20` are excluded;
- no target value may enter feature construction;
- for every train/test boundary, the **label target date** for every training row must remain inside the training interval and strictly before the OOS test interval.

In other words, training rows near a boundary must be purged if their `t+20` target crosses into the test period.

No 60D model in this first ML task. R60 may remain a later challenger.

## 7. Frozen LightGBM configuration

Use one fixed regression configuration; **no hyperparameter search**.

Preferred fixed parameters, if supported by the installed official workflow:

```text
objective = regression
n_estimators = 200
learning_rate = 0.03
num_leaves = 15
min_child_samples = 30
subsample = 0.8
colsample_bytree = 0.8
random_state = 42
verbosity = -1
```

If VeighNa Alpha exposes a wrapper with different parameter names/capabilities, use the nearest direct fixed mapping and document it. Do not tune parameters to improve results.

No Optuna/grid/random/Bayesian search.

## 8. Walk-forward protocol

### 8.1 Primary: rolling 3 calendar years

For each OOS calendar year `Y`:

```text
train = Y-3-01-01 .. Y-1-12-31
OOS test = Y-01-01 .. Y-12-31
```

Use actual available trading bars inside those calendar boundaries.

Primary OOS years:

```text
2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026(partial to 2026-09-04)
```

Example:

```text
2018 test -> train 2015-2017
2024 test -> train 2021-2023
2026 test -> train 2023-2025
```

Feature warm-up may use earlier bars, but training samples themselves must be inside the declared train interval.

### 8.2 Secondary robustness: rolling 5 calendar years

Use the same annual OOS protocol with:

```text
train = Y-5-01-01 .. Y-1-12-31
```

Start only where five full prior calendar years are available without inventing pre-listing history.

Use:

```text
2020 .. 2026(partial)
```

The 5Y path is a **predeclared robustness comparison**, not a parameter search. Do not choose 3Y or 5Y based on one favorable test segment.

## 9. Model fitting discipline

For every OOS year:

1. build training features only from the declared historical train interval;
2. purge any row whose `y20` target crosses the train/test boundary;
3. fit a fresh model using that training set only;
4. freeze the fitted model for the entire OOS calendar year;
5. produce one prediction after each OOS day's close when all features are available;
6. never refit using data from inside the same OOS year;
7. move to the next annual fold and repeat.

No expanding-window model unless separately reported as an informational extra; it is not the primary result.

## 10. Prediction → timing state

Use one fixed decision rule:

```text
LONG_STATE if predicted_y20 > 0
CASH_STATE otherwise
```

No threshold optimization.

No short selling.

Trading semantics:

```text
signal computed after t close
execution at next tradable bar
LONG target uses the same conservative capital convention:
gap_buffer = 1.20
100-share board lot
same commission/slippage assumptions as locked baseline
sell stamp duty disclosed consistently
```

Only trade on state/target transitions; do not submit redundant daily orders when target state is unchanged.

The ML research backtest must not call MiniQMT send/cancel APIs.

## 11. Required OOS evaluation windows

For the rolling-3Y challenger report at least:

```text
ALL_3Y    : 2018-01-01 .. 2026-09-04
RECENT_3Y : 2021-01-01 .. 2026-09-04
R4_3Y     : 2024-01-01 .. 2026-09-04
```

For the rolling-5Y challenger report at least:

```text
ALL_5Y    : 2020-01-01 .. 2026-09-04
RECENT_5Y : 2021-01-01 .. 2026-09-04
R4_5Y     : 2024-01-01 .. 2026-09-04
```

Each requested evaluation window must start from:

```text
1,000,000 equity
flat position
```

and use annual walk-forward models trained only on prior data.

This avoids inheriting hidden PnL/state from an earlier evaluation window.

## 12. Mandatory comparators

On each evaluation window compare, where date coverage permits:

```text
BH_100
BH_STATIC_CONSERVATIVE (~1/gap_buffer)
MA_FIXED (locked MA20/60/120)
ML_ROLLING_3Y
ML_ROLLING_5Y (for 2020+ windows)
```

Use the same start-anchor, primary MTM, optional terminal-liquidation, board-lot, commission/slippage and stamp-duty conventions already accepted.

Do not modify the baseline rules to make them more competitive.

## 13. Required performance metrics

For every comparator/window report:

```text
actual start/end
start_equity
period_count / years
final_equity
CAGR
annualized_volatility
Sharpe (rf=0)
MaxDD
Calmar
entries / exits
annualized_turnover
realized_stamp_duty
time_in_market
overall_avg_gross_exposure
```

For ML also report:

```text
number of annual model fits
number of OOS prediction days
LONG_STATE fraction
average deployed fraction while LONG
```

Keep optional terminal-liquidation metrics symmetric.

## 14. Exposure-normalized diagnostic

The accepted regime study left one non-blocking limitation: `BH_STATIC_CONSERVATIVE` matches the long-state sizing cap but not the ML/MA strategy's much lower realized average gross exposure caused by time in cash.

For each ML evaluation window, add a **diagnostic only** static comparator:

```text
BH_STATIC_MATCHED_AVG_EXPOSURE
```

Definition:

- after the ML path is computed, take its realized `overall_avg_gross_exposure`;
- run a static B&H path from the same start with target initial exposure equal to that fraction;
- residual stays cash;
- board-lot/cost-aware sizing;
- no rebalancing.

Clearly label this comparator **ex-post diagnostic / not a deployable benchmark**.

Purpose: help distinguish drawdown reduction from simply spending less time exposed to the stock.

Do not use this ex-post diagnostic to tune the ML model.

## 15. Prediction-quality diagnostics

Per annual OOS fold report at least:

```text
train sample count after purge
OOS prediction count
mean predicted y20
mean realized y20
Pearson correlation(prediction, realized y20)
sign accuracy: sign(prediction) == sign(realized y20)
LONG_STATE fraction
mean realized y20 when predicted > 0
mean realized y20 when predicted <= 0
spread between those two realized-return means
```

Also aggregate these diagnostics for:

```text
2018-2020
2021-2023
2024-2026
```

Forward labels overlap, therefore do **not** claim naive independent-sample statistical significance.

## 16. Required conclusions

The report must answer all of these explicitly.

### A. Does ML beat the locked fixed-MA baseline out of sample?

Use primarily:

```text
Sharpe
MaxDD
CAGR
Calmar
```

Do not declare a win based on one metric alone.

### B. Does rolling 3Y vs rolling 5Y materially change recent OOS behavior?

Choose one descriptive conclusion:

```text
3Y_BETTER_RECENTLY
5Y_BETTER_RECENTLY
SIMILAR
REGIME_DEPENDENT
INSUFFICIENT_EVIDENCE
```

This is not permission to tune between them after the fact.

### C. Does the ML model show positive directional separation in 2024-2026?

Compare mean realized `y20` for predicted LONG vs predicted CASH.

### D. Is any drawdown improvement still present after the ex-post average-exposure diagnostic?

State the limitation clearly.

## 17. Allowed files

Prefer keeping this challenger isolated from the locked baseline.

Allowed implementation files:

```text
scripts/midea_vnpy_alpha_lightgbm_challenger.py
src/trader/strategies/midea_timing/ml_research.py
tests/strategies/test_midea_vnpy_alpha_challenger.py
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER_20260908.md
```

If an official VeighNa Alpha configuration file is genuinely required, STOP and explain before modifying unrelated project files.

Do not modify existing locked baseline/review/report files.

## 18. Tests required

At minimum add deterministic tests for:

```text
[ ] feature at t does not depend on any close after t
[ ] y20 is exactly t+20
[ ] final 20 bars without targets are excluded
[ ] train rows stay inside declared training interval
[ ] training labels do not cross into OOS test interval
[ ] OOS rows are never present in training rows
[ ] annual model is fit only once per OOS year
[ ] 3Y train windows are exactly the declared prior 3 calendar years
[ ] 5Y train windows are exactly the declared prior 5 calendar years
[ ] LONG iff predicted_y20 > 0
[ ] no negative/short target state
[ ] execution is next-bar, not same-close
[ ] 100-share lot sizing/cost reserve remains valid
[ ] evaluation windows reset to 1,000,000 flat
[ ] exposure-matched diagnostic uses ML realized average gross exposure and does not feed back into model
[ ] locked MA parameters remain 20/60/120 and gap_buffer=1.20
[ ] existing QMT/read-only and locked-baseline tests still pass
```

Run:

```powershell
python -B -m unittest discover -s tests -t . -v
```

## 19. Reproducibility commands

If capability gate passes, the study should run from the existing environment without installs:

```powershell
python -B scripts\midea_vnpy_alpha_lightgbm_challenger.py --fetch --json work\midea_vnpy_alpha_lightgbm_summary.json
python -B scripts\midea_vnpy_alpha_lightgbm_challenger.py --csv work\midea_000333_daily_back.csv --json work\midea_vnpy_alpha_lightgbm_summary.json
```

`--fetch` and `--csv` must agree for the same cached market data.

## 20. Prohibited scope expansion

Do not:

- install/upgrade packages;
- use Qlib/RL/cvxportfolio/skfolio;
- optimize features;
- optimize LightGBM hyperparameters;
- optimize prediction threshold;
- change MA baseline parameters;
- add alternative datasets;
- add intraday execution;
- implement live send/cancel;
- change QmtGateway;
- modify MiniQMT configuration;
- modify VeighNa Studio.

## 21. Report

Write a new report:

```text
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER_20260908.md
```

Include:

1. capability-gate result with exact imports/versions/APIs;
2. changed files;
3. data source/date coverage;
4. frozen features/target/model config;
5. exact walk-forward train/test schedule and purge rule;
6. prediction diagnostics per annual fold and aggregate era;
7. full OOS performance comparison tables;
8. exposure-normalized diagnostic;
9. required A/B/C/D conclusions;
10. tests and commands/results;
11. limitations;
12. explicit live-trading side-effect statement.

If capability gate is BLOCKED, report only what was actually verified and do not fabricate model results.

## Definition of Done

```text
[ ] official VeighNa Alpha capability is actually used, or task is explicitly BLOCKED
[ ] no package installation/upgrade
[ ] frozen 10-feature set
[ ] y20 target only
[ ] boundary-purged walk-forward training
[ ] rolling-3Y annual OOS completed
[ ] rolling-5Y robustness OOS completed where coverage permits
[ ] common baseline comparisons completed
[ ] exposure-normalized diagnostic completed
[ ] prediction diagnostics completed
[ ] no look-ahead/data leakage
[ ] all tests pass
[ ] locked baselines unchanged
[ ] no live trading side effects
```
