"""MA-regime timing baseline for a single A-share (research/backtest only).

Signal rule (binary position state):
    LONG/HOLD  when  close > MA_slow  AND  MA_fast > MA_mid
    CASH       otherwise
Position state is 0% or 100%; A-share long-only (no short selling).
"""
from __future__ import annotations

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


class MaRegimeStrategy(CtaTemplate):
    """Binary MA-regime timing for a long-only A-share daily backtest.

    Position state is 0% or 100%: when the LONG condition holds the strategy
    invests ~all current equity (rounded down to board lots); otherwise it is
    flat in cash. Equity is tracked by the strategy's own cash ledger updated
    on fills, so sizing compounds as equity grows.
    """

    author = "agent"

    fast_window = 20
    mid_window = 60
    slow_window = 120
    lot_size = 100
    target_capital = 1_000_000.0

    parameters = ["fast_window", "mid_window", "slow_window", "lot_size", "target_capital"]
    variables = ["last_price", "cash"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        self.am = ArrayManager(size=self.slow_window + 1)
        self.last_price = 0.0
        self.cash = self.target_capital

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

        close = self.am.close[-1]
        ma_fast = self.am.sma(self.fast_window)
        ma_mid = self.am.sma(self.mid_window)
        ma_slow = self.am.sma(self.slow_window)

        long_condition = ma_regime_signal(close, ma_fast, ma_mid, ma_slow)

        if long_condition and self.pos == 0:
            # All-in on current equity, rounded down to the board lot (100).
            equity = self.cash + self.pos * bar.close_price
            target = int(equity / bar.close_price / self.lot_size) * self.lot_size
            if target >= self.lot_size:
                # Wide limit so the backtester fills at the NEXT bar's open
                # (next-tradable-bar execution; no same-close look-ahead).
                self.buy(price=bar.close_price * 1.15, volume=target)
        elif not long_condition and self.pos > 0:
            self.sell(price=bar.close_price * 0.85, volume=self.pos)

    def on_order(self, order) -> None:
        pass

    def on_trade(self, trade) -> None:
        """Update the cash ledger. Position is updated by the engine/backtester."""
        if trade.direction == Direction.LONG:
            self.cash -= trade.volume * trade.price
        else:
            self.cash += trade.volume * trade.price
        self.write_log(
            f"trade {trade.direction.value} vol={trade.volume} px={trade.price:.3f}"
        )

    def on_stop_order(self, stop_order) -> None:
        pass
