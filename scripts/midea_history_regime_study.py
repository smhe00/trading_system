"""Midea historical regime / old-vs-recent data study (research/backtest only).

Evaluates the LOCKED Midea timing baseline across fixed calendar regimes.

Per regime (R1-R4, OLD, RECENT), compares three comparators built on the
accepted baseline conventions:
    A. BH_100                 - 100% Buy & Hold
    B. BH_STATIC_CONSERVATIVE - static B&H at ~1/gap_buffer exposure (no rebalancing)
    C. MA_FIXED               - accepted fixed MA20/60/120 conservative-capital strategy

plus a forward R20/R60 state-conditional signal diagnostic and a basic
feature-drift summary. The locked baseline files are imported, never modified.

Usage:
    python scripts/midea_history_regime_study.py --csv work/midea_000333_daily_back.csv --json work/midea_history_regime_summary.json
    python scripts/midea_history_regime_study.py --fetch --json work/midea_history_regime_summary.json
"""
import argparse
from datetime import timedelta
import json
import math
import statistics
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vnpy.trader.constant import Direction

from src.trader.strategies.midea_timing import (
    MaRegimeStrategy,
    build_anchored_series,
    size_board_lots,
    terminal_liquidation,
)
from src.trader.strategies.midea_timing.research import (
    forward_returns,
    ma_state_at,
    position_series,
    regime_contained_sample,
    select_regime_bars,
    sma_series,
    warmup_bars,
)
from scripts.midea_timing_backtest import (
    ANNUAL_DAYS,
    CAPITAL,
    COMMISSION_RATE,
    FETCH_START,
    GAP_BUFFER,
    LOT_SIZE,
    SLIPPAGE,
    STAMP_DUTY,
    SYMBOL,
    VT_SYMBOL,
    fetch_bars_xtdata,
    load_bars_csv,
    metrics_from_equity,
    run_buy_and_hold,
)

WARMUP_COUNT = 130   # >= slow_window + 1 so MA120 is ready by the period start

REGIMES = {
    "R1": ("20140401", "20171231"),
    "R2": ("20180101", "20201231"),
    "R3": ("20210101", "20231231"),
    "R4": ("20240101", "20260904"),
    "OLD": ("20140401", "20201231"),
    "RECENT": ("20210101", "20260904"),
}
R1_R4 = ["R1", "R2", "R3", "R4"]

COMPARATORS = ("BH_100", "BH_STATIC_CONSERVATIVE", "MA_FIXED")


