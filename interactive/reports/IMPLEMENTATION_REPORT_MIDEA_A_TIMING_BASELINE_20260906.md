# IMPLEMENTATION_REPORT — Midea A-share Timing Baseline

对应任务书：`interactive/TASK_MIDEA_A_TIMING_BASELINE_20260906.md`
标的：**美的集团 A股 `000333.SZ`**
日期：2026-09-06
性质：**研究/回测 only**（未启用任何实盘能力）

## 1. 修改文件列表

| 文件 | 说明 |
| --- | --- |
| `src/trader/strategies/midea_timing/__init__.py` | 策略包入口 |
| `src/trader/strategies/midea_timing/ma_regime.py` | 纯信号函数（`compute_ma` / `ma_regime_signal`）+ `MaRegimeStrategy(CtaTemplate)` |
| `scripts/midea_timing_backtest.py` | 回测脚本：数据加载/拉取、vn.py CTA 回测、Buy&Hold、指标、对比输出 |
| `tests/strategies/__init__.py` | 测试包标记 |
| `tests/strategies/test_midea_ma_regime.py` | 策略单测（预热/转换/无前视/不做空）+ 真实引擎 next-bar 成交集成测试 |
| `interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_TIMING_BASELINE_20260906.md` | 本报告（未覆盖旧报告） |

未修改 QmtGateway、`scripts/qmt_probe.py`、`scripts/qmt_gateway_probe.py` 及任何既有模块。

## 2. vn.py 模块与实际版本

- 实际使用：**`vnpy_ctastrategy`**（BacktestingEngine, CtaTemplate, BacktestingMode.BAR）
- 版本：`vnpy_ctastrategy 1.4.1`（`D:\veighna_studio\Lib\site-packages\vnpy_ctastrategy`）
- 基础：`vn.py 4.4.0`（EventEngine/MainEngine/ArrayManager）
- 说明：该版本 `BacktestingEngine` 无 `add_data()`，通过注入 `engine.history_data = bars` 喂数据；`BacktestingMode` 为普通 Enum，必须传枚举值（传整数 1 会走 TICK 分支）。

## 3. 数据来源 / 区间 / 复权

- **数据源**：本机 miniQMT 行情服务（xtdata，`127.0.0.1:58610`，`XtMiniQmt`），经 `xtdata.get_market_data_ex(..., dividend_type="back")` 取数。
- **标的**：`000333.SZ`（美的集团）。
- **区间**：2013-09-18（上市）→ 2026-09-04；分析窗口 **2014-04-01 → 2026-09-04**（约 12.36 年，MA120 预热充足）。
- **复权**：**后复权（back-adjust，含现金分红与送转）**。
  - 选择原因：前复权在本股上出现**负价格伪影**（IPO 价高、分红大，2013–2014 前复权价<0），MA 信号在负价格上无意义；后复权早期价≈真实正价、含总回报，无负值。
- **数据质量核验**：
  - CSV 与 SH 交易日历完全对齐（上市日起 3151 行 = 3163 交易日 − 12 上市前日），**无假日填充行**（源数据未虚构交易日）。
  - 62 个零成交量行均为 SH 交易日（**停牌日**，价格平盘），已从回测数据中剔除，避免在不可交易日成交；不构成"静默填充缺失交易日"。
- 数据落盘：`work/midea_000333_daily_back.csv`（gitignored）；`--fetch` 可从 xtdata 复现。

## 4. 执行与成本假设

| 项 | 假设 | 建模方式 |
| --- | --- | --- |
| 执行 | 信号在 t 日收盘产生，**t+1 交易日开盘成交**（宽限价单 → 回测器以次根 bar open 成交） | vnpy_ctastrategy BAR 模式 next-bar cross + 单测验证 |
| T+1 | 日线 + 次 bar 成交 → 买入最早 t+2 才能卖出，结构上满足 T+1 | 文档化（结构性满足） |
| 100 股整手 | 买入量 = floor(权益/价格/100)×100 | 策略内取整（全仓二进制） |
| 佣金 | 万 3（0.0003），买卖双边 | vnpy `rate` 参数 |
| 滑点 | 每股 0.01（约 1 tick） | vnpy `slippage` 参数 |
| 印花税 | 卖出 0.05%（0.0005） | vn.py 引擎不支持单边税，**单独计算并披露**（报告/期末权益单列 `stamp_duty` 与 `*_net`） |
| 禁止卖空 | 状态二进制 0%/100%，只做多 | 策略逻辑 + 单测（pos 永不为负） |
| 仓位 | 100% 当前权益（随权益复利放大），整手取整后残差现金闲置 | 策略自记账现金 ledger + `on_trade` 更新 |

## 5. 执行命令

```powershell
# 数据（可复现）：从本机 miniQMT 拉后复权日线
python -B scripts\midea_timing_backtest.py --fetch --json work\midea_timing_summary.json
# 或复用已保存 CSV
python -B scripts\midea_timing_backtest.py --csv work\midea_000333_daily_back.csv --json work\midea_timing_summary.json

# 全部单测（含既有 QMT 回归）
python -B -m unittest discover -s tests -t . -v
```

## 6. 测试结果

**`Ran 70 tests ... OK`**（基线探针 12 + QmtGateway 加固 48 + Midea 择时 10）。其中择时测试覆盖：

