# REVIEW: Midea A — vnpy.alpha / LightGBM Walk-Forward Challenger

Date: 2026-09-08
Reviewed commit: `fcd062bc840fc3de706fe108756ff08feaa0dc25`
Task: `interactive/TASK_MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER_20260908.md`
Verdict: **CHANGES_REQUIRED**
Nature: research/backtest only

## 1. Scope / safety audit

The implementation commit changes only the four task-scoped files:

```text
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER_20260908.md
scripts/midea_vnpy_alpha_lightgbm_challenger.py
src/trader/strategies/midea_timing/ml_research.py
tests/strategies/test_midea_vnpy_alpha_challenger.py
```

Locked MA baseline and QmtGateway files were not modified in this commit. No live send/cancel path was added.

The report states that optional vnpy.alpha/LightGBM dependencies were installed into `.venv` after explicit user authorization. This review does not treat those environment changes as a code-gate failure, but the exact installed versions/conflicts must remain disclosed.

## 2. What is good

The implementation genuinely uses official VeighNa Alpha (`AlphaDataset`, `LgbModel`, `AlphaLab`) rather than bypassing it. The frozen 10-feature set and `y20` label are backward-looking / forward-targeted as intended, and the boundary purge uses an explicit target-date map so training labels do not cross the OOS boundary. Annual 3Y/5Y fold schedules are fixed before result inspection. The implementation also isolates XtQuant data fetching from LightGBM in a child process after observing a native-DLL conflict.

These parts are directionally correct.

## 3. Blocking findings

### P0 — Initial OOS LONG state is silently ignored

`simulate_ml()` initializes:

```python
prev_state = None
```

and only trades when:

```python
if prev_state is not None and state != prev_state:
```

Therefore if an evaluation window starts flat and the first available ML state is `LONG`, no order is created. If the signal stays LONG for weeks/months, the strategy remains incorrectly flat until a later CASH→LONG transition.

This violates the task requirement that every evaluation window starts flat and then follows `LONG iff predicted_y20 > 0` with next-bar execution. It can materially change CAGR, drawdown, exposure, turnover, and all comparator deltas.

The existing unit test masks this defect:

```python
self.assertLessEqual(len(longs), 1)
```

for an initially LONG sequence. The correct behavior must be tested as exactly one next-bar entry.

### P0 — ML sizing does not use the locked `gap_buffer=1.20` conservative-capital convention

The task requires ML LONG targets to use the same conservative capital convention as the locked MA baseline. But `simulate_ml()` sizes directly from the *next bar actual open*:

```python
target = size_board_lots(cash, nxt.open_price, ...)
```

`GAP_BUFFER` is never used in the ML simulator. This makes the ML path close to fully invested when LONG instead of the locked baseline's approximately 1/1.20 capital cap before lot rounding, and it uses the realized next-open price to determine share quantity after the signal day.

That breaks the intended apples-to-apples comparison and contaminates the exposure-normalized diagnostic.

The ML simulator must make the position-size decision from information available on the signal bar, using the same conservative reserve rule as the locked MA baseline. At minimum, sizing must use signal-close × `gap_buffer` plus buy costs; preferably also mirror the locked next-bar limit/fill convention so a gap beyond the allowed buy limit is not treated as an automatic fill.

### P1 — Early-stopping validation overlaps the model TRAIN segment

`fold_schedule()` declares:

```text
TRAIN = full prior 3Y/5Y interval
VALID = last calendar year of that same TRAIN interval
```

and `AlphaDataset` is constructed with both ranges. The report also uses `early_stopping_rounds=50`.

Thus the same last-year observations appear in the TRAIN interval and validation interval unless the official wrapper internally removes overlap (the implementation does not demonstrate that). This does not leak the OOS year, but it makes early-stopping validation non-independent and weakens the claimed clean walk-forward protocol.

Because the task predeclared a fixed 200-tree model and did not require early stopping, the preferred fix is to use a fixed 200 boosting rounds without overlapping early-stopping feedback, if supported by the installed official wrapper. If the wrapper mandates a VALID segment, document the exact official behavior and use a non-overlapping scheme without changing the predeclared OOS years or tuning based on outcomes.

## 4. Consequence for reported results

The current numerical conclusions are **PROVISIONAL** and must not be accepted as the ML challenger baseline yet, including:

```text
ML does not beat locked MA OOS
5Y_BETTER_RECENTLY
2024-2026 directional separation ~0
no drawdown improvement after exposure matching
```

The prediction-quality diagnostics may remain broadly informative, but the trading-path metrics are invalid until the initial-state and conservative-sizing defects are fixed. If the validation construction changes, prediction diagnostics must also be recomputed.

## 5. Required disposition

- Keep the frozen feature set, target, 3Y/5Y OOS schedule, prediction threshold, MA baseline, data source, and QMT read-only boundary unchanged.
- Fix the two P0 simulator defects.
- Resolve/document the validation-overlap issue without post-hoc tuning.
- Add deterministic tests that would fail on the current implementation.
- Re-run the full suite and both `--csv` / `--fetch` challenger runs.
- Recompute all fold diagnostics, OOS performance tables, exposure-matched diagnostics, and A/B/C/D conclusions from scratch.

No LightGBM/feature/threshold optimization is authorized.
