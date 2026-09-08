"""Midea A — vnpy.alpha / LightGBM walk-forward challenger (research only).

Leakage-safe ML challenger against the locked Midea timing baseline, built
on the OFFICIAL VeighNa Alpha capability:

    AlphaDataset (official) : frozen 10 polars-expression features + y20 label
                              + learn-processor boundary purge (official
                              extension point AlphaDataset.add_processor)
    LgbModel (official)     : official LightGBM estimator wrapper
    AlphaLab (official)     : dataset/model/signal persistence

LightGBM supplies only the gradient-boosting estimator beneath the official
workflow. Execution/cost/accounting conventions are identical to the locked
baseline (next-bar open, gap_buffer=1.20, 100-share lots, cost-aware cash
ledger, commission/slippage, stamp duty disclosed).

Usage:
    python scripts/midea_vnpy_alpha_lightgbm_challenger.py --csv work/midea_000333_daily_back.csv --json work/midea_vnpy_alpha_lightgbm_summary.json
    python scripts/midea_vnpy_alpha_lightgbm_challenger.py --fetch --json work/midea_vnpy_alpha_lightgbm_summary.json
"""
import argparse
import json
import math
import statistics
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import polars as pl

from src.trader.strategies.midea_timing import (
    build_anchored_series,
    terminal_liquidation,
)
from src.trader.strategies.midea_timing.ml_research import (
    ANNUAL_DAYS,
    CAPITAL,
    COMMISSION_RATE,
    FROZEN_FEATURES,
    GAP_BUFFER,
    LABEL_Y20,
    LOT_SIZE,
    SLIPPAGE,
    STAMP_DUTY,
    fold_schedule,
    make_purge_processor,
    run_static_bh_fraction,
    simulate_ml,
)
from scripts.midea_timing_backtest import (
    SYMBOL,
    VT_SYMBOL,
    fetch_bars_xtdata,
    load_bars_csv,
    metrics_from_equity,
    run_buy_and_hold,
)
from scripts.midea_history_regime_study import (
    run_bh_static_conservative,
    run_ma_fixed,
)

OOS_3Y = list(range(2018, 2027))          # 2018..2026 (2026 partial to 09-04)
OOS_5Y = list(range(2020, 2027))          # 2020..2026
FETCH_START = "20130901"

# Evaluation windows: (start, end, pred_key)
WINDOWS = {
    "ALL_3Y": ("20180101", "20260904", "pred3"),
    "RECENT_3Y": ("20210101", "20260904", "pred3"),
    "R4_3Y": ("20240101", "20260904", "pred3"),
    "ALL_5Y": ("20200101", "20260904", "pred5"),
    "RECENT_5Y": ("20210101", "20260904", "pred5"),
    "R4_5Y": ("20240101", "20260904", "pred5"),
}

ERA_BANDS = {"2018-2020": ("20180101", "20201231"),
             "2021-2023": ("20210101", "20231231"),
             "2024-2026": ("20240101", "20261231")}


def capability_report() -> dict:
    """Official capability gate record (imports/versions/APIs used)."""
    import importlib
    from vnpy.alpha import AlphaDataset, AlphaLab, AlphaModel, AlphaStrategy  # noqa: F401
    from vnpy.alpha import Segment  # noqa: F401
    from vnpy.alpha.model.models.lgb_model import LgbModel

    polars = importlib.import_module("polars")
    lgb = importlib.import_module("lightgbm")
    return {
        "vnpy_alpha_import_path": __import__("vnpy").alpha.__file__,
        "vnpy_alpha_version": __import__("vnpy").__version__,
        "polars_version": polars.__version__,
        "lightgbm_version": lgb.__version__,
        "api_used": [
            "AlphaDataset(add_feature/set_label/add_processor/prepare_data/process_data/fetch_learn/fetch_infer)",
            "Segment(TRAIN/VALID/TEST)",
            "LgbModel(learning_rate=0.03, num_leaves=15, num_boost_round=200, "
            "early_stopping_rounds=50, log_evaluation_period=0, seed=42)",
            "AlphaLab(save_dataset/save_model/save_signal)",
        ],
        "frozen_lgb_mapping_note": (
            "official LgbModel exposes only objective/learning_rate/num_leaves/seed/"
            "num_boost_round/early_stopping_rounds; the frozen config's "
            "min_child_samples/subsample/colsample_bytree/verbosity are NOT exposed by "
            "the official wrapper and use LightGBM defaults (nearest fixed mapping, no tuning)"
        ),
    }


