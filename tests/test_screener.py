"""Tests for stock screener — all mocked, no yfinance calls."""

import pytest
from unittest.mock import patch, MagicMock

from pyhood.screener import StockScreener, SP500_TOP, NASDAQ100_TOP
from pyhood.fundamentals import FundamentalData


# Mock info dicts for different tickers
MOCK_INFOS = {
    'AAPL': {
        'trailingPE': 28.5, 'revenueGrowth': 0.12, 'marketCap': 2_800_000_000_000,
        'beta': 1.2, 'profitMargins': 0.25, 'sector': 'Technology',
    },
    'MSFT': {
        'trailingPE': 35.0, 'revenueGrowth': 0.15, 'marketCap': 2_500_000_000_000,
        'beta': 0.9, 'profitMargins': 0.35, 'sector': 'Technology',
    },
    'JPM': {
        'trailingPE': 12.0, 'revenueGrowth': 0.08, 'marketCap': 500_000_000_000,
        'beta': 1.1, 'profitMargins': 0.30, 'sector': 'Financial Services',
    },
    'XOM': {
        'trailingPE': 10.0, 'revenueGrowth': -0.05, 'marketCap': 400_000_000_000,
        'beta': 0.8, 'profitMargins': 0.12, 'sector': 'Energy',
    },
    'KO': {
        'trailingPE': 22.0, 'revenueGrowth': 0.03, 'marketCap': 250_000_000_000,
        'beta': 0.6, 'profitMargins': 0.22, 'sector': 'Consumer Defensive',
    },
}


def _mock_fundamental_data(ticker):
    """Create a FundamentalData with mocked info (no yfinance)."""
    fd = FundamentalData(ticker)
    fd._info = MOCK_INFOS.get(ticker, {})
    return fd


class TestTickerLists:
    """Test hardcoded ticker lists."""

    def test_sp500_tickers_not_empty(self):
        tickers = StockScreener.get_sp500_tickers()
        assert len(tickers) > 50

    def test_nasdaq100_tickers_not_empty(self):
        tickers = StockScreener.get_nasdaq100_tickers()
        assert len(tickers) > 50

    def test_sp500_contains_known_tickers(self):
        tickers = StockScreener.get_sp500_tickers()
        assert 'AAPL' in tickers
        assert 'MSFT' in tickers
        assert 'JPM' in tickers

    def test_nasdaq100_contains_known_tickers(self):
        tickers = StockScreener.get_nasdaq100_tickers()
        assert 'AAPL' in tickers
        assert 'NVDA' in tickers
        assert 'TSLA' in tickers

    def test_sp500_returns_copy(self):
        """Modifying the returned list shouldn't affect the original."""
        tickers = StockScreener.get_sp500_tickers()
        tickers.append('FAKE')
        assert 'FAKE' not in SP500_TOP


class TestScreenerInit:
    """Test StockScreener initialization."""

    def test_init_sp500(self):
        screener = StockScreener('sp500')
        assert len(screener.tickers) > 50

    def test_init_nasdaq100(self):
        screener = StockScreener('nasdaq100')
        assert len(screener.tickers) > 50

    def test_init_custom_list(self):
        screener = StockScreener(['AAPL', 'MSFT', 'GOOGL'])
        assert screener.tickers == ['AAPL', 'MSFT', 'GOOGL']

    def test_init_invalid_universe(self):
        with pytest.raises(ValueError, match="Unknown universe"):
            StockScreener('invalid')


