"""Deterministic tests for the Midea vnpy.alpha / LightGBM challenger helpers.

These test the pure research layer (frozen features/label, fold schedule,
boundary purge, ML simulation, static-fraction B&H) without running heavy
model training.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import polars as pl

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData

from src.trader.strategies.midea_timing import MaRegimeStrategy
from src.trader.strategies.midea_timing.ml_research import (
    FROZEN_FEATURES,
    LABEL_Y20,
    fold_schedule,
    make_purge_processor,
    run_static_bh_fraction,
    simulate_ml,
)

BASE = datetime(2020, 1, 1)


def make_bars(closes, opens=None, start=BASE):
    bars = []
    for i, c in enumerate(closes):
        o = opens[i] if opens and i < len(opens) and opens[i] else c * 0.99
        bars.append(BarData(
            symbol="000333", exchange=Exchange.SZSE,
            datetime=start + timedelta(days=i), interval=Interval.DAILY,
            open_price=o, high_price=max(o, c) * 1.01, low_price=min(o, c) * 0.99,
            close_price=c, volume=10000.0, gateway_name="test",
        ))
    return bars


def closes_df(closes):
    return pl.DataFrame({
        "datetime": [BASE + timedelta(days=i) for i in range(len(closes))],
        "vt_symbol": ["000333.SZSE"] * len(closes),
        "close": closes,
    })


class FrozenFeatureTests(unittest.TestCase):
    def test_features_do_not_depend_on_future_closes(self):
        closes = [100.0 + i for i in range(160)]
        df = closes_df(closes)
        t = 100
        for name in FROZEN_FEATURES:
            before = df.select(FROZEN_FEATURES[name].alias("f"))["f"][t]
            changed = closes[:130] + [9999.0] + closes[131:]
            df2 = closes_df(changed)
            after = df2.select(FROZEN_FEATURES[name].alias("f"))["f"][t]
            self.assertEqual(before, after, f"feature {name} leaked future data")

    def test_all_features_backward_looking_and_null_until_warmup(self):
        closes = [100.0 + i for i in range(160)]
        df = closes_df(closes)
        for name, expr in FROZEN_FEATURES.items():
            col = df.select(expr.alias("f"))["f"]
            # first row must be null/None (shift/rolling not available)
            self.assertIsNone(col[0], f"feature {name} uses future data")


class LabelTests(unittest.TestCase):
    def test_y20_is_exactly_t_plus_20(self):
        closes = [100.0 + i for i in range(160)]
        df = closes_df(closes)
        y = df.select(LABEL_Y20.alias("y"))["y"]
        self.assertAlmostEqual(y[10], closes[30] / closes[10] - 1.0)
        # final 20 bars have no target -> excluded (null)
        self.assertTrue(all(v is None for v in y[-20:]))


class FoldScheduleTests(unittest.TestCase):
    def test_3y_train_is_exactly_prior_3_calendar_years(self):
        folds = fold_schedule([2018, 2024, 2026], 3)
        by_year = {f[4][:4]: f for f in folds}
        self.assertEqual(by_year["2018"][:2], ("2015-01-01", "2017-12-31"))
        self.assertEqual(by_year["2024"][:2], ("2021-01-01", "2023-12-31"))
        self.assertEqual(by_year["2026"][:2], ("2023-01-01", "2025-12-31"))
        self.assertEqual(by_year["2026"][4], "2026-01-01")
        self.assertEqual(len(folds), 3)                 # one fold per OOS year

    def test_5y_train_is_exactly_prior_5_calendar_years(self):
        folds = fold_schedule([2020, 2026], 5)
        by_year = {f[4][:4]: f for f in folds}
        self.assertEqual(by_year["2020"][:2], ("2015-01-01", "2019-12-31"))
        self.assertEqual(by_year["2026"][:2], ("2021-01-01", "2025-12-31"))

    def test_valid_is_last_train_year_and_test_is_oos_year(self):
        folds = fold_schedule([2021], 3)
        self.assertEqual(folds[0][2:4], ("2020-01-01", "2020-12-31"))
        self.assertEqual(folds[0][4:], ("2021-01-01", "2021-12-31"))


class PurgeProcessorTests(unittest.TestCase):
    def test_training_labels_do_not_cross_into_oos(self):
        bars = make_bars([100.0 + i for i in range(400)])
        tgt_map = {}
        for i, b in enumerate(bars):
            tgt_map[b.datetime] = bars[i + 20].datetime if i + 20 < len(bars) else None
        proc = make_purge_processor(tgt_map, "2020-12-31")
        # learn_df rows at 2020-12-20 (t+20 -> 2021-01-xx) must be dropped;
        # rows at 2020-12-01 (t+20 -> 2020-12-21) kept.
        feat_cols = list(FROZEN_FEATURES)
        df = pl.DataFrame({
            "datetime": [datetime(2020, 12, 1), datetime(2020, 12, 20)],
            "vt_symbol": ["000333.SZSE", "000333.SZSE"],
            **{c: [1.0, 1.0] for c in feat_cols},
            "label": [0.1, 0.1],
        })
        out = proc(df)
        self.assertEqual(len(out), 1)
        self.assertEqual(out["datetime"][0], datetime(2020, 12, 1))

    def test_null_label_rows_are_dropped(self):
        bars = make_bars([100.0 + i for i in range(40)])
        tgt_map = {b.datetime: None for b in bars}      # no valid targets
        proc = make_purge_processor(tgt_map, "2020-12-31")
        feat_cols = list(FROZEN_FEATURES)
        df = pl.DataFrame({
            "datetime": [datetime(2020, 1, 1)],
            "vt_symbol": ["000333.SZSE"],
            **{c: [1.0] for c in feat_cols},
            "label": [0.1],
        })
        self.assertEqual(len(proc(df)), 0)


class MlmSimulationTests(unittest.TestCase):
    def test_long_only_next_bar_execution_and_transitions(self):
        closes = [100.0] * 6
        opens = [99.0, 100.0, 101.0, 102.0, 103.0, 104.0]
        bars = make_bars(closes, opens=opens)
        # day1 CASH, day2 LONG (transition at day2 close -> fill day3 open),
        # day3 hold, day4 CASH (transition -> sell day5 open)
        pred = {"20200102": -0.1, "20200103": 0.2, "20200104": 0.1,
                "20200105": -0.2, "20200106": -0.1}
        res = simulate_ml(bars, pred, "20200101", "20200106")
        longs = [t for t in res["trades"] if t["direction"] == "LONG"]
        sells = [t for t in res["trades"] if t["direction"] == "SELL"]
        self.assertEqual(len(longs), 1)
        self.assertEqual(len(sells), 1)
        self.assertEqual(longs[0]["date"], "20200104")   # next bar after day2 signal
        self.assertEqual(sells[0]["date"], "20200106")   # next bar after day4 signal
        self.assertEqual(longs[0]["volume"] % 100, 0)    # board lot
        self.assertGreaterEqual(res["cash"], 0.0)        # no negative cash
        self.assertGreaterEqual(res["pos"], 0.0)         # long-only

    def test_hold_state_does_not_trade_redundantly(self):
        bars = make_bars([100.0] * 5)
        pred = {"20200102": 0.1, "20200103": 0.1, "20200104": 0.1, "20200105": 0.1}
        res = simulate_ml(bars, pred, "20200101", "20200105")
        longs = [t for t in res["trades"] if t["direction"] == "LONG"]
        self.assertLessEqual(len(longs), 1)              # no redundant daily orders


class StaticFractionTests(unittest.TestCase):
    def test_exposure_fraction_and_no_rebalancing(self):
        bars = make_bars([100.0 + i for i in range(100)])
        res = run_static_bh_fraction(bars, "20200101", "20200410", 0.5)
        self.assertAlmostEqual(res["initial_deployed_fraction"], 0.5, delta=0.02)
        longs = [t for t in res["trades"] if t["direction"] == "LONG"]
        sells = [t for t in res["trades"] if t["direction"] == "SELL"]
        self.assertEqual(len(longs), 1)
        self.assertEqual(len(sells), 0)                  # no rebalancing
        # full fraction equals full B&H sizing
        full = run_static_bh_fraction(bars, "20200101", "20200410", 1.0)
        self.assertGreaterEqual(full["pos"], res["pos"])


class FrozenBaselineTests(unittest.TestCase):
    def test_locked_ma_parameters_unchanged(self):
        self.assertEqual(MaRegimeStrategy.fast_window, 20)
        self.assertEqual(MaRegimeStrategy.mid_window, 60)
        self.assertEqual(MaRegimeStrategy.slow_window, 120)
        self.assertEqual(MaRegimeStrategy.gap_buffer, 1.20)


if __name__ == "__main__":
    unittest.main()
