"""Backtesting engine for pyhood strategies."""

from pyhood.backtest.compare import compare_backtests, rank_backtests
from pyhood.backtest.engine import Backtester
from pyhood.backtest.models import BacktestResult, Trade
from pyhood.backtest.strategies import (
    bollinger_breakout,
    ema_crossover,
    ma_atr_mean_reversion,
    rsi_mean_reversion,
)

__all__ = [
    "Backtester",
    "BacktestResult",
    "Trade",
    "compare_backtests",
    "rank_backtests",
    "bollinger_breakout",
    "ema_crossover",
    "ma_atr_mean_reversion",
    "rsi_mean_reversion",
]
