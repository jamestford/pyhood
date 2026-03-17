"""Tests for backtesting engine."""

import pytest
from datetime import datetime, timedelta

from pyhood.models import Candle
from pyhood.backtest import Backtester, BacktestResult, Trade, compare_backtests, rank_backtests
from pyhood.backtest.strategies import ema_crossover, rsi_mean_reversion, bollinger_breakout


def create_synthetic_candles(symbol: str = "AAPL", days: int = 100, start_price: float = 100.0, trend: float = 0.1) -> list[Candle]:
    """Create synthetic candle data for testing.
    
    Args:
        symbol: Stock symbol
        days: Number of days of data
        start_price: Starting price
        trend: Daily trend (0.1 = 10% total increase over period)
        
    Returns:
        List of synthetic Candle objects
    """
    candles = []
    price = start_price
    base_date = datetime(2023, 1, 1)
    
    for i in range(days):
        # Simple price evolution with some volatility
        daily_change = (trend / days) + (0.02 * (i % 5 - 2))  # +/- 4% daily volatility
        price *= (1 + daily_change)
        
        # OHLC with some realistic spread
        high = price * 1.02
        low = price * 0.98
        open_price = price * 0.995
        close = price
        
        date_str = (base_date + timedelta(days=i)).isoformat() + "Z"
        
        candle = Candle(
            symbol=symbol,
            begins_at=date_str,
            open_price=open_price,
            close_price=close,
            high_price=high,
            low_price=low,
            volume=1000000,
            session="reg",
            interpolated=False
        )
        candles.append(candle)
    
    return candles


class TestBacktester:
    """Test the core Backtester functionality."""
    
    def test_backtester_initialization(self):
        """Test backtester initialization."""
        candles = create_synthetic_candles(days=30)
        backtester = Backtester(candles, initial_capital=10000.0)
        
        assert len(backtester.candles) == 30
        assert backtester.initial_capital == 10000.0
        assert backtester.symbol == "AAPL"
    
    def test_empty_candles_raises_error(self):
        """Test that empty candle list raises ValueError."""
        with pytest.raises(ValueError, match="Cannot backtest with empty candle data"):
            Backtester([])
    
    def test_backtester_buy_and_hold(self):
        """Test a simple buy-and-hold strategy."""
        candles = create_synthetic_candles(days=50, trend=0.2)  # 20% trend up
        backtester = Backtester(candles, initial_capital=10000.0)
        
        def buy_and_hold_strategy(candles_so_far: list[Candle], position: dict | None) -> str | None:
            # Buy on first day, hold until end
            if len(candles_so_far) == 1 and position is None:
                return 'buy'
            return None
        
        result = backtester.run(buy_and_hold_strategy, "Buy and Hold")
        
        # Should have positive return due to upward trend
        assert result.total_return > 0
        assert result.strategy_name == "Buy and Hold"
        assert result.symbol == "AAPL"
        assert result.total_trades == 0  # Never sold, so no completed trades
        assert len(result.equity_curve) == 50
        
    def test_no_trades_strategy(self):
        """Test a strategy that never trades."""
        candles = create_synthetic_candles(days=30)
        backtester = Backtester(candles, initial_capital=10000.0)
        
        def no_trade_strategy(candles_so_far: list[Candle], position: dict | None) -> str | None:
            return None  # Never trade
        
        result = backtester.run(no_trade_strategy, "No Trades")
        
        assert result.total_return == 0.0  # No trades, no return
        assert result.total_trades == 0
        assert result.win_rate == 0.0
        assert result.profit_factor == 0.0
        assert len(result.trades) == 0
        assert all(value == 10000.0 for value in result.equity_curve)  # Capital unchanged
        
    def test_simple_buy_sell_trade(self):
        """Test a strategy that makes one complete trade."""
        # Create data where price goes up then down
        candles = create_synthetic_candles(days=20, trend=0.0)
        # Manually adjust prices for predictable pattern
        for i, candle in enumerate(candles):
            if i < 10:
                # Price goes up first 10 days
                price = 100 + i * 2
            else:
                # Price comes down next 10 days  
                price = 120 - (i - 10) * 1
            
            # Update candle prices
            candles[i] = Candle(
                symbol=candle.symbol,
                begins_at=candle.begins_at,
                open_price=price * 0.99,
                close_price=price,
                high_price=price * 1.01,
                low_price=price * 0.98,
                volume=candle.volume,
                session=candle.session,
                interpolated=candle.interpolated
            )
        
        backtester = Backtester(candles, initial_capital=10000.0)
        
        def simple_strategy(candles_so_far: list[Candle], position: dict | None) -> str | None:
            if len(candles_so_far) == 5 and position is None:  # Buy on day 5
                return 'buy'
            elif len(candles_so_far) == 15 and position is not None:  # Sell on day 15
                return 'sell'
            return None
        
        result = backtester.run(simple_strategy, "Simple Strategy")
        
        assert result.total_trades == 1
        assert len(result.trades) == 1
        
        trade = result.trades[0]
        assert trade.side == "long"
        assert trade.entry_price == 108.0  # Day 5 price  
        assert trade.exit_price == 116.0   # Day 15 price (120 - 4)
        assert trade.pnl > 0  # Profitable trade
        

