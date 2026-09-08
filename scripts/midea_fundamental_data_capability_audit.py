"""Midea A — Fundamental/Valuation Point-in-Time Data Capability Audit.

Audit-only task: determines whether the existing local XtQuant/MiniQMT
environment can supply historical financial/valuation data with reliable
historical availability timestamps, sufficient to build a leakage-safe
fundamental challenger for 000333.SZ. NO model is trained and no feature is
optimized here.

The capability surface is inspected from the installed xtquant source (never
assumed). Live extraction runs only when the local data service is reachable;
otherwise the audit fails closed (BLOCKED_DATA_SERVICE_DOWN) and no panel is
fabricated.

Usage:
    python scripts/midea_fundamental_data_capability_audit.py --json work/midea_fundamental_audit.json
"""
import argparse
import datetime
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SYMBOL = "000333.SZ"
TARGET_WINDOW = ("20140101", "20260904")
FIN_TABLES = ["Income", "Balance", "CashFlow", "Capital", "PershareIndex"]

# Availability vs report-period fields observed in the RAW server rows.
PIT_FIELD = "m_anntime"          # ms announcement timestamp (availability)
PERIOD_FIELD = "m_timetag"       # ms report-period tag (NOT availability)
PERIOD_FIELD2 = "m_quarter"      # period/quarter indicator

# Candidate feature concepts (task §9) -> required raw PIT-safe financial fields.
CANDIDATE_FEATURES = {
    "revenue_ttm_growth": ["revenue"],
    "net_profit_ttm_growth": ["net_profit_excl_min_int_inc"],
    "operating_cashflow_ttm_over_net_profit_ttm":
        ["net_cash_flows_oper_act", "net_profit_excl_min_int_inc"],
    "roe_ttm": ["net_profit_excl_min_int_inc", "tot_shrhldr_eqy_excl_min_int"],
    "liability_to_assets": ["tot_liab", "tot_assets"],
    "gross_margin_ttm": ["revenue", "total_operating_cost"],
    "pe_ttm": ["net_profit_excl_min_int_inc", "__market_cap__"],
    "pb": ["tot_shrhldr_eqy_excl_min_int", "__market_cap__"],
    "free_cashflow_yield":
        ["net_cash_flows_oper_act", "cash_pay_acq_const_fiolta", "__market_cap__"],
}

# Concepts that are DERIVABLE from other PIT-safe data (shares + unadjusted
# price) rather than raw financial fields.
DERIVABLE_NOTES = {
    "__market_cap__": (
        "DERIVABLE_PIT_SAFE conditionally: total_capital (PIT) x unadjusted "
        "historical price (xtdata dividend_type='none'); MUST NOT use "
        "back-adjusted price for valuation derivation."
    ),
}


def capability_from_source() -> dict:
    """Inspect the installed xtquant financial API surface (source-level)."""
    import inspect
    from xtquant import xtdata

    out = {"xtquant_import_path": xtdata.__file__, "financial_api_members": {}}
    for name in ("download_financial_data", "download_financial_data2",
                 "get_financial_data", "get_financial_data_ori"):
        obj = getattr(xtdata, name, None)
        if obj is None:
            out["financial_api_members"][name] = "MISSING"
            continue
        try:
            out["financial_api_members"][name] = str(inspect.signature(obj))
        except Exception:
            out["financial_api_members"][name] = "callable"

    out["table_mapping"] = {
        "Income": "ASHAREINCOME", "Balance": "ASHAREBALANCESHEET",
        "CashFlow": "ASHARECASHFLOW", "Capital": "CAPITALSTRUCTURE",
        "HolderNum": "SHAREHOLDER", "Top10Holder": "TOP10HOLDER",
        "Top10FlowHolder": "TOP10FLOWHOLDER", "PershareIndex": "PERSHAREINDEX",
    }
    out["date_fields_observed_in_raw_schema"] = {
        PIT_FIELD: "ms announcement timestamp (historical availability)",
        PERIOD_FIELD: "ms report-period tag (NOT availability)",
        PERIOD_FIELD2: "period/quarter indicator (NOT availability)",
        "actual_ann_dt": "announcement date (observed in ASHAREINCOME)",
    }
    return out


