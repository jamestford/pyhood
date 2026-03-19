"""Stock universe screener for fundamental-based stock selection.

Provides StockScreener for filtering stocks by fundamental criteria
against pre-built universes (S&P 500, Nasdaq 100) or custom ticker lists.
"""

from __future__ import annotations

import logging
import time

from pyhood.fundamentals import FundamentalData

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hardcoded ticker universes (no web scraping)
# ---------------------------------------------------------------------------

SP500_TOP: list[str] = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'BRK-B', 'TSLA',
    'UNH', 'JPM', 'V', 'JNJ', 'XOM', 'PG', 'MA', 'HD', 'CVX', 'MRK',
    'ABBV', 'PEP', 'KO', 'COST', 'AVGO', 'LLY', 'WMT', 'MCD', 'CSCO',
    'TMO', 'ABT', 'CRM', 'ACN', 'DHR', 'LIN', 'NKE', 'TXN', 'NEE',
    'PM', 'UNP', 'RTX', 'LOW', 'BMY', 'AMGN', 'IBM', 'QCOM', 'INTC',
    'AMAT', 'GS', 'CAT', 'BLK', 'AXP', 'DE', 'ISRG', 'MDLZ', 'ADI',
    'GILD', 'SYK', 'BKNG', 'VRTX', 'MMC', 'CB', 'LRCX', 'REGN', 'ZTS',
    'TMUS', 'PLD', 'CI', 'NOW', 'SCHW', 'KLAC', 'CME', 'BSX', 'SO',
    'DUK', 'ICE', 'AON', 'SHW', 'CL', 'MO', 'PGR', 'MCK', 'EQIX',
    'ITW', 'HUM', 'FDX', 'GD', 'EMR', 'ORLY', 'PSA', 'NSC', 'APD',
    'CTAS', 'WM', 'MAR', 'MCO', 'ADP', 'MSI', 'TGT', 'SRE',
]

NASDAQ100_TOP: list[str] = [
    'AAPL', 'MSFT', 'AMZN', 'NVDA', 'META', 'GOOGL', 'GOOG', 'TSLA',
    'AVGO', 'COST', 'NFLX', 'TMUS', 'CSCO', 'AMD', 'ADBE', 'PEP',
    'INTC', 'LIN', 'INTU', 'CMCSA', 'TXN', 'QCOM', 'ISRG', 'AMAT',
    'AMGN', 'HON', 'BKNG', 'LRCX', 'VRTX', 'ADP', 'REGN', 'KLAC',
    'SBUX', 'MDLZ', 'GILD', 'ADI', 'PANW', 'SNPS', 'CDNS', 'PYPL',
    'MELI', 'ABNB', 'ORLY', 'CRWD', 'NXPI', 'CTAS', 'MAR', 'CSX',
    'MRVL', 'PCAR', 'FTNT', 'MNST', 'WDAY', 'ROST', 'KDP', 'DXCM',
    'CPRT', 'ODFL', 'KHC', 'IDXX', 'EXC', 'GEHC', 'FAST', 'VRSK',
    'AEP', 'ON', 'FANG', 'EA', 'CTSH', 'BKR', 'XEL', 'DLTR', 'ANSS',
    'CDW', 'GFS', 'TEAM', 'DDOG', 'ZS', 'MDB', 'BIIB', 'ILMN', 'ENPH',
    'SIRI', 'AZN', 'WBD', 'LCID', 'RIVN', 'JD', 'PDD', 'BIDU',
]


class StockScreener:
    """Screen for stocks matching fundamental criteria.

    Usage::

        screener = StockScreener('sp500')
        results = screener.screen(
            filters={'pe_ratio': {'max': 25}, 'revenue_growth': {'min': 0.10}},
            max_results=10,
            sort_by='market_cap',
        )
    """

    SP500 = 'sp500'
    NASDAQ100 = 'nasdaq100'

    def __init__(self, universe: str | list[str] = 'sp500'):
        """
        Args:
            universe: ``'sp500'``, ``'nasdaq100'``, or an explicit list of
                ticker strings.
        """
        if isinstance(universe, str):
            if universe.lower() == 'sp500':
                self.tickers = list(SP500_TOP)
            elif universe.lower() == 'nasdaq100':
                self.tickers = list(NASDAQ100_TOP)
            else:
                raise ValueError(
                    f"Unknown universe '{universe}'. "
                    f"Use 'sp500', 'nasdaq100', or a list of tickers."
                )
        else:
            self.tickers = list(universe)

    @staticmethod
    def get_sp500_tickers() -> list[str]:
        """Return the hardcoded S&P 500 top tickers list."""
        return list(SP500_TOP)

    @staticmethod
    def get_nasdaq100_tickers() -> list[str]:
        """Return the hardcoded Nasdaq 100 top tickers list."""
        return list(NASDAQ100_TOP)

    def screen(
        self,
        filters: dict,
        max_results: int = 20,
        sort_by: str | None = None,
        sort_desc: bool = True,
    ) -> list[dict]:
        """Screen universe for stocks matching fundamental criteria.

        Args:
            filters: Same format as ``FundamentalData.passes_filter``.
            max_results: Maximum tickers to return.
            sort_by: Optional fundamental property name to sort by
                (e.g. ``'revenue_growth'``, ``'market_cap'``).
            sort_desc: Sort descending (True) or ascending (False).

        Returns:
            List of summary dicts for passing tickers::

                [{'ticker': 'AAPL', 'pe_ratio': 28.5, ...}, ...]
        """
        results: list[dict] = []

        for ticker in self.tickers:
            try:
                fd = FundamentalData(ticker)
                if fd.passes_filter(filters):
                    results.append(fd.summary())
            except Exception as exc:
                logger.warning("Failed to screen %s: %s", ticker, exc)
                continue

            # Rate-limit yfinance calls
            time.sleep(0.1)

        # Sort if requested
        if sort_by and results:
            results.sort(
                key=lambda d: d.get(sort_by, 0) or 0,
                reverse=sort_desc,
            )

        return results[:max_results]

    def screen_for_autoresearch(
        self,
        filters: dict,
        max_tickers: int = 10,
        sort_by: str = 'market_cap',
    ) -> list[str]:
        """Screen and return just ticker symbols for autoresearch.

        Convenience method that returns ``['AAPL', 'MSFT', ...]`` ready
        to feed into ``AutoResearcher``.

        Args:
            filters: Fundamental filter dict.
            max_tickers: Maximum tickers to return.
            sort_by: Fundamental to sort by (default ``'market_cap'``).

        Returns:
            List of ticker symbol strings.
        """
        results = self.screen(
            filters, max_results=max_tickers, sort_by=sort_by
        )
        return [r['ticker'] for r in results]