class TestScreen:
    """Test the screen method with mocked FundamentalData."""

    @patch('pyhood.screener.FundamentalData')
    @patch('pyhood.screener.time.sleep')  # Skip rate limiting in tests
    def test_basic_screen(self, mock_sleep, mock_fd_class):
        mock_fd_class.side_effect = _mock_fundamental_data

        screener = StockScreener(['AAPL', 'MSFT', 'JPM', 'XOM', 'KO'])
        results = screener.screen(
            filters={'pe_ratio': {'max': 30}},
            max_results=10,
        )

        # AAPL (28.5), JPM (12), XOM (10), KO (22) pass; MSFT (35) fails
        tickers = [r['ticker'] for r in results]
        assert 'MSFT' not in tickers
        assert 'AAPL' in tickers
        assert 'JPM' in tickers

    @patch('pyhood.screener.FundamentalData')
    @patch('pyhood.screener.time.sleep')
    def test_max_results_limits_output(self, mock_sleep, mock_fd_class):
        mock_fd_class.side_effect = _mock_fundamental_data

        screener = StockScreener(['AAPL', 'MSFT', 'JPM', 'XOM', 'KO'])
        results = screener.screen(
            filters={},  # No filters — all pass
            max_results=2,
        )
        assert len(results) <= 2

    @patch('pyhood.screener.FundamentalData')
    @patch('pyhood.screener.time.sleep')
    def test_sort_by_ascending(self, mock_sleep, mock_fd_class):
        mock_fd_class.side_effect = _mock_fundamental_data

        screener = StockScreener(['AAPL', 'MSFT', 'JPM', 'XOM', 'KO'])
        results = screener.screen(
            filters={},
            sort_by='pe_ratio',
            sort_desc=False,
            max_results=10,
        )

        # Should be sorted by PE ascending: XOM(10) < JPM(12) < KO(22) < AAPL(28.5) < MSFT(35)
        pe_values = [r.get('pe_ratio', 0) for r in results]
        assert pe_values == sorted(pe_values)

    @patch('pyhood.screener.FundamentalData')
    @patch('pyhood.screener.time.sleep')
    def test_sort_by_descending(self, mock_sleep, mock_fd_class):
        mock_fd_class.side_effect = _mock_fundamental_data

        screener = StockScreener(['AAPL', 'MSFT', 'JPM', 'XOM', 'KO'])
        results = screener.screen(
            filters={},
            sort_by='market_cap',
            sort_desc=True,
            max_results=10,
        )

        # First result should have highest market cap
        assert results[0]['ticker'] == 'AAPL'  # 2.8T

    @patch('pyhood.screener.FundamentalData')
    @patch('pyhood.screener.time.sleep')
    def test_min_and_max_filter(self, mock_sleep, mock_fd_class):
        mock_fd_class.side_effect = _mock_fundamental_data

        screener = StockScreener(['AAPL', 'MSFT', 'JPM', 'XOM', 'KO'])
        results = screener.screen(
            filters={
                'pe_ratio': {'min': 15, 'max': 30},
            },
            max_results=10,
        )

        # Only AAPL (28.5) and KO (22) are in range 15-30
        tickers = [r['ticker'] for r in results]
        assert 'AAPL' in tickers
        assert 'KO' in tickers
        assert 'JPM' not in tickers  # 12 < 15
        assert 'MSFT' not in tickers  # 35 > 30
        assert 'XOM' not in tickers  # 10 < 15

    @patch('pyhood.screener.FundamentalData')
    @patch('pyhood.screener.time.sleep')
    def test_handles_exception_gracefully(self, mock_sleep, mock_fd_class):
        """If FundamentalData raises, skip that ticker."""
        def side_effect(ticker):
            if ticker == 'MSFT':
                raise Exception("API error")
            return _mock_fundamental_data(ticker)

        mock_fd_class.side_effect = side_effect

        screener = StockScreener(['AAPL', 'MSFT', 'JPM'])
        results = screener.screen(filters={}, max_results=10)

        tickers = [r['ticker'] for r in results]
        assert 'MSFT' not in tickers
        assert 'AAPL' in tickers


class TestScreenForAutoresearch:
    """Test screen_for_autoresearch convenience method."""

    @patch('pyhood.screener.FundamentalData')
    @patch('pyhood.screener.time.sleep')
    def test_returns_list_of_strings(self, mock_sleep, mock_fd_class):
        mock_fd_class.side_effect = _mock_fundamental_data

        screener = StockScreener(['AAPL', 'MSFT', 'JPM'])
        tickers = screener.screen_for_autoresearch(
            filters={'pe_ratio': {'max': 30}},
            max_tickers=5,
        )

        assert isinstance(tickers, list)
        assert all(isinstance(t, str) for t in tickers)
        assert 'AAPL' in tickers

    @patch('pyhood.screener.FundamentalData')
    @patch('pyhood.screener.time.sleep')
    def test_respects_max_tickers(self, mock_sleep, mock_fd_class):
        mock_fd_class.side_effect = _mock_fundamental_data

        screener = StockScreener(['AAPL', 'MSFT', 'JPM', 'XOM', 'KO'])
        tickers = screener.screen_for_autoresearch(
            filters={},
            max_tickers=2,
        )
        assert len(tickers) <= 2

    @patch('pyhood.screener.FundamentalData')
    @patch('pyhood.screener.time.sleep')
    def test_sorted_by_market_cap_default(self, mock_sleep, mock_fd_class):
        mock_fd_class.side_effect = _mock_fundamental_data

        screener = StockScreener(['AAPL', 'MSFT', 'JPM', 'XOM', 'KO'])
        tickers = screener.screen_for_autoresearch(
            filters={},
            max_tickers=5,
        )
        # AAPL has highest market cap, should be first
        assert tickers[0] == 'AAPL'
