# Trading Strategy AutoResearch Program

## Your Goal
Find trading strategies that beat SPY buy & hold on a risk-adjusted basis (Sharpe ratio).

## The Setup
- You have access to pyhood's backtesting engine with 11 built-in strategies
- Data is split: Train (50%), Test (25%), Validate (25%)
- You ONLY optimize on Train data. Test data confirms. Validate is untouched until the end.

## Quick Start

```python
from pyhood.autoresearch import AutoResearcher
from pyhood.backtest.strategies import *

researcher = AutoResearcher(ticker='SPY', total_period='10y')
```

## Your Loop

1. Pick a strategy or create a new one
2. Run parameter sweep on TRAIN data
3. Check top 3 parameter sets on TEST data
4. If test Sharpe > current best AND test Sharpe > 0.8, keep it
5. Log everything
6. Repeat with a different strategy or modification

## Rules

- **Minimum trades per split** — Train: 20, Test: 10, Validate: 10. Strategies with fewer trades are noise.
- **Results must be stable** — if changing a parameter by ±10% kills performance, it's overfitting
- **Train and Test Sharpe should be within 30% of each other** — big gap = overfitting
- **Round number parameters only** — no 13.7, use 14
- **Multi-regime profitability** — Strategy must be profitable in at least 2 out of 4 regimes (bull/bear/recovery/correction)
- **Regime dependency check** — If 80%+ of total P&L comes from one regime, flag as regime-dependent. These strategies are fragile and will blow up in different market conditions.
- **Check regime_breakdown** — Always inspect `result.regime_breakdown` before declaring a strategy "found". Use `regime_report(result)` for a formatted view.
- **Cross-validation required** — After a strategy passes train/test/validate, it must also pass cross-validation on related tickers.
  - Default cross-validation for equity index ETFs: SPY + QQQ + DIA (must pass 2 out of 3, excluding primary ticker)
  - Default cross-validation for crypto: BTC-USD + ETH-USD + SOL-USD (same rule)
  - Cross-validation minimum: Sharpe > 0.5 and positive returns on each cross-validation ticker
  - If cross-validation fails, the strategy is **ticker-specific** and should be noted as such — it may work on one instrument but not generalise

## Available Strategies

### 1. EMA Crossover — `ema_crossover(fast, slow)`
Trend-following. Buy when fast EMA crosses above slow EMA, sell on the reverse.
- `fast`: Fast EMA period (default 9)
- `slow`: Slow EMA period (default 21)

### 2. RSI Mean Reversion — `rsi_mean_reversion(period, oversold, overbought)`
Counter-trend. Buy when RSI < oversold, sell when RSI > overbought.
- `period`: RSI period (default 14)
- `oversold`: Buy threshold (default 30)
- `overbought`: Sell threshold (default 70)

### 3. RSI(2) Connors — `rsi2_connors(rsi_period, sma_period, oversold, overbought)`
Short-term mean reversion with 200 SMA trend filter.
- `rsi_period`: Ultra-short RSI period (default 2)
- `sma_period`: Trend filter SMA (default 200)
- `oversold`: Buy threshold (default 10)
- `overbought`: Sell threshold (default 90)

### 4. MACD Crossover — `macd_crossover(fast, slow, signal)`
Classic trend-following with MACD line vs signal line crossovers.
- `fast`: Fast EMA period (default 12)
- `slow`: Slow EMA period (default 26)
- `signal`: Signal line EMA period (default 9)

### 5. Golden Cross — `golden_cross(fast_period, slow_period)`
Long-term trend-following (50/200 SMA crossover).
- `fast_period`: Fast SMA (default 50)
- `slow_period`: Slow SMA (default 200)

### 6. Bollinger Breakout — `bollinger_breakout(period, std_dev)`
Buy on upper band breakout, sell on middle band (SMA) breakdown.
- `period`: BB period (default 20)
- `std_dev`: Standard deviation multiplier (default 2.0)

### 7. Keltner Squeeze — `keltner_squeeze(keltner_period, keltner_atr_mult, bb_period, bb_std)`
Volatility squeeze detection + breakout trading.
- `keltner_period`: EMA/ATR period (default 20)
- `keltner_atr_mult`: ATR multiplier (default 1.5)
- `bb_period`: Bollinger period (default 20)
- `bb_std`: BB std dev multiplier (default 2.0)

### 8. Donchian Breakout — `donchian_breakout(entry_period, exit_period)`
Turtle Trading rules. Buy on channel high breakout, sell on channel low breakdown.
- `entry_period`: Entry channel lookback (default 20)
- `exit_period`: Exit channel lookback (default 10)

