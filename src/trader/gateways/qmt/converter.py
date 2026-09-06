"""Convert XtQuant data objects into VeighNa trader objects.

Each ``to_*`` function is pure (no I/O, no XtQuant import) so it can be
unit-tested with plain fake objects.
"""
from datetime import datetime
from typing import Any

from vnpy.trader.constant import Direction, Exchange
from vnpy.trader.object import AccountData, OrderData, PositionData, TradeData

from .constants import (
    EXCHANGE_MAP,
    OFFSET_NONE,
    ORDER_STATUS_MAP,
    ORDER_TYPE_BUY,
    ORDER_TYPE_MAP,
    ORDER_TYPE_SELL,
    POSITION_DIRECTION,
    TIME_FORMAT,
)


def parse_symbol(stock_code: str) -> tuple[str, Exchange]:
    """Split ``'600000.SH'`` into ``(symbol, Exchange)``.

    Raises ValueError on a malformed code or an unsupported exchange suffix.
    """
    try:
        symbol, suffix = stock_code.rsplit(".", 1)
    except (AttributeError, ValueError):
        raise ValueError(f"Invalid stock_code: {stock_code!r}") from None
    exchange = EXCHANGE_MAP.get(suffix.upper())
    if exchange is None:
        raise ValueError(f"Unsupported exchange suffix in stock_code: {stock_code!r}")
    if not symbol:
        raise ValueError(f"Empty symbol in stock_code: {stock_code!r}")
    return symbol, exchange


def parse_time(value: Any) -> datetime | None:
    """Parse a MiniQMT order/trade time into a datetime.

    Live MiniQMT returns Unix timestamps (epoch seconds, e.g. 1788485412);
    the documentation format is 'yyyyMMddHHmmss'. Both are accepted. Returns
    None for missing, empty, or unrecognized input (never raises).
    """
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value)
        except (ValueError, OverflowError, OSError):
            return None
    text = str(value).strip()
    if text.isdigit():
        if len(text) >= 14:
            try:
                return datetime.strptime(text[:14], TIME_FORMAT)
            except ValueError:
                return None
        if 9 <= len(text) <= 11:  # epoch seconds as a digit string
            try:
                return datetime.fromtimestamp(int(text))
            except (ValueError, OverflowError, OSError):
                return None
    return None


def to_account(asset: Any, gateway_name: str) -> AccountData:
    """XtQuant Asset -> vn.py AccountData."""
    account = AccountData(
        accountid=asset.account_id,
        balance=asset.total_asset,
        frozen=asset.frozen_cash,
        gateway_name=gateway_name,
    )
    # Securities buying power is cash, not total assets minus frozen cash.
    account.available = asset.cash
    account.extra = {
        "market_value": asset.market_value,
        "fetch_balance": asset.fetch_balance,
    }
    return account


def to_position(position: Any, gateway_name: str) -> PositionData:
    """XtQuant Position -> vn.py PositionData (NET direction for stocks)."""
    symbol, exchange = parse_symbol(position.stock_code)
    if not 0 <= position.can_use_volume <= position.volume:
        raise ValueError(
            f"Invalid available volume for {position.stock_code}: "
            f"can_use_volume={position.can_use_volume} volume={position.volume}"
        )
    data = PositionData(
        symbol=symbol,
        exchange=exchange,
        direction=POSITION_DIRECTION,
        volume=position.volume,
        frozen=position.volume - position.can_use_volume,
        price=position.open_price,
        gateway_name=gateway_name,
    )
    data.yd_volume = position.yesterday_volume
    data.extra = {
        "avg_price": position.avg_price,
        "market_value": position.market_value,
        "profit_rate": position.profit_rate,
        "last_price": position.last_price,
        "on_road_volume": position.on_road_volume,
    }
    return data


def to_direction(order_type: Any, direction: Any = None) -> Direction:
    """Resolve vn.py Direction for a STOCK order/trade.

    XtQuant documents that the ``direction`` field is not applicable to
    stocks, while ``order_type`` (STOCK_BUY / STOCK_SELL) is the
    authoritative buy/sell source. A conflicting ``direction`` value must
    not override a valid stock ``order_type``; an unknown ``order_type``
    fails closed.
    """
    if order_type == ORDER_TYPE_BUY:
        return Direction.LONG
    if order_type == ORDER_TYPE_SELL:
        return Direction.SHORT
    raise ValueError(
        f"Unknown XtQuant stock order_type: {order_type!r} (direction={direction!r})"
    )


def to_order(order: Any, gateway_name: str) -> OrderData:
    """XtQuant Order -> vn.py OrderData (fails closed on unknown enums)."""
    symbol, exchange = parse_symbol(order.stock_code)
    try:
        order_type = ORDER_TYPE_MAP[order.price_type]
    except KeyError:
        raise ValueError(
            f"Unknown XtQuant price_type: {order.price_type!r}"
        ) from None
    try:
        status = ORDER_STATUS_MAP[order.order_status]
    except KeyError:
        raise ValueError(
            f"Unknown XtQuant order_status: {order.order_status!r}"
        ) from None
    data = OrderData(
        symbol=symbol,
        exchange=exchange,
        orderid=str(order.order_id),
        type=order_type,
        direction=to_direction(order.order_type, order.direction),
        offset=OFFSET_NONE,
        price=order.price,
        volume=order.order_volume,
        traded=order.traded_volume,
        status=status,
        datetime=parse_time(order.order_time),
        gateway_name=gateway_name,
    )
    data.reference = order.strategy_name
    data.extra = {
        "order_sysid": order.order_sysid,
        "price_type": order.price_type,
        "status_msg": order.status_msg,
        "order_remark": order.order_remark,
    }
    return data


def to_trade(trade: Any, gateway_name: str) -> TradeData:
    """XtQuant Trade -> vn.py TradeData."""
    symbol, exchange = parse_symbol(trade.stock_code)
    return TradeData(
        symbol=symbol,
        exchange=exchange,
        orderid=str(trade.order_id),
        tradeid=str(trade.traded_id),
        direction=to_direction(trade.order_type, trade.direction),
        offset=OFFSET_NONE,
        price=trade.traded_price,
        volume=trade.traded_volume,
        datetime=parse_time(trade.traded_time),
        gateway_name=gateway_name,
    )
