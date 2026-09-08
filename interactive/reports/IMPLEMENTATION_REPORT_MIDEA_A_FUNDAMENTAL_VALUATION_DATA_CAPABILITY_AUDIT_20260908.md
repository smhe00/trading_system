# IMPLEMENTATION_REPORT — Midea Fundamental/Valuation Point-in-Time Data Capability Audit

对应任务书：`interactive/TASK_MIDEA_A_FUNDAMENTAL_VALUATION_DATA_CAPABILITY_AUDIT_20260908.md`
标的：`000333.SZ`；窗口：2014-01-01..2026-09-04；日期：2026-09-08
性质：**数据能力/审计 only**（不建模型、不调参）

## 1. 修改文件列表

| 文件 | 说明 |
| --- | --- |
| `src/trader/strategies/midea_timing/fundamental_pit.py` | 纯 PIT helper：可用性门槛、as-of 映射策略、特征可行性分类（fail-closed） |
| `scripts/midea_fundamental_data_capability_audit.py` | 能力静态核验 + 活数据提取（覆盖/时间戳/重述/证明面板/特征矩阵）；服务不可用即 fail-closed |
| `tests/strategies/test_midea_fundamental_data_capability.py` | 13 项确定性测试（PIT 规则 + fail-closed + 静态能力核验） |
| `interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_FUNDAMENTAL_VALUATION_DATA_CAPABILITY_AUDIT_20260908.md` | 本报告 |

锁定 V1/V2/基线/QmtGateway 零改动；未安装/升级任何包；未修改 `D:\veighna_studio`/MiniQMT 配置。

## 2. 本地 API / 能力核验（任务书 §2，源码级、未假定）

已装 XtQuant 的财务能力（`xtdata`，`D:\veighna_studio\Lib\site-packages\xtquant\xtdata.py`，xtquant 250807.1.2）：

```text
download_financial_data(stock_list, table_list=[], start_time='', end_time='', incrementally=None)
download_financial_data2(stock_list, table_list=[], start_time='', end_time='', callback=None)
get_financial_data(stock_list, table_list=[], start_time='', end_time='', report_type='report_time')
get_financial_data_ori(stock_list, table_list=[], start_time='', end_time='', report_type='report_time')
```

- `get_financial_data` 返回 DataFrame 并做日期换算；`get_financial_data_ori` 返回**原始行**（毫秒时间戳保留）——审计用 `_ori` 以保留精确可用性时间戳。
- `report_type` 参数存在（默认 `'report_time'`）。

**服务端表名（server table）↔ 逻辑名**：Income=ASHAREINCOME、Balance=ASHAREBALANCESHEET、CashFlow=ASHARECASHFLOW、Capital=CAPITALSTRUCTURE、HolderNum=SHAREHOLDER、Top10Holder=TOP10HOLDER、Top10FlowHolder=TOP10FLOWHOLDER、PershareIndex=PERSHAREINDEX。

**原始行时间字段**（审计实测，非假设）：

| 字段 | 含义 | 是否可用性时间戳 |
| --- | --- | --- |
| `m_anntime` | **公告时间（毫秒）** | **是（PIT 可用性）** |
| `m_timetag` | 报告期标签（毫秒） | 否（报告期） |
| `m_quarter` | 期/季度指示 | 否（报告期） |
| `actual_ann_dt` | 公告日期（ASHAREINCOME 中观察到） | 是（补充） |

## 3. PIT 硬门槛判定（任务书 §3）

- **`m_anntime` 为可靠的历史可用性时间戳**：5 张表**全部行**均填充（Income 77/77、Balance 59/59、CashFlow 61/61、Capital 216/216、PershareIndex 55/55），0 缺失。
- 硬规则遵守：**绝不用报告期（`m_timetag`/`m_quarter`）单独映射交易日期**；缺失可用性时间戳 → fail-closed（审计 helper 测试覆盖）。
- **硬门槛：PASS**（存在可靠历史可用性时间戳）。

## 4. 重述/修订风险（任务书 §4）

**证据：同一报告期存在多个行且 `m_anntime` 不同**（= 首披 + 后续修订版本均被返回，修订元数据可用，**非 latest-snapshot-only**）：

