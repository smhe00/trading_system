# REVIEW — Midea Timing Terminal Valuation Fix

Date: 2026-09-07
Reviewed commit: `e71ee64f9f0a5a1bc9266392765cdaa83f56f943`
Task: `interactive/TASK_MIDEA_A_TIMING_TERMINAL_VALUATION_FIX_20260907.md`

## Verdict

**CHANGES_REQUIRED**

The terminal MTM/liquidation asymmetry is fixed correctly, and the shared `terminal_liquidation()` helper is acceptable. However, the baseline is still not ready to be frozen because the return-series anchor and activity metrics are not yet aligned between Buy & Hold and MA.

## What passed

- Both strategies now use last-close mark-to-market as the primary terminal convention.
- Optional terminal liquidation uses one shared helper for both strategies.
- Open MA terminal positions are handled without injecting fake vn.py trades.
- Buy sizing/cash-ledger/start-gate/no-lookahead/long-only/board-lot fixes remain intact.
- The agent reports 83/83 tests passing and `--fetch` / `--csv` agreement.
- No live trading write path was added.

## Blocking findings

### 1. Starting anchor is still not symmetric in the return series

`run_buy_and_hold()` prepends a separate 1,000,000 anchor and then appends the first close-marked equity at the same trading date. This creates an explicit first open→close return.

The MA path does not prepend an equivalent anchor to its scored balance series. Its first point is simply the first daily close balance (1,000,000 because it is still flat), so the first zero-return period is not represented as a `pct_change()` observation.

Consequence:

- B&H has one additional return observation;
- MA omits the corresponding initial 0% return;
- annualized volatility/Sharpe are therefore not computed over exactly the same return periods.

The task explicitly required a common explicit starting-equity anchor before strategy-specific market movement is scored.

Required fix: build both scored equity series as:

```text
common start-open anchor = 1,000,000
then one close-marked equity point per analysis trading bar
```

For MA, the first close will normally also be 1,000,000, producing an explicit 0% first-period return.

Avoid ambiguous duplicate timestamps if practical; a clearly defined synthetic start-open timestamp immediately before the first close is preferred.

### 2. CAGR year basis is not identical after adding the B&H anchor

`metrics_from_equity()` uses:

```text
years = len(series) / ANNUAL_DAYS
```

B&H now has `N + 1` points because of the extra anchor, while MA has `N` points. The two CAGR calculations therefore use slightly different year lengths for the same analysis window.

Required fix: derive duration from the common number of scored return periods, e.g. `(len(series) - 1) / ANNUAL_DAYS` once both series use `anchor + N closes`, or pass an explicit common period count/duration.

### 3. Primary MTM B&H activity metrics still include an artificial terminal exit

The primary B&H convention is now mark-to-market with the position still open, but the script/report still state:

```text
entries = 1
exits = 1
annualized_turnover includes entry + terminal sell notional
stamp_duty includes terminal sell stamp duty
```

Those fields describe the optional liquidated view, not the primary MTM strategy.

This is inconsistent with MA, whose primary `entries/exits/turnover` reflect actual vn.py trades and whose optional terminal exit is kept separate.

Required primary-MTM semantics:

```text
B&H entries = 1
B&H exits = 0
B&H primary turnover = actual entry turnover only
B&H primary realized stamp duty = 0
```

If desired, add separate liquidated-view fields such as:

```text
liquidated_exits
liquidated_total_turnover
liquidated_annualized_turnover
```

using the same optional terminal-liquidation convention for both strategies.

### 4. Report labels currently mix primary and liquidated accounting

The report row `交易印花税` shows B&H terminal liquidation stamp duty while the primary B&H path remains open, whereas MA's row refers to actual historical sell trades. This is not an apples-to-apples field.

Separate clearly:

- primary realized transaction costs/turnover;
- optional terminal liquidation costs/turnover.

## Scope

This is a narrow accounting/metric-alignment fix only.

Do not change:

- MA20/60/120 rule;
- gap buffer;
- data source or adjustment method;
- transaction-cost assumptions;
- QmtGateway;
- any live trading capability.

## Gate

The numerical direction remains informative but still **provisional** until the above metrics are aligned.
