"""One-shot MiniQMT read-only query, with optional headless vn.py OMS check."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
from random import SystemRandom
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
QMT_PATH = r"D:\国金证券QMT交易端\userdata_mini"


def mask(value):
    return "*" * max(4, len(value) - 4) + value[-4:] if len(value) > 4 else "****"


def select_account(infos, account_factory, account_types):
    if infos is None:
        raise RuntimeError("Account enumeration returned None")
    if len(infos) != 1:
        raise RuntimeError(f"Expected exactly one account, found {len(infos)}")
    info = infos[0]
    kind = info.account_type
    kind = kind.upper() if isinstance(kind, str) else account_types.get(kind)
    if kind != "STOCK":
        raise RuntimeError(f"This probe supports STOCK accounts only; found {kind!r}")
    if not isinstance(info.account_id, str) or not info.account_id.strip():
        raise RuntimeError("Account ID is missing or invalid")
    return account_factory(info.account_id, kind)


def checked_rows(rows, label, account_id):
    # XtQuant None can mean empty OR failed: never silently turn it into [].
    if rows is None:
        raise RuntimeError(f"{label} returned None (empty or failed; not confirmed)")
    for row in rows:
        if row.account_id != account_id:
            raise RuntimeError(f"{label} returned a different account")
    return rows


def collect_snapshot(trader, account_factory, account_types):
    try:
        trader.start()
        result = trader.connect()
        if result != 0:
            raise RuntimeError(f"MiniQMT connect()={result}")
        print("MiniQMT connection: OK", flush=True)
        account = select_account(trader.query_account_infos(), account_factory, account_types)
        print(f"Unique STOCK account: {mask(account.account_id)}", flush=True)
        result = trader.subscribe(account)
        if result != 0:
            raise RuntimeError(f"MiniQMT subscribe()={result}")
        asset = trader.query_stock_asset(account)
        if asset is None:
            raise RuntimeError("Asset query returned None")
        checked_rows([asset], "Asset", account.account_id)
        positions = checked_rows(trader.query_stock_positions(account), "Positions", account.account_id)
        orders = checked_rows(trader.query_stock_orders(account, False), "Orders", account.account_id)
        trades = checked_rows(trader.query_stock_trades(account), "Trades", account.account_id)
        return dict(account_id=account.account_id, asset=asset,
                    positions=positions, orders=orders, trades=trades)
    finally:
        active_error = sys.exc_info()[0] is not None
        try:
            trader.stop()
        except Exception:
            if not active_error:
                raise
            traceback.print_exc()


def pick(obj, names):
    return {name: getattr(obj, name, None) for name in names.split()}


def serializable_snapshot(snapshot):
    return {
        "observed_at": datetime.now().astimezone().isoformat(),
        "mode": "real_account_read_only",
        "account_id": mask(snapshot["account_id"]),
        "account_type": "STOCK",
        "asset": pick(snapshot["asset"], "total_asset cash frozen_cash market_value fetch_balance"),
        "positions": [pick(x, "stock_code volume can_use_volume open_price avg_price market_value")
                      for x in snapshot["positions"]],
        "orders": [pick(x, "order_id stock_code order_type order_volume traded_volume price order_status")
                   for x in snapshot["orders"]],
        "trades": [pick(x, "order_id traded_id stock_code traded_volume traded_price traded_amount")
                   for x in snapshot["trades"]],
    }


def to_vnpy(snapshot):
    from vnpy.trader.constant import Direction, Exchange
    from vnpy.trader.object import AccountData, PositionData

    asset = snapshot["asset"]
    account = AccountData(accountid=snapshot["account_id"], balance=asset.total_asset,
                          frozen=asset.frozen_cash, gateway_name="QMT_READONLY")
    # Securities buying power is cash, not total assets minus frozen cash.
    account.available = asset.cash
    exchanges = {"SH": Exchange.SSE, "SZ": Exchange.SZSE, "BJ": Exchange.BSE}
    positions = []
    for item in snapshot["positions"]:
        symbol, suffix = item.stock_code.rsplit(".", 1)
        if suffix not in exchanges:
            raise RuntimeError(f"Unsupported position exchange: {suffix}")
        if not 0 <= item.can_use_volume <= item.volume:
            raise RuntimeError(f"Invalid available volume: {item.stock_code}")
        position = PositionData(symbol=symbol, exchange=exchanges[suffix],
                                direction=Direction.NET, volume=item.volume,
                                frozen=item.volume - item.can_use_volume,
                                price=item.open_price, gateway_name="QMT_READONLY")
        # Previous-day quantity and PnL are not supplied by this mapping.
        # Leave vn.py defaults; available quantity is not previous-day holdings.
        positions.append(position)
    return account, positions


def verify_vnpy(snapshot):
    from threading import Event as ThreadEvent
    from vnpy.event import Event, EventEngine
    from vnpy.trader.engine import MainEngine
    from vnpy.trader.event import EVENT_ACCOUNT, EVENT_POSITION

    account, positions = to_vnpy(snapshot)
    events = EventEngine()
    main = MainEngine(events)
    try:
        done = ThreadEvent()
        events.register("qmt_snapshot_complete", lambda event: done.set())
        events.put(Event(EVENT_ACCOUNT, account))
        for position in positions:
            events.put(Event(EVENT_POSITION, position))
        events.put(Event("qmt_snapshot_complete"))
        if not done.wait(5):
            raise RuntimeError("vn.py event processing timed out")
        stored = main.get_account(account.vt_accountid)
        if stored != account or len(main.get_all_positions()) != len(positions):
            raise RuntimeError("vn.py OMS snapshot mismatch")
        for position in positions:
            if main.get_position(position.vt_positionid) != position:
                raise RuntimeError("vn.py OMS position mismatch")
        return {"account_count": len(main.get_all_accounts()),
                "position_count": len(main.get_all_positions()),
                "gateway_count": len(main.get_all_gateway_names()),
                "scope": "one-shot account/position events; orders/trades remain raw QMT data"}
    finally:
        main.close()


def worker(args):
    if not Path(args.qmt_path).is_dir():
        raise RuntimeError(f"QMT userdata directory does not exist: {args.qmt_path}")
    os.chdir(ROOT)
    (ROOT / ".vntrader").mkdir(exist_ok=True)
    from xtquant import xtconstant
    from xtquant.xttrader import XtQuantTrader
    from xtquant.xttype import StockAccount

    trader = XtQuantTrader(args.qmt_path, SystemRandom().randint(100000, 999999999))
    snapshot = collect_snapshot(trader, StockAccount, xtconstant.ACCOUNT_TYPE_DICT)
    report = serializable_snapshot(snapshot)
    if args.vnpy:
        report["vnpy"] = verify_vnpy(snapshot)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.json:
        output = Path(args.json).resolve()
        if not output.is_relative_to(ROOT / "work"):
            raise RuntimeError("Snapshot output must be inside project work/")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded, flush=True)
    print("Read-only probe: PASS", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qmt-path", default=QMT_PATH)
    parser.add_argument("--vnpy", action="store_true", help="Check account/position events in vn.py OMS")
    parser.add_argument("--json", help="Save masked snapshot inside project work/")
    parser.add_argument("--timeout", type=float, default=45, help="Total worker timeout in seconds")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 0 < args.timeout <= 300:
        parser.error("--timeout must be > 0 and <= 300")
    if args.worker:
        worker(args)
        return 0
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1", PYTHONUNBUFFERED="1")
    try:
        result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()),
                                 *sys.argv[1:], "--worker"], env=env, cwd=ROOT,
                                timeout=args.timeout, check=False)
        return result.returncode
    except subprocess.TimeoutExpired:
        print("Probe timed out; its worker was terminated. MiniQMT remains running.", file=sys.stderr)
        return 124


if __name__ == "__main__":
    raise SystemExit(main())
