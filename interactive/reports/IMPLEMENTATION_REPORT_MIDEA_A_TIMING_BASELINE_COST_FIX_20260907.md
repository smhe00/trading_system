# IMPLEMENTATION_REPORT — Midea Timing Baseline Cost-Accounting Fix

对应任务书：`interactive/TASK_MIDEA_A_TIMING_BASELINE_COST_FIX_20260907.md`
基于评审：`interactive/REVIEW_MIDEA_A_TIMING_BASELINE_FIX_20260907.md`（verdict: CHANGES_REQUIRED）
标的：美的集团 `000333.SZ`；分析窗口 **2014-04-01 → 2026-09-04**（12.36 年）；初始资金 1,000,000
日期：2026-09-07
性质：**研究/回测 only**

## 1. 修改文件列表

| 文件 | 变更 |
| --- | --- |
| `src/trader/strategies/midea_timing/ma_regime.py` | `on_trade` 现金账本改为**成本感知**（买卖各扣佣金+滑点）；新增纯函数 `size_board_lots`（预留买入成本后取整手）；文档改称 "conservative-capital MA regime" |
| `src/trader/strategies/midea_timing/__init__.py` | 导出 `size_board_lots` |
| `scripts/midea_timing_backtest.py` | B&H 整手 sizing 改用 `size_board_lots`（成本预留）；MA 输出 `gap_buffer` 与 `deployed_fraction_approx` |
| `tests/strategies/test_midea_ma_regime.py` | 新增成本感知账本测试（买卖成本、多轮无漂移）、整手成本预留测试 |
| `interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_TIMING_BASELINE_COST_FIX_20260907.md` | 本报告（未覆盖旧报告） |

未修改 QmtGateway、MiniQMT 配置、VeighNa Studio；未安装/升级依赖。

## 2. 修复说明

### 3.1 策略 sizing 现金账本成本感知（阻断）
- `on_trade` 现按与回测引擎相同的成本口径更新现金账本：
  - 买入：`cash -= notional + notional×rate + volume×slip`
  - 卖出：`cash += notional − notional×rate − volume×slip`
- 多次往返后账本与"经济现金"不再漂移（此前只按毛额更新，累积成本被虚增为可部署现金）。
- **印花税约定**：**不**计入策略 sizing 账本（vn.py 引擎也不计）；印花税单列披露（`stamp_duty` / `final_equity_net` / `cagr_net`），口径全程一致、不混用。
- 测试：`test_buy_reduces_cash_by_notional_plus_costs`、`test_sell_adds_proceeds_net_of_costs`、`test_multi_round_trip_ledger_does_not_drift`（多轮往返后账本 == 成本感知期望，且毛额口径会高于成本感知口径——证明测试能捕获漂移）；gap-up 测试继续保证现金非负。

### 3.2 B&H 整手 sizing 成本预留（阻断）
- 新增纯函数 `size_board_lots(cash, price, rate, slip, lot)`：选满足
  `shares×price + shares×price×rate + shares×slip ≤ cash` 的最大整手。
- B&H 与策略入场均改用该函数，杜绝 `remaining_cash < 0`（合成杠杆）。
- 测试：`test_reserves_buy_costs`（资本 10 万、价 1.00：朴素按名义买 10 万股需 101,030 > 资本 → 修正后 98,900 股、剩余现金 ≥ 0）；`test_zero_when_no_full_lot_fits`。

### 3.3 既有修复保持
- 无起点前交易、公共起点权益恰 1,000,000、next-bar 成交、只做多、100 股整手、无同收盘价前视、无合成杠杆、B&H 日线含闲置现金 —— 均通过既有 + 新增测试验证（78/78）。

### 3.4 实际敞口澄清（非阻断，已落实）
- 代码/报告统一使用 **conservative-capital MA regime** 表述；MA 指标输出 `gap_buffer=1.20` 与 `deployed_fraction_approx=0.8333`（≈1/1.20，整手取整前），明示典型投入比例约 83% 而非严格 100%。未优化 gap buffer（任务书禁止）。

