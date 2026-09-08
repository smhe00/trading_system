# IMPLEMENTATION_REPORT — Midea vnpy.alpha Context-Feature Challenger V2

对应任务书：`interactive/TASK_MIDEA_A_VNPY_ALPHA_CONTEXT_FEATURE_CHALLENGER_20260908.md`
基于已锁定 V1：`interactive/REVIEW_MIDEA_A_VNPY_ALPHA_EXECUTION_TIMELINE_FIX_20260908.md`（MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER_V1 = PASS / LOCKED）
标的：`000333.SZ`；市场上下文：`000300.SH`（沪深300）；日期：2026-09-08
性质：**研究/回测 only**（特征消融实验，非优化任务）

## 1. 修改文件列表

| 文件 | 说明 |
| --- | --- |
| `src/trader/strategies/midea_timing/ml_context_research.py` | V2 的 7 个预声明上下文特征（polars 表达式）+ 严格年代包含诊断 `era_contained` |
| `scripts/midea_vnpy_alpha_context_challenger.py` | V1（复用锁定 `run_fold` 保证复现）/V2（参数化 `run_fold_v2`）3Y+5Y 折、6 窗口、V2-V1/V2-MA deltas、exposure-matched、严格年代诊断、JSON 输出 |
| `tests/strategies/test_midea_vnpy_alpha_context_challenger.py` | 17 项确定性测试 |
| `interactive/reports/IMPLEMENTATION_REPORT_MIDEA_A_VNPY_ALPHA_CONTEXT_FEATURE_CHALLENGER_20260908.md` | 本报告 |

**锁定 V1 文件零改动**（`ml_research.py`/challenger 脚本/V1 测试/基线/历史研究/QmtGateway 全部未改）；数据/模型/执行语义全部复用锁定 helper（`simulate_ml`/`fold_schedule`/`make_purge_processor`/`finalize_metrics`/`pred_diagnostics` 等）。**未安装/升级/降级任何包**。

## 2. 能力门 / 数据可用性

- **000300.SH（沪深300）本地 XtQuant 可用**：`get_instrument_detail` 确认（InstrumentName=沪深300），3163 根日线（2013-09-02..2026-09-04），close 2320→4548。能力门 PASS。
- 取数沿用子进程隔离（`--data-worker`：stock + CSI300 同 worker 内取数，xtdata 不与 lightgbm 共存）。
- 对齐：股票可交易日为主，CSI300 按**精确日期** join；**join 缺失 = 0 行**（`excluded_rows=0`，CSI300 覆盖全部股票交易日）；无前向/后向填充；停牌零量股票日沿用锁定剔除。

## 3. 特征定义

**V1（对照，锁定 10 个，名字逐一复现）**：`ret_5/ret_20/ret_60/vol_20/vol_60/close_ma20/close_ma60/close_ma120/ma20_ma60/ma60_ma120`。

**V2 = V1 + 恰好 7 个预声明特征**（全部仅用 ≤t 信息，测试验证无未来数据）：

| 特征 | 定义 |
| --- | --- |
| volume_ratio20 | volume[t]/MA20(volume)[t] − 1 |
| range_20 | mean((high−low)/close, 后 20 根) |
| mkt_ret20 | CSI300_close[t]/CSI300_close[t−20] − 1 |
| mkt_ret60 | CSI300_close[t]/CSI300_close[t−60] − 1 |
| mkt_vol20 | 后 20 根 CSI300 日收益的年化 std |
| rel_ret20 | stock ret_20 − mkt_ret20 |
| rel_ret60 | stock ret_60 − mkt_ret60 |

无估值/北向/情绪/行业/成交额等新数据；无特征选择/剪枝/手调阈值。

## 4. 折与标签包含

- 与锁定 V1 完全一致：3Y（OOS 2018..2026 部分）/ 5Y（2020..2026 部分）；非重叠 fit/valid（fit=声明窗去掉最后一年、valid=最后一年）；分段感知标签包含（FIT t+20≤fit_end、VALID t+20≤valid_end）。
- 32 折（16 V1 + 16 V2），每折一模型并全年冻结；逐折 `fit_valid_overlap=False`、`max_fit_label_target_date≤fit_end`、`max_valid_label_target_date≤valid_end`（与锁定 V1 相同的逐折证据结构）。

