"""Constants for the read-only QmtGateway (XtQuant / MiniQMT).

Numeric values mirror the installed xtquant package (xtconstant / xttype).
Keeping them here makes the gateway independent of importing xtquant at
import time, so converter/gateway unit tests can run with plain mocks.
"""
from vnpy.trader.constant import Direction, Exchange, Offset, OrderType, Status

# Gateway identity.
GATEWAY_NAME = "QMT"

# Default MiniQMT userdata directory used when connect() receives no path.
DEFAULT_QMT_PATH = r"D:\国金证券QMT交易端\userdata_mini"

# XtQuant account type id for a plain stock account (xtconstant.ACCOUNT_TYPE_DICT[2]).
ACCOUNT_TYPE_STOCK = 2

# XtQuant exchange suffixes -> vn.py Exchange.
EXCHANGE_MAP = {
    "SH": Exchange.SSE,
    "SZ": Exchange.SZSE,
    "BJ": Exchange.BSE,
}

# XtQuant price_type -> vn.py OrderType.
# 11 = FIX_PRICE (limit), 5 = LATEST_PRICE (market).
ORDER_TYPE_MAP = {
    11: OrderType.LIMIT,
    5: OrderType.MARKET,
}
DEFAULT_ORDER_TYPE = OrderType.LIMIT

# XtQuant order_status -> vn.py Status.
ORDER_STATUS_MAP = {
    48: Status.SUBMITTING,    # ORDER_UNREPORTED
    49: Status.SUBMITTING,    # ORDER_WAIT_REPORTING
    50: Status.NOTTRADED,     # ORDER_REPORTED
    55: Status.PARTTRADED,    # ORDER_PART_SUCC
    52: Status.CANCELLED,     # ORDER_PARTSUCC_CANCEL
    51: Status.CANCELLED,     # ORDER_REPORTED_CANCEL
    53: Status.CANCELLED,     # ORDER_PART_CANCEL
    54: Status.CANCELLED,     # ORDER_CANCELED
    56: Status.ALLTRADED,     # ORDER_SUCCEEDED
    57: Status.REJECTED,      # ORDER_JUNK
    255: Status.REJECTED,     # ORDER_UNKNOWN
}
DEFAULT_ORDER_STATUS = Status.NOTTRADED

# XtQuant direction flags (DIRECTION_FLAG_BUY=48 / DIRECTION_FLAG_SELL=49).
DIRECTION_BUY = 48
DIRECTION_SELL = 49

# XtQuant stock order op types (STOCK_BUY=23 / STOCK_SELL=24).
ORDER_TYPE_BUY = 23
ORDER_TYPE_SELL = 24

# Stock positions are always NET in vn.py; orders/trades have no open/close offset.
POSITION_DIRECTION = Direction.NET
OFFSET_NONE = Offset.NONE

# MiniQMT returns order/trade time as 'yyyyMMddHHmmss' strings.
TIME_FORMAT = "%Y%m%d%H%M%S"

# Message used whenever a write path is attempted.
READ_ONLY_MESSAGE = (
    "QmtGateway is strictly read-only: send_order/cancel_order are not supported."
)
