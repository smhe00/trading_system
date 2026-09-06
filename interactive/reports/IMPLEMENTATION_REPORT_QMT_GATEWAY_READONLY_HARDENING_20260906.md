# IMPLEMENTATION_REPORT — QmtGateway Read-Only Hardening

对应任务书：`interactive/TASK_QMT_GATEWAY_READONLY_HARDENING_20260906.md`
基于评审：`interactive/REVIEW_QMT_GATEWAY_READONLY_20260906.md`（verdict: CHANGES_REQUIRED）
日期：2026-09-06（加固完成，含真实 MiniQMT 只读冒烟）

## 1. 修改文件列表

**实现（仅任务书允许的文件）：**

| 文件 | 变更 |
| --- | --- |
| `src/trader/gateways/qmt/client.py` | 3.1 账户选择按过滤后唯一 STOCK；3.3 每类响应校验 `account_id` 归属 |
| `src/trader/gateways/qmt/gateway.py` | 3.2 connect 事务化 + 重复连接拒绝；3.6 全量持仓快照清除陈旧持仓 |
| `src/trader/gateways/qmt/converter.py` | 3.4 未知枚举 fail-closed；3.5 方向以 `order_type` 为准；`parse_time` 兼容 Unix 时间戳 |
| `src/trader/gateways/qmt/constants.py` | 移除语义默认值；显式登记 repo 报价类型 55 |
| `tests/qmt/test_converter.py` | 新增/更新：方向语义、未知枚举拒绝、repo price_type、Unix 时间戳 |
| `tests/qmt/test_gateway_readonly.py` | 新增：过滤式账户选择、跨账户拒绝、事务化 connect、重复连接拒绝、陈旧持仓清除、持仓消失/重现 |
| `scripts/qmt_gateway_probe.py` | 未修改（无需变更） |

**未修改：** `scripts/qmt_probe.py`（基线）、vn.py/VeighNa Studio、MiniQMT 配置、其他模块。
**新增报告：** `interactive/reports/IMPLEMENTATION_REPORT_QMT_GATEWAY_READONLY_HARDENING_20260906.md`（本文件，未覆盖旧报告）。

## 2. 各强制修复的行为变更

### 3.1 账户选择（client.py `_select_account_id`）
- 变更：先 `query_account_infos()` → 归一化所有账户类型 → 过滤出 STOCK → 恰好 1 个 STOCK 才选中；0 个或 >1 个报错停止。
- 不再要求"账户总数 == 1"；其他类型（CREDIT/期权等）不会让唯一 STOCK 账户变模糊。

### 3.2 connect 事务化（gateway.py `connect`）
- 变更：connect + 初始四类快照视为一个事务。`client.connect()`、账户/持仓/委托/成交任一阶段失败 → 先 `client.close()` 再置 `self.client=None`，最后 re-raise。
- 重复连接：显式拒绝（`"already connected; call close() before reconnecting"`），不创建第二个会话、不泄漏旧会话；选中并测试该行为。
- 成功后仅在全部阶段完成后写日志。

### 3.3 账户归属校验（client.py）
- Asset / Position / Order / Trade 每行校验 `account_id == 选中账户`；缺失或不一致立即 raise，绝不进入 OMS。

### 3.4 未知枚举 fail-closed（converter.py / constants.py）
- 移除 `DEFAULT_ORDER_TYPE` / `DEFAULT_ORDER_STATUS` 语义默认值。
- 未知 `price_type`、未知 `order_status`、未知股票 `order_type` → 抛 `ValueError`，异常文本含原始值。
- **例外（显式登记，非默认）**：实时数据发现逆回购委托（204001.SH GC001）`price_type=55`，SDK 报价类型列表（xtconstant.py 176–209）未收录该值；判定为本环境逆回购收益率报价方式，显式加入 `ORDER_TYPE_MAP`（55 → LIMIT，逆回购按固定收益率报价）并在常量注释与本节披露。真正未知值（如 999）仍拒绝。

### 3.5 股票方向以 `order_type` 为准（converter.py `to_direction`）
- STOCK_BUY(23)→LONG、STOCK_SELL(24)→SHORT；不再以 `direction` 为主。
- 冲突的 `direction` 不能覆盖有效 `order_type`；未知 `order_type` 抛错。
- 实时佐证：repo 卖出委托 `order_type=24`（正确→SHORT），而 `direction=48`（买标志）——印证 XtQuant 文档"direction 多空，股票不需要"。

### 3.6 全量持仓快照清除陈旧持仓（gateway.py `query_position`）
- 维护上次快照见过的身份键 `(symbol, exchange, direction)`。
- 每次全量快照：先发当前持仓；对"上次见过、本次缺失"的键发 `volume=0/frozen=0` 的 `PositionData` 清除事件；不发明从未见过的持仓。
- 覆盖消失/重现场景。

### 附带修正：`parse_time` 兼容实时时间格式
- 实时 XtOrder/XtTrade 的 `order_time`/`traded_time` 是 **Unix 时间戳（epoch 秒，如 1788485412 → 2026-09-04 09:30:12 +08:00）**，而非文档所述的 `yyyyMMddHHmmss` 字符串。`parse_time` 现两者皆兼容；无法识别时返回 None（不抛错）。

## 3. 新增测试