def build_raw_df(bars) -> pl.DataFrame:
    """Official AlphaDataset raw frame: [datetime, vt_symbol, OHLC, volume]."""
    rows = [
        {
            "datetime": b.datetime,
            "vt_symbol": VT_SYMBOL,
            "open": b.open_price,
            "high": b.high_price,
            "low": b.low_price,
            "close": b.close_price,
            "volume": b.volume,
        }
        for b in bars
    ]
    return pl.DataFrame(rows).sort("datetime")


def target_date_map(bars) -> dict:
    """datetime of bar t+20 for each bar (None for the last 20 bars)."""
    out = {}
    for i, b in enumerate(bars):
        out[b.datetime] = bars[i + 20].datetime if i + 20 < len(bars) else None
    return out


def run_fold(bars, raw_df, tgt_map, fold, lab, tag, train_years):
    """Official vnpy.alpha fold: non-overlapping fit/valid split inside the
    declared training window, LgbModel fit (early stopping on the disjoint
    valid set), then OOS predictions."""
    from vnpy.alpha import AlphaDataset, Segment
    from vnpy.alpha.model.models.lgb_model import LgbModel

    fit_period = fold["fit"]
    valid_period = fold["valid"]
    test_period = fold["test"]

    ds = AlphaDataset(
        raw_df,
        fit_period,
        valid_period,
        test_period,
    )
    # Official expression path for the frozen features (polars expressions).
    for name, expr in FROZEN_FEATURES.items():
        ds.add_feature(name, expression=expr)
    # Official result path for the y20 label. The label is added LAST so it
    # becomes the final column (LgbModel expects label last). We deliberately
    # do NOT use set_label() with a pl.Expr: the official prepare_data() does
    # `if self.label_expression:` truthiness, which raises on polars 1.x.
    label_result = raw_df.select(["datetime", "vt_symbol", LABEL_Y20.alias("data")])
    ds.add_feature("label", result=label_result)
    # Segment-aware label containment: FIT labels must end by fit_end, VALID
    # labels by valid_end (strictly before OOS).
    ds.add_processor("learn", make_purge_processor(tgt_map, fit_period[1], valid_period[1]))
    ds.prepare_data(max_workers=1)
    ds.process_data()

    model = LgbModel(
        learning_rate=0.03,
        num_leaves=15,
        num_boost_round=200,
        early_stopping_rounds=50,
        log_evaluation_period=0,
        seed=42,
    )
    model.fit(ds)

    fit_df = ds.fetch_learn(Segment.TRAIN)
    valid_df = ds.fetch_learn(Segment.VALID)
    train_count = len(fit_df)
    valid_count = len(valid_df)

    def max_target_date(frame):
        vals = [tgt_map.get(d) for d in frame["datetime"]]
        vals = [v for v in vals if v is not None]
        return max(vals).strftime("%Y-%m-%d") if vals else None

    infer = ds.fetch_infer(Segment.TEST).sort(["datetime", "vt_symbol"])
    preds = model.predict(ds, Segment.TEST)

    feat_cols = list(FROZEN_FEATURES)
    pairs = []
    for row, pred in zip(infer.iter_rows(), preds):
        d = row[0]
        feats = row[2:-1]
        realized = row[-1]
        if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in feats):
            continue
        pairs.append({
            "date": d.strftime("%Y%m%d"),
            "pred": float(pred),
            "realized": None if realized is None
                       or (isinstance(realized, float) and math.isnan(realized))
                       else float(realized),
        })

    lab.save_dataset(f"{tag}_ds", ds)
    lab.save_model(f"{tag}_model", model)
    lab.save_signal(f"{tag}_signal", infer.with_columns(pl.Series("signal", preds)))

    return {
        "fold": f"{test_period[0]}..{test_period[1]}",
        "train_years": train_years,
        "declared_train_range": "..".join(fold["declared_train"]),
        "fit_range": "..".join(fit_period),
        "valid_range": "..".join(valid_period),
        "test_range": "..".join(test_period),
        "fit_valid_overlap": bool(
            fit_period[1] >= valid_period[0]),   # must be False
        "train_count_after_purge": train_count,
        "valid_count_after_purge": valid_count,
        "max_fit_label_target_date": max_target_date(fit_df),
        "max_valid_label_target_date": max_target_date(valid_df),
        "infer_count": len(infer),
        "oos_pred_count": len(pairs),
        "pairs": pairs,
    }


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return num / (dx * dy) if dx and dy else None


