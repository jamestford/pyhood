#!/usr/bin/env python3
"""Benchmark all built-in strategies across multiple tickers.

Runs each strategy on SPY, QQQ, AAPL, TSLA, and BTC-USD (all 10yr) using
yfinance data, prints compact summary and detailed comparison tables, and
saves results to examples/catalog_results.json.

Usage:
    pip install yfinance
    python examples/strategy_catalog.py
"""

import json
import os

from pyhood.backtest import Backtester, benchmark_spy, compare_backtests
from pyhood.backtest.strategies import (
    bollinger_breakout,
    donchian_breakout,
    ema_crossover,
    golden_cross,
    keltner_squeeze,
    ma_atr_mean_reversion,
    macd_crossover,
    rsi2_connors,
    rsi_mean_reversion,
)

STRATEGIES = [
    ("EMA Crossover", ema_crossover(fast=9, slow=21)),
    ("RSI Mean Reversion", rsi_mean_reversion(period=14, oversold=30, overbought=70)),
    ("Bollinger Breakout", bollinger_breakout(period=20, std_dev=2.0)),
    ("MA+ATR Mean Reversion", ma_atr_mean_reversion()),
    ("Donchian Breakout", donchian_breakout(entry_period=20, exit_period=10)),
    ("RSI(2) Connors", rsi2_connors()),
    ("MACD Crossover", macd_crossover()),
    ("Golden Cross", golden_cross()),
    ("Keltner Squeeze", keltner_squeeze()),
]

TICKERS = [
    ("SPY", "10y"),
    ("QQQ", "10y"),
    ("AAPL", "10y"),
    ("TSLA", "10y"),
    ("BTC-USD", "10y"),
]

# Short display names for the compact table
TICKER_SHORT = {"SPY": "SPY", "QQQ": "QQQ", "AAPL": "AAPL", "TSLA": "TSLA", "BTC-USD": "BTC"}


def _verdict_icon(verdict: str) -> str:
    """Extract just the icon from a verdict string."""
    if "\u2705" in verdict:
        return "\u2705"
    if "\u26a0\ufe0f" in verdict:
        return "\u26a0\ufe0f"
    return "\u274c"


def _compact_cell(result) -> str:
    """Format a compact cell: 'Return% / Sharpe Verdict'."""
    icon = _verdict_icon(result.verdict) if result.verdict else ""
    return f"{result.total_return:.1f}% / {result.sharpe_ratio:.2f} {icon}".strip()


def _compact_cell_benchmark(result) -> str:
    """Format a compact cell for SPY Buy & Hold (no verdict)."""
    return f"{result.spy_return:.1f}% / {result.spy_sharpe:.2f}"


def main():
    print("Strategy Catalog Benchmark")
    print("=" * 80)

    all_results = {}          # JSON output: {symbol: [result_dicts]}
    grid = {}                 # grid[(strategy_name, symbol)] = enriched BacktestResult
    spy_bench = {}            # spy_bench[symbol] = (spy_return, spy_sharpe)

    for symbol, period in TICKERS:
        short = TICKER_SHORT[symbol]
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

        # Benchmark against SPY
        ticker_results = benchmark_spy(ticker_results)

        # Store for compact table
        for r in ticker_results:
            grid[(r.strategy_name, symbol)] = r

        # Cache SPY benchmark values for this ticker
        if ticker_results and ticker_results[0].spy_return is not None:
            spy_bench[symbol] = (ticker_results[0].spy_return, ticker_results[0].spy_sharpe)

        # Print detailed per-ticker table
        print(f"\n{short} ({period}) Results:")
        print("-" * 80)
        print(compare_backtests(ticker_results))

    # ── Compact Summary Table ──
    print("\n")
    print("=" * 80)
    print("COMPACT SUMMARY  (Return% / Sharpe Verdict)")
    print("=" * 80)

    ticker_headers = [TICKER_SHORT[t] for t, _ in TICKERS]
    header = "| Strategy | " + " | ".join(ticker_headers) + " |"
    sep = "|---|" + "|".join(["---"] * len(TICKERS)) + "|"
    print(header)
    print(sep)

    for name, _ in STRATEGIES:
        cells = []
        for symbol, _ in TICKERS:
            r = grid.get((name, symbol))
            if r:
                cells.append(_compact_cell(r))
            else:
                cells.append("N/A")
        print(f"| {name} | " + " | ".join(cells) + " |")

    # SPY Buy & Hold row
    bh_cells = []
    for symbol, _ in TICKERS:
        if symbol in spy_bench:
            ret, sharpe = spy_bench[symbol]
            bh_cells.append(f"{ret:.1f}% / {sharpe:.2f}")
        else:
            bh_cells.append("N/A")
    print("| **SPY Buy & Hold** | " + " | ".join(bh_cells) + " |")

    # Save to JSON
    output_path = os.path.join(os.path.dirname(__file__), "catalog_results.json")
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
