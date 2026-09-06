"""Midea A-share timing baseline (research/backtest only)."""
from .ma_regime import MaRegimeStrategy, compute_ma, ma_regime_signal

__all__ = ["MaRegimeStrategy", "compute_ma", "ma_regime_signal"]
