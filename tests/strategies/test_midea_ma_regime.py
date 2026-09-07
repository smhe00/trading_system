"""Unit tests for the Midea MA-regime timing baseline (no live data needed).

The strategy is driven through a small execution harness that crosses
pending orders at the NEXT bar's open (like vnpy_ctastrategy's backtester),
so next-bar execution, gap-ups, cash and position invariants can be tested
deterministically.
"""
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
    build_anchored_series,
    compute_ma,
    ma_regime_signal,
    size_board_lots,
    terminal_liquidation,
)

BASE = datetime(2020, 1, 1)


def make_bar(i: int, close: float, open_price: float | None = None) -> BarData:
    o = open_price if open_price is not None else close * 0.99
    return BarData(
        symbol="000333",
        exchange=Exchange.SZSE,
        datetime=BASE + timedelta(days=i),
        interval=Interval.DAILY,
        open_price=o,
        high_price=max(o, close) * 1.01,
        low_price=min(o, close) * 0.99,
        close_price=close,
        volume=10000.0,
        gateway_name="test",
    )


def bars_from_closes(closes, opens=None) -> list:
    return [make_bar(i, c, opens[i] if opens else None) for i, c in enumerate(closes)]


class FakeEngine:
    def write_log(self, msg, strategy=None):
        pass


class RecordingStrategy(MaRegimeStrategy):
    """Records orders and crosses them at the next bar's open via feed()."""

    def __init__(self, **setting):
        super().__init__(FakeEngine(), "test", "000333.SZ", setting)
        self.buy_orders = []      # (price, volume) placed
        self.sell_orders = []
        self.pending = []         # (direction, volume, limit_price)
        self.fill_log = []        # (direction, volume, fill_price)
        self.min_pos = 0.0

    def buy(self, price, volume, stop=False, lock=False, net=False):
        self.buy_orders.append((price, volume))
        self.pending.append((Direction.LONG, volume, price))
        return []

    def sell(self, price, volume, stop=False, lock=False, net=False):
        self.sell_orders.append((price, volume))
        self.pending.append((Direction.SHORT, volume, price))
        return []

    def fill(self, direction, volume, price):
        self.fill_log.append((direction, volume, price))
        if direction == Direction.LONG:
            self.pos += volume
        else:
            self.pos -= volume
        self.min_pos = min(self.min_pos, self.pos)
        trade = TradeData(
            symbol="000333", exchange=Exchange.SZSE, orderid="1", tradeid="1",
            direction=direction, price=price, volume=volume,
            datetime=BASE, gateway_name="test",
        )
        self.on_trade(trade)      # updates the cash ledger


def feed(strategy: RecordingStrategy, bars: list) -> None:
    """Cross pending orders at each bar's open, then run on_bar."""
    for bar in bars:
        pending, strategy.pending = strategy.pending, []
        for direction, volume, limit in pending:
            if direction == Direction.LONG:
                fill_price = min(limit, bar.open_price)
            else:
                fill_price = max(limit, bar.open_price)
            strategy.fill(direction, volume, fill_price)
        strategy.on_bar(bar)


def uptrend(n=200, start=100.0, step=0.5):
    return [start + step * i for i in range(n)]


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
        self.assertFalse(ma_regime_signal(close=9, ma_fast=11, ma_mid=10, ma_slow=10))
        self.assertFalse(ma_regime_signal(close=11, ma_fast=9, ma_mid=10, ma_slow=10))

    def test_missing_inputs_are_cash(self):
        self.assertFalse(ma_regime_signal(None, 11, 10, 10))
        self.assertFalse(ma_regime_signal(11, None, 10, 10))


class WarmupAndStartGateTests(unittest.TestCase):
    def test_no_signal_before_sufficient_history(self):
        s = RecordingStrategy()
        feed(s, bars_from_closes([100.0] * 120))
        self.assertFalse(s.am.inited)
        self.assertEqual(s.buy_orders, [])
        self.assertEqual(s.sell_orders, [])

    def test_prestart_bars_warm_indicators_but_cannot_trade(self):
        # analysis_start far beyond the fed bars -> every bar is pre-start.
        s = RecordingStrategy(analysis_start=(BASE + timedelta(days=400)).strftime("%Y%m%d"))
        feed(s, bars_from_closes(uptrend()))
        self.assertTrue(s.am.inited)          # warmed by pre-start bars
        self.assertEqual(s.buy_orders, [])    # ...but no trade allowed
        self.assertEqual(s.sell_orders, [])
        self.assertEqual(s.pos, 0)
        self.assertEqual(s.cash, s.target_capital)