### 9. Volume Confirmed Breakout — `volume_confirmed_breakout(volume_period, top_pct, threshold, sma_period)`
SMA trend + net distribution volume filter.
- `volume_period`: Volume lookback (default 20)
- `top_pct`: High-volume fraction (default 0.25)
- `threshold`: Bullish confirmation threshold (default 0.6)
- `sma_period`: SMA period (default 50)

### 10. Bull Flag Breakout — `bull_flag_breakout(pole_min_pct, flag_max_bars, flag_retrace_max, volume_confirm)`
Chart pattern recognition — bull flag continuation.
- `pole_min_pct`: Minimum pole gain % (default 5.0)
- `flag_max_bars`: Maximum flag duration (default 15)
- `flag_retrace_max`: Max retracement fraction (default 0.5)
- `volume_confirm`: Require volume confirmation (default True)

### 11. MA+ATR Mean Reversion — `ma_atr_mean_reversion(ma_period, atr_length, mean_period, entry_multiplier, exit_multiplier)`
Triple nested MA trend filter + ATR-scaled pullback entries.
- `ma_period`: SMA period for triple nesting (default 40)
- `atr_length`: ATR period (default 14)
- `mean_period`: Short-term mean period (default 5)
- `entry_multiplier`: ATR entry band multiplier (default 1.0)
- `exit_multiplier`: ATR exit band multiplier (default 0.5)

## Creating New Strategies

You can create new strategy functions following this pattern:

```python
def my_strategy(param1=default1, param2=default2):
    def strategy_fn(candles, position):
        # candles: list[Candle] — all bars up to current
        # position: dict | None — {'side': 'long', 'quantity': ..., ...}
        
        # Your logic here
        # Use helpers from pyhood.backtest.strategies:
        #   _calculate_ema, _calculate_sma, _calculate_rsi,
        #   _calculate_atr, _calculate_bollinger_bands
        
        return 'buy'   # Enter long
        return 'sell'   # Exit long
        return None     # Do nothing
    return strategy_fn
```

## Example Session

```python
from pyhood.autoresearch import AutoResearcher
from pyhood.backtest.strategies import ema_crossover, macd_crossover

r = AutoResearcher(ticker='SPY', total_period='10y')

# Sweep EMA crossover parameters
results = r.parameter_sweep(
    ema_crossover, 'fast', [5, 7, 9, 11, 13, 15],
    base_params={'slow': 21},
    strategy_name='EMA Crossover'
)

# Grid search MACD
results = r.multi_param_sweep(
    macd_crossover,
    {'fast': [8, 10, 12, 14], 'slow': [20, 24, 26, 30], 'signal': [7, 9, 11]},
    strategy_name='MACD'
)

# Validate the best findings on held-out data
validated = r.validate_best(n=3)

# Full report
r.report()

# Save for later
r.save('my_research.json')
```

## Logging Engine Limitations

If you want to test something but the backtesting engine doesn't support it, **don't skip it silently**. Log it to `autoresearch_limitations.md` in the working directory:

```markdown
## Limitation: [short description]
- **What I wanted to test:** [the idea]
- **What's missing:** [what the engine can't do]
- **Suggested fix:** [how the engine could be extended]
- **Priority:** [high/medium/low based on expected impact]
```

Examples of things you might hit:
- No commission/slippage modeling (results are too optimistic)
- No stop-loss/take-profit as engine features (only signal-based exits)
- No trailing stops
- No multi-asset or hedged strategies
- No intraday data (daily bars only)
- No short selling with borrowing costs
- Missing indicators (no VWAP, no order flow, no options Greeks)
- Can't size positions dynamically (always 100% in or 100% out)

This log is critical — it tells us exactly what to build next.

## Overnight Execution

The `OvernightRunner` automates the full strategy discovery program with crash resilience.

### Quick Start

```bash
python scripts/run_overnight.py
```

### Resume

Just run it again — it auto-detects previous state from `experiments.json`:

```bash
# Crashed at experiment 342? Just restart:
python scripts/run_overnight.py
# → "Resuming from experiment #342"
```

### CLI Options

```bash
python scripts/run_overnight.py \
  --ticker SPY \
  --period 10y \
  --results-dir autoresearch_results \
  --timeout 60 \
  --slippage 0.01
```

### Watchdog (Cron)

For truly unattended overnight runs, use the watchdog:

```bash
# Add to crontab — checks every 30 minutes, restarts if dead
crontab -e
*/30 * * * * /path/to/scripts/watchdog.sh
```

