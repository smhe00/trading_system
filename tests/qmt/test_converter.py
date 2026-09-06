"""Unit tests for XtQuant -> vn.py converters (pure, no MiniQMT needed)."""
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

from vnpy.trader.constant import Direction, Exchange, Offset, OrderType, Status

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.trader.gateways.qmt.converter import (
    parse_symbol,
    parse_time,
    to_account,
    to_direction,
    to_order,
    to_position,
    to_trade,
)

GATEWAY = "QMT"


def asset(**kw):
    defaults = dict(
        account_id="12345678", cash=1500.0, frozen_cash=200.0,
        market_value=8300.0, total_asset=10000.0, fetch_balance=908.72,
    )
    defaults.update(kw)
    return NS(**defaults)


def position(**kw):
    defaults = dict(
        account_id="12345678", stock_code="600000.SH", volume=100,
        can_use_volume=70, open_price=10.0, market_value=8300.0,
        frozen_volume=30, on_road_volume=0, yesterday_volume=60,
        avg_price=10.5, direction=48, last_price=10.6, profit_rate=0.01,
        secu_account="A123456", instrument_name="浦发银行",
    )
    defaults.update(kw)
    return NS(**defaults)


def order(**kw):
    defaults = dict(
        account_id="12345678", stock_code="600000.SH", order_id=100001,
        order_sysid="100001", order_time="20240906103000", order_type=23,
        order_volume=100, price_type=11, price=10.0, traded_volume=0,
        traded_price=0.0, order_status=50, status_msg="", strategy_name="probe",
        order_remark="", direction=48, offset_flag=0, secu_account="A123456",
        instrument_name="浦发银行",
    )
    defaults.update(kw)
    return NS(**defaults)


def trade(**kw):
    defaults = dict(
        account_id="12345678", stock_code="600000.SH", order_type=23,
        traded_id=5001, traded_time="20240906103100", traded_price=10.02,
        traded_volume=100, traded_amount=1002.0, order_id=100001,
        order_sysid="100001", strategy_name="probe", order_remark="",
        direction=48, offset_flag=0, commission=0.5, secu_account="A123456",
        instrument_name="浦发银行",
    )
    defaults.update(kw)
    return NS(**defaults)


class ParseSymbolTests(unittest.TestCase):
    def test_three_exchanges(self):
        self.assertEqual(parse_symbol("600000.SH"), ("600000", Exchange.SSE))
        self.assertEqual(parse_symbol("000001.SZ"), ("000001", Exchange.SZSE))
        self.assertEqual(parse_symbol("830001.BJ"), ("830001", Exchange.BSE))

    def test_rejects_invalid_codes(self):
        for code in ("600000.HK", "600000", "600000.xx", "", "600000.SH."):
            with self.subTest(code=code):
                with self.assertRaises(ValueError):
                    parse_symbol(code)


class ParseTimeTests(unittest.TestCase):
    def test_parses_xtquant_format(self):
        self.assertEqual(parse_time("20240906103000"), datetime(2024, 9, 6, 10, 30, 0))

    def test_missing_or_bad_input_is_none(self):
        for value in (None, "", "garbage", "20240906"):
            with self.subTest(value=value):
                self.assertIsNone(parse_time(value))


class AccountConverterTests(unittest.TestCase):
    def test_mapping(self):
        account = to_account(asset(), GATEWAY)
        self.assertEqual(account.gateway_name, GATEWAY)
        self.assertEqual(account.accountid, "12345678")
        self.assertEqual(account.balance, 10000.0)
        self.assertEqual(account.frozen, 200.0)
        self.assertEqual(account.available, 1500.0)
        self.assertEqual(account.extra["market_value"], 8300.0)
        self.assertEqual(account.extra["fetch_balance"], 908.72)


