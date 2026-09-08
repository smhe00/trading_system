"""Deterministic tests for the vnpy.alpha context-feature challenger V2 helpers."""
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
    make_purge_processor,
)
from src.trader.strategies.midea_timing.ml_context_research import (
    V2_EXTRA_FEATURES,
    V2_FEATURES,
    era_contained,
)

BASE = datetime(2020, 1, 1)
V1_NAMES = ["ret_5", "ret_20", "ret_60", "vol_20", "vol_60",
            "close_ma20", "close_ma60", "close_ma120", "ma20_ma60", "ma60_ma120"]
V2_ADDITIONS = ["volume_ratio20", "range_20", "mkt_ret20", "mkt_ret60",
                "mkt_vol20", "rel_ret20", "rel_ret60"]


def make_bars(closes, start=BASE):
    return [
        BarData(
            symbol="000333", exchange=Exchange.SZSE,
            datetime=start + timedelta(days=i), interval=Interval.DAILY,
            open_price=c * 0.99, high_price=c * 1.01, low_price=c * 0.98,
            close_price=c, volume=10000.0 + i, gateway_name="test",
        )
        for i, c in enumerate(closes)
    ]


def ctx_df(closes, mkt, volumes=None, highs=None, lows=None, n=200):
    vols = volumes or [10000.0 + i for i in range(n)]
    highs = highs or [c * 1.01 for c in closes]
    lows = lows or [c * 0.98 for c in closes]
    return pl.DataFrame({
        "datetime": [BASE + timedelta(days=i) for i in range(n)],
        "vt_symbol": ["000333.SZSE"] * n,
        "open": [c * 0.99 for c in closes],
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": vols,
        "mkt_close": mkt,
    })


class FeatureNameTests(unittest.TestCase):
    def test_v1_names_exact(self):
        self.assertEqual(list(FROZEN_FEATURES), V1_NAMES)

    def test_v2_names_are_v1_plus_exactly_seven(self):
        self.assertEqual(set(V2_ADDITIONS), set(V2_EXTRA_FEATURES))
        self.assertEqual(len(V2_ADDITIONS), 7)
        self.assertEqual(set(V2_FEATURES), set(V1_NAMES) | set(V2_ADDITIONS))
        self.assertEqual(len(V2_FEATURES), 17)


class V2FeatureSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.n = 200
        self.closes = [100.0 + i for i in range(self.n)]
        self.mkt = [3000.0 + i for i in range(self.n)]
        self.vols = [10000.0 + i for i in range(self.n)]
        self.df = ctx_df(self.closes, self.mkt, self.vols, n=self.n)

    def test_features_do_not_depend_on_future_prices(self):
        t = 150
        # mutate data strictly AFTER t (index 160) -> feature at t unchanged
        for name in V2_FEATURES:
            before = self.df.select(V2_FEATURES[name].alias("f"))["f"][t]
            changed = ctx_df(
                self.closes[:160] + [9999.0] + self.closes[161:],
                self.mkt[:160] + [99999.0] + self.mkt[161:],
                self.vols[:160] + [999999.0] + self.vols[161:],
                n=self.n,
            )
            after = changed.select(V2_FEATURES[name].alias("f"))["f"][t]
            self.assertEqual(before, after, f"{name} leaked future data")

    def test_volume_ratio20_trailing(self):
        f = self.df.select(V2_FEATURES["volume_ratio20"].alias("f"))["f"]
        t = 150
        ma20 = sum(self.vols[t - 19:t + 1]) / 20
        self.assertAlmostEqual(f[t], self.vols[t] / ma20 - 1.0)

    def test_range_20_trailing(self):
        f = self.df.select(V2_FEATURES["range_20"].alias("f"))["f"]
        t = 150
        vals = [(self.closes[i] * 1.01 - self.closes[i] * 0.98) / self.closes[i]
                for i in range(t - 19, t + 1)]
        self.assertAlmostEqual(f[t], sum(vals) / 20)

    def test_mkt_ret_exact_horizons(self):
        f20 = self.df.select(V2_FEATURES["mkt_ret20"].alias("f"))["f"]
        f60 = self.df.select(V2_FEATURES["mkt_ret60"].alias("f"))["f"]
        self.assertAlmostEqual(f20[150], self.mkt[150] / self.mkt[130] - 1.0)
        self.assertAlmostEqual(f60[150], self.mkt[150] / self.mkt[90] - 1.0)

    def test_rel_ret_exact_definitions(self):
        f20 = self.df.select(V2_FEATURES["rel_ret20"].alias("f"))["f"]
        t = 150
        stock = self.closes[t] / self.closes[t - 20] - 1
        mkt = self.mkt[t] / self.mkt[t - 20] - 1
        self.assertAlmostEqual(f20[t], stock - mkt)


