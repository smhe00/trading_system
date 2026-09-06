# IMPLEMENTATION_REPORT — 只读 QmtGateway

对应任务书：`interactive/TASK_QMT_GATEWAY_READONLY.md`（2026-09-06 执行）。

## 1. 修改文件列表

**新增（Gateway 代码，目录规范与任务书一致）：**

| 文件 | 说明 |
| --- | --- |
| `src/trader/gateways/qmt/__init__.py` | 包入口，导出 `QmtGateway` |
| `src/trader/gateways/qmt/gateway.py` | `QmtGateway(BaseGateway)` 只读网关 |
| `src/trader/gateways/qmt/client.py` | `QmtClient`：封装 XtQuantTrader，只暴露只读查询 |
| `src/trader/gateways/qmt/converter.py` | XtQuant → vn.py 纯函数转换器 |
| `src/trader/gateways/qmt/constants.py` | 常量与映射表（不依赖 xtquant 导入） |

**新增（测试与脚本）：**

| 文件 | 说明 |
| --- | --- |
| `tests/qmt/test_converter.py` | 转换器单元测试（fake 数据，不依赖真实 MiniQMT） |
| `tests/qmt/test_gateway_readonly.py` | Gateway 只读测试 + QmtClient 账户选择测试（mock client） |
| `scripts/qmt_gateway_probe.py` | 只读冒烟脚本（真实 MiniQMT 联调用） |

**其他：** `tests/__init__.py`、`tests/qmt/__init__.py`（测试包标记，使单命令发现生效）。

**未修改：** `scripts/qmt_probe.py`（基线探针，保持原样）、`D:\veighna_studio`、vn.py 官方源码、MiniQMT 配置。

## 2. QmtGateway 架构

```text
MiniQMT (D:\国金证券QMT交易端\userdata_mini)
   ↓ XtQuantTrader (session id 随机生成, 每次连接唯一)
QmtClient (client.py)
   ├─ connect(): start → connect → 自动挑选唯一 STOCK 账户 → subscribe
   ├─ query_account()   → XtAsset
   ├─ query_positions() → list[XtPosition]
   ├─ query_orders()    → list[XtOrder]   (cancelable_only=False)
   ├─ query_trades()    → list[XtTrade]
   └─ close(): stop
   ↓ converter.py (纯函数, 可单测)
vn.py 对象: AccountData / PositionData / OrderData / TradeData
   ↓ 标准 Gateway 回调
self.on_account / on_position / on_order / on_trade
   ↓
vn.py EventEngine → OmsEngine (MainEngine)
```

- **账户选择**：`client._select_account_id()` 调用 `query_account_infos()`，要求恰好 1 个且类型为 `STOCK`（`ACCOUNT_TYPE_DICT[2]`），0 个/多个/非 STOCK 均抛错停止；**全程不硬编码真实 account_id**。
- **安全**：`QmtClient` 不提供任何下单/撤单方法；`QmtGateway.send_order()` / `cancel_order()` 记录日志后**抛 `NotImplementedError`**，绝不触碰 XtQuant 交易 API。`subscribe()` 仅记日志（不订阅行情）。
- **连接生命周期**：`connect(setting)` 读取 `QMT路径`/`会话ID`（缺省用 `constants.DEFAULT_QMT_PATH`、随机会话号），连接成功后立即做一次四类数据全量拉取推送 OMS；`close()` 停止会话。失败时清理 `client` 引用并向上抛出。

## 3. XtQuant → VeighNa 字段映射

| vn.py 对象 | XtQuant 数据 | 映射 |
| --- | --- | --- |
| `AccountData` | `XtAsset` | `accountid=account_id`；`balance=total_asset`；`frozen=frozen_cash`；`available=cash`（证券可用资金=现金，非总资产-冻结）；`extra={market_value, fetch_balance}` |
| `PositionData` | `XtPosition` | `symbol/exchange` 由 `stock_code` 拆解（SH→SSE、SZ→SZSE、BJ→BSE）；`direction=NET`；`volume=volume`；`frozen=volume-can_use_volume`；`price=open_price`（与基线探针一致）；`yd_volume=yesterday_volume`；`extra={avg_price, market_value, profit_rate, last_price, on_road_volume}`。`can_use_volume` 越界即报错 |
| `OrderData` | `XtOrder` | `orderid=str(order_id)`；`type`：`price_type` 11→LIMIT、5→MARKET、其余默认 LIMIT；`direction`：`direction`/`order_type`（48/23→LONG，49/24→SHORT）；`offset=NONE`；`price=price`；`volume=order_volume`；`traded=traded_volume`；`status`：见状态映射表；`datetime=parse_time(order_time)`（yyyyMMddHHmmss）；`reference=strategy_name`；`extra={order_sysid, price_type, status_msg, order_remark}` |
| `TradeData` | `XtTrade` | `orderid=str(order_id)`；`tradeid=str(traded_id)`；`direction` 同 Order 规则；`offset=NONE`；`price=traded_price`；`volume=traded_volume`；`datetime=parse_time(traded_time)` |

**订单状态映射**（xtconstant → vn.py Status）：

| XtQuant | 值 | vn.py |
| --- | --- | --- |
| ORDER_UNREPORTED / ORDER_WAIT_REPORTING | 48 / 49 | SUBMITTING |
| ORDER_REPORTED | 50 | NOTTRADED |
| ORDER_PART_SUCC | 55 | PARTTRADED |
| ORDER_PARTSUCC_CANCEL / ORDER_REPORTED_CANCEL / ORDER_PART_CANCEL / ORDER_CANCELED | 52/51/53/54 | CANCELLED |
| ORDER_SUCCEEDED | 56 | ALLTRADED |
| ORDER_JUNK / ORDER_UNKNOWN | 57 / 255 | REJECTED |

