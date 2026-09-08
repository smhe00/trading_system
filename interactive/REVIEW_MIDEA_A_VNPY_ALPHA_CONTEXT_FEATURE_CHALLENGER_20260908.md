# REVIEW — Midea A vnpy.alpha Context-Feature Challenger V2

Date: 2026-09-08
Architect review of Agent commit: `44847f286b14d467a46ca19d26514d7add4278b5`
Task: `interactive/TASK_MIDEA_A_VNPY_ALPHA_CONTEXT_FEATURE_CHALLENGER_20260908.md`
Verdict: **PASS**

## 1. Gate decision

`MIDEA_A_VNPY_ALPHA_CONTEXT_FEATURE_CHALLENGER_V2 = PASS / LOCKED`

The experiment answers the authorized narrow question without changing the locked V1 model/target/execution/walk-forward semantics. The accepted conclusion is:

```text
CONTEXT_FEATURES_HURT
```

The 7 predeclared volume/range/CSI300 context features do not add broad OOS value to the locked V1 price/volatility LightGBM challenger and materially increase trading activity/cost in several windows.

## 2. Independent scope audit

Compared base `a79d3e7b1fa5d6df4fda157ecfeb304caddc0ee2` to Agent head `44847f286b14d467a46ca19d26514d7add4278b5`.

Changed files are exactly the four authorized new files:

```text
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_VNPY_ALPHA_CONTEXT_FEATURE_CHALLENGER_20260908.md
scripts/midea_vnpy_alpha_context_challenger.py
src/trader/strategies/midea_timing/ml_context_research.py
tests/strategies/test_midea_vnpy_alpha_context_challenger.py
```

No locked V1 challenger file, MA baseline, history-study file, QmtGateway file, Studio file, or dependency declaration was modified.

## 3. Implementation checks

### 3.1 Feature set

V2 is exactly V1's locked 10 features plus the 7 authorized additions:

```text
volume_ratio20
range_20
mkt_ret20
mkt_ret60
mkt_vol20
rel_ret20
rel_ret60
```

The implementation uses trailing/lagged Polars expressions only. The test suite explicitly checks exact feature names, trailing volume/range semantics, exact 20/60-bar market-return horizons, relative-return definitions, and invariance to data strictly after `t`.

### 3.2 Market data alignment

`000300.SH` is sourced from local XtQuant, with stock tradable dates as the master and exact-date lookup only. No forward/back fill is used. For the actual study dataset the report records `excluded_rows=0`, so the CSI300 series covers every retained Midea observation used by V2.

### 3.3 Official VeighNa Alpha path

V2 continues to use the official installed workflow:

```text
AlphaDataset
Segment
LgbModel
AlphaLab
```

The accepted V1 chronological simulator, fold schedule, segment-aware label purge, and metrics helpers are imported and reused rather than forked.

### 3.4 Leakage / boundary controls

The V2 fold runner preserves:

```text
FIT y20 target <= fit_end
VALID y20 target <= valid_end
fit/valid non-overlap
annual OOS model freeze
```

Era diagnostics use strict containment: both prediction date `t` and target date `t+20` must remain inside the same 2018-2020 / 2021-2023 / 2024-2026 era.

### 3.5 Execution identity

The V2 script imports the already accepted `simulate_ml` object from the locked V1 helper. The context test suite checks object identity, so this experiment did not introduce another execution simulator.

## 4. V1 control reproduction

The Agent reran V1 through the locked `run_fold`. The six evaluation-window V1 metrics match the accepted timeline-fixed V1 results to the reported tolerance (`<=1e-4`). Key values such as ALL_3Y final equity `1,123,537`, CAGR `1.36%`, Sharpe `0.166`, MaxDD `43.6%` match the locked accepted result.

This is sufficient to treat V1 as a valid internal control for the V2 ablation.

## 5. Accepted results

### V2 versus V1

Across the six predeclared windows, V2 has lower CAGR in 5/6 and lower Sharpe in 5/6. Examples:

```text
ALL_3Y:    CAGR 1.36% -> 0.08%, Sharpe 0.166 -> 0.100, MaxDD 43.6% -> 51.8%
RECENT_3Y: CAGR -5.67% -> -6.63%, Sharpe -0.325 -> -0.366, MaxDD 41.6% -> 50.2%
R4_5Y:     CAGR 15.30% -> 11.68%, Sharpe 1.050 -> 0.820, MaxDD 11.6% -> 18.9%
```

Turnover also rises materially in several windows, for example R4_3Y `0.91 -> 10.52` and R4_5Y `5.80 -> 11.96` annualized turnover units under the study convention.

Therefore the formal experiment-level conclusion is **CONTEXT_FEATURES_HURT**, not merely `NO_CLEAR_VALUE`.

### 2024-2026 directional diagnostic

Strict-contained V2 diagnostics show:

```text
3Y: corr +0.014, LONG-CASH spread +1.35pp
5Y: corr +0.290, LONG-CASH spread +0.70pp
```

The 5Y correlation is directionally interesting, but the economic spread is small, the 3Y correlation is approximately zero, labels overlap, and trading results do not improve. The correct conclusion remains **NO reliable positive directional separation**.

### V2 versus MA / exposure matched control

V2 does not broadly beat the locked MA baseline. The ex-post average-exposure diagnostic also removes any apparent drawdown story: V2 MaxDD is worse than its matched static control in 5/6 windows and approximately flat in the remaining one.

## 6. Tests / reproducibility

Agent reports:

```text
146/146 tests PASS
--fetch and cached --csv-stock/--csv-market outputs MD5-identical
no package mutation
zero broker write side effects
```

I independently reviewed the new tests. They materially exercise the task's required properties rather than only asserting output existence.

## 7. Residual limitations — accepted, non-blocking

1. Forward `y20` samples overlap; prediction correlations/spreads are descriptive, not independent-sample significance tests.
2. The current actual CSI300 join has zero missing rows. The helper drops a stock row before rolling/shift expressions if a future dataset ever has a missing market date. With nonzero join loss, that would compress the observation grid and could change exact-horizon feature/label semantics around the gap. This does **not** affect the accepted V2 numbers because `excluded_rows=0`, but any future generic multi-context pipeline must preserve the full stock timeline and mask the affected feature row rather than silently alter horizons.
3. Existing environment health warning remains: installed `peewee 3.17.3` is below the declared `>=3.17.9` requirement of vnpy-sqlite/mysql/postgresql. No failure is observed in this task and no dependency mutation is authorized here.
4. Results are specific to Midea, the frozen y20 target, fixed LightGBM mapping, and the predeclared context set. They do not prove that all market/sector/fundamental context is useless.

## 8. Architectural consequence

Do **not** continue stacking more price/volume/index technical features or tune LightGBM to rescue V2. Two successive frozen ML challengers have now failed to establish robust OOS alpha:

```text
V1 price/vol only          -> no win
V2 + volume/CSI300 context -> worse
```

The next useful gate is data capability for genuinely different information: point-in-time fundamentals / valuation. Before any fundamental ML challenger, the project must prove that locally available data has reliable publication timestamps and can be mapped to trading dates without report-date look-ahead.

## 9. Safety

```text
QmtGateway write path = NOT AUTHORIZED
live trading = NONE
research/backtest only
```