class PositionConverterTests(unittest.TestCase):
    def test_mapping(self):
        pos = to_position(position(), GATEWAY)
        self.assertEqual(pos.gateway_name, GATEWAY)
        self.assertEqual(pos.symbol, "600000")
        self.assertEqual(pos.exchange, Exchange.SSE)
        self.assertEqual(pos.direction, Direction.NET)
        self.assertEqual(pos.volume, 100)
        self.assertEqual(pos.frozen, 30)
        self.assertEqual(pos.price, 10.0)
        self.assertEqual(pos.yd_volume, 60)
        self.assertEqual(pos.extra["avg_price"], 10.5)

    def test_rejects_invalid_available_volume(self):
        for can_use in (-1, 101):
            with self.subTest(can_use=can_use):
                with self.assertRaises(ValueError):
                    to_position(position(can_use_volume=can_use), GATEWAY)

    def test_rejects_unsupported_exchange(self):
        with self.assertRaises(ValueError):
            to_position(position(stock_code="600000.HK"), GATEWAY)


class DirectionConverterTests(unittest.TestCase):
    def test_order_type_drives_direction(self):
        self.assertEqual(to_direction(23, None), Direction.LONG)
        self.assertEqual(to_direction(24, None), Direction.SHORT)

    def test_direction_flag_drives_direction(self):
        self.assertEqual(to_direction(None, 48), Direction.LONG)
        self.assertEqual(to_direction(None, 49), Direction.SHORT)

    def test_unknown_raises(self):
        with self.assertRaises(ValueError):
            to_direction(99, 88)


class OrderConverterTests(unittest.TestCase):
    def test_mapping(self):
        order_data = to_order(order(), GATEWAY)
        self.assertEqual(order_data.gateway_name, GATEWAY)
        self.assertEqual(order_data.symbol, "600000")
        self.assertEqual(order_data.exchange, Exchange.SSE)
        self.assertEqual(order_data.orderid, "100001")
        self.assertEqual(order_data.type, OrderType.LIMIT)
        self.assertEqual(order_data.direction, Direction.LONG)
        self.assertEqual(order_data.offset, Offset.NONE)
        self.assertEqual(order_data.price, 10.0)
        self.assertEqual(order_data.volume, 100)
        self.assertEqual(order_data.traded, 0)
        self.assertEqual(order_data.status, Status.NOTTRADED)
        self.assertEqual(order_data.datetime, datetime(2024, 9, 6, 10, 30, 0))
        self.assertEqual(order_data.reference, "probe")

    def test_market_price_type_maps_to_market(self):
        self.assertEqual(to_order(order(price_type=5), GATEWAY).type, OrderType.MARKET)

    def test_status_map(self):
        cases = {
            48: Status.SUBMITTING, 49: Status.SUBMITTING, 50: Status.NOTTRADED,
            55: Status.PARTTRADED, 52: Status.CANCELLED, 51: Status.CANCELLED,
            53: Status.CANCELLED, 54: Status.CANCELLED, 56: Status.ALLTRADED,
            57: Status.REJECTED, 255: Status.REJECTED,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(to_order(order(order_status=raw), GATEWAY).status, expected)

    def test_sell_direction(self):
        self.assertEqual(to_order(order(order_type=24, direction=49), GATEWAY).direction, Direction.SHORT)


class TradeConverterTests(unittest.TestCase):
    def test_mapping(self):
        trade_data = to_trade(trade(), GATEWAY)
        self.assertEqual(trade_data.gateway_name, GATEWAY)
        self.assertEqual(trade_data.symbol, "600000")
        self.assertEqual(trade_data.exchange, Exchange.SSE)
        self.assertEqual(trade_data.orderid, "100001")
        self.assertEqual(trade_data.tradeid, "5001")
        self.assertEqual(trade_data.direction, Direction.LONG)
        self.assertEqual(trade_data.offset, Offset.NONE)
        self.assertEqual(trade_data.price, 10.02)
        self.assertEqual(trade_data.volume, 100)
        self.assertEqual(trade_data.datetime, datetime(2024, 9, 6, 10, 31, 0))


if __name__ == "__main__":
    unittest.main()