### 非阻断 4：起始日约定
- B&H 在分析窗口开盘买入，日收益序列自首个收盘标记起；MA 首日可能为空仓平盘。两者日收益统计的时点约定**不完全相同**，报告中不将其描述为完全一致的执行时点（仅在同一公共起点资金/平仓状态与同一窗口下比较）。

## 3. 测试命令与结果

```powershell
python -B -m unittest discover -s tests -t . -v
```
**`Ran 78 tests ... OK`**（基线 12 + QmtGateway 加固 48 + 择时 18），QMT 回归全部通过。

```powershell
python -B scripts\midea_timing_backtest.py --fetch --json work\midea_timing_summary.json
python -B scripts\midea_timing_backtest.py --csv work\midea_000333_daily_back.csv --json work\midea_timing_summary.json
```
两者结果一致（`--fetch` 已实测，退出码 0）。

## 4. 修正后对比表（重算，非复制旧值）

| 指标 | Buy & Hold | MA Regime（conservative-capital） | Delta (MA − BH) |
| --- | --- | --- | --- |
| 起点权益 | 1,000,000 | 1,000,000 | — |
| CAGR | 19.69% | **11.33%**（净 11.22%） | **−8.47pp** |
| 年化波动率 | 29.37% | 19.11% | −10.26pp |
| Sharpe | 0.7475 | 0.6572 | **−0.0903** |
| 最大回撤 | 55.69% | 33.04% | **−22.65pp** |
| Calmar | 0.3537 | 0.3429 | −0.0108 |
| 期末权益 | 9,217,566 | 3,767,495（净 3,721,484） | — |
| 进出场 | 1 / 1 | 42 / 41 | — |
| 年化换手 | 0.83 | 14.91 | — |
| 印花税（卖出） | 4,611 | 46,012 | — |
| 实际敞口（≈） | 100%（整手后） | ≈83.3%（gap_buffer=1.20） | — |

**说明**：与上一版（ddd4ede）相比，MA CAGR 11.40%→**11.33%**、期末权益 3,794,786→3,767,495、换手 15.16→14.91——成本感知账本使每次入场所用资金扣除了已发生的交易成本，数值略降且口径正确。结论方向不变：MA 显著降回撤/降波动，收益与 Sharpe 落后于买入持有，**不宣称更优**。

## 5. 剩余限制（如实声明）

1. 复权价用于信号/总回报研究；固定 0.01/股滑点与绝对现金/整手 sizing 为研究近似，非券商实盘执行价。
2. T+1 为结构性兼容（日线 next-bar 序列），未建模显式可卖持仓约束；未建模涨跌停无法成交。
3. 印花税单列披露，未并入逐日 MA 权益曲线与 sizing 账本（口径已明示、全程一致）。
4. gap_buffer=1.20 使典型投入约 83%，非严格 100%（conservative-capital）。
5. 单一标的/单一区间；`work/` 下数据 gitignored，`--fetch` 可复现。

## 6. 交易副作用声明

**零实盘副作用**：新增委托数 = 0，新增成交数 = 0，撤单数 = 0；未启用/修改 QmtGateway 写路径（`send_order`/`cancel_order` 仍 `NotImplementedError`）；未动 `D:\veighna_studio`、MiniQMT 配置、未安装/升级依赖。

## Definition of Done 核对（成本修复任务书）

```text
[x] strategy cash ledger deducts commission/slippage on buys
[x] strategy cash ledger deducts commission/slippage on sells
[x] multi-round-trip ledger test passes
[x] B&H share sizing reserves buy costs before lot selection
[x] B&H residual cash cannot be negative from buy costs
[x] previous analysis-start / no-lookahead fixes remain intact
[x] common initial equity remains exactly 1,000,000
[x] all existing QMT tests still pass
[x] corrected comparison metrics are recomputed
[x] no live trading side effects
```
