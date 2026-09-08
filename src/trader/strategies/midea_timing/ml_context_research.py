"""Pure research helpers for the Midea vnpy.alpha context-feature challenger V2.

V2 = the locked V1 10 features plus exactly 7 predeclared market-context and
volume/range features. All features at date ``t`` use only information
available through ``t`` close. Also provides the strict era-contained
diagnostic filter used for aggregate prediction diagnostics.
"""
from __future__ import annotations

import math
from datetime import datetime

import polars as pl

from .ml_research import ANNUAL_DAYS, FROZEN_FEATURES

# Exactly these 7 predeclared context/volume/range features (V2 additions).
V2_EXTRA_FEATURES = {
    "volume_ratio20": (
        pl.col("volume")
        / pl.col("volume").rolling_mean(window_size=20, min_periods=20) - 1
    ),
    "range_20": (
        ((pl.col("high") - pl.col("low")) / pl.col("close"))
        .rolling_mean(window_size=20, min_periods=20)
    ),
    "mkt_ret20": pl.col("mkt_close") / pl.col("mkt_close").shift(20) - 1,
    "mkt_ret60": pl.col("mkt_close") / pl.col("mkt_close").shift(60) - 1,
    "mkt_vol20": (
        pl.col("mkt_close").pct_change().rolling_std(
            window_size=20, min_periods=20) * math.sqrt(ANNUAL_DAYS)
    ),
    "rel_ret20": (
        (pl.col("close") / pl.col("close").shift(20) - 1)
        - (pl.col("mkt_close") / pl.col("mkt_close").shift(20) - 1)
    ),
    "rel_ret60": (
        (pl.col("close") / pl.col("close").shift(60) - 1)
        - (pl.col("mkt_close") / pl.col("mkt_close").shift(60) - 1)
    ),
}

# V2 = locked V1 features + the 7 additions (exactly 17 features).
V2_FEATURES = {**FROZEN_FEATURES, **V2_EXTRA_FEATURES}


def era_contained(pairs, target_date_map, start: str, end: str) -> list:
    """Strict era containment for aggregate diagnostics.

    A sample belongs to era ``[start, end]`` only when BOTH its prediction
    date ``t`` and its y20 realized target date ``t+20`` are inside the same
    era. ``target_date_map`` maps each bar datetime to the t+20 datetime.
    """
    out = []
    for p in pairs:
        if not (start <= p["date"] <= end):
            continue
        tgt = target_date_map.get(datetime.strptime(p["date"], "%Y%m%d"))
        if tgt is None:
            continue
        tgt_str = tgt.strftime("%Y%m%d")
        if not (start <= tgt_str <= end):
            continue
        out.append(p)
    return out
