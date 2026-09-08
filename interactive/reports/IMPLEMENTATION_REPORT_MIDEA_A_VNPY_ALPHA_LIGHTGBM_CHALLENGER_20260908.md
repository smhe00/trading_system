# IMPLEMENTATION_REPORT — Midea vnpy.alpha / LightGBM Walk-Forward Challenger

对应任务书：`interactive/TASK_MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER_20260908.md`
标的：美的集团 `000333.SZ`；日期：2026-09-08
性质：**研究/回测 only**

## 1. 能力门结果（任务书 §2；初判 BLOCKED → 用户授权解锁后 PASS）

**初判 BLOCKED**（首轮能力探测）：`import vnpy.alpha` 因缺 `polars` 失败、`lightgbm` 未安装；`vnpy/alpha` 模块文件存在（安装版与上游 `D:\gitee\vnpy-upstream`（v4.4.0）均有，用户所述"文件能找到"属实），但 polars/lightgbm 是 vnpy `pyproject.toml` 中 `alpha` **可选 extras** 声明的运行依赖，本环境从未安装。

**用户授权解锁**（2026-09-08，用户明确选择"授权安装 polars+lightgbm"），安装到 `.venv`：

| 包 | 版本 | 用途 |
| --- | --- | --- |
| polars | 1.44.1 | vnpy.alpha 官方数据集/表达式引擎必需 |
| lightgbm | 4.7.0 | 官方 `LgbModel` 估计器 |
| alphalens-reloaded | 0.4.6 | 官方 `dataset/template.py` 模块级导入必需（随带 statsmodels 0.15.0 / seaborn 0.13.2 / empyrical-reloaded 0.5.12 / formulaic 1.2.2 等） |
| pyarrow | 25.0.1 | 官方 `LgbModel._prepare_data` 的 `to_pandas()` 必需 |

**能力门最终 PASS**：

| 项 | 值 |
| --- | --- |
| vnpy.alpha 导入路径 | `D:\veighna_studio\Lib\site-packages\vnpy\alpha`（随 vn.py 4.4.0 内置） |
| vnpy.alpha 版本 | 4.4.0 |
| polars / lightgbm | 1.44.1 / 4.7.0 |
| 实际使用的官方 API | `AlphaDataset(add_feature/set_label 替代/add_processor/prepare_data/process_data/fetch_learn/fetch_infer)`、`Segment(TRAIN/VALID/TEST)`、`LgbModel`、`AlphaLab(save_dataset/save_model/save_signal)` |

**官方适配点（如实记录）**：
1. `set_label(pl.Expr)` 不可用：官方 `prepare_data` 做 `if self.label_expression:` 真值检查，polars 1.x 对 Expr 求值即抛 `TypeError: the truth value of an Expr is ambiguous`。改用官方 **`add_feature(name="label", result=...)` 结果路径**（标签列为末列，符合 `LgbModel` 的 `columns[2:-1]` 假设；`label_expression` 保持空串）。
2. 边界 purge 用官方 **`add_processor("learn", ...)` 扩展点**；处理器实现为模块级可 pickle 类（`BoundaryPurgeProcessor`），使 `AlphaLab.save_dataset` 可持久化。
3. 冻结 LightGBM 配置与官方 `LgbModel` 参数的最近映射：官方仅暴露 `objective/learning_rate/num_leaves/seed/num_boost_round/early_stopping_rounds`；任务书冻结配置中的 `min_child_samples/subsample/colsample_bytree/verbosity` **官方包装不暴露**，按 LightGBM 默认（nearest fixed mapping，未调参）。固定参数：`learning_rate=0.03, num_leaves=15, num_boost_round=200, early_stopping_rounds=50, log_evaluation_period=0, seed=42`。
4. **环境缺陷（已规避）**：`--fetch` 路径（同一进程加载 xtdata 后训练 lightgbm）在 `LGBM_DatasetSetField` 稳定触发原生 access violation（xtdata 与 lightgbm 原生 DLL 共存冲突）。已按 qmt_probe 的 worker 模式把 xtdata 取数隔离到子进程（`--data-worker`），主进程只读 CSV。
5. 依赖冲突提示（非阻断）：alphalens 依赖链把 `peewee` 装到 3.17.3（vnpy-sqlite/mysql/postgresql 声明 ≥3.17.9）；QMT/基线全量测试 115/115 通过，未发现功能影响，记录备查。

## 2. 修改文件列表