def run_ma_fixed(bars_full, start, end):
    """Run the accepted MA_FIXED strategy on a regime (warm-up never trades)."""
    import pandas as pd
    from vnpy.trader.constant import Interval
    from vnpy_ctastrategy.backtesting import BacktestingEngine
    from vnpy_ctastrategy.base import BacktestingMode

    window = select_regime_bars(bars_full, start, end)
    if not window:
        return None
    eff_start = window[0].datetime.strftime("%Y%m%d")
    feed = warmup_bars(bars_full, eff_start, WARMUP_COUNT) + window

    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol=VT_SYMBOL,
        interval=Interval.DAILY,
        start=feed[0].datetime,
        rate=COMMISSION_RATE,
        slippage=SLIPPAGE,
        size=1.0,
        pricetick=0.01,
        capital=int(CAPITAL),
        end=window[-1].datetime,
        mode=BacktestingMode.BAR,
        annual_days=ANNUAL_DAYS,
    )
    engine.add_strategy(MaRegimeStrategy, {
        "analysis_start": eff_start,
        "commission_rate": COMMISSION_RATE,
        "slippage_per_share": SLIPPAGE,
    })
    engine.history_data = feed
    engine.run_backtesting()
    df = engine.calculate_result()
    trades = engine.get_all_trades()

    bal = engine.capital + df["net_pnl"].cumsum()
    bal.index = pd.to_datetime(bal.index)
    bal = bal[bal.index >= pd.to_datetime(eff_start)]
    if abs(float(bal.iloc[0]) - CAPITAL) > 1e-6:
        raise RuntimeError(f"MA_FIXED {start}..{end} did not start flat at CAPITAL")
    anchor_ts = bal.index[0] - pd.Timedelta(seconds=1)
    series = build_anchored_series(CAPITAL, anchor_ts, bal.values, bal.index)
    metrics = metrics_from_equity(series, CAPITAL)

    buys = [t for t in trades if t.direction == Direction.LONG]
    sells = [t for t in trades if t.direction == Direction.SHORT]
    metrics["entries"] = len(buys)
    metrics["exits"] = len(sells)
    metrics["n_trades"] = len(trades)
    turnover = sum(t.volume * t.price for t in trades)
    metrics["primary_turnover"] = round(turnover, 2)
    metrics["annualized_turnover"] = round(turnover / CAPITAL / metrics["years"], 4)
    metrics["realized_stamp_duty"] = round(
        sum(t.volume * t.price for t in sells) * STAMP_DUTY, 2)

    # Deterministic daily position/exposure reconstruction from trades.
    dates = [d.date() for d in bal.index]
    pos = position_series(trades, dates)
    closes = list(df["close_price"].reindex(bal.index).values)
    exposure = [p * c / b for p, c, b in zip(pos, closes, bal.values) if b > 0]
    metrics["time_in_market"] = round(sum(1 for p in pos if p > 0) / len(pos), 4)
    long_expo = [e for p, e in zip(pos, exposure) if p > 0]
    metrics["avg_deployed_while_long"] = round(
        float(sum(long_expo) / len(long_expo)), 4) if long_expo else 0.0
    metrics["overall_avg_gross_exposure"] = round(
        float(sum(exposure) / len(exposure)), 4) if exposure else 0.0

    final_shares = sum(t.volume for t in buys) - sum(t.volume for t in sells)
    last_close = float(df["close_price"].iloc[-1])
    metrics.update(terminal_liquidation(
        metrics["final_equity"], final_shares, last_close,
        COMMISSION_RATE, SLIPPAGE, STAMP_DUTY))
    metrics["liquidated_cagr"] = round(
        (metrics["liquidated_final_equity"] / CAPITAL) ** (1 / metrics["years"]) - 1, 4)
    metrics["liquidated_exits"] = len(sells) + (1 if final_shares > 0 else 0)
    liq_turnover = turnover + final_shares * last_close
    metrics["liquidated_total_turnover"] = round(liq_turnover, 2)
    metrics["liquidated_annualized_turnover"] = round(
        liq_turnover / CAPITAL / metrics["years"], 4)
    metrics["final_shares"] = int(final_shares)
    metrics["actual_start"] = eff_start
    metrics["actual_end"] = window[-1].datetime.strftime("%Y%m%d")
    return metrics


def run_bh_static_conservative(bars, start):
    """Static Buy & Hold at ~1/gap_buffer exposure; cost-aware lot sizing;
    no rebalancing. Residual + un-deployed capital stays as cash in equity."""
    import pandas as pd

    window = [b for b in bars if b.datetime.strftime("%Y%m%d") >= start]
    if not window:
        raise RuntimeError(f"empty window for BH_STATIC_CONSERVATIVE {start}")
    first, last = window[0], window[-1]
    start_price = first.open_price
    end_price = last.close_price
    target_cash = CAPITAL / GAP_BUFFER
    shares = size_board_lots(target_cash, start_price, COMMISSION_RATE, SLIPPAGE, LOT_SIZE)
    if shares < LOT_SIZE:
        raise RuntimeError("capital too small for one board lot at conservative exposure")

    buy_cost = shares * start_price * COMMISSION_RATE + shares * SLIPPAGE
    remaining_cash = CAPITAL - shares * start_price - buy_cost
    initial_deployed = shares * start_price / CAPITAL

    anchor_ts = first.datetime - timedelta(seconds=1)
    daily_equity = build_anchored_series(
        CAPITAL, anchor_ts,
        [remaining_cash + shares * b.close_price for b in window],
        [b.datetime for b in window],
    )
    metrics = metrics_from_equity(daily_equity, CAPITAL)
    metrics["final_equity"] = round(float(metrics["final_equity"]), 2)
    metrics["entries"] = 1
    metrics["exits"] = 0
    metrics["primary_turnover"] = round(shares * start_price, 2)
    metrics["annualized_turnover"] = round(
        metrics["primary_turnover"] / CAPITAL / metrics["years"], 4)
    metrics["realized_stamp_duty"] = 0.0
    metrics.update(terminal_liquidation(
        metrics["final_equity"], shares, end_price,
        COMMISSION_RATE, SLIPPAGE, STAMP_DUTY))
    metrics["liquidated_cagr"] = round(
        (metrics["liquidated_final_equity"] / CAPITAL) ** (1 / metrics["years"]) - 1, 4)
    metrics["liquidated_exits"] = 1
    metrics["liquidated_total_turnover"] = round(shares * start_price + shares * end_price, 2)
    metrics["liquidated_annualized_turnover"] = round(
        metrics["liquidated_total_turnover"] / CAPITAL / metrics["years"], 4)
    metrics["shares"] = shares
    metrics["initial_deployed_fraction"] = round(initial_deployed, 4)
    metrics["time_in_market"] = 1.0
    metrics["actual_start"] = first.datetime.strftime("%Y%m%d")
    metrics["actual_end"] = last.datetime.strftime("%Y%m%d")
    return metrics


