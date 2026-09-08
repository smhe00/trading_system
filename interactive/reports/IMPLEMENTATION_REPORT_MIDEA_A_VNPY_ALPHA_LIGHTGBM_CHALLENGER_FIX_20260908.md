# IMPLEMENTATION_REPORT — Midea vnpy.alpha / LightGBM Challenger Fix

对应任务书：`interactive/TASK_MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER_FIX_20260908.md`
基于评审：`interactive/REVIEW_MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER_20260908.md`（verdict: CHANGES_REQUIRED，P0×2 + P1×1）
标的：美的集团 `000333.SZ`；日期：2026-09-08
性质：**研究/回测 only**

## 1. 修改文件列表

| 文件 | 变更 |
| --- | --- |
| `src/trader/strategies/midea_timing/ml_research.py` | **修复 A**：`simulate_ml` 初态改为 CASH（初始 LONG 立即可执行）；**修复 B**：入场 sizing 改用 signal-close×gap_buffer（不再用次日开盘定股数）、买限价 close×1.15、次日仅在 `next_low ≤ limit` 时以 `min(limit, next_open)` 成交、超限跳空显式不成交；**修复 C**：`fold_schedule` 改为 dict，fit/valid **非重叠**切分（fit=声明训练窗去掉最后一年，valid=最后一年） |
| `scripts/midea_vnpy_alpha_lightgbm_challenger.py` | `run_fold` 用 fit/valid/test 周期构建 AlphaDataset、purge 以声明窗终点为界；逐折报告 `fit_range/valid_range/fit_valid_overlap/fit/valid 行数` |
| `tests/strategies/test_midea_vnpy_alpha_challenger.py` | 新增：初始 LONG 次根入场、初始 CASH→LONG、sizing 用 signal-close×gap_buffer、gap_buffer 影响股数、+10% 跳空全额资金、超限跳空不成交、fit/valid 非重叠 |
| `interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER_FIX_20260908.md` | 本报告 |

锁定基线、QmtGateway、依赖声明零改动；**本修复任务未安装任何包**。

## 2. 修复实现（逐项）

### A. 初始状态可执行（P0）
- `simulate_ml` 初态 `prev_state = "CASH"`（窗口以空仓开始）；首个可用信号若为 LONG，则在**下一可交易 bar** 入场，不再等待后续 CASH→LONG。
- 测试：`test_initial_long_enters_on_next_tradable_bar`（首日起 LONG 且持续 → 恰好一次入场、发生在首个 LONG 信号次根 bar）、`test_initial_cash_then_long_still_enters`、既有 LONG→CASH 保留。

### B. 使用锁定保守资金规则 sizing（P0）
- 入场股数在**信号 bar** 用 `max_price = signal_close × gap_buffer(1.20)` + 买入佣金/滑点预留决定（`size_board_lots`），**不使用次日开盘价**。
- 买限价与锁定基线一致：`signal_close × 1.15`；次日成交条件 `next_low ≤ limit`，成交价 `min(limit, next_open)`；**gap 完全高于限价 → 显式不成交**（不静默假定成交）。
- 测试：`test_sizing_uses_signal_close_times_gap_buffer_not_next_open`、`test_gap_buffer_affects_quantity`、`test_plus_ten_percent_gap_is_fully_funded_no_negative_cash`、`test_gap_beyond_buy_limit_is_no_fill_not_silent`、整手/现金非负保留。

### C. 消除早停验证重叠（P1）
- 官方 `LgbModel.fit` **强制** valid + early_stopping（`callbacks=[lgb.early_stopping(...), ...]`，无禁用开关），故采用任务书允许的**确定、预声明、非重叠** fit/valid 构造：
  - 声明训练窗 = `Y-train_years-01-01 .. Y-1-12-31`
  - `fit = 声明窗去掉最后一年`；`valid = 最后一年`；`test = OOS 年`