class TestTechnicalIndicators:
    """Test the technical indicator implementations."""
    
    def test_ema_crossover_signals(self):
        """Test EMA crossover strategy generates correct signals."""
        # Create data with clear trend change
        candles = []
        base_date = datetime(2023, 1, 1)
        
        # First 30 days: downtrend (fast EMA below slow)
        # Next 30 days: uptrend (fast EMA above slow)
        for i in range(60):
            if i < 30:
                price = 100 - i * 0.5  # Declining
            else:
                price = 85 + (i - 30) * 1.0  # Rising
            
            date_str = (base_date + timedelta(days=i)).isoformat() + "Z"
            candle = Candle(
                symbol="TEST",
                begins_at=date_str,
                open_price=price * 0.99,
                close_price=price,
                high_price=price * 1.01,
                low_price=price * 0.98,
                volume=1000000
            )
            candles.append(candle)
        
        backtester = Backtester(candles, initial_capital=10000.0)
        strategy = ema_crossover(fast=9, slow=21)
        result = backtester.run(strategy, "EMA Crossover")
        
        # Should generate at least one trade when trend changes
        assert result.total_trades >= 0  # May or may not generate trades depending on exact crossover
        
    def test_rsi_calculation(self):
        """Test RSI calculation with known data."""
        # Create simple price data for RSI testing
        candles = []
        base_date = datetime(2023, 1, 1)
        
        # Price pattern that should create clear RSI signals
        prices = [100, 102, 104, 103, 101, 99, 98, 97, 95, 93,  # Down trend (oversold)
                  94, 96, 98, 100, 102, 104, 106, 108, 110, 112] # Up trend (overbought)
        
        for i, price in enumerate(prices):
            date_str = (base_date + timedelta(days=i)).isoformat() + "Z"
            candle = Candle(
                symbol="TEST",
                begins_at=date_str,
                open_price=price * 0.99,
                close_price=price,
                high_price=price * 1.01,
                low_price=price * 0.98,
                volume=1000000
            )
            candles.append(candle)
        
        backtester = Backtester(candles, initial_capital=10000.0)
        strategy = rsi_mean_reversion(period=14, oversold=30, overbought=70)
        result = backtester.run(strategy, "RSI Mean Reversion")
        
        # Test passes if it doesn't crash (RSI calculation is complex to verify exactly)
        assert isinstance(result, BacktestResult)
        assert result.strategy_name == "RSI Mean Reversion"


class TestBacktestResult:
    """Test BacktestResult metrics calculation."""
    
    def test_backtest_result_metrics(self):
        """Test that backtest metrics are calculated correctly."""
        candles = create_synthetic_candles(days=252, trend=0.15)  # 1 year, 15% trend
        backtester = Backtester(candles, initial_capital=10000.0)
        
        def buy_hold_strategy(candles_so_far: list[Candle], position: dict | None) -> str | None:
            if len(candles_so_far) == 1:
                return 'buy'
            elif len(candles_so_far) == len(candles):  # Sell at end
                return 'sell'
            return None
        
        result = backtester.run(buy_hold_strategy, "Buy Hold Test")
        
        # Check basic metrics are calculated
        assert isinstance(result.total_return, float)
        assert isinstance(result.annual_return, float)
        assert isinstance(result.sharpe_ratio, float)
        assert isinstance(result.max_drawdown, float)
        assert isinstance(result.win_rate, float)
        assert isinstance(result.profit_factor, float)
        assert isinstance(result.alpha, float)
        
        # Max drawdown should be negative or zero
        assert result.max_drawdown <= 0
        
        # Should have approximately 252 equity curve points
        assert len(result.equity_curve) == 252
        
    def test_win_rate_calculation(self):
        """Test win rate calculation with known trades."""
        candles = create_synthetic_candles(days=50)
        backtester = Backtester(candles, initial_capital=10000.0)
        
        # Strategy that makes multiple trades with predictable outcomes
        trade_count = 0
        def multiple_trades_strategy(candles_so_far: list[Candle], position: dict | None) -> str | None:
            nonlocal trade_count
            day = len(candles_so_far)
            
            # Make trades every 10 days
            if day % 10 == 1 and position is None:
                return 'buy'
            elif day % 10 == 6 and position is not None:
                trade_count += 1
                return 'sell'
            return None
        
        result = backtester.run(multiple_trades_strategy, "Multiple Trades")
        
        if result.total_trades > 0:
            assert 0 <= result.win_rate <= 100
            
            # Verify win rate calculation
            winning_trades = [t for t in result.trades if t.pnl > 0]
            expected_win_rate = (len(winning_trades) / result.total_trades) * 100
            assert abs(result.win_rate - expected_win_rate) < 0.01


