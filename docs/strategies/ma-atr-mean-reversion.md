# MA+ATR Mean Reversion (Triple Nested MA)

A mean-reversion swing trading strategy that uses **triple nested moving averages** to confirm uptrends, then buys pullbacks using ATR-scaled bands around a short-term mean. Designed for high win rate and low drawdown rather than maximum returns.

## Source

[Forget 50 Indicators: This 3-Line QQQ Strategy Beats 90% of Traders](https://lirannh.medium.com/forget-50-indicators-this-3-line-qqq-strategy-beats-90-of-traders-85eb3edbddc2) by Liran Nachman (Jan 2026). Originally designed for QQQ on daily timeframe.

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `ma_period` | 40 | SMA period for all three nested MAs |
| `atr_length` | 14 | ATR calculation period |
| `mean_period` | 5 | Short-term mean (SMA of close) for entry/exit levels |
| `entry_multiplier` | 1.0 | ATR multiplier below mean for entry |
| `exit_multiplier` | 0.5 | ATR multiplier above mean for exit |

## How It Works

### Part 1: Trend Filter (Triple Nested MAs)

Three moving averages, each smoothing the previous one:

- **MA1** = SMA(close, 40)
- **MA2** = SMA(MA1, 40)
- **MA3** = SMA(MA2, 40)

**Uptrend confirmed** when: MA1 > MA2 AND MA2 > MA3 AND close > MA3

This creates a hierarchy of trend confirmation. All three layers must align before considering any entry.

### Part 2: Entry (Buy the Pullback)

Once in a confirmed uptrend, wait for price to pull back:

- **Entry level:** `mean - (1.0 × ATR)`
- **Buy when:** uptrend AND close < entry level AND no position

The ATR adapts to current volatility — wider bands in volatile markets, tighter in calm ones. We're buying weakness in strength, not weakness in weakness.

### Part 3: Exit (Take Profits)

Don't wait for trend reversal — take profits on the bounce:

- **Exit level:** `mean + (0.5 × ATR)`
- **Sell when:** close > exit level AND holding long

This captures the recovery from oversold to normal conditions without waiting for a full trend move.

## Code Example

```python
from pyhood.backtest import Backtester
from pyhood.backtest.strategies import ma_atr_mean_reversion

# QQQ is the original benchmark ticker
bt = Backtester.from_yfinance("QQQ", period="10y")
result = bt.run(ma_atr_mean_reversion(), "MA+ATR Mean Reversion")

print(f"Win Rate:      {result.win_rate:.1f}%")
print(f"Profit Factor: {result.profit_factor:.2f}")
print(f"Total Return:  {result.total_return:.1f}%")
print(f"Max Drawdown:  {result.max_drawdown:.1f}%")
print(f"Total Trades:  {result.total_trades}")
print(f"Sharpe Ratio:  {result.sharpe_ratio:.2f}")

# Custom parameters
aggressive = ma_atr_mean_reversion(entry_multiplier=0.5, exit_multiplier=0.3)
result2 = bt.run(aggressive, "MA+ATR Aggressive")
```

## Backtest Results

**QQQ 10yr (the article's benchmark):**
- Win Rate: 76.6% (article claims 79.1%)
- Profit Factor: 2.75 (article claims 3.22)
- Max Drawdown: -15.1% (article claims -17.4%)
- Total Trades: 64

**SPY 10yr:** 75.4% win rate, 2.54 PF, -10.2% max drawdown, 61 trades, 51.9% return

**AAPL 5yr:** 58.8% win rate, 1.03 PF, -11.4% max drawdown, 17 trades, 0.6% return

**TSLA 5yr:** 64.7% win rate, 0.94 PF, -54.0% max drawdown, 17 trades, -3.6% return

Small differences from the article likely stem from date range and TradingView's bar-by-bar execution model vs our end-of-day approach.

## When to Use / When to Avoid

**Works well on:**
- Large-cap ETFs with established uptrends (QQQ, SPY)
- Range-bound markets with clear mean-reversion dynamics
- When you prioritize **consistency and low drawdown** over raw returns

**Avoid on:**
- Highly volatile individual stocks (TSLA) — the trend filter whipsaws
- Extended downtrend periods — the filter correctly stays out but misses recovery rallies
- If you need to beat buy & hold — this sacrifices absolute returns for smoother equity curve

As one commenter noted: *"This is a volatility reduction strategy, not a return maximization strategy."*

## Parameter Tuning

| Adjustment | Effect |
|---|---|
| Higher `entry_multiplier` | Deeper pullbacks required → fewer trades, potentially better entries |
| Lower `exit_multiplier` | Exit faster with smaller gains → higher win rate, less per trade |
| Shorter `ma_period` | More responsive trend filter → more trades, more whipsaws |
| Longer `mean_period` | Smoother mean → slower entry/exit signals |
