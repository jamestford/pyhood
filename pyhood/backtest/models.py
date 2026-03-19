"""Data models for backtesting results."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Trade:
    """A completed trade with entry and exit details."""
    entry_date: str
    exit_date: str
    side: str  # 'long' or 'short'
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float


@dataclass(frozen=True)
class BacktestResult:
    """Complete results of a backtest run."""
    strategy_name: str
    symbol: str
    period: str  # "2021-01-01 to 2026-03-16"
    total_return: float  # percentage
    annual_return: float
    sharpe_ratio: float
    max_drawdown: float  # percentage (negative)
    win_rate: float  # percentage
    profit_factor: float
    total_trades: int
    avg_trade_return: float
    avg_win: float
    avg_loss: float
    buy_hold_return: float  # benchmark
    alpha: float  # strategy return - buy & hold
    trades: list[Trade]
    equity_curve: list[float]  # daily portfolio values
    # SPY benchmark fields (populated by benchmark_spy())
    spy_return: float | None = None        # SPY buy & hold return for same period
    spy_sharpe: float | None = None        # SPY Sharpe ratio for same period
    spy_alpha: float | None = None         # strategy total_return - spy_return
    verdict: str = ''                       # '✅ Beats both' / '⚠️ Better risk-adjusted' / '❌ Underperforms'
    slippage_pct: float = 0.0               # slippage applied per trade (% of price, e.g. 0.01 = 0.01%)
