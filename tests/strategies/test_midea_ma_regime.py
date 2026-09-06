"""Unit tests for the Midea MA-regime timing baseline (no live data needed)."""
import sys
from datetime import datetime, timedelta
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vnpy.trader.constant import Direction, Exchange, Interval
from vnpy.trader.object import BarData, TradeData

from src.trader.strategies.midea_timing import (
    MaRegimeStrategy,
    compute_ma,
    ma_regime_signal,
)


def make_bar(i: int, close: float) -> BarData:
    return BarData(
        symbol="000333",
        exchange=Exchange.SZSE,
        datetime=datetime(2020, 1, 1) + timedelta(days=i),
        interval=Interval.DAILY,
        open_price=close * 0.99,
        high_price=close * 1.01,
        low_price=close * 0.98,
        close_price=close,
        volume=10000.0,
        gateway_name="test",
    )


class FakeEngine:
    def write_log(self, msg, strategy=None):
        pass


class RecordingStrategy(MaRegimeStrategy):
    def __init__(self):
        super().__init__(FakeEngine(), "test", "000333.SZ", {})
        self.buy_calls = []
        self.sell_calls = []

    def _fill(self, direction, volume, price):
        # Mimic the backtester: position is updated by the engine, cash by
        # on_trade(). Calling on_trade() here updates the strategy cash ledger.
        if direction == Direction.LONG:
            self.pos += volume
        else:
            self.pos -= volume
        trade = TradeData(
            symbol="000333", exchange=Exchange.SZSE, orderid="1", tradeid="1",
            direction=direction, price=price, volume=volume,
            datetime=datetime(2020, 1, 1), gateway_name="test",
        )
        self.on_trade(trade)

    def buy(self, price, volume, stop=False, lock=False, net=False):
        self.buy_calls.append((price, volume))
        self._fill(Direction.LONG, volume, price)
        return []

    def sell(self, price, volume, stop=False, lock=False, net=False):
        self.sell_calls.append((price, volume))
        self._fill(Direction.SHORT, volume, price)
        return []


def feed(strategy, closes):
    for i, close in enumerate(closes):
        strategy.on_bar(make_bar(i, close))


class ComputeMaTests(unittest.TestCase):
    def test_none_before_window(self):
        self.assertIsNone(compute_ma([1, 2, 3], 5))
        self.assertIsNone(compute_ma(None, 5))
        self.assertIsNone(compute_ma([1, 2, 3], 0))

    def test_value_at_window(self):
        self.assertEqual(compute_ma([1, 2, 3, 4], 3), 3.0)
        self.assertEqual(compute_ma([10, 20, 30], 3), 20.0)


class MaRegimeSignalTests(unittest.TestCase):
    def test_long_only_when_both_conditions_hold(self):
        self.assertTrue(ma_regime_signal(close=11, ma_fast=11, ma_mid=10, ma_slow=10))
        # close not above slow MA
        self.assertFalse(ma_regime_signal(close=9, ma_fast=11, ma_mid=10, ma_slow=10))
        # fast MA not above mid MA
        self.assertFalse(ma_regime_signal(close=11, ma_fast=9, ma_mid=10, ma_slow=10))

    def test_missing_inputs_are_cash(self):
        self.assertFalse(ma_regime_signal(None, 11, 10, 10))
        self.assertFalse(ma_regime_signal(11, None, 10, 10))


