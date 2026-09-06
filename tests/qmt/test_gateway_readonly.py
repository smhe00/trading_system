"""Tests for the read-only QmtGateway using a mocked client (no MiniQMT)."""
import sys
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from vnpy.event import EventEngine
from vnpy.trader.constant import Direction, Exchange, OrderType
from vnpy.trader.object import (
    AccountData,
    CancelRequest,
    OrderData,
    OrderRequest,
    PositionData,
    SubscribeRequest,
    TradeData,
)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trader.gateways.qmt.client import QmtClient
from src.trader.gateways.qmt.gateway import QmtGateway

GATEWAY = "QMT"
QMT_PATH = r"D:\国金证券QMT交易端\userdata_mini"


def make_client():
    client = Mock()
    client.query_account.return_value = NS(
        account_id="12345678", cash=1500.0, frozen_cash=200.0,
        market_value=8300.0, total_asset=10000.0, fetch_balance=908.72,
    )
    client.query_positions.return_value = [NS(
        account_id="12345678", stock_code="600000.SH", volume=100,
        can_use_volume=70, open_price=10.0, market_value=8300.0,
        frozen_volume=30, on_road_volume=0, yesterday_volume=60,
        avg_price=10.5, direction=48, last_price=10.6, profit_rate=0.01,
        secu_account="A123456", instrument_name="浦发银行",
    )]
    client.query_orders.return_value = [NS(
        account_id="12345678", stock_code="600000.SH", order_id=100001,
        order_sysid="100001", order_time="20240906103000", order_type=23,
        order_volume=100, price_type=11, price=10.0, traded_volume=0,
        traded_price=0.0, order_status=50, status_msg="", strategy_name="probe",
        order_remark="", direction=48, offset_flag=0, secu_account="A123456",
        instrument_name="浦发银行",
    )]
    client.query_trades.return_value = [NS(
        account_id="12345678", stock_code="600000.SH", order_type=23,
        traded_id=5001, traded_time="20240906103100", traded_price=10.02,
        traded_volume=100, traded_amount=1002.0, order_id=100001,
        order_sysid="100001", strategy_name="probe", order_remark="",
        direction=48, offset_flag=0, commission=0.5, secu_account="A123456",
        instrument_name="浦发银行",
    )]
    return client


