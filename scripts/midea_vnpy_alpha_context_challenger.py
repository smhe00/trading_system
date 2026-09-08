"""Midea A — vnpy.alpha Context-Feature Challenger V2 (research only).

Feature-set ablation against the locked V1 challenger, using the official
vnpy.alpha workflow (AlphaDataset / Segment / LgbModel / AlphaLab):

    V1 (control)  = locked 10 price/volatility features (reproduced via the
                    locked challenger run_fold)
    V2            = V1 + exactly 7 predeclared context features
                    (volume_ratio20, range_20, mkt_ret20, mkt_ret60,
                     mkt_vol20, rel_ret20, rel_ret60)

Market context = CSI300 (000300.SH) daily close from local XtQuant, joined to
stock tradable dates by exact date (no forward/back fill; missing rows
excluded and reported). Folds, label containment, chronological execution and
all accounting conventions are identical to the locked V1 challenger (helpers
are imported, not forked).

Usage:
    python scripts/midea_vnpy_alpha_context_challenger.py --fetch --json work/midea_vnpy_alpha_context_summary.json
    python scripts/midea_vnpy_alpha_context_challenger.py --csv-stock work/midea_000333_daily_back.csv --csv-market work/csi300_000300_daily.csv --json work/midea_vnpy_alpha_context_summary.json
"""
import argparse
import csv as _csv
import json
import math
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import polars as pl