| 测试 | 覆盖 |
| --- | --- |
| `ClientAccountSelectionTests` | 过滤后唯一 STOCK 选中；STOCK+CREDIT 选中 STOCK；零 STOCK 拒绝；多 STOCK 拒绝；None/空拒绝；account_id 缺失拒绝 |
| `ClientOwnershipTests` | Asset/Position/Order/Trade 跨账户拒绝；匹配账户通过 |
| `GatewayReadOnlyTests.test_client_connect_failure_cleans_up` | 连接失败清理 client |
| `GatewayReadOnlyTests.test_initial_query_failure_closes_client_and_disconnects` | 四个初始查询阶段任一失败 → close + client=None |
| `GatewayReadOnlyTests.test_repeated_connect_is_rejected_and_leaks_nothing` | 重复连接拒绝、不泄漏会话 |
| `GatewayReadOnlyTests.test_missing_position_in_next_snapshot_emits_clearing_event` | 缺失持仓 → 零量清除事件 |
| `GatewayReadOnlyTests.test_position_disappear_then_reappear` | 消失/重现 |
| `DirectionConverterTests`（更新） | order_type 权威；冲突 direction 不覆盖；未知 order_type 拒绝 |
| `OrderConverterTests`（新增） | 未知 price_type/order_status/order_type 拒绝；repo 55→LIMIT |
| `ParseTimeTests`（新增） | Unix 时间戳（int/数字串）解析 |

## 4. 测试命令与结果

```powershell
python -B -m unittest discover -s tests -t . -v
```

结果：**Ran 60 tests ... OK**（基线探针 12 + QmtGateway 加固 48），2026-09-06 执行。

```powershell
python -B .\scripts\qmt_probe.py --vnpy
```
结果：`Read-only probe: PASS`（account_count=1, position_count=2，实时）。

```powershell
python -B .\scripts\qmt_gateway_probe.py
```
结果：`QmtGateway read-only smoke: PASS`（退出码 0），实时，见第 5 节。

## 5. 实时只读冒烟结果

2026-09-06 20:21 完整权限环境运行 `qmt_gateway_probe.py`：

```json
{
  "observed_at": "2026-09-06T20:21:58",
  "mode": "real_account_read_only",
  "account_id": "******2011",
  "account_balance": 503924.23,
  "position_count": 2,
  "order_count": 1,
  "trade_count": 0,
  "gateway_names": ["QMT"],
  "read_only_guard": "send_order/cancel_order raised NotImplementedError"
}
QmtGateway read-only smoke: PASS
```

- 真实委托 XtOrder 已成功转换进 vn.py OMS：`204001.SH`（GC001 逆回购），`order_type=24`（→SHORT）、`price_type=55`（repo→LIMIT）、`order_status=56`（→ALLTRADED）、`order_time` epoch 秒→datetime。
- 这补齐了评审"非空 Order 转换"的验证缺口（`order_count=1`）。
- `trade_count=0`：当前时刻无成交行，**非空 XtTrade 实时转换仍未观察到**，不作为已验证（见第 6 节）。

## 6. 未验证字段/语义（如实声明）

1. **非空 XtTrade 实时转换**：`trade_count=0`，成交转换仅由单元测试（fake 数据）覆盖，未经真实非空成交验证。
2. **price_type=55（逆回购）语义**：由真实委托（204001.SH）观察判定为逆回购收益率报价并映射 LIMIT；SDK/官方文档未收录该值，建议与券商确认后再作最终定论（不影响只读正确性）。
3. **时间字段**：实时为 epoch 秒，文档为 `yyyyMMddHHmmss`；两者均已兼容，但跨券商/版本行为未逐一验证。
4. **`offset_flag` 字段**：尚未用于任何映射（股票场景按 Offset.NONE 处理）；逆回购委托 `offset_flag=49` 的含义未建模。
5. **多账户真实场景**：当前只有 1 个账户，过滤后唯一 STOCK 选择逻辑由单元测试覆盖，未在真实多账户环境复现。

## 7. 交易副作用声明

**全程零交易副作用。** 明确声明：

- **新增委托数 = 0，新增成交数 = 0，撤单数 = 0**（全程仅执行只读查询；`order_count=1` 是当天已存在的真实历史委托，非本次产生）。
- 代码无任何 `order_stock*` / `cancel_order_stock*` / `send_order` / `cancel_order` 的 XtQuant 调用路径；`QmtGateway.send_order()`/`cancel_order()` 仍抛 `NotImplementedError`（冒烟脚本已实测）。
- 未修改 `D:\veighna_studio`、vn.py 官方源码、MiniQMT 配置；未硬编码真实 account_id。
- 未生成任何真实订单/撤单来制造测试数据。

## Definition of Done 核对（加固任务书第 6 节）

```text
[x] unique STOCK account is selected after filtering, not by total account count
[x] cross-account Asset is rejected
[x] cross-account Position is rejected
[x] cross-account Order is rejected
[x] cross-account Trade is rejected
[x] any initial snapshot failure closes the client and leaves gateway disconnected
[x] repeated connect cannot leak a session
[x] unknown order price type is rejected
[x] unknown order status is rejected
[x] unknown stock operation is rejected
[x] STOCK buy/sell derives from order_type
[x] conflicting direction cannot override stock order_type
[x] missing position in next full snapshot emits zero-volume clearing event
[x] original qmt_probe still PASS
[x] QmtGateway read-only smoke still PASS
[x] no real order submitted
[x] no real order cancelled
[x] no modification under D:\veighna_studio
```
