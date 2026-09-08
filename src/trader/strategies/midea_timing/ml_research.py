"""Pure research helpers for the Midea vnpy.alpha / LightGBM challenger.

Provides the frozen feature/label polars expressions, the walk-forward fold
schedules, the boundary-purge learn processor, the deterministic ML timing
simulation (same execution/cost conventions as the locked baseline) and a
generic static-Buy&Hold-at-a-fraction helper. The heavy official vnpy.alpha
workflow (AlphaDataset / LgbModel / AlphaLab) lives in the challenger
script; this module stays import-safe and unit-testable.
"""
from __future__ import annotations

import math
from datetime import datetime

import polars as pl

from .ma_regime import size_board_lots

ANNUAL_DAYS = 240
LOT_SIZE = 100
GAP_BUFFER = 1.20
COMMISSION_RATE = 0.0003
SLIPPAGE = 0.01
STAMP_DUTY = 0.0005
CAPITAL = 1_000_000.0

# Frozen feature set (selected before seeing ML results; backward-looking only:
# every feature at date t uses information available through t close).
FROZEN_FEATURES = {
    "ret_5": pl.col("close") / pl.col("close").shift(5) - 1,
    "ret_20": pl.col("close") / pl.col("close").shift(20) - 1,
    "ret_60": pl.col("close") / pl.col("close").shift(60) - 1,
    "vol_20": (
        pl.col("close").pct_change().rolling_std(
            window_size=20, min_periods=20) * math.sqrt(ANNUAL_DAYS)
    ),
    "vol_60": (
        pl.col("close").pct_change().rolling_std(
            window_size=60, min_periods=60) * math.sqrt(ANNUAL_DAYS)
    ),
    "close_ma20": (
        pl.col("close") / pl.col("close").rolling_mean(
            window_size=20, min_periods=20) - 1
    ),
    "close_ma60": (
        pl.col("close") / pl.col("close").rolling_mean(
            window_size=60, min_periods=60) - 1
    ),
    "close_ma120": (
        pl.col("close") / pl.col("close").rolling_mean(
            window_size=120, min_periods=120) - 1
    ),
    "ma20_ma60": (
        pl.col("close").rolling_mean(window_size=20, min_periods=20)
        / pl.col("close").rolling_mean(window_size=60, min_periods=60) - 1
    ),
    "ma60_ma120": (
        pl.col("close").rolling_mean(window_size=60, min_periods=60)
        / pl.col("close").rolling_mean(window_size=120, min_periods=120) - 1
    ),
}

# Frozen target: y20[t] = close[t+20] / close[t] - 1 (regression).
LABEL_Y20 = pl.col("close").shift(-20) / pl.col("close") - 1


def fold_schedule(oos_years: list, train_years: int) -> list:
    """Annual walk-forward folds with a NON-OVERLAPPING fit/valid split.

    For each OOS year ``Y`` the declared training window is the prior
    ``train_years`` full calendar years (``Y-train_years-01-01 ..
    Y-1-12-31``). The official LgbModel mandates a validation segment for
    early stopping, so that declared window is split deterministically and
    without overlap:

        fit   = declared window minus its last calendar year
        valid = the last calendar year of the declared window

    Early-stopping feedback therefore never overlaps the fit rows, and no
    OOS (test) data is used. Returns a dict per fold with ``declared_train``,
    ``fit``, ``valid``, ``test`` as (start, end) date strings.
    """
    out = []
    for y in oos_years:
        declared_start = f"{y - train_years}-01-01"
        declared_end = f"{y - 1}-12-31"
        valid_start = f"{y - 1}-01-01"
        out.append({
            "declared_train": (declared_start, declared_end),
            "fit": (declared_start, f"{y - 2}-12-31"),
            "valid": (valid_start, declared_end),
            "test": (f"{y}-01-01", f"{y}-12-31"),
        })
    return out


class BoundaryPurgeProcessor:
    """Picklable ``learn`` processor enforcing the boundary purge.

    Implements the official AlphaDataset.add_processor extension point. A
    training row is kept only when its y20 label target date (t+20) is inside
    the training interval (never crossing into the OOS test period) and when
    features/label are fully available (null OR NaN dropped, since
    prepare_data fills nulls with NaN). Module-level and picklable so the
    dataset can be persisted through the official AlphaLab.
    """

    def __init__(self, target_date_map: dict, train_end: str):
        self.target_date_map = target_date_map
        self.train_end = train_end
        self.feat_cols = list(FROZEN_FEATURES)

    def __call__(self, df: pl.DataFrame) -> pl.DataFrame:
        train_end_dt = datetime.strptime(self.train_end, "%Y-%m-%d")
        tgt = pl.Series([self.target_date_map.get(d) for d in df["datetime"]])
        df = df.with_columns(tgt.alias("__tgt"))
        df = df.filter(
            pl.col("__tgt").is_not_null()
            & (pl.col("__tgt") <= train_end_dt)
        ).drop("__tgt")
        for col in self.feat_cols + ["label"]:
            df = df.filter(
                pl.col(col).is_not_null() & (~pl.col(col).is_nan()))
        return df


