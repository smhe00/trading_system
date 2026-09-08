# TASK: Midea A — vnpy.alpha / LightGBM Challenger Fix

Date: 2026-09-08
Based on review: `interactive/REVIEW_MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER_20260908.md`
State: **CHANGES_REQUIRED**
Target: 美的集团 A股 `000333.SZ`
Nature: research/backtest only

## 1. Goal

Repair the first vnpy.alpha / LightGBM challenger without changing the frozen research hypothesis.

Do not optimize features, hyperparameters, prediction threshold, walk-forward windows, or the accepted MA baseline.

## 2. Allowed files

Modify only as needed:

```text
src/trader/strategies/midea_timing/ml_research.py
scripts/midea_vnpy_alpha_lightgbm_challenger.py
tests/strategies/test_midea_vnpy_alpha_challenger.py
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER_FIX_20260908.md
```

Do not modify locked baseline files, QmtGateway, MiniQMT configuration, VeighNa Studio, previous reports/reviews/tasks, or dependency declarations.

No additional package installation/upgrade is authorized by this fix task.

## 3. Mandatory fix A — initial state must be actionable

Every evaluation window starts:

```text
equity = 1,000,000
position = 0
```

If the first available signal in the evaluation window is LONG, the simulator must place the corresponding entry for the **next tradable bar**. It must not wait for a later CASH→LONG transition.

Required deterministic test:

```text
predictions begin LONG and stay LONG
-> exactly one entry
-> entry occurs on the next tradable bar after the first LONG signal
-> no redundant later entries
```

Also test initial CASH followed by LONG and existing LONG→CASH behavior.

## 4. Mandatory fix B — use the locked conservative-capital sizing rule

ML entry sizing must use the same information timing and conservative reserve principle as `MaRegimeStrategy`:

```text
signal after t close
size decision at t using only information available through t
max sizing price = close_t * gap_buffer
GAP_BUFFER = 1.20
100-share board lots
buy commission/slippage reserved
execution no earlier than next tradable bar
```

Do **not** determine share quantity from the realized next-day open.

Prefer mirroring the locked baseline's order semantics as closely as possible:

```text
size against close_t * 1.20
buy limit consistent with locked baseline (currently close_t * 1.15)
next-bar fill only when the bar can execute that order under the simulator convention
```

If exact vn.py bar-crossing semantics are reimplemented in the pure simulator, document them and test them.

Required tests:

```text
[ ] sizing uses signal-day close, not next-day open
[ ] gap_buffer=1.20 affects quantity
[ ] +10% next-open gap remains fully funded
[ ] no negative cash
[ ] 100-share lot preserved
[ ] next-bar execution preserved
[ ] a gap beyond the chosen buy-limit convention is handled explicitly, not silently assumed filled
```

## 5. Mandatory fix C — resolve overlapping early-stopping validation

Current implementation makes VALID the last year of a TRAIN interval that already includes that year while also using `early_stopping_rounds=50`.

This must be resolved without post-hoc tuning.

Preferred approach:

- keep the task's fixed 200 boosting rounds;
- disable early stopping if the installed official `LgbModel` supports a clean fixed-round configuration;
- then train on the full declared prior 3Y/5Y interval.

If the official wrapper requires validation data:

- inspect/document the exact API behavior;
- use a deterministic, predeclared non-overlapping fit/validation construction entirely inside the declared historical window;
- do not change it after seeing results;
- report effective fit/validation date ranges and row counts per fold.

OOS test years and 3Y/5Y historical coverage must remain as originally authorized.

Add tests/structural assertions proving TRAIN and VALID rows used for early-stopping feedback do not overlap, or proving early stopping is disabled and therefore no overlapping validation feedback is used.

## 6. Preserve leakage controls

Must remain true:

```text
10 frozen features only
y20 exactly t+20
training targets purged if t+20 crosses OOS boundary
no OOS rows in fit data
one fresh model per OOS year
prediction threshold fixed at >0
long-only
no feature/hyperparameter/threshold optimization
```

## 7. Recompute everything

After fixes, run:

```powershell
python -B -m unittest discover -s tests -t . -v
python -B scripts\midea_vnpy_alpha_lightgbm_challenger.py --csv work\midea_000333_daily_back.csv --json work\midea_vnpy_alpha_lightgbm_summary.json
python -B scripts\midea_vnpy_alpha_lightgbm_challenger.py --fetch --json work\midea_vnpy_alpha_lightgbm_summary.json
```

`--csv` and `--fetch` must agree for the same market-data snapshot.

Recompute and report from scratch:

- per-fold train/valid/OOS counts and prediction diagnostics;
- ALL_3Y / RECENT_3Y / R4_3Y;
- ALL_5Y / RECENT_5Y / R4_5Y;
- BH_100 / BH_STATIC_CONSERVATIVE / MA_FIXED / ML;
- ex-post matched-average-exposure comparator;
- CAGR, vol, Sharpe, MaxDD, Calmar, turnover, time in market, average gross exposure;
- conclusions A/B/C/D.

Do not reuse the previous numerical conclusion if results change.

## 8. Environment disclosure

The previous report recorded user-authorized `.venv` installs required to make vnpy.alpha usable. Preserve an exact dependency/version disclosure, including the observed `peewee` version conflict warning. Do not install anything else in this task.

## 9. Safety

Research/backtest only.

```text
QMT write trading: NOT AUTHORIZED
send_order/cancel_order: must remain unavailable
live orders/fills/cancels caused by this task: 0
```

## 10. Report

Write a new report only:

```text
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER_FIX_20260908.md
```

Include exact changed files, implementation fixes, tests, commands/results, recomputed tables, limitations, environment disclosure, and trading-side-effect statement.

## Definition of Done

```text
[ ] initial LONG signal enters on next tradable bar
[ ] initial CASH -> LONG transition still correct
[ ] ML sizing uses signal-close * gap_buffer, not future open
[ ] board-lot/cost reserve/no-negative-cash tests pass
[ ] execution semantics mirror/document locked baseline
[ ] no overlapping early-stopping feedback, or early stopping disabled
[ ] train/OOS leakage controls remain intact
[ ] full tests pass
[ ] all challenger metrics are recomputed
[ ] --csv / --fetch agree
[ ] locked baseline and QmtGateway unchanged
[ ] no live trading side effects
```
