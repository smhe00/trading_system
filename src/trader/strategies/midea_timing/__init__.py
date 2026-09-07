"""Midea A-share timing baseline (research/backtest only)."""
from .ma_regime import (
    MaRegimeStrategy,
    build_anchored_series,
    compute_ma,
    ma_regime_signal,
    size_board_lots,
    terminal_liquidation,
)

__all__ = [
    "MaRegimeStrategy",
    "build_anchored_series",
    "compute_ma",
    "ma_regime_signal",
    "size_board_lots",
    "terminal_liquidation",
]
