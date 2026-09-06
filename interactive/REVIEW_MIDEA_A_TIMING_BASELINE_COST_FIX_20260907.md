# REVIEW — Midea A Timing Baseline Cost Fix

Date: 2026-09-07
Reviewed commit: `ec4d01eb70aab1af1e6a865f65417a0f6a55d2a8`
Task: `interactive/TASK_MIDEA_A_TIMING_BASELINE_COST_FIX_20260907.md`
Verdict: **CHANGES_REQUIRED**

## 1. What passed

The requested cost-accounting fixes are implemented correctly enough for this stage:

- strategy sizing cash ledger now deducts buy/sell commission and per-share slippage;
- repeated round trips no longer reuse gross cash as if costs had not occurred;
- `size_board_lots()` reserves buy-side commission/slippage before selecting a 100-share lot size;
- Buy & Hold now uses the same cost-aware sizing helper;
- previous analysis-start gating, next-bar execution, long-only, board-lot and no-prestart-trade protections remain present;
- the strategy is now correctly described as **conservative-capital MA regime**, with `gap_buffer=1.20` and approximate deployment around 83% explicitly disclosed;
- no QMT write path was added.

These changes address the previous review findings.

## 2. Blocking issue: inconsistent terminal valuation

The reported comparison still mixes two different end-of-window conventions.

Current report says:

```text
Buy & Hold: entries/exits = 1 / 1
MA:         entries/exits = 42 / 41
```

Therefore the MA strategy still holds an open position at the end of the analysis window.

Current behavior is asymmetric:

### Buy & Hold

`run_buy_and_hold()` explicitly assumes a terminal sale at the final close and subtracts:

- sell commission;
- sell slippage;
- stamp duty.

Its reported `final_equity` and CAGR therefore use a **liquidated terminal value**.

### MA regime

The vn.py equity curve ends mark-to-market with the final open position still held. No final liquidation trade is present in the strategy results. Consequently its `final_equity` does not include terminal sell commission/slippage. Its separately calculated stamp duty also only covers the 41 actual sell trades, not liquidation of the final open position.

This gives the two strategies different terminal accounting rules and makes the final CAGR comparison formally inconsistent.

The magnitude is probably small, but this baseline will be used later to judge ML improvements, so the endpoint convention must be exact before acceptance.

## 3. Secondary boundary issue: starting-equity anchor for return statistics

Buy & Hold's daily equity series begins after the analysis-start open purchase and is first marked at that day's close. `pct_change()` therefore does not include the move from the common initial 1,000,000 equity at the analysis-start open to the first close.

The MA curve can begin at 1,000,000 while still flat. This creates a small first-day asymmetry in Sharpe/volatility/max-drawdown calculations.

For a 12-year sample this is not likely to change the qualitative conclusion, but the benchmark should have an explicit common starting-equity anchor.

## 4. Required correction

Use one explicit, common endpoint convention for both strategies. Recommended approach:

### Primary research metrics: mark-to-market

- both strategies start from an explicit equity anchor of 1,000,000 at analysis start;
- both end at last-close **mark-to-market**, without assuming an artificial terminal sale;
- primary CAGR / Sharpe / volatility / MaxDD / Calmar use this common mark-to-market convention.

### Optional liquidation metrics

Also report a separate `liquidated_final_equity` / `liquidated_cagr` for both strategies:

- if a strategy holds shares at the final close, deduct the same terminal sell commission, slippage and stamp-duty assumptions;
- if already flat, liquidation value equals mark-to-market value;
- do not insert a fake strategy trade into the vn.py trade history merely to manufacture this number.

An alternative is to make liquidation the primary convention, but it must be applied identically to both strategies. Do not continue with one liquidated and one mark-to-market.

## 5. Tests required

Add tests that prove:

1. Buy & Hold and MA both expose the same explicit starting-equity anchor.
2. Primary final equity is mark-to-market for both, or liquidated for both — never mixed.
3. When MA ends with an open position, optional terminal liquidation deducts sell commission + sell slippage + stamp duty.
4. When MA ends flat, liquidation adjustment is zero.
5. Buy & Hold uses the same terminal liquidation helper/convention as MA.
6. Existing cost-ledger, no-lookahead, analysis-start and QMT regression tests still pass.

## 6. Baseline status

The current numbers:

```text
Buy & Hold CAGR    19.69%
MA CAGR            11.33% (11.22% net-stamp variant)
Buy & Hold MaxDD   55.69%
MA MaxDD           33.04%
```

remain **PROVISIONAL** until the common boundary/terminal convention is fixed.

The qualitative finding is unchanged: this conservative-capital MA rule materially reduces volatility/drawdown but underperforms Buy & Hold on return and Sharpe. The next task should not yet use these values as the locked ML benchmark.

## 7. Safety

No live trading is authorized by this review. QmtGateway write paths remain out of scope.