class StrategyBehaviorTests(unittest.TestCase):
    def test_no_signal_before_sufficient_history(self):
        s = RecordingStrategy()
        # 120 bars < required warm-up (size = slow_window + 1 = 121)
        feed(s, [100.0] * 120)
        self.assertFalse(s.am.inited)
        self.assertEqual(s.buy_calls, [])
        self.assertEqual(s.sell_calls, [])

    def test_cash_to_long_only_when_both_conditions_hold(self):
        s = RecordingStrategy()
        # steady uptrend -> close > MA120 and MA20 > MA60
        feed(s, [100.0 + 0.5 * i for i in range(200)])
        self.assertTrue(s.am.inited)
        self.assertEqual(len(s.buy_calls), 1)      # single all-in entry
        price, volume = s.buy_calls[0]
        self.assertEqual(volume % 100, 0)          # board lot
        self.assertGreater(volume, 0)
        # first inited bar is index 120 (close = 100 + 0.5*120 = 160.0)
        self.assertAlmostEqual(price, 160.0 * 1.15)

    def test_long_to_cash_when_condition_fails(self):
        s = RecordingStrategy()
        feed(s, [100.0 + 0.5 * i for i in range(200)])
        self.assertEqual(len(s.buy_calls), 1)
        buy_vol = s.buy_calls[0][1]
        self.assertGreater(s.pos, 0)               # auto-filled
        # sharp decline breaks close > MA120 (and MA20 > MA60)
        feed(s, [199.5 - 2.0 * j for j in range(40)])
        self.assertEqual(len(s.sell_calls), 1)
        price, volume = s.sell_calls[0]
        self.assertEqual(volume, buy_vol)          # full exit, never a short
        self.assertEqual(s.pos, 0)

    def test_no_short_position_state(self):
        s = RecordingStrategy()
        feed(s, [100.0 + 0.5 * i for i in range(200)])
        feed(s, [199.5 - 2.0 * j for j in range(80)])
        self.assertEqual(len(s.sell_calls), 1)     # one full exit, then flat
        self.assertEqual(s.pos, 0)

    def test_orders_use_wide_limits_for_next_bar_open(self):
        s = RecordingStrategy()
        feed(s, [100.0 + 0.5 * i for i in range(200)])
        buy_price, volume = s.buy_calls[0]
        # buy limit = close * 1.15 -> backtester fills at next bar open
        self.assertAlmostEqual(buy_price, 160.0 * 1.15)
        decline = [199.5 - 2.0 * j for j in range(40)]
        feed(s, decline)
        self.assertEqual(len(s.sell_calls), 1)
        sell_price, sell_vol = s.sell_calls[0]
        self.assertEqual(sell_vol, volume)         # full exit, no short
        # sell limit = 0.85 * some fed close (discount -> next-open fill)
        self.assertIn(
            round(sell_price / 0.85, 4),
            [round(c, 4) for c in decline],
        )


class NextBarExecutionTests(unittest.TestCase):
    """Integration: the real vn.py backtester must fill on the bar AFTER the
    signal bar (no same-close look-ahead)."""

    def test_fill_is_on_next_bar_after_signal(self):
        from vnpy_ctastrategy.backtesting import BacktestingEngine

        closes = [100.0 + 0.5 * i for i in range(200)]
        bars = [make_bar(i, c) for i, c in enumerate(closes)]

        # Find the first bar index where the LONG condition turns true.
        from src.trader.strategies.midea_timing import compute_ma

        signal_idx = None
        for i in range(120, len(closes)):
            window = closes[: i + 1]
            ok = ma_regime_signal(
                closes[i],
                compute_ma(window, 20),
                compute_ma(window, 60),
                compute_ma(window, 120),
            )
            if ok:
                signal_idx = i
                break
        self.assertIsNotNone(signal_idx)

        engine = BacktestingEngine()
        engine.set_parameters(
            vt_symbol="000333.SZSE", interval=Interval.DAILY,
            start=datetime(2020, 1, 1), rate=0.0003, slippage=0.01,
            size=1.0, pricetick=0.01, capital=1_000_000,
        )
        engine.add_strategy(MaRegimeStrategy, {})
        engine.history_data = bars            # this vnpy_ctastrategy version has no add_data()
        engine.run_backtesting()
        trades = engine.get_all_trades()
        self.assertTrue(trades, "expected at least one trade")
        first_trade = trades[0]
        # Fill must occur at the bar AFTER the signal bar (next-tradable-bar).
        self.assertEqual(
            first_trade.datetime.date(),
            bars[signal_idx + 1].datetime.date(),
        )


if __name__ == "__main__":
    unittest.main()