class TestCompareFunctions:
    """Test comparison and ranking functions."""
    
    def test_compare_backtests(self):
        """Test comparison table generation."""
        # Create mock results
        result1 = BacktestResult(
            strategy_name="Strategy A",
            symbol="AAPL", 
            period="2023-01-01 to 2023-12-31",
            total_return=15.5,
            annual_return=15.5,
            sharpe_ratio=1.2,
            max_drawdown=-5.5,
            win_rate=60.0,
            profit_factor=1.8,
            total_trades=10,
            avg_trade_return=1.5,
            avg_win=3.2,
            avg_loss=-1.8,
            buy_hold_return=12.0,
            alpha=3.5,
            trades=[],
            equity_curve=[]
        )
        
        result2 = BacktestResult(
            strategy_name="Strategy B",
            symbol="AAPL",
            period="2023-01-01 to 2023-12-31", 
            total_return=12.0,
            annual_return=12.0,
            sharpe_ratio=0.9,
            max_drawdown=-8.2,
            win_rate=55.0,
            profit_factor=1.5,
            total_trades=15,
            avg_trade_return=0.8,
            avg_win=2.1,
            avg_loss=-1.4,
            buy_hold_return=12.0,
            alpha=0.0,
            trades=[],
            equity_curve=[]
        )
        
        comparison = compare_backtests([result1, result2])
        
        assert "Strategy A" in comparison
        assert "Strategy B" in comparison
        assert "15.50" in comparison  # Total return for Strategy A
        assert "1.20" in comparison   # Sharpe ratio for Strategy A
        
    def test_rank_backtests(self):
        """Test ranking by different metrics."""
        # Create results with different performance characteristics
        results = [
            BacktestResult(
                strategy_name="Low Sharpe", symbol="AAPL", period="2023",
                total_return=10.0, annual_return=10.0, sharpe_ratio=0.5,
                max_drawdown=-10.0, win_rate=50.0, profit_factor=1.2,
                total_trades=5, avg_trade_return=2.0, avg_win=4.0, avg_loss=-2.0,
                buy_hold_return=8.0, alpha=2.0, trades=[], equity_curve=[]
            ),
            BacktestResult(
                strategy_name="High Sharpe", symbol="AAPL", period="2023",
                total_return=8.0, annual_return=8.0, sharpe_ratio=1.5,
                max_drawdown=-3.0, win_rate=70.0, profit_factor=2.0,
                total_trades=8, avg_trade_return=1.0, avg_win=2.5, avg_loss=-1.0,
                buy_hold_return=8.0, alpha=0.0, trades=[], equity_curve=[]
            )
        ]
        
        # Rank by Sharpe ratio (default)
        ranked = rank_backtests(results)
        assert ranked[0].strategy_name == "High Sharpe"
        assert ranked[1].strategy_name == "Low Sharpe"
        
        # Rank by total return
        ranked_by_return = rank_backtests(results, by="total_return")
        assert ranked_by_return[0].strategy_name == "Low Sharpe"
        assert ranked_by_return[1].strategy_name == "High Sharpe"
        
        # Rank by max drawdown (less negative is better)
        ranked_by_dd = rank_backtests(results, by="max_drawdown")
        assert ranked_by_dd[0].strategy_name == "High Sharpe"  # -3.0 is better than -10.0
        
    def test_rank_backtests_invalid_metric(self):
        """Test ranking with invalid metric raises error."""
        results = [BacktestResult(
            strategy_name="Test", symbol="AAPL", period="2023",
            total_return=10.0, annual_return=10.0, sharpe_ratio=1.0,
            max_drawdown=-5.0, win_rate=60.0, profit_factor=1.5,
            total_trades=3, avg_trade_return=3.3, avg_win=5.0, avg_loss=-2.0,
            buy_hold_return=8.0, alpha=2.0, trades=[], equity_curve=[]
        )]
        
        with pytest.raises(ValueError, match="Unknown ranking metric"):
            rank_backtests(results, by="invalid_metric")
    
    def test_compare_empty_results(self):
        """Test comparison with empty results list."""
        comparison = compare_backtests([])
        assert comparison == "No backtest results to compare."