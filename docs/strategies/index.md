# Strategy Catalog

A catalog of built-in trading strategies with reproducible backtest results. All strategies are implemented in pure Python with no external dependencies.

Each strategy follows the same interface: a factory function that returns a callable `(candles, position) -> signal`. This makes them plug-and-play with the `Backtester` engine.

## Benchmark Comparison

All strategies benchmarked with default parameters, $10,000 initial capital, 10yr period. Each cell shows `Return% / Sharpe Verdict` where ✅ = beats SPY on both return and Sharpe, ⚠️ = better risk-adjusted only, ❌ = underperforms.

### Trend Following

| Strategy | SPY | QQQ | AAPL | TSLA | BTC |
|---|---|---|---|---|---|
| [EMA Crossover](ema-crossover.md) | 144.1% / 0.88 ⚠️ | 200.2% / 0.87 ⚠️ | 661.3% / 1.16 ✅ | 2013.0% / 0.94 ✅ | 24022.1% / 1.14 ✅ |
| [MACD Crossover](macd-crossover.md) | 107.8% / 0.78 ❌ | 119.7% / 0.67 ❌ | 607.8% / 1.19 ✅ | 2952.6% / 1.04 ✅ | 17664.4% / 1.13 ✅ |
| [Golden Cross](golden-cross.md) | 89.3% / 0.53 ❌ | 226.2% / 0.77 ❌ | 162.5% / 0.54 ❌ | 621.5% / 0.65 ❌ | 671.8% / 0.58 ❌ |
| [Donchian Breakout](donchian-breakout.md) | 105.6% / 0.82 ❌ | 149.4% / 0.84 ❌ | 394.8% / 1.03 ✅ | 725.7% / 0.77 ❌ | 15088.3% / 1.13 ✅ |

### Mean Reversion

| Strategy | SPY | QQQ | AAPL | TSLA | BTC |
|---|---|---|---|---|---|
| [RSI Mean Reversion](rsi-mean-reversion.md) | 91.7% / 0.53 ❌ | 125.0% / 0.57 ❌ | 125.1% / 0.49 ❌ | 223.6% / 0.49 ❌ | -20.4% / 0.15 ❌ |
| [RSI(2) Connors](rsi2-connors.md) | 66.9% / 0.62 ❌ | 101.9% / 0.59 ❌ | 110.0% / 0.51 ❌ | 12.7% / 0.21 ❌ | 93.6% / 0.30 ❌ |
| [MA+ATR Mean Reversion](ma-atr-mean-reversion.md) | 51.9% / 0.67 ❌ | 84.8% / 0.72 ❌ | 41.6% / 0.37 ❌ | -13.9% / 0.08 ❌ | 535.2% / 0.70 ❌ |

### Volatility

| Strategy | SPY | QQQ | AAPL | TSLA | BTC |
|---|---|---|---|---|---|
| [Bollinger Breakout](bollinger-breakout.md) | 17.7% / 0.28 ❌ | 43.8% / 0.43 ❌ | 325.4% / 1.04 ✅ | 1858.6% / 1.06 ✅ | 5725.3% / 1.04 ✅ |
| [Keltner Squeeze](keltner-squeeze.md) | -4.0% / -0.16 ❌ | -13.5% / -0.40 ❌ | 16.6% / 0.30 ❌ | 96.7% / 0.47 ❌ | 165.8% / 0.51 ❌ |

### Benchmark (Buy & Hold)

| Strategy | SPY | QQQ | AAPL | TSLA | BTC |
|---|---|---|---|---|---|
| **Buy & Hold** | **276.8% / 0.83** | **485.6% / 0.91** | **926.3% / 0.95** | **2343.0% / 0.84** | **16751.0% / 0.91** |

## Key Findings

- **Almost nothing beats buy & hold of the same ticker.** AAPL returned 926%, TSLA 2343%, BTC 16,751% over 10yr. Even strategies that "beat SPY" mostly lost to just holding the ticker they traded.
- **Trend following beats SPY but not the ticker itself:** EMA, MACD, Bollinger on AAPL/TSLA/BTC all beat SPY's 279% — but still underperformed each ticker's own buy & hold.
- **MACD on TSLA (2952%) came closest** to beating TSLA buy & hold (2343%) — one of the rare ✅ where active trading actually added value.
- **Mean reversion is a trap:** RSI, RSI(2) Connors, and MA+ATR all underperformed across every ticker. High win rates, low returns. Feels good, makes less money.
- **The honest conclusion:** For most people, buying and holding beats active trading. These strategies are most useful for risk management (lower drawdowns) or as components of more complex systems — not as standalone approaches.

Run `examples/strategy_catalog.py` to reproduce these results with live data.

## Quick Start

```python
from pyhood.backtest import Backtester, benchmark_spy
from pyhood.backtest.strategies import ema_crossover, macd_crossover, donchian_breakout

bt = Backtester.from_yfinance("AAPL", period="10y")

results = [
    bt.run(ema_crossover(), "EMA Crossover"),
    bt.run(macd_crossover(), "MACD Crossover"),
    bt.run(donchian_breakout(), "Donchian Breakout"),
]

# Add SPY benchmark comparison
results = benchmark_spy(results)

for r in results:
    print(f"{r.strategy_name}: {r.total_return:.1f}% / {r.sharpe_ratio:.2f} {r.verdict}")
```