def pred_diagnostics(pairs):
    valid = [p for p in pairs if p["realized"] is not None]
    if not valid:
        return {"count": 0}
    preds = [p["pred"] for p in valid]
    rl = [p["realized"] for p in valid]
    n = len(valid)
    long_idx = [i for i, p in enumerate(preds) if p > 0]
    cash_idx = [i for i, p in enumerate(preds) if p <= 0]
    rl_long = [rl[i] for i in long_idx]
    rl_cash = [rl[i] for i in cash_idx]
    return {
        "count": n,
        "mean_pred": round(statistics.mean(preds), 6),
        "mean_realized": round(statistics.mean(rl), 6),
        "pearson_corr": round(pearson(preds, rl), 4) if pearson(preds, rl) is not None else None,
        "sign_accuracy": round(sum(1 for p, r in zip(preds, rl) if (p > 0) == (r > 0)) / n, 4),
        "long_fraction": round(len(long_idx) / n, 4),
        "mean_realized_long": round(statistics.mean(rl_long), 6) if rl_long else None,
        "mean_realized_cash": round(statistics.mean(rl_cash), 6) if rl_cash else None,
        "spread_long_minus_cash": round(
            (statistics.mean(rl_long) if rl_long else 0.0)
            - (statistics.mean(rl_cash) if rl_cash else 0.0), 6),
    }


def finalize_metrics(bars, rows, trades, window_start, window_end,
                     capital=CAPITAL, extra=None):
    """Common anchored/M TM metrics + activity + liquidation for a simulated path."""
    window = [b for b in bars
              if window_start <= b.datetime.strftime("%Y%m%d") <= window_end]
    first = window[0]
    anchor_ts = first.datetime - timedelta(seconds=1)
    series = build_anchored_series(
        capital, anchor_ts, [v for _, v in rows], [datetime.strptime(d, "%Y%m%d") for d, _ in rows])
    m = metrics_from_equity(series, capital)
    m["final_equity"] = round(float(m["final_equity"]), 2)

    entries = [t for t in trades if t["direction"] == "LONG"]
    sells = [t for t in trades if t["direction"] == "SELL"]
    m["entries"] = len(entries)
    m["exits"] = len(sells)
    turnover = sum(t["volume"] * t["price"] for t in trades)
    m["primary_turnover"] = round(turnover, 2)
    m["annualized_turnover"] = round(turnover / capital / m["years"], 4)
    m["realized_stamp_duty"] = round(
        sum(t["volume"] * t["price"] for t in sells) * STAMP_DUTY, 2)

    closes_by_date = {b.datetime.strftime("%Y%m%d"): b.close_price for b in window}
    pos_by_date = {}
    for t in trades:
        pos_by_date[t["date"]] = t["volume"] if t["direction"] == "LONG" else 0
    pos_series = []
    cur = 0
    for d, _ in rows:
        cur = pos_by_date.get(d, cur)
        pos_series.append(cur)
    exposure = []
    for (d, eq), p in zip(rows, pos_series):
        if eq > 0:
            exposure.append(p * closes_by_date[d] / eq)
    m["time_in_market"] = round(sum(1 for p in pos_series if p > 0) / len(pos_series), 4)
    long_expo = [e for p, e in zip(pos_series, exposure) if p > 0]
    m["avg_deployed_while_long"] = round(
        float(statistics.mean(long_expo)), 4) if long_expo else 0.0
    m["overall_avg_gross_exposure"] = round(
        float(statistics.mean(exposure)), 4) if exposure else 0.0

    final_shares = sum(t["volume"] for t in entries) - sum(t["volume"] for t in sells)
    last_close = window[-1].close_price
    m.update(terminal_liquidation(
        m["final_equity"], final_shares, last_close,
        COMMISSION_RATE, SLIPPAGE, STAMP_DUTY))
    m["liquidated_cagr"] = round(
        (m["liquidated_final_equity"] / capital) ** (1 / m["years"]) - 1, 4)
    m["liquidated_exits"] = len(sells) + (1 if final_shares > 0 else 0)
    liq_turnover = turnover + final_shares * last_close
    m["liquidated_total_turnover"] = round(liq_turnover, 2)
    m["liquidated_annualized_turnover"] = round(
        liq_turnover / capital / m["years"], 4)
    m["final_shares"] = int(final_shares)
    m["actual_start"] = window[0].datetime.strftime("%Y%m%d")
    m["actual_end"] = window[-1].datetime.strftime("%Y%m%d")
    if extra:
        m.update(extra)
    return m


