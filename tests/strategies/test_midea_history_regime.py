"""Deterministic tests for the Midea historical regime study helpers."""
import sys
from datetime import datetime, timedelta
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vnpy.trader.constant import Direction, Exchange, Interval
from vnpy.trader.object import BarData, TradeData

from src.trader.strategies.midea_timing.research import (
    forward_return,
    forward_returns,
    ma_state_at,
    position_series,
    select_regime_bars,
    sma_series,
    warmup_bars,
)
from src.trader.strategies.midea_timing import MaRegimeStrategy

BASE = datetime(2020, 1, 1)


def make_bars(closes, start=BASE):
    return [
        BarData(
            symbol="000333", exchange=Exchange.SZSE,
            datetime=start + timedelta(days=i), interval=Interval.DAILY,
            open_price=c * 0.99, high_price=c * 1.01, low_price=c * 0.98,
            close_price=c, volume=10000.0, gateway_name="test",
        )
        for i, c in enumerate(closes)
    ]


class RegimeBarSelectionTests(unittest.TestCase):
    def test_boundaries_inside_requested_interval(self):
        bars = make_bars([100.0 + i for i in range(400)], start=BASE - timedelta(days=50))
        sel = select_regime_bars(bars, "20200110", "20201231")
        self.assertTrue(sel)
        first = sel[0].datetime.strftime("%Y%m%d")
        last = sel[-1].datetime.strftime("%Y%m%d")
        self.assertGreaterEqual(first, "20200110")
        self.assertLessEqual(last, "20201231")

    def test_warmup_bars_strictly_before_start(self):
        bars = make_bars([100.0] * 300, start=BASE - timedelta(days=100))
        wu = warmup_bars(bars, "20200101", 130)
        self.assertLessEqual(len(wu), 130)
        self.assertTrue(all(b.datetime.strftime("%Y%m%d") < "20200101" for b in wu))

    def test_old_recent_boundaries_are_fixed(self):
        from scripts.midea_history_regime_study import REGIMES

        self.assertEqual(REGIMES["OLD"], ("20140401", "20201231"))
        self.assertEqual(REGIMES["RECENT"], ("20210101", "20260904"))


class ForwardReturnTests(unittest.TestCase):
    def test_r20_uses_exactly_t_plus_20(self):
        closes = [float(100 + i) for i in range(100)]
        r = forward_return(closes, 10, 20)
        self.assertAlmostEqual(r, closes[30] / closes[10] - 1.0)
        # changing an intermediate close (t+19) must NOT affect the R20 target
        closes[29] = 9999.0
        self.assertAlmostEqual(forward_return(closes, 10, 20), closes[30] / 110.0 - 1.0)
        # changing the exact target (t+20) DOES affect it
        closes[30] = 7777.0
        self.assertAlmostEqual(forward_return(closes, 10, 20), 7777.0 / 110.0 - 1.0)

    def test_r60_uses_exactly_t_plus_60(self):
        closes = [float(100 + i) for i in range(120)]
        r = forward_return(closes, 20, 60)
        self.assertAlmostEqual(r, closes[80] / closes[20] - 1.0)

    def test_tail_without_target_is_excluded_not_filled(self):
        closes = [float(1 + i) for i in range(50)]
        fr20 = forward_returns(closes, 20)
        self.assertEqual(fr20[-20:], [None] * 20)
        self.assertIsNotNone(fr20[-21])
        fr60 = forward_returns(closes, 60)
        self.assertTrue(all(v is None for v in fr60))


class PositionSeriesTests(unittest.TestCase):
    def _trade(self, i, direction, volume):
        return TradeData(
            symbol="000333", exchange=Exchange.SZSE, orderid="1", tradeid=str(i),
            direction=direction, price=100.0, volume=volume,
            datetime=BASE + timedelta(days=i), gateway_name="test",
        )

    def test_consistent_with_trades(self):
        trades = [
            self._trade(5, Direction.LONG, 1000),
            self._trade(10, Direction.SHORT, 400),
            self._trade(20, Direction.LONG, 200),
        ]
        dates = [(BASE + timedelta(days=i)).date() for i in range(25)]
        pos = position_series(trades, dates)
        self.assertEqual(pos[0], 0)
        self.assertEqual(pos[5], 1000)
        self.assertEqual(pos[9], 1000)
        self.assertEqual(pos[10], 600)
        self.assertEqual(pos[20], 800)
        self.assertEqual(len(pos), 25)


class FrozenBaselineTests(unittest.TestCase):
    def test_ma_parameters_are_frozen(self):
        self.assertEqual(MaRegimeStrategy.fast_window, 20)
        self.assertEqual(MaRegimeStrategy.mid_window, 60)
        self.assertEqual(MaRegimeStrategy.slow_window, 120)
        self.assertEqual(MaRegimeStrategy.gap_buffer, 1.20)
        self.assertEqual(MaRegimeStrategy.lot_size, 100)


class ComparatorBehaviorTests(unittest.TestCase):
    def test_regime_resets_flat_and_warmup_never_trades(self):
        from scripts.midea_history_regime_study import run_ma_fixed

        bars = make_bars([100.0 + 0.5 * i for i in range(400)],
                         start=BASE - timedelta(days=200))
        metrics = run_ma_fixed(bars, "20200101", "20201231")
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics["start_equity"], 1_000_000.0)  # flat at period start
        self.assertGreaterEqual(metrics["actual_start"], "20200101")
        self.assertLessEqual(metrics["actual_end"], "20201231")

    def test_static_conservative_no_rebalancing_and_lower_exposure(self):
        from scripts.midea_history_regime_study import (
            run_bh_static_conservative,
        )
        from scripts.midea_timing_backtest import run_buy_and_hold

        bars = make_bars([100.0 + 0.5 * i for i in range(300)])
        bh = run_buy_and_hold(bars, "20200101")
        sc = run_bh_static_conservative(bars, "20200101")
        self.assertEqual(sc["entries"], 1)
        self.assertEqual(sc["exits"], 0)                  # no rebalancing
        self.assertLessEqual(sc["shares"], bh["shares"])  # exposure <= full B&H
        self.assertGreaterEqual(sc["initial_deployed_fraction"], 0.0)
        self.assertLessEqual(sc["initial_deployed_fraction"], 1.0)


class StateDiagnosticTests(unittest.TestCase):
    def test_ma_state_only_uses_past(self):
        closes = [float(100 + i) for i in range(200)]
        ma20 = sma_series(closes, 20)
        ma60 = sma_series(closes, 60)
        ma120 = sma_series(closes, 120)
        self.assertIsNone(ma_state_at(closes, ma20, ma60, ma120, 118))   # not warmed
        self.assertIsNotNone(ma_state_at(closes, ma20, ma60, ma120, 119))
        # state at t must not depend on closes after t
        state_before = ma_state_at(closes, ma20, ma60, ma120, 130)
        closes_after = closes[:131] + [9999.0] * 69
        ma20b = sma_series(closes_after, 20)
        ma60b = sma_series(closes_after, 60)
        ma120b = sma_series(closes_after, 120)
        self.assertEqual(state_before, ma_state_at(closes_after, ma20b, ma60b, ma120b, 130))


if __name__ == "__main__":
    unittest.main()
