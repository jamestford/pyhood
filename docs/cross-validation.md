# Multi-Ticker Cross-Validation

## Overview

A strategy that works on SPY but fails on QQQ and DIA isn't a strategy — it's a coincidence. Single-ticker backtests are **dangerous** because they can overfit to the specific price patterns of one instrument while telling you nothing about whether the underlying logic actually works.

pyhood's cross-validation system tests your strategies across multiple related tickers automatically. If a strategy can't generalise beyond the ticker it was optimised on, it gets flagged.

## Why Single-Ticker Results Are Dangerous

Consider: you test 100 parameter combinations of EMA crossover on SPY and find one with a 1.5 Sharpe ratio. Impressive? Maybe not.

With 100 random tries, you'd expect some to look good by chance alone. If that same parameter set also produces positive returns on QQQ and DIA — instruments with similar but different price action — now you have evidence that the signal is real, not noise.

Cross-validation is the difference between **data mining** and **strategy discovery**.

## How pyhood's Cross-Validation Works

After a strategy passes the train → test → validate pipeline on its primary ticker, `validate_best()` automatically runs it on a set of related tickers:

```
Primary ticker (SPY) → Train ✅ → Test ✅ → Validate ✅ → Cross-validate on QQQ, DIA
```

A ticker passes cross-validation if **all three conditions** are met:
1. `sharpe_ratio >= cross_validate_min_sharpe` (default: 0.5)
2. `total_return > 0` (positive returns)
3. `total_trades >= min_trades_test` (enough trades to be meaningful)

The strategy passes overall cross-validation if enough tickers pass (default: 2 out of the available cross-validation tickers).

## Default Ticker Groups

pyhood automatically selects cross-validation tickers based on the primary ticker:

### Equity Index ETFs

| Primary Ticker | Cross-Validate Against |
|---------------|----------------------|
| SPY | QQQ, DIA |
| QQQ | SPY, DIA |
| DIA | SPY, QQQ |
| IWM | SPY, QQQ, DIA |
| VOO | SPY, QQQ, DIA |

### Crypto

| Primary Ticker | Cross-Validate Against |
|---------------|----------------------|
| BTC-USD | ETH-USD, SOL-USD |
| ETH-USD | BTC-USD, SOL-USD |
| SOL-USD | BTC-USD, ETH-USD |

For other tickers (individual stocks like AAPL, MSFT), no default cross-validation tickers are set — you need to provide them explicitly.

## Configuration

### AutoResearcher Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `cross_validate_tickers` | Auto-detected | List of ticker symbols for cross-validation |
| `cross_validate_min_pass` | `2` | Minimum tickers that must pass |
| `cross_validate_min_sharpe` | `0.5` | Minimum Sharpe ratio on each cross-validation ticker |

### Setting Custom Cross-Validation Tickers

```python
from pyhood.autoresearch import AutoResearcher

# Explicit cross-validation tickers
researcher = AutoResearcher(
    ticker='AAPL',
    total_period='10y',
    cross_validate_tickers=['MSFT', 'GOOGL', 'AMZN'],
    cross_validate_min_pass=2,
    cross_validate_min_sharpe=0.3,
)
```

### Disabling Cross-Validation

```python
# Pass an empty list to disable
researcher = AutoResearcher(
    ticker='SPY',
    total_period='10y',
    cross_validate_tickers=[],
)
```

## The `cross_validate()` Method

You can call cross-validation directly on any strategy:

```python
from pyhood.autoresearch import AutoResearcher
from pyhood.backtest.strategies import ema_crossover

researcher = AutoResearcher(ticker='SPY', total_period='10y')

strategy = ema_crossover(fast=9, slow=21)
cv_result = researcher.cross_validate(strategy, "EMA 9/21")

print(f"Passed: {cv_result['passed']}")
print(f"Pass count: {cv_result['pass_count']}/{cv_result['required']}")

for ticker, data in cv_result['results'].items():
    status = '✅' if data['passed'] else '❌'
    print(f"  {status} {ticker}: Sharpe={data['sharpe']:.4f}, "
          f"Return={data['return']:.2f}%, Trades={data['trades']}")
```