- 每折输出 `fit_range/valid_range/fit_valid_overlap=False`（已全部验证为 False）与 fit/valid purge 后行数；早停反馈只来自 valid，与 fit 不重叠、不触 OOS。
- 测试：`test_fit_and_valid_are_non_overlapping` + 脚本逐折 `fit_valid_overlap` 字段断言。

## 3. 泄漏控制保持（任务书 §6）

10 冻结特征、y20 精确 t+20、purge（t+20 目标跨 OOS 即剔除）、无 OOS 行入 fit、每 OOS 年一模型、阈值固定 >0、只做多、无任何特征/超参/阈值优化 —— 全部保持（相关测试保留并通过）。

## 4. 测试与命令结果

```powershell
python -B -m unittest discover -s tests -t . -v
```
**`Ran 122 tests ... OK`**（基线 12 + QMT 加固 48 + 择时 27 + 历史研究 12 + challenger 23）。

```powershell
python -B scripts\midea_vnpy_alpha_lightgbm_challenger.py --csv work\midea_000333_daily_back.csv --json work\midea_vnpy_alpha_lightgbm_summary.json
python -B scripts\midea_vnpy_alpha_lightgbm_challenger.py --fetch --json work\midea_vnpy_alpha_lightgbm_summary.json
```
`--csv` 两次运行与 `--fetch` 输出 **MD5 完全一致**（确定性可复现；fetch 仍走子进程隔离 xtdata）。

## 5. 重算的预测诊断

### 逐折（3Y；fit/valid 非重叠已核验）

| OOS年 | fitRows | validRows | oos | corr | LONG占比 | spread |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2018 | 475 | 224 | 214 | +0.069 | 0.96 | −0.17pp |
| 2019 | 478 | 194 | 233 | −0.223 | 1.00 | +3.30pp |
| 2020 | 458 | 213 | 243 | −0.100 | 1.00 | +4.80pp |
| 2021 | 447 | 223 | 243 | −0.189 | 0.82 | −2.76pp |
| 2022 | 476 | 223 | 242 | +0.462 | 1.00 | −1.66pp |
| 2023 | 486 | 222 | 242 | +0.019 | 0.43 | +0.70pp |
| 2024 | 485 | 222 | 242 | +0.162 | 0.00 | −2.44pp |
| 2025 | 484 | 222 | 243 | −0.202 | 0.00 | −0.69pp |
| 2026 | 484 | 223 | 164 | −0.210 | 0.94 | +2.13pp |

所有折 `fit_valid_overlap = False`。逐折 corr 在 −0.22~+0.46 间无稳定符号。

### 年代聚合（重叠样本，不宣称显著性）

| 年代 | 预测源 | n | corr | 符号命中 | 实现均值 LONG | 实现均值 CASH | spread |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2018-2020 | pred3 | 690 | −0.017 | 0.583 | 6.21% | 1.49% | +4.72pp |
| 2018-2020 | pred5 | 243 | −0.262 | 0.700 | 6.52% | 1.72% | +4.80pp |
| 2021-2023 | pred3 | 727 | −0.032 | 0.413 | −0.38% | 1.32% | −1.70pp |
| 2021-2023 | pred5 | 727 | −0.093 | 0.413 | −1.24% | 0.67% | −1.91pp |
| 2024-2026 | pred3 | 629 | −0.088 | 0.501 | 1.70% | 1.46% | +0.24pp |
| 2024-2026 | pred5 | 629 | +0.059 | 0.540 | 1.68% | 1.38% | +0.30pp |

## 6. 重算的 OOS 绩效（主口径 MTM；每窗口 1,000,000 空仓起算）