class JoinTests(unittest.TestCase):
    def test_exact_date_join_no_fill_missing_excluded(self):
        from scripts.midea_vnpy_alpha_context_challenger import build_v2_raw_df

        bars = make_bars([100.0 + i for i in range(60)])
        dates = [b.datetime.strftime("%Y%m%d") for b in bars]
        mkt = {d: 3000.0 + i for i, d in enumerate(dates) if d != dates[30]}
        df, stats = build_v2_raw_df(bars, mkt)
        self.assertEqual(stats["excluded_rows"], 1)
        self.assertEqual(stats["excluded_range"], (dates[30], dates[30]))
        self.assertEqual(len(df), 59)
        self.assertNotIn(dates[30], set(df["datetime"].dt.strftime("%Y%m%d").to_list()))
        # no fill: the row before the gap keeps its own mkt_close, not a carry
        self.assertEqual(df["mkt_close"][29], 3000.0 + 29)


class LabelContainmentTests(unittest.TestCase):
    def test_fit_and_valid_boundaries(self):
        bars = make_bars([100.0 + i for i in range(460)], start=datetime(2019, 11, 1))
        tgt = {}
        for i, b in enumerate(bars):
            tgt[b.datetime] = bars[i + 20].datetime if i + 20 < len(bars) else None
        proc = make_purge_processor(tgt, "2019-12-31", "2020-12-31")
        feat_cols = list(FROZEN_FEATURES)
        df = pl.DataFrame({
            "datetime": [datetime(2019, 12, 1), datetime(2019, 12, 20),
                         datetime(2020, 6, 1), datetime(2020, 12, 20)],
            "vt_symbol": ["000333.SZSE"] * 4,
            **{c: [1.0] * 4 for c in feat_cols},
            "label": [0.1] * 4,
        })
        out = proc(df)
        kept = {datetime(2019, 12, 1), datetime(2020, 6, 1)}
        self.assertEqual(set(out["datetime"].to_list()), kept)


class EraContainmentTests(unittest.TestCase):
    def test_requires_both_t_and_t_plus_20_inside_era(self):
        bars = make_bars([100.0 + i for i in range(60)], start=datetime(2020, 12, 1))
        tgt = {}
        for i, b in enumerate(bars):
            tgt[b.datetime] = bars[i + 20].datetime if i + 20 < len(bars) else None
        pairs = [
            {"date": "20201205", "pred": 0.1, "realized": 0.05},   # t+20 in 2020 -> kept
            {"date": "20201220", "pred": 0.1, "realized": 0.05},   # t+20 in 2021 -> excluded
        ]
        kept = era_contained(pairs, tgt, "20201201", "20201231")
        self.assertEqual([p["date"] for p in kept], ["20201205"])


class WorkflowIdentityTests(unittest.TestCase):
    def test_execution_reuses_accepted_chronological_simulator(self):
        import scripts.midea_vnpy_alpha_context_challenger as ctx_script
        from src.trader.strategies.midea_timing import ml_research

        self.assertIs(ctx_script.simulate_ml, ml_research.simulate_ml)

    def test_windows_reset_to_1m_flat(self):
        from scripts.midea_vnpy_alpha_lightgbm_challenger import finalize_metrics
        from src.trader.strategies.midea_timing.ml_research import simulate_ml

        bars = make_bars([100.0 + i for i in range(100)])
        pred = {b.datetime.strftime("%Y%m%d"): 0.2 for b in bars}
        sim = simulate_ml(bars, pred, "20200101", "20200409")
        m = finalize_metrics(bars, sim["rows"], sim["trades"], "20200101", "20200409")
        self.assertEqual(m["start_equity"], 1_000_000.0)

    def test_target_is_exact_y20(self):
        df = ctx_df([100.0 + i for i in range(60)],
                    [3000.0 + i for i in range(60)], n=60)
        y = df.select(LABEL_Y20.alias("y"))["y"]
        self.assertAlmostEqual(y[10], (100.0 + 30) / (100.0 + 10) - 1.0)

    def test_locked_ma_parameters_unchanged(self):
        self.assertEqual(MaRegimeStrategy.fast_window, 20)
        self.assertEqual(MaRegimeStrategy.mid_window, 60)
        self.assertEqual(MaRegimeStrategy.slow_window, 120)
        self.assertEqual(MaRegimeStrategy.gap_buffer, 1.20)


if __name__ == "__main__":
    unittest.main()
