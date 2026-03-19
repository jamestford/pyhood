#!/usr/bin/env python3
"""Benchmark all built-in strategies across multiple tickers.

Runs each strategy on SPY (10yr), AAPL (5yr), and TSLA (5yr) using
yfinance data, prints a formatted comparison table, and saves results
to examples/catalog_results.json.

Usage:
    pip install yfinance
    python examples/strategy_catalog.py
"""

import json
import os

from pyhood.backtest import Backtester, compare_backtests
from pyhood.backtest.strategies import (
    bollinger_breakout,
    ema_crossover,
    ma_atr_mean_reversion,
    rsi_mean_reversion,
)

STRATEGIES = [
    ("EMA Crossover", ema_crossover(fast=9, slow=21)),
    ("RSI Mean Reversion", rsi_mean_reversion(period=14, oversold=30, overbought=70)),
    ("Bollinger Breakout", bollinger_breakout(period=20, std_dev=2.0)),
    ("MA+ATR Mean Reversion", ma_atr_mean_reversion()),
]

TICKERS = [
    ("SPY", "10y"),
    ("AAPL", "5y"),
    ("TSLA", "5y"),
]


def main():
    print("Strategy Catalog Benchmark")
    print("=" * 80)

    all_results = {}

    for symbol, period in TICKERS:
        print(f"\nLoading {symbol} ({period})...", end=" ", flush=True)
        bt = Backtester.from_yfinance(symbol, period=period)
        print(f"{len(bt.candles)} candles")

        ticker_results = []

        for name, strategy in STRATEGIES:
            result = bt.run(strategy, name)
            ticker_results.append(result)

            all_results.setdefault(symbol, []).append({
                "strategy": name,
                "total_return": round(result.total_return, 2),
                "annual_return": round(result.annual_return, 2),
                "sharpe_ratio": round(result.sharpe_ratio, 2),
                "max_drawdown": round(result.max_drawdown, 2),
                "win_rate": round(result.win_rate, 1),
                "profit_factor": round(result.profit_factor, 2),
                "total_trades": result.total_trades,
                "alpha": round(result.alpha, 2),
            })

        print(f"\n{symbol} ({period}) Results:")
        print("-" * 80)
        print(compare_backtests(ticker_results))

    # Save to JSON
    output_path = os.path.join(os.path.dirname(__file__), "catalog_results.json")
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