def make_purge_processor(target_date_map: dict, train_end: str) -> BoundaryPurgeProcessor:
    """Build the picklable boundary-purge learn processor (see class)."""
    return BoundaryPurgeProcessor(target_date_map, train_end)


def simulate_ml(
    bars,
    pred_by_date: dict,
    window_start: str,
    window_end: str,
    capital: float = CAPITAL,
    commission_rate: float = COMMISSION_RATE,
    slippage: float = SLIPPAGE,
    lot_size: int = LOT_SIZE,
    gap_buffer: float = GAP_BUFFER,
):
    """Deterministic next-bar ML timing simulation with locked conventions.

    State per day: LONG iff predicted_y20 > 0, else CASH. The window starts
    flat (position 0); an initial LONG signal is actionable and enters on the
    next tradable bar (a first-state CASH does nothing).

    Entry sizing mirrors the locked MaRegimeStrategy convention: the size
    decision is made on the signal bar using ONLY information through its
    close — ``max price = signal_close * gap_buffer``, buy costs reserved,
    100-share lots. A buy limit of ``signal_close * 1.15`` (locked baseline)
    fills on the next bar at ``min(limit, next_open)`` only if the next bar
    traded down to the limit (``next_low <= limit``); a gap entirely above
    the limit is handled explicitly as a no-fill (never silently assumed
    filled). Exits fill at the next bar's open. Long-only; only transitions
    trade (no redundant daily orders).
    """
    window = [b for b in bars
              if window_start <= b.datetime.strftime("%Y%m%d") <= window_end]
    if not window:
        raise RuntimeError(f"empty ML window {window_start}..{window_end}")

    cash = float(capital)
    pos = 0
    prev_state = "CASH"      # window starts flat; initial LONG is actionable
    rows = []                # (date_str, equity)
    trades = []              # {"direction": "LONG"/"SELL", "date", "price", "volume"}

    for i, b in enumerate(window):
        date_str = b.datetime.strftime("%Y%m%d")
        pred = pred_by_date.get(date_str)
        state = "LONG" if (pred is not None and pred > 0) else "CASH"

        if state != prev_state and i + 1 < len(window):
            nxt = window[i + 1]
            if state == "LONG":
                # Size decision on the signal bar using only information
                # through t close (locked conservative-capital convention).
                max_price = b.close_price * gap_buffer
                target = size_board_lots(
                    cash, max_price, commission_rate, slippage, lot_size)
                limit = b.close_price * 1.15
                # Next-bar fill only if the bar can execute the limit order.
                if target >= lot_size and nxt.low_price <= limit:
                    fill = min(limit, nxt.open_price)
                    cash -= target * fill * (1 + commission_rate) + target * slippage
                    pos = target
                    trades.append({
                        "direction": "LONG",
                        "date": nxt.datetime.strftime("%Y%m%d"),
                        "price": fill,
                        "volume": target,
                    })
            else:
                if pos > 0:
                    cash += pos * nxt.open_price * (1 - commission_rate) - pos * slippage
                    trades.append({
                        "direction": "SELL",
                        "date": nxt.datetime.strftime("%Y%m%d"),
                        "price": nxt.open_price,
                        "volume": pos,
                    })
                    pos = 0

        prev_state = state
        rows.append((date_str, cash + pos * b.close_price))

    return {
        "rows": rows,
        "trades": trades,
        "cash": cash,
        "pos": pos,
        "last_close": window[-1].close_price,
    }


def run_static_bh_fraction(
    bars,
    window_start: str,
    window_end: str,
    fraction: float,
    capital: float = CAPITAL,
    commission_rate: float = COMMISSION_RATE,
    slippage: float = SLIPPAGE,
    lot_size: int = LOT_SIZE,
):
    """Static Buy & Hold at a target exposure ``fraction`` of capital:
    cost-aware board-lot sizing, residual + un-deployed capital stays as
    cash, no rebalancing. Used for BH_STATIC_CONSERVATIVE (~1/gap_buffer)
    and the ex-post exposure-matched diagnostic."""
    window = [b for b in bars
              if window_start <= b.datetime.strftime("%Y%m%d") <= window_end]
    if not window:
        raise RuntimeError(f"empty static BH window {window_start}..{window_end}")
    first, last = window[0], window[-1]
    start_price = first.open_price
    target_cash = capital * fraction
    shares = size_board_lots(target_cash, start_price, commission_rate, slippage, lot_size)
    buy_cost = shares * start_price * commission_rate + shares * slippage
    remaining = capital - shares * start_price - buy_cost
    rows = [
        (b.datetime.strftime("%Y%m%d"), remaining + shares * b.close_price)
        for b in window
    ]
    trades = [{
        "direction": "LONG",
        "date": first.datetime.strftime("%Y%m%d"),
        "price": start_price,
        "volume": shares,
    }]
    return {
        "rows": rows,
        "trades": trades,
        "cash": remaining,
        "pos": shares,
        "last_close": last.close_price,
        "initial_deployed_fraction": round(shares * start_price / capital, 4),
    }
