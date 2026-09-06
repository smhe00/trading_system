# TASK: QmtGateway Read-Only Hardening

Date: 2026-09-06
Based on review: `interactive/REVIEW_QMT_GATEWAY_READONLY_20260906.md`
State: **CHANGES_REQUIRED**

## 1. Goal

Harden the existing read-only QmtGateway so it can be trusted as the broker-state source for later reconciliation work.

Do **not** add writable trading capability.

Target remains:

```text
MiniQMT
  -> XtQuant
  -> QmtClient
  -> QmtGateway
  -> vn.py EventEngine / OMS
```

## 2. Allowed files

Implementation may modify only:

```text
src/trader/gateways/qmt/client.py
src/trader/gateways/qmt/gateway.py
src/trader/gateways/qmt/converter.py
src/trader/gateways/qmt/constants.py
tests/qmt/test_converter.py
tests/qmt/test_gateway_readonly.py
scripts/qmt_gateway_probe.py        # only if needed for read-only verification
interactive/reports/IMPLEMENTATION_REPORT_QMT_GATEWAY_READONLY_HARDENING_20260906.md
```

Do not modify vn.py/VeighNa Studio, MiniQMT configuration, unrelated project modules, or the original `scripts/qmt_probe.py`.

## 3. Mandatory fixes

### 3.1 Correct STOCK account selection

Implement this exact rule:

1. `query_account_infos()`
2. normalize all account types
3. filter to STOCK accounts
4. exactly one STOCK account -> select it
5. zero STOCK accounts -> raise
6. more than one STOCK account -> raise

Other non-STOCK accounts must not make a unique STOCK account ambiguous.

Tests required:

- one STOCK -> success
- one STOCK + one CREDIT -> STOCK selected
- zero STOCK -> reject
- two STOCK -> reject
- missing/invalid account id -> reject

### 3.2 Make gateway connect transactional

`QmtGateway.connect()` must not leave a live session or non-None client after any failed initialization step.

Required:

- If `QmtClient.connect()` fails -> cleanup.
- If account snapshot fails -> cleanup.
- If position snapshot fails -> cleanup.
- If order snapshot fails -> cleanup.
- If trade snapshot fails -> cleanup.
- `self.client` must be `None` after failure.
- The underlying client `close()` must have been called when a session had already been established.
- A repeated `connect()` must not leak the old session. Either explicitly reject an already-connected gateway or close it before reconnecting; choose one behavior and test it.

### 3.3 Validate account ownership on every broker response

For Asset, Position, Order and Trade responses:

```text
row.account_id == selected account_id
```

must hold.

Missing or mismatched account id -> raise immediately and do not push that object into OMS.

Add tests for each data class.

### 3.4 Fail closed on unknown enum values

Remove semantic defaults that can disguise unknown broker values.

Required:

- unknown `price_type` -> raise
- unknown `order_status` -> raise
- unknown stock `order_type` -> raise

Do not silently map unknown values to LIMIT, NOTTRADED, LONG or SHORT.

Exception text should contain the raw unsupported value.

### 3.5 Correct STOCK direction mapping

This gateway is STOCK-only.

For stock Order/Trade conversion:

- use `order_type` STOCK_BUY/STOCK_SELL as the authoritative buy/sell source
- do not rely on XtQuant `direction` as the primary field for stocks
- a conflicting `direction` field must not override a valid stock `order_type`
- unknown `order_type` must raise

Add tests where `order_type` and `direction` conflict.

### 3.6 Clear stale positions on a full snapshot

A repeated `query_position()` must represent current broker truth.

Required behavior:

```text
snapshot 1: 600000.SH volume=100
snapshot 2: []
```

The second snapshot must cause an OMS-facing zero-volume `PositionData` event for the previously seen 600000.SH position so stale holdings do not remain.

Implementation requirements:

- maintain only the minimal previous-position identity/state needed for clearing
- do not invent positions never seen by this gateway
- current returned positions must still be emitted normally
- cleared position must use the same symbol/exchange/direction identity and volume=0/frozen=0

Add unit tests for disappear/reappear scenarios.

## 4. Read-only safety must remain absolute

The following remain prohibited:

```text
order_stock
order_stock_async
cancel_order_stock
cancel_order_stock_async
```

Do not add any writable XtQuant call path.

`QmtGateway.send_order()` and `cancel_order()` must continue to refuse execution.

No real order or cancellation may be used to generate test data.

## 5. Verification requirements

Run:

```powershell
python -B -m unittest discover -s tests -t . -v
python -B .\scripts\qmt_probe.py --vnpy
python -B .\scripts\qmt_gateway_probe.py
```

Real MiniQMT checks remain read-only.

Also verify XtOrder/XtTrade field names and enum semantics against:

1. the installed XtQuant SDK used by this environment
2. official XtQuant documentation

Do not claim live validation of non-empty Order/Trade conversion unless non-empty broker data was actually observed.

## 6. Acceptance criteria

All must hold:

```text
[ ] unique STOCK account is selected after filtering, not by total account count
[ ] cross-account Asset is rejected
[ ] cross-account Position is rejected
[ ] cross-account Order is rejected
[ ] cross-account Trade is rejected
[ ] any initial snapshot failure closes the client and leaves gateway disconnected
[ ] repeated connect cannot leak a session
[ ] unknown order price type is rejected
[ ] unknown order status is rejected
[ ] unknown stock operation is rejected
[ ] STOCK buy/sell derives from order_type
[ ] conflicting direction cannot override stock order_type
[ ] missing position in next full snapshot emits zero-volume clearing event
[ ] original qmt_probe still PASS
[ ] QmtGateway read-only smoke still PASS
[ ] no real order submitted
[ ] no real order cancelled
[ ] no modification under D:\veighna_studio
```

## 7. Report

Write the implementation report to this **new** file:

```text
interactive/reports/IMPLEMENTATION_REPORT_QMT_GATEWAY_READONLY_HARDENING_20260906.md
```

Report must include:

1. exact changed files
2. behavior changes for each mandatory fix
3. tests added
4. exact test commands and results
5. live read-only smoke result
6. any remaining unverified fields/semantics
7. explicit statement of trading side effects (`orders submitted / cancels / fills`)

Do not overwrite the previous implementation report.