| 表 | 多行报告期数 | 含不同 m_anntime 版本的报告期数 | 示例（期 → 公告时间版本） |
| --- | ---: | ---: | --- |
| ASHAREINCOME | 27 | 27 | 2014-03-31 → [2014-04-29, 2015-04-29]；2014-12-31 → [2015-03-31, 2016-03-26] |
| ASHAREBALANCESHEET | 6 | 6 | 2015-12-31 → [2016-03-26, 2016-04-30, 2016-08-31, 2017-03-31] |
| ASHARECASHFLOW | 11 | 11 | 2014-03-31 → [2014-04-29, 2015-04-29] |
| CAPITALSTRUCTURE | 0 | 0 | 股本变动逐条记录（无重述） |
| PERSHAREINDEX | 5 | 5 | 2014-12-31 → [2015-03-31, 2016-03-26] |

**分类：`REVISION_METADATA_AVAILABLE_BUT_NEEDS_POLICY`** —— 修订版本与各自公告时间戳均可见（可据此选"首披版本"、或把修订视为新可用性事件）；但需实现并验证"每报告期取最早 m_anntime 为首披"的 PIT 选择策略后才算完全泄漏安全。**不做 latest-snapshot 误用**。

## 5. 2014-2026 覆盖量化（任务书 §6）

| 表 | 行数 | 不同报告期 | 首期 | 末期 | 含可用性时间戳 | 缺失时间戳 |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| ASHAREINCOME | 77 | 50（季度） | 2014-03-31 | 2026-06-30 | 77 | 0 |
| ASHAREBALANCESHEET | 59 | 50 | 2014-03-31 | 2026-06-30 | 59 | 0 |
| ASHARECASHFLOW | 61 | 50 | 2014-03-31 | 2026-06-30 | 61 | 0 |
| CAPITALSTRUCTURE | 216 | 216（股本变动） | 2014-03-31 | 2026-08-29 | 216 | 0 |
| PERSHAREINDEX | 55 | 50 | 2014-03-31 | 2026-06-30 | 55 | 0 |

覆盖跨越目标窗口（2014-01-01..2026-09-04），季度覆盖连续（50 期 ≈ 2014Q1..2026Q2）；无缺失填充。明显的缺口：财务表起始为 2014-03-31（美的 2013-09 上市后首个完整报告期，2013 年报/2013Q4 未含于 `report_time` 窗口内，可另行核实），其余连续。

## 6. 估值 / 股本 / 资本化（任务书 §5.4/5.5）

- **股本 PIT 数据存在**：CAPITALSTRUCTURE `total_capital`（总股本）、`circulating_capital`（流通股本）、`freeFloatCapital`、`restrict_circulating_capital` —— 216 条逐股本变动记录，**每行有 m_anntime**。
- **每股/ROE 指标存在**：PERSHAREINDEX `s_fa_bps`（每股净资产）、`s_fa_eps_basic/diluted`、`du_return_on_equity`（ROE）、`s_fa_ocfps`、`s_fa_fcfps`、`gear_ratio`、`gross_profit` 等。
- **PE/PB/PS/市值**：原始财务表**无直接估值字段**；`__market_cap__` 概念**可由 `total_capital`（PIT）× 不复权历史价（xtdata `dividend_type='none'`）推导** → 标记 **DERIVABLE**，并强制**不得用后复权价**推导估值（本审计不推导、不静默使用）。

## 7. 候选特征可行性矩阵（任务书 §9）

| 特征 | 所需 PIT 安全字段（实测存在） | 分类 |
| --- | --- | --- |
| revenue_ttm_growth | revenue ✓ | DIRECTLY_AVAILABLE |
| net_profit_ttm_growth | net_profit_excl_min_int_inc（归母净利）✓ | DIRECTLY_AVAILABLE |
| operating_cashflow_ttm / net_profit_ttm | net_cash_flows_oper_act + 归母净利 ✓ | DIRECTLY_AVAILABLE |
| ROE_TTM | 归母净利 + tot_shrhldr_eqy_excl_min_int（归母权益）✓ | DIRECTLY_AVAILABLE |
| liability_to_assets | tot_liab + tot_assets ✓ | DIRECTLY_AVAILABLE |
| gross_margin_ttm | revenue + total_operating_cost ✓ | DIRECTLY_AVAILABLE |
| PE_TTM | 归母净利 + `__market_cap__` | DERIVABLE（total_capital × 不复权价） |
| PB | 归母权益 + `__market_cap__` | DERIVABLE（同上） |
| free_cashflow_yield | net_cash_flows_oper_act + cash_pay_acq_const_fiolta（capex）+ `__market_cap__` | DERIVABLE（同上） |

