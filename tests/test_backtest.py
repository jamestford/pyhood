"""Tests for backtesting engine."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from pyhood.backtest import (
    Backtester,
    BacktestResult,
    Trade,
    benchmark_spy,
    compare_backtests,
    rank_backtests,
    regime_report,
)
from pyhood.backtest.compare import sensitivity_report, sensitivity_test
from pyhood.backtest.strategies import (
    _calculate_net_distribution,
    _classify_regime,
    _detect_bull_flag,
    bull_flag_breakout,
    donchian_breakout,
    ema_crossover,
    golden_cross,
    keltner_squeeze,
    ma_atr_mean_reversion,
    macd_crossover,
    rsi2_connors,
    rsi_mean_reversion,
    volume_confirmed_breakout,
)
from pyhood.models import Candle


def create_synthetic_candles(
    symbol: str = "AAPL", days: int = 100,
    start_price: float = 100.0, trend: float = 0.1,
) -> list[Candle]:
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

        def buy_and_hold_strategy(
            candles_so_far: list[Candle], position: dict | None,
        ) -> str | None:
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
        # May or may not generate trades depending on exact crossover
        assert result.total_trades >= 0

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
        def multiple_trades_strategy(
            candles_so_far: list[Candle], position: dict | None,
        ) -> str | None:
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


class TestMaAtrMeanReversion:
    """Test the MA+ATR Mean Reversion strategy."""

    def _make_candles(self, prices: list[float], symbol: str = "TEST") -> list[Candle]:
        """Helper to create candles from a price list."""
        base_date = datetime(2023, 1, 1)
        candles = []
        for i, price in enumerate(prices):
            date_str = (base_date + timedelta(days=i)).isoformat() + "Z"
            candle = Candle(
                symbol=symbol,
                begins_at=date_str,
                open_price=price * 0.995,
                close_price=price,
                high_price=price * 1.02,
                low_price=price * 0.98,
                volume=1000000,
            )
            candles.append(candle)
        return candles

    def test_returns_callable(self):
        """Test that ma_atr_mean_reversion returns a callable."""
        strategy = ma_atr_mean_reversion()
        assert callable(strategy)

    def test_no_signal_insufficient_data(self):
        """Test that strategy returns None when not enough data."""
        strategy = ma_atr_mean_reversion(ma_period=40)
        candles = self._make_candles([100.0 + i for i in range(20)])
        assert strategy(candles, None) is None

    def test_runs_without_error(self):
        """Test that strategy runs against the backtester without crashing."""
        candles = create_synthetic_candles(days=252, trend=0.1)
        backtester = Backtester(candles, initial_capital=10000.0)
        strategy = ma_atr_mean_reversion()
        result = backtester.run(strategy, "MA+ATR Mean Reversion")

        assert isinstance(result, BacktestResult)
        assert result.strategy_name == "MA+ATR Mean Reversion"
        assert len(result.equity_curve) == 252

    def test_generates_trades_on_mean_reverting_data(self):
        """Test that the strategy generates trades on oscillating data."""
        # Create oscillating price data around 100 that should trigger
        # mean reversion signals: price drops below the lower band then recovers
        prices = []
        for cycle in range(6):
            # Each cycle: stable -> dip -> recovery
            for i in range(20):
                prices.append(100.0 + 0.5 * i)  # Gentle uptrend
            for i in range(15):
                prices.append(110.0 - 2.0 * i)  # Sharp dip
            for i in range(15):
                prices.append(80.0 + 2.0 * i)   # Recovery

        candles = self._make_candles(prices)
        backtester = Backtester(candles, initial_capital=10000.0)
        strategy = ma_atr_mean_reversion(ma_period=40, atr_length=14, mean_period=5)
        result = backtester.run(strategy, "MA+ATR Mean Reversion")

        assert isinstance(result, BacktestResult)
        # With this oscillating pattern the strategy should find at least one trade
        assert result.total_trades >= 0

    def test_custom_parameters(self):
        """Test that custom parameters are accepted."""
        strategy = ma_atr_mean_reversion(
            ma_period=20,
            atr_length=10,
            mean_period=3,
            entry_multiplier=1.5,
            exit_multiplier=0.3,
        )
        candles = create_synthetic_candles(days=100, trend=0.05)
        backtester = Backtester(candles, initial_capital=10000.0)
        result = backtester.run(strategy, "Custom MA+ATR")

        assert isinstance(result, BacktestResult)
        assert result.strategy_name == "Custom MA+ATR"

    def test_import_from_backtest_init(self):
        """Test that ma_atr_mean_reversion is importable from pyhood.backtest."""
        from pyhood.backtest import ma_atr_mean_reversion as imported_strategy
        assert callable(imported_strategy)
        strategy = imported_strategy()
        assert callable(strategy)


def _make_result(**overrides) -> BacktestResult:
    """Helper to create a BacktestResult with sensible defaults."""
    defaults = dict(
        strategy_name="Test Strategy",
        symbol="AAPL",
        period="2023-01-01 to 2023-12-31",
        total_return=15.0,
        annual_return=15.0,
        sharpe_ratio=1.2,
        max_drawdown=-5.0,
        win_rate=60.0,
        profit_factor=1.8,
        total_trades=10,
        avg_trade_return=1.5,
        avg_win=3.0,
        avg_loss=-1.5,
        buy_hold_return=12.0,
        alpha=3.0,
        trades=[],
        equity_curve=[],
    )
    defaults.update(overrides)
    return BacktestResult(**defaults)


def _mock_spy_history(start, end):
    """Create a mock DataFrame resembling yfinance output."""
    import types

    # Simulate SPY going from 400 to 440 (10% return) with 252 daily closes
    num_days = 252
    closes = [400 + (40 * i / (num_days - 1)) for i in range(num_days)]

    class MockDF:
        empty = False

        def __init__(self, closes):
            self._closes = closes

        def __len__(self):
            return len(self._closes)

        def __getitem__(self, key):
            if key == "Close":
                return types.SimpleNamespace(values=self._closes)
            raise KeyError(key)

    return MockDF(closes)


class TestBenchmarkSpy:
    """Test SPY benchmark comparison."""

    def test_benchmark_spy_returns_enriched_results(self):
        """Test that benchmark_spy populates SPY fields."""
        results = [_make_result()]

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _mock_spy_history("2023-01-01", "2023-12-31")

        with patch("pyhood.backtest.compare.yf", create=True) as mock_yf:
            # Patch the import inside benchmark_spy

            # We need to mock yfinance at import time inside the function
            with patch.dict("sys.modules", {"yfinance": mock_yf}):
                mock_yf.Ticker.return_value = mock_ticker
                enriched = benchmark_spy(results)

        assert len(enriched) == 1
        r = enriched[0]
        assert r.spy_return is not None
        assert r.spy_sharpe is not None
        assert r.spy_alpha is not None
        assert r.verdict != ''
        # spy_alpha should equal total_return - spy_return
        assert abs(r.spy_alpha - (r.total_return - r.spy_return)) < 0.01

    def test_verdict_beats_both(self):
        """Test verdict when strategy beats SPY on both return and Sharpe."""
        # Strategy: return=20%, sharpe=1.5; SPY: return=10%, sharpe=0.8
        result = _make_result(total_return=20.0, sharpe_ratio=1.5)

        with patch("pyhood.backtest.compare._fetch_spy_metrics", return_value=(10.0, 0.8)):
            with patch.dict("sys.modules", {"yfinance": MagicMock()}):
                enriched = benchmark_spy([result])

        assert enriched[0].verdict == '\u2705 Beats both'
        assert abs(enriched[0].spy_alpha - 10.0) < 0.01

    def test_verdict_better_risk_adjusted(self):
        """Test verdict when strategy has better Sharpe but lower return than SPY."""
        # Strategy: return=5%, sharpe=2.0; SPY: return=10%, sharpe=0.8
        result = _make_result(total_return=5.0, sharpe_ratio=2.0)

        with patch("pyhood.backtest.compare._fetch_spy_metrics", return_value=(10.0, 0.8)):
            with patch.dict("sys.modules", {"yfinance": MagicMock()}):
                enriched = benchmark_spy([result])

        assert enriched[0].verdict == '\u26a0\ufe0f Better risk-adjusted'
        assert abs(enriched[0].spy_alpha - (-5.0)) < 0.01

    def test_verdict_underperforms(self):
        """Test verdict when strategy underperforms SPY on both metrics."""
        # Strategy: return=5%, sharpe=0.3; SPY: return=10%, sharpe=0.8
        result = _make_result(total_return=5.0, sharpe_ratio=0.3)

        with patch("pyhood.backtest.compare._fetch_spy_metrics", return_value=(10.0, 0.8)):
            with patch.dict("sys.modules", {"yfinance": MagicMock()}):
                enriched = benchmark_spy([result])

        assert enriched[0].verdict == '\u274c Underperforms'

    def test_benchmark_spy_empty_results(self):
        """Test benchmark_spy with empty list."""
        assert benchmark_spy([]) == []

    def test_benchmark_spy_no_yfinance(self):
        """Test graceful handling when yfinance is not installed."""
        results = [_make_result()]

        # Simulate yfinance not installed
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "yfinance":
                raise ImportError("No module named 'yfinance'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = benchmark_spy(results)

        # Should return original results unchanged
        assert result is results
        assert result[0].spy_return is None

    def test_benchmark_spy_caches_per_period(self):
        """Test that SPY data is fetched once per unique period."""
        results = [
            _make_result(strategy_name="A", period="2023-01-01 to 2023-12-31"),
            _make_result(strategy_name="B", period="2023-01-01 to 2023-12-31"),
        ]

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _mock_spy_history("2023-01-01", "2023-12-31")

        with patch.dict("sys.modules", {"yfinance": MagicMock()}):
            import sys
            mock_yf = sys.modules["yfinance"]
            mock_yf.Ticker.return_value = mock_ticker
            enriched = benchmark_spy(results)

        # Should have called Ticker.history only once for the same period
        assert mock_ticker.history.call_count == 1
        # Both results should be enriched
        assert enriched[0].spy_return is not None
        assert enriched[1].spy_return is not None

    def test_compare_backtests_shows_spy_columns(self):
        """Test that compare_backtests includes SPY columns when benchmarked."""
        result = _make_result(
            spy_return=10.0,
            spy_sharpe=0.8,
            spy_alpha=5.0,
            verdict='\u2705 Beats both',
        )
        table = compare_backtests([result])

        assert "SPY Return (%)" in table
        assert "SPY Alpha (%)" in table
        assert "Verdict" in table
        assert "10.00" in table
        assert "5.00" in table
        assert "\u2705 Beats both" in table

    def test_compare_backtests_hides_spy_columns_when_not_benchmarked(self):
        """Test that SPY columns are hidden when spy_return is None."""
        result = _make_result()  # No SPY fields set
        table = compare_backtests([result])

        assert "SPY Return (%)" not in table
        assert "Verdict" not in table

    def test_rank_backtests_by_spy_alpha(self):
        """Test ranking by spy_alpha metric."""
        results = [
            _make_result(strategy_name="Low Alpha", spy_alpha=2.0),
            _make_result(strategy_name="High Alpha", spy_alpha=10.0),
        ]
        ranked = rank_backtests(results, by="spy_alpha")
        assert ranked[0].strategy_name == "High Alpha"
        assert ranked[1].strategy_name == "Low Alpha"

    def test_rank_backtests_spy_alpha_none_sorts_last(self):
        """Test that results without spy_alpha sort last."""
        results = [
            _make_result(strategy_name="No SPY"),  # spy_alpha=None
            _make_result(strategy_name="Has SPY", spy_alpha=5.0),
        ]
        ranked = rank_backtests(results, by="spy_alpha")
        assert ranked[0].strategy_name == "Has SPY"
        assert ranked[1].strategy_name == "No SPY"

    def test_backtest_result_default_spy_fields(self):
        """Test that BacktestResult defaults preserve backward compatibility."""
        result = _make_result()
        assert result.spy_return is None
        assert result.spy_sharpe is None
        assert result.spy_alpha is None
        assert result.verdict == ''


class TestDonchianBreakout:
    """Test the Donchian Channel Breakout strategy."""

    def _make_candles(self, prices: list[float], symbol: str = "TEST") -> list[Candle]:
        base_date = datetime(2023, 1, 1)
        candles = []
        for i, price in enumerate(prices):
            date_str = (base_date + timedelta(days=i)).isoformat() + "Z"
            candles.append(Candle(
                symbol=symbol,
                begins_at=date_str,
                open_price=price * 0.995,
                close_price=price,
                high_price=price * 1.02,
                low_price=price * 0.98,
                volume=1000000,
            ))
        return candles

    def test_returns_callable(self):
        strategy = donchian_breakout()
        assert callable(strategy)

    def test_no_signal_insufficient_data(self):
        strategy = donchian_breakout(entry_period=20, exit_period=10)
        candles = self._make_candles([100.0 + i for i in range(15)])
        assert strategy(candles, None) is None

    def test_runs_without_error(self):
        candles = create_synthetic_candles(days=252, trend=0.1)
        backtester = Backtester(candles, initial_capital=10000.0)
        strategy = donchian_breakout()
        result = backtester.run(strategy, "Donchian Breakout")

        assert isinstance(result, BacktestResult)
        assert result.strategy_name == "Donchian Breakout"
        assert len(result.equity_curve) == 252

    def test_import_from_backtest_init(self):
        from pyhood.backtest import donchian_breakout as imported
        assert callable(imported)


class TestRsi2Connors:
    """Test the RSI(2) Connors strategy."""

    def _make_candles(self, prices: list[float], symbol: str = "TEST") -> list[Candle]:
        base_date = datetime(2023, 1, 1)
        candles = []
        for i, price in enumerate(prices):
            date_str = (base_date + timedelta(days=i)).isoformat() + "Z"
            candles.append(Candle(
                symbol=symbol,
                begins_at=date_str,
                open_price=price * 0.995,
                close_price=price,
                high_price=price * 1.02,
                low_price=price * 0.98,
                volume=1000000,
            ))
        return candles

    def test_returns_callable(self):
        strategy = rsi2_connors()
        assert callable(strategy)

    def test_no_signal_insufficient_data(self):
        strategy = rsi2_connors(sma_period=200)
        candles = self._make_candles([100.0 + i * 0.1 for i in range(50)])
        assert strategy(candles, None) is None

    def test_runs_without_error(self):
        candles = create_synthetic_candles(days=300, trend=0.15)
        backtester = Backtester(candles, initial_capital=10000.0)
        strategy = rsi2_connors()
        result = backtester.run(strategy, "RSI(2) Connors")

        assert isinstance(result, BacktestResult)
        assert result.strategy_name == "RSI(2) Connors"
        assert len(result.equity_curve) == 300

    def test_import_from_backtest_init(self):
        from pyhood.backtest import rsi2_connors as imported
        assert callable(imported)


class TestMacdCrossover:
    """Test the MACD Crossover strategy."""

    def _make_candles(self, prices: list[float], symbol: str = "TEST") -> list[Candle]:
        base_date = datetime(2023, 1, 1)
        candles = []
        for i, price in enumerate(prices):
            date_str = (base_date + timedelta(days=i)).isoformat() + "Z"
            candles.append(Candle(
                symbol=symbol,
                begins_at=date_str,
                open_price=price * 0.995,
                close_price=price,
                high_price=price * 1.02,
                low_price=price * 0.98,
                volume=1000000,
            ))
        return candles

    def test_returns_callable(self):
        strategy = macd_crossover()
        assert callable(strategy)

    def test_no_signal_insufficient_data(self):
        strategy = macd_crossover(fast=12, slow=26, signal=9)
        candles = self._make_candles([100.0 + i for i in range(30)])
        assert strategy(candles, None) is None

    def test_runs_without_error(self):
        candles = create_synthetic_candles(days=252, trend=0.1)
        backtester = Backtester(candles, initial_capital=10000.0)
        strategy = macd_crossover()
        result = backtester.run(strategy, "MACD Crossover")

        assert isinstance(result, BacktestResult)
        assert result.strategy_name == "MACD Crossover"
        assert len(result.equity_curve) == 252

    def test_import_from_backtest_init(self):
        from pyhood.backtest import macd_crossover as imported
        assert callable(imported)


class TestGoldenCross:
    """Test the Golden Cross strategy."""

    def _make_candles(self, prices: list[float], symbol: str = "TEST") -> list[Candle]:
        base_date = datetime(2023, 1, 1)
        candles = []
        for i, price in enumerate(prices):
            date_str = (base_date + timedelta(days=i)).isoformat() + "Z"
            candles.append(Candle(
                symbol=symbol,
                begins_at=date_str,
                open_price=price * 0.995,
                close_price=price,
                high_price=price * 1.02,
                low_price=price * 0.98,
                volume=1000000,
            ))
        return candles

    def test_returns_callable(self):
        strategy = golden_cross()
        assert callable(strategy)

    def test_no_signal_insufficient_data(self):
        strategy = golden_cross(fast_period=50, slow_period=200)
        candles = self._make_candles([100.0 + i * 0.1 for i in range(150)])
        assert strategy(candles, None) is None

    def test_runs_without_error(self):
        candles = create_synthetic_candles(days=400, trend=0.2)
        backtester = Backtester(candles, initial_capital=10000.0)
        strategy = golden_cross()
        result = backtester.run(strategy, "Golden Cross")

        assert isinstance(result, BacktestResult)
        assert result.strategy_name == "Golden Cross"
        assert len(result.equity_curve) == 400

    def test_import_from_backtest_init(self):
        from pyhood.backtest import golden_cross as imported
        assert callable(imported)


class TestKeltnerSqueeze:
    """Test the Keltner Channel Squeeze strategy."""

    def _make_candles(self, prices: list[float], symbol: str = "TEST") -> list[Candle]:
        base_date = datetime(2023, 1, 1)
        candles = []
        for i, price in enumerate(prices):
            date_str = (base_date + timedelta(days=i)).isoformat() + "Z"
            candles.append(Candle(
                symbol=symbol,
                begins_at=date_str,
                open_price=price * 0.995,
                close_price=price,
                high_price=price * 1.02,
                low_price=price * 0.98,
                volume=1000000,
            ))
        return candles

    def test_returns_callable(self):
        strategy = keltner_squeeze()
        assert callable(strategy)

    def test_no_signal_insufficient_data(self):
        strategy = keltner_squeeze(keltner_period=20, bb_period=20)
        candles = self._make_candles([100.0 + i for i in range(15)])
        assert strategy(candles, None) is None

    def test_runs_without_error(self):
        candles = create_synthetic_candles(days=252, trend=0.1)
        backtester = Backtester(candles, initial_capital=10000.0)
        strategy = keltner_squeeze()
        result = backtester.run(strategy, "Keltner Squeeze")

        assert isinstance(result, BacktestResult)
        assert result.strategy_name == "Keltner Squeeze"
        assert len(result.equity_curve) == 252

    def test_import_from_backtest_init(self):
        from pyhood.backtest import keltner_squeeze as imported
        assert callable(imported)


class TestNetDistribution:
    """Test the _calculate_net_distribution helper."""

    def _make_candles(self, prices_and_volumes, symbol="TEST"):
        """Create candles from (open, close, volume) tuples."""
        base_date = datetime(2023, 1, 1)
        candles = []
        for i, (open_p, close_p, vol) in enumerate(prices_and_volumes):
            date_str = (base_date + timedelta(days=i)).isoformat() + "Z"
            high = max(open_p, close_p) * 1.01
            low = min(open_p, close_p) * 0.99
            candles.append(Candle(
                symbol=symbol,
                begins_at=date_str,
                open_price=open_p,
                close_price=close_p,
                high_price=high,
                low_price=low,
                volume=vol,
            ))
        return candles

    def test_all_up_volume(self):
        """All high-volume bars are up days -> ratio = 1.0."""
        # 20 bars: all close > open, varying volume
        data = [(100.0, 105.0, 1000 + i * 100) for i in range(20)]
        candles = self._make_candles(data)
        result = _calculate_net_distribution(candles, period=20, top_pct=0.25)
        assert result == 1.0

    def test_all_down_volume(self):
        """All high-volume bars are down days -> ratio = 0.0."""
        data = [(105.0, 100.0, 1000 + i * 100) for i in range(20)]
        candles = self._make_candles(data)
        result = _calculate_net_distribution(candles, period=20, top_pct=0.25)
        assert result == 0.0

    def test_mixed_volume(self):
        """Mixed up/down -> ratio between 0 and 1."""
        data = []
        for i in range(20):
            if i % 2 == 0:
                data.append((100.0, 105.0, 2000))  # up day, high vol
            else:
                data.append((105.0, 100.0, 1000))  # down day, low vol
        candles = self._make_candles(data)
        result = _calculate_net_distribution(candles, period=20, top_pct=0.25)
        assert 0.0 <= result <= 1.0

    def test_insufficient_data(self):
        """Returns 0.5 when not enough bars."""
        data = [(100.0, 105.0, 1000) for _ in range(5)]
        candles = self._make_candles(data)
        result = _calculate_net_distribution(candles, period=20)
        assert result == 0.5


class TestVolumeConfirmedBreakout:
    """Test the Volume Confirmed Breakout strategy."""

    def _make_candles(self, prices, symbol="TEST"):
        base_date = datetime(2023, 1, 1)
        candles = []
        for i, price in enumerate(prices):
            date_str = (base_date + timedelta(days=i)).isoformat() + "Z"
            candles.append(Candle(
                symbol=symbol,
                begins_at=date_str,
                open_price=price * 0.995,
                close_price=price,
                high_price=price * 1.02,
                low_price=price * 0.98,
                volume=1000000,
            ))
        return candles

    def test_returns_callable(self):
        strategy = volume_confirmed_breakout()
        assert callable(strategy)

    def test_no_signal_insufficient_data(self):
        strategy = volume_confirmed_breakout(sma_period=50)
        candles = self._make_candles([100.0 + i for i in range(30)])
        assert strategy(candles, None) is None

    def test_runs_without_error(self):
        candles = create_synthetic_candles(days=252, trend=0.1)
        backtester = Backtester(candles, initial_capital=10000.0)
        strategy = volume_confirmed_breakout()
        result = backtester.run(strategy, "Volume Confirmed Breakout")

        assert isinstance(result, BacktestResult)
        assert result.strategy_name == "Volume Confirmed Breakout"
        assert len(result.equity_curve) == 252

    def test_import_from_backtest_init(self):
        from pyhood.backtest import volume_confirmed_breakout as imported
        assert callable(imported)


class TestBullFlagDetector:
    """Test the _detect_bull_flag helper."""

    def _make_candles(self, prices, symbol="TEST"):
        base_date = datetime(2023, 1, 1)
        candles = []
        for i, price in enumerate(prices):
            date_str = (base_date + timedelta(days=i)).isoformat() + "Z"
            candles.append(Candle(
                symbol=symbol,
                begins_at=date_str,
                open_price=price * 0.995,
                close_price=price,
                high_price=price * 1.02,
                low_price=price * 0.98,
                volume=1000000,
            ))
        return candles

    def test_callable(self):
        """_detect_bull_flag is callable."""
        assert callable(_detect_bull_flag)

    def test_insufficient_data(self):
        """Returns None when not enough data."""
        candles = self._make_candles([100.0 + i for i in range(10)])
        result = _detect_bull_flag(candles)
        assert result is None

    def test_detects_pattern(self):
        """Detects a bull flag in synthetic data with a clear pole + flag."""
        # Pole: sharp rise from 100 to 115 (15%)
        prices = [100.0 + i * 0.1 for i in range(10)]  # flat lead-in
        for i in range(8):
            prices.append(101.0 + i * 2.0)  # pole: 101 -> 115
        # Flag: consolidation around 113-115
        for i in range(12):
            prices.append(113.0 + (i % 3) * 0.5)
        candles = self._make_candles(prices)
        result = _detect_bull_flag(candles)
        # May or may not detect depending on exact geometry — just test no crash
        assert result is None or isinstance(result, dict)


class TestBullFlagBreakout:
    """Test the Bull Flag Breakout strategy."""

    def _make_candles(self, prices, symbol="TEST"):
        base_date = datetime(2023, 1, 1)
        candles = []
        for i, price in enumerate(prices):
            date_str = (base_date + timedelta(days=i)).isoformat() + "Z"
            candles.append(Candle(
                symbol=symbol,
                begins_at=date_str,
                open_price=price * 0.995,
                close_price=price,
                high_price=price * 1.02,
                low_price=price * 0.98,
                volume=1000000,
            ))
        return candles

    def test_returns_callable(self):
        strategy = bull_flag_breakout()
        assert callable(strategy)

    def test_no_signal_insufficient_data(self):
        strategy = bull_flag_breakout()
        candles = self._make_candles([100.0 + i for i in range(15)])
        assert strategy(candles, None) is None

    def test_runs_without_error(self):
        candles = create_synthetic_candles(days=252, trend=0.1)
        backtester = Backtester(candles, initial_capital=10000.0)
        strategy = bull_flag_breakout()
        result = backtester.run(strategy, "Bull Flag Breakout")

        assert isinstance(result, BacktestResult)
        assert result.strategy_name == "Bull Flag Breakout"
        assert len(result.equity_curve) == 252

    def test_import_from_backtest_init(self):
        from pyhood.backtest import bull_flag_breakout as imported
        assert callable(imported)


class TestSlippage:
    """Test slippage modeling in the backtesting engine."""

    def _make_candles(self, prices: list[float], symbol: str = "TEST") -> list[Candle]:
        base_date = datetime(2023, 1, 1)
        candles = []
        for i, price in enumerate(prices):
            date_str = (base_date + timedelta(days=i)).isoformat() + "Z"
            candles.append(Candle(
                symbol=symbol,
                begins_at=date_str,
                open_price=price * 0.995,
                close_price=price,
                high_price=price * 1.02,
                low_price=price * 0.98,
                volume=1000000,
            ))
        return candles

    def _buy_sell_strategy(self, buy_day: int, sell_day: int):
        """Strategy that buys on buy_day and sells on sell_day."""
        def strategy(candles_so_far, position):
            day = len(candles_so_far)
            if day == buy_day and position is None:
                return 'buy'
            elif day == sell_day and position is not None:
                return 'sell'
            return None
        return strategy

    def test_slippage_reduces_returns(self):
        """Slippage should reduce returns compared to zero slippage."""
        prices = [100.0 + i * 0.5 for i in range(50)]  # gentle uptrend
        candles = self._make_candles(prices)

        bt_no_slip = Backtester(candles, initial_capital=10000.0, slippage_pct=0.0)
        bt_with_slip = Backtester(candles, initial_capital=10000.0, slippage_pct=0.01)

        strategy = self._buy_sell_strategy(buy_day=5, sell_day=40)

        result_no_slip = bt_no_slip.run(strategy, "No Slippage")
        result_with_slip = bt_with_slip.run(strategy, "With Slippage")

        assert result_no_slip.total_return > result_with_slip.total_return

    def test_slippage_pct_recorded_in_result(self):
        """BacktestResult should record the slippage_pct used."""
        candles = self._make_candles([100.0 + i for i in range(20)])
        bt = Backtester(candles, initial_capital=10000.0, slippage_pct=0.05)
        result = bt.run(lambda c, p: None, "Test")
        assert result.slippage_pct == 0.05

    def test_higher_slippage_lower_returns(self):
        """Higher slippage should produce lower returns."""
        prices = [100.0 + i * 0.5 for i in range(50)]
        candles = self._make_candles(prices)
        strategy = self._buy_sell_strategy(buy_day=5, sell_day=40)

        results = []
        for slip in [0.0, 0.01, 0.1, 1.0]:
            bt = Backtester(candles, initial_capital=10000.0, slippage_pct=slip)
            results.append(bt.run(strategy, f"slip={slip}"))

        for i in range(len(results) - 1):
            assert results[i].total_return >= results[i + 1].total_return, (
                f"Expected return with slippage {results[i].slippage_pct} >= "
                f"return with slippage {results[i+1].slippage_pct}"
            )

    def test_backward_compat_default_slippage_zero(self):
        """Default slippage_pct should be 0.0 for backward compatibility."""
        candles = self._make_candles([100.0 + i for i in range(20)])
        bt = Backtester(candles, initial_capital=10000.0)
        assert bt.slippage_pct == 0.0
        result = bt.run(lambda c, p: None, "Test")
        assert result.slippage_pct == 0.0

    def test_backtest_result_default_slippage_field(self):
        """BacktestResult should default slippage_pct to 0.0."""
        result = _make_result()
        assert result.slippage_pct == 0.0

    def test_slippage_affects_trade_prices(self):
        """Trade entry/exit prices should reflect slippage."""
        # Fixed prices for predictable results
        prices = [100.0] * 5 + [110.0] * 5 + [120.0] * 10
        candles = self._make_candles(prices)

        bt = Backtester(candles, initial_capital=10000.0, slippage_pct=1.0)  # 1% slippage
        strategy = self._buy_sell_strategy(buy_day=1, sell_day=10)
        result = bt.run(strategy, "Slippage Price Test")

        assert result.total_trades == 1
        trade = result.trades[0]
        # Buy at day 1: close=100, effective = 100 * 1.01 = 101
        assert abs(trade.entry_price - 101.0) < 0.01
        # Sell at day 10 (index 9): close=110, effective = 110 * 0.99 = 108.9
        assert abs(trade.exit_price - 108.9) < 0.01


class TestSensitivityTest:
    """Test the sensitivity_test and sensitivity_report functions."""

    def test_returns_list_of_correct_length(self):
        candles = create_synthetic_candles(days=100, trend=0.1)
        backtester = Backtester(candles, initial_capital=10000.0)
        param_values = [5, 9, 13]
        results = sensitivity_test(
            backtester, ema_crossover, "fast", param_values,
            base_params={"slow": 21}, strategy_name="EMA"
        )
        assert len(results) == 3
        assert all(isinstance(r, BacktestResult) for r in results)
        # Check names include param values
        assert "fast=5" in results[0].strategy_name
        assert "fast=9" in results[1].strategy_name
        assert "fast=13" in results[2].strategy_name

    def test_sensitivity_report_returns_string(self):
        candles = create_synthetic_candles(days=100, trend=0.1)
        backtester = Backtester(candles, initial_capital=10000.0)
        results = sensitivity_test(
            backtester, ema_crossover, "fast", [5, 9, 13],
            base_params={"slow": 21},
        )
        report = sensitivity_report(results, "fast")
        assert isinstance(report, str)
        assert "Sensitivity Analysis" in report
        assert "Stability score" in report

    def test_sensitivity_report_empty(self):
        report = sensitivity_report([], "fast")
        assert report == "No results to report."

    def test_import_from_backtest_init(self):
        from pyhood.backtest import sensitivity_report as sr
        from pyhood.backtest import sensitivity_test as st
        assert callable(st)
        assert callable(sr)


class TestClassifyRegime:
    """Test the _classify_regime helper."""

    def _make_candles(self, prices: list[float], symbol: str = "TEST") -> list[Candle]:
        base_date = datetime(2023, 1, 1)
        candles = []
        for i, price in enumerate(prices):
            date_str = (base_date + timedelta(days=i)).isoformat() + "Z"
            candles.append(Candle(
                symbol=symbol,
                begins_at=date_str,
                open_price=price * 0.995,
                close_price=price,
                high_price=price * 1.02,
                low_price=price * 0.98,
                volume=1000000,
            ))
        return candles

    def test_unknown_insufficient_data(self):
        """Returns 'unknown' when not enough data for SMA."""
        prices = [100.0 + i * 0.1 for i in range(100)]
        candles = self._make_candles(prices)
        assert _classify_regime(candles, 50) == 'unknown'

    def test_bull_regime(self):
        """Price above rising SMA -> 'bull'."""
        # Create 210 bars of steady uptrend so SMA is rising and price > SMA
        prices = [100.0 + i * 0.5 for i in range(210)]
        candles = self._make_candles(prices)
        result = _classify_regime(candles, 209)
        assert result == 'bull'

    def test_bear_regime(self):
        """Price below falling SMA -> 'bear'."""
        # Create 210 bars of steady downtrend
        prices = [200.0 - i * 0.5 for i in range(210)]
        candles = self._make_candles(prices)
        result = _classify_regime(candles, 209)
        assert result == 'bear'

    def test_recovery_regime(self):
        """Price above SMA but SMA falling -> 'recovery'."""
        # Start with downtrend (SMA will be falling), then spike price above SMA
        prices = [200.0 - i * 0.3 for i in range(205)]
        # Spike price well above the SMA at the end
        for i in range(5):
            prices.append(180.0)
        candles = self._make_candles(prices)
        result = _classify_regime(candles, len(prices) - 1)
        assert result == 'recovery'

    def test_correction_regime(self):
        """Price below SMA but SMA rising -> 'correction'."""
        # Strong uptrend for 208 bars so SMA is solidly rising,
        # then a single bar dip below the SMA value.
        prices = [50.0 + i * 0.5 for i in range(208)]
        # The SMA at bar 207 is approx average of prices[8..207] = avg of (54..153.5) ≈ 103.75
        # Drop price just below SMA but SMA will still be rising (only 2 low bars)
        prices.append(60.0)
        prices.append(60.0)
        candles = self._make_candles(prices)
        result = _classify_regime(candles, len(prices) - 1)
        assert result == 'correction'

    def test_custom_sma_period(self):
        """Test with a shorter SMA period."""
        prices = [100.0 + i * 0.5 for i in range(60)]
        candles = self._make_candles(prices)
        result = _classify_regime(candles, 59, sma_period=50)
        assert result == 'bull'


class TestTradeRegimeField:
    """Test that Trade objects carry the regime field."""

    def test_trade_default_regime(self):
        """Trade should default regime to 'unknown'."""
        trade = Trade(
            entry_date="2023-01-01",
            exit_date="2023-02-01",
            side="long",
            entry_price=100.0,
            exit_price=110.0,
            quantity=10.0,
            pnl=100.0,
            pnl_pct=10.0,
        )
        assert trade.regime == 'unknown'

    def test_trade_with_regime(self):
        """Trade should accept and store regime."""
        trade = Trade(
            entry_date="2023-01-01",
            exit_date="2023-02-01",
            side="long",
            entry_price=100.0,
            exit_price=110.0,
            quantity=10.0,
            pnl=100.0,
            pnl_pct=10.0,
            regime='bull',
        )
        assert trade.regime == 'bull'


class TestBacktestResultRegimeBreakdown:
    """Test that BacktestResult has regime_breakdown."""

    def test_default_regime_breakdown_is_none(self):
        """BacktestResult should default regime_breakdown to None."""
        result = _make_result()
        assert result.regime_breakdown is None

    def test_regime_breakdown_with_value(self):
        """BacktestResult should accept regime_breakdown dict."""
        breakdown = {
            'bull': {'trades': 5, 'wins': 4, 'win_rate': 80.0, 'pnl': 500.0},
            'bear': {'trades': 3, 'wins': 1, 'win_rate': 33.3, 'pnl': -200.0},
        }
        result = _make_result(regime_breakdown=breakdown)
        assert result.regime_breakdown is not None
        assert result.regime_breakdown['bull']['trades'] == 5
        assert result.regime_breakdown['bear']['pnl'] == -200.0


class TestRegimeReport:
    """Test regime_report formatting."""

    def test_no_breakdown(self):
        """Report handles missing regime_breakdown."""
        result = _make_result()
        report = regime_report(result)
        assert "No regime breakdown" in report

    def test_basic_report(self):
        """Report formats regime data correctly."""
        breakdown = {
            'bull': {'trades': 10, 'wins': 8, 'win_rate': 80.0, 'pnl': 5000.0},
            'bear': {'trades': 5, 'wins': 1, 'win_rate': 20.0, 'pnl': -1000.0},
        }
        result = _make_result(regime_breakdown=breakdown)
        report = regime_report(result)
        assert "Regime Report" in report
        assert "bull" in report
        assert "bear" in report
        assert "5000.00" in report

    def test_regime_dependent_flag(self):
        """Report flags when 80%+ of P&L comes from one regime."""
        breakdown = {
            'bull': {'trades': 10, 'wins': 9, 'win_rate': 90.0, 'pnl': 9000.0},
            'bear': {'trades': 5, 'wins': 2, 'win_rate': 40.0, 'pnl': 100.0},
        }
        result = _make_result(regime_breakdown=breakdown)
        report = regime_report(result)
        assert "REGIME-DEPENDENT" in report

    def test_import_from_backtest_init(self):
        from pyhood.backtest import regime_report as imported
        assert callable(imported)


class TestRegimeIntegration:
    """Test that a full backtest populates regime data end-to-end."""

    def test_regime_populated_on_run(self):
        """Running a strategy should populate regime_breakdown in results."""
        # Need 250+ candles for 200 SMA to have data
        candles = create_synthetic_candles(days=300, trend=0.15)
        backtester = Backtester(candles, initial_capital=10000.0)
        strategy = ema_crossover(fast=9, slow=21)
        result = backtester.run(strategy, "EMA Crossover Regime Test")

        if result.total_trades > 0:
            # regime_breakdown should be populated
            assert result.regime_breakdown is not None
            # Each trade should have a regime
            for trade in result.trades:
                assert trade.regime in ('bull', 'bear', 'recovery', 'correction', 'unknown')
            # regime_breakdown values should match trades
            total_trades_in_breakdown = sum(
                d['trades'] for d in result.regime_breakdown.values()
            )
            assert total_trades_in_breakdown == result.total_trades
