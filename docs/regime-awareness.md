# Market Regime Classification

## Overview

Not all market conditions are created equal. A strategy that prints money in a bull run might bleed you dry in a correction. pyhood classifies every trading day into one of four **market regimes** so you can see exactly where your strategy's profits (and losses) come from.

If 80%+ of your P&L comes from a single regime, you don't have a strategy — you have a bet on market direction.

## The Four Regimes

| Regime | Price vs 200 SMA | SMA Slope | What It Means |
|--------|-------------------|-----------|---------------|
| **Bull** 🐂 | Above | Rising | Strong uptrend — price above rising moving average |
| **Bear** 🐻 | Below | Falling | Downtrend — price below falling moving average |
| **Recovery** 🔄 | Above | Falling | Price recovering, but trend hasn't confirmed — SMA still falling |
| **Correction** ⚠️ | Below | Rising | Pullback in an uptrend — SMA rising but price dipped below |
| **Unknown** ❓ | — | — | Not enough data (< 205 bars) for SMA calculation |

## How Classification Works

The regime classifier uses the **200-period Simple Moving Average (SMA)** — the same indicator institutional traders watch for long-term trend direction.

Two inputs determine the regime:

1. **Price position**: Is the current close above or below the 200 SMA?
2. **SMA slope**: Is the 200 SMA rising or falling? (Compared to its value 5 bars ago)

```
Price > SMA + SMA rising  → Bull
Price > SMA + SMA falling → Recovery
Price < SMA + SMA rising  → Correction
Price < SMA + SMA falling → Bear
```

### The `_classify_regime` Helper

The classification logic lives in `pyhood.backtest.strategies._classify_regime`:

```python
from pyhood.backtest.strategies import _classify_regime

# Classify regime at a specific candle index
regime = _classify_regime(candles, index=500, sma_period=200)
# Returns: 'bull', 'bear', 'recovery', 'correction', or 'unknown'
```

The function needs at least `sma_period + 5` bars of data (205 bars for the default 200 SMA). Earlier bars return `'unknown'`.

## Regime on Trade Objects

Every `Trade` object carries a `regime` field set at the time of entry:

```python
result = bt.run(ema_crossover(fast=9, slow=21), "EMA 9/21")

for trade in result.trades[:5]:
    print(f"{trade.entry_date[:10]} | {trade.regime:>12} | "
          f"P&L: {trade.pnl_pct:+.1f}%")
```

Output:
```
2016-08-15 |         bull | P&L: +3.2%
2016-11-02 |   correction | P&L: -1.8%
2017-01-10 |         bull | P&L: +5.1%
2018-12-05 |         bear | P&L: -4.3%
2019-02-20 |     recovery | P&L: +2.7%
```

## Regime Breakdown on BacktestResult

After a backtest, `result.regime_breakdown` contains aggregated performance per regime:

```python
result = bt.run(ema_crossover(fast=9, slow=21), "EMA 9/21")

for regime, stats in result.regime_breakdown.items():
    print(f"{regime:>12}: {stats['trades']} trades, "
          f"{stats['win_rate']}% win rate, "
          f"P&L: ${stats['pnl']:.2f}")
```

### Breakdown Structure

```python
result.regime_breakdown = {
    'bull': {
        'trades': 45,       # Number of trades entered during this regime
        'wins': 28,         # Winning trades
        'win_rate': 62.2,   # Win rate percentage
        'pnl': 1523.45,     # Total P&L in dollars
    },
    'bear': {
        'trades': 12,
        'wins': 3,
        'win_rate': 25.0,
        'pnl': -342.10,
    },
    # ... recovery, correction, unknown
}
```

## The `regime_report()` Function

For a formatted view, use `regime_report()` from `pyhood.backtest.compare`:

```python
from pyhood.backtest.compare import regime_report

result = bt.run(ema_crossover(fast=9, slow=21), "EMA 9/21")
print(regime_report(result))
```

### Example Output

```
=== Regime Report: EMA 9/21 ===

  Regime              Trades   Wins   Win Rate          P&L
  -------------- ------- ------ ---------- ------------
  bull                45     28      62.2%     1523.45
  bear                12      3      25.0%     -342.10
  recovery             8      5      62.5%      234.67
  correction          15      6      40.0%     -112.30

  Total P&L: $1,303.72
```

### Regime-Dependent Warning

If 80%+ of total P&L comes from a single regime, the report flags it:

```
  Total P&L: $1,303.72
  ⚠️  REGIME-DEPENDENT: 87% of P&L comes from 'bull' regime
```

This means the strategy is essentially a bull market strategy wearing a technical indicator costume. It will likely lose money in bear markets.

## Regime Data in AutoResearch

The [AutoResearch](autoresearch.md) system uses regime data as a robustness filter:

### Rule: Must Profit in 2+ Regimes

A strategy that only works in bull markets isn't robust. The autoresearch program requires strategies to show profitability across at least 2 out of 4 regimes before being considered "found."

### Anti-Overfitting Checklist (Regime Items)

From the full checklist in `program.md`:

- [ ] Profitable in ≥2 regimes (`regime_breakdown` check)
- [ ] Not regime-dependent (no single regime contributes 80%+ of P&L)
- [ ] `regime_report(result)` reviewed — no warning flags

## Complete Example

```python
from pyhood.backtest import Backtester
from pyhood.backtest.strategies import ema_crossover
from pyhood.backtest.compare import regime_report

# Load 10 years of SPY data
bt = Backtester.from_yfinance("SPY", period="10y")

# Run strategy
result = bt.run(ema_crossover(fast=9, slow=21), "EMA 9/21")

# Print the regime report
print(regime_report(result))

# Programmatically check regime dependency
if result.regime_breakdown:
    total_pnl = sum(d['pnl'] for d in result.regime_breakdown.values())
    profitable_regimes = sum(
        1 for d in result.regime_breakdown.values() if d['pnl'] > 0
    )
    print(f"\nProfitable in {profitable_regimes}/4 regimes")

    if total_pnl != 0:
        for regime, data in result.regime_breakdown.items():
            pct = (data['pnl'] / total_pnl) * 100 if data['pnl'] > 0 else 0
            if pct >= 80:
                print(f"⚠️ WARNING: {regime} contributes {pct:.0f}% of P&L")
```

## Why This Matters for Real Trading

Consider two strategies with identical backtested returns:

- **Strategy A**: Sharpe 1.2, profitable in bull + recovery, loses in bear + correction
- **Strategy B**: Sharpe 1.0, profitable in bull + bear + recovery, flat in correction

Strategy B is the better choice for real trading — it survives more market conditions. Strategy A will blow up the first time the market enters a sustained bear phase, and you'll be sitting there wondering why your "proven" strategy is hemorrhaging money.

The regime breakdown turns a single number (total return) into a story about when and why a strategy works. Read it before you trade.

## Related Docs

- [Backtesting](backtesting.md) — Core backtesting engine
- [Benchmarking](benchmarking.md) — SPY comparison with verdicts
- [Cross-Validation](cross-validation.md) — Multi-ticker robustness testing
- [AutoResearch](autoresearch.md) — Automated strategy discovery with regime filters
