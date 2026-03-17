#!/usr/bin/env python3
"""Demo of the pyhood backtesting engine."""

from datetime import datetime, timedelta

from pyhood import Backtester
from pyhood.backtest import compare_backtests, rank_backtests
from pyhood.backtest.strategies import ema_crossover, rsi_mean_reversion, bollinger_breakout
from pyhood.models import Candle


def create_demo_data(symbol: str = "AAPL", days: int = 252) -> list[Candle]:
    """Create synthetic price data for demonstration."""
    candles = []
    price = 100.0
    base_date = datetime(2023, 1, 1)
    
    for i in range(days):
        # Simulate price movement with trend and volatility
        trend = 0.0005  # slight upward trend
        volatility = 0.02 * (i % 10 - 5) / 5  # cyclical volatility
        price *= (1 + trend + volatility)
        
        date_str = (base_date + timedelta(days=i)).isoformat() + "Z"
        candle = Candle(
            symbol=symbol,
            begins_at=date_str,
            open_price=price * 0.998,
            close_price=price,
            high_price=price * 1.015,
            low_price=price * 0.985,
            volume=1_000_000 + i * 1000
        )
        candles.append(candle)
    
    return candles


def main():
    """Run backtest demo."""
    print("🚀 pyhood Backtesting Engine Demo\n")
    
    # Create synthetic data
    candles = create_demo_data("AAPL", days=252)  # 1 year of data
    print(f"📊 Generated {len(candles)} days of synthetic AAPL data")
    print(f"   Price range: ${candles[0].close_price:.2f} → ${candles[-1].close_price:.2f}\n")
    
    # Initialize backtester
    backtester = Backtester(candles, initial_capital=10000.0)
    
    # Test different strategies
    strategies = [
        ("EMA Crossover (9/21)", ema_crossover(fast=9, slow=21)),
        ("RSI Mean Reversion", rsi_mean_reversion(period=14, oversold=30, overbought=70)),
        ("Bollinger Breakout", bollinger_breakout(period=20, std_dev=2.0)),
    ]
    
    results = []
    
    print("🔥 Running backtests...\n")
    
    for name, strategy in strategies:
        result = backtester.run(strategy, name)
        results.append(result)
        
        print(f"📈 {name}:")
        print(f"   Total Return: {result.total_return:.2f}%")
        print(f"   Annual Return: {result.annual_return:.2f}%") 
        print(f"   Sharpe Ratio: {result.sharpe_ratio:.2f}")
        print(f"   Max Drawdown: {result.max_drawdown:.2f}%")
        print(f"   Win Rate: {result.win_rate:.1f}%")
        print(f"   Total Trades: {result.total_trades}")
        print(f"   Alpha vs Buy-Hold: {result.alpha:.2f}%")
        print()
    
    # Compare strategies
    print("📋 Strategy Comparison:")
    print("=" * 100)
    print(compare_backtests(results))
    print()
    
    # Rank by Sharpe ratio
    ranked = rank_backtests(results, by="sharpe_ratio")
    print("🏆 Ranking by Sharpe Ratio:")
    for i, result in enumerate(ranked, 1):
        print(f"   {i}. {result.strategy_name} (Sharpe: {result.sharpe_ratio:.2f})")
    
    print("\n✅ Demo complete!")


if __name__ == "__main__":
    main()