| 文件 | 说明 |
| --- | --- |
| `src/trader/strategies/midea_timing/ml_research.py` | 纯研究层：冻结 10 特征/ y20 标签 polars 表达式、3Y/5Y fold 计划、可 pickle 边界 purge 处理器、ML 确定性模拟（锁定执行/成本约定）、静态分数 B&H |
| `scripts/midea_vnpy_alpha_lightgbm_challenger.py` | 官方 AlphaDataset+LgbModel+AlphaLab walk-forward 编排、评估窗口与比较器、诊断、结论、JSON 输出 |
| `tests/strategies/test_midea_vnpy_alpha_challenger.py` | 16 项确定性测试（不跑重型训练） |
| `interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER_20260908.md` | 本报告 |

未修改锁定基线（`scripts/midea_timing_backtest.py`、`ma_regime.py`、`midea_history_regime_study.py`、`src/trader/gateways/qmt/**`）；未动 VeighNa Studio、MiniQMT 配置。

## 3. 数据

- 源/口径与锁定基线一致：miniQMT（xtdata，**后复权**，含现金分红与送转），2013-09-18（上市）→ 2026-09-04，3089 根（剔除 62 停牌零量 bar）。特征预热用更早 bar（df 自 2013 起）。
- 未添加外部数据集；未静默填充缺失/停牌日。

## 4. 冻结特征 / 目标 / 模型

- **10 特征**（全部仅用 ≤t 收盘信息，单测验证无未来数据）：`ret_5/ret_20/ret_60`、`vol_20/vol_60`（年化滚动 std）、`close_ma20/close_ma60/close_ma120`、`ma20_ma60/ma60_ma120`。
- **目标**：`y20[t] = close[t+20]/close[t] − 1`（回归）；缺失目标行排除；训练/测试边界 purge（`t+20` 落入 OOS 的训练行剔除）。
- **模型**：官方 `LgbModel`，固定参数见 §1.3；无任何超参/特征/阈值优化。

## 5. Walk-forward 计划与 purge 规则

- **3Y**：`train = Y-3-01-01..Y-1-12-31`，`valid = Y-1`（早停用），`OOS = Y`；Y ∈ 2018..2026。
- **5Y**：`train = Y-5-01-01..Y-1-12-31`，Y ∈ 2020..2026（2020 起有完整前 5 年）。
- **purge**：`BoundaryPurgeProcessor`（官方 learn processor）剔除 (a) `t+20` 目标日超出训练区间（含落入 OOS 年）的行；(b) 特征/标签缺失(NaN/null)的行。`t+20` 目标日不进入特征构造；预测仅用 ≤t 特征。每 OOS 年**只拟合一次**新模型（3Y/5Y 各 9/7 折，共 16 折），全年冻结。

## 6. 预测诊断

### 逐折（3Y，trainPurge=purge 后训练行数；corr=预测与实现 y20 的 Pearson；spread=pred>0 组与 ≤0 组实现均值差）

| OOS年 | trainPurge | oos | corr | 符号命中 | LONG占比 | spread |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2018 | 699 | 214 | +0.196 | 0.393 | 0.89 | +3.87pp |
| 2019 | 672 | 233 | −0.235 | 0.579 | 0.69 | −2.38pp |
| 2020 | 671 | 243 | +0.034 | 0.580 | 0.63 | −0.10pp |
| 2021 | 670 | 243 | −0.123 | 0.477 | 0.61 | −0.71pp |
| 2022 | 699 | 242 | +0.220 | 0.430 | 0.82 | +0.29pp |
| 2023 | 708 | 242 | −0.053 | 0.467 | 0.11 | −3.82pp |
| 2024 | 707 | 242 | +0.196 | 0.471 | 0.38 | +1.06pp |
| 2025 | 706 | 243 | −0.179 | 0.362 | 0.57 | −2.86pp |
| 2026 | 707 | 164 | +0.274 | 0.681 | 0.60 | +2.68pp |

5Y 逐折 corr：−0.276 / +0.065 / −0.102 / −0.209 / −0.103 / +0.073 / −0.060（同样无稳定方向）。

### 年代聚合（重叠样本，不做显著性宣称）

| 年代 | 预测源 | n | corr | 符号命中 | 实现均值 LONG | 实现均值 CASH | spread |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2018-2020 | pred3 | 690 | −0.178 | 0.522 | 1.32% | 3.44% | −2.12pp |
| 2018-2020 | pred5 | 243 | −0.276 | 0.580 | 3.96% | 8.90% | −4.94pp |
| 2021-2023 | pred3 | 727 | −0.097 | 0.458 | −1.88% | −0.02% | −1.86pp |
| 2021-2023 | pred5 | 727 | −0.099 | 0.473 | −1.44% | −0.07% | −1.36pp |
| 2024-2026 | pred3 | 629 | +0.045 | 0.477 | 1.41% | 1.76% | −0.35pp |
| 2024-2026 | pred5 | 629 | −0.010 | 0.520 | 1.68% | 1.45% | +0.23pp |