def summarize(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"count": 0}
    return {
        "count": len(vals),
        "mean": round(statistics.mean(vals), 4),
        "median": round(statistics.median(vals), 4),
        "p_positive": round(sum(1 for v in vals if v > 0) / len(vals), 4),
    }


def forward_diagnostic(closes, dates, regimes=None, horizons=(20, 60)):
    """State-conditional forward returns per regime (descriptive only).

    Every sample is regime-contained: BOTH the state date ``t`` and the
    forward target date ``t+h`` must lie inside the same requested interval
    (``regime_contained_sample``). A late-OLD sample whose target falls in
    RECENT is therefore excluded. The state at ``t`` still uses only data
    through ``t`` close.
    """
    if regimes is None:
        regimes = REGIMES
    ma20 = sma_series(closes, 20)
    ma60 = sma_series(closes, 60)
    ma120 = sma_series(closes, 120)
    fwd = {h: forward_returns(closes, h) for h in horizons}

    buckets = {}
    for name, (s, e) in regimes.items():
        buckets[name] = {"LONG": {h: [] for h in horizons}, "CASH": {h: [] for h in horizons}}

    for i in range(len(closes)):
        state = ma_state_at(closes, ma20, ma60, ma120, i)
        if state is None:
            continue
        key = "LONG" if state else "CASH"
        for name, (s, e) in regimes.items():
            for h in horizons:
                if not regime_contained_sample(dates, i, h, s, e):
                    continue
                if fwd[h][i] is not None:
                    buckets[name][key][h].append(fwd[h][i])

    out = {}
    for name, states in buckets.items():
        out[name] = {}
        for state, by_h in states.items():
            out[name][state] = {str(h): summarize(by_h[h]) for h in horizons}
        out[name]["spreads"] = {}
        for h in horizons:
            long_s = out[name]["LONG"][str(h)]
            cash_s = out[name]["CASH"][str(h)]
            out[name]["spreads"][f"mean_R{h}"] = round(
                (long_s.get("mean", 0) or 0) - (cash_s.get("mean", 0) or 0), 4)
            out[name]["spreads"][f"median_R{h}"] = round(
                (long_s.get("median", 0) or 0) - (cash_s.get("median", 0) or 0), 4)
    return out