（`__market_cap__` 派生**强制用不复权价**，禁止后复权；本审计不实际计算特征。）

## 8. as-of 证明面板（任务书 §7；PIT 门槛通过后构建）

- 策略：`next_trading_day`（披露时点未知 → 下一交易日可用），仅用 `m_anntime`；缺失时间戳 fail-closed。
- 覆盖 3021 个美的交易日；413 条带可用性时间戳的财务记录参与；缺失时间戳排除 0。
- 披露边界示例（披露日 → 首个可用交易日，旧→新记录切换）：

| 交易日期 | 披露时间 | 新记录（期/字段） |
| --- | --- | --- |
| 2014-04-01 | 2014-03-31 00:00 | CAPITALSTRUCTURE 2014-03-31 total_capital… |
| 2014-04-17 | 2014-04-16 00:00 | CAPITALSTRUCTURE 2014-04-18… |
| 2014-04-24 | 2014-04-23 00:00 | CAPITALSTRUCTURE 2014-04-30… |

（示例边界以股本变动记录为多，因其逐条时间戳最密；收入/净利等财务报表记录同样进入面板。面板仅作血缘验证，不建模、不评收益。）

## 9. 泄漏测试（任务书 §8；13 项确定性测试）

- 报告期单独不激活记录、披露前看不到新季度、披露边界后可看到、同日披露未知时点 → 次交易日可用、缺失时间戳 fail-closed、未来基本面不回填、美的交易日为主日期；
- 重述版本不覆盖早期 as-of 状态（面板保留两版、审计显式分类修订风险）；
- 特征可行性分类（直取/可派生/不可用）；
- 静态能力核验（4 个财务 API 签名存在、`m_anntime` 在原始 schema 中、表映射 Income→ASHAREINCOME）。

## 10. 环境健康（任务书 §13，诊断 only）

`python -m pip check`：仍报告 `peewee 3.17.3` vs `vnpy-sqlite/mysql/postgresql >=3.17.9`。全量测试通过、功能未受影响；依赖修复需另行授权。**本任务未变更任何包**。

## 11. 交易副作用声明

**零实盘副作用**：未产生/无法产生任何委托、成交、撤单；未启用/修改 QmtGateway 写路径；未动 `D:\veighna_studio`、MiniQMT 配置；锁定 V1/V2/基线文件零改动；未安装任何包。

## 12. 最终门结论

```text
PIT_FUNDAMENTALS_PARTIAL
```

**理由（证据支撑）**：
- ✅ 硬 PIT 门槛 **PASS**：`m_anntime`（公告毫秒时间戳）在 5 张表 100% 行填充，覆盖 2014-03-31..2026-06-30，可靠历史可用性时间戳成立。
- ✅ 非 latest-snapshot-only：同一报告期存在**多个版本且 m_anntime 不同**（重述元数据可用）。
- ⚠ 但实现"每报告期取最早 m_anntime 为首披版本"的 PIT 选择策略并验证其正确性后，所提字段才算完全泄漏安全（`REVISION_METADATA_AVAILABLE_BUT_NEEDS_POLICY`）。
- 因此**能力就绪、策略待落实** → `PIT_FUNDAMENTALS_PARTIAL`；满足下述条件后升级为 `PIT_FUNDAMENTALS_READY`：实现并测试首披选择策略、复核 2013Q4/2013 年报覆盖、确认估值派生仅用不复权价。

**未授权后续动作**（由架构师决定）：在 PIT 策略落地并复审计通过前，不构建基本面 challenger V3。

## Definition of Done 核对

```text
[x] installed XtQuant financial capability is inspected, not assumed（源码级 + 实测）
[x] exact APIs/tables/fields are reported
[x] report-period vs publication-time distinction is enforced（m_anntime vs m_timetag，测试）
[x] restatement/revision risk is explicitly classified（REVISION_METADATA_AVAILABLE_BUT_NEEDS_POLICY）
[x] 2014-2026 coverage is quantified（5 表、50 期、时间戳 100%）
[x] candidate feature feasibility matrix is complete（6 直取 + 3 可派生）
[x] PIT as-of proof is built only if safe（m_anntime 通过后构建）
[x] leakage tests pass or audit fails closed（13 项确定性测试 + 服务不可用 fail-closed）
[x] no ML/backtest optimization is performed
[x] no dependency mutation（pip check 诊断 only）
[x] locked V1/V2/baseline/QmtGateway unchanged
[x] no live trading side effects
```