def pred_frame(fold_results, train_years_key):
    """Global prediction frame from per-fold pairs (date -> predicted y20)."""
    by_date = {}
    for fr in fold_results:
        if fr["train_years"] != train_years_key:
            continue
        for p in fr["pairs"]:
            by_date[p["date"]] = p["pred"]
    return by_date


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", help="read bars from a CSV (miniQMT format)")
    parser.add_argument("--fetch", action="store_true", help="fetch from local miniQMT")
    parser.add_argument("--json", help="write summary JSON under work/")
    parser.add_argument("--lab", default=str(ROOT / "work" / "alpha_lab"),
                        help="AlphaLab persistence directory")
    parser.add_argument("--data-worker", action="store_true",
                        help=argparse.SUPPRESS)   # internal: fetch data in a child process
    args = parser.parse_args()

    if args.data_worker:
        # Child process: fetch via xtdata and write the CSV. Kept separate so
        # xtdata's native DLLs never coexist with polars/lightgbm in the main
        # process (observed native access violation otherwise).
        fetch_bars_xtdata(FETCH_START, "20260904")
        print("data worker: CSV written", flush=True)
        return 0

    if args.csv:
        bars = load_bars_csv(Path(args.csv), FETCH_START, "20260904")
    elif args.fetch:
        # Isolate the xtdata fetch (native DLLs) from the ML process.
        subprocess.run(
            [sys.executable, "-B", str(Path(__file__).resolve()), "--data-worker"],
            cwd=ROOT, check=True, timeout=180,
        )
        bars = load_bars_csv(ROOT / "work" / "midea_000333_daily_back.csv",
                             FETCH_START, "20260904")
    else:
        parser.error("provide --csv <file> or --fetch")
    if not bars:
        raise SystemExit("no bars loaded")

    from vnpy.alpha import AlphaLab

    lab = AlphaLab(args.lab)
    raw_df = build_raw_df(bars)
    tgt_map = target_date_map(bars)
    cap = capability_report()

    # ---- walk-forward folds (official vnpy.alpha workflow) ----
    fold_results = []
    for train_years, oos_years in ((3, OOS_3Y), (5, OOS_5Y)):
        for fold in fold_schedule(oos_years, train_years):
            tag = f"y{train_years}_{fold['test'][0][:4]}"
            fr = run_fold(bars, raw_df, tgt_map, fold, lab, tag, train_years)
            fold_results.append(fr)

    pred3 = pred_frame(fold_results, 3)
    pred5 = pred_frame(fold_results, 5)

    # ---- prediction diagnostics per fold + era aggregates ----
    fold_diag = []
    for fr in fold_results:
        d = {"fold": fr["fold"], "train_years": fr["train_years"],
             "declared_train_range": fr["declared_train_range"],
             "fit_range": fr["fit_range"], "valid_range": fr["valid_range"],
             "test_range": fr["test_range"],
             "fit_valid_overlap": fr["fit_valid_overlap"],
             "train_count_after_purge": fr["train_count_after_purge"],
             "valid_count_after_purge": fr["valid_count_after_purge"],
             "max_fit_label_target_date": fr["max_fit_label_target_date"],
             "max_valid_label_target_date": fr["max_valid_label_target_date"],
             "infer_count": fr["infer_count"], "oos_pred_count": fr["oos_pred_count"]}
        d.update(pred_diagnostics(fr["pairs"]))
        fold_diag.append(d)

    era_diag = {}
    for era, (s, e) in ERA_BANDS.items():
        era_diag[era] = {}
        for ky in ("pred3", "pred5"):
            frs = [fr for fr in fold_results if fr["train_years"] == (3 if ky == "pred3" else 5)]
            pairs = [p for fr in frs for p in fr["pairs"] if s <= p["date"] <= e]
            era_diag[era][ky] = pred_diagnostics(pairs)

    # ---- evaluation windows: ML + comparators ----
    windows_out = {}
    for wname, (ws, we, pred_key) in WINDOWS.items():
        pf = pred3 if pred_key == "pred3" else pred5
        ml = simulate_ml(bars, pf, ws, we)
        ml_metrics = finalize_metrics(bars, ml["rows"], ml["trades"], ws, we)

        wbars = [b for b in bars if ws <= b.datetime.strftime("%Y%m%d") <= we]
        bh = run_buy_and_hold(wbars, ws)
        bh["time_in_market"] = 1.0
        sc = run_bh_static_conservative(wbars, ws)
        ma = run_ma_fixed(bars, ws, we)

        # ex-post exposure-matched diagnostic (not a deployable benchmark)
        matched_fraction = ml_metrics["overall_avg_gross_exposure"]
        matched = run_static_bh_fraction(bars, ws, we, matched_fraction)
        matched_metrics = finalize_metrics(bars, matched["rows"], matched["trades"], ws, we)
        matched_metrics["matched_fraction"] = matched_fraction
        matched_metrics["label"] = "BH_STATIC_MATCHED_AVG_EXPOSURE (ex-post diagnostic)"

        windows_out[wname] = {
            "window": f"{ws}..{we}",
            "ML_ROLLING": ml_metrics,
            "BH_100": bh,
            "BH_STATIC_CONSERVATIVE": sc,
            "MA_FIXED": ma,
            "BH_STATIC_MATCHED_AVG_EXPOSURE": matched_metrics,
            "deltas_ML_vs_MA": {
                k: round(ml_metrics[k] - ma[k], 4)
                for k in ("cagr", "sharpe", "max_drawdown", "calmar")
            },
            "deltas_ML_vs_BH100": {
                k: round(ml_metrics[k] - bh[k], 4)
                for k in ("cagr", "sharpe", "max_drawdown", "calmar")
            },
            "deltas_ML_vs_MATCHED": {
                k: round(ml_metrics[k] - matched_metrics[k], 4)
                for k in ("cagr", "sharpe", "max_drawdown", "calmar")
            },
        }

    summary = {
        "symbol": SYMBOL,
        "nature": "research/backtest only",
        "capability": cap,
        "install_authorization": (
            "User-authorized unblock installs into .venv (2026-09-08): polars, lightgbm, "
            "alphalens-reloaded, pyarrow. Recorded in "
            "IMPLEMENTATION_REPORT_MIDEA_A_VNPY_ALPHA_LIGHTGBM_CHALLENGER_20260908.md"
        ),
        "data_source": "miniQMT (xtdata, 后复权/back-adjust, 含现金分红与送转)",
        "features": list(FROZEN_FEATURES),
        "target": "y20 = close[t+20]/close[t]-1",
        "walk_forward": {
            "3Y_train": "Y-3-01-01 .. Y-1-12-31, OOS = Y",
            "5Y_train": "Y-5-01-01 .. Y-1-12-31, OOS = Y (2020+)",
            "purge": "train rows whose y20 target date (t+20) crosses the OOS boundary are excluded",
        },
        "fold_diagnostics": fold_diag,
        "era_diagnostics": era_diag,
        "windows": windows_out,
        "trade_side_effects": {"orders_submitted": 0, "orders_cancelled": 0, "fills": 0},
    }
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.json:
        out = Path(args.json).resolve()
        if not out.is_relative_to(ROOT / "work"):
            raise SystemExit("--json output must be inside work/")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"summary written: {out}", flush=True)


if __name__ == "__main__":
    main()
