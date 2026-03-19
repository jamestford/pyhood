# Strategy Catalog

A catalog of built-in trading strategies with reproducible backtest results. All strategies are implemented in pure Python with no external dependencies.

Each strategy follows the same interface: a factory function that returns a callable `(candles, position) -> signal`. This makes them plug-and-play with the `Backtester` engine.

## Benchmark Comparison

All strategies benchmarked with default parameters and $10,000 initial capital.

| Strategy | SPY 10yr Return | SPY 10yr Sharpe | AAPL 5yr Return | AAPL 5yr Sharpe | TSLA 5yr Return | TSLA 5yr Sharpe |
|---|---|---|---|---|---|---|
| [EMA Crossover](ema-crossover.md) | TBD | TBD | TBD | TBD | TBD | TBD |
| [RSI Mean Reversion](rsi-mean-reversion.md) | TBD | TBD | TBD | TBD | TBD | TBD |
| [Bollinger Breakout](bollinger-breakout.md) | TBD | TBD | TBD | TBD | TBD | TBD |
| [MA+ATR Mean Reversion](ma-atr-mean-reversion.md) | TBD | TBD | TBD | TBD | TBD | TBD |

Run `examples/strategy_catalog.py` to reproduce these results with live data.

## Quick Start

```python
from pyhood.backtest import Backtester
from pyhood.backtest.strategies import ema_crossover, ma_atr_mean_reversion

bt = Backtester.from_yfinance("SPY", period="10y")

result = bt.run(ema_crossover(), "EMA Crossover")
print(f"Return: {result.total_return:.2f}%  Sharpe: {result.sharpe_ratio:.2f}")

result = bt.run(ma_atr_mean_reversion(), "MA+ATR Mean Reversion")
print(f"Return: {result.total_return:.2f}%  Sharpe: {result.sharpe_ratio:.2f}")
```
