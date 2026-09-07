"""Midea A-share timing baseline backtest (research/backtest only).

Compares Buy & Hold with an MA-regime timing strategy on 000333.SZ daily
data using the official vn.py CTA backtest infrastructure.

Usage:
    python scripts/midea_timing_backtest.py --csv work/midea_000333_daily_back.csv
    python scripts/midea_timing_backtest.py --fetch   # pull from local miniQMT
"""
import argparse
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trader.strategies.midea_timing import (
    MaRegimeStrategy,
    build_anchored_series,
    size_board_lots,
    terminal_liquidation,
)

SYMBOL = "000333.SZ"        # market symbol (xtdata / CSV)
VT_SYMBOL = "000333.SZSE"   # vn.py vt_symbol (vn.py exchange value suffix)
DEFAULT_START = "20140401"      # analysis window start (after MA120 warm-up from IPO)
DEFAULT_END = "20260904"        # analysis window end
FETCH_START = "20130901"        # data fetch start (IPO 2013-09-18 + warm-up)
ANNUAL_DAYS = 240

# A-share cost assumptions
CAPITAL = 1_000_000.0
COMMISSION_RATE = 0.0003        # 万3, both sides
SLIPPAGE = 0.01                 # one tick per share
STAMP_DUTY = 0.0005             # 0.05% on sells only (not modeled by vn.py engine)
LOT_SIZE = 100                  # A-share board lot
GAP_BUFFER = 1.20               # strategy worst-case next-open gap reserve (sizing)


def load_bars_csv(csv_path: Path, start: str = "", end: str = "") -> list:
    """Load daily bars from a miniQMT-style CSV; drop zero-volume suspension
    bars so no fill can occur on an untradable day. Does not invent bars."""
    import csv as _csv

    from vnpy.trader.constant import Exchange, Interval
    from vnpy.trader.object import BarData

    bars = []
    with open(csv_path, encoding="utf-8") as f:
        for row in _csv.DictReader(f):
            date_str = row["date"]
            compact = date_str.replace("-", "")
            if start and compact < start:
                continue
            if end and compact > end:
                continue
            if float(row["volume"]) == 0:
                continue
            bar = BarData(
                symbol=SYMBOL.split(".")[0],
                exchange=Exchange.SZSE,
                datetime=datetime.strptime(date_str, "%Y-%m-%d"),
                interval=Interval.DAILY,
                open_price=float(row["open"]),
                high_price=float(row["high"]),
                low_price=float(row["low"]),
                close_price=float(row["close"]),
                volume=float(row["volume"]),
                gateway_name="QMT",
            )
            bars.append(bar)
    return bars


def fetch_bars_xtdata(start: str, end: str) -> list:
    """Pull 000333.SZ back-adjusted daily bars from local miniQMT (xtdata)."""
    from xtquant import xtdata

    xtdata.download_history_data(SYMBOL, period="1d", start_time=start, end_time=end)
    data = xtdata.get_market_data_ex(
        field_list=["open", "high", "low", "close", "volume"],
        stock_list=[SYMBOL],
        period="1d",
        start_time=start,
        end_time=end,
        dividend_type="back",   # 后复权 (含现金分红/送转)
    )
    frame = data[SYMBOL]
    import csv as _csv
    from io import StringIO

    buf = StringIO()
    writer = _csv.writer(buf)
    writer.writerow(["date", "open", "high", "low", "close", "volume", "amount"])
    for date_int in frame.index:
        writer.writerow([
            str(date_int)[:4] + "-" + str(date_int)[4:6] + "-" + str(date_int)[6:8],
            frame["open"][date_int], frame["high"][date_int],
            frame["low"][date_int], frame["close"][date_int],
            frame["volume"][date_int], 0.0,
        ])
    csv_path = ROOT / "work" / "midea_000333_daily_back.csv"
    csv_path.parent.mkdir(exist_ok=True)
    csv_path.write_text(buf.getvalue(), encoding="utf-8")
    return load_bars_csv(csv_path, start, end)


def run_ma_backtest(bars: list, analysis_start: str):
    """Run the MA-regime strategy through vnpy_ctastrategy BacktestingEngine.

    ``analysis_start`` gates trading: bars before it only warm the MA
    indicators, so the strategy starts the scored window flat at CAPITAL.
    """
    from vnpy.trader.constant import Interval
    from vnpy_ctastrategy.base import BacktestingMode
    from vnpy_ctastrategy.backtesting import BacktestingEngine

    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol=VT_SYMBOL,
        interval=Interval.DAILY,
        start=datetime.strptime(FETCH_START, "%Y%m%d"),
        rate=COMMISSION_RATE,
        slippage=SLIPPAGE,
        size=1.0,
        pricetick=0.01,
        capital=int(CAPITAL),
        end=datetime.strptime(DEFAULT_END, "%Y%m%d"),
        mode=BacktestingMode.BAR,
        annual_days=ANNUAL_DAYS,
    )
    engine.add_strategy(MaRegimeStrategy, {
        "analysis_start": analysis_start,
        "commission_rate": COMMISSION_RATE,
        "slippage_per_share": SLIPPAGE,
    })
    engine.history_data = bars            # this vnpy_ctastrategy version has no add_data()
    engine.run_backtesting()
    df = engine.calculate_result()
    trades = engine.get_all_trades()
    return engine, df, trades