- `compute_ma` 预热（窗口不足返回 None）
- `ma_regime_signal` 真值表（两条件同时成立才 LONG）
- 历史不足不发信号（120 bar < 121 预热）
- CASH→LONG（整手、单次全仓）与 LONG→CASH（全平、不卖空）
- 订单用宽限价（buy=close×1.15 / sell=close×0.85）→ 次 bar open 成交
- **真实 vn.py BacktestingEngine 集成测试**：首个成交发生在信号 bar 的**下一根** bar（无同收盘价前视）

既有 QMT 回归测试（QmtGateway 加固、`qmt_probe`）全部仍通过，未破坏已验收基线。

## 7. Buy & Hold 指标

分析窗口 2014-04-01 → 2026-09-04（12.36 年），初始资金 1,000,000，期初开盘买入、期末收盘卖出，含佣金/滑点/印花税：

| 指标 | 值 |
| --- | --- |
| 期末权益 | 9,217,566 |
| CAGR | **19.69%** |
| 年化波动率 | 29.41% |
| Sharpe（rf=0） | 0.7478 |
| 最大回撤 | 55.71% |
| Calmar | 0.3469 |
| 进出场次数 | 1 / 1 |
| 年化换手（≈） | 0.83 |
| 印花税（卖出） | 4,611 |

## 8. MA Regime 指标（MA20/60/120，二进制全仓）

| 指标 | 值 |
| --- | --- |
| 期末权益 | 4,716,957（印花税后 4,650,061） |
| CAGR | **13.37%**（印花税后 13.24%） |
| 年化波动率 | 22.40% |
| Sharpe（rf=0） | 0.6722 |
| 最大回撤 | 37.28% |
| Calmar | 0.3587 |
| 进出场次数 | 42 / 41（83 笔） |
| 年化换手 | 21.73 |
| 印花税（卖出） | 66,895 |

## 9. 直接对比

| 指标 | Buy & Hold | MA Regime | Delta (MA − BH) |
| --- | --- | --- | --- |
| CAGR | 19.69% | 13.37% | **−6.45pp** |
| 年化波动率 | 29.41% | 22.40% | −7.01pp |
| Sharpe | 0.7478 | 0.6722 | **−0.0756** |
| 最大回撤 | 55.71% | 37.28% | **−18.43pp** |
| Calmar | 0.3469 | 0.3587 | +0.0118 |
| 换手（年化） | 0.83 | 21.73 | — |

**结论（不夸大）**：该 MA Regime 用约 6.5pp 的年化收益和 0.08 的 Sharpe 换来了**回撤显著下降（−18.4pp）**与波动率下降（−7pp），Calmar 基本持平（略升）。**不宣称择时更优**；它是"降回撤/降波动"取向的基线，收益维度落后于买入持有。换手高（年化 21.7，42 进/41 出，全仓进出）带来的交易成本也是收益差距的一部分（含佣金/滑点/印花税）。

## 10. 剩余限制 / 未验证项（如实声明）

1. **复权口径**：使用后复权（含分红送转），已避开前复权负价格伪影；信号与收益在同一复权口径下自洽，但与券商实盘成交价（不复权）不完全一致，成本按后复权价格估算（滑点等相对值近似）。
2. **印花税**：vn.py 引擎不支持单边税，印花税单列披露（期末权益 `*_net`），未并入逐日权益曲线；对 CAGR 影响约 0.13pp（MA）。
3. **换手/交易频率**：83 笔在日线上较多，部分可能源于 MA 参数在震荡市的反复穿越；本任务不做参数挖掘（遵守任务书），后续可作敏感性分析。
4. **无行情过滤/涨跌停**：未建模 A 股涨跌停无法成交、停牌无法成交的滑点/无法成交情形（停牌日已剔除，但涨跌停未建模）。
5. **数据落盘在 gitignored 的 `work/`**：CSV 与摘要未提交；可通过 `--fetch`（需 miniQMT 运行）或本地 CSV 复现。
6. **单一标的/单一区间**：基线仅覆盖美的一只股票，结论不代表一般性。

## 11. 交易副作用声明

**本次任务零实盘副作用。** 明确声明：

- **新增委托数 = 0，新增成交数 = 0，撤单数 = 0**（本次全部为离线回测与只读数据查询）。
- 未启用/修改 QmtGateway 任何写路径；`send_order`/`cancel_order` 仍抛 `NotImplementedError`。
- 未修改 `D:\veighna_studio`、MiniQMT 配置；未安装/升级任何依赖（`vnpy_ctastrategy` 为既有安装）。

## Definition of Done 核对（任务书第 11 节）

```text
[x] target is exactly 000333.SZ
[x] historical adjusted daily data source is documented (miniQMT/xtdata, 后复权)
[x] Buy & Hold baseline is reproducible (script)
[x] MA20/60/120 timing baseline is reproducible
[x] execution avoids same-close look-ahead (next-bar fill + test)
[x] A-share costs/constraints are documented or modeled (T+1/整手/佣金/印花税/滑点/禁卖空)
[x] required metrics are produced for both baselines
[x] unit tests pass (70/70)
[x] existing QMT regression tests still pass
[x] no live order submitted
[x] no live order cancelled
[x] QmtGateway remains read-only
[x] implementation report written under interactive/reports/
```