class StrategyBehaviorTests(unittest.TestCase):
    def test_cash_to_long_only_when_both_conditions_hold(self):
        s = RecordingStrategy()
        feed(s, bars_from_closes(uptrend()))
        self.assertEqual(len(s.buy_orders), 1)     # single all-in entry
        price, volume = s.buy_orders[0]
        self.assertEqual(volume % 100, 0)          # board lot
        self.assertGreater(volume, 0)
        # first inited bar is index 120 (close = 100 + 0.5*120 = 160.0)
        self.assertAlmostEqual(price, 160.0 * 1.15)

    def test_long_to_cash_when_condition_fails(self):
        s = RecordingStrategy()
        feed(s, bars_from_closes(uptrend()))
        buy_vol = s.buy_orders[0][1]
        # one filler bar crosses the buy at its open
        feed(s, bars_from_closes([200.0]))
        self.assertGreater(s.pos, 0)
        # sharp decline breaks close > MA120 (and MA20 > MA60)
        decline = [199.5 - 2.0 * j for j in range(40)]
        feed(s, bars_from_closes(decline))
        self.assertEqual(len(s.sell_orders), 1)
        price, volume = s.sell_orders[0]
        self.assertEqual(volume, buy_vol)          # full exit, never a short
        feed(s, bars_from_closes([120.0]))
        self.assertEqual(s.pos, 0)
        self.assertGreaterEqual(s.min_pos, 0)

    def test_no_short_position_state(self):
        s = RecordingStrategy()
        feed(s, bars_from_closes(uptrend()))
        feed(s, bars_from_closes([200.0]))         # fill buy
        feed(s, bars_from_closes([199.5 - 2.0 * j for j in range(80)]))  # exit + stay out
        self.assertEqual(len(s.sell_orders), 1)
        self.assertEqual(s.pos, 0)
        self.assertGreaterEqual(s.min_pos, 0)

    def test_orders_use_wide_limits_for_next_bar_open(self):
        s = RecordingStrategy()
        feed(s, bars_from_closes(uptrend()))
        buy_price, volume = s.buy_orders[0]
        self.assertAlmostEqual(buy_price, 160.0 * 1.15)
        feed(s, bars_from_closes([200.0]))
        decline = [199.5 - 2.0 * j for j in range(40)]
        feed(s, bars_from_closes(decline))
        self.assertEqual(len(s.sell_orders), 1)
        sell_price, sell_vol = s.sell_orders[0]
        self.assertEqual(sell_vol, volume)
        self.assertIn(round(sell_price / 0.85, 4), [round(c, 4) for c in decline])


class GapUpCashTests(unittest.TestCase):
    """Entry sizing must not create negative cash on a next-bar gap-up."""

    def test_gap_up_fill_keeps_cash_non_negative(self):
        # 150 flat bars (warm) then a rising tail -> LONG fires, then a gap-up.
        closes = [100.0] * 150 + [100 + 10 * k for k in range(1, 16)]
        signal_idx = 150          # close=110 at index 150 fires LONG
        gap_open = closes[signal_idx] * 1.10        # next bar opens +10%
        opens = [None] * len(closes)
        opens[signal_idx + 1] = gap_open
        s = RecordingStrategy()
        feed(s, bars_from_closes(closes, opens))

        self.assertEqual(len(s.buy_orders), 1)
        self.assertGreater(len(s.fill_log), 0)
        fill = s.fill_log[0]
        self.assertEqual(fill[0], Direction.LONG)
        self.assertAlmostEqual(fill[2], gap_open)   # filled at the gap-up open
        self.assertGreaterEqual(s.cash, 0.0)        # no synthetic leverage
        self.assertGreaterEqual(s.pos, 0)
        self.assertGreaterEqual(s.min_pos, 0)


