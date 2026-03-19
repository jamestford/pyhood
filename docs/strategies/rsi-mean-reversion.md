# RSI Mean Reversion

A mean-reversion strategy that uses the Relative Strength Index to identify oversold and overbought conditions.

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `period` | 14 | RSI calculation period |
| `oversold` | 30 | RSI level below which the asset is considered oversold (buy signal) |
| `overbought` | 70 | RSI level above which the asset is considered overbought (sell signal) |

## Entry / Exit Logic

- **Buy:** RSI drops below the oversold threshold (no existing position)
- **Sell:** RSI rises above the overbought threshold (holding long)

RSI is calculated using the standard formula: `RSI = 100 - 100 / (1 + RS)` where RS is the ratio of average gains to average losses over the lookback period.

## Code Example

```python
from pyhood.backtest import Backtester
from pyhood.backtest.strategies import rsi_mean_reversion

bt = Backtester.from_yfinance("SPY", period="10y")
result = bt.run(rsi_mean_reversion(period=14, oversold=30, overbought=70), "RSI Mean Reversion")

print(f"Total Return: {result.total_return:.2f}%")
print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
print(f"Win Rate: {result.win_rate:.1f}%")
print(f"Total Trades: {result.total_trades}")
```

## Source

Developed by J. Welles Wilder Jr. and introduced in his 1978 book *New Concepts in Technical Trading Systems*. The 30/70 thresholds are the standard levels used by most practitioners.
