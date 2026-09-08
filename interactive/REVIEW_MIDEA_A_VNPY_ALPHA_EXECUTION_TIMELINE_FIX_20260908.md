# REVIEW — Midea A vnpy.alpha Challenger Execution Timeline Fix

Date: 2026-09-08
Reviewed implementation commit: `06e0fa91984d7be56f0a2925446e6e0a4279a681`
Based on task: `interactive/TASK_MIDEA_A_VNPY_ALPHA_EXECUTION_TIMELINE_FIX_20260908.md`
Verdict: **PASS**
Nature: research/backtest only

## 1. Scope / diff audit

Compared against Architect task commit `7eda588c32e421c49fd971ca89f262addb47167d`.

Changed files are confined to the authorized challenger scope:

```text
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_VNPY_ALPHA_EXECUTION_TIMELINE_FIX_20260908.md
scripts/midea_vnpy_alpha_lightgbm_challenger.py
src/trader/strategies/midea_timing/ml_research.py
tests/strategies/test_midea_vnpy_alpha_challenger.py
```

Locked artifacts remain unchanged:

```text
scripts/midea_timing_backtest.py
src/trader/strategies/midea_timing/ma_regime.py
scripts/midea_history_regime_study.py
src/trader/gateways/qmt/**
```

No package mutation was made in this fix task. No live QMT send/cancel path was enabled.

## 2. P0 execution timeline — PASS

The simulator is now strictly chronological per bar:

```text
A. process only a previously pending order on the current bar
B. mark current-bar close equity using the actually held position
C. after close, read the current prediction and create/cancel a pending order
```

This removes the prior look-ahead defect where bar `t+1` execution changed bar `t` equity.

Independent code review confirms:

- cash/position mutate only while processing a pending order on the current bar;
- equity is appended only after current-bar execution state is settled;
- current close prediction is consumed only after the close-equity row is written;
- a first-bar LONG signal cannot fill before the next tradable bar.

Verdict: **PASS**.

## 3. P0 pending/no-fill state machine — PASS

The implementation now maintains a single explicit pending order.

Verified behavior:

- pending BUY persists after a no-fill while target remains LONG;
- pending BUY is cancelled if desired state returns to CASH before fill;
- pending SELL persists after a no-fill while target remains CASH;
- pending SELL is cancelled if desired state returns to LONG before fill;
- duplicate entry/exit orders are not stacked;
- buy sizing remains based on signal-close `× gap_buffer=1.20`, not future open;
- buy crossing: `low <= limit`, fill at `min(open, limit)`;
- sell crossing: `high >= limit`, fill at `max(open, limit)`;
- trade date is the actual crossing/fill bar;
- modeled buy fills retain non-negative cash under the conservative sizing rule.

This matches the deterministic execution semantics required by the task.

Verdict: **PASS**.

## 4. P1 fit/validation label containment — PASS

`BoundaryPurgeProcessor` is now segment-aware:

```text
FIT   row: t+20 target date <= fit_end
VALID row: t+20 target date <= valid_end
```

Independent review confirms this prevents:

- VALID-period prices entering FIT labels;
- OOS-period prices entering VALID labels.

The implementation also reports per fold:

```text
fit_range
valid_range
test_range
train_count_after_purge
valid_count_after_purge
max_fit_label_target_date
max_valid_label_target_date
```

The reported 3Y folds all satisfy the corresponding containment upper bounds.

Verdict: **PASS**.

## 5. Test / reproducibility evidence

Agent reports:

```text
python -B -m unittest discover -s tests -t . -v
Ran 132 tests ... OK
```

The newly added tests cover the specific execution defects that blocked the previous gate, including signal-day equity isolation, initial LONG timing, persistent no-fill, cancellation, duplicate-order prevention, sell-limit persistence/crossing, trade dates, cash non-negativity, and segment-aware label purge.

Agent also reports deterministic agreement across repeated `--csv` runs and `--fetch` output (MD5 identical).

No repository CI status is present for this commit, so PASS is based on independent code/diff review plus the submitted local test evidence.

## 6. Accepted challenger result

With the execution and validation defects corrected, the vnpy.alpha / LightGBM challenger result is accepted as the first locked ML baseline for `000333.SZ`.

### A. Does ML beat the locked fixed-MA baseline OOS?

**NO.**

Primary `ALL_3Y`:

```text
ML - MA:
CAGR   -2.51 pp
Sharpe -0.159
MaxDD  +12.2 pp   (worse)
Calmar -0.092
```

`RECENT_3Y` is also worse. The 5Y variants improve materially, and `R4_5Y` is strong, but one favorable subwindow is insufficient to declare a general challenger win.

### B. 3Y vs 5Y

Accepted descriptive result:

```text
5Y_BETTER_RECENTLY
```

This is an observed robustness result, not authorization to optimize the train window post hoc.

### C. Directional separation in 2024-2026

Accepted result: **no reliable positive separation**.

Reported aggregate diagnostics remain near zero:

```text
pred3 corr   ≈ -0.052
pred5 corr   ≈ +0.042
LONG-CASH spread ≈ +0.24 pp / +0.88 pp
```

The fixed price/volatility-only feature set therefore does not demonstrate a stable recent y20 directional edge.

### D. Exposure-normalized drawdown

Accepted result: **no robust ML drawdown edge**.

Against the ex-post static comparator initialized to the ML average-exposure fraction, ML MaxDD is worse in all six requested windows. The apparent R4 drawdown advantage versus MA is therefore largely attributable to lower realized exposure rather than superior timing.

## 7. Residual limitations / follow-up notes

Non-blocking limitations retained:

1. `y20` diagnostic samples overlap; no naive independent-sample significance claim is valid.
2. Current feature set is deliberately narrow: price/volatility only.
3. The official LgbModel workflow uses a declared 3Y/5Y history split into non-overlapping fit + final-year validation; this should remain explicit when interpreting `3Y`/`5Y` labels.
4. Era aggregate diagnostics group by prediction date; a late-era `y20` realized target can fall just beyond an era boundary. This does not leak into model fitting or trading, but future research comparing era-level predictive information should use regime-contained diagnostic targets for strict comparability.
5. `pip check` still reports `peewee 3.17.3` versus `vnpy-sqlite/mysql/postgresql >=3.17.9`. Current tests pass, but dependency health should be repaired before treating the environment as production-ready.

## 8. Gate decision

```text
MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER_V1 = PASS / LOCKED
execution timeline                        = PASS
pending/no-fill semantics                 = PASS
fit/valid label containment               = PASS
vnpy.alpha official workflow              = ACCEPTED
ML beats MA baseline                       = NO
5Y vs 3Y recent behavior                   = 5Y_BETTER_RECENTLY
2024-2026 directional separation           = NOT DEMONSTRATED
live trading authorization                 = NONE
```

The numerical challenger result is no longer provisional.