class CostAwareLedgerTests(unittest.TestCase):
    """The sizing cash ledger must deduct the engine's commission/slippage."""

    RATE = 0.0003
    SLIP = 0.01

    def make(self):
        return RecordingStrategy(commission_rate=self.RATE, slippage_per_share=self.SLIP)

    def expected(self, cash, direction, volume, price):
        notional = volume * price
        cost = notional * self.RATE + volume * self.SLIP
        return cash - notional - cost if direction == Direction.LONG else cash + notional - cost

    def test_buy_reduces_cash_by_notional_plus_costs(self):
        s = self.make()
        s.fill(Direction.LONG, 1000, 10.0)
        expected = self.expected(s.target_capital, Direction.LONG, 1000, 10.0)
        self.assertAlmostEqual(s.cash, expected, places=6)
        self.assertAlmostEqual(s.cash, 1_000_000 - 10_000 - 3 - 10, places=6)

    def test_sell_adds_proceeds_net_of_costs(self):
        s = self.make()
        s.fill(Direction.LONG, 1000, 10.0)
        after_buy = s.cash
        s.fill(Direction.SHORT, 1000, 12.0)
        expected = self.expected(after_buy, Direction.SHORT, 1000, 12.0)
        self.assertAlmostEqual(s.cash, expected, places=6)

    def test_multi_round_trip_ledger_does_not_drift(self):
        s = self.make()
        trips = [
            (Direction.LONG, 500, 8.0),
            (Direction.SHORT, 500, 9.0),
            (Direction.LONG, 400, 7.5),
            (Direction.SHORT, 400, 8.8),
            (Direction.LONG, 600, 9.5),
            (Direction.SHORT, 600, 10.2),
        ]
        expected = s.target_capital
        for direction, volume, price in trips:
            s.fill(direction, volume, price)
            expected = self.expected(expected, direction, volume, price)
        self.assertAlmostEqual(s.cash, expected, places=6)
        # Gross-only accounting would have drifted above the cost-aware ledger.
        gross_expected = s.target_capital
        for direction, volume, price in trips:
            gross_expected += volume * price if direction == Direction.SHORT else -volume * price
        self.assertGreater(gross_expected, s.cash)


class BoardLotSizingTests(unittest.TestCase):
    """size_board_lots must reserve buy costs before selecting the lot."""

    def test_reserves_buy_costs(self):
        # capital=100k, price=1.00: naive notional sizing would buy 100,000
        # shares costing 100,000 + 30 + 1,000 = 101,030 > capital.
        naive = int(100_000 / 1.0 / 100) * 100
        self.assertEqual(naive, 100_000)
        naive_cost = naive * 1.0 * (1 + 0.0003) + naive * 0.01
        self.assertGreater(naive_cost, 100_000)      # naive would overdraw

        shares = size_board_lots(100_000, 1.0, 0.0003, 0.01, 100)
        self.assertEqual(shares, 98_900)             # one lot fewer
        self.assertEqual(shares % 100, 0)
        cost = shares * 1.0 * (1 + 0.0003) + shares * 0.01
        self.assertLessEqual(cost, 100_000)
        self.assertGreaterEqual(100_000 - cost, 0)   # residual cash >= 0

    def test_zero_when_no_full_lot_fits(self):
        self.assertEqual(size_board_lots(1.0, 10.0, 0.0003, 0.01, 100), 0)
        self.assertEqual(size_board_lots(0.0, 10.0, 0.0003, 0.01, 100), 0)


class TerminalLiquidationTests(unittest.TestCase):
    """Shared terminal-liquidation helper used by B&H and MA alike."""

    RATE = 0.0003
    SLIP = 0.01
    STAMP = 0.0005

    def test_open_position_liquidation_deducts_all_costs(self):
        equity = 1_000_000.0
        shares, price = 10_000, 90.0
        notional = shares * price
        commission = notional * self.RATE
        slippage = shares * self.SLIP
        stamp = notional * self.STAMP
        res = terminal_liquidation(
            equity, shares, price, self.RATE, self.SLIP, self.STAMP)
        self.assertEqual(res["terminal_sell_commission"], round(commission, 2))
        self.assertEqual(res["terminal_sell_slippage"], round(slippage, 2))
        self.assertEqual(res["terminal_stamp_duty"], round(stamp, 2))
        self.assertEqual(
            res["liquidated_final_equity"],
            round(equity - commission - slippage - stamp, 2),
        )

    def test_flat_position_liquidation_is_zero(self):
        res = terminal_liquidation(
            1_000_000.0, 0, 90.0, self.RATE, self.SLIP, self.STAMP)
        self.assertEqual(res["liquidated_final_equity"], 1_000_000.0)
        self.assertEqual(res["liquidation_adjustment"], 0.0)
        for key in ("terminal_sell_commission", "terminal_sell_slippage",
                    "terminal_stamp_duty"):
            self.assertEqual(res[key], 0.0)