def metrics_from_equity(balance, start_equity) -> dict:
    """CAGR / annualized vol / Sharpe / MaxDD / Calmar from a daily balance
    series, all referring to one explicit common starting equity.

    Both scored series are built as ``anchor + N closes``, so the number of
    scored return periods is ``len(series) - 1`` and duration is derived from
    that common period count — identical for Buy & Hold and MA.
    """
    import pandas as pd

    s = balance.dropna()
    if len(s) < 2:
        return {}
    period_count = len(s) - 1
    years = period_count / ANNUAL_DAYS
    end_v = s.iloc[-1]
    cagr_curve = (end_v / start_equity) ** (1 / years) - 1
    daily_ret = s.pct_change().dropna()
    ann_vol = daily_ret.std(ddof=1) * math.sqrt(ANNUAL_DAYS)
    sharpe = (daily_ret.mean() * ANNUAL_DAYS) / ann_vol if ann_vol else float("nan")
    max_dd = -(s / s.cummax() - 1).min()
    calmar = cagr_curve / max_dd if max_dd else float("nan")
    return {
        "start_equity": round(float(start_equity), 2),
        "final_equity": round(float(end_v), 2),
        "cagr": round(cagr_curve, 4),
        "annualized_vol": round(ann_vol, 4),
        "sharpe": round(sharpe, 4),
        "max_drawdown": round(max_dd, 4),
        "calmar": round(calmar, 4),
        "period_count": int(period_count),
        "years": round(years, 4),
    }