| 窗口 | 比较器 | final | CAGR | 年化波动 | Sharpe | MaxDD | Calmar | e/x | 年化换手 | 已实现印花税 | 在场时长 | 均毛敞口 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL_3Y 18-26 | ML_ROLLING | 1,133,999 | 1.47% | 18.9% | 0.172 | 43.3% | 0.034 | 17/16 | 3.55 | 7,441 | 0.67 | 0.540 |
| | BH_100 | 1,879,272 | 7.60% | 26.1% | 0.411 | 55.7% | 0.137 | 1/0 | 0.12 | 0 | 1.00 | 1.000 |
| | BH_STATIC_CONS | 1,722,957 | 6.52% | 22.0% | 0.398 | 50.1% | 0.130 | 1/0 | 0.10 | 0 | 1.00 | 0.833 |
| | MA_FIXED | 1,387,149 | 3.87% | 15.3% | 0.325 | 31.4% | 0.123 | 30/29 | 6.77 | 14,382 | 0.50 | 0.420 |
| | 匹配敞口诊断 | 1,468,945 | 4.57% | 15.0% | 0.374 | 38.3% | 0.119 | 1/0 | 0.06 | 0 | 1.00 | 0.582 |
| RECENT_3Y 21-26 | ML_ROLLING | 759,531 | −4.68% | 14.7% | −0.252 | 41.3% | −0.114 | 15/14 | 3.19 | 4,358 | 0.51 | 0.401 |
| | BH_100 | 1,049,097 | 0.84% | 23.4% | 0.152 | 55.4% | 0.015 | 1/0 | 0.17 | 0 | 1.00 | 1.000 |
| | BH_STATIC_CONS | 1,039,278 | 0.67% | 17.5% | 0.126 | 45.0% | 0.015 | 1/0 | 0.14 | 0 | 1.00 | 0.833 |
| | MA_FIXED | 909,160 | −1.65% | 12.2% | −0.075 | 29.6% | −0.056 | 21/20 | 4.91 | 6,828 | 0.45 | 0.370 |
| | 匹配敞口诊断 | 1,019,639 | 0.34% | 7.8% | 0.083 | 23.2% | 0.015 | 1/0 | 0.07 | 0 | 1.00 | 0.333 |
| R4_3Y 24-26 | ML_ROLLING | 1,074,270 | 2.68% | 6.5% | 0.443 | 7.5% | 0.358 | 2/1 | 0.91 | 413 | 0.24 | 0.194 |
| | BH_100 | 1,639,362 | 20.06% | 18.1% | 1.102 | 13.4% | 1.494 | 1/0 | 0.37 | 0 | 1.00 | 1.000 |
| | BH_STATIC_CONS | 1,524,605 | 16.88% | 15.5% | 1.086 | 11.6% | 1.451 | 1/0 | 0.30 | 0 | 1.00 | 0.833 |
| | MA_FIXED | 1,182,956 | 6.41% | 12.0% | 0.576 | 19.2% | 0.334 | 12/11 | 7.87 | 5,131 | 0.63 | 0.511 |
| | 匹配敞口诊断 | 1,114,757 | 4.10% | 4.0% | 1.017 | 3.2% | 1.290 | 1/0 | 0.07 | 0 | 1.00 | 0.224 |
| ALL_5Y 20-26 | ML_ROLLING | 1,441,844 | 5.57% | 20.4% | 0.368 | 47.5% | 0.117 | 22/21 | 6.12 | 10,134 | 0.94 | 0.788 |
| | BH_100 | 1,724,002 | 8.41% | 24.4% | 0.453 | 55.3% | 0.152 | 1/0 | 0.15 | 0 | 1.00 | 1.000 |
| | BH_STATIC_CONS | 1,600,392 | 7.22% | 20.8% | 0.439 | 49.5% | 0.146 | 1/0 | 0.12 | 0 | 1.00 | 0.833 |
| | MA_FIXED | 1,209,101 | 2.85% | 14.4% | 0.268 | 31.2% | 0.091 | 22/21 | 5.82 | 9,612 | 0.49 | 0.411 |
| | 匹配敞口诊断 | 1,565,075 | 6.87% | 19.7% | 0.435 | 47.7% | 0.144 | 1/0 | 0.11 | 0 | 1.00 | 0.803 |
| RECENT_5Y 21-26 | ML_ROLLING | 986,297 | −0.24% | 18.4% | 0.079 | 44.8% | −0.005 | 22/21 | 4.89 | 6,810 | 0.92 | 0.751 |
| | MA_FIXED | 909,160 | −1.65% | 12.2% | −0.075 | 29.6% | −0.056 | 21/20 | 4.91 | 6,828 | 0.45 | 0.370 |
| | 匹配敞口诊断 | 1,035,350 | 0.61% | 15.4% | 0.116 | 40.7% | 0.015 | 1/0 | 0.12 | 0 | 1.00 | 0.654 |
| R4_5Y 24-26 | ML_ROLLING | 1,381,551 | 12.70% | 14.6% | 0.893 | 17.3% | 0.735 | 10/9 | 7.16 | 4,655 | 0.88 | 0.731 |
| | BH_100 | 1,639,362 | 20.06% | 18.1% | 1.102 | 13.4% | 1.494 | 1/0 | 0.37 | 0 | 1.00 | 1.000 |
| | BH_STATIC_CONS | 1,524,605 | 16.88% | 15.5% | 1.086 | 11.6% | 1.451 | 1/0 | 0.30 | 0 | 1.00 | 0.833 |
| | MA_FIXED | 1,182,956 | 6.41% | 12.0% | 0.576 | 19.2% | 0.334 | 12/11 | 7.87 | 5,131 | 0.63 | 0.511 |
| | 匹配敞口诊断 | 1,459,029 | 14.99% | 13.9% | 1.076 | 10.5% | 1.426 | 1/0 | 0.26 | 0 | 1.00 | 0.764 |