class TerminalConventionTests(unittest.TestCase):
    """B&H and MA must share the same start/terminal valuation conventions."""

    def _engine_last_balance(self, bars, analysis_start="", capital=1_000_000):
        from vnpy_ctastrategy.backtesting import BacktestingEngine

        engine = BacktestingEngine()
        engine.set_parameters(
            vt_symbol="000333.SZSE", interval=Interval.DAILY,
            start=BASE, rate=0.0003, slippage=0.01,
            size=1.0, pricetick=0.01, capital=capital,
        )
        engine.add_strategy(MaRegimeStrategy, {"analysis_start": analysis_start})
        engine.history_data = bars
        engine.run_backtesting()
        df = engine.calculate_result()
        trades = engine.get_all_trades()
        return engine, df, trades

    def test_ma_ending_long_liquidation_matches_helper(self):
        # Uptrend keeps the MA LONG at the end -> open position held.
        engine, df, trades = self._engine_last_balance(bars_from_closes(uptrend()))
        balance = engine.capital + df["net_pnl"].cumsum()
        primary = float(balance.iloc[-1])
        buys = [t for t in trades if t.direction == Direction.LONG]
        sells = [t for t in trades if t.direction == Direction.SHORT]
        final_shares = sum(t.volume for t in buys) - sum(t.volume for t in sells)
        self.assertGreater(final_shares, 0)          # ends with an open position
        last_close = float(df["close_price"].iloc[-1])
        expected = terminal_liquidation(
            primary, final_shares, last_close, 0.0003, 0.01, 0.0005)
        self.assertLess(expected["liquidated_final_equity"], primary)
        self.assertGreater(expected["liquidation_adjustment"], 0.0)
        self.assertGreater(expected["terminal_stamp_duty"], 0.0)

    def test_ma_ending_flat_liquidation_is_zero(self):
        # Uptrend then sharp decline -> exits and stays flat at the end.
        closes = uptrend() + [199.5 - 2.0 * j for j in range(80)]
        engine, df, trades = self._engine_last_balance(bars_from_closes(closes))
        balance = engine.capital + df["net_pnl"].cumsum()
        primary = float(balance.iloc[-1])
        buys = [t for t in trades if t.direction == Direction.LONG]
        sells = [t for t in trades if t.direction == Direction.SHORT]
        final_shares = sum(t.volume for t in buys) - sum(t.volume for t in sells)
        self.assertEqual(final_shares, 0)            # flat at the end
        last_close = float(df["close_price"].iloc[-1])
        expected = terminal_liquidation(
            primary, final_shares, last_close, 0.0003, 0.01, 0.0005)
        self.assertAlmostEqual(expected["liquidated_final_equity"], primary, places=2)
        self.assertAlmostEqual(expected["liquidation_adjustment"], 0.0, places=6)

    def test_buy_and_hold_uses_same_anchor_and_liquidation_convention(self):
        from scripts.midea_timing_backtest import run_buy_and_hold

        bars = bars_from_closes(uptrend())
        bh = run_buy_and_hold(bars, "20200101")
        self.assertEqual(bh["start_equity"], 1_000_000.0)     # explicit anchor
        shares = bh["shares"]
        end_price = bh["end_price"]
        # Primary final equity is mark-to-market (open position, no terminal
        # exit cost deducted) -> it must exceed the liquidated value.
        self.assertGreater(bh["final_equity"], bh["liquidated_final_equity"])
        # Liquidated view must match the shared helper exactly.
        expected = terminal_liquidation(
            bh["final_equity"], shares, end_price, 0.0003, 0.01, 0.0005)
        self.assertEqual(bh["liquidated_final_equity"],
                         expected["liquidated_final_equity"])
        self.assertEqual(bh["terminal_sell_commission"],
                         expected["terminal_sell_commission"])
        self.assertEqual(bh["terminal_stamp_duty"],
                         expected["terminal_stamp_duty"])


