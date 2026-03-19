# SPY Benchmark & Verdict System

## Overview

A strategy that returns 50% sounds great — until you learn SPY returned 120% over the same period. Every strategy needs a benchmark, and for US equities, that benchmark is **SPY** (the S&P 500 ETF).

pyhood's `benchmark_spy()` function enriches your backtest results with SPY comparison data and assigns a **verdict** — a brutally honest assessment of whether your strategy actually beats the market.

## Why Benchmark Against SPY?

SPY represents the **default alternative**. If you're not trading a strategy, you could just buy SPY and hold it. Any strategy that can't beat SPY on a risk-adjusted basis is costing you money — you'd be better off doing nothing.

The backtesting engine already calculates `alpha` (strategy return minus ticker buy & hold return), but that only tells you if you beat holding the same stock. SPY benchmarking tells you if you beat **the market**.

## The `benchmark_spy()` Function

```python
from pyhood.backtest.compare import benchmark_spy

# Enrich results with SPY comparison
enriched = benchmark_spy(results)

for r in enriched:
    print(f"{r.strategy_name}: {r.verdict}")
    print(f"  Strategy: {r.total_return:.1f}% return, {r.sharpe_ratio:.2f} Sharpe")
    print(f"  SPY:      {r.spy_return:.1f}% return, {r.spy_sharpe:.2f} Sharpe")
    print(f"  Alpha:    {r.spy_alpha:+.1f}%")
```

### What It Does

1. Fetches SPY historical data for the same date range as your backtest
2. Calculates SPY buy & hold return and Sharpe ratio
3. Compares your strategy against SPY
4. Assigns a verdict

### Fields Added to BacktestResult

| Field | Type | Description |
|-------|------|-------------|
| `spy_return` | `float` | SPY buy & hold return (%) for the same period |
| `spy_sharpe` | `float` | SPY Sharpe ratio for the same period |
| `spy_alpha` | `float` | `total_return - spy_return` — excess return over SPY |
| `verdict` | `str` | Human-readable verdict (see below) |

## Verdict Logic

The verdict compares both **return** and **Sharpe ratio** against SPY:

| Verdict | Condition | Meaning |
|---------|-----------|---------|
| ✅ **Beats both** | Higher return AND higher Sharpe than SPY | Genuinely superior — better returns with better risk-adjusted performance |
| ⚠️ **Better risk-adjusted** | Higher Sharpe but lower return than SPY | Smoother ride, less risk — but lower total returns |
| ❌ **Underperforms** | Lower Sharpe than SPY | SPY wins on risk-adjusted basis — this strategy isn't worth the effort |

### The Honest Truth

In our testing, **3 out of 45 strategies** beat SPY on both return and Sharpe ratio over 10 years. Most technical analysis strategies underperform buy & hold on major indices.

This isn't a bug — it's the market working as intended. SPY is a diversified, low-cost, tax-efficient vehicle. Beating it consistently is genuinely hard.

## The Ticker Buy & Hold Comparison

The `BacktestResult` already includes two levels of comparison:

1. **`alpha`** = Strategy return − Ticker buy & hold return (e.g., strategy vs holding AAPL)
2. **`spy_alpha`** = Strategy return − SPY buy & hold return (e.g., strategy vs holding SPY)

Both matter:
- Negative `alpha` means you'd be better off just holding the stock you're trading
- Negative `spy_alpha` means you'd be better off in an index fund

## Code Examples

### Basic Benchmarking

```python
from pyhood.backtest import Backtester
from pyhood.backtest.strategies import ema_crossover, rsi_mean_reversion
from pyhood.backtest.compare import benchmark_spy

bt = Backtester.from_yfinance("AAPL", period="10y")

results = [
    bt.run(ema_crossover(fast=9, slow=21), "EMA 9/21"),
    bt.run(rsi_mean_reversion(oversold=30, overbought=70), "RSI 30/70"),
]

# Add SPY benchmark data
enriched = benchmark_spy(results)

for r in enriched:
    print(f"\n{r.strategy_name}")
    print(f"  Return:     {r.total_return:>7.1f}%")
    print(f"  Sharpe:     {r.sharpe_ratio:>7.2f}")
    print(f"  SPY Return: {r.spy_return:>7.1f}%")
    print(f"  SPY Sharpe: {r.spy_sharpe:>7.2f}")
    print(f"  SPY Alpha:  {r.spy_alpha:>+7.1f}%")
    print(f"  Verdict:    {r.verdict}")
```

### Using with `compare_backtests`

The comparison table automatically includes SPY columns when available:

```python
from pyhood.backtest.compare import benchmark_spy, compare_backtests

enriched = benchmark_spy(results)
print(compare_backtests(enriched))
```

### Interpreting Verdicts

```python
enriched = benchmark_spy(results)

for r in enriched:
    if '✅' in r.verdict:
        print(f"🎯 {r.strategy_name} genuinely beats the market!")
    elif '⚠️' in r.verdict:
        print(f"📉 {r.strategy_name} has lower risk but lower returns")
    else:
        print(f"❌ {r.strategy_name} — just buy SPY instead")
```

## When "Losing" Strategies Are Still Useful

A strategy with verdict ❌ isn't necessarily worthless:

- **Lower drawdown**: If SPY dropped -34% but your strategy only dropped -15%, that might be worth the lower return. You sleep better.
- **Smoother equity curve**: Less volatility means more predictable outcomes — useful if you're drawing income from the portfolio.
- **Hedging**: A strategy that profits in bear markets (even with low overall returns) can complement a buy-and-hold portfolio.
- **Different asset class**: If you're testing crypto strategies, SPY isn't a fair benchmark — the risk profiles are different.

The verdict is a starting point, not the final word. Context matters.

## Requirements

`benchmark_spy()` requires `yfinance` to fetch SPY data:

```bash
pip install yfinance
```

If yfinance is not installed, the function returns results unchanged (no SPY data, no verdict).

## Related Docs

- [Backtesting](backtesting.md) — Core backtesting engine and metrics
- [Regime Awareness](regime-awareness.md) — Understanding when strategies work
- [Cross-Validation](cross-validation.md) — Multi-ticker robustness testing
- [AutoResearch](autoresearch.md) — Automated strategy discovery