## 4. 测试命令

```powershell
# 全部测试（基线探针 12 + QmtGateway 30 = 42）
python -B -m unittest discover -s tests -t . -v

# 或分开跑
python -B -m unittest discover -s tests -v          # 基线探针
python -B -m unittest discover -s tests/qmt -v      # QmtGateway

# 只读冒烟（真实 MiniQMT 联调）
python -B .\scripts\qmt_gateway_probe.py

# 基线探针（验收 A）
python -B .\scripts\qmt_probe.py --vnpy
```

## 5. 测试结果

**单元测试（2026-09-06 执行）：** `Ran 42 tests ... OK`

- `tests.test_qmt_probe`（基线，未改动）：12/12 通过
- `tests.qmt.test_converter`：16/16 通过（Asset/Position/Order/Trade 映射、状态/方向/类型映射、非法数据拒绝、时间解析）
- `tests.qmt.test_gateway_readonly`：14/14 通过（connect 推送四类数据、对象 gateway_name、连接失败清理、send/cancel 抛 NotImplementedError、未连接查询仅记日志、close 停止 client、QmtClient 唯一 STOCK 账户选择规则与目录校验）

**冒烟脚本（真实 MiniQMT）—— 实时验收已通过：**

- **基线探针实时 PASS**（用户终端 2026-09-06 11:32:55 与完整权限环境 11:38 复跑）：`python .\scripts\qmt_probe.py --vnpy` → `MiniQMT connection: OK`、`account_count=1 / position_count=1`、`Read-only probe: PASS`。
- **QmtGateway 实时冒烟 PASS**（2026-09-06 11:38:11，完整权限环境）：`python .\scripts\qmt_gateway_probe.py` → `QmtGateway(QMT) read-only connect: OK`，唯一 STOCK 账户 ******2011（balance 503924.23），OMS 收到 `position_count=1 / order_count=0 / trade_count=0`（当日无委托/成交，与探针数据一致），`gateway_names=["QMT"]`，`read_only_guard: send_order/cancel_order raised NotImplementedError`，输出 `QmtGateway read-only smoke: PASS`，退出码 0。**验收 B/C/D 全部满足。**

**关于执行上下文：** 自动化工具默认沙箱会拦截 XtQuant 到 MiniQMT 的底层 IPC（共享内存/命名管道），表现为 `connect()=-1`；在用户授权的完整权限（danger-full-access）模式下实时联调全部通过。此限制属于工具沙箱边界，不是代码或环境配置问题。

## 6. 已知限制

1. **行情不支持**：`subscribe()` 仅记日志，本网关只做账户/持仓/委托/成交四类状态查询。
2. **只支持 STOCK 账户**：恰好 1 个 STOCK 账户时自动使用；多账户/信用账户等按任务书要求报错停止。
3. **无定时轮询**：`query_*` 为手动/连接时一次性拉取；如需持续同步需在外部定时调用（本任务不引入自动策略逻辑）。
4. 委托/成交时间按 `yyyyMMddHHmmss` 解析，异常格式返回 `None`（不抛错）。
5. `PositionData.price` 采用基线探针一致的 `open_price`；`avg_price` 等存入 `extra` 不丢失。

## 7. 交易副作用声明

**全程零交易副作用。** 明确声明：

- 本次实现与测试过程中：**新增委托数 = 0，新增成交数 = 0，撤单数 = 0**。
- 代码中不存在任何 `order_stock` / `order_stock_async` / `cancel_order_stock` / `cancel_order_stock_async` / `send_order` / `cancel_order` 的 XtQuant 调用路径；`QmtGateway.send_order`/`cancel_order` 直接抛 `NotImplementedError`。
- 未修改 `D:\veighna_studio`、vn.py 官方源码、MiniQMT 配置；未硬编码真实 account_id。
- 冒烟脚本中的 `send_order`/`cancel_order` 守卫调用同样只会命中 `NotImplementedError`，不触达任何交易接口。

## Definition of Done 核对

```text
[x] QmtGateway 可连接 MiniQMT          （实时 PASS：qmt_gateway_probe.py 11:38 冒烟通过）
[x] 自动识别唯一 STOCK 账户             （QmtClient._select_account_id + 单测；实时冒烟 ******2011）
[x] AccountData 正常进入 vn.py          （mock 单测通过 + 实时冒烟 OMS 收到）
[x] PositionData 正常进入 vn.py         （同上，position_count=1）
[x] OrderData 正常进入 vn.py            （同上，当日 order_count=0）
[x] TradeData 正常进入 vn.py            （同上，当日 trade_count=0）
[x] MainEngine/OMS 可读取这些状态       （冒烟脚本读取 OMS 计数 + gateway_names=["QMT"]）
[x] qmt_probe.py 仍 PASS                （12/12 单测通过；实时 PASS 11:32:55 / 11:38 确认）
[x] 单元测试 PASS                       （42/42）
[x] 没有任何下单 / 撤单                 （见第 7 节声明）
[x] 没有修改 VeighNa Studio             （未触碰）
[x] 没有硬编码真实 account_id           （未硬编码）
[x] 提交 IMPLEMENTATION_REPORT.md       （本文件）
```
