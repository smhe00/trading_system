"""Midea A-share timing baseline backtest (research/backtest only).

Compares Buy & Hold with an MA-regime timing strategy on 000333.SZ daily
data using the official vn.py CTA backtest infrastructure.

Usage:
    python scripts/midea_timing_backtest.py --csv work/midea_000333_daily_back.csv
    python scripts/midea_timing_backtest.py --fetch   # pull from local miniQMT
"""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trader.strategies.midea_timing import MaRegimeStrategy

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


def run_ma_backtest(bars: list):
    """Run the MA-regime strategy through vnpy_ctastrategy BacktestingEngine."""
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
    engine.add_strategy(MaRegimeStrategy, {})
    engine.history_data = bars            # this vnpy_ctastrategy version has no add_data()
    engine.run_backtesting()
    df = engine.calculate_result()
    trades = engine.get_all_trades()
    return engine, df, trades


def metrics_from_equity(balance):
    """CAGR / annualized vol / Sharpe / MaxDD / Calmar from a daily balance series."""
    import pandas as pd

    s = balance.dropna()
    if len(s) < 2:
        return {}
    years = len(s) / ANNUAL_DAYS
    start_v = s.iloc[0]
    end_v = s.iloc[-1]
    cagr_curve = (end_v / start_v) ** (1 / years) - 1
    daily_ret = s.pct_change().dropna()
    ann_vol = daily_ret.std(ddof=1) * math.sqrt(ANNUAL_DAYS)
    sharpe = (daily_ret.mean() * ANNUAL_DAYS) / ann_vol if ann_vol else float("nan")
    max_dd = -(s / s.cummax() - 1).min()
    calmar = cagr_curve / max_dd if max_dd else float("nan")
    return {
        "final_equity": round(float(end_v), 2),
        "cagr": round(cagr_curve, 4),
        "annualized_vol": round(ann_vol, 4),
        "sharpe": round(sharpe, 4),
        "max_drawdown": round(max_dd, 4),
        "calmar": round(calmar, 4),
        "years": round(years, 2),
    }


def run_buy_and_hold(bars: list, start: str) -> dict:
    """Buy at the analysis-window open, hold, sell at the last close.

    Models board-lot rounding, commission, slippage; stamp duty on the
    terminal sell is reported separately.
    """
    import pandas as pd

    from vnpy.trader.constant import Direction

    window = [b for b in bars if b.datetime.strftime("%Y%m%d") >= start]
    if not window:
        raise RuntimeError("empty analysis window for Buy & Hold")
    first = window[0]
    last = window[-1]

    start_price = first.open_price
    end_price = last.close_price
    shares = int(CAPITAL / start_price / LOT_SIZE) * LOT_SIZE
    if shares < LOT_SIZE:
        raise RuntimeError("capital too small for one board lot")

    buy_cost = shares * start_price * COMMISSION_RATE + shares * SLIPPAGE
    sell_value = shares * end_price
    sell_cost = sell_value * COMMISSION_RATE + shares * SLIPPAGE
    stamp = sell_value * STAMP_DUTY
    remaining_cash = CAPITAL - shares * start_price - buy_cost
    proceeds = sell_value - sell_cost - stamp
    final_equity = remaining_cash + proceeds

    daily_equity = pd.Series(
        {b.datetime: shares * b.close_price - buy_cost for b in window}
    ).sort_index()
    metrics = metrics_from_equity(daily_equity)
    metrics["final_equity"] = round(final_equity, 2)
    metrics["cagr"] = round((final_equity / CAPITAL) ** (1 / metrics["years"]) - 1, 4)
    metrics["entries"] = 1
    metrics["exits"] = 1
    metrics["stamp_duty"] = round(stamp, 2)
    metrics["shares"] = shares
    metrics["start_price"] = round(start_price, 3)
    metrics["end_price"] = round(end_price, 3)
    metrics["total_turnover"] = round(
        shares * start_price + sell_value, 2)
    metrics["annualized_turnover"] = round(
        (shares * start_price + sell_value) / CAPITAL / metrics["years"], 4)
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
    engine, df, trades = run_ma_backtest(bars)
    import pandas as pd
    df = df.copy()
    df["balance"] = df["net_pnl"].cumsum() + engine.capital
    df.index = pd.to_datetime(df.index)
    balance = df["balance"][df.index >= pd.to_datetime(args.start)]
    ma_metrics = metrics_from_equity(balance)

    buys = [t for t in trades if t.direction == Direction.LONG]
    sells = [t for t in trades if t.direction == Direction.SHORT]
    ma_metrics["entries"] = len(buys)
    ma_metrics["exits"] = len(sells)
    ma_metrics["n_trades"] = len(trades)
    turnover = sum(t.volume * t.price for t in trades)
    ma_metrics["total_turnover"] = round(turnover, 2)
    ma_metrics["annualized_turnover"] = round(turnover / CAPITAL / ma_metrics["years"], 4)
    stamp = sum(t.volume * t.price for t in sells) * STAMP_DUTY
    ma_metrics["stamp_duty"] = round(stamp, 2)
    # Net-of-stamp final equity / CAGR (engine already nets commission+slippage)
    net_final = ma_metrics["final_equity"] - stamp
    ma_metrics["final_equity_net"] = round(net_final, 2)
    ma_metrics["cagr_net"] = round(
        (net_final / CAPITAL) ** (1 / ma_metrics["years"]) - 1, 4)

    # Buy & Hold
    bh_metrics = run_buy_and_hold(bars, args.start)

    delta = {
        "delta_sharpe": round(ma_metrics["sharpe"] - bh_metrics["sharpe"], 4),
        "delta_maxdd": round(ma_metrics["max_drawdown"] - bh_metrics["max_drawdown"], 4),
        "delta_cagr": round(ma_metrics["cagr_net"] - bh_metrics["cagr"], 4),
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
