# Bollinger Breakout

A volatility-breakout strategy that buys when price breaks above the upper Bollinger Band and exits when it falls back to the middle band (SMA).

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `period` | 20 | Bollinger Bands moving average period |
| `std_dev` | 2.0 | Standard deviation multiplier for band width |

## Entry / Exit Logic

- **Buy:** Price closes above the upper band (SMA + std_dev * StdDev) with no existing position
- **Sell:** Price closes below the middle band (SMA) while holding long

The upper band acts as a breakout confirmation — price exceeding it signals strong momentum. The middle band (SMA) serves as a trailing exit.

## Code Example

```python
from pyhood.backtest import Backtester
from pyhood.backtest.strategies import bollinger_breakout

bt = Backtester.from_yfinance("SPY", period="10y")
result = bt.run(bollinger_breakout(period=20, std_dev=2.0), "Bollinger Breakout")

print(f"Total Return: {result.total_return:.2f}%")
print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
print(f"Win Rate: {result.win_rate:.1f}%")
print(f"Total Trades: {result.total_trades}")
```

## Source

Developed by John Bollinger in the 1980s. Bollinger Bands are among the most popular volatility indicators. This implementation uses the breakout variant rather than the mean-reversion variant.
