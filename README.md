# Trading_system

本地编程入口：`D:\gitee\trading_system`。当前阶段为 **真实账户只读查询 + vn.py 一次性快照验证**。

## 环境

- 项目 Python：`.venv\Scripts\python.exe`，Python 3.13.8。
- `.venv` 使用 `include-system-site-packages = true`，继承 `D:\veighna_studio`。
- 本机已验证版本：vn.py 4.4.0、vnpy_xt 1.4.6、XtQuant 250516.1.1。
- `D:\veighna_studio` 是只读运行时。项目运行使用 `-B` 禁止写入字节码；不在 Studio 中安装、升级、修改或开发。
- 截至 2026-09-06，此目录没有 `.git`，尚未初始化 Git，也没有分支、提交或远程。
- 2026-09-06 已初始化 Git 并关联远程 `https://github.com/smhe00/trading_system`（默认分支 `main`），后续指导文件经该远程仓库传达。

## 运行

在 PowerShell 中：

```powershell
Set-Location D:\gitee\trading_system
.\.venv\Scripts\python.exe -B -X utf8 scripts\qmt_probe.py --vnpy --json work\qmt_snapshot.json
```

默认连接 `D:\国金证券QMT交易端\userdata_mini`，无需手填资金账号。省略 `--vnpy` 可只查询 QMT。
`--qmt-path` 可指定另一个 userdata 路径；只接受唯一的普通股票账户，多账户、无账户、信用或期权等类型均停止。
默认 45 秒总超时，只终止本次探针子进程；连接正常退出时调用 `trader.stop()`。

探针只调用连接、账户订阅及资金/持仓/当日委托/当日成交查询，不包含下单、撤单、划拨调用。
账户订阅仅接收该连接的数据推送，不启动策略或持续监控。
账号输出默认脱敏，但资金、证券代码和委托/成交标识仍属账户数据，保存在被忽略的 `work/` 中。
`--json` 仅允许写入项目 `work/`；成功后更新文件，判断结果时同时检查退出码和 `observed_at`，失败不会覆盖上次成功快照。

## vn.py 验证范围

将 QMT 查询结果转换为 `AccountData`、`PositionData`，通过 `EventEngine` 发送到 `MainEngine` 的 OMS，核对内容后关闭引擎。
没有注册可交易 Gateway，没有启动 GUI、策略、行情服务或后台循环。
委托和成交目前仅保留原始查询字段；尚未接入 OMS 的委托/成交事件、实时行情和持续回调。

映射中 `balance = total_asset`、`available = cash`，避免把证券市值误算成可用资金；持仓 `frozen = volume - can_use_volume`、`price = open_price`。
`yd_volume` 和 `pnl` 暂无可靠映射，保留 vn.py 默认值，不能用于交易决策或收益分析。
零数量记录保留以忠实反映 QMT 返回，记录数量不等于实际持有证券数量。

已安装的 `vnpy_xt` 默认连接迅投研数据中心，在“仿真交易”路径下将 QMT 路径拼接为 `userdata`，不能直接套用当前券商 `userdata_mini`。
本阶段不修改官方插件；后续实时 Gateway 应在项目内实现或适配，并单独验证权限及字段语义。

## 测试与记录

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -v
```

`tests/test_qmt_probe.py` 覆盖账户类型转换、唯一账户约束、失败中止、None 与空列表区分、跨账户返回拒绝、资源清理、账户脱敏，以及 vn.py 金额/持仓字段和事件接收。
离线测试使用模拟查询对象，不连接 QMT；账户类型构造验证会导入本机 XtQuant，其自身初始化可能进行版本检查，不会安装更新。

- `work/qmt_probe.original.py`：修改前探针备份。
- `work/tests.log`、`work/qmt_probe.log`：测试与本机只读连接日志。
- `work/qmt_snapshot.json`：最新成功查询快照。
- `.vntrader/`：本项目 vn.py 配置/日志目录，避免使用用户主目录。

原探针中的 `StockAccount(info.account_id, info.account_type)` 与本机 SDK 不兼容：枚举结果是数字类型，构造函数要求字符串。现通过 SDK 的 `ACCOUNT_TYPE_DICT` 映射后构造。
查询返回 `None` 时停止并报告“不确定是空还是失败”，不会用 `or []` 将其伪装为成功空列表。

接口参考：[迅投 XtQuant 交易模块](https://dict.thinktrader.net/nativeApi/xttrader.html)。具体兼容性以本机已安装 SDK 源码和本次测试为准。

## 只读 QmtGateway（2026-09-06 完成）

按 `interactive/TASK_QMT_GATEWAY_READONLY.md` 实现基于 XtQuant 的只读 VeighNa QmtGateway：

- 代码：`src/trader/gateways/qmt/`（`gateway.py` / `client.py` / `converter.py` / `constants.py` / `__init__.py`）
- 测试：`tests/qmt/test_converter.py`、`tests/qmt/test_gateway_readonly.py`
- 冒烟：`scripts/qmt_gateway_probe.py`（连接真实 MiniQMT，推进 vn.py OMS，校验只读守卫）
- 报告：`interactive/reports/IMPLEMENTATION_REPORT_QMT_GATEWAY_READONLY.md`

```powershell
# 全部单测（42/42）
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -t .

# 只读冒烟（真实 MiniQMT；需在无沙箱限制的终端运行）
.\.venv\Scripts\python.exe -B -X utf8 scripts\qmt_gateway_probe.py
```

账户自动选择唯一 STOCK 账户（0/多/非 STOCK 停止）；`send_order`/`cancel_order` 抛 `NotImplementedError`，全程只读、不硬编码真实账户。