### Results Directory

After a run, find everything in `autoresearch_results/`:

| File | Contents |
|---|---|
| `experiments.json` | Full experiment log (machine-readable) |
| `errors.log` | Failed experiments with tracebacks |
| `summary.md` | Human-readable progress summary |
| `best_strategies.json` | Top strategies found so far |
| `run_log.txt` | Timestamped log of every action |
| `final_report.txt` | Full AutoResearcher report |

### Interpreting the Summary

- **Best train Sharpe / Best test Sharpe**: The best metric values found so far
- **Kept strategies**: Strategies that passed the train → test pipeline
- After the run, check `summary.md` for a quick overview
- For full details, read `final_report.txt`

### What It Tests

All 11 built-in strategies with full parameter grids (~632 combinations):
EMA Crossover, MACD, RSI Mean Reversion, RSI(2) Connors, Bollinger Breakout,
Donchian Breakout, MA+ATR Mean Reversion, Golden Cross, Keltner Squeeze,
Volume Confirmed Breakout, Bull Flag Breakout.

## Screening — Fundamental-Filtered Discovery

Use `StockScreener` to find candidates by fundamentals before running technical strategy sweeps.

### Quick Example

```python
from pyhood.autoresearch import AutoResearcher
from pyhood.screener import StockScreener

# Screen for undervalued growth stocks
screener = StockScreener('sp500')
tickers = screener.screen_for_autoresearch(
    filters={
        'pe_ratio': {'max': 25},
        'revenue_growth': {'min': 0.10},
        'market_cap': {'min': 10_000_000_000},
    },
    max_tickers=5,
    sort_by='revenue_growth',
)
# tickers → ['NVDA', 'AVGO', 'CRM', ...]
```

### Combined: Screen + Sweep

```python
researcher = AutoResearcher(ticker='SPY', total_period='10y')
results = researcher.run_with_screening(
    filters={'pe_ratio': {'max': 30}, 'revenue_growth': {'min': 0.05}},
    universe='sp500',
    max_tickers=5,
)
# results['tickers'] → screened tickers
# results['ranked'] → all experiments sorted by test Sharpe
```

### Fundamental Filter on Strategies

Wrap any strategy so it only trades tickers that pass fundamental checks:

```python
from pyhood.fundamentals import fundamental_filter
from pyhood.backtest.strategies import ema_crossover

strategy = fundamental_filter(
    ema_crossover(fast=9, slow=21),
    ticker='AAPL',
    filters={'pe_ratio': {'max': 30}, 'revenue_growth': {'min': 0.05}}
)
# If AAPL fails the filter, strategy always returns None (no trades)
```

### Available Universes

- `'sp500'` — Top ~100 S&P 500 stocks by market cap
- `'nasdaq100'` — Top ~90 Nasdaq 100 stocks
- Or pass a custom list: `['AAPL', 'MSFT', 'GOOGL']`

### Filter Syntax

```python
filters = {
    'pe_ratio': {'max': 25},          # PE ratio ≤ 25
    'revenue_growth': {'min': 0.10},   # Revenue growth ≥ 10%
    'market_cap': {'min': 1e9},        # Market cap ≥ $1B
    'beta': {'min': 0.5, 'max': 2.0},  # Beta between 0.5 and 2.0
}
```

Available filter properties: `pe_ratio`, `forward_pe`, `pb_ratio`, `debt_to_equity`, `revenue_growth`, `profit_margin`, `market_cap`, `beta`, `dividend_yield`, `insider_buy_pct`, `institutional_pct`, `short_ratio`, `earnings_growth`, `current_ratio`, `free_cash_flow`.

## Anti-Overfitting Checklist

Before declaring a strategy "found":

1. ☐ Train Sharpe > 0.8
2. ☐ Test Sharpe > 0.8
3. ☐ Train–Test gap < 30%
4. ☐ Validate Sharpe confirms (no big drop)
5. ☐ Minimum 10 trades in each split
6. ☐ Nearby parameters produce similar results (stability)
7. ☐ Strategy makes economic sense (not just noise fitting)
8. ☐ Profitable in ≥2 regimes (`regime_breakdown` check)
9. ☐ Not regime-dependent (no single regime contributes 80%+ of P&L)
10. ☐ `regime_report(result)` reviewed — no warning flags
11. ☐ Cross-validation passed on related tickers (Sharpe > 0.5, positive returns)
12. ☐ Strategy is not ticker-specific — generalises across at least 2 related instruments
