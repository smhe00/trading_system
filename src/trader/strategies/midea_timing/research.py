"""Pure research helpers for the Midea historical regime study.

These are descriptive-research utilities only — no trading, no parameter
optimization. They reuse the locked baseline conventions (close/MA regime
state, forward adjusted returns, deterministic position reconstruction).
"""
from __future__ import annotations

from typing import Optional


def forward_return(closes, idx: int, horizon: int) -> Optional[float]:
    """``close[idx+horizon] / close[idx] - 1``.

    Uses only data through ``idx`` plus the single forward target. Returns
    None when the forward target is out of range — the tail bars are
    excluded, never filled.
    """
    if closes is None or idx < 0 or idx + horizon >= len(closes):
        return None
    return closes[idx + horizon] / closes[idx] - 1.0


def forward_returns(closes, horizon: int) -> list:
    """List of forward returns with None at the tail (``horizon`` bars)."""
    return [forward_return(closes, i, horizon) for i in range(len(closes))]


def regime_contained_sample(
    dates, idx: int, horizon: int, start: str, end: str
) -> bool:
    """True when BOTH the state date ``idx`` and the forward target date
    ``idx + horizon`` lie inside the calendar interval ``[start, end]``.

    This prevents cross-regime contamination: a sample labelled OLD must
    never use a target price from RECENT. Checking the target date only
    defines the evaluation sample boundary — it does not introduce
    look-ahead into the state calculation (which still uses data through
    ``idx`` close only).
    """
    if dates is None or idx < 0 or idx + horizon >= len(dates):
        return False
    d_t = dates[idx]
    d_th = dates[idx + horizon]
    return start <= d_t <= end and start <= d_th <= end


def select_regime_bars(bars, start: str, end: str) -> list:
    """Bars whose trading dates fall inside the calendar interval
    ``[start, end]`` (YYYYMMDD). Returns only available tradable bars inside
    the bounds; the actual first/last are the caller's effective boundaries.
    """
    return [b for b in bars if start <= b.datetime.strftime("%Y%m%d") <= end]


def warmup_bars(bars, window_start: str, count: int) -> list:
    """Up to ``count`` bars strictly before ``window_start`` (for indicator
    warm-up only — never traded before the period start)."""
    pre = [b for b in bars if b.datetime.strftime("%Y%m%d") < window_start]
    return pre[-count:] if count > 0 else []


def position_series(trades, dates) -> list:
    """Deterministic daily position series (net shares) over ``dates``.

    Consistent with the trade list: on a trade date the delta is applied from
    that date onward; dates without trades carry the previous position. The
    trade direction/volume semantics match the locked baseline (LONG +vol,
    SHORT -vol). No look-ahead.
    """
    from vnpy.trader.constant import Direction

    deltas = {}
    for trade in trades:
        d = trade.datetime.date()
        delta = trade.volume if trade.direction == Direction.LONG else -trade.volume
        deltas[d] = deltas.get(d, 0) + delta

    pos = 0
    series = []
    for d in dates:
        pos += deltas.get(d, 0)
        series.append(pos)
    return series


def sma_series(closes, window: int) -> list:
    """Rolling simple moving average (None until ``window`` values)."""
    n = len(closes)
    out: list = [None] * n
    if window <= 0:
        return out
    running = 0.0
    for i, c in enumerate(closes):
        running += c
        if i >= window:
            running -= closes[i - window]
        if i >= window - 1:
            out[i] = running / window
    return out


def ma_state_at(closes, ma_fast, ma_mid, ma_slow, idx: int) -> Optional[bool]:
    """Fixed MA state at ``idx`` using only data through ``idx`` close.

    True = LONG (close > MA_slow AND MA_fast > MA_mid), False = CASH, or
    None when indicators are not yet available (insufficient warm-up).
    """
    if None in (ma_fast[idx], ma_mid[idx], ma_slow[idx]):
        return None
    return closes[idx] > ma_slow[idx] and ma_fast[idx] > ma_mid[idx]
