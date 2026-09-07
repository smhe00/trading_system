# REVIEW — Midea A Timing Metric Alignment Fix

Date: 2026-09-07
Reviewed commit: `969f52a487438141503973ca0bc366b8a3a49c9c`
Task: `interactive/TASK_MIDEA_A_TIMING_METRIC_ALIGNMENT_FIX_20260907.md`
Target: 美的集团 A股 `000333.SZ`
Verdict: **PASS**

## 1. Review scope

Independent review covered the Agent report and the actual implementation in:

```text
src/trader/strategies/midea_timing/ma_regime.py
scripts/midea_timing_backtest.py
tests/strategies/test_midea_ma_regime.py
```

This review does not rely on the Agent's PASS claim alone.

## 2. Findings

The remaining metric-alignment defects from the previous review are fixed.

### 2.1 Common scored-equity shape — PASS

Both Buy & Hold and MA now use the same explicit scored-series convention:

```text
point 0     : common start-open anchor = 1,000,000
point 1..N  : one close-marked equity point per analysis trading day
```

`build_anchored_series()` is shared by both baselines. The anchor timestamp is strictly earlier than the first close point, eliminating the previous duplicate-index/return-period ambiguity.

### 2.2 Return-period and CAGR duration alignment — PASS

`metrics_from_equity()` now defines:

```text
period_count = len(series) - 1
years        = period_count / 240
```

For the accepted full-window run, both strategies have:

```text
period_count = 2966
years        = 12.3583
```

Therefore CAGR, volatility and Sharpe are now computed over the same scored return count.

### 2.3 Primary MTM activity semantics — PASS

The primary convention remains last-close mark-to-market. Artificial terminal sales are no longer mixed into primary activity metrics.

Buy & Hold primary activity is correctly represented as:

```text
entries = 1
exits   = 0
realized_stamp_duty = 0
primary turnover = entry only
```

MA primary activity contains only actual vn.py trades. Optional terminal liquidation remains a separate symmetric view for both strategies.

### 2.4 Previous safety/accounting fixes preserved — PASS

The review found no regression in the previously accepted constraints:

- pre-start bars only warm indicators;
- no pre-start trade;
- next-bar execution remains the intended backtest convention;
- no same-close look-ahead;
- long-only;
- 100-share board lots;
- cost-aware strategy cash ledger for commission/slippage;
- Buy & Hold sizing reserves buy costs;
- no tested negative-cash synthetic leverage;
- terminal liquidation is symmetric;
- QmtGateway remains read-only.

The Agent reports 87/87 tests passing, including existing QMT regressions.

## 3. Accepted baseline — LOCKED

The following numbers are accepted as the **Midea A research timing baseline v1** under the current documented assumptions.

### Primary: last-close mark-to-market

| Metric | Buy & Hold | MA Regime (conservative-capital) | MA − B&H |
| --- | ---: | ---: | ---: |
| Start equity | 1,000,000 | 1,000,000 | — |
| Periods / years | 2966 / 12.3583 | 2966 / 12.3583 | — |
| Final equity | 9,225,164 | 3,767,495 | — |
| CAGR | **19.70%** | **11.33%** | **−8.37pp** |
| Annualized volatility | 29.39% | 19.11% | −10.28pp |
| Sharpe (rf=0) | **0.7585** | **0.6570** | **−0.1015** |
| MaxDD | 55.69% | 33.04% | **−22.65pp** |
| Calmar | 0.3537 | 0.3429 | −0.0108 |
| Actual entries/exits | 1 / 0 | 42 / 41 | — |
| Annualized primary turnover | 0.0806 | 14.9166 | — |
| Realized stamp duty reported | 0 | 46,012 | — |

### Optional terminal liquidation

| Metric | Buy & Hold | MA Regime |
| --- | ---: | ---: |
| Liquidated final equity | 9,217,566 | 3,764,916 |
| Liquidated CAGR | 19.69% | 11.32% |
| Liquidated exits | 1 | 42 |
| Liquidated annualized turnover | 0.8268 | 15.1698 |
| Final shares | 22,100 | 7,500 |

## 4. Interpretation

The fixed MA20/60/120 rule is **not an accepted alpha improvement over Buy & Hold** for the full history. It materially reduces drawdown and volatility, but loses both CAGR and Sharpe.

The accepted interpretation is narrower:

> The MA rule is a conservative risk-reduction baseline against which later timing methods must demonstrate incremental value.

The lower drawdown must not automatically be attributed to timing skill because `gap_buffer=1.20` leaves typical deployed capital near 83.3%, materially below Buy & Hold exposure.

## 5. Accepted limitations

These do not block the research baseline, but they remain mandatory disclosures:

1. Back-adjusted prices are used for signal/return research; absolute cash sizing and 0.01/share slippage are approximations rather than production execution prices.
2. T+1 is structurally compatible with the daily next-bar sequence but not explicitly broker-constrained.
3. Limit-up/limit-down non-fill behavior is not modeled.
4. Sell-side stamp duty is reported separately rather than integrated into vn.py's primary equity curve and strategy sizing ledger. Future challengers must either use the same convention or upgrade the cost accounting for **all** compared strategies before comparison.
5. `gap_buffer=1.20` means this is a **conservative-capital** MA baseline, not a strict 0%/100% exposure baseline.

## 6. Gate decision

```text
MIDEA_A_TIMING_BASELINE_V1 = PASS / LOCKED
```

Do not keep modifying this baseline merely to improve its performance. Any future methodological change that affects the benchmark must be versioned as a new baseline.

The next research gate should test whether this fixed rule behaves consistently across historical regimes and whether older Midea data remains informative for medium-horizon timing, before introducing LightGBM or other ML models.
