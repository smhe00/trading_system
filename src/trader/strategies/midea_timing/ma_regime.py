"""MA-regime timing baseline for a single A-share (research/backtest only).

Signal rule (binary position state):
    LONG/HOLD  when  close > MA_slow  AND  MA_fast > MA_mid
    CASH       otherwise
Position state is 0% or 100%; A-share long-only (no short selling).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from vnpy.trader.constant import Direction
from vnpy.trader.object import BarData
from vnpy.trader.utility import ArrayManager
from vnpy_ctastrategy import CtaTemplate


def compute_ma(closes: Optional[list], window: int) -> Optional[float]:
    """Rolling simple moving average of the last ``window`` closes.

    Returns None until at least ``window`` values are available (warm-up).
    Uses only past/current data — no look-ahead.
    """
    if not closes or window <= 0 or len(closes) < window:
        return None
    return sum(closes[-window:]) / window


def ma_regime_signal(close, ma_fast, ma_mid, ma_slow) -> bool:
    """LONG condition: close > MA_slow AND MA_fast > MA_mid.

    Returns False (CASH) when any input is missing.
    """
    if None in (close, ma_fast, ma_mid, ma_slow):
        return False
    return close > ma_slow and ma_fast > ma_mid


def size_board_lots(
    cash: float,
    price: float,
    commission_rate: float,
    slippage_per_share: float,
    lot_size: int = 100,
) -> int:
    """Largest multiple of ``lot_size`` whose total buy cash requirement fits.

    Total buy requirement = notional + commission + slippage:
        shares * price * (1 + commission_rate) + shares * slippage_per_share
    must not exceed ``cash``, so residual cash can never go negative from the
    modeled buy costs. Returns 0 when no full lot fits.
    """
    if cash <= 0 or price <= 0 or lot_size <= 0:
        return 0
    per_share_cost = price * (1 + commission_rate) + slippage_per_share
    return int(cash / per_share_cost / lot_size) * lot_size


def build_anchored_series(
    anchor_value: float,
    anchor_timestamp,
    close_values,
    close_timestamps,
):
    """Build one scored equity series used identically by both baselines:

        point 0: analysis-start-open anchor (common initial equity)
        point 1..N: one close-marked equity point per analysis trading bar

    ``anchor_timestamp`` must be strictly before the first close timestamp so
    the index is unambiguous (no duplicate datetimes). Both B&H and MA use
    this shape, giving them the same number of scored return periods.
    """
    import pandas as pd

    anchor = pd.Series([float(anchor_value)], index=[anchor_timestamp])
    closes = pd.Series(list(close_values), index=list(close_timestamps))
    series = pd.concat([anchor, closes])
    return series


def terminal_liquidation(
    equity: float,
    shares: float,
    price: float,
    commission_rate: float,
    slippage_per_share: float,
    stamp_duty: float,
) -> dict:
    """Optional terminal-liquidation accounting for a position still held at
    the final close.

    When ``shares`` > 0, liquidated equity = ``equity`` minus the same
    terminal sell commission, per-share slippage and stamp duty assumptions
    used by the baseline; when ``shares`` == 0 the adjustment is zero and
    liquidated equity equals ``equity``.

    This is used identically for Buy & Hold and the MA regime (shared
    convention). No fake trade is ever injected into the vn.py trade history.
    """
    if shares <= 0:
        return {
            "liquidated_final_equity": round(float(equity), 2),
            "liquidation_adjustment": 0.0,
            "terminal_sell_commission": 0.0,
            "terminal_sell_slippage": 0.0,
            "terminal_stamp_duty": 0.0,
        }
    notional = shares * price
    commission = notional * commission_rate
    slippage = shares * slippage_per_share
    stamp = notional * stamp_duty
    adjustment = commission + slippage + stamp
    return {
        "liquidated_final_equity": round(float(equity - adjustment), 2),
        "liquidation_adjustment": round(adjustment, 2),
        "terminal_sell_commission": round(commission, 2),
        "terminal_sell_slippage": round(slippage, 2),
        "terminal_stamp_duty": round(stamp, 2),
    }


class MaRegimeStrategy(CtaTemplate):
    """Conservative-capital MA-regime timing for a long-only A-share daily
    backtest.

    Position state is 0% or "conservative long": when the LONG condition
    holds the strategy invests up to ~all current equity, rounded down to
    board lots, but reserves a worst-case next-bar gap (``gap_buffer``) plus
    buy-side costs — so typical deployed capital is below 100% (≈1/gap_buffer
    before lot rounding) and cash can never go negative. When CASH it is
    flat. The cost-aware cash ledger tracks economic cash across round trips.

    ``analysis_start`` ("YYYYMMDD") gates trading: bars before it may only
    warm the MA indicators — no order is submitted or filled before it, so
    both strategies always start the scored window flat with the common
    initial capital.
    """

    author = "agent"

    fast_window = 20
    mid_window = 60
    slow_window = 120
    lot_size = 100
    target_capital = 1_000_000.0
    analysis_start = ""
    commission_rate = 0.0003
    slippage_per_share = 0.01
    gap_buffer = 1.20

    parameters = [
        "fast_window", "mid_window", "slow_window", "lot_size", "target_capital",
        "analysis_start", "commission_rate", "slippage_per_share", "gap_buffer",
    ]
    variables = ["last_price", "cash"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        self.am = ArrayManager(size=self.slow_window + 1)
        self.last_price = 0.0
        self.cash = self.target_capital
        self.start_dt = (
            datetime.strptime(self.analysis_start, "%Y%m%d")
            if self.analysis_start else datetime.min
        )

    def on_init(self) -> None:
        """History is fed through the backtest engine's add_data, so the
        ArrayManager warms up naturally during replay (no DB load)."""
        self.write_log("MaRegimeStrategy init")

    def on_start(self) -> None:
        self.write_log("MaRegimeStrategy start")

    def on_stop(self) -> None:
        self.write_log("MaRegimeStrategy stop")

    def on_bar(self, bar: BarData) -> None:
        self.am.update_bar(bar)
        if not self.am.inited:
            self.write_log(f"MA warm-up: {len(self.am.close)}/{self.slow_window}")
            return
        self.last_price = bar.close_price

        # Bars before analysis_start may warm indicators but must not trade.
        if bar.datetime < self.start_dt:
            return

        close = self.am.close[-1]
        ma_fast = self.am.sma(self.fast_window)
        ma_mid = self.am.sma(self.mid_window)
        ma_slow = self.am.sma(self.slow_window)

        long_condition = ma_regime_signal(close, ma_fast, ma_mid, ma_slow)

        if long_condition and self.pos == 0:
            # All-in on current equity, rounded down to the board lot (100).
            # Conservative sizing: reserve a worst-case next-open gap
            # (gap_buffer) plus buy commission and slippage, so the modeled
            # fill can never exceed available cash (no synthetic leverage).
            # This is a "conservative-capital MA regime": the gap buffer
            # deliberately caps deployed capital below 100%.
            max_price = bar.close_price * self.gap_buffer
            target = size_board_lots(
                self.cash, max_price, self.commission_rate,
                self.slippage_per_share, self.lot_size,
            )
            if target >= self.lot_size:
                # Wide limit so the backtester fills at the NEXT bar's open
                # (next-tradable-bar execution; no same-close look-ahead).
                self.buy(price=bar.close_price * 1.15, volume=target)
        elif not long_condition and self.pos > 0:
            self.sell(price=bar.close_price * 0.85, volume=self.pos)

    def on_order(self, order) -> None:
        pass

    def on_trade(self, trade) -> None:
        """Update the cost-aware cash ledger used for future entry sizing.

        The ledger deducts the same buy/sell commission and per-share
        slippage assumptions passed to the backtest engine, so it stays
        aligned with economic cash across repeated round trips. Stamp duty
        is NOT included here — it is handled and disclosed separately for
        this baseline (not charged by the vn.py engine either).
        """
        notional = trade.volume * trade.price
        cost = notional * self.commission_rate + trade.volume * self.slippage_per_share
        if trade.direction == Direction.LONG:
            self.cash -= notional + cost
        else:
            self.cash += notional - cost
        self.write_log(
            f"trade {trade.direction.value} vol={trade.volume} px={trade.price:.3f}"
        )

    def on_stop_order(self, stop_order) -> None:
        pass
