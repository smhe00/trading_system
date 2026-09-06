# TASK: 实现只读 QmtGateway

## 1. 目标

在现有 `trading_system` 项目中，实现一个基于 XtQuant 的 **只读 VeighNa QmtGateway**。

目标链路：

```text
MiniQMT
  ↓
XtQuant
  ↓
QmtGateway
  ↓
vn.py MainEngine / OmsEngine
```

本任务只处理：

- 账户
- 持仓
- 当日委托
- 当日成交

**禁止任何下单、撤单或其他实盘写操作。**

---

## 2. 已知环境

项目目录：

```text
D:\gitee\trading_system
```

Python 环境：

```text
D:\gitee\trading_system\.venv
```

VeighNa Studio：

```text
D:\veighna_studio
```

MiniQMT userdata：

```text
D:\国金证券QMT交易端\userdata_mini
```

当前已验证：

```text
Python 3.13.8              PASS
vn.py                      PASS
EventEngine/MainEngine     PASS
XtQuant                    PASS
MiniQMT read-only connect  PASS
```

已有底层探针：

```text
scripts/qmt_probe.py
```

该脚本已经成功读取：

- 唯一 STOCK 账户
- Asset
- Positions
- Orders
- Trades

`qmt_probe.py` 是已验证基线，**禁止破坏其现有功能**。

---

## 3. 目录规范

新增代码放在：

```text
src/
└── trader/
    └── gateways/
        └── qmt/
            ├── __init__.py
            ├── gateway.py
            ├── client.py
            ├── converter.py
            └── constants.py
```

测试放在：

```text
tests/
└── qmt/
```

不要创建：

```text
src/trading_system/
```

---

## 4. 功能要求

实现：

```python
QmtGateway(BaseGateway)
```

至少支持：

```text
connect()
close()

query_account()
query_position()
query_orders()
query_trades()
```

通过 XtQuant 读取 MiniQMT 数据。

---

## 5. VeighNa 数据映射

将 XtQuant 数据转换成 VeighNa 标准对象：

```text
XtQuant Asset
    → AccountData

XtQuant Position
    → PositionData

XtQuant Order
    → OrderData

XtQuant Trade
    → TradeData
```

并通过标准 Gateway 回调发送：

```python
self.on_account(...)
self.on_position(...)
self.on_order(...)
self.on_trade(...)
```

不要绕过 VeighNa Gateway/EventEngine 直接修改 OMS 状态。

---

## 6. 账户选择规则

MiniQMT 当前只有一个 STOCK 账户。

实现时：

1. 自动调用 `query_account_infos()`
2. 筛选 STOCK 账户
3. 如果只有一个，自动使用
4. 如果为 0 个，报错并停止
5. 如果超过 1 个，报错并停止

**不要在代码中硬编码真实 account_id。**

---

## 7. 安全限制

本任务运行在真实 MiniQMT 客户端上，因此必须严格只读。

### 明确禁止

不得调用：

```text
order_stock
order_stock_async
cancel_order_stock
cancel_order_stock_async
```

以及任何：

```text
send_order
cancel_order
```

真实写接口。

`QmtGateway.send_order()` 和 `cancel_order()` 如果必须满足抽象接口，可以：

- 明确抛出 `NotImplementedError`
- 或返回拒绝结果

但绝不能调用 XtQuant 实盘交易 API。

---

## 8. 禁止事项

禁止：

- 修改 `D:\veighna_studio`
- 修改 vn.py 官方源码
- 升级 vn.py
- 升级 XtQuant
- 升级 numpy/PySide 等基础依赖
- 修改 MiniQMT 配置
- 写死真实账户 ID
- 下单
- 撤单
- 自动交易
- 引入 Qlib
- 引入 cvxportfolio
- 引入 skfolio
- 做策略逻辑
- 大规模重构项目

本任务只做 **QMT → vn.py 的只读 Gateway**。

---

## 9. 测试要求

至少增加：

```text
tests/qmt/test_converter.py
tests/qmt/test_gateway_readonly.py
```

### converter 测试

验证：

```text
Asset → AccountData
Position → PositionData
Order → OrderData
Trade → TradeData
```

字段映射正确。

尽量使用 mock/fake 数据，不依赖真实 MiniQMT。

### Gateway smoke test

允许增加只读脚本，例如：

```text
scripts/qmt_gateway_probe.py
```

运行后应完成：

```text
QmtGateway connect
      ↓
发现唯一 STOCK account
      ↓
AccountData
PositionData
OrderData
TradeData
      ↓
进入 VeighNa EventEngine/OMS
```

---

## 10. 验收标准

任务完成必须满足：

### A. 原有探针

```powershell
python .\scripts\qmt_probe.py
```

仍然 PASS。

### B. Gateway

QmtGateway 能成功连接当前 MiniQMT。

### C. 数据

VeighNa 能获得：

```text
AccountData
PositionData
OrderData
TradeData
```

### D. OMS

通过：

```python
MainEngine
```

能够查询到对应：

```text
Account
Positions
Orders
Trades
```

### E. 安全

整个测试过程中：

```text
新增委托数 = 0
新增成交数 = 0
撤单数     = 0
```

---

## 11. 完成后提交报告

完成后输出简短报告：

```text
IMPLEMENTATION_REPORT.md
```

内容包括：

1. 修改文件列表
2. QmtGateway 架构
3. XtQuant → VeighNa 字段映射
4. 测试命令
5. 测试结果
6. 已知限制
7. 明确声明是否发生任何交易副作用

禁止只写“测试通过”，必须列出实际执行的测试。

---

# Definition of Done

只有以下全部满足才算完成：

```text
[ ] QmtGateway 可连接 MiniQMT
[ ] 自动识别唯一 STOCK 账户
[ ] AccountData 正常进入 vn.py
[ ] PositionData 正常进入 vn.py
[ ] OrderData 正常进入 vn.py
[ ] TradeData 正常进入 vn.py
[ ] MainEngine/OMS 可读取这些状态
[ ] qmt_probe.py 仍 PASS
[ ] 单元测试 PASS
[ ] 没有任何下单
[ ] 没有任何撤单
[ ] 没有修改 VeighNa Studio
[ ] 没有硬编码真实 account_id
[ ] 提交 IMPLEMENTATION_REPORT.md
```
