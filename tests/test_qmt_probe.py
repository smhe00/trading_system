import contextlib
import io
import os
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

from scripts.qmt_probe import (
    ROOT, collect_snapshot, select_account, serializable_snapshot, to_vnpy, verify_vnpy,
)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.old_cwd = Path.cwd()
        os.chdir(ROOT)
        (ROOT / ".vntrader").mkdir(exist_ok=True)
        self.factory = lambda account_id, kind: NS(account_id=account_id, account_type=kind)
        self.account = NS(account_id="12345678", account_type=2)
        self.asset = NS(account_id="12345678", total_asset=10000., cash=1500.,
                        frozen_cash=200., market_value=8300.)
        self.position = NS(account_id="12345678", stock_code="600000.SH", volume=100,
                           can_use_volume=70, open_price=10.)
        self.trader = Mock()
        self.trader.connect.return_value = 0
        self.trader.subscribe.return_value = 0
        self.trader.query_account_infos.return_value = [self.account]
        self.trader.query_stock_asset.return_value = self.asset
        self.trader.query_stock_positions.return_value = [self.position]
        self.trader.query_stock_orders.return_value = []
        self.trader.query_stock_trades.return_value = []

    def tearDown(self):
        os.chdir(self.old_cwd)

    def collect(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return collect_snapshot(self.trader, self.factory, {2: "STOCK", 3: "CREDIT"})

    def test_account_type_mapping(self):
        account = select_account([self.account], self.factory, {2: "STOCK"})
        self.assertEqual(account.account_type, "STOCK")
        from xtquant.xttype import StockAccount
        account = select_account([self.account], StockAccount, {2: "STOCK"})
        self.assertEqual(account.account_type, 2)

    def test_reject_ambiguous_or_unsupported_account(self):
        for infos in (None, [], [self.account, self.account],
                      [NS(account_id="12345678", account_type=3)],
                      [NS(account_id="", account_type=2)]):
            with self.subTest(infos=infos), self.assertRaises(RuntimeError):
                select_account(infos, self.factory, {2: "STOCK", 3: "CREDIT"})

    def test_success_calls_only_read_operations(self):
        snapshot = self.collect()
        self.assertEqual(snapshot["orders"], [])
        self.assertEqual([call[0] for call in self.trader.mock_calls], [
            "start", "connect", "query_account_infos", "subscribe", "query_stock_asset",
            "query_stock_positions", "query_stock_orders", "query_stock_trades", "stop",
        ])

    def test_connection_failure_stops_before_account_queries(self):
        self.trader.connect.return_value = -1
        with self.assertRaisesRegex(RuntimeError, "connect"):
            self.collect()
        self.trader.query_account_infos.assert_not_called()
        self.trader.stop.assert_called_once()

    def test_subscription_failure_stops_before_asset_query(self):
        self.trader.subscribe.return_value = -1
        with self.assertRaisesRegex(RuntimeError, "subscribe"):
            self.collect()
        self.trader.query_stock_asset.assert_not_called()
        self.trader.stop.assert_called_once()

    def test_none_queries_are_not_successful_empty_results(self):
        for method in ("query_stock_asset", "query_stock_positions", "query_stock_orders", "query_stock_trades"):
            with self.subTest(method=method):
                query = getattr(self.trader, method)
                original = query.return_value
                query.return_value = None
                self.trader.reset_mock()
                try:
                    with self.assertRaises(RuntimeError):
                        self.collect()
                    self.trader.stop.assert_called_once()
                finally:
                    query.return_value = original

    def test_cross_account_result_is_rejected(self):
        self.position.account_id = "87654321"
        with self.assertRaisesRegex(RuntimeError, "different account"):
            self.collect()
        self.trader.stop.assert_called_once()

    def test_error_cleanup(self):
        self.trader.query_stock_asset.side_effect = ValueError("query failed")
        with self.assertRaisesRegex(ValueError, "query failed"):
            self.collect()
        self.trader.stop.assert_called_once()

    def test_snapshot_masks_account(self):
        report = serializable_snapshot(self.collect())
        self.assertEqual(report["account_id"], "****5678")
        self.assertNotIn("12345678", str(report))

    def test_vnpy_buying_power_and_position_mapping(self):
        account, positions = to_vnpy(self.collect())
        self.assertEqual(account.balance, 10000.)
        self.assertEqual(account.available, 1500.)
        self.assertEqual(positions[0].frozen, 30)
        self.assertEqual(positions[0].vt_symbol, "600000.SSE")
        self.assertEqual(positions[0].yd_volume, 0)

    def test_vnpy_rejects_invalid_position(self):
        for code, available in (("600000.HK", 70), ("600000.SH", 101)):
            with self.subTest(code=code, available=available):
                self.position.stock_code = code
                self.position.can_use_volume = available
                with self.assertRaises(RuntimeError):
                    to_vnpy(self.collect())

    def test_headless_oms_receives_snapshot_without_gateway(self):
        result = verify_vnpy(self.collect())
        self.assertEqual(result["account_count"], 1)
        self.assertEqual(result["position_count"], 1)
        self.assertEqual(result["gateway_count"], 0)


if __name__ == "__main__":
    unittest.main()