**结论 C 数据基础**：2024-2026 预测与实现 y20 相关性 ≈0（0.045 / −0.010），LONG/CASH 实现均值差 ≈0（−0.35pp / +0.23pp）——**无可靠的正向方向分离**。

## 7. OOS 绩效对比（主口径 MTM；每窗口 1,000,000 空仓起算；ML 为年化 walk-forward）

| 窗口 | 比较器 | final | CAGR | 年化波动 | Sharpe | MaxDD | Calmar | e/x | 年化换手 | 已实现印花税 | 在场时长 | 均毛敞口 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL_3Y 2018-26 | ML_ROLLING | 945,372 | −0.65% | 25.2% | 0.076 | 50.2% | −0.013 | 94/94 | 20.00 | 43,050 | 0.57 | 0.565 |
| | BH_100 | 1,879,272 | 7.60% | 25.4% | 0.411 | 55.7% | 0.137 | 1/0 | 0.12 | 0 | 1.00 | 1.000 |
| | BH_STATIC_CONS | 1,722,957 | 6.52% | 23.4% | 0.398 | 50.1% | 0.130 | 1/0 | 0.10 | 0 | 1.00 | 0.833 |
| | MA_FIXED | 1,387,149 | 3.87% | 19.5% | 0.325 | 31.4% | 0.123 | 30/29 | 6.77 | 14,382 | 0.50 | 0.420 |
| | 匹配敞口诊断 | 1,488,485 | 4.73% | 19.7% | 0.376 | 39.4% | 0.120 | 1/0 | 0.06 | 0 | 1.00 | 0.603 |
| RECENT_3Y 21-26 | ML_ROLLING | 745,457 | −4.99% | 22.7% | −0.200 | 50.1% | −0.100 | 66/66 | 17.14 | 24,514 | 0.50 | 0.488 |
| | BH_100 | 1,049,097 | 0.84% | 23.4% | 0.152 | 55.4% | 0.015 | 1/0 | 0.17 | 0 | 1.00 | 1.000 |
| | BH_STATIC_CONS | 1,039,278 | 0.67% | 17.5% | 0.126 | 45.0% | 0.015 | 1/0 | 0.14 | 0 | 1.00 | 0.833 |
| | MA_FIXED | 909,160 | −1.65% | 12.2% | −0.075 | 29.6% | −0.056 | 21/20 | 4.91 | 6,828 | 0.45 | 0.370 |
| | 匹配敞口诊断 | 1,023,567 | 0.41% | 14.5% | 0.090 | 27.6% | 0.015 | 1/0 | 0.08 | 0 | 1.00 | 0.408 |
| R4_3Y 24-26 | ML_ROLLING | 1,110,776 | 3.96% | 14.7% | 0.393 | 16.1% | 0.247 | 33/33 | 25.86 | 17,519 | 0.49 | 0.481 |
| | BH_100 | 1,639,362 | 20.06% | 18.1% | 1.102 | 13.4% | 1.494 | 1/0 | 0.37 | 0 | 1.00 | 1.000 |
| | BH_STATIC_CONS | 1,524,605 | 16.88% | 15.5% | 1.086 | 11.6% | 1.451 | 1/0 | 0.30 | 0 | 1.00 | 0.833 |
| | MA_FIXED | 1,182,956 | 6.41% | 12.0% | 0.576 | 19.2% | 0.334 | 12/11 | 7.87 | 5,131 | 0.63 | 0.511 |
| | 匹配敞口诊断 | 1,295,090 | 10.03% | 15.3% | 1.050 | 7.4% | 1.363 | 1/0 | 0.17 | 0 | 1.00 | 0.527 |
| ALL_5Y 20-26 | ML_ROLLING | 1,417,027 | 5.30% | 22.8% | 0.361 | 57.2% | 0.093 | 70/70 | 26.77 | 45,267 | 0.61 | 0.606 |
| | BH_100 | 1,724,002 | 8.41% | 23.5% | 0.453 | 55.3% | 0.152 | 1/0 | 0.15 | 0 | 1.00 | 1.000 |
| | BH_STATIC_CONS | 1,600,392 | 7.22% | 21.3% | 0.439 | 49.5% | 0.146 | 1/0 | 0.12 | 0 | 1.00 | 0.833 |
| | MA_FIXED | 1,209,101 | 2.85% | 18.3% | 0.268 | 31.2% | 0.091 | 22/21 | 5.82 | 9,612 | 0.49 | 0.411 |
| | 匹配敞口诊断 | 1,441,465 | 5.57% | 19.4% | 0.420 | 40.6% | 0.137 | 1/0 | 0.09 | 0 | 1.00 | 0.648 |
| RECENT_5Y 21-26 | ML_ROLLING | 774,607 | −4.36% | 22.5% | −0.145 | 56.3% | −0.077 | 60/60 | 14.49 | 20,726 | 0.61 | 0.595 |
| | MA_FIXED | 909,160 | −1.65% | 12.2% | −0.075 | 29.6% | −0.056 | 21/20 | 4.91 | 6,828 | 0.45 | 0.370 |
| | 匹配敞口诊断 | 1,027,494 | 0.47% | 14.4% | 0.099 | 32.0% | 0.015 | 1/0 | 0.10 | 0 | 1.00 | 0.486 |
| R4_5Y 24-26 | ML_ROLLING | 1,234,511 | 8.10% | 15.4% | 0.622 | 14.5% | 0.557 | 28/28 | 23.50 | 15,954 | 0.55 | 0.538 |
| | BH_100 | 1,639,362 | 20.06% | 18.1% | 1.102 | 13.4% | 1.494 | 1/0 | 0.37 | 0 | 1.00 | 1.000 |
| | BH_STATIC_CONS | 1,524,605 | 16.88% | 15.5% | 1.086 | 11.6% | 1.451 | 1/0 | 0.30 | 0 | 1.00 | 0.833 |
| | MA_FIXED | 1,182,956 | 6.41% | 12.0% | 0.576 | 19.2% | 0.334 | 12/11 | 7.87 | 5,131 | 0.63 | 0.511 |
| | 匹配敞口诊断 | 1,344,272 | 11.56% | 15.6% | 1.058 | 8.4% | 1.382 | 1/0 | 0.20 | 0 | 1.00 | 0.602 |

