# TASK: Fix Midea A-share Timing Baseline

Date: 2026-09-06
Based on review: `interactive/REVIEW_MIDEA_A_TIMING_BASELINE_20260906.md`
State: **CHANGES_REQUIRED**

## Goal

Correct the Midea `000333.SZ` Buy&Hold vs MA20/60/120 timing baseline so both strategies are compared from the same economic initial state and the reported metrics are internally consistent.

This remains **research/backtest only**. Do not enable live trading.

## Allowed files

Modify only as needed:

```text
src/trader/strategies/midea_timing/ma_regime.py
scripts/midea_timing_backtest.py
tests/strategies/test_midea_ma_regime.py
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_TIMING_BASELINE_FIX_20260906.md
```

Do not modify QmtGateway, MiniQMT configuration, VeighNa Studio, or install/upgrade dependencies.

## Mandatory fixes

### 1. Common analysis start state

Both Buy&Hold and MA timing must start the scored analysis window with:

```text
capital = 1,000,000
position = 0
```

Bars before `analysis_start` may be used only to warm MA20/60/120.

No MA strategy order may be submitted or filled before `analysis_start`.

Add tests proving:

- indicators can warm using pre-start bars;
- no pre-start trade occurs;
- first eligible signal after start executes on next tradable bar;
- analysis-window starting equity is exactly the common initial capital.

### 2. Consistent metrics basis

Use one explicit starting equity for all CAGR calculations.

Do not mix:

```text
first sliced MA balance
```

with:

```text
fixed CAPITAL
```

unless they are guaranteed identical by construction.

CAGR, Sharpe, MaxDD, Calmar and final equity must all refer to the same scored analysis window.

### 3. Prevent synthetic leverage / negative cash

Entry sizing must not allow modeled execution cost to exceed available cash.

Account for at least:

- next-bar execution price uncertainty using a conservative sizing rule suitable for this baseline;
- buy commission;
- per-share slippage.

Add a test with a next-bar gap-up scenario proving strategy cash does not become negative and position remains <= 100% funded.

Do not rely on vn.py BacktestingEngine to enforce broker cash constraints implicitly.

### 4. Improve Buy&Hold equity curve

Daily Buy&Hold equity must include residual cash after the board-lot purchase.

Do not calculate daily equity as stock value alone.

### 5. Clarify T+1 claim

Documentation/report must say:

> the daily binary strategy is structurally compatible with A-share T+1 under the current next-bar execution sequence

Do not claim a general T+1 broker constraint is fully modeled unless an explicit sellable-position constraint is implemented and tested.

### 6. Adjusted-price caveat

Keep back-adjusted data if desired, but clearly separate:

- adjusted prices for signal/total-return research;
- production-realistic broker execution prices.

State that fixed `0.01/share` slippage and absolute cash/lot sizing on adjusted prices are research approximations unless raw-price execution is implemented.

No need to add a second raw-price data pipeline in this narrow fix unless straightforward.

## Re-run and report

Run at minimum:

```powershell
python -B -m unittest discover -s tests -t . -v
python -B scripts\midea_timing_backtest.py --fetch --json work\midea_timing_summary.json
```

Report the corrected table:

```text
Buy&Hold vs MA Regime
CAGR
Annualized Vol
Sharpe
MaxDD
Calmar
Final Equity
Entries/Exits
Annualized Turnover
```

Do not reuse the previous numerical conclusion without recomputation.

## Acceptance criteria

```text
[ ] both strategies start analysis window at exactly 1,000,000 and flat
[ ] pre-start bars warm indicators but cannot trade
[ ] next-bar execution remains verified
[ ] entry sizing cannot create negative cash in tested gap-up case
[ ] board-lot constraint remains 100 shares
[ ] long-only remains enforced
[ ] Buy&Hold daily equity includes idle cash
[ ] CAGR basis is consistent
[ ] report clearly qualifies T+1 modeling
[ ] report clearly qualifies adjusted-price execution assumptions
[ ] all existing QMT tests still pass
[ ] no live order/cancel path added
```

## Report file

Write a new report:

```text
interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_TIMING_BASELINE_FIX_20260906.md
```

Do not overwrite the previous report.