## 5. V1 复现校验（锁定 V1 vs 本实验 V1）

对 6 个评估窗口逐一比较锁定 V1（timeline-fix 版本）与本实验 V1 的 `final_equity/cagr/sharpe/max_drawdown/calmar/entries/exits/annualized_turnover/realized_stamp_duty/time_in_market/overall_avg_gross_exposure`：

**V1 复现 = TRUE（全部字段差异 ≤ 1e-4）**。V1 路径直接调用锁定 `run_fold`，与接受结果字节级一致。

## 6. 逐折预测诊断（3Y；V1 vs V2，corr=预测与实现 y20 的 Pearson，spread=LONG−CASH 实现均值差）

| OOS年 | V1 corr | V1 spread | V2 corr | V2 spread |
| --- | ---: | ---: | ---: | ---: |
| 2018 | +0.120 | +6.74pp | +0.077 | −0.55pp |
| 2019 | −0.078 | +3.30pp | −0.044 | +3.30pp |
| 2020 | −0.111 | +4.80pp | +0.043 | +4.80pp |
| 2021 | −0.140 | −2.76pp | +0.003 | −4.91pp |
| 2022 | +0.381 | −1.66pp | +0.401 | −1.66pp |
| 2023 | +0.019 | +0.27pp | −0.041 | +0.38pp |
| 2024 | +0.224 | −2.44pp | +0.305 | −2.44pp |
| 2025 | −0.210 | −0.69pp | +0.242 | −0.69pp |
| 2026 | +0.015 | +2.13pp | +0.212 | +2.34pp |

观察：V2 在 2024-2026 的逐折 corr **连续为正**（+0.31/+0.24/+0.21），V1 则震荡（+0.22/−0.21/+0.01）——V2 近期预测与实现 y20 的相关性方向更稳定，但 LONG-CASH 经济 spread 仍很小（见 §7）。

## 7. 严格年代包含聚合诊断（t 与 t+20 均须落在同一年代）

| 年代 | 路径 | n | corr | 符号命中 | LONG-CASH spread |
| --- | --- | ---: | ---: | ---: | ---: |
| 2018-2020 | V1 3Y | 670 | −0.017 | 0.583 | +4.72pp |
| | V2 3Y | 670 | −0.019 | 0.580 | +4.56pp |
| | V1 5Y | 223 | −0.262 | 0.700 | +4.80pp |
| | V2 5Y | 223 | −0.133 | 0.664 | +4.26pp |
| 2021-2023 | V1 3Y | 707 | −0.032 | 0.413 | −1.70pp |
| | V2 3Y | 707 | −0.045 | 0.401 | −2.07pp |
| | V1 5Y | 707 | −0.093 | 0.413 | −1.91pp |
| | V2 5Y | 707 | −0.175 | 0.412 | −5.38pp |
| 2024-2026 | V1 3Y | 629 | −0.052 | 0.501 | +0.24pp |
| | V2 3Y | 629 | **+0.014** | 0.483 | +1.35pp |
| | V1 5Y | 629 | +0.042 | 0.552 | +0.88pp |
| | V2 5Y | 629 | **+0.290** | 0.566 | +0.70pp |

## 8. 完整 OOS 绩效（主口径 MTM；每窗口 1,000,000 空仓起算）

