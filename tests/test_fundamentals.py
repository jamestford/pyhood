"""Tests for fundamental data module — all mocked, no yfinance calls."""

from unittest.mock import patch

from pyhood.fundamentals import FundamentalData, fundamental_filter

# Sample yfinance-like info dict for mocking
MOCK_INFO = {
    'trailingPE': 28.5,
    'forwardPE': 25.0,
    'priceToBook': 40.2,
    'debtToEquity': 150.3,
    'revenueGrowth': 0.12,
    'profitMargins': 0.25,
    'marketCap': 2_800_000_000_000,
    'beta': 1.2,
    'dividendYield': 0.005,
    'sector': 'Technology',
    'industry': 'Consumer Electronics',
    'heldPercentInsiders': 0.0007,
    'heldPercentInstitutions': 0.61,
    'shortRatio': 1.5,
    'earningsGrowth': 0.10,
    'currentRatio': 1.07,
    'freeCashflow': 100_000_000_000,
}


def _make_fd(info: dict | None = None) -> FundamentalData:
    """Create a FundamentalData with a pre-loaded info dict (no yfinance)."""
    fd = FundamentalData('AAPL')
    fd._info = info if info is not None else dict(MOCK_INFO)
    return fd


class TestFundamentalDataProperties:
    """Test all property accessors."""

    def test_pe_ratio(self):
        fd = _make_fd()
        assert fd.pe_ratio == 28.5

    def test_forward_pe(self):
        fd = _make_fd()
        assert fd.forward_pe == 25.0

    def test_pb_ratio(self):
        fd = _make_fd()
        assert fd.pb_ratio == 40.2

    def test_debt_to_equity(self):
        fd = _make_fd()
        assert fd.debt_to_equity == 150.3

    def test_revenue_growth(self):
        fd = _make_fd()
        assert fd.revenue_growth == 0.12

    def test_profit_margin(self):
        fd = _make_fd()
        assert fd.profit_margin == 0.25

    def test_market_cap(self):
        fd = _make_fd()
        assert fd.market_cap == 2_800_000_000_000

    def test_beta(self):
        fd = _make_fd()
        assert fd.beta == 1.2

    def test_dividend_yield(self):
        fd = _make_fd()
        assert fd.dividend_yield == 0.005

    def test_sector(self):
        fd = _make_fd()
        assert fd.sector == 'Technology'

    def test_industry(self):
        fd = _make_fd()
        assert fd.industry == 'Consumer Electronics'

    def test_insider_buy_pct(self):
        fd = _make_fd()
        assert fd.insider_buy_pct == 0.0007

    def test_institutional_pct(self):
        fd = _make_fd()
        assert fd.institutional_pct == 0.61

    def test_short_ratio(self):
        fd = _make_fd()
        assert fd.short_ratio == 1.5

    def test_earnings_growth(self):
        fd = _make_fd()
        assert fd.earnings_growth == 0.10

    def test_current_ratio(self):
        fd = _make_fd()
        assert fd.current_ratio == 1.07

    def test_free_cash_flow(self):
        fd = _make_fd()
        assert fd.free_cash_flow == 100_000_000_000


class TestMissingKeys:
    """Test that missing keys return None gracefully."""

    def test_empty_info_returns_none(self):
        fd = _make_fd({})
        assert fd.pe_ratio is None
        assert fd.forward_pe is None
        assert fd.market_cap is None
        assert fd.sector is None
        assert fd.beta is None

    def test_partial_info(self):
        fd = _make_fd({'trailingPE': 20.0})
        assert fd.pe_ratio == 20.0
        assert fd.forward_pe is None
        assert fd.market_cap is None


class TestSummary:
    """Test the summary() method."""

    def test_summary_returns_dict_with_ticker(self):
        fd = _make_fd()
        s = fd.summary()
        assert s['ticker'] == 'AAPL'

    def test_summary_includes_available_props(self):
        fd = _make_fd()
        s = fd.summary()
        assert s['pe_ratio'] == 28.5
        assert s['market_cap'] == 2_800_000_000_000
        assert s['sector'] == 'Technology'

    def test_summary_skips_none_values(self):
        fd = _make_fd({'trailingPE': 15.0})
        s = fd.summary()
        assert 'pe_ratio' in s
        assert 'market_cap' not in s

    def test_summary_empty_info(self):
        fd = _make_fd({})
        s = fd.summary()
        assert s == {'ticker': 'AAPL'}


