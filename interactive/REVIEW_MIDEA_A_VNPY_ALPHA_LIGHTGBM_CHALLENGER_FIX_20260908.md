# REVIEW: Midea A — vnpy.alpha / LightGBM Challenger Fix

Date: 2026-09-08
Reviewed commit: `ad86a0079229bda40c88f9cc1032b0c7827efa33`
Prior task: `interactive/TASK_MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER_FIX_20260908.md`
Verdict: **CHANGES_REQUIRED**

## 1. Scope / repository audit

The Agent changed only the expected challenger research files and added a new report. The locked deterministic baseline and QmtGateway remain unchanged in this commit. The previous requested fixes are partially implemented:

- initial LONG is now actionable;
- sizing uses signal-close × `gap_buffer=1.20` instead of next-open;
- fit/valid row ranges are calendar-disjoint;
- full test suite is reported as 122/122 PASS.

These are real improvements. However, the ML execution simulator still contains a blocking time-accounting defect that invalidates the recomputed equity curves and therefore all reported challenger performance metrics.

## 2. P0 — next-bar fill is applied backward to the signal-day equity

Current `simulate_ml()` processes a state transition while iterating signal bar `b=t`, inspects `window[i+1]`, executes the trade using the next bar, mutates `cash`/`pos`, and only then appends:

```python
rows.append((date_str, cash + pos * b.close_price))
```

Therefore a trade whose recorded execution date is `t+1` already changes the equity recorded for date `t`.

Example:

```text
t close: LONG signal
      -> simulator looks at t+1 open/low
      -> cash/position are changed immediately
      -> row for t close is then valued with the post-t+1 position
```

This is a backwards time shift and also uses t+1 execution information in the t equity row. It can materially change daily returns, Sharpe, MaxDD, CAGR, time-in-market and average gross exposure.

### Required invariant

The simulator must be chronological:

```text
start of bar t:
    process only orders pending from t-1
    fill/cancel against bar t

close of bar t:
    mark equity using state actually held at t close
    compute signal from information through t close
    create pending order for t+1
```

For an initial LONG signal on the first evaluation bar:

```text
first close equity = 1,000,000 (still flat)
entry executes no earlier than the next tradable bar
```

Add a deterministic test that asserts the signal-day equity is unchanged by a next-day fill.

## 3. P0 — no-fill transition can permanently suppress the intended entry

Current code sets:

```python
prev_state = state
```

even when a LONG transition produced a limit order that did **not** fill because the next bar remained above the buy limit.

Result:

```text
state becomes LONG
order does not fill
position remains 0
prev_state becomes LONG
subsequent LONG days generate no new action
```

The desired portfolio state is LONG but the simulator can remain flat indefinitely until the signal first turns CASH and later back to LONG.

This is not an acceptable target-state execution model and is not equivalent to a persistent/retried limit order.

### Required behavior

A failed transition order must not be treated as a completed state transition. Implement one explicit deterministic policy, preferably:

- maintain a single pending order until it fills or the desired state changes; or
- cancel/reissue deterministically while target state remains unmet.

Do not create multiple simultaneous duplicate orders. Add tests for:

1. LONG target + first next bar no-fill + later bar fill;
2. LONG target cancelled because state returns to CASH before fill;
3. no duplicate stacked entry orders.

## 4. P1 — exit execution is still not symmetric with the locked MA limit semantics

Entry was changed to a next-bar limit-crossing model, but exit still sells unconditionally at `next.open_price`.

The locked MA baseline submits a wide sell limit around `signal_close × 0.85`. In a severe gap-down / limit-down style bar, unconditional next-open liquidation is not equivalent.

For the challenger to claim identical execution conventions, use a symmetric deterministic sell-limit crossing rule:

```text
sell limit = signal_close × 0.85
fill on a later bar only if bar.high >= sell_limit
fill price = max(bar.open, sell_limit)
```

or document and justify another exact vn.py-compatible rule. The order must remain pending or be deterministically reissued if it does not fill.

## 5. P1 — fit/valid rows are disjoint, but fit labels can still consume validation-period prices

The new calendar split is:

```text
fit   = declared train window except last calendar year
valid = last calendar year
```

but the single `BoundaryPurgeProcessor` is configured with:

```python
train_end = declared_train_end
```

for both fit and validation segments.

That means a late-fit sample may have its `y20` target inside the validation year. The fit and validation **rows** are disjoint, but the validation period is not fully untouched by model fitting because validation-period prices can enter fit labels.

This is not OOS test leakage, but it weakens the claimed clean early-stopping validation.

### Required fix

Use segment-aware label containment:

```text
fit row:   t+20 target must be <= fit_end
valid row: t+20 target must be <= valid_end and remain before OOS
```

Add direct tests for both boundaries.

## 6. Environment/process note — do not make further package mutations in this fix

The report states that a prior user-authorized unblock installed `polars`, `lightgbm`, `alphalens-reloaded`, `pyarrow`, and that the resulting environment currently has `peewee 3.17.3` while vnpy database plugins declare `>=3.17.9`.

This review does not attempt to reverse or alter that environment. For this fix:

- do not install/upgrade/downgrade packages;
- report the current `pip check` result if available;
- preserve the working Alpha environment;
- any dependency repair requires a separate explicit authorization/task.

## 7. Numerical conclusions remain provisional

Because the current equity path applies future fills to prior-day equity, the following reported results are **not accepted yet**:

```text
ML does not beat MA
5Y_BETTER_RECENTLY
2024-2026 has no directional separation
exposure-matched drawdown conclusion
```

The prediction-quality diagnostics that depend only on model predictions and realized y20 are less affected by the execution-timeline bug, but the performance and exposure conclusions must be recomputed after the simulator is corrected.

## 8. Gate

```text
MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER
→ CHANGES_REQUIRED
```

Do not proceed to feature expansion, threshold tuning, additional models, Qlib, RL, or live execution until this challenger has a chronologically correct and internally consistent OOS execution path.
