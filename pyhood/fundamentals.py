"""Fundamental data integration for stock screening and strategy filtering.

Provides FundamentalData for fetching/caching fundamental ratios via yfinance,
and fundamental_filter for wrapping any strategy with a fundamental pre-screen.
"""

from __future__ import annotations


class FundamentalData:
    """Fetch and cache fundamental data for a ticker using yfinance."""

    def __init__(self, ticker: str):
        self.ticker = ticker
        self._info: dict | None = None  # Lazy-loaded

    @property
    def info(self) -> dict:
        """Cached yfinance Ticker.info dict."""
        if self._info is None:
            import yfinance as yf
            self._info = yf.Ticker(self.ticker).info or {}
        return self._info

    # -- Key ratio properties ------------------------------------------------

    def _get(self, key: str):
        """Safely get a value from the info dict."""
        try:
            val = self.info.get(key)
            return val
        except Exception:
            return None

    @property
    def pe_ratio(self) -> float | None:
        return self._get('trailingPE')

    @property
    def forward_pe(self) -> float | None:
        return self._get('forwardPE')

    @property
    def pb_ratio(self) -> float | None:
        return self._get('priceToBook')

    @property
    def debt_to_equity(self) -> float | None:
        return self._get('debtToEquity')

    @property
    def revenue_growth(self) -> float | None:
        return self._get('revenueGrowth')

    @property
    def profit_margin(self) -> float | None:
        return self._get('profitMargins')

    @property
    def market_cap(self) -> float | None:
        return self._get('marketCap')

    @property
    def beta(self) -> float | None:
        return self._get('beta')

    @property
    def dividend_yield(self) -> float | None:
        return self._get('dividendYield')

    @property
    def sector(self) -> str | None:
        return self._get('sector')

    @property
    def industry(self) -> str | None:
        return self._get('industry')

    @property
    def insider_buy_pct(self) -> float | None:
        return self._get('heldPercentInsiders')

    @property
    def institutional_pct(self) -> float | None:
        return self._get('heldPercentInstitutions')

    @property
    def short_ratio(self) -> float | None:
        return self._get('shortRatio')

    @property
    def earnings_growth(self) -> float | None:
        return self._get('earningsGrowth')

    @property
    def current_ratio(self) -> float | None:
        return self._get('currentRatio')

    @property
    def free_cash_flow(self) -> float | None:
        return self._get('freeCashflow')

    # -- Aggregate helpers ---------------------------------------------------

    # All numeric property names and their display labels
    _PROPERTIES = [
        'pe_ratio', 'forward_pe', 'pb_ratio', 'debt_to_equity',
        'revenue_growth', 'profit_margin', 'market_cap', 'beta',
        'dividend_yield', 'sector', 'industry', 'insider_buy_pct',
        'institutional_pct', 'short_ratio', 'earnings_growth',
        'current_ratio', 'free_cash_flow',
    ]

    def summary(self) -> dict:
        """Return all available fundamentals as a clean dict (skipping None)."""
        result = {'ticker': self.ticker}
        for prop in self._PROPERTIES:
            val = getattr(self, prop)
            if val is not None:
                result[prop] = val
        return result

    def passes_filter(self, filters: dict) -> bool:
        """Check if this ticker passes all fundamental filters.

        Args:
            filters: Dict mapping property names to constraint dicts.
                Example::

                    {
                        'pe_ratio': {'max': 25},
                        'revenue_growth': {'min': 0.10},
                        'market_cap': {'min': 1_000_000_000},
                        'beta': {'min': 0.5, 'max': 2.0},
                    }

                Each key is a property name, value is dict with 'min'
                and/or 'max'.  Returns True if ALL filters pass.
                Missing data (None) causes that individual filter to be
                skipped (not failed).

        Returns:
            True if all filters pass (or are skipped due to missing data).
        """
        for prop_name, constraints in filters.items():
            val = getattr(self, prop_name, None)
            if val is None:
                # Missing data — skip this filter
                continue
            if not isinstance(val, (int, float)):
                continue
            if 'min' in constraints and val < constraints['min']:
                return False
            if 'max' in constraints and val > constraints['max']:
                return False
        return True


def fundamental_filter(strategy_fn, ticker: str, filters: dict):
    """Wrap any strategy with fundamental pre-screening.

    If the ticker doesn't pass fundamental filters, the wrapped strategy
    never generates signals (always returns None).

    This is a STATIC filter — checks fundamentals once at creation time,
    not dynamically during the backtest.

    Args:
        strategy_fn: A strategy callable ``(candles, position) -> signal``.
            This is the already-called factory result, not the factory itself.
        ticker: Ticker symbol to check fundamentals for.
        filters: Fundamental filter dict (same format as
            ``FundamentalData.passes_filter``).

    Returns:
        A strategy callable that delegates to *strategy_fn* if fundamentals
        pass, or always returns None if they don't.

    Example::

        strategy = fundamental_filter(
            ema_crossover(fast=9, slow=21),
            ticker='AAPL',
            filters={'pe_ratio': {'max': 30}, 'revenue_growth': {'min': 0.05}}
        )
        result = bt.run(strategy, "EMA + Fundamentals")
    """
    fd = FundamentalData(ticker)
    passes = fd.passes_filter(filters)

    if passes:
        return strategy_fn
    else:
        def _blocked(candles, position):
            return None
        return _blocked
