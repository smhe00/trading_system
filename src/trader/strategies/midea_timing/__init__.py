"""Midea A-share timing baseline (research/backtest only)."""
from .ma_regime import (
    MaRegimeStrategy,
    compute_ma,
    ma_regime_signal,
    size_board_lots,
    terminal_liquidation,
)

__all__ = [
    "MaRegimeStrategy",
    "compute_ma",
    "ma_regime_signal",
    "size_board_lots",
    "terminal_liquidation",
]
