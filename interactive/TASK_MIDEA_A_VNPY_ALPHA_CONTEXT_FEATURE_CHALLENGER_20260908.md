# TASK: Midea A — vnpy.alpha Context-Feature Challenger V2

Date: 2026-09-08
Based on accepted review: `interactive/REVIEW_MIDEA_A_VNPY_ALPHA_EXECUTION_TIMELINE_FIX_20260908.md`
State: **AUTHORIZED**
Target: 美的集团 A股 `000333.SZ`
Nature: **research/backtest only**

## 1. Goal

The first locked vnpy.alpha / LightGBM challenger is now accepted and shows:

```text
price/volatility-only ML does NOT beat locked MA OOS
5Y_BETTER_RECENTLY (descriptive)
2024-2026 directional separation not demonstrated
exposure-normalized drawdown edge not demonstrated
```

The next experiment must answer one narrow question:

> Does adding simple, predeclared market-context and volume/range information materially improve the same leakage-safe vnpy.alpha / LightGBM timing workflow?

This is a **feature-set ablation/challenger**, not a hyperparameter, threshold, target, execution, or train-window optimization task.

## 2. Locked V1 artifacts / semantics

Do not modify the accepted V1 challenger files:

```text
src/trader/strategies/midea_timing/ml_research.py
scripts/midea_vnpy_alpha_lightgbm_challenger.py
tests/strategies/test_midea_vnpy_alpha_challenger.py
```

Also keep locked:

```text
scripts/midea_timing_backtest.py
src/trader/strategies/midea_timing/ma_regime.py
scripts/midea_history_regime_study.py
src/trader/gateways/qmt/**
```

Reuse their accepted helpers/imports where practical rather than copying execution logic.

The following remain frozen exactly:

```text
target: y20[t] = close[t+20]/close[t]-1
model family: official vnpy.alpha LgbModel / LightGBM regression
LightGBM fixed configuration / nearest official wrapper mapping
LONG iff predicted_y20 > 0
3Y annual walk-forward schedule
5Y annual walk-forward robustness schedule
non-overlapping fit / valid split
segment-aware FIT/VALID label containment
strict chronological pending-order simulator
signal-close × 1.20 sizing
buy limit = signal_close × 1.15
sell limit = signal_close × 0.85
100-share lot
commission/slippage/stamp conventions
long-only
1,000,000 start equity per evaluation window
```

Do not tune any of these.

## 3. Data — local MiniQMT only

Use only local MiniQMT / XtQuant daily data.

Required symbols:

```text
stock  : 000333.SZ
market : 000300.SH   # CSI 300
```

Adjustment convention:

```text
stock  : same back-adjusted convention as locked baseline
market : same compatible adjusted/index-close convention returned by XtQuant
```

Use the existing isolated data-worker pattern so XtQuant native DLLs do not coexist with LightGBM in the training process.

Do not install external datasets or use web data.

If `000300.SH` is unavailable from the local XtQuant environment, write a **BLOCKED** report with the exact failure. Do not silently substitute another benchmark.

Alignment rule:

- stock tradable dates remain the master observation dates;
- join CSI300 data by exact trading date;
- do not forward-fill or back-fill missing market observations;
- if an exact-date market row is missing, exclude that feature row and report the count/date range;
- suspended/zero-volume stock days remain excluded exactly as in the locked baseline.

## 4. Feature sets

### 4.1 V1 control — locked 10 features

Rerun the accepted V1 feature set unchanged:

```text
ret_5
ret_20
ret_60
vol_20
vol_60
close_ma20
close_ma60
close_ma120
ma20_ma60
ma60_ma120
```

This is the internal control for the experiment.

The rerun V1 metrics/predictions must reproduce the accepted V1 challenger result to normal deterministic/rounding tolerance. If not, STOP and report the mismatch before interpreting V2.

### 4.2 V2 contextual feature set

V2 = all 10 V1 features plus exactly these **7 predeclared features**:

```text
volume_ratio20
    = volume[t] / MA20(volume)[t] - 1

range_20
    = mean((high-low)/close, trailing 20 bars)

mkt_ret20
    = CSI300_close[t] / CSI300_close[t-20] - 1

mkt_ret60
    = CSI300_close[t] / CSI300_close[t-60] - 1

mkt_vol20
    = annualized std of trailing 20 CSI300 daily returns

rel_ret20
    = stock ret_20 - mkt_ret20

rel_ret60
    = stock ret_60 - mkt_ret60
```