def run_buy_and_hold(bars: list, start: str) -> dict:
    """Buy at the analysis-window open, hold, mark to market until the last
    close (primary convention), with an optional terminal-liquidation view.

    Primary metrics use the common mark-to-market convention: an explicit
    1,000,000 starting-equity anchor at the analysis-start open, then
    close-marked equity (idle cash + position value) with the position still
    held. Liquidated metrics use the shared terminal_liquidation helper.
    """
    import pandas as pd

    window = [b for b in bars if b.datetime.strftime("%Y%m%d") >= start]
    if not window:
        raise RuntimeError("empty analysis window for Buy & Hold")
    first = window[0]
    last = window[-1]

    start_price = first.open_price
    end_price = last.close_price
    # Cost-aware board-lot sizing: the total buy cash requirement (notional +
    # commission + slippage) must fit within CAPITAL, so residual cash cannot
    # go negative from buy costs.
    shares = size_board_lots(CAPITAL, start_price, COMMISSION_RATE, SLIPPAGE, LOT_SIZE)
    if shares < LOT_SIZE:
        raise RuntimeError("capital too small for one board lot")

    buy_cost = shares * start_price * COMMISSION_RATE + shares * SLIPPAGE
    sell_value = shares * end_price
    remaining_cash = CAPITAL - shares * start_price - buy_cost

    # Shared scored equity shape: explicit 1,000,000 start-open anchor then
    # one close-marked point per analysis trading bar. Anchor timestamp is
    # strictly before the first close so the first open->close return exists.
    anchor_ts = first.datetime - timedelta(seconds=1)
    daily_equity = build_anchored_series(
        CAPITAL, anchor_ts,
        [remaining_cash + shares * b.close_price for b in window],
        [b.datetime for b in window],
    )
    metrics = metrics_from_equity(daily_equity, CAPITAL)
    # Primary final equity is mark-to-market (position still held).
    metrics["final_equity"] = round(float(metrics["final_equity"]), 2)
    # Primary MTM activity: one entry, NO terminal exit, entry-only turnover,
    # zero realized stamp duty (the position is still open).
    metrics["entries"] = 1
    metrics["exits"] = 0
    metrics["primary_turnover"] = round(shares * start_price, 2)
    metrics["annualized_turnover"] = round(
        metrics["primary_turnover"] / CAPITAL / metrics["years"], 4)
    metrics["realized_stamp_duty"] = 0.0
    # Optional terminal liquidation via the shared helper (same convention as MA).
    metrics.update(terminal_liquidation(
        metrics["final_equity"], shares, end_price,
        COMMISSION_RATE, SLIPPAGE, STAMP_DUTY,
    ))
    metrics["liquidated_cagr"] = round(
        (metrics["liquidated_final_equity"] / CAPITAL) ** (1 / metrics["years"]) - 1, 4)
    # Liquidated-view activity (terminal sale included).
    metrics["liquidated_exits"] = 1
    metrics["liquidated_total_turnover"] = round(shares * start_price + sell_value, 2)
    metrics["liquidated_annualized_turnover"] = round(
        metrics["liquidated_total_turnover"] / CAPITAL / metrics["years"], 4)
    metrics["shares"] = shares
    metrics["start_price"] = round(start_price, 3)
    metrics["end_price"] = round(end_price, 3)
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", help="read bars from a CSV (miniQMT format)")
    parser.add_argument("--fetch", action="store_true", help="fetch from local miniQMT")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=DEFAULT_END)
    parser.add_argument("--json", help="write summary JSON under work/")
    args = parser.parse_args()

    if args.csv:
        bars = load_bars_csv(Path(args.csv), FETCH_START, args.end)
    elif args.fetch:
        bars = fetch_bars_xtdata(FETCH_START, args.end)
    else:
        parser.error("provide --csv <file> or --fetch")

    if not bars:
        raise SystemExit("no bars loaded")

    from vnpy.trader.constant import Direction

    # MA regime (vnpy_ctastrategy)
    engine, df, trades = run_ma_backtest(bars, args.start)
    import pandas as pd
    df = df.copy()
    df["balance"] = df["net_pnl"].cumsum() + engine.capital
    df.index = pd.to_datetime(df.index)
    balance = df["balance"][df.index >= pd.to_datetime(args.start)]
    # Common initial state must hold by construction (no pre-start trades).
    start_equity = float(balance.iloc[0])
    if abs(start_equity - CAPITAL) > 1e-6:
        raise RuntimeError(
            f"MA analysis-window starting equity {start_equity:.2f} != "
            f"common capital {CAPITAL:.2f}"
        )
    # Shared scored equity shape: explicit 1,000,000 start-open anchor then
    # the close-marked balance points. MA is flat on the first analysis day,
    # so the first-period return is an explicit 0%.
    anchor_ts = balance.index[0] - pd.Timedelta(seconds=1)
    daily_equity = build_anchored_series(
        CAPITAL, anchor_ts, balance.values, balance.index)
    ma_metrics = metrics_from_equity(daily_equity, CAPITAL)

    buys = [t for t in trades if t.direction == Direction.LONG]
    sells = [t for t in trades if t.direction == Direction.SHORT]
    # Primary MTM activity: only actual vn.py trades (no artificial terminal exit).
    ma_metrics["entries"] = len(buys)
    ma_metrics["exits"] = len(sells)
    ma_metrics["n_trades"] = len(trades)
    turnover = sum(t.volume * t.price for t in trades)
    ma_metrics["primary_turnover"] = round(turnover, 2)
    ma_metrics["annualized_turnover"] = round(turnover / CAPITAL / ma_metrics["years"], 4)
    ma_metrics["realized_stamp_duty"] = round(
        sum(t.volume * t.price for t in sells) * STAMP_DUTY, 2)
    # Conservative-capital disclosure: the gap buffer caps deployed capital
    # below 100% (≈ 1/gap_buffer before lot rounding).
    ma_metrics["gap_buffer"] = GAP_BUFFER
    ma_metrics["deployed_fraction_approx"] = round(1 / GAP_BUFFER, 4)
    # Optional terminal liquidation via the shared helper (MA may end with an
    # open position; primary final equity is mark-to-market).
    final_shares = sum(t.volume for t in buys) - sum(t.volume for t in sells)
    last_close = float(df["close_price"].iloc[-1])
    ma_metrics.update(terminal_liquidation(
        ma_metrics["final_equity"], final_shares, last_close,
        COMMISSION_RATE, SLIPPAGE, STAMP_DUTY,
    ))
    ma_metrics["liquidated_cagr"] = round(
        (ma_metrics["liquidated_final_equity"] / CAPITAL) ** (1 / ma_metrics["years"]) - 1, 4)
    # Liquidated-view activity (terminal sale included when a position remains).
    ma_metrics["liquidated_exits"] = len(sells) + (1 if final_shares > 0 else 0)
    liq_turnover = turnover + final_shares * last_close
    ma_metrics["liquidated_total_turnover"] = round(liq_turnover, 2)
    ma_metrics["liquidated_annualized_turnover"] = round(
        liq_turnover / CAPITAL / ma_metrics["years"], 4)
    ma_metrics["final_shares"] = int(final_shares)

    # Buy & Hold
    bh_metrics = run_buy_and_hold(bars, args.start)

    delta = {
        "delta_sharpe": round(ma_metrics["sharpe"] - bh_metrics["sharpe"], 4),
        "delta_maxdd": round(ma_metrics["max_drawdown"] - bh_metrics["max_drawdown"], 4),
        # Primary (mark-to-market) CAGR deltas on the common convention.
        "delta_cagr": round(ma_metrics["cagr"] - bh_metrics["cagr"], 4),
        "delta_cagr_liquidated": round(
            ma_metrics["liquidated_cagr"] - bh_metrics["liquidated_cagr"], 4),
    }

    summary = {
        "symbol": SYMBOL,
        "data_source": "miniQMT (xtdata, 后复权/back-adjust, 含现金分红与送转)",
        "analysis_window": f"{args.start} -> {args.end}",
        "bars_loaded": len(bars),
        "buy_and_hold": bh_metrics,
        "ma_regime": ma_metrics,
        "delta": delta,
        "trade_side_effects": {
            "orders_submitted": 0,
            "orders_cancelled": 0,
            "fills": 0,
        },
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
