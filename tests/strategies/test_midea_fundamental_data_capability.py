"""Deterministic tests for the Midea fundamental/PIT data-capability audit
logic (pure helpers; no live data, no model)."""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trader.strategies.midea_timing.fundamental_pit import (
    build_as_of_panel,
    classify_feature,
    first_usable_trading_date,
)

WEEKDAYS = [date(2020, 1, 6) + timedelta(days=i) for i in range(10)]  # Mon..Wed


class AvailabilityGateTests(unittest.TestCase):
    def test_report_period_alone_never_activates(self):
        # a record with only endDate (report period) and NO disclosure date is
        # never usable -> first_usable returns None and panel excludes it.
        rec = {"disclosure_date": None, "record": {"endDate": "2020-12-31"}}
        panel = build_as_of_panel([rec], WEEKDAYS)
        self.assertTrue(all(not p["active_records"] for p in panel))

    def test_before_disclosure_cannot_see_new_quarter(self):
        disclosure = date(2020, 2, 3)     # Q4 disclosed on a Monday
        rec = {"disclosure_date": disclosure, "record": {"q": "Q4"}}
        panel = build_as_of_panel([rec], WEEKDAYS)
        # records only become active at the first trading date > disclosure
        for p in panel:
            if p["trading_date"] <= disclosure:
                self.assertEqual(p["active_records"], [])
            else:
                self.assertEqual(p["active_records"], [{"q": "Q4"}])

    def test_after_allowed_boundary_can_see(self):
        self.assertEqual(first_usable_trading_date(date(2020, 1, 6), WEEKDAYS,
                                                   "next_trading_day"), date(2020, 1, 7))
        self.assertEqual(first_usable_trading_date(date(2020, 1, 5), WEEKDAYS,
                                                   "next_trading_day"), date(2020, 1, 6))

    def test_same_day_disclosure_unknown_time_next_trading_day(self):
        # disclosure on a trading day with unknown time -> usable NEXT trading day
        d = date(2020, 1, 6)   # a trading day in WEEKDAYS
        self.assertEqual(first_usable_trading_date(d, WEEKDAYS, "next_trading_day"),
                         date(2020, 1, 7))

    def test_missing_disclosure_timestamp_fails_closed(self):
        self.assertIsNone(first_usable_trading_date(None, WEEKDAYS))
        panel = build_as_of_panel(
            [{"disclosure_date": None, "record": "x"}], WEEKDAYS)
        self.assertTrue(all(not p["active_records"] for p in panel))

    def test_no_backward_fill_of_future_fundamentals(self):
        # a record disclosed AFTER the window end never appears in the panel
        rec = {"disclosure_date": date(2021, 1, 4), "record": "future"}
        panel = build_as_of_panel([rec], WEEKDAYS)
        self.assertTrue(all(not p["active_records"] for p in panel))

    def test_midea_trading_dates_are_master_dates(self):
        master = [date(2020, 1, 6), date(2020, 1, 7), date(2020, 1, 8)]
        panel = build_as_of_panel(
            [{"disclosure_date": date(2020, 1, 6), "record": "r"}], master)
        self.assertEqual([p["trading_date"] for p in panel], master)


class RestatementTests(unittest.TestCase):
    def test_restated_value_does_not_overwrite_earlier_as_of_state(self):
        # first disclosure Q1 = 100 on 2020-04-20; restated Q1 = 105 disclosed
        # on 2020-08-01. The 100 must be visible between 04-21 and 07-31.
        dates = [date(2020, 4, 10) + timedelta(days=i) for i in range(140)]
        panel = build_as_of_panel([
            {"disclosure_date": date(2020, 4, 20), "record": {"q1": 100}},
            {"disclosure_date": date(2020, 8, 1), "record": {"q1": 105}},
        ], dates)
        seen_before_aug = [p["active_records"] for p in panel
                           if p["trading_date"] < date(2020, 8, 1)
                           and p["trading_date"] > date(2020, 4, 20)]
        self.assertTrue(all({"q1": 100} in r for r in seen_before_aug))
        # after Aug 1 the active set contains both versions (revision metadata
        # absent -> we do NOT silently overwrite; the panel keeps both and the
        # audit classifies the restatement risk explicitly).
        after = [p["active_records"] for p in panel if p["trading_date"] >= date(2020, 8, 3)]
        self.assertTrue(all({"q1": 100} in r and {"q1": 105} in r for r in after))


class FeatureFeasibilityTests(unittest.TestCase):
    def test_directly_available(self):
        self.assertEqual(
            classify_feature(["revenue"], {"revenue", "net_profit"}),
            "DIRECTLY_AVAILABLE")

    def test_derivable_pit_safe(self):
        # market_cap is not a raw field but derives from shares x price, both
        # of which are PIT-safe available.
        self.assertEqual(
            classify_feature(["market_cap"], {"total_shares", "price"},
                             derivable_from={"market_cap": ["total_shares", "price"]}),
            "DERIVABLE_PIT_SAFE")

    def test_unavailable(self):
        self.assertEqual(
            classify_feature(["sentiment"], {"revenue"}), "UNAVAILABLE")


class CapabilitySourceTests(unittest.TestCase):
    def test_installed_financial_apis_exist_with_signatures(self):
        from scripts.midea_fundamental_data_capability_audit import capability_from_source

        cap = capability_from_source()
        for name in ("download_financial_data", "get_financial_data",
                     "get_financial_data_ori"):
            self.assertNotEqual(cap["financial_api_members"][name], "MISSING")
            self.assertIn("report_type", cap["financial_api_members"]["get_financial_data"])
        self.assertIn("m_anntime", cap["date_fields_observed_in_raw_schema"])
        self.assertEqual(cap["table_mapping"]["Income"], "ASHAREINCOME")


if __name__ == "__main__":
    unittest.main()
