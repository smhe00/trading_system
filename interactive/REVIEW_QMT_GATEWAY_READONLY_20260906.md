# REVIEW: QmtGateway Read-Only

Date: 2026-09-06
Reviewed commit: `096d5be9d58c2a3cd765ec1aebb09b6bd4b006a5`
Verdict: **CHANGES_REQUIRED**

## 1. Overall assessment

The implementation is directionally correct and the read-only safety boundary is real: `QmtClient` exposes no order/cancel methods, while `QmtGateway.send_order()` and `cancel_order()` raise `NotImplementedError`. The code is small, understandable, and the initial MiniQMT -> XtQuant -> QmtGateway -> vn.py OMS path has been demonstrated.

However, the current implementation is not yet suitable to serve as the authoritative broker-state adapter for later reconciliation or writable execution. Several fail-closed and snapshot-consistency issues must be fixed first.

## 2. Required fixes

### P0-1. Account selection does not follow the task specification

File: `src/trader/gateways/qmt/client.py`

Current behavior checks `len(infos) == 1` before filtering account type. Therefore, if MiniQMT later exposes one STOCK account plus one CREDIT/OPTION/other account, the gateway rejects the configuration even though there is exactly one valid STOCK account.

Required behavior:

1. Query all account infos.
2. Normalize account type.
3. Filter to STOCK accounts.
4. Exactly one STOCK account -> select it.
5. Zero or more than one STOCK account -> fail closed.

Do not require the total account count to equal one.

### P0-2. `connect()` is not transactional after the XtQuant session is established

File: `src/trader/gateways/qmt/gateway.py`

`self.client.connect()` is protected, but the four initial snapshot queries are not. If `query_account()`, `query_position()`, `query_orders()` or `query_trades()` raises, `connect()` exits with an exception while `self.client` remains non-None and the MiniQMT/XtQuant session can remain open.

Required behavior:

- Treat connect + initial snapshot as one transaction.
- Any failure after session creation must call `client.close()` and set `self.client = None` before re-raising.
- A second `connect()` while already connected must either be explicitly rejected or close the previous session first; it must never leak a session.
- Add tests for failures in each initial query stage.

### P0-3. Returned account ownership is not validated

Files: `src/trader/gateways/qmt/client.py`, converter path

After selecting the account, query results are accepted without checking `row.account_id == selected_account_id`. The earlier baseline probe already used cross-account rejection; the Gateway must preserve the same fail-closed property.

Required behavior:

- Validate `account_id` on Asset, every Position, every Order and every Trade.
- Any mismatched or missing account id must raise and must not be pushed into vn.py OMS.
- Add explicit cross-account tests.

### P0-4. Unknown broker semantics are silently converted into valid vn.py states

Files: `src/trader/gateways/qmt/constants.py`, `converter.py`

Current behavior:

- unknown `price_type` -> `OrderType.LIMIT`
- unknown `order_status` -> `Status.NOTTRADED`

This can turn an unsupported/changed broker enum into a plausible but incorrect state. Broker truth must not be guessed.

Required behavior:

- Known enums map explicitly.
- Unknown `price_type` and unknown `order_status` must fail closed with a clear exception containing the raw value.
- Add tests proving unknown values are rejected.

### P0-5. Stock buy/sell direction should use the stock operation field, not `direction` as primary authority

File: `src/trader/gateways/qmt/converter.py`

XtQuant documentation states that `direction` is not applicable to stocks, while `order_type` identifies STOCK_BUY/STOCK_SELL. Current `to_direction()` checks `direction` first and can therefore accept a conflicting or meaningless value before looking at `order_type`.

Required behavior for the current STOCK-only gateway:

- Derive buy/sell from stock `order_type` (`STOCK_BUY` / `STOCK_SELL`).
- Do not use the stock `direction` field as the primary source.
- Unknown stock operation must raise.
- Add conflicting-field tests to ensure `order_type` is authoritative.

## 3. Snapshot consistency issue to fix before reconciliation

### P1-1. Repeated position queries can leave stale positions in OMS

File: `src/trader/gateways/qmt/gateway.py`

`query_position()` only emits rows returned by MiniQMT. If a previously held symbol disappears from the next broker snapshot, no zero-position event is emitted, so vn.py OMS can retain the old position.

Required behavior:

- Track the previous position keys seen by this gateway.
- On every full position snapshot, emit current positions and emit a zero-volume PositionData for previously seen keys that are now absent.
- Keep this logic confined to broker snapshot synchronization; do not invent positions that were never seen.
- Add a test: first snapshot contains a position, second snapshot is empty -> OMS-facing events must include a zero-volume clearing event.

## 4. Verification gaps

The live smoke run had `order_count=0` and `trade_count=0`, so real XtOrder/XtTrade conversion was not exercised against a non-empty live broker response. This is acceptable for a read-only development gate, but it must not be described as live validation of actual OrderData/TradeData fields.

For this hardening task:

- Keep all real-account testing strictly read-only.
- Verify XtOrder/XtTrade field names and enum values against the installed XtQuant SDK and official documentation.
- Do not generate a real order solely to create test data.

## 5. Items that are acceptable in the current implementation

- No XtQuant order or cancel APIs are exposed by `QmtClient`.
- `send_order()` / `cancel_order()` are hard blocked.
- `None` query results are treated conservatively rather than silently coerced to empty lists.
- Unsupported exchanges are rejected.
- Position available-volume bounds are validated.
- The original `qmt_probe.py` remains available as a lower-layer known-good probe.

## 6. Gate decision

**CHANGES_REQUIRED**

The current implementation is a good prototype and the read-only safety property is credible, but the broker-state adapter must be fail-closed and snapshot-correct before it becomes the base for reconciliation or execution.

The follow-up task is defined in:

`interactive/TASK_QMT_GATEWAY_READONLY_HARDENING_20260906.md`
