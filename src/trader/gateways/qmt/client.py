"""Minimal read-only client wrapper around XtQuantTrader (MiniQMT).

The wrapper deliberately exposes only read-only query methods. There is no
order or cancel method at all, so a future write path would require adding
explicit new code — nothing here can place or cancel an order.
"""
import os
from random import SystemRandom
from typing import Any, Optional

from .constants import ACCOUNT_TYPE_STOCK


def _random_session_id() -> int:
    """Return a fresh session id; MiniQMT requires a unique session per trader."""
    return SystemRandom().randint(100000, 999999999)


class QmtClient:
    """Owns one XtQuantTrader session and wraps its read-only stock queries."""

    def __init__(self, qmt_path: str, session_id: int = 0) -> None:
        if not qmt_path or not os.path.isdir(qmt_path):
            raise ValueError(f"MiniQMT userdata directory does not exist: {qmt_path!r}")
        self.qmt_path = qmt_path
        self.session_id = session_id if session_id else _random_session_id()
        self._trader = None
        self.account_id: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    def connect(self) -> None:
        """Start an XtQuantTrader, connect to MiniQMT, select the unique
        STOCK account and subscribe to it. Raises on any failure."""
        from xtquant.xttrader import XtQuantTrader

        trader = XtQuantTrader(self.qmt_path, self.session_id)
        trader.start()
        try:
            result = trader.connect()
        except BaseException:
            trader.stop()
            raise
        if result != 0:
            trader.stop()
            raise RuntimeError(f"MiniQMT connect() failed with code {result}")
        self._trader = trader
        try:
            self.account_id = self._select_account_id()
            result = trader.subscribe(self._account())
        except BaseException:
            trader.stop()
            self._trader = None
            raise
        if result != 0:
            trader.stop()
            self._trader = None
            raise RuntimeError(f"MiniQMT subscribe() failed with code {result}")

    def close(self) -> None:
        """Stop the XtQuantTrader session if one is active."""
        if self._trader is not None:
            try:
                self._trader.stop()
            finally:
                self._trader = None

    # ------------------------------------------------------------------ #
    # Account selection (no hard-coded real account id)
    # ------------------------------------------------------------------ #
    def _account(self) -> Any:
        from xtquant.xttype import StockAccount

        return StockAccount(self.account_id)

    def _select_account_id(self) -> str:
        """Select the unique STOCK account among all returned accounts.

        The rule is: query all accounts, normalize their types, filter to
        STOCK, then require exactly one STOCK account. Other account types
        must not make a unique STOCK account ambiguous, and the total
        account count is irrelevant.
        """
        from xtquant import xtconstant

        infos = self._trader.query_account_infos()
        if infos is None:
            raise RuntimeError("MiniQMT returned None from query_account_infos")
        expected = xtconstant.ACCOUNT_TYPE_DICT.get(ACCOUNT_TYPE_STOCK)
        stock = []
        for info in infos:
            kind = info.account_type
            kind = kind.upper() if isinstance(kind, str) else xtconstant.ACCOUNT_TYPE_DICT.get(kind)
            if kind == expected:
                stock.append(info)
        if len(stock) != 1:
            raise RuntimeError(
                f"Expected exactly one {expected} account, found {len(stock)} "
                f"{expected} among {len(infos)} total; this read-only gateway "
                "refuses ambiguous configuration"
            )
        info = stock[0]
        if not isinstance(info.account_id, str) or not info.account_id.strip():
            raise RuntimeError("MiniQMT account_id is missing or invalid")
        return info.account_id

    # ------------------------------------------------------------------ #
    # Account ownership validation (fail closed)
    # ------------------------------------------------------------------ #
    def _check_account(self, obj: Any, label: str) -> None:
        """Raise unless ``obj.account_id`` equals the selected account id."""
        account_id = getattr(obj, "account_id", None)
        if account_id is None or account_id != self.account_id:
            raise RuntimeError(
                f"{label} returned a missing or different account: "
                f"{account_id!r} (expected {self.account_id!r})"
            )

    # ------------------------------------------------------------------ #
    # Read-only queries
    # ------------------------------------------------------------------ #
    def query_account(self) -> Any:
        """Return the current XtAsset or raise (ownership validated)."""
        asset = self._trader.query_stock_asset(self._account())
        if asset is None:
            raise RuntimeError("MiniQMT query_stock_asset returned None")
        self._check_account(asset, "Asset")
        return asset

    def query_positions(self) -> list:
        """Return the current positions or raise (ownership validated)."""
        rows = self._trader.query_stock_positions(self._account())
        if rows is None:
            raise RuntimeError("MiniQMT query_stock_positions returned None")
        for row in rows:
            self._check_account(row, "Position")
        return rows

    def query_orders(self) -> list:
        """Return today's orders or raise (ownership validated)."""
        rows = self._trader.query_stock_orders(self._account(), cancelable_only=False)
        if rows is None:
            raise RuntimeError("MiniQMT query_stock_orders returned None")
        for row in rows:
            self._check_account(row, "Order")
        return rows

    def query_trades(self) -> list:
        """Return today's trades or raise (ownership validated)."""
        rows = self._trader.query_stock_trades(self._account())
        if rows is None:
            raise RuntimeError("MiniQMT query_stock_trades returned None")
        for row in rows:
            self._check_account(row, "Trade")
        return rows
