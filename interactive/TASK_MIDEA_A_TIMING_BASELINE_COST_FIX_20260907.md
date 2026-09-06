# TASK — Midea A-share Timing Baseline Cost Accounting Fix

Date: 2026-09-07
Based on review: `interactive/REVIEW_MIDEA_A_TIMING_BASELINE_FIX_20260907.md`
State: **CHANGES_REQUIRED**
Target: 美的集团 A股 `000333.SZ`

## 1. Goal

Fix the remaining cost-accounting inconsistencies in the Midea timing baseline, then recompute the comparison table.

This remains **research/backtest only**. Do not add or enable any live trading capability.

## 2. Allowed files

Modify only as needed:

```text
src/trader/strategies/midea_timing/ma_regime.py
scripts/midea_timing_backtest.py
tests/strategies/test_midea_ma_regime.py
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_TIMING_BASELINE_COST_FIX_20260907.md
```

Do not modify QmtGateway, MiniQMT configuration, VeighNa Studio, or unrelated modules.

## 3. Mandatory fixes

### 3.1 Make strategy sizing cash ledger cost-aware

`MaRegimeStrategy.cash` is used for future entry sizing, so it must reflect the transaction costs assumed by the backtest.

For a buy fill, update cash approximately as:

```text
cash -= trade_notional
cash -= trade_notional * commission_rate
cash -= volume * slippage_per_share
```

For a sell fill:

```text
cash += trade_notional
cash -= trade_notional * commission_rate
cash -= volume * slippage_per_share
```

Keep this convention aligned with the rate/slippage assumptions passed to `BacktestingEngine`.

Stamp duty may remain separately handled outside the vn.py engine for this baseline, but the report must state whether stamp duty is or is not included in the strategy sizing cash ledger. Do not silently mix conventions.

Required tests:

- one buy correctly reduces cash by notional + modeled buy costs;
- one sell correctly adds proceeds net of modeled sell costs;
- multiple round trips do not let the private cash ledger drift upward by omitted commission/slippage;
- cash remains non-negative in the existing gap-up test.

### 3.2 Make Buy & Hold lot sizing cost-aware

Choose the largest 100-share lot such that total buy cash requirement does not exceed `CAPITAL`:

```text
shares * start_price
+ shares * start_price * COMMISSION_RATE
+ shares * SLIPPAGE
<= CAPITAL
```

Do not first size by notional alone and then allow costs to push residual cash negative.

Required test:

- construct a deterministic price/capital case where naive lot sizing would create negative remaining cash;
- verify corrected sizing selects one fewer lot as necessary and leaves `remaining_cash >= 0`.

Prefer extracting a small pure helper for board-lot sizing if it makes the test clean.

### 3.3 Preserve earlier fixes

Must remain true:

```text
- no pre-analysis-start trades
- common start equity exactly 1,000,000
- next-bar execution
- long-only
- 100-share board lot
- no same-close look-ahead
- no synthetic leverage
- B&H daily equity includes idle cash
- QMT regression tests unchanged/passing
```

### 3.4 Clarify actual exposure

The existing `gap_buffer=1.20` makes typical deployed capital materially below 100%.

Do not call this strict 100% exposure without qualification. In code/report use wording such as:

```text
conservative-capital MA regime
```

or explicitly report the approximate deployed fraction.

Do not optimize the gap buffer in this task.

## 4. Recompute results

After fixes, rerun the baseline on the same target/data/window:

```text
000333.SZ
2014-04-01 -> 2026-09-04
initial capital = 1,000,000
```

Report at least:

```text
CAGR
annualized volatility
Sharpe
MaxDD
Calmar
final equity
entries/exits
annualized turnover
stamp duty
```

for Buy & Hold and MA regime, plus deltas.

The previous 19.69% / 11.40% values must not simply be copied; recompute them.

## 5. Verification

Run:

```powershell
python -B -m unittest discover -s tests -t . -v
python -B scripts\midea_timing_backtest.py --fetch --json work\midea_timing_summary.json
```

If `--fetch` cannot run because local MiniQMT data service is unavailable, use the existing local CSV and state that limitation explicitly. Do not invent results.

## 6. Safety

Forbidden:

```text
- real orders
- real cancels
- QmtGateway write enablement
- dependency upgrades
- changes under D:\veighna_studio
```

## 7. Acceptance criteria

```text
[ ] strategy cash ledger deducts commission/slippage on buys
[ ] strategy cash ledger deducts commission/slippage on sells
[ ] multi-round-trip ledger test passes
[ ] B&H share sizing reserves buy costs before lot selection
[ ] B&H residual cash cannot be negative from buy costs
[ ] previous analysis-start / no-lookahead fixes remain intact
[ ] common initial equity remains exactly 1,000,000
[ ] all existing QMT tests still pass
[ ] corrected comparison metrics are recomputed
[ ] no live trading side effects
```

## 8. Report

Write a new report:

```text
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_TIMING_BASELINE_COST_FIX_20260907.md
```

Do not overwrite any previous task or report file.
