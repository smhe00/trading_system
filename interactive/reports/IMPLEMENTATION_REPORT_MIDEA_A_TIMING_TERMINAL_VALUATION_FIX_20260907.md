# IMPLEMENTATION_REPORT — Midea Timing Baseline Terminal Valuation Fix

对应任务书：`interactive/TASK_MIDEA_A_TIMING_TERMINAL_VALUATION_FIX_20260907.md`
基于评审：`interactive/REVIEW_MIDEA_A_TIMING_BASELINE_COST_FIX_20260907.md`（verdict: CHANGES_REQUIRED）
标的：美的集团 `000333.SZ`；分析窗口 **2014-04-01 → 2026-09-04**（12.36 年）；初始资金 1,000,000
日期：2026-09-07
性质：**研究/回测 only**

## 1. 修改文件列表

| 文件 | 变更 |
| --- | --- |
| `src/trader/strategies/midea_timing/ma_regime.py` | 新增共享清算纯函数 `terminal_liquidation(equity, shares, price, rate, slip, stamp)` |
| `src/trader/strategies/midea_timing/__init__.py` | 导出 `terminal_liquidation` |
| `scripts/midea_timing_backtest.py` | B&H 改为**主口径=末收盘盯市(MTM)** + 显式 1,000,000 起点锚（首日 open→close 收益计入）；B&H 与 MA 均通过共享 `terminal_liquidation` 产出可选清算指标 |
| `tests/strategies/test_midea_ma_regime.py` | 新增 `TerminalLiquidationTests`（清算纯函数）、`TerminalConventionTests`（MA 末持仓/末空仓清算、B&H 同锚点同口径） |
| `interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_TIMING_TERMINAL_VALUATION_FIX_20260907.md` | 本报告（未覆盖旧报告） |

未修改 QmtGateway、MiniQMT 配置、VeighNa Studio、无关模块；未安装/升级依赖。

## 2. 选定的统一起点/终点口径

- **共同起点锚**：两策略在分析窗口起点均以**权益 = 1,000,000、空仓**起评；`start_equity` 字段显式输出。
- **主口径 = 末收盘盯市（mark-to-market）**：两策略期末权益均为最后一根收盘标记值（持仓未平、不计人工清仓成本）；主指标 CAGR/Sharpe/年化波动/MaxDD/Calmar 全部基于此口径，两策略一致。
- **可选清算口径**：两策略均用共享 `terminal_liquidation` 计算 `liquidated_final_equity` / `liquidated_cagr` / `terminal_sell_commission` / `terminal_sell_slippage` / `terminal_stamp_duty`；若期末空仓则清算调整 = 0；**不向 vn.py 成交历史注入伪造平仓交易**。
- 首期收益不再被静默省略：B&H 日线序列在分析起点开盘插入 1,000,000 锚点后再按收盘标记，首日 open→close 变动计入收益统计；MA 因 next-bar 执行在起点日天然空仓（余额=1,000,000），起点锚自然存在。

## 3. 实现细节

- `terminal_liquidation(equity, shares, price, rate, slip, stamp)`：
  - `shares ≤ 0` → `liquidated_final_equity = equity`，各终端成本 = 0。
  - `shares > 0` → `liquidated = equity − (notional×rate + shares×slip + notional×stamp)`，返回三项成本与调整额。
- B&H：`daily_equity = [1,000,000 锚点] + [remaining_cash + shares×close ...]`；`final_equity`(主) = 最后标记值；清算视图 = `terminal_liquidation(final_equity, shares, end_price, ...)`。
- MA：主 `final_equity` = 引擎盯市余额末值；`final_shares = Σ买 − Σ卖`；`last_close` 取末 bar 收盘；清算视图 = `terminal_liquidation(...)`。
- 放弃旧 `final_equity_net`/`cagr_net` 变体，避免与新的主/清算双口径混淆。

## 4. 新增/更新测试

- `TerminalLiquidationTests`：持仓清算扣佣金+滑点+印花税（各项校验）；空仓清算调整 = 0。
- `TerminalConventionTests`：
  - MA 末持仓（上升趋势收尾）→ 清算值 < 主盯市值、调整额与终端印花税 > 0；
  - MA 末空仓（先升后跌收尾）→ 清算值 == 主盯市值、调整 = 0；
  - B&H 起点锚 = 1,000,000；主终值 > 清算值（未扣终端成本）；清算值与共享 helper 完全一致（同口径）。