| 窗口 | 比较器 | final | CAGR | 年化波动 | Sharpe | MaxDD | Calmar | e/x | 年化换手 | 已实现印花税 | 在场时长 | 均毛敞口 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL_3Y 18-26 | ML_V1 | 1,123,537 | 1.36% | 19.1% | 0.166 | 43.6% | 0.031 | 18/17 | 3.87 | 8,249 | 0.67 | 0.542 |
| | ML_V2 | 1,006,558 | 0.08% | 20.3% | 0.100 | 51.8% | 0.002 | 30/29 | 7.34 | 12,905 | 0.69 | 0.527 |
| | BH_100 | 1,879,272 | 7.60% | 26.1% | 0.411 | 55.7% | 0.137 | 1/0 | 0.12 | 0 | 1.00 | 1.000 |
| | BH_STATIC_CONS | 1,722,957 | 6.52% | 22.0% | 0.398 | 50.1% | 0.130 | 1/0 | 0.10 | 0 | 1.00 | 0.833 |
| | MA_FIXED | 1,387,149 | 3.87% | 15.3% | 0.325 | 31.4% | 0.123 | 30/29 | 6.77 | 14,382 | 0.50 | 0.420 |
| | 匹配V1诊断 | 1,468,290 | 4.56% | 15.0% | 0.373 | 38.3% | 0.119 | 1/0 | 0.06 | 0 | 1.00 | 0.581 |
| | 匹配V2诊断 | 1,449,130 | 4.34% | 15.0% | 0.367 | 37.2% | 0.117 | 1/0 | 0.06 | 0 | 1.00 | 0.565 |
| RECENT_3Y 21-26 | ML_V1 | 715,427 | −5.67% | 14.5% | −0.325 | 41.6% | −0.136 | 16/15 | 3.31 | 4,927 | 0.51 | 0.400 |
| | ML_V2 | 674,965 | −6.63% | 15.4% | −0.366 | 50.2% | −0.132 | 22/21 | 5.75 | 7,270 | 0.53 | 0.396 |
| | MA_FIXED | 909,160 | −1.65% | 12.2% | −0.075 | 29.6% | −0.056 | 21/20 | 4.91 | 6,828 | 0.45 | 0.370 |
| R4_3Y 24-26 | ML_V1 | 1,074,270 | 2.68% | 6.5% | 0.440 | 7.5% | 0.358 | 2/1 | 0.91 | 413 | 0.24 | 0.194 |
| | ML_V2 | 1,058,672 | 2.13% | 6.3% | 0.455 | 6.9% | 0.310 | 6/5 | 10.52 | 3,500 | 0.17 | 0.119 |
| | MA_FIXED | 1,182,956 | 6.41% | 12.0% | 0.576 | 19.2% | 0.334 | 12/11 | 7.87 | 5,131 | 0.63 | 0.511 |
| ALL_5Y 20-26 | ML_V1 | 1,518,097 | 6.38% | 20.4% | 0.406 | 48.9% | 0.131 | 19/19 | 5.36 | 8,899 | 0.91 | 0.764 |
| | ML_V2 | 1,323,827 | 4.25% | 18.8% | 0.305 | 48.0% | 0.088 | 18/18 | 5.98 | 8,520 | 0.94 | 0.796 |
| | MA_FIXED | 1,209,101 | 2.85% | 14.4% | 0.268 | 31.2% | 0.091 | 22/21 | 5.82 | 9,612 | 0.49 | 0.411 |
| RECENT_5Y 21-26 | ML_V1 | 1,061,762 | 1.05% | 18.5% | 0.148 | 45.2% | 0.023 | 19/19 | 4.40 | 6,040 | 0.89 | 0.715 |
| | ML_V2 | 918,565 | −1.47% | 17.6% | 0.010 | 44.8% | −0.033 | 18/18 | 4.84 | 6,013 | 0.93 | 0.755 |
| | MA_FIXED | 909,160 | −1.65% | 12.2% | −0.075 | 29.6% | −0.056 | 21/20 | 4.91 | 6,828 | 0.45 | 0.370 |
| R4_5Y 24-26 | ML_V1 | 1,469,542 | 15.30% | 14.6% | 1.050 | 11.6% | 1.316 | 7/7 | 5.80 | 3,875 | 0.87 | 0.732 |
| | ML_V2 | 1,347,979 | 11.68% | 15.4% | 0.820 | 18.9% | 0.616 | 10/9 | 11.96 | 7,180 | 0.89 | 0.764 |
| | MA_FIXED | 1,182,956 | 6.41% | 12.0% | 0.576 | 19.2% | 0.334 | 12/11 | 7.87 | 5,131 | 0.63 | 0.511 |

（"匹配V1/V2诊断" = `BH_STATIC_MATCHED_AVG_EXPOSURE`，分别以 V1/V2 实际均毛敞口初始化，ex-post、非可部署基准。）

## 9. V2−V1 与 V2−MA delta（主口径）