from src.trader.strategies.midea_timing.ml_research import (
    CAPITAL,
    FROZEN_FEATURES,
    LABEL_Y20,
    fold_schedule,
    make_purge_processor,
    simulate_ml,
)
from src.trader.strategies.midea_timing.ml_context_research import (
    V2_EXTRA_FEATURES,
    era_contained,
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
from scripts.midea_vnpy_alpha_lightgbm_challenger import (
    build_raw_df,           # locked V1 raw df (7 columns)
    capability_report,
    finalize_metrics,
    pred_diagnostics,
    pred_frame,
    run_fold,               # locked V1 fold runner (hardcodes FROZEN_FEATURES)
    target_date_map,
)

STOCK_START = "20130901"
MKT_SYMBOL = "000300.SH"
OOS_3Y = list(range(2018, 2027))
OOS_5Y = list(range(2020, 2027))
WINDOWS = {
    "ALL_3Y": ("20180101", "20260904", 3),
    "RECENT_3Y": ("20210101", "20260904", 3),
    "R4_3Y": ("20240101", "20260904", 3),
    "ALL_5Y": ("20200101", "20260904", 5),
    "RECENT_5Y": ("20210101", "20260904", 5),
    "R4_5Y": ("20240101", "20260904", 5),
}
ERA_BANDS = {"2018-2020": ("20180101", "20201231"),
             "2021-2023": ("20210101", "20231231"),
             "2024-2026": ("20240101", "20261231")}


def fetch_csi300_csv():
    """Child-process data fetch: CSI300 close -> work/csi300_000300_daily.csv."""
    from xtquant import xtdata

    xtdata.download_history_data(MKT_SYMBOL, period="1d",
                                 start_time=STOCK_START, end_time="20260904")
    data = xtdata.get_market_data_ex(
        ["close"], [MKT_SYMBOL], period="1d",
        start_time=STOCK_START, end_time="20260904", dividend_type="none")
    frame = data[MKT_SYMBOL]
    buf = StringIO()
    w = _csv.writer(buf)
    w.writerow(["date", "close"])
    for idx in frame.index:
        d = str(idx)
        w.writerow([f"{d[:4]}-{d[4:6]}-{d[6:8]}", frame["close"][idx]])
    out = ROOT / "work" / "csi300_000300_daily.csv"
    out.parent.mkdir(exist_ok=True)
    out.write_text(buf.getvalue(), encoding="utf-8")
    print(f"csi300 CSV written: {out}", flush=True)


def load_market_csv(path) -> dict:
    """CSI300 close by YYYYMMDD."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for row in _csv.DictReader(f):
            out[row["date"].replace("-", "")] = float(row["close"])
    return out


def build_v2_raw_df(bars, mkt_by_date):
    """V2 raw df = locked 7 columns + mkt_close, exact-date joined.

    Stock tradable dates are the master; market rows missing on an exact date
    exclude that stock row (reported via returned stats). No fill.
    """
    rows = []
    excluded = []
    for b in bars:
        d = b.datetime.strftime("%Y%m%d")
        mkt = mkt_by_date.get(d)
        if mkt is None:
            excluded.append(d)
            continue
        rows.append({
            "datetime": b.datetime,
            "vt_symbol": VT_SYMBOL,
            "open": b.open_price, "high": b.high_price, "low": b.low_price,
            "close": b.close_price, "volume": b.volume,
            "mkt_close": mkt,
        })
    df = pl.DataFrame(rows).sort("datetime")
    stats = {
        "excluded_rows": len(excluded),
        "excluded_range": (excluded[0], excluded[-1]) if excluded else None,
    }
    return df, stats


def run_fold_v2(bars, raw_df, tgt_map, fold, lab, tag, train_years, features):
    """Official vnpy.alpha fold for an arbitrary frozen feature set.

    Mirrors the locked run_fold exactly (same AlphaDataset / purge / LgbModel
    / persistence) but parameterized by ``features`` and adds the t+20 target
    date to each OOS pair for strict era-contained diagnostics.
    """
    from vnpy.alpha import AlphaDataset, Segment
    from vnpy.alpha.model.models.lgb_model import LgbModel

    fit_period = fold["fit"]
    valid_period = fold["valid"]
    test_period = fold["test"]

    ds = AlphaDataset(raw_df, fit_period, valid_period, test_period)
    for name, expr in features.items():
        ds.add_feature(name, expression=expr)
    label_result = raw_df.select(["datetime", "vt_symbol", LABEL_Y20.alias("data")])
    ds.add_feature("label", result=label_result)
    ds.add_processor("learn", make_purge_processor(tgt_map, fit_period[1], valid_period[1]))
    ds.prepare_data(max_workers=1)
    ds.process_data()

    model = LgbModel(learning_rate=0.03, num_leaves=15, num_boost_round=200,
                     early_stopping_rounds=50, log_evaluation_period=0, seed=42)
    model.fit(ds)

    fit_df = ds.fetch_learn(Segment.TRAIN)
    valid_df = ds.fetch_learn(Segment.VALID)
    infer = ds.fetch_infer(Segment.TEST).sort(["datetime", "vt_symbol"])
    preds = model.predict(ds, Segment.TEST)

    feat_cols = list(features)
    pairs = []
    for row, pred in zip(infer.iter_rows(), preds):
        d = row[0]
        feats = row[2:-1]
        realized = row[-1]
        if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in feats):
            continue
        tgt = tgt_map.get(d)
        pairs.append({
            "date": d.strftime("%Y%m%d"),
            "tgt_date": tgt.strftime("%Y%m%d") if tgt else None,
            "pred": float(pred),
            "realized": None if realized is None
                       or (isinstance(realized, float) and math.isnan(realized))
                       else float(realized),
        })

    lab.save_dataset(f"{tag}_ds", ds)
    lab.save_model(f"{tag}_model", model)
    lab.save_signal(f"{tag}_signal", infer.with_columns(pl.Series("signal", preds)))

    def max_target_date(frame):
        vals = [tgt_map.get(dd) for dd in frame["datetime"]]
        vals = [v for v in vals if v is not None]
        return max(vals).strftime("%Y-%m-%d") if vals else None

    return {
        "fold": f"{test_period[0]}..{test_period[1]}",
        "train_years": train_years,
        "declared_train_range": "..".join(fold["declared_train"]),
        "fit_range": "..".join(fit_period),
        "valid_range": "..".join(valid_period),
        "test_range": "..".join(test_period),
        "fit_valid_overlap": bool(fit_period[1] >= valid_period[0]),
        "train_count_after_purge": len(fit_df),
        "valid_count_after_purge": len(valid_df),
        "max_fit_label_target_date": max_target_date(fit_df),
        "max_valid_label_target_date": max_target_date(valid_df),
        "infer_count": len(infer),
        "oos_pred_count": len(pairs),
        "pairs": pairs,
    }


def build_pairs_by_date(fold_results, train_years, with_tgt=False):
    """date -> pair dict for a given train window."""
    by_date = {}
    for fr in fold_results:
        if fr["train_years"] != train_years:
            continue
        for p in fr["pairs"]:
            by_date[p["date"]] = p
    return by_date


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", help="fetch stock+CSI300 via child worker")
    parser.add_argument("--csv-stock", help="stock daily CSV (back-adjusted)")
    parser.add_argument("--csv-market", help="CSI300 daily close CSV")
    parser.add_argument("--json", help="write summary JSON under work/")
    parser.add_argument("--lab", default=str(ROOT / "work" / "alpha_lab_context"),
                        help="AlphaLab persistence dir")
    parser.add_argument("--data-worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.data_worker:
        fetch_bars_xtdata(STOCK_START, "20260904")   # stock CSV
        fetch_csi300_csv()                           # market CSV
        return 0

    if args.fetch:
        subprocess.run(
            [sys.executable, "-B", str(Path(__file__).resolve()), "--data-worker"],
            cwd=ROOT, check=True, timeout=180,
        )
        stock_csv = ROOT / "work" / "midea_000333_daily_back.csv"
        market_csv = ROOT / "work" / "csi300_000300_daily.csv"
    elif args.csv_stock and args.csv_market:
        stock_csv = Path(args.csv_stock)
        market_csv = Path(args.csv_market)
    else:
        parser.error("provide --fetch, or --csv-stock + --csv-market")

    bars = load_bars_csv(stock_csv, STOCK_START, "20260904")
    mkt_by_date = load_market_csv(market_csv)
    if not bars or not mkt_by_date:
        raise SystemExit("no stock or market data loaded")

    from vnpy.alpha import AlphaLab

    lab = AlphaLab(args.lab)
    v1_raw = build_raw_df(bars)
    v2_raw, mkt_stats = build_v2_raw_df(bars, mkt_by_date)
    tgt_map = target_date_map(bars)
    cap = capability_report()

    # ---- folds: V1 via locked run_fold, V2 via parameterized run_fold_v2 ----
    fold_results = {"V1": [], "V2": []}
    for train_years, oos_years in ((3, OOS_3Y), (5, OOS_5Y)):
        for fold in fold_schedule(oos_years, train_years):
            yr = fold["test"][0][:4]
            fr1 = run_fold(bars, v1_raw, tgt_map, fold, lab, f"v1_y{train_years}_{yr}", train_years)
            fr2 = run_fold_v2(bars, v2_raw, tgt_map, fold, lab, f"v2_y{train_years}_{yr}",
                              train_years, {**FROZEN_FEATURES, **V2_EXTRA_FEATURES})
            fold_results["V1"].append(fr1)
            fold_results["V2"].append(fr2)

    pairs_by_date = {
        "V1": {ty: build_pairs_by_date(fold_results["V1"], ty) for ty in (3, 5)},
        "V2": {ty: build_pairs_by_date(fold_results["V2"], ty) for ty in (3, 5)},
    }
    pred_by_date = {
        "V1": {ty: {d: p["pred"] for d, p in pairs_by_date["V1"][ty].items()} for ty in (3, 5)},
        "V2": {ty: {d: p["pred"] for d, p in pairs_by_date["V2"][ty].items()} for ty in (3, 5)},
    }

    # ---- per-fold + strict era-contained diagnostics ----
    fold_diag = {"V1": [], "V2": []}
    for variant in ("V1", "V2"):
        for fr in fold_results[variant]:
            d = {"fold": fr["fold"], "train_years": fr["train_years"],
                 "fit_range": fr["fit_range"], "valid_range": fr["valid_range"],
                 "fit_valid_overlap": fr["fit_valid_overlap"],
                 "train_count_after_purge": fr["train_count_after_purge"],
                 "valid_count_after_purge": fr["valid_count_after_purge"],
                 "max_fit_label_target_date": fr["max_fit_label_target_date"],
                 "max_valid_label_target_date": fr["max_valid_label_target_date"],
                 "infer_count": fr["infer_count"], "oos_pred_count": fr["oos_pred_count"]}
            d.update(pred_diagnostics(fr["pairs"]))
            fold_diag[variant].append(d)

    era_diag = {"V1": {}, "V2": {}}
    for variant in ("V1", "V2"):
        for era, (s, e) in ERA_BANDS.items():
            era_diag[variant][era] = {}
            for ty, label in ((3, "3Y"), (5, "5Y")):
                all_pairs = [p for fr in fold_results[variant]
                             if fr["train_years"] == ty for p in fr["pairs"]]
                contained = era_contained(all_pairs, tgt_map, s, e)
                era_diag[variant][era][f"{label}_strict_contained"] = pred_diagnostics(contained)

    # ---- OOS windows: V1/V2 + comparators ----
    from src.trader.strategies.midea_timing.ml_research import run_static_bh_fraction

    windows_out = {}
    for wname, (ws, we, ty) in WINDOWS.items():
        row = {"window": f"{ws}..{we}"}
        for variant in ("V1", "V2"):
            sim = simulate_ml(bars, pred_by_date[variant][ty], ws, we)
            row[f"ML_{variant}"] = finalize_metrics(
                bars, sim["rows"], sim["trades"], ws, we)
        # comparators (variant-independent)
        wbars = [b for b in bars if ws <= b.datetime.strftime("%Y%m%d") <= we]
        row["BH_100"] = run_buy_and_hold(wbars, ws)
        row["BH_100"]["time_in_market"] = 1.0
        row["BH_STATIC_CONSERVATIVE"] = run_bh_static_conservative(wbars, ws)
        row["MA_FIXED"] = run_ma_fixed(bars, ws, we)
        # exposure-matched diagnostics (per variant)
        for variant in ("V1", "V2"):
            frac = row[f"ML_{variant}"]["overall_avg_gross_exposure"]
            matched = run_static_bh_fraction(bars, ws, we, frac)
            row[f"BH_STATIC_MATCHED_{variant}"] = finalize_metrics(
                bars, matched["rows"], matched["trades"], ws, we)
            row[f"BH_STATIC_MATCHED_{variant}"]["matched_fraction"] = frac
        row["deltas_V2_minus_V1"] = {
            k: round(row["ML_V2"][k] - row["ML_V1"][k], 4)
            for k in ("cagr", "sharpe", "max_drawdown", "calmar",
                      "annualized_turnover", "overall_avg_gross_exposure")
        }
        row["deltas_V2_minus_MA"] = {
            k: round(row["ML_V2"][k] - row["MA_FIXED"][k], 4)
            for k in ("cagr", "sharpe", "max_drawdown", "calmar")
        }
        row["deltas_V2_minus_V2_matched"] = {
            k: round(row["ML_V2"][k] - row[f"BH_STATIC_MATCHED_V2"][k], 4)
            for k in ("cagr", "sharpe", "max_drawdown", "calmar")
        }
        windows_out[wname] = row

    summary = {
        "symbol": SYMBOL,
        "market": MKT_SYMBOL,
        "nature": "research/backtest only",
        "capability": cap,
        "data": {
            "stock_range": f"{bars[0].datetime:%Y-%m-%d}..{bars[-1].datetime:%Y-%m-%d}",
            "stock_bars": len(bars),
            "market_rows": len(mkt_by_date),
            "market_join": mkt_stats,
        },
        "features": {
            "V1": list(FROZEN_FEATURES),
            "V2": list({**FROZEN_FEATURES, **V2_EXTRA_FEATURES}),
            "V2_extras": list(V2_EXTRA_FEATURES),
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