class MetricAlignmentTests(unittest.TestCase):
    """B&H and MA must share the same start anchor / duration / period basis
    and keep primary MTM activity metrics free of artificial terminal exits."""

    ANNUAL_DAYS = 240

    def _run_ma(self, bars, analysis_start):
        import pandas as pd
        from vnpy_ctastrategy.backtesting import BacktestingEngine

        engine = BacktestingEngine()
        engine.set_parameters(
            vt_symbol="000333.SZSE", interval=Interval.DAILY, start=BASE,
            rate=0.0003, slippage=0.01, size=1.0, pricetick=0.01,
            capital=1_000_000,
        )
        engine.add_strategy(MaRegimeStrategy, {"analysis_start": analysis_start})
        engine.history_data = bars
        engine.run_backtesting()
        df = engine.calculate_result()
        bal = engine.capital + df["net_pnl"].cumsum()
        bal.index = pd.to_datetime(bal.index)
        bal = bal[bal.index >= pd.to_datetime(analysis_start)]
        anchor_ts = bal.index[0] - pd.Timedelta(seconds=1)
        series = build_anchored_series(1_000_000.0, anchor_ts, bal.values, bal.index)
        return series

    def test_anchored_series_shape_and_first_period_return(self):
        ts0 = BASE - timedelta(seconds=1)
        ts1, ts2 = BASE, BASE + timedelta(days=1)
        s = build_anchored_series(1_000_000.0, ts0, [1_050_000.0, 1_100_000.0], [ts1, ts2])
        self.assertEqual(len(s), 3)                  # anchor + N closes
        self.assertEqual(s.iloc[0], 1_000_000.0)     # explicit start-open anchor
        self.assertLess(s.index[0], s.index[1])      # unambiguous timestamps
        # First-period return (anchor -> first close) is a real observation.
        self.assertAlmostEqual(s.pct_change().dropna().iloc[0], 0.05)

    def test_ma_first_analysis_day_is_explicit_zero_return(self):
        start_date = (BASE + timedelta(days=150)).strftime("%Y%m%d")
        s = self._run_ma(bars_from_closes(uptrend()), start_date)
        self.assertEqual(s.iloc[0], 1_000_000.0)
        self.assertAlmostEqual(
            float(s.pct_change().dropna().iloc[0]), 0.0, places=6)

    def test_bh_and_ma_same_period_count_and_years(self):
        from scripts.midea_timing_backtest import run_buy_and_hold

        bars = bars_from_closes(uptrend())
        start_date = (BASE + timedelta(days=150)).strftime("%Y%m%d")
        bh = run_buy_and_hold(bars, start_date)
        ma_series = self._run_ma(bars, start_date)
        ma_period_count = len(ma_series) - 1
        self.assertEqual(bh["period_count"], ma_period_count)
        self.assertEqual(bh["years"], round(ma_period_count / self.ANNUAL_DAYS, 4))
        self.assertGreater(bh["period_count"], 0)

    def test_bh_primary_activity_is_clean_mtm(self):
        from scripts.midea_timing_backtest import run_buy_and_hold

        bars = bars_from_closes(uptrend())
        bh = run_buy_and_hold(bars, "20200101")
        self.assertEqual(bh["entries"], 1)
        self.assertEqual(bh["exits"], 0)                  # no terminal exit in primary
        self.assertEqual(bh["realized_stamp_duty"], 0.0)  # no realized sell
        self.assertEqual(bh["primary_turnover"],
                         round(bh["shares"] * bh["start_price"], 2))
        self.assertEqual(bh["liquidated_exits"], 1)       # optional view adds the exit


class NextBarExecutionTests(unittest.TestCase):
    """Integration: real vn.py backtester, gated by analysis_start."""

    def _run_engine(self, bars, analysis_start):
        from vnpy_ctastrategy.backtesting import BacktestingEngine

        engine = BacktestingEngine()
        engine.set_parameters(
            vt_symbol="000333.SZSE", interval=Interval.DAILY,
            start=BASE, rate=0.0003, slippage=0.01,
            size=1.0, pricetick=0.01, capital=1_000_000,
        )
        engine.add_strategy(MaRegimeStrategy, {"analysis_start": analysis_start})
        engine.history_data = bars            # this vnpy_ctastrategy version has no add_data()
        engine.run_backtesting()
        return engine

    def test_no_prestart_trade_and_fill_on_next_bar_after_start(self):
        bars = bars_from_closes(uptrend())
        start_date = (BASE + timedelta(days=150)).strftime("%Y%m%d")
        engine = self._run_engine(bars, start_date)
        trades = engine.get_all_trades()
        self.assertTrue(trades)

        start_dt = datetime.strptime(start_date, "%Y%m%d")
        # No trade may occur before analysis_start.
        self.assertTrue(all(t.datetime >= start_dt for t in trades))
        # First eligible signal (index 150, first bar >= start) fills on the
        # NEXT tradable bar (index 151).
        self.assertEqual(trades[0].datetime.date(), bars[151].datetime.date())

    def test_starting_equity_is_exactly_common_capital(self):
        import pandas as pd

        bars = bars_from_closes(uptrend())
        start_date = (BASE + timedelta(days=150)).strftime("%Y%m%d")
        engine = self._run_engine(bars, start_date)
        df = engine.calculate_result()
        df = df.copy()
        df["balance"] = df["net_pnl"].cumsum() + engine.capital
        df.index = pd.to_datetime(df.index)
        start_balance = df["balance"][df.index >= pd.to_datetime(start_date)].iloc[0]
        self.assertAlmostEqual(start_balance, engine.capital, places=4)


if __name__ == "__main__":
    unittest.main()