### Return Value

```python
{
    'passed': True,              # Overall pass/fail
    'results': {
        'QQQ': {
            'sharpe': 0.8234,    # Sharpe ratio on this ticker
            'return': 45.2,      # Total return (%)
            'trades': 48,        # Number of trades
            'passed': True,      # This ticker passed
        },
        'DIA': {
            'sharpe': 0.3120,
            'return': 12.1,
            'trades': 52,
            'passed': False,     # Below min_sharpe threshold
        },
    },
    'pass_count': 1,             # How many tickers passed
    'required': 2,               # How many needed to pass
}
```

## How `validate_best()` Integrates Cross-Validation

When you call `researcher.validate_best()`, cross-validation runs automatically after the validate split:

```python
validated = researcher.validate_best(n=3)

for exp in validated:
    print(f"{exp.strategy_name}: {exp.reason}")
    if exp.cross_validation:
        cv = exp.cross_validation
        status = '✅ PASSED' if cv['passed'] else '❌ FAILED'
        print(f"  Cross-validation: {status} "
              f"({cv['pass_count']}/{cv['required']})")
```

The full report (`researcher.report()`) also includes cross-validation results for each kept strategy.

## What "Robust" Means

A strategy is considered robust in pyhood if it passes **all four gates**:

1. **Train** — Sharpe > 0.8 with sufficient trades (≥20)
2. **Test** — Sharpe confirms on unseen data (≥10 trades)
3. **Validate** — Final confirmation on held-out data (≥10 trades)
4. **Cross-validation** — Works on related tickers (≥2 pass with Sharpe > 0.5)

Plus the qualitative checks:
- Train–Test gap < 30% (no overfitting)
- Profitable in ≥2 market regimes (not regime-dependent)
- Parameter stability (nearby parameters produce similar results)

If a strategy clears all these hurdles, you have genuine evidence — not proof, but evidence — that the underlying signal is real.

## When to Override Defaults

### Sector-Specific Strategies

If you're testing a strategy designed for tech stocks, cross-validating against DIA (Dow Jones industrials) may not be appropriate:

```python
researcher = AutoResearcher(
    ticker='QQQ',
    cross_validate_tickers=['XLK', 'SOXX'],  # Tech ETFs
)
```

### Individual Stocks

For single-stock strategies, pick peers:

```python
researcher = AutoResearcher(
    ticker='AAPL',
    cross_validate_tickers=['MSFT', 'GOOGL'],
    cross_validate_min_pass=1,  # Looser requirement for individual stocks
)
```

### Crypto Strategies

The defaults (BTC/ETH/SOL) work well for major crypto. For altcoins:

```python
researcher = AutoResearcher(
    ticker='DOGE-USD',
    cross_validate_tickers=['SHIB-USD', 'PEPE-USD'],
    cross_validate_min_sharpe=0.3,  # Lower bar for volatile assets
)
```

## Manually Setting Cross-Validators

For testing or when you want full control over the data:

```python
from pyhood.backtest import Backtester

researcher = AutoResearcher(ticker='SPY', total_period='10y')

# Set up custom backtesters for cross-validation
researcher.set_cross_validators({
    'QQQ': Backtester.from_yfinance('QQQ', period='10y'),
    'DIA': Backtester.from_yfinance('DIA', period='10y'),
    'IWM': Backtester.from_yfinance('IWM', period='10y'),
})
```

## Related Docs

- [AutoResearch](autoresearch.md) — Full automated strategy discovery pipeline
- [Regime Awareness](regime-awareness.md) — Another robustness dimension (time-based)
- [Benchmarking](benchmarking.md) — SPY comparison and verdicts
- [Overnight Runner](overnight-runner.md) — Running cross-validated research overnight