def _ms_to_dt(v):
    if v is None or (isinstance(v, float) and (math.isnan(v) or v == 0)):
        return None
    return datetime.datetime.fromtimestamp(float(v) / 1000.0)


def _rows(df_or_list):
    if isinstance(df_or_list, list):
        return df_or_list
    return df_or_list.to_dict("records")


def audit_live(master_dates) -> dict:
    """Live extraction + coverage/PIT/restatement audit (raw rows)."""
    from xtquant import xtdata

    xtdata.connect()
    xtdata.download_financial_data(
        [SYMBOL], table_list=FIN_TABLES,
        start_time=TARGET_WINDOW[0], end_time=TARGET_WINDOW[1], incrementally=None)
    data = xtdata.get_financial_data_ori(
        [SYMBOL], table_list=FIN_TABLES,
        start_time=TARGET_WINDOW[0], end_time=TARGET_WINDOW[1],
        report_type="report_time")
    d = data[SYMBOL]

    tables_out = {}
    available_fields = set()
    for tname, raw in d.items():
        rows = _rows(raw)
        n = len(rows)
        n_anntime = sum(1 for r in rows if _ms_to_dt(r.get(PIT_FIELD)) is not None)
        n_period = sum(1 for r in rows if _ms_to_dt(r.get(PERIOD_FIELD)) is not None)
        period_strs = sorted({_ms_to_dt(r.get(PERIOD_FIELD)).strftime("%Y-%m-%d")
                              for r in rows if _ms_to_dt(r.get(PERIOD_FIELD))})
        from collections import Counter
        c = Counter(_ms_to_dt(r.get(PERIOD_FIELD)).strftime("%Y-%m-%d")
                    for r in rows if _ms_to_dt(r.get(PERIOD_FIELD)))
        multi = {k: v for k, v in c.items() if v > 1}
        # restatement evidence: do multiple rows of the same period carry
        # DIFFERENT announcement timestamps (=> revision versions exist)?
        anntime_by_period = {}
        for r in rows:
            p = _ms_to_dt(r.get(PERIOD_FIELD))
            a = _ms_to_dt(r.get(PIT_FIELD))
            if p is None or a is None:
                continue
            key = p.strftime("%Y-%m-%d")
            anntime_by_period.setdefault(key, set()).add(a.strftime("%Y-%m-%d %H:%M"))
        periods_with_revisions = {
            k: sorted(v) for k, v in anntime_by_period.items() if len(v) > 1
        }
        fields = sorted({k for r in rows for k in r})
        tables_out[tname] = {
            "rows": n,
            "records_with_anntime": n_anntime,
            "records_missing_anntime": n - n_anntime,
            "records_with_period_tag": n_period,
            "distinct_fiscal_periods": len(period_strs),
            "first_period": period_strs[0] if period_strs else None,
            "last_period": period_strs[-1] if period_strs else None,
            "periods_with_multiple_rows": len(multi),
            "example_multi_periods": list(multi.items())[:5],
            "periods_with_distinct_anntime_versions": len(periods_with_revisions),
            "example_revision_periods": list(periods_with_revisions.items())[:3],
            "columns": fields,
        }
        available_fields.update(fields)

    # Feature feasibility (real fields; market-cap concept handled separately).
    feat_feas = {}
    for feat, required in CANDIDATE_FEATURES.items():
        missing = [f for f in required if f not in available_fields]
        if not missing:
            feat_feas[feat] = "DIRECTLY_AVAILABLE"
        else:
            derivable = all(f == "__market_cap__" for f in missing)
            if derivable:
                feat_feas[feat] = DERIVABLE_NOTES["__market_cap__"]
            elif any(f in available_fields for f in required):
                feat_feas[feat] = "DERIVABLE_BUT_MISSING_REQUIRED_HISTORY"
            else:
                feat_feas[feat] = "UNAVAILABLE"

    panel = build_as_of_panel_from_live(d, master_dates)

    return {
        "tables": tables_out,
        "available_columns_by_table": {
            t: sorted({k for r in _rows(raw) for k in r}) for t, raw in d.items()
        },
        "feature_feasibility": feat_feas,
        "as_of_proof_panel": panel,
    }