No other new features.

Do not add:

- valuation/fundamental data;
- northbound flow;
- sentiment/news;
- industry index;
- alternate market indices;
- amount/turnover-rate fields requiring new reference data;
- feature selection/pruning;
- nonlinear hand-designed thresholds.

All V2 features at `t` must use data available through `t` close only.

## 5. Official vnpy.alpha requirement

The V2 path must continue to use the official installed VeighNa Alpha workflow:

```text
AlphaDataset
Segment
LgbModel
AlphaLab
```

LightGBM remains only the estimator beneath the official vnpy.alpha workflow.

Do not replace this with Qlib, sklearn-only, or a home-grown training framework.

No package installation/upgrades/downgrades in this task.

## 6. Experimental design

Train and evaluate **both V1 and V2** using identical folds and identical execution semantics.

Required annual OOS folds remain:

```text
3Y declared history: OOS 2018..2026(partial)
5Y declared history: OOS 2020..2026(partial)
```

Use the same accepted deterministic fit/valid split inside each declared history window and the same segment-aware y20 containment.

For each `(feature_set, train_window, OOS_year)` fit one fresh model and freeze it for that OOS year.

Do not choose years, features, thresholds, or train windows after seeing results.

## 7. Prediction-quality diagnostics

For V1 and V2, report per fold:

```text
fit_count_after_purge
valid_count_after_purge
OOS prediction count
mean predicted y20
mean realized y20
Pearson corr(pred, realized)
sign accuracy
LONG_STATE fraction
mean realized y20 | pred>0
mean realized y20 | pred<=0
LONG-CASH realized-return spread
```

For aggregate era diagnostics use strict target containment:

```text
2018-2020
2021-2023
2024-2026
```

A sample belongs to an era only if **both**:

```text
prediction date t is inside the era
realized target date t+20 is also inside the same era
```

This avoids the residual era-boundary limitation recorded in the V1 PASS review.

Forward-label samples overlap; do not claim naive independent-sample significance.

## 8. OOS trading evaluation

For each V1/V2 3Y and 5Y prediction path, use the accepted simulator unchanged.

Required windows:

```text
ALL_3Y    2018-01-01..2026-09-04
RECENT_3Y 2021-01-01..2026-09-04
R4_3Y     2024-01-01..2026-09-04

ALL_5Y    2020-01-01..2026-09-04
RECENT_5Y 2021-01-01..2026-09-04
R4_5Y     2024-01-01..2026-09-04
```

Every evaluation window resets to 1,000,000 and flat.

Report for V1 and V2:

```text
final_equity
CAGR
annualized_volatility
Sharpe
MaxDD
Calmar
entries / exits
annualized_turnover
realized_stamp_duty
time_in_market
overall_avg_gross_exposure
```

Also retain mandatory comparators:

```text
BH_100
BH_STATIC_CONSERVATIVE
MA_FIXED
BH_STATIC_MATCHED_AVG_EXPOSURE (ex-post diagnostic, separately for V1 and V2 if exposure differs)
```

## 9. Mandatory V2-vs-V1 deltas

For every requested evaluation window report:

```text
V2 - V1 CAGR
V2 - V1 Sharpe
V2 - V1 MaxDD
V2 - V1 Calmar
V2 - V1 turnover
V2 - V1 average gross exposure
```

Also report V2 vs locked MA for the same four primary performance metrics.

## 10. Required conclusions

### A. Do contextual features add OOS value versus the locked V1 feature set?

Choose exactly one:

```text
CONTEXT_FEATURES_HELP
CONTEXT_FEATURES_HURT
REGIME_DEPENDENT
NO_CLEAR_VALUE
```

Do not call it a win based only on R4 or only on one metric.

A `CONTEXT_FEATURES_HELP` conclusion requires broad support across the main/recent OOS views, especially Sharpe/CAGR, without a material deterioration in MaxDD.

### B. Does V2 show positive directional separation in 2024-2026 under strict era-contained y20 targets?

Answer YES/NO from correlation and LONG-CASH realized-return spread for both 3Y and 5Y paths.

### C. Does V2 improve on the locked MA baseline?

