"""One-shot smoke test: QmtGateway -> vn.py OMS (strictly read-only).

Runs QmtGateway against the real MiniQMT through XtQuant, then verifies the
vn.py OMS received Account/Position/Order/Trade data and that send_order /
cancel_order are refused with NotImplementedError.

Usage:
    python scripts/qmt_gateway_probe.py [--qmt-path <userdata>] [--timeout 45]
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
from random import SystemRandom
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_QMT_PATH = r"D:\国金证券QMT交易端\userdata_mini"


def mask(value):
    return "*" * max(4, len(value) - 4) + value[-4:] if len(value) > 4 else "****"


def wait_for_oms(main, getter, timeout):
    """Wait until the OMS snapshot arrives (events are async via EventEngine)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if getter(main):
            return
        time.sleep(0.05)
    raise RuntimeError("Timed out waiting for the vn.py OMS snapshot")


def worker(args):
    os.chdir(ROOT)
    (ROOT / ".vntrader").mkdir(exist_ok=True)

    from vnpy.event import EventEngine
    from vnpy.trader.engine import MainEngine
    from vnpy.trader.constant import Direction, Exchange, OrderType
    from vnpy.trader.object import CancelRequest, OrderRequest
    from src.trader.gateways.qmt.gateway import QmtGateway

    engine = EventEngine()
    main = MainEngine(engine)
    gateway = main.add_gateway(QmtGateway, "QMT")
    try:
        gateway.connect({
            "QMT路径": args.qmt_path,
            "会话ID": SystemRandom().randint(100000, 999999999),
        })

        wait_for_oms(main, lambda m: m.get_all_accounts(), args.timeout)
        accounts = main.get_all_accounts()
        positions = main.get_all_positions()
        orders = main.get_all_orders()
        trades = main.get_all_trades()

        if not accounts:
            raise RuntimeError("No account reached the vn.py OMS")

        # Read-only guard: placing/cancelling must be refused.
        probes = (
            ("send_order", gateway.send_order, OrderRequest(
                symbol="600000", exchange=Exchange.SSE, direction=Direction.LONG,
                type=OrderType.LIMIT, volume=100, price=10.0,
            )),
            ("cancel_order", gateway.cancel_order, CancelRequest(
                orderid="0", symbol="600000", exchange=Exchange.SSE,
            )),
        )
        for label, fn, req in probes:
            try:
                fn(req)
            except NotImplementedError:
                continue
            raise RuntimeError(
                f"Read-only guard failed: {label} must raise NotImplementedError"
            )

        report = {
            "observed_at": datetime.now().astimezone().isoformat(),
            "mode": "real_account_read_only",
            "account_id": mask(accounts[0].accountid),
            "account_balance": accounts[0].balance,
            "position_count": len(positions),
            "order_count": len(orders),
            "trade_count": len(trades),
            "gateway_names": main.get_all_gateway_names(),
            "read_only_guard": "send_order/cancel_order raised NotImplementedError",
        }
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        print("QmtGateway read-only smoke: PASS", flush=True)
    finally:
        # Also closes gateway -> client -> trader.stop().
        main.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qmt-path", default=DEFAULT_QMT_PATH)
    parser.add_argument("--timeout", type=float, default=45, help="Total worker timeout in seconds")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 0 < args.timeout <= 300:
        parser.error("--timeout must be > 0 and <= 300")
    if args.worker:
        return worker(args)
    env = dict(
        os.environ,
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUTF8="1",
        PYTHONUNBUFFERED="1",
    )
    try:
        result = subprocess.run(
            [sys.executable, "-B", str(Path(__file__).resolve()), *sys.argv[1:], "--worker"],
            env=env, cwd=ROOT, timeout=args.timeout, check=False,
        )
        return result.returncode
    except subprocess.TimeoutExpired:
        print(
            "Gateway probe timed out; its worker was terminated. "
            "MiniQMT remains running.",
            file=sys.stderr,
        )
        return 124


if __name__ == "__main__":
    raise SystemExit(main())