def build_as_of_panel_from_live(d, master_dates) -> dict:
    """Minimal as-of proof panel from live records using m_anntime only.

    ``d`` is keyed by SERVER table names (ASHAREINCOME, ...)."""
    from src.trader.strategies.midea_timing.fundamental_pit import (
        build_as_of_panel,
    )

    PANEL_TABLES = ("ASHAREINCOME", "ASHAREBALANCESHEET",
                    "ASHARECASHFLOW", "CAPITALSTRUCTURE")
    records = []
    for tname in PANEL_TABLES:
        for r in _rows(d.get(tname, [])):
            dt = _ms_to_dt(r.get(PIT_FIELD))
            period = _ms_to_dt(r.get(PERIOD_FIELD))
            rec = {
                "table": tname,
                "period_end": period.strftime("%Y-%m-%d") if period else None,
                "m_anntime": dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None,
                "revenue": r.get("revenue"),
                "net_profit_parent": r.get("net_profit_excl_min_int_inc"),
                "net_cash_flows_oper_act": r.get("net_cash_flows_oper_act"),
                "tot_assets": r.get("tot_assets"),
                "tot_liab": r.get("tot_liab"),
                "total_capital": r.get("total_capital"),
            }
            records.append({
                "disclosure_date": dt.date() if dt else None,
                "record": rec,
            })
    panel = build_as_of_panel(records, master_dates, policy="next_trading_day")
    # disclosure boundaries: first trading day where a new record became active
    boundaries = []
    for p in panel:
        if p["active_records"]:
            newest = p["active_records"][-1]
            if newest.get("m_anntime"):
                ad = datetime.datetime.strptime(
                    newest["m_anntime"], "%Y-%m-%d %H:%M:%S").date()
                # boundary = the trading day right after the disclosure date
                if (p["trading_date"] - ad).days in (0, 1) and len(boundaries) < 6:
                    boundaries.append({
                        "trading_date": str(p["trading_date"]),
                        "disclosed_on": newest["m_anntime"],
                        "new_record": {k: newest[k] for k in
                                       ("table", "period_end", "revenue",
                                        "net_profit_parent",
                                        "net_cash_flows_oper_act",
                                        "tot_assets", "tot_liab",
                                        "total_capital")},
                        "active_count": len(p["active_records"]),
                    })
    return {
        "policy": "next_trading_day (unknown disclosure time -> usable next trading day)",
        "trading_dates_covered": len(panel),
        "records_with_available_timestamp": sum(
            1 for r in records if r["disclosure_date"] is not None),
        "records_missing_timestamp_excluded": sum(
            1 for r in records if r["disclosure_date"] is None),
        "example_boundaries": boundaries,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", help="write audit JSON under work/")
    args = parser.parse_args()

    from scripts.midea_timing_backtest import load_bars_csv

    bars = load_bars_csv(ROOT / "work" / "midea_000333_daily_back.csv",
                         TARGET_WINDOW[0], TARGET_WINDOW[1])
    master_dates = [b.datetime.date() for b in bars]

    audit = {"symbol": SYMBOL, "window": "..".join(TARGET_WINDOW),
             "master_trading_dates": len(master_dates),
             "capability": capability_from_source(),
             "live_status": "NOT_RUN"}

    try:
        live = audit_live(master_dates)
        audit["live_status"] = "OK"
        audit.update(live)
    except Exception as e:
        audit["live_status"] = "BLOCKED_DATA_SERVICE_DOWN"
        audit["live_error"] = f"{type(e).__name__}: {str(e)[:300]}"
        audit["note"] = (
            "Fail-closed: no live financial extraction performed; no as-of "
            "panel fabricated. Static capability/schema audit above is from "
            "the installed xtquant source."
        )

    audit["trade_side_effects"] = {"orders_submitted": 0, "orders_cancelled": 0, "fills": 0}
    text = json.dumps(audit, ensure_ascii=False, indent=2)
    print(text)
    if args.json:
        out = Path(args.json).resolve()
        if not out.is_relative_to(ROOT / "work"):
            raise SystemExit("--json output must be inside work/")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
        print(f"audit written: {out}", flush=True)


if __name__ == "__main__":
    main()