### ML 相对 MA_FIXED 的 delta（主口径）

| 窗口 | ΔCAGR | ΔSharpe | ΔMaxDD | ΔCalmar |
| --- | --- | --- | --- | --- |
| ALL_3Y | −2.40pp | −0.153 | +11.9pp | −0.089 |
| RECENT_3Y | −3.03pp | −0.177 | +11.6pp | −0.058 |
| R4_3Y | −3.73pp | −0.133 | −11.7pp | +0.024 |
| ALL_5Y | +2.72pp | +0.100 | +16.3pp | +0.026 |
| RECENT_5Y | +1.41pp | +0.154 | +15.2pp | +0.050 |
| R4_5Y | +6.29pp | +0.317 | −1.9pp | +0.401 |

### ML 相对"等均毛敞口静态持有"诊断的 delta（结论 D 依据）

| 窗口 | ΔCAGR | ΔSharpe | ΔMaxDD | ΔCalmar |
| --- | --- | --- | --- | --- |
| ALL_3Y | −3.10pp | −0.202 | **+5.0pp** | −0.085 |
| RECENT_3Y | −5.02pp | −0.335 | **+18.1pp** | −0.128 |
| R4_3Y | −1.42pp | −0.574 | **+4.3pp** | −0.932 |
| ALL_5Y | −1.30pp | −0.067 | −0.2pp | −0.027 |
| RECENT_5Y | −0.85pp | −0.038 | **+4.1pp** | −0.020 |
| R4_5Y | −2.29pp | −0.183 | **+6.8pp** | −0.692 |

## 7. 重算的结论 A/B/C/D

### A. ML 是否在样本外战胜锁定 MA 基线？→ **否（NO）**

主评估窗口 ALL_3Y（2018-2026）：ML 四项全面落后 MA_FIXED（CAGR −2.40pp、Sharpe −0.153、MaxDD +11.9pp 更差、Calmar −0.089）；RECENT_3Y 亦落后。仅 ALL_5Y/RECENT_5Y/R4_5Y 在 CAGR/Sharpe 上反超，但除 R4_5Y 外 MaxDD 显著更差（+15~16pp）；R4_5Y 虽四项反超（CAGR +6.29pp、Sharpe +0.317、MaxDD −1.9pp、Calmar +0.401），按任务书"不得基于单一有利区段宣布胜利"，且该优势在敞口匹配后消失（D）。**不宣布 ML 战胜锁定基线。**

