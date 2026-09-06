# REVIEW — Midea A-share Timing Baseline Fix

Date: 2026-09-07
Reviewed commit: `ddd4ededd591f5e16c969c5317ff432df7fa1cf5`
Task: `interactive/TASK_MIDEA_A_TIMING_BASELINE_FIX_20260906.md`

## Verdict

**CHANGES_REQUIRED**

The previous blocking issues were mostly fixed correctly: common analysis start, no pre-start trades, consistent explicit starting equity, next-bar execution, and B&H residual cash in the marked equity curve are all materially improved. However, the strategy still uses a private cash ledger for future position sizing that does not deduct the same transaction costs charged by the vn.py backtest engine. This can progressively overstate deployable cash after repeated trades. The B&H share-sizing formula also does not reserve buy-side commission/slippage before choosing the board-lot quantity.

The resulting 19.69% B&H / 11.40% MA numbers are therefore still **provisional**, not yet the accepted baseline for later ML comparison.

## Findings

### 1. Blocking — strategy sizing cash ledger ignores trading costs

`MaRegimeStrategy.on_trade()` currently updates cash only by gross trade notional:

```python
if trade.direction == Direction.LONG:
    self.cash -= trade.volume * trade.price
else:
    self.cash += trade.volume * trade.price
```

But the backtest engine is configured with commission and slippage. Therefore, after every round trip, `self.cash` used for the next entry is greater than the engine/economic cash by accumulated costs. The 20% gap reserve does not make this accounting inconsistency correct; it only masks it probabilistically.

Required behavior:

- the strategy sizing ledger must deduct the same buy/sell commission and per-share slippage assumptions used by the backtest engine;
- after a sell, the ledger must add net proceeds after those modeled costs;
- add a multi-round-trip test proving the sizing ledger does not drift upward relative to a cost-aware expected ledger;
- keep stamp duty handling explicitly documented. It may remain outside vn.py engine PnL for this baseline, but the sizing convention must be stated consistently.

### 2. Blocking — B&H board-lot sizing does not reserve buy costs

Current B&H sizing is:

```python
shares = int(CAPITAL / start_price / LOT_SIZE) * LOT_SIZE
```

and only afterward subtracts commission/slippage. This can make `remaining_cash < 0` for some prices/capital combinations, which is synthetic leverage.

Required behavior:

Choose the largest 100-share lot satisfying:

```text
shares * start_price
+ shares * start_price * commission_rate
+ shares * slippage_per_share
<= CAPITAL
```

Add a deterministic unit test where naive lot sizing would make cash negative and verify the corrected sizing keeps residual cash >= 0.

### 3. Non-blocking — 20% gap reserve changes the strategy meaning

The report correctly discloses that `gap_buffer=1.20` reduces typical invested capital to about 83%. This means the current strategy is no longer a strict "0% / 100%" MA timing baseline; it is closer to "0% / conservatively capped long exposure".

Do not hide this. For the accepted baseline, either:

- rename/document it as a conservative-capital MA regime baseline, or
- implement an execution/sizing method that targets near-100% without allowing negative cash.

No parameter optimization is requested.

### 4. Non-blocking — Sharpe/MaxDD start-day convention

B&H buys at the analysis-start open but its daily return series starts from the first marked close; MA may remain flat on the first day. This is acceptable for a coarse baseline if documented, but do not describe daily return statistics as perfectly identical execution timing conventions.

## What passed independent review

- pre-start bars are used only for indicator warm-up;
- trading is gated by `analysis_start`;
- the MA scored window starts from the common capital and flat state;
- next-bar execution remains explicit and tested;
- long-only / 100-share lot constraints remain present;
- B&H daily marked equity now includes idle residual cash;
- CAGR uses an explicit common start equity;
- T+1 and adjusted-price limitations are no longer overstated;
- no QMT write path was added.

## Gate

Until Findings 1 and 2 are fixed and the corrected results are recomputed:

```text
MIDEA_A_TIMING_BASELINE = CHANGES_REQUIRED
Current reported metrics = PROVISIONAL
QmtGateway read-only gate = unchanged / PASS
Live trading authorization = NONE
```