class TestPassesFilter:
    """Test the passes_filter method."""

    def test_passes_all_filters(self):
        fd = _make_fd()
        assert fd.passes_filter({
            'pe_ratio': {'max': 30},
            'revenue_growth': {'min': 0.10},
            'market_cap': {'min': 1_000_000_000},
        }) is True

    def test_fails_max_filter(self):
        fd = _make_fd()
        assert fd.passes_filter({
            'pe_ratio': {'max': 20},  # 28.5 > 20 → fail
        }) is False

    def test_fails_min_filter(self):
        fd = _make_fd()
        assert fd.passes_filter({
            'revenue_growth': {'min': 0.50},  # 0.12 < 0.50 → fail
        }) is False

    def test_passes_min_max_range(self):
        fd = _make_fd()
        assert fd.passes_filter({
            'beta': {'min': 0.5, 'max': 2.0},
        }) is True

    def test_fails_min_max_range(self):
        fd = _make_fd()
        assert fd.passes_filter({
            'beta': {'min': 1.5, 'max': 2.0},  # 1.2 < 1.5 → fail
        }) is False

    def test_missing_data_skips_filter(self):
        fd = _make_fd({})
        # No data at all — all filters skipped → passes
        assert fd.passes_filter({
            'pe_ratio': {'max': 10},
            'market_cap': {'min': 999_999_999_999_999},
        }) is True

    def test_empty_filters_always_passes(self):
        fd = _make_fd()
        assert fd.passes_filter({}) is True

    def test_multiple_filters_all_must_pass(self):
        fd = _make_fd()
        # pe_ratio passes (28.5 < 30) but revenue_growth fails (0.12 < 0.50)
        assert fd.passes_filter({
            'pe_ratio': {'max': 30},
            'revenue_growth': {'min': 0.50},
        }) is False

    def test_non_numeric_property_skipped(self):
        fd = _make_fd()
        # sector is a string — min/max doesn't apply, should be skipped
        assert fd.passes_filter({
            'sector': {'min': 'A'},
        }) is True


class TestFundamentalFilter:
    """Test the fundamental_filter wrapper."""

    def test_passes_delegates_to_inner_strategy(self):
        """When fundamentals pass, the inner strategy is called."""
        inner_called = []

        def mock_strategy(candles, position):
            inner_called.append(True)
            return 'buy'

        fd = FundamentalData('AAPL')
        fd._info = dict(MOCK_INFO)

        with patch('pyhood.fundamentals.FundamentalData', return_value=fd):
            wrapped = fundamental_filter(
                mock_strategy, 'AAPL',
                filters={'pe_ratio': {'max': 50}}
            )
            result = wrapped([], None)

        assert result == 'buy'
        assert len(inner_called) == 1

    def test_fails_returns_none(self):
        """When fundamentals fail, always returns None."""
        def mock_strategy(candles, position):
            return 'buy'

        fd = FundamentalData('AAPL')
        fd._info = dict(MOCK_INFO)

        with patch('pyhood.fundamentals.FundamentalData', return_value=fd):
            wrapped = fundamental_filter(
                mock_strategy, 'AAPL',
                filters={'pe_ratio': {'max': 10}}  # 28.5 > 10 → fail
            )
            result = wrapped([], None)

        assert result is None

    def test_filter_is_static(self):
        """Filter checks fundamentals once at creation, not per call."""
        call_count = [0]

        original_init = FundamentalData.__init__

        def counting_init(self, ticker):
            call_count[0] += 1
            original_init(self, ticker)
            self._info = dict(MOCK_INFO)

        with patch.object(FundamentalData, '__init__', counting_init):
            def mock_strategy(candles, position):
                return 'buy'

            wrapped = fundamental_filter(
                mock_strategy, 'AAPL',
                filters={'pe_ratio': {'max': 50}}
            )

        init_count = call_count[0]

        # Call the wrapped strategy multiple times
        wrapped([], None)
        wrapped([], None)
        wrapped([], None)

        # FundamentalData should not be re-created on each call
        assert call_count[0] == init_count
