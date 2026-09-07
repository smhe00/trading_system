# REVIEW — Midea A Historical Regime Study Fix

Date: 2026-09-08
Reviewed commit: `a63e6db49658773e3f92950c3b56780652528484`
Task: `interactive/TASK_MIDEA_A_HISTORY_REGIME_STUDY_FIX_20260908.md`
Prior review: `interactive/REVIEW_MIDEA_A_HISTORY_REGIME_STUDY_20260908.md`
Target: 美的集团 A股 `000333.SZ`
Nature: research/backtest only

## Verdict

**PASS**

The blocking forward-target regime-boundary contamination is fixed, the mandatory report fields are now present, the locked timing baseline remains unchanged, and no broker write path was introduced.

The historical-regime study is accepted as the current research basis for the next ML experiment.

## 1. Independent scope/diff audit

Compared Architect base `b54d50eb4a7d5f050cacfcdbcad51b1468d22a35` to Agent head `a63e6db49658773e3f92950c3b56780652528484`.

Only four authorized files changed:

```text
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_HISTORY_REGIME_STUDY_FIX_20260908.md
scripts/midea_history_regime_study.py
src/trader/strategies/midea_timing/research.py
tests/strategies/test_midea_history_regime.py
```

No changes were made to:

```text
scripts/midea_timing_backtest.py
src/trader/strategies/midea_timing/ma_regime.py
src/trader/gateways/qmt/**
MiniQMT configuration
VeighNa Studio
```

The accepted `MIDEA_A_TIMING_BASELINE_V1` therefore remains frozen.

## 2. Blocking boundary defect — fixed

The new helper:

```python
regime_contained_sample(dates, idx, horizon, start, end)
```

requires both:

```text
t   ∈ [start, end]
t+h ∈ [start, end]
```

before a forward R20/R60 observation is included in a regime bucket.

`forward_diagnostic()` applies this check separately for each regime and each horizon. A late-OLD state whose R20/R60 target falls in RECENT is excluded rather than labelled OLD.

This directly resolves the P0 defect in the prior review.

## 3. Tests reviewed

The new boundary tests cover:

- crossing a regime end → excluded;
- target exactly on the final included date → accepted;
- R20 and R60 boundary handling;
- OLD target cannot consume a RECENT date;
- end-to-end `forward_diagnostic()` containment with injected disjoint regimes;
- existing no-lookahead and tail-censoring tests remain present.

Agent reports:

```text
Ran 103 tests ... OK
```

No CI status is published for this commit, so this review relies on independent code/test inspection plus the reported local execution result; it does not claim an independent remote CI run.

## 4. Mandatory report completeness — fixed

The corrected report now includes the fields that were missing previously:

- actual start/end trading dates;
- start equity;
- period count / years;
- time in market;
- static conservative initial deployed fraction;
- MA average deployment while LONG;
- MA overall average gross exposure;
- LONG and CASH sample counts for both R20 and R60;
- median/Q25/Q75 for all five requested drift features.

The feature-drift quartiles now use one documented inclusive quantile convention.

## 5. Accepted research findings

### 5.1 Fixed MA rule is regime-dependent

Accepted label:

```text
REGIME_DEPENDENT
```

The fixed MA20/60/120 rule has materially different behavior across periods.

Most notably:

- R2 (2018–2020): MA improves Sharpe and MaxDD versus both B&H comparators.
- R4 (2024–2026): MA is clearly worse — CAGR `6.41%` vs BH100 `20.06%`, Sharpe `0.5763` vs `1.1022`, and MaxDD `19.20%` vs BH100 `13.42%`.

This is sufficient to reject treating the fixed MA rule as a stable cross-era timing edge.

### 5.2 Old vs recent forward-information sign flip survives the fix

After strict regime-contained censoring:

```text
OLD R20 mean spread    +1.65pp
OLD R60 mean spread    +0.41pp
RECENT R20 mean spread -1.26pp
RECENT R60 mean spread -2.97pp
```

Median spreads show the same broad old-positive / recent-negative direction.

This is descriptive evidence only because the forward windows overlap; no independent-sample significance claim is accepted.

### 5.3 Feature distribution shifted materially

The study shows substantial feature drift. The clearest example is 20D realized volatility, falling from roughly `28.5%` in R1/R2 to `15.1%` in R4. Price/MA and MA-ratio distributions also change sign/magnitude across eras.

Therefore full-history equal weighting is not a justified default for the next predictive model.

## 6. Accepted provisional ML-data recommendation

For the next ML stage, accept the study's provisional recommendation:

```text
ROLLING_3Y_TO_5Y_PRIMARY_WITH_OLD_HISTORY_FOR_ROBUSTNESS
```

Interpretation:

- recent rolling history is the primary training source;
- old history remains useful for robustness/regime-diversity testing;
- old and recent samples should not simply be pooled at equal weight by default;
- this study does **not** prove that 3 years or 5 years is the optimal window.

## 7. Residual methodological limitation — non-blocking

`BH_STATIC_CONSERVATIVE` matches the MA strategy's **long-state sizing cap** (~`1/gap_buffer ≈ 83%`), but it does not match MA's realized average gross exposure, which is much lower because MA spends substantial time in cash.

Examples from the study:

```text
R3 MA overall average gross exposure ≈ 24%
RECENT aggregate ≈ 37%
R4 ≈ 51%
```

Therefore the current comparator separates the `gap_buffer` effect from timing, but it does **not** fully decompose:

```text
predictive timing skill
vs
lower average market exposure caused by spending time in cash
```

Do not overstate causal attribution from the current drawdown comparison. This is not a blocker for the regime/data-window conclusion, but future strategy comparisons should disclose exposure-normalized results where practical.

## 8. Safety

Confirmed by diff inspection:

```text
QmtGateway write path unchanged
send_order/cancel_order not enabled
no live order/cancel code added
research/backtest only
```

## Gate decision

```text
MIDEA_A_TIMING_BASELINE_V1       PASS / LOCKED
MIDEA_A_HISTORY_REGIME_STUDY     PASS
QMT writable trading             NOT AUTHORIZED
```

The next authorized direction is a leakage-safe `vnpy.alpha` / LightGBM challenger, subject to local capability discovery and with no package installation or broker writes.
