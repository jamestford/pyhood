# EMA Crossover

A classic trend-following strategy that uses two Exponential Moving Averages of different periods to detect momentum shifts.

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `fast` | 9 | Fast EMA period |
| `slow` | 21 | Slow EMA period |

## Entry / Exit Logic

- **Buy:** Fast EMA crosses above slow EMA (no existing position)
- **Sell:** Fast EMA crosses below slow EMA (holding long)

The crossover is detected by comparing the relative position of the two EMAs on consecutive bars.

## Code Example

```python
from pyhood.backtest import Backtester
from pyhood.backtest.strategies import ema_crossover

bt = Backtester.from_yfinance("SPY", period="10y")
result = bt.run(ema_crossover(fast=9, slow=21), "EMA Crossover")

print(f"Total Return: {result.total_return:.2f}%")
print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
print(f"Win Rate: {result.win_rate:.1f}%")
print(f"Total Trades: {result.total_trades}")
```

## Source

Classic technical analysis. The EMA crossover is one of the most widely used trend-following signals, popularized in the 1970s alongside the development of computerized charting.