class GatewayReadOnlyTests(unittest.TestCase):
    def setUp(self):
        self.engine = EventEngine()
        self.gateway = QmtGateway(self.engine, GATEWAY)
        self.received = {"account": [], "position": [], "order": [], "trade": [], "log": []}
        self.gateway.on_account = self.received["account"].append
        self.gateway.on_position = self.received["position"].append
        self.gateway.on_order = self.received["order"].append
        self.gateway.on_trade = self.received["trade"].append
        self.gateway.on_log = lambda event: self.received["log"].append(event.msg)

    def connect(self, client):
        with patch("src.trader.gateways.qmt.gateway.QmtClient", return_value=client):
            self.gateway.connect({"QMT路径": QMT_PATH, "会话ID": 123})

    def test_connect_pushes_all_four_data_types(self):
        self.connect(make_client())
        self.assertEqual(len(self.received["account"]), 1)
        self.assertEqual(len(self.received["position"]), 1)
        self.assertEqual(len(self.received["order"]), 1)
        self.assertEqual(len(self.received["trade"]), 1)
        self.assertIsInstance(self.received["account"][0], AccountData)
        self.assertIsInstance(self.received["position"][0], PositionData)
        self.assertIsInstance(self.received["order"][0], OrderData)
        self.assertIsInstance(self.received["trade"][0], TradeData)

    def test_connect_uses_unique_gateway_name_in_objects(self):
        self.connect(make_client())
        for key in ("account", "position", "order", "trade"):
            self.assertEqual(self.received[key][0].gateway_name, GATEWAY)

    def test_client_connect_failure_cleans_up(self):
        client = make_client()
        client.connect.side_effect = RuntimeError("boom")
        with patch("src.trader.gateways.qmt.gateway.QmtClient", return_value=client):
            with self.assertRaises(RuntimeError):
                self.gateway.connect({"QMT路径": QMT_PATH})
        self.assertIsNone(self.gateway.client)
        client.close.assert_called_once()
        self.assertEqual(self.received["account"], [])

    def test_initial_query_failure_closes_client_and_disconnects(self):
        for stage in ("query_account", "query_positions", "query_orders", "query_trades"):
            with self.subTest(stage=stage):
                engine = EventEngine()
                gateway = QmtGateway(engine, GATEWAY)
                received = {"log": []}
                gateway.on_log = lambda event: received["log"].append(event.msg)
                for name in ("on_account", "on_position", "on_order", "on_trade"):
                    setattr(gateway, name, lambda *a, **k: None)
                client = make_client()
                getattr(client, stage).side_effect = RuntimeError(f"{stage} failed")
                with patch("src.trader.gateways.qmt.gateway.QmtClient", return_value=client):
                    with self.assertRaises(RuntimeError):
                        gateway.connect({"QMT路径": QMT_PATH})
                self.assertIsNone(gateway.client)
                client.close.assert_called_once()

    def test_repeated_connect_is_rejected_and_leaks_nothing(self):
        client = make_client()
        with patch("src.trader.gateways.qmt.gateway.QmtClient", return_value=client) as cls:
            self.gateway.connect({"QMT路径": QMT_PATH})
            with self.assertRaisesRegex(RuntimeError, "already connected"):
                self.gateway.connect({"QMT路径": QMT_PATH})
            # No second client was ever created; the existing session is kept.
            self.assertEqual(cls.call_count, 1)
            client.close.assert_not_called()
        self.assertIs(self.gateway.client, client)

    def test_send_order_raises_not_implemented(self):
        req = OrderRequest(
            symbol="600000", exchange=Exchange.SSE, direction=Direction.LONG,
            type=OrderType.LIMIT, volume=100, price=10.0,
        )
        with self.assertRaises(NotImplementedError):
            self.gateway.send_order(req)
        self.assertTrue(any("read-only" in msg.lower() for msg in self.received["log"]))

    def test_cancel_order_raises_not_implemented(self):
        req = CancelRequest(orderid="100001", symbol="600000", exchange=Exchange.SSE)
        with self.assertRaises(NotImplementedError):
            self.gateway.cancel_order(req)
        self.assertTrue(any("read-only" in msg.lower() for msg in self.received["log"]))

    def test_subscribe_is_logged_only(self):
        req = SubscribeRequest(symbol="600000", exchange=Exchange.SSE)
        self.gateway.subscribe(req)  # must not raise
        self.assertEqual(self.received["account"], [])
        self.assertGreaterEqual(len(self.received["log"]), 1)

    def test_queries_without_connect_log_only(self):
        for method in (
            self.gateway.query_account,
            self.gateway.query_position,
            self.gateway.query_orders,
            self.gateway.query_trades,
        ):
            method()
        self.assertEqual(self.received["account"], [])
        self.assertEqual(self.received["position"], [])
        self.assertEqual(self.received["order"], [])
        self.assertEqual(self.received["trade"], [])
        self.assertGreaterEqual(len(self.received["log"]), 4)

    def test_close_stops_client(self):
        client = make_client()
        self.connect(client)
        self.gateway.close()
        client.close.assert_called_once()
        self.assertIsNone(self.gateway.client)

    def test_close_without_connect_is_safe(self):
        self.gateway.close()  # must not raise
        self.assertIsNone(self.gateway.client)

    # ------------------------------------------------------------------ #
    # 3.6 Stale position clearing on a full snapshot
    # ------------------------------------------------------------------ #
    def test_missing_position_in_next_snapshot_emits_clearing_event(self):
        client = make_client()
        client.query_positions.side_effect = [
            client.query_positions.return_value,
            [],
        ]
        self.connect(client)
        self.assertEqual(len(self.received["position"]), 1)
        self.gateway.query_position()
        self.assertEqual(len(self.received["position"]), 2)
        clearing = self.received["position"][1]
        self.assertEqual(clearing.symbol, "600000")
        self.assertEqual(clearing.exchange, Exchange.SSE)
        self.assertEqual(clearing.direction, Direction.NET)
        self.assertEqual(clearing.volume, 0)
        self.assertEqual(clearing.frozen, 0)

    def test_position_disappear_then_reappear(self):
        client = make_client()
        pos = client.query_positions.return_value[0]
        client.query_positions.side_effect = [[pos], [], [pos]]
        self.connect(client)
        self.gateway.query_position()
        self.gateway.query_position()
        # [pos, clearing, pos] -> no clearing on the reappear snapshot.
        self.assertEqual(len(self.received["position"]), 3)
        self.assertEqual(self.received["position"][1].volume, 0)
        self.assertEqual(self.received["position"][2].volume, 100)