| 窗口 | ΔCAGR(V2−V1) | ΔSharpe | ΔMaxDD | ΔCalmar | Δ换手 | Δ均敞口 | ΔCAGR(V2−MA) | ΔSharpe | ΔMaxDD | ΔCalmar |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL_3Y | −1.28pp | −0.066 | +8.2pp | −0.030 | +3.47 | −0.015 | −3.79pp | −0.225 | +20.4pp | −0.122 |
| RECENT_3Y | −0.96pp | −0.041 | +8.6pp | +0.004 | +2.44 | −0.004 | −4.98pp | −0.291 | +20.6pp | −0.076 |
| R4_3Y | −0.55pp | +0.015 | −0.6pp | −0.048 | +9.61 | −0.075 | −4.28pp | −0.121 | −12.3pp | −0.024 |
| ALL_5Y | −2.13pp | −0.100 | −0.9pp | −0.042 | +0.62 | +0.032 | +1.40pp | +0.037 | +16.7pp | −0.003 |
| RECENT_5Y | −2.52pp | −0.138 | −0.4pp | −0.056 | +0.44 | +0.040 | +0.18pp | +0.086 | +15.2pp | +0.023 |
| R4_5Y | −3.62pp | −0.230 | +7.3pp | −0.700 | +6.16 | +0.032 | +5.27pp | +0.244 | −0.2pp | +0.282 |

## 10. 敞口匹配诊断（ML_V2 vs 匹配V2静态；ΔMaxDD）

| 窗口 | ΔCAGR | ΔSharpe | ΔMaxDD |
| --- | --- | --- | --- |
| ALL_3Y | −4.26pp | −0.267 | **+14.6pp** |
| RECENT_3Y | −6.93pp | −0.449 | **+29.3pp** |
| R4_3Y | −1.97pp | −0.562 | **+5.0pp** |
| ALL_5Y | −2.44pp | −0.128 | −0.7pp |
| RECENT_5Y | −2.46pp | −0.102 | **+2.0pp** |
| R4_5Y | −3.32pp | −0.256 | **+7.9pp** |

## 11. 结论 A/B/C/D（明确回答）

### A. 上下文特征是否相对锁定 V1 增加 OOS 价值？→ **CONTEXT_FEATURES_HURT**

V2 在 6 个窗口中 **5 个 CAGR 更差**（−0.55~−3.62pp）、**5 个 Sharpe 更差**（仅 R4_3Y +0.015）、Calmar 5 个更差；MaxDD 3 个更差（+7~8pp）、3 个基本持平（−0.4~−0.9pp），无任何窗口出现材料性回撤改善。V2 反而**换手显著上升**（ALL_3Y 3.87→7.34、R4_3Y 0.91→10.52、R4_5Y 5.80→11.96，交易成本/印花税翻倍），收益被侵蚀。主/近期视图全面支持"无帮助甚至有害"。→ **CONTEXT_FEATURES_HURT**（无一处材料性正向；不加特征不宣胜）。

### B. V2 在 2024-2026 严格年代包含目标下是否显示正向方向分离？→ **NO（未可靠证实）**

严格年代包含后：V2 3Y corr +0.014（≈0）、LONG-CASH spread +1.35pp；V2 5Y corr +0.290、spread +0.70pp。V2 5Y 的相关性方向为正（且 2024/2025/2026 逐折 corr 连续为正，优于 V1），但 **LONG-CASH 经济 spread 仅 0.7–1.35pp**、3Y 路径相关性≈0，且样本重叠。证据为"弱/混合"，**不构成可靠的正向方向分离**。

### C. V2 是否改进锁定 MA 基线？→ **NO**

主评估窗口 ALL_3Y/RECENT_3Y/R4_3Y：V2 全面落后 MA_FIXED（CAGR −3.8~−5.0pp、Sharpe −0.12~−0.29、MaxDD +12~+21pp 更差）。5Y 各窗口 V2 在 CAGR/Sharpe 反超（ALL_5Y +1.40pp/+0.037、R4_5Y +5.27pp/+0.244）但 MaxDD 显著更差（+15~17pp，R4_5Y ≈−0.2pp）。仅 R4_5Y 四项反超，按任务书不基于单一有利区段宣布。→ **不宣布 V2 改进锁定 MA**。

