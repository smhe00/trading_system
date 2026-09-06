# REVIEW — Midea A-share Timing Baseline

Date: 2026-09-06
Reviewed commit: `a0fc391f6ebc6e95857fcc0e721ce7a23e794922`
Task: `interactive/TASK_MIDEA_A_TIMING_BASELINE_20260906.md`
Verdict: **CHANGES_REQUIRED**

## What is good

- Target is correctly fixed to `000333.SZ`.
- Uses existing `vnpy_ctastrategy` instead of introducing new dependencies.
- Signal rule is implemented as requested: `close > MA120 and MA20 > MA60`.
- Strategy is long-only and 100-share rounded.
- Real `BacktestingEngine` test verifies next-bar execution rather than same-close fills.
- Existing QMT tests remain green according to the report.
- No live trading path was enabled.

## Blocking issues

### 1. MA and Buy&Hold do not start from the same economic initial state

The backtest engine is run from `FETCH_START=20130901`, while reported analysis starts at `20140401`.

The strategy is allowed to trade during the warm-up/history period before `20140401`. Later the code only slices the resulting equity curve from `20140401` onward:

```python
engine.run_backtesting()
...
balance = df["balance"][df.index >= pd.to_datetime(args.start)]
```

Therefore the MA strategy can enter the comparison window with a non-1,000,000 balance and/or an existing position, while Buy&Hold is initialized fresh with `CAPITAL=1_000_000` at the analysis-window open.

This makes the reported CAGR/Sharpe/MaxDD comparison not apples-to-apples.

**Required correction:** historical bars before `analysis_start` may warm indicators, but no trade may occur before the common analysis start. Both strategies must start the scored window with the same capital and flat position.

### 2. CAGR calculation is internally inconsistent

`metrics_from_equity()` computes CAGR from the first balance inside the sliced MA window, but later `cagr_net` is recomputed using fixed `CAPITAL`:

```python
cagr_net = (net_final / CAPITAL) ** (1 / years) - 1
```

If pre-window trading changed the balance, these two CAGR bases differ. This is a direct consequence of issue 1 and must be removed.

The corrected implementation should define one common initial equity at analysis start and use it consistently for all metrics.

### 3. Strategy sizing can overspend because fill price and costs are ignored

Entry size is calculated from signal-bar close:

```python
target = int(equity / bar.close_price / lot_size) * lot_size
```

but the actual trade occurs on the next bar and may fill at a higher price. Commission and slippage are also not reserved in sizing. vn.py's backtester does not inherently enforce a cash constraint in the same way a broker would, so this can produce negative synthetic cash / leverage even though the strategy claims 0%/100% long-only cash-equity behavior.

**Required correction:** sizing must conservatively guarantee that the next-bar fill plus modeled buy-side commission/slippage cannot exceed available cash, or the test harness must explicitly detect and reject negative cash. Add a gap-up test.

### 4. Report overstates A-share T+1 realism

The implementation's next-bar signal execution avoids same-close look-ahead, and because an exit order can only be created after the entry is filled, the current daily engine tends to produce a later exit. That is useful, but it is not a general A-share T+1 execution model.

The report should state that the baseline is **structurally compatible with T+1 for this daily binary strategy**, not that T+1 is fully modeled. There is no explicit sellable-yesterday-position constraint.

### 5. Adjusted-price execution assumptions need clearer separation

Back-adjusted prices are acceptable for signal and total-return research, but absolute execution assumptions such as `0.01` per-share slippage and 100-share cash sizing are not economically invariant under adjusted price scaling.

For this baseline, either:

- use adjusted series for signal/return calculation but explicitly avoid interpreting fixed-price slippage and absolute lot-cash mechanics as production-realistic; or
- use a consistent raw-price execution series alongside an adjusted signal/return series.

Do not silently treat back-adjusted absolute prices as directly equivalent to broker execution prices.

## Non-blocking observations

- Buy&Hold daily equity omits idle residual cash from the daily curve, which slightly distorts Sharpe/MaxDD. Include residual cash in the curve in the fix.
- Stamp duty is only deducted from terminal summary, not the daily MA equity curve, so MA Sharpe/MaxDD are pre-stamp while final CAGR is post-stamp. This should be disclosed clearly or, preferably, incorporated into per-trade equity accounting.
- The 15%/85% wide-limit trick is acceptable for proving next-bar execution in a baseline, but it is not a production execution model and should stay confined to research/backtest code.

## Gate decision

**CHANGES_REQUIRED**.

The current numerical conclusion — roughly 19.7% CAGR Buy&Hold vs 13.3% MA timing — must not be treated as an accepted baseline until the common-start-state and cash-sizing issues are fixed and the metrics are rerun.