def feature_drift(closes, dates):
    """Median / IQR of fixed features per R1-R4 (descriptive only)."""
    ma20 = sma_series(closes, 20)
    ma60 = sma_series(closes, 60)
    ma120 = sma_series(closes, 120)
    daily_ret = [None] + [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]

    features = {"ret20": [], "ret60": [], "rv20": [], "close_ma120": [], "ma20_ma60": []}
    out = {}
    for name, (s, e) in REGIMES.items():
        if name not in R1_R4:
            continue
        cols = {k: [] for k in features}
        for i in range(len(closes)):
            if not (s <= dates[i] <= e):
                continue
            if ma120[i] is None or i < 60:
                continue
            cols["ret20"].append(closes[i] / closes[i - 20] - 1)
            cols["ret60"].append(closes[i] / closes[i - 60] - 1)
            window_rets = [r for r in daily_ret[i - 19:i + 1] if r is not None]
            cols["rv20"].append(statistics.pstdev(window_rets) * math.sqrt(ANNUAL_DAYS))
            cols["close_ma120"].append(closes[i] / ma120[i] - 1)
            cols["ma20_ma60"].append(ma20[i] / ma60[i] - 1)
        out[name] = {}
        for k, vals in cols.items():
            vals_sorted = sorted(vals)
            # One documented quantile convention (standard-library inclusive
            # quartiles), applied consistently to every feature.
            q25, _median, q75 = statistics.quantiles(
                vals_sorted, n=4, method="inclusive")
            out[name][k] = {
                "median": round(statistics.median(vals_sorted), 4),
                "q25": round(q25, 4),
                "q75": round(q75, 4),
                "count": len(vals_sorted),
            }
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", help="read bars from a CSV (miniQMT format)")
    parser.add_argument("--fetch", action="store_true", help="fetch from local miniQMT")
    parser.add_argument("--json", help="write summary JSON under work/")
    args = parser.parse_args()

    if args.csv:
        bars = load_bars_csv(Path(args.csv), FETCH_START, "20260904")
    elif args.fetch:
        bars = fetch_bars_xtdata(FETCH_START, "20260904")
    else:
        parser.error("provide --csv <file> or --fetch")
    if not bars:
        raise SystemExit("no bars loaded")

    closes = [b.close_price for b in bars]
    dates = [b.datetime.strftime("%Y%m%d") for b in bars]

    regimes_out = {}
    for name, (s, e) in REGIMES.items():
        window = select_regime_bars(bars, s, e)
        eff_start = window[0].datetime.strftime("%Y%m%d") if window else None
        row = {"requested": f"{s}..{e}", "actual_start": eff_start,
               "actual_end": window[-1].datetime.strftime("%Y%m%d") if window else None}
        row["BH_100"] = run_buy_and_hold(window, eff_start) if window else None
        row["BH_STATIC_CONSERVATIVE"] = (
            run_bh_static_conservative(window, eff_start) if window else None)
        row["MA_FIXED"] = run_ma_fixed(bars, s, e) if window else None
        if row["BH_100"]:
            row["BH_100"]["time_in_market"] = 1.0
        regimes_out[name] = row

    # Deltas per regime (primary metrics).
    deltas = {}
    for name in REGIMES:
        m = regimes_out[name]
        if not m["MA_FIXED"] or not m["BH_100"]:
            continue
        deltas[name] = {
            "MA_vs_BH100": {
                k: round(m["MA_FIXED"][k] - m["BH_100"][k], 4)
                for k in ("cagr", "sharpe", "max_drawdown", "calmar")
            },
            "MA_vs_BH_STATIC": {
                k: round(m["MA_FIXED"][k] - m["BH_STATIC_CONSERVATIVE"][k], 4)
                for k in ("cagr", "sharpe", "max_drawdown", "calmar")
            },
        }

    fwd = forward_diagnostic(closes, dates)
    drift = feature_drift(closes, dates)

    summary = {
        "symbol": SYMBOL,
        "data_source": "miniQMT (xtdata, 后复权/back-adjust, 含现金分红与送转)",
        "warmup_count": WARMUP_COUNT,
        "regimes": regimes_out,
        "deltas": deltas,
        "forward_r20_r60_by_state": fwd,
        "feature_drift_r1_r4": drift,
        "trade_side_effects": {"orders_submitted": 0, "orders_cancelled": 0, "fills": 0},
    }
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.json:
        out = Path(args.json).resolve()
        if not out.is_relative_to(ROOT / "work"):
            raise SystemExit("--json output must be inside work/")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"summary written: {out}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
