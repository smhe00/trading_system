# REVIEW — Midea A Historical Regime / Old-vs-Recent Data Study

Date: 2026-09-08
Task: `interactive/TASK_MIDEA_A_HISTORY_REGIME_STUDY_20260907.md`
Reviewed Agent commit: `84cf2f6d820a91a8a3f2eb91b811eeb473687205`
Base task commit: `d11bc920202aad8f4e3ad7ad1c052454c1d975b5`
Verdict: **CHANGES_REQUIRED**

## 1. What passed independent review

The implementation respected the frozen-baseline boundary:

- only four authorized new files were added;
- `scripts/midea_timing_backtest.py` was not modified;
- `src/trader/strategies/midea_timing/ma_regime.py` was not modified;
- QmtGateway / broker write paths were not modified;
- the accepted MA20/60/120, `gap_buffer=1.20`, long-only, next-bar structure remains unchanged.

The following implementation choices are structurally sound:

- independent regime resets to 1,000,000 and flat;
- pre-regime bars are used only as warm-up;
- `BH_100`, `BH_STATIC_CONSERVATIVE`, and `MA_FIXED` are all present;
- static conservative B&H is cost-aware and non-rebalanced;
- MA daily position/exposure is reconstructed deterministically from trades;
- forward-return helper uses exact `t+h` close and excludes the global data tail;
- the report explicitly avoids naive significance claims on overlapping R20/R60 samples;
- no live trading side effects were introduced.

The Agent-reported `98/98` test result is credible from the inspected test set, but there is no GitHub CI status for this commit, so this review does not treat the local test report as independent CI evidence.

## 2. Blocking issue — cross-regime contamination in R20/R60 diagnostic

`forward_diagnostic()` currently assigns a sample to a regime solely from the **state date `t`**:

```python
if s <= date_str <= e:
    ... append forward_return(t, h)
```

The forward target date `t+h` is not required to remain inside the same requested regime.

Consequences:

- late-R1 R20/R60 samples can use R2 prices;
- late-R2 samples can use R3 prices;
- late-R3 samples can use R4 prices;
- most importantly, late-`OLD` samples can use `RECENT` prices.

That directly contaminates the study's core old-vs-recent inference. A sample labelled `OLD` must not use a target price from `RECENT` when we are claiming to compare signal relevance by era.

### Required correction

For each regime and horizon, include a sample only when **both** dates belong to that same requested interval:

```text
state date t      ∈ [regime_start, regime_end]
target date t+h   ∈ [regime_start, regime_end]
```

Since `t+h > t`, checking the target does not introduce look-ahead into the state calculation; it only defines the evaluation sample boundary.

Recompute all R20/R60 counts, conditional returns, spreads, and any conclusion that depends on them. Do not assume the current sign-flip conclusion remains unchanged until rerun.

## 3. Required report fields are incomplete

The task explicitly required the report to include, per regime/comparator:

- actual first/last trading dates;
- `start_equity`;
- `period_count / years`;
- `time_in_market`;
- actual initial deployed fraction for `BH_STATIC_CONSERVATIVE`.

The implementation appears to place several of these in JSON, but the submitted Markdown performance table does not report them. The task requires the report itself to carry them.

The forward diagnostic report also omits **R60 sample counts** in its compact table, even though sample count is mandatory for both horizons and both states.

The feature-drift table reports IQR brackets for 20D/60D return, but only medians for:

- 20D realized volatility;
- `close / MA120 - 1`;
- `MA20 / MA60 - 1`.

The task requires median **and IQR for all five features**.

These are reporting deficiencies rather than trading-safety defects, but they prevent acceptance of the research deliverable as specified.

## 4. P1 methodological cleanup — define IQR convention explicitly

The current feature-drift code derives Q25/Q75 using hand-picked sorted-array indices. For a research baseline, use one documented quantile convention consistently, for example pandas `.quantile(0.25/0.75)` or `statistics.quantiles(..., method="inclusive")`.

This is not expected to change the high-level conclusion materially, but it removes an avoidable ambiguity in the feature-drift evidence.

## 5. Acceptance conditions for the fix

The next submission must demonstrate all of the following:

```text
[ ] forward R20/R60 samples are censored when t+h leaves the evaluated regime
[ ] OLD forward targets never use RECENT dates
[ ] R1/R2/R3 forward targets never spill into the following regime
[ ] tests explicitly cover regime-end censoring for R20 and R60
[ ] R20/R60 tables are fully recomputed after censoring
[ ] conclusion label and old-data recommendation are re-evaluated from recomputed values
[ ] report includes actual start/end, start_equity, period_count/years, time_in_market
[ ] report includes BH_STATIC actual initial deployed fraction
[ ] report includes R20 and R60 sample counts for LONG and CASH
[ ] report includes median + Q25 + Q75/IQR for every requested drift feature
[ ] locked Midea baseline files remain unchanged
[ ] all existing tests, including QMT regressions, still pass
[ ] --csv and --fetch outputs agree
[ ] no live order/cancel capability is added
```

## 6. Gate decision

```text
MIDEA_A_HISTORY_REGIME_STUDY
→ CHANGES_REQUIRED
```

The performance/regime tables are useful provisional evidence, but the `OLD` vs `RECENT` forward-signal conclusion is **not accepted yet** because the current forward target construction crosses regime boundaries.
