"""Backtesting engine for pyhood strategies."""

from pyhood.backtest.compare import (
    benchmark_spy,
    compare_backtests,
    rank_backtests,
    regime_report,
    sensitivity_report,
    sensitivity_test,
)
from pyhood.backtest.engine import Backtester
from pyhood.backtest.models import BacktestResult, Trade
from pyhood.backtest.strategies import (
    bollinger_breakout,
    bull_flag_breakout,
    donchian_breakout,
    ema_crossover,
    golden_cross,
    keltner_squeeze,
    ma_atr_mean_reversion,
    macd_crossover,
    rsi2_connors,
    rsi_mean_reversion,
    volume_confirmed_breakout,
)

__all__ = [
    "Backtester",
    "BacktestResult",
    "Trade",
    "benchmark_spy",
    "compare_backtests",
    "rank_backtests",
    "regime_report",
    "sensitivity_report",
    "sensitivity_test",
    "bollinger_breakout",
    "bull_flag_breakout",
    "donchian_breakout",
    "ema_crossover",
    "golden_cross",
    "keltner_squeeze",
    "ma_atr_mean_reversion",
    "macd_crossover",
    "rsi2_connors",
    "rsi_mean_reversion",
    "volume_confirmed_breakout",
]