- 既有成本账本、无前视、起点门控、gap-up 无负现金、QMT 回归测试全部保留并通过。

## 5. 测试命令与结果

```powershell
python -B -m unittest discover -s tests -t . -v
```
**`Ran 83 tests ... OK`**（基线 12 + QmtGateway 加固 48 + 择时 23）。

```powershell
python -B scripts\midea_timing_backtest.py --fetch --json work\midea_timing_summary.json
python -B scripts\midea_timing_backtest.py --csv work\midea_000333_daily_back.csv --json work\midea_timing_summary.json
```
两者结果完全一致（`--fetch` 已实测，退出码 0）。

## 6. 重算对比表（主口径 = 末收盘盯市；清算口径单列）

| 指标 | Buy & Hold | MA Regime（conservative-capital） | Delta (MA − BH) |
| --- | --- | --- | --- |
| start_equity | 1,000,000 | 1,000,000 | — |
| **主：期末权益（MTM）** | 9,225,164 | 3,767,495 | — |
| **主：CAGR** | 19.69% | 11.33% | **−8.36pp** |
| 年化波动率 | 29.39% | 19.11% | −10.28pp |
| Sharpe | 0.7585 | 0.6572 | **−0.1013** |
| MaxDD | 55.69% | 33.04% | **−22.65pp** |
| Calmar | 0.3536 | 0.3429 | −0.0107 |
| 进出场 | 1 / 1 | 42 / 41 | — |
| 年化换手 | 0.83 | 14.91 | — |
| 交易印花税 | 4,611 | 46,012 | — |
| **清算：期末权益** | 9,217,566 | 3,764,916 | — |
| **清算：CAGR** | 19.69% | 11.32% | −8.37pp |
| 清算调整额 | 7,599 | 2,579 | — |
| 终端卖佣金 | 2,767 | 939 | — |
| 终端卖滑点 | 221 | 75 | — |
| 终端印花税 | 4,611 | 1,565 | — |
| 期末持仓（股） | 22,100 | 7,500 | — |

**说明**：主口径（MTM）下两策略口径一致；清算口径（可选）用同一 helper 计算。B&H 计入首日 open→close 后 Sharpe 由 0.7475→0.7585。结论不变：MA 显著降回撤/降波动，收益与 Sharpe 落后于买入持有；主/清算 CAGR 差值均 <0.1pp，量级如评审预期很小。**不宣称择时更优。**

## 7. 剩余限制（如实声明）

1. 复权价用于信号/总回报研究；固定 0.01/股滑点与绝对现金/整手 sizing 为研究近似，非券商实盘执行价。
2. T+1 为结构性兼容（日线 next-bar 序列），未建模显式可卖持仓约束；未建模涨跌停无法成交。
3. 印花税：交易印花税按实际卖单计（MA 46,012）；终端清算印花税单列（MA 1,565）——口径全程一致并明示。
4. gap_buffer=1.20 使典型投入约 83%（`deployed_fraction_approx=0.8333`），非严格 100%（conservative-capital MA regime）。
5. 单一标的/单一区间；`work/` 下数据 gitignored，`--fetch` 可复现。

## 8. 交易副作用声明

**零实盘副作用**：新增委托数 = 0，新增成交数 = 0，撤单数 = 0；未启用/修改 QmtGateway 写路径（`send_order`/`cancel_order` 仍 `NotImplementedError`）；未动 `D:\veighna_studio`、MiniQMT 配置、未安装/升级依赖。

## Definition of Done 核对（终值修复任务书）

```text
[x] Buy & Hold and MA share one explicit start-equity convention (1,000,000)
[x] Buy & Hold and MA share one primary terminal valuation convention (mark-to-market)
[x] first-period return is not silently omitted for one benchmark only (B&H anchor point)
[x] optional liquidation accounting is symmetric (shared terminal_liquidation helper)
[x] open MA terminal position is handled correctly (final_shares=7,500, adjustment 2,579)
[x] previous safety/cost/no-lookahead fixes remain intact
[x] all tests pass (83/83)
[x] baseline is recomputed (--fetch == --csv)
[x] no live trading side effects
```