### B. 滚动 3Y vs 5Y → **5Y_BETTER_RECENTLY**（描述性）

可比较窗口 5Y 全面优于 3Y：ALL_5Y 5.57% vs ALL_3Y 1.47%；RECENT_5Y −0.24% vs RECENT_3Y −4.68%；R4_5Y 12.70% vs R4_3Y 2.68%（R4_5Y 为唯一四项反超 MA 的窗口）。5Y 训练期更长（含 2018-2020），近期 OOS 更有利。预声明稳健性比较，非事后调窗。

### C. ML 在 2024-2026 是否显示正向方向分离？→ **否（无可靠分离）**

2024-2026：pred3 corr −0.088、spread +0.24pp；pred5 corr +0.059、spread +0.30pp——预测与实现 y20 相关性≈0、LONG/CASH 实现均值差≈0。冻结价格/波动特征 + y20 + 固定 LightGBM 配置无可靠正向方向信息（逐折 corr 亦无稳定符号）。

### D. 敞口匹配后是否仍有回撤改善？→ **否（多数窗口更差）**

对"等均毛敞口静态持有"（ex-post）比较，ML 的 MaxDD 在 6 个窗口中 5 个更高（+4.1~+18.1pp），仅 ALL_5Y 持平（−0.2pp）。ML 在 R4 相对 MA 的"回撤更低"基本由更低平均敞口解释；敞口匹配后优势消失/反转。**ML 无稳健的回撤优势。**

## 8. 环境披露（延续上轮）

- 上轮用户授权安装（`.venv`）：polars 1.44.1、lightgbm 4.7.0、alphalens-reloaded 0.4.6（含 statsmodels 0.15.0/seaborn 0.13.2/empyrical-reloaded 0.5.12/formulaic 1.2.2 等）、pyarrow 25.0.1。
- 观测依赖冲突（未处理、功能未受影响、测试全过）：alphalens 依赖链把 `peewee` 装为 3.17.3，vnpy-sqlite/mysql/postgresql 声明 ≥3.17.9。
- **本修复任务未安装/升级任何包。**

## 9. 限制（如实声明）

1. 前向 y20 样本重叠，诊断不做显著性宣称。
2. 冻结特征仅价格/波动技术面；结论不代表其他特征/模型配置。
3. 后复权价用于研究；绝对滑点/现金 sizing 为近似。
4. T+1 结构性兼容；未建模涨跌停无法成交。
5. 官方 `LgbModel` 强制 early-stopping，已用确定非重叠 fit/valid 构造消除重叠反馈；报告逐折有效区间与行数。
6. ML 模拟的限价成交语义（`next_low ≤ limit` 才成交、超限跳空不成交）是对锁定基线 vn.py bar-crossing 的确定性复刻，已在测试中固化。

## 10. 交易副作用声明

**零实盘副作用**：新增委托数 = 0，新增成交数 = 0，撤单数 = 0；未启用/修改 QmtGateway 写路径；未动 `D:\veighna_studio`、MiniQMT 配置；锁定基线零改动；未安装任何包。

## Definition of Done 核对

```text
[x] initial LONG signal enters on next tradable bar
[x] initial CASH -> LONG transition still correct
[x] ML sizing uses signal-close * gap_buffer, not future open
[x] board-lot/cost reserve/no-negative-cash tests pass
[x] execution semantics mirror/document locked baseline (限价+low 门槛成交，测试固化)
[x] no overlapping early-stopping feedback (fit/valid 非重叠，全部折 overlap=False)
[x] train/OOS leakage controls remain intact
[x] full tests pass (122/122)
[x] all challenger metrics are recomputed
[x] --csv (×2) / --fetch agree (MD5 一致)
[x] locked baseline and QmtGateway unchanged
[x] no live trading side effects
```