### D. 敞口匹配后是否仍有回撤改善？→ **NO**

V2 vs 匹配 V2 均敞口静态持有：MaxDD 在 6 窗口中 5 个更高（+2.0~+29.3pp），仅 ALL_5Y ≈持平（−0.7pp）。V2 相对 MA 的 R4 回撤优势由更低敞口解释；敞口匹配后优势消失/反转。→ **无稳健回撤优势**。

## 12. 测试与可复现性

```powershell
python -B -m unittest discover -s tests -t . -v
```
**`Ran 146 tests ... OK`**（基线 12 + QMT 48 + 择时 27 + 历史研究 12 + challenger V1 33 + context V2 14）。context 测试覆盖：V1/V2 特征名精确、V2 特征无未来泄漏、volume_ratio20/range_20/mkt_ret/rel_ret 精确定义、精确日 join 无填充、缺失市场日剔除、FIT/VALID 标签边界、严格年代包含（t 与 t+20 均须在年代内）、执行复用锁定 chronological 模拟器（对象同一性断言）、窗口重置 1M、锁定 MA 参数。

```powershell
python -B scripts\midea_vnpy_alpha_context_challenger.py --fetch --json work\midea_vnpy_alpha_context_summary.json
python -B scripts\midea_vnpy_alpha_context_challenger.py --csv-stock work\midea_000333_daily_back.csv --csv-market work\csi300_000300_daily.csv --json work\midea_vnpy_alpha_context_summary.json
```
`--fetch` 与 `--csv-stock/--csv-market` 输出 **MD5 完全一致**；V1 复现校验 = TRUE。生成的 CSV/JSON/AlphaLab 产物均在 `work/`（gitignored，未提交）。

## 13. 环境健康披露

```powershell
python -m pip check
```
仍报告（诊断性，未变更任何包）：`vnpy-mysql/postgresql/sqlite 要求 peewee>=3.17.9，当前 peewee 3.17.3`。全量测试通过、功能未受影响；依赖修复需另行授权。既有用户授权安装（polars 1.44.1 / lightgbm 4.7.0 / alphalens-reloaded 0.4.6 / pyarrow 25.0.1）保持。

## 14. 限制（如实声明）

1. 前向 y20 样本重叠，诊断不做独立样本显著性宣称。
2. 上下文仅 CSI300 收盘（量能/相对收益）；未含估值/资金流/行业等。
3. 后复权价用于研究；绝对滑点/现金 sizing 为近似。
4. T+1 结构性兼容；未建模涨跌停无法成交。
5. 官方 `LgbModel` 强制 early-stopping，沿用锁定非重叠 fit/valid + 分段标签包含。
6. V2 换手更高、成本更高（印花税翻倍），是 V2 收益落后的重要组成部分。

## 15. 交易副作用声明

**零实盘副作用**：新增委托数 = 0，新增成交数 = 0，撤单数 = 0；未启用/修改 QmtGateway 写路径；未动 `D:\veighna_studio`、MiniQMT 配置；锁定 V1/基线/QmtGateway 零改动；未安装/升级任何包。

## Definition of Done 核对

```text
[x] V1 rerun reproduces locked challenger（6 窗口全字段差异≤1e-4）
[x] V2 uses exactly 17 frozen features (10+7)
[x] CSI300 exact-date context is local-XtQuant sourced（能力门 PASS，excluded_rows=0）
[x] no market-data fill or future leakage（精确日 join + 测试）
[x] official vnpy.alpha workflow remains in use（AlphaDataset/Segment/LgbModel/AlphaLab）
[x] 3Y/5Y walks remain frozen and label-clean（逐折 overlap=False、maxFitTgt/maxValidTgt 上界满足）
[x] accepted chronological simulator is reused（对象同一性断言）
[x] strict era-contained diagnostics are complete（t 与 t+20 均须在年代内）
[x] all requested OOS comparisons are recomputed（6 窗口 × V1/V2 × 比较器 + deltas）
[x] A/B/C/D conclusions are explicit and non-cherry-picked（HURT/NO/NO/NO）
[x] all tests pass（146/146）
[x] no dependency mutation（pip check 仅诊断）
[x] no live trading side effects
```
