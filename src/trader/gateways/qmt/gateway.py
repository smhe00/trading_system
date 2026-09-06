"""Read-only VeighNa QmtGateway backed by XtQuant (MiniQMT).

Data flow: MiniQMT -> XtQuant -> QmtClient -> converter -> VeighNa events.

Only account / position / order / trade queries are supported. Order
placement and cancellation intentionally raise NotImplementedError so this
integration can never touch a real trading API.
"""
from vnpy.trader.constant import Exchange
from vnpy.trader.gateway import BaseGateway
from vnpy.trader.object import CancelRequest, OrderRequest, SubscribeRequest

from .client import QmtClient
from .constants import DEFAULT_QMT_PATH, GATEWAY_NAME, READ_ONLY_MESSAGE
from .converter import to_account, to_order, to_position, to_trade


class QmtGateway(BaseGateway):
    """VeighNa gateway that reads MiniQMT through XtQuant, read-only."""

    default_name = GATEWAY_NAME
    default_setting = {
        "QMT路径": DEFAULT_QMT_PATH,
        "会话ID": 0,
    }
    exchanges = [Exchange.SSE, Exchange.SZSE, Exchange.BSE]

    def __init__(self, event_engine, gateway_name: str) -> None:
        super().__init__(event_engine, gateway_name)
        self.client: QmtClient | None = None

    # ------------------------------------------------------------------ #
    # Connection management
    # ------------------------------------------------------------------ #
    def connect(self, setting: dict) -> None:
        """Connect to MiniQMT and push an initial snapshot into vn.py."""
        qmt_path = setting.get("QMT路径") or setting.get("qmt_path") or DEFAULT_QMT_PATH
        session_id = setting.get("会话ID") or setting.get("session_id") or 0
        self.client = QmtClient(qmt_path=qmt_path, session_id=session_id)
        try:
            self.client.connect()
        except Exception:
            self.client = None
            raise
        self.write_log(f"QmtGateway({self.gateway_name}) read-only connect: OK")
        # Initial pull so the vn.py OMS is populated right after connect.
        self.query_account()
        self.query_position()
        self.query_orders()
        self.query_trades()
        self.write_log("QmtGateway initial snapshot pushed to OMS")

    def close(self) -> None:
        """Stop the MiniQMT session (read-only; nothing else to release)."""
        if self.client is not None:
            self.client.close()
            self.client = None

    # ------------------------------------------------------------------ #
    # Read-only queries (each re-pulls from MiniQMT and pushes events)
    # ------------------------------------------------------------------ #
    def query_account(self) -> None:
        if self.client is None:
            self.write_log("QmtGateway not connected; cannot query account")
            return
        self.on_account(to_account(self.client.query_account(), self.gateway_name))

    def query_position(self) -> None:
        if self.client is None:
            self.write_log("QmtGateway not connected; cannot query position")
            return
        for position in self.client.query_positions():
            self.on_position(to_position(position, self.gateway_name))

    def query_orders(self) -> None:
        if self.client is None:
            self.write_log("QmtGateway not connected; cannot query orders")
            return
        for order in self.client.query_orders():
            self.on_order(to_order(order, self.gateway_name))

    def query_trades(self) -> None:
        if self.client is None:
            self.write_log("QmtGateway not connected; cannot query trades")
            return
        for trade in self.client.query_trades():
            self.on_trade(to_trade(trade, self.gateway_name))

    # ------------------------------------------------------------------ #
    # Deliberately unsupported paths (strictly read-only)
    # ------------------------------------------------------------------ #
    def subscribe(self, req: SubscribeRequest) -> None:
        """Market data subscription is out of scope for this read-only gateway."""
        self.write_log("QmtGateway is read-only; market data subscription is not supported")

    def send_order(self, req: OrderRequest) -> str:
        """Refuse to place orders; this gateway must stay read-only."""
        self.write_log(READ_ONLY_MESSAGE)
        raise NotImplementedError(READ_ONLY_MESSAGE)

    def cancel_order(self, req: CancelRequest) -> None:
        """Refuse to cancel orders; this gateway must stay read-only."""
        self.write_log(READ_ONLY_MESSAGE)
        raise NotImplementedError(READ_ONLY_MESSAGE)