（BH_100/BH_STATIC_CONS 部分窗口与基线研究数字一致；"匹配敞口诊断"= `BH_STATIC_MATCHED_AVG_EXPOSURE`，ex-post、非可部署基准。）

### ML 相对 MA_FIXED 的 delta（主口径）

| 窗口 | ΔCAGR | ΔSharpe | ΔMaxDD | ΔCalmar |
| --- | --- | --- | --- | --- |
| ALL_3Y | −4.52pp | −0.248 | +18.8pp | −0.136 |
| RECENT_3Y | −3.34pp | −0.124 | +20.5pp | −0.044 |
| R4_3Y | −2.45pp | −0.183 | −3.1pp | −0.087 |
| ALL_5Y | +2.45pp | +0.093 | +25.9pp | +0.001 |
| RECENT_5Y | −2.71pp | −0.069 | +26.7pp | −0.022 |
| R4_5Y | +1.69pp | +0.046 | −4.7pp | +0.223 |

### ML 相对"等均毛敞口静态持有"诊断的 delta（结论 D 依据）

| 窗口 | ΔCAGR | ΔSharpe | ΔMaxDD | ΔCalmar |
| --- | --- | --- | --- | --- |
| ALL_3Y | −5.38pp | −0.299 | **+10.9pp** | −0.133 |
| ALL_5Y | −0.27pp | −0.059 | **+16.6pp** | −0.044 |
| R4_3Y | −6.07pp | −0.656 | **+8.7pp** | −1.116 |
| R4_5Y | −3.46pp | −0.436 | **+6.2pp** | −0.825 |

## 8. 结论 A/B/C/D（明确回答）

### A. ML 是否在样本外战胜锁定 MA 基线？→ **否（NO）**

以主评估窗口 ALL_3Y（2018-2026）为准：ML_ROLLING 四项全面落后 MA_FIXED（CAGR −4.52pp、Sharpe −0.248、MaxDD +18.8pp 更差、Calmar −0.136）。RECENT_3Y 同样落后。仅在 **R4_5Y** 单一窗口 ML 四项反超（CAGR +1.69pp、Sharpe +0.046、MaxDD −4.7pp、Calmar +0.223），但按任务书"不得基于单一有利区段宣布胜利"，且该优势在敞口匹配后消失（见 D）。**不宣布 ML 战胜锁定基线。**

### B. 滚动 3Y vs 5Y 是否实质性改变近期 OOS 行为？→ **5Y_BETTER_RECENTLY**（描述性）

可比较窗口上 5Y 全面优于 3Y：ALL_5Y CAGR 5.30% vs ALL_3Y −0.65%；RECENT_5Y −4.36% vs RECENT_3Y −4.99%；R4_5Y 8.10% vs R4_3Y 3.96%（且 R4_5Y 是唯一四项反超 MA 的窗口）。5Y 使用更长训练期（含 2018-2020），对近期 OOS 更有利。此为预声明稳健性比较，非事后调窗。

