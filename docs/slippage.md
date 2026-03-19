# Slippage Modeling

## Overview

Slippage is the difference between the price you expect to trade at and the price you actually get. In the real world, you never buy at exactly the close price — market orders execute at the best available ask (for buys) or bid (for sells), which is always slightly worse than the midpoint.

Backtests that ignore slippage produce results that are **too optimistic**. For low-frequency stock strategies (10–200 trades over several years), the impact is small. For high-frequency strategies or illiquid assets, slippage can turn a winner into a loser.

pyhood's backtesting engine supports configurable slippage modeling to keep your results honest.

## How It Works

When `slippage_pct` is set, the engine adjusts execution prices on every trade:

- **Buy orders** execute at `close_price × (1 + slippage_pct / 100)` — you pay slightly more
- **Sell orders** execute at `close_price × (1 - slippage_pct / 100)` — you receive slightly less
- **Short entries** execute at `close_price × (1 - slippage_pct / 100)` — you receive slightly less on the initial sale
- **Short covers** execute at `close_price × (1 + slippage_pct / 100)` — you pay slightly more to close

Every round-trip trade costs you slippage twice — once on entry, once on exit.

## The `slippage_pct` Parameter

| Setting | Meaning | Use Case |
|---------|---------|----------|
| `0.0` (default) | No slippage — ideal execution | Quick prototyping, upper-bound estimates |
| `0.01` | 0.01% per trade (1 basis point) | **Recommended for Robinhood stock/ETF trades** |
| `0.05` | 0.05% per trade | Small-cap stocks, moderate liquidity |
| `0.10` | 0.10% per trade | Illiquid stocks, penny stocks |
| `0.25`+ | 0.25%+ per trade | Crypto, very illiquid assets |

### Why 0.01% for Robinhood?

Robinhood routes orders through market makers (payment for order flow). For liquid stocks and ETFs like AAPL, SPY, and QQQ, the effective spread is typically 1–3 basis points. A `slippage_pct` of `0.01` is a conservative estimate for the average cost per execution.

## Code Examples

### Creating a Backtester with Slippage

```python
from pyhood.backtest import Backtester
from pyhood.backtest.strategies import ema_crossover

# Direct construction with candle data
bt = Backtester(candles, initial_capital=10000, slippage_pct=0.01)
result = bt.run(ema_crossover(fast=9, slow=21), "EMA 9/21")
```

### Using `from_yfinance` with Slippage

```python
# Recommended: use yfinance for 10+ years of data with slippage
bt = Backtester.from_yfinance("SPY", period="10y", slippage_pct=0.01)
result = bt.run(ema_crossover(fast=9, slow=21), "EMA 9/21 (with slippage)")

print(f"Total Return: {result.total_return:.1f}%")
print(f"Slippage applied: {result.slippage_pct}%")
```

### Comparing With and Without Slippage

```python
bt_no_slip = Backtester.from_yfinance("SPY", period="10y", slippage_pct=0.0)
bt_slip = Backtester.from_yfinance("SPY", period="10y", slippage_pct=0.01)

strategy = ema_crossover(fast=9, slow=21)

result_ideal = bt_no_slip.run(strategy, "EMA 9/21 (no slippage)")
result_real = bt_slip.run(strategy, "EMA 9/21 (0.01% slippage)")

print(f"Without slippage: {result_ideal.total_return:.1f}%")
print(f"With slippage:    {result_real.total_return:.1f}%")
print(f"Slippage cost:    {result_ideal.total_return - result_real.total_return:.2f}%")
```

## Impact on Results

The impact depends on **how many trades** a strategy makes:

| Trades | Slippage (0.01%) | Impact on $10,000 |
|--------|-----------------|-------------------|
| 20 | ~0.004% total | ~$0.40 |
| 100 | ~0.02% total | ~$2.00 |
| 500 | ~0.10% total | ~$10.00 |
| 5,000 | ~1.0% total | ~$100.00 |

For a typical pyhood strategy generating 50–200 trades over 10 years, the impact of 0.01% slippage is **negligible for stocks**. It matters more for:

- **High-frequency strategies** (500+ trades) — slippage compounds
- **Illiquid assets** — effective slippage is higher than 0.01%
- **Crypto** — spreads are wider, use 0.10–0.25%

## When to Use Higher Slippage

| Scenario | Recommended `slippage_pct` |
|----------|---------------------------|
| S&P 500 stocks, major ETFs | `0.01` |
| Mid-cap stocks | `0.03–0.05` |
| Small-cap / penny stocks | `0.10–0.25` |
| Crypto (BTC, ETH) | `0.10` |
| Crypto (altcoins) | `0.25–0.50` |
| After-hours trading | `0.10–0.20` |

## How Slippage Is Recorded

The `slippage_pct` value used during a backtest is stored on the `BacktestResult` object:

```python
result = bt.run(strategy, "My Strategy")
print(result.slippage_pct)  # 0.01
```

This makes results self-documenting — you always know what assumptions went into a backtest. When saving results with `AutoResearcher.save()`, the slippage value is preserved in the JSON output.

## Slippage in Overnight Research

The [Overnight Runner](overnight-runner.md) applies `0.01%` slippage by default for all experiments:

```bash
python scripts/run_overnight.py --slippage 0.01
```

This ensures all discovered strategies are already adjusted for realistic execution costs.

## Related Docs

- [Backtesting](backtesting.md) — Core backtesting engine
- [Benchmarking](benchmarking.md) — SPY comparison (also affected by slippage on your strategy)
- [Overnight Runner](overnight-runner.md) — Automated research with slippage defaults