Use CAGR/Sharpe/MaxDD/Calmar across the predeclared windows. Do not declare a general win from one favorable subperiod.

### D. Is any drawdown improvement still present after exposure matching?

Use the same ex-post diagnostic method and disclose its limitation.

## 11. Tests required

At minimum add deterministic tests for:

```text
[ ] exact-date stock/CSI300 join; no forward/back fill
[ ] missing market date excludes row
[ ] each V2 feature at t is invariant to stock/market prices after t
[ ] volume_ratio20 uses trailing data only
[ ] range_20 uses trailing OHLC only
[ ] mkt_ret20/mkt_ret60 exact horizons
[ ] rel_ret20/rel_ret60 definitions are exact
[ ] V1 feature names remain exactly the accepted 10
[ ] V2 feature names are V1 + exactly the 7 declared additions
[ ] target remains exact y20
[ ] FIT label target <= fit_end
[ ] VALID label target <= valid_end
[ ] era diagnostics require both t and t+20 inside era
[ ] execution uses the imported accepted chronological simulator, not a forked variant
[ ] evaluation windows reset to 1M flat
[ ] locked MA parameters remain 20/60/120 and gap_buffer=1.20
[ ] existing QMT/read-only/baseline/V1 challenger tests still pass
```

Run:

```powershell
python -B -m unittest discover -s tests -t . -v
```

## 12. Reproducibility

Suggested commands:

```powershell
python -B scripts\midea_vnpy_alpha_context_challenger.py --fetch --json work\midea_vnpy_alpha_context_summary.json
python -B scripts\midea_vnpy_alpha_context_challenger.py --csv-stock work\midea_000333_daily_back.csv --csv-market work\csi300_000300_daily.csv --json work\midea_vnpy_alpha_context_summary.json
```

Repeated cached-data runs must be deterministic.

## 13. Allowed files

```text
scripts/midea_vnpy_alpha_context_challenger.py
src/trader/strategies/midea_timing/ml_context_research.py
tests/strategies/test_midea_vnpy_alpha_context_challenger.py
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_VNPY_ALPHA_CONTEXT_FEATURE_CHALLENGER_20260908.md
```

Generated CSV/JSON/AlphaLab artifacts remain under `work/` and must not be committed.

Do not modify V1 challenger files to implement V2.

## 14. Environment health

Run `python -m pip check` as diagnostic only and report the existing peewee conflict if still present.

Do not mutate packages in this task.

## 15. Prohibited scope expansion

Do not:

- tune LightGBM hyperparameters;
- tune LONG threshold;
- tune 3Y/5Y windows;
- add/remove V2 features after seeing results;
- change y20 target;
- add another model family;
- add Qlib/RL;
- add external/fundamental/news data;
- change execution semantics;
- change QmtGateway;
- enable live send/cancel;
- install/upgrade/downgrade packages.

## 16. Report

Write a new report:

```text
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_VNPY_ALPHA_CONTEXT_FEATURE_CHALLENGER_20260908.md
```

Include:

1. exact changed files;
2. capability/data availability result for `000300.SH`;
3. stock/market date coverage and join losses;
4. exact V1/V2 feature definitions;
5. exact folds and label-containment evidence;
6. V1 reproduction check against locked V1;
7. per-fold prediction diagnostics V1 vs V2;
8. strict era-contained aggregate diagnostics;
9. full OOS performance tables;
10. V2-V1 and V2-MA deltas;
11. exposure-matched diagnostics;
12. required A/B/C/D conclusions;
13. tests/reproducibility;
14. environment-health disclosure;
15. explicit zero-live-trading side-effect statement.

## Definition of Done

```text
[ ] V1 rerun reproduces locked challenger
[ ] V2 uses exactly 17 frozen features (10+7)
[ ] CSI300 exact-date context is local-XtQuant sourced
[ ] no market-data fill or future leakage
[ ] official vnpy.alpha workflow remains in use
[ ] 3Y/5Y walks remain frozen and label-clean
[ ] accepted chronological simulator is reused
[ ] strict era-contained diagnostics are complete
[ ] all requested OOS comparisons are recomputed
[ ] A/B/C/D conclusions are explicit and non-cherry-picked
[ ] all tests pass
[ ] no dependency mutation
[ ] no live trading side effects
```