### C. ML 在 2024-2026 是否显示正向方向分离？→ **否（无可靠分离）**

2024-2026 年代诊断：pred3 corr +0.045、spread −0.35pp；pred5 corr −0.010、spread +0.23pp——预测与实现 y20 相关性≈0、LONG/CASH 实现均值差≈0。冻结的价格/波动特征 + y20 目标 + 固定 LightGBM 配置**无可靠正向方向信息**（逐折 corr 在 −0.28~+0.27 无稳定符号）。

### D. 敞口匹配后是否仍有回撤改善？→ **否，反而更差**

对"等均毛敞口静态持有"（ex-post 诊断）比较，ML 的 MaxDD 在四个窗口**全部更高**（+10.9 / +16.6 / +8.7 / +6.2pp）。ML 在 R4 相对 MA 的"回撤更低"完全由更低平均敞口（~0.48-0.54 vs 静态 1.0）解释；敞口匹配后优势消失且反转。**ML 的换手成本与无效信号使其在同等敞口下回撤更高。**

## 9. 测试与命令结果

```powershell
python -B -m unittest discover -s tests -t . -v
```
**`Ran 115 tests ... OK`**（基线 12 + QMT 加固 48 + 择时 27 + 历史研究 12 + challenger 16）。challenger 测试覆盖：特征不依赖未来数据、y20 精确 t+20、尾部 20 根排除、3Y/5Y 训练窗恰为前 3/5 个日历年、训练标签不跨 OOS、purge 剔除跨边界与缺失行、LONG iff pred>0、只做多、次 bar 执行、整手/成本预留现金非负、持仓不重复下单、静态分数敞口与无再平衡、锁定 MA 参数不变。

```powershell
python -B scripts\midea_vnpy_alpha_lightgbm_challenger.py --csv work\midea_000333_daily_back.csv --json work\midea_vnpy_alpha_lightgbm_summary.json
python -B scripts\midea_vnpy_alpha_lightgbm_challenger.py --fetch --json work\midea_vnpy_alpha_lightgbm_summary.json
```
`--csv` 两次运行与 `--fetch` 输出 **MD5 完全一致**（确定性可复现）。官方 AlphaLab 持久化写入 `work/alpha_lab/`（gitignored），每折保存 dataset/model/signal。

## 10. 限制（如实声明）

1. 前向 y20 样本重叠，诊断不做独立样本显著性宣称（corr/spread 为描述性）。
2. 冻结特征仅价格/波动技术面（任务书限制）；结论不代表其他特征/模型配置。
3. 后复权价用于研究；绝对滑点/现金 sizing 为近似，非券商执行价。
4. T+1 结构性兼容；未建模涨跌停无法成交。
5. 依赖安装系**用户 2026-09-08 显式授权**（polars/lightgbm/alphalens-reloaded/pyarrow），报告如实记录；`peewee 3.17.3` 与 vnpy 数据库模块声明（≥3.17.9）存在补丁级版本差，全量测试通过、功能未受影响，记录备查。
6. `--fetch` 需子进程隔离 xtdata（原生 DLL 与 lightgbm 共存冲突，已规避并记录）。

## 11. 交易副作用声明

**零实盘副作用**：新增委托数 = 0，新增成交数 = 0，撤单数 = 0；未启用/修改 QmtGateway 写路径；未动 `D:\veighna_studio`、MiniQMT 配置；锁定基线零改动；ML 回测未调用任何 MiniQMT 交易接口。

## Definition of Done 核对

```text
[x] official VeighNa Alpha capability is actually used (AlphaDataset/LgbModel/AlphaLab/Segment；初判 BLOCKED→用户授权安装后 PASS 并记录)
[x] no unauthorized package install/upgrade（polars/lightgbm/alphalens-reloaded/pyarrow 为 2026-09-08 用户显式授权的最小解锁安装，已在 §1 记录）
[x] frozen 10-feature set
[x] y20 target only
[x] boundary-purged walk-forward training
[x] rolling-3Y annual OOS completed (2018-2026)
[x] rolling-5Y robustness OOS completed (2020-2026)
[x] common baseline comparisons completed (BH_100/BSC/MA_FIXED/ML)
[x] exposure-normalized diagnostic completed
[x] prediction diagnostics completed (逐折+年代)
[x] no look-ahead/data leakage (特征/标签/purge 测试)
[x] all tests pass (115/115)
[x] locked baselines unchanged
[x] no live trading side effects
```
