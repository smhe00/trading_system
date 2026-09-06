# REVIEW — QmtGateway Read-Only Hardening

Date: 2026-09-06
Reviewed commit: `5626426f0a41fd88182be4f585ac66eb624809ab`
Task: `interactive/TASK_QMT_GATEWAY_READONLY_HARDENING_20260906.md`

## Verdict

**PASS**

The mandatory hardening items are implemented and the read-only QMT gateway is accepted as the current broker-state source for later reconciliation work.

## Independent review findings

1. **STOCK account selection** now filters all accounts by normalized type and requires exactly one STOCK account; non-STOCK accounts do not create false ambiguity.
2. **Connect cleanup** closes the client and clears `self.client` when client connect or any initial snapshot query fails; repeated connect is explicitly rejected.
3. **Account ownership** is checked on Asset, Position, Order and Trade rows before conversion/push.
4. **Unknown broker enums** now fail closed instead of silently defaulting. The observed reverse-repo `price_type=55` is explicitly registered rather than used as a generic fallback.
5. **STOCK direction** is derived from `order_type` and conflicting XtQuant `direction` does not override it.
6. **Stale positions** are cleared by emitting zero-volume PositionData when a previously seen identity disappears from a later full snapshot.
7. **Read-only boundary remains intact**: QmtClient has no order/cancel path and QmtGateway `send_order` / `cancel_order` still refuse execution.
8. Reported verification is materially stronger than the first implementation: 60 tests pass, the original probe still passes, the gateway smoke test passes, and one real non-empty XtOrder was observed and converted into OMS.

## Residual limitations — accepted for this gate

- Real non-empty XtTrade conversion has still not been observed; unit tests cover it, but this remains an explicitly unverified live field path.
- Reverse-repo `price_type=55` semantics are environment-observed and not documented by the installed SDK; keep the mapping explicit and provisional.
- `connect()` is transactional with respect to session/client cleanup, not atomic rollback of already-emitted OMS events. This is acceptable for the current read-only snapshot gate but must be addressed architecturally when reconciliation becomes authoritative.

These limitations do not block the current read-only milestone.

## Gate decision

```text
QmtGateway read-only baseline        PASS
QmtGateway read-only hardening       PASS
Broker state -> vn.py OMS            ACCEPTED
Writable trading capability          NOT AUTHORIZED
```

Next work should proceed above this stable read-only broker-state layer. No live order capability is authorized by this review.