class ClientAccountSelectionTests(unittest.TestCase):
    """QmtClient selects the unique STOCK account after filtering by type."""

    def make_client(self, infos):
        client = QmtClient(qmt_path=str(ROOT), session_id=1)
        trader = Mock()
        trader.query_account_infos.return_value = infos
        client._trader = trader
        return client

    def test_selects_unique_stock_account(self):
        client = self.make_client([NS(account_type=2, account_id="12345678")])
        self.assertEqual(client._select_account_id(), "12345678")

    def test_stock_selected_even_with_other_account_types(self):
        client = self.make_client([
            NS(account_type=3, account_id="CREDIT001"),
            NS(account_type=2, account_id="12345678"),
        ])
        self.assertEqual(client._select_account_id(), "12345678")

    def test_zero_stock_accounts_rejected(self):
        client = self.make_client([NS(account_type=3, account_id="CREDIT001")])
        with self.assertRaises(RuntimeError):
            client._select_account_id()

    def test_multiple_stock_accounts_rejected(self):
        client = self.make_client([
            NS(account_type=2, account_id="1"), NS(account_type=2, account_id="2"),
        ])
        with self.assertRaises(RuntimeError):
            client._select_account_id()

    def test_none_or_empty_infos_rejected(self):
        for infos in (None, []):
            with self.subTest(infos=infos):
                client = self.make_client(infos)
                with self.assertRaises(RuntimeError):
                    client._select_account_id()

    def test_missing_account_id_rejected(self):
        client = self.make_client([NS(account_type=2, account_id="")])
        with self.assertRaises(RuntimeError):
            client._select_account_id()

    def test_rejects_missing_directory(self):
        with self.assertRaises(ValueError):
            QmtClient(qmt_path=r"D:\no_such_miniqmt_dir_xyz", session_id=1)


class ClientOwnershipTests(unittest.TestCase):
    """QmtClient must fail closed when a broker row belongs to another account."""

    ACCOUNT = "12345678"

    def make_client(self, method, rows, account_id=ACCOUNT):
        client = QmtClient(qmt_path=str(ROOT), session_id=1)
        client.account_id = self.ACCOUNT
        trader = Mock()
        getattr(trader, method).return_value = rows
        client._trader = trader
        return client

    def test_cross_account_asset_rejected(self):
        asset = NS(account_id="87654321", cash=1.0, frozen_cash=0.0,
                   market_value=0.0, total_asset=1.0, fetch_balance=0.0)
        client = self.make_client("query_stock_asset", asset)
        with self.assertRaisesRegex(RuntimeError, "different account"):
            client.query_account()

    def test_cross_account_position_rejected(self):
        pos = NS(account_id="87654321", stock_code="600000.SH", volume=0,
                 can_use_volume=0, open_price=0.0)
        client = self.make_client("query_stock_positions", [pos])
        with self.assertRaisesRegex(RuntimeError, "different account"):
            client.query_positions()

    def test_cross_account_order_rejected(self):
        order = NS(account_id="87654321", stock_code="600000.SH", order_id=1)
        client = self.make_client("query_stock_orders", [order])
        with self.assertRaisesRegex(RuntimeError, "different account"):
            client.query_orders()

    def test_cross_account_trade_rejected(self):
        trade = NS(account_id="87654321", stock_code="600000.SH", traded_id=1)
        client = self.make_client("query_stock_trades", [trade])
        with self.assertRaisesRegex(RuntimeError, "different account"):
            client.query_trades()

    def test_matching_account_is_accepted(self):
        pos = NS(account_id=self.ACCOUNT, stock_code="600000.SH", volume=0,
                 can_use_volume=0, open_price=0.0)
        client = self.make_client("query_stock_positions", [pos])
        self.assertEqual(client.query_positions(), [pos])


if __name__ == "__main__":
    unittest.main()
