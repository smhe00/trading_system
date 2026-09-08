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
    """Picklable, segment-aware ``learn`` processor enforcing label containment.

    Implements the official AlphaDataset.add_processor extension point with
    per-segment target-date containment:

        FIT row   (t <= fit_end)  : keep only if t+20 target date <= fit_end
        VALID row (t > fit_end)   : keep only if t+20 target date <= valid_end

    This guarantees no VALID-period price enters a FIT label and no OOS-period
    price enters a VALID label (valid_end is the last day of the declared
    training window, strictly before OOS). Rows with missing (null/NaN)
    features/label are also dropped. Module-level and picklable so the dataset
    can be persisted through the official AlphaLab.
    """

    def __init__(self, target_date_map: dict, fit_end: str, valid_end: str):
        self.target_date_map = target_date_map
        self.fit_end = fit_end
        self.valid_end = valid_end
        self.feat_cols = list(FROZEN_FEATURES)

    def __call__(self, df: pl.DataFrame) -> pl.DataFrame:
        fit_end_dt = datetime.strptime(self.fit_end, "%Y-%m-%d")
        valid_end_dt = datetime.strptime(self.valid_end, "%Y-%m-%d")
        tgt = pl.Series([self.target_date_map.get(d) for d in df["datetime"]])
        df = df.with_columns(tgt.alias("__tgt"))
        max_target = pl.when(pl.col("datetime") <= fit_end_dt).then(fit_end_dt).otherwise(valid_end_dt)
        df = df.filter(
            pl.col("__tgt").is_not_null()
            & (pl.col("__tgt") <= max_target)
        ).drop("__tgt")
        for col in self.feat_cols + ["label"]:
            df = df.filter(
                pl.col(col).is_not_null() & (~pl.col(col).is_nan()))
        return df


def make_purge_processor(target_date_map: dict, fit_end: str, valid_end: str) -> BoundaryPurgeProcessor:
    """Build the picklable segment-aware purge processor (see class)."""
    return BoundaryPurgeProcessor(target_date_map, fit_end, valid_end)


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
    """Chronological pending-order ML timing simulation (locked conventions).

    Per bar ``t`` the simulator is strictly chronological:

      A. BAR OPEN / INTRABAR — process only an order already pending from a
         prior signal bar (mutate cash/position only here):
           BUY  fills when ``bar.low  <= buy_limit``  at ``min(open, buy_limit)``
           SELL fills when ``bar.high >= sell_limit`` at ``max(open, sell_limit)``
         otherwise the order stays pending.
      B. BAR CLOSE — mark equity using the position actually held at t close.
      C. AFTER CLOSE — read the t state (LONG iff predicted_y20 > 0) and
         create/cancel a SINGLE pending order that cannot execute before the
         next tradable bar.

    Hard invariant: no bar-t equity value depends on bar t+1 data. An initial
    LONG signal on the first bar keeps that bar's close equity at 1,000,000
    (still flat); the earliest possible fill is the next tradable bar. A
    no-fill order remains pending until it fills or the desired state changes
    (then it is cancelled) — it never suppresses the target state, and no
    duplicate pending orders are stacked.

    Buy sizing follows the locked conservative-capital convention: size at the
    signal close with ``max price = signal_close * gap_buffer`` and buy costs
    reserved; ``buy_limit = signal_close * 1.15``. Exit uses the symmetric
    ``sell_limit = signal_close * 0.85``. Long-only.
    """
    window = [b for b in bars
              if window_start <= b.datetime.strftime("%Y%m%d") <= window_end]
    if not window:
        raise RuntimeError(f"empty ML window {window_start}..{window_end}")

    cash = float(capital)
    pos = 0
    pending = None       # {"side": "BUY"/"SELL", "limit": float, "volume": int}
    rows = []            # (date_str, equity)
    trades = []          # {"direction": "LONG"/"SELL", "date", "price", "volume"}

    for b in window:
        date_str = b.datetime.strftime("%Y%m%d")

        # A. process pending order at this bar's open
        if pending is not None:
            if pending["side"] == "BUY":
                if b.low_price <= pending["limit"]:
                    fill = min(b.open_price, pending["limit"])
                    vol = pending["volume"]
                    cash -= vol * fill * (1 + commission_rate) + vol * slippage
                    pos = vol
                    trades.append({
                        "direction": "LONG", "date": date_str,
                        "price": fill, "volume": vol,
                    })
                    pending = None
            else:  # SELL
                if b.high_price >= pending["limit"]:
                    fill = max(b.open_price, pending["limit"])
                    vol = pos
                    cash += vol * fill * (1 - commission_rate) - vol * slippage
                    trades.append({
                        "direction": "SELL", "date": date_str,
                        "price": fill, "volume": vol,
                    })
                    pos = 0
                    pending = None

        # B. mark equity at close with the position held at t close
        rows.append((date_str, cash + pos * b.close_price))

        # C. after close: decide desired target state and manage the pending order
        pred = pred_by_date.get(date_str)
        desired_long = pred is not None and pred > 0
        if desired_long:
            if pos == 0:
                if pending is None:
                    max_price = b.close_price * gap_buffer
                    target = size_board_lots(
                        cash, max_price, commission_rate, slippage, lot_size)
                    if target >= lot_size:
                        pending = {
                            "side": "BUY",
                            "limit": b.close_price * 1.15,
                            "volume": target,
                        }
                elif pending["side"] == "SELL":
                    pending = None          # state back to LONG: cancel exit
            else:
                if pending is not None and pending["side"] == "SELL":
                    pending = None          # already long: cancel stale exit
        else:  # desired CASH
            if pos > 0:
                if pending is None:
                    pending = {
                        "side": "SELL",
                        "limit": b.close_price * 0.85,
                        "volume": pos,
                    }
                elif pending["side"] == "BUY":
                    pending = None          # state back to CASH: cancel entry
            else:
                if pending is not None and pending["side"] == "BUY":
                    pending = None          # flat and want cash: cancel stale entry

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
