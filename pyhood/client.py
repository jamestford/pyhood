"""PyhoodClient — high-level API for Robinhood operations.

All methods return typed dataclasses, not raw dicts.
"""

from __future__ import annotations

import csv
import logging
import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pyhood import urls
from pyhood.auth import get_session
from pyhood.exceptions import OrderError, SymbolNotFound
from pyhood.http import Session
from pyhood.models import (
    ACHTransfer,
    BankAccount,
    Candle,
    CardTransaction,
    Dividend,
    Document,
    Earnings,
    FuturesContract,
    FuturesOrder,
    FuturesPnL,
    FuturesQuote,
    InterestPayment,
    Market,
    MarketHours,
    Mover,
    NewsArticle,
    NotificationSettings,
    OptionContract,
    OptionPosition,
    OptionsChain,
    Order,
    PortfolioCandle,
    Position,
    Quote,
    Rating,
    StockSplit,
    SubscriptionFee,
    UnifiedTransfer,
    UserProfile,
    Watchlist,
)

logger = logging.getLogger("pyhood")

# Robinhood versions its order form and refuses orders from clients sending an
# older value (or none) with "Your app version is missing important stock
# trading updates." Captured from the web client on 2026-08-09; 6 is also
# accepted, 1 is not. Bump this if that error reappears.
ORDER_FORM_VERSION = 7

# Robinhood instrument IDs, as returned bare in news related_instruments
_INSTRUMENT_ID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)

# Index options use different API paths and chain symbols than equity options.
# Keys are the base index symbol; values are the chain_symbol Robinhood expects
# when querying /options/instruments/.
INDEX_CHAIN_SYMBOLS: dict[str, str] = {
    "SPX": "SPXW",
    "NDX": "NDXP",
    "VIX": "VIXW",
    "RUT": "RUTW",
    "XSP": "XSP",
}


class PyhoodClient:
    """High-level Robinhood API client.

    Usage:
        client = PyhoodClient(session)  # explicit session
        client = PyhoodClient()         # uses active session from pyhood.login()
    """

    def __init__(self, session: Session | None = None):
        self._session = session or get_session()

    # ── Stocks ──────────────────────────────────────────────────────────

    def get_quote(self, symbol: str, include_fundamentals: bool = False) -> Quote:
        """Get a stock quote.

        Args:
            symbol: Stock ticker.
            include_fundamentals: Also fetch the symbol's fundamentals, to
                fill `volume`, `pe_ratio`, `market_cap`, `high_52w` and
                `low_52w`. Robinhood's quote does not carry them, so they
                are None without this. Costs one more request.
        """
        data = self._session.get(f"{urls.QUOTES}{symbol.upper()}/")
        if not data or "last_trade_price" not in data:
            raise SymbolNotFound(f"No quote data for {symbol}")
        fundamentals = self.get_fundamentals(symbol) if include_fundamentals else None
        return _quote(data, symbol.upper(), fundamentals)

    def get_quotes(
        self, symbols: list[str], include_fundamentals: bool = False,
    ) -> dict[str, Quote]:
        """Get quotes for multiple symbols (batched).

        Robinhood's quotes endpoint supports up to ~1,000 symbols per
        request (limited by URL length ~5,700 chars). We use 1,000 as
        a safe batch size.

        Args:
            symbols: Stock tickers.
            include_fundamentals: Also fetch fundamentals, to fill `volume`,
                `pe_ratio`, `market_cap`, `high_52w` and `low_52w`, which
                are None without this. Fundamentals come 100 symbols to a
                request, so this adds one request per 100 symbols.
        """
        fundamentals = self.get_fundamentals_batch(symbols) if include_fundamentals else {}
        results: dict[str, Quote] = {}
        batch_size = 1000
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            data = self._session.get(
                urls.QUOTES, params={"symbols": ",".join(s.upper() for s in batch)}
            )
            for item in data.get("results", []):
                if not item or "symbol" not in item:
                    continue
                sym = item["symbol"]
                results[sym] = _quote(item, sym, fundamentals.get(sym.upper()))
        return results

    def get_fundamentals(self, symbol: str) -> dict[str, Any]:
        """Get fundamental data for a symbol (PE, market cap, 52w range)."""
        data = self._session.get(f"{urls.FUNDAMENTALS}{symbol.upper()}/")
        return data or {}

    def get_fundamentals_batch(
        self, symbols: list[str],
    ) -> dict[str, dict[str, Any]]:
        """Get fundamental data for multiple symbols (batched).

        Returns dict mapping symbol to fundamentals. Robinhood's
        fundamentals endpoint supports exactly 100 symbols per request.

        Returned fields include: high_52_weeks, low_52_weeks, market_cap,
        pb_ratio, pe_ratio, shares_outstanding, float, volume,
        average_volume, sector, industry, description, and more.
        """
        results: dict[str, dict[str, Any]] = {}
        batch_size = 100  # Robinhood hard limit: exactly 100

        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            data = self._session.get(
                urls.FUNDAMENTALS,
                params={"symbols": ",".join(s.upper() for s in batch)},
            )
            for j, fund in enumerate(data.get("results", [])):
                if fund and j < len(batch):
                    results[batch[j].upper()] = fund

        return results

    def get_all_instruments(
        self, tradeable_only: bool = True,
    ) -> list[str]:
        """Get all stock symbols available on Robinhood.

        Paginates through the instruments endpoint to collect every
        tradeable stock symbol. Typically returns ~5,000 symbols.

        Args:
            tradeable_only: If True, only return actively tradeable stocks.

        Returns:
            List of ticker symbols.
        """
        symbols: list[str] = []
        url: str | None = f"{urls.INSTRUMENTS}/"
        params: dict[str, str] | None = (
            {"active_instruments_only": "true"} if tradeable_only else None
        )

        while url:
            data = self._session.get(url, params=params)
            params = None  # Only on first request
            for inst in data.get("results", []):
                if tradeable_only:
                    if (inst.get("tradeable")
                            and inst.get("state") == "active"
                            and inst.get("type") == "stock"):
                        symbols.append(inst["symbol"])
                else:
                    if inst.get("symbol"):
                        symbols.append(inst["symbol"])
            url = data.get("next")

        return symbols

    # ── Options ─────────────────────────────────────────────────────────

    @staticmethod
    def _is_index(symbol: str) -> bool:
        """Check if a symbol is an index option (SPX, NDX, etc.)."""
        return symbol.upper() in INDEX_CHAIN_SYMBOLS

    @staticmethod
    def _resolve_chain_symbol(symbol: str) -> str:
        """Map index symbols to the chain_symbol Robinhood expects.

        Equity options use the ticker as-is (e.g. "AAPL").
        Index options use a variant (e.g. SPX → SPXW, NDX → NDXP).
        """
        return INDEX_CHAIN_SYMBOLS.get(symbol.upper(), symbol.upper())

    def get_options_expirations(self, symbol: str) -> list[str]:
        """Get available options expiration dates for a symbol.

        Works for both equity options (AAPL, SPY) and index options (SPX, NDX, VIX, RUT).
        """
        sym = symbol.upper()

        if self._is_index(sym):
            # Index options: lookup via /indexes/, chain uses tradable_chain_ids (plural)
            idx_data = self._session.get(urls.INDEXES, params={"symbol": sym})
            idx_results = idx_data.get("results", [])
            if not idx_results:
                return []
            chain_ids = idx_results[0].get("tradable_chain_ids", [])
            if not chain_ids:
                return []
            # Use first chain ID (primary chain for major indexes)
            chains = self._session.get(
                urls.OPTIONS_CHAINS, params={"ids": sorted(chain_ids)[0]},
            )
            results = chains.get("results", [])
            if results:
                return results[0].get("expiration_dates", [])
            return []

        # Equity options: lookup via /instruments/
        inst_data = self._session.get(
            urls.INSTRUMENTS, params={"symbol": sym}
        )
        inst_results = inst_data.get("results", [])
        if not inst_results:
            return []

        inst = inst_results[0]
        inst_id = inst.get("id", "")
        if not inst_id:
            return []

        chains = self._session.get(
            urls.OPTIONS_CHAINS,
            params={"equity_instrument_ids": inst_id},
        )
        results = chains.get("results", [])
        if results and results[0].get("expiration_dates"):
            return results[0].get("expiration_dates", [])

        # Fallback: some equities return an empty chain lookup even though
        # the instrument carries a tradable chain ID and Robinhood has valid
        # expiration dates available.
        chain_id = inst.get("tradable_chain_id")
        if chain_id:
            chains = self._session.get(
                urls.OPTIONS_CHAINS,
                params={"ids": chain_id},
            )
            results = chains.get("results", [])
            if results:
                return results[0].get("expiration_dates", [])

        return []

    def get_options_chain(
        self,
        symbol: str,
        expiration: str,
        option_type: str | None = None,
    ) -> OptionsChain:
        """Get the full options chain for a symbol + expiration.

        Works for both equity options (AAPL, SPY) and index options (SPX, NDX, VIX, RUT).

        Args:
            symbol: Ticker symbol (e.g. "AAPL", "SPX").
            expiration: Expiration date (YYYY-MM-DD).
            option_type: Filter by 'call' or 'put'. None = both.
        """
        params: dict[str, str] = {
            "chain_symbol": self._resolve_chain_symbol(symbol),
            "expiration_dates": expiration,
            "state": "active",
        }
        if option_type:
            params["type"] = option_type

        instruments = self._session.get_paginated(urls.OPTIONS_INSTRUMENTS, params=params)

        # Batch fetch market data for all instruments
        calls: list[OptionContract] = []
        puts: list[OptionContract] = []

        # Get market data in batches
        # Market data endpoint requires full instrument URLs, not IDs
        inst_urls = [
            inst.get("url", "") for inst in instruments if inst.get("url")
        ]
        inst_id_map = {
            inst.get("url", ""): inst.get("id", "")
            for inst in instruments
        }
        market_data_map: dict[str, dict] = {}

        batch_size = 17  # Robinhood rejects large batches
        for i in range(0, len(inst_urls), batch_size):
            batch = inst_urls[i : i + batch_size]
            md_data = self._session.get(
                urls.OPTIONS_MARKET_DATA,
                params={"instruments": ",".join(batch)},
            )
            for item in md_data.get("results", []):
                if not item:
                    continue
                # Map by instrument_id or instrument URL
                iid = item.get("instrument_id", "")
                if iid:
                    market_data_map[iid] = item
                inst = item.get("instrument", "")
                if inst:
                    mapped_id = inst_id_map.get(inst, "")
                    if mapped_id:
                        market_data_map[mapped_id] = item

        for inst in instruments:
            inst_id = inst.get("id", "")
            md = market_data_map.get(inst_id, {})

            try:
                contract = OptionContract(
                    symbol=symbol.upper(),
                    option_type=inst.get("type", ""),
                    strike=float(inst.get("strike_price", 0)),
                    expiration=inst.get("expiration_date", expiration),
                    mark=float(md.get("adjusted_mark_price", 0) or 0),
                    bid=float(md.get("bid_price", 0) or 0),
                    ask=float(md.get("ask_price", 0) or 0),
                    # Robinhood sends null greeks on a contract's expiration
                    # day; keep them None so they can't pass for a real zero.
                    iv=_safe_float(md.get("implied_volatility")),
                    delta=_safe_float(md.get("delta")),
                    gamma=_safe_float(md.get("gamma")),
                    theta=_safe_float(md.get("theta")),
                    vega=_safe_float(md.get("vega")),
                    volume=int(md.get("volume", 0) or 0),
                    open_interest=int(md.get("open_interest", 0) or 0),
                    option_id=inst_id,
                )
            except (ValueError, TypeError):
                continue

            if contract.option_type == "call":
                calls.append(contract)
            else:
                puts.append(contract)

        return OptionsChain(
            symbol=symbol.upper(),
            expiration=expiration,
            calls=sorted(calls, key=lambda c: c.strike),
            puts=sorted(puts, key=lambda p: p.strike),
        )

    # ── Historicals ─────────────────────────────────────────────────────

    def get_stock_historicals(
        self,
        symbol: str,
        interval: str = "day",
        span: str = "year",
        bounds: str = "regular",
    ) -> list[Candle]:
        """Get historical OHLCV data for a stock.

        Args:
            symbol: Ticker symbol.
            interval: Candle interval. One of '5minute', '10minute',
                'hour', 'day', 'week'. Default: 'day'.
            span: Time range. One of 'day', 'week', 'month', '3month',
                'year', '5year'. Default: 'year'.
            bounds: Trading hours. One of 'regular', 'extended',
                'trading'. Default: 'regular'. Extended/trading
                only valid with span='day'.

        Returns:
            List of Candle dataclasses with OHLCV data.
        """
        valid_intervals = ("5minute", "10minute", "hour", "day", "week")
        valid_spans = ("day", "week", "month", "3month", "year", "5year")
        valid_bounds = ("regular", "extended", "trading")

        if interval not in valid_intervals:
            raise ValueError(
                f"interval must be one of {valid_intervals}, got '{interval}'"
            )
        if span not in valid_spans:
            raise ValueError(
                f"span must be one of {valid_spans}, got '{span}'"
            )
        if bounds not in valid_bounds:
            raise ValueError(
                f"bounds must be one of {valid_bounds}, got '{bounds}'"
            )
        if bounds in ("extended", "trading") and span != "day":
            raise ValueError(
                "extended/trading bounds can only be used with span='day'"
            )

        data = self._session.get(
            urls.HISTORICALS,
            params={
                "symbols": symbol.upper(),
                "interval": interval,
                "span": span,
                "bounds": bounds,
            },
        )

        results = data.get("results", [])
        candles: list[Candle] = []

        for item in results:
            sym = item.get("symbol", symbol.upper())
            for h in item.get("historicals", []):
                candles.append(Candle(
                    symbol=sym,
                    begins_at=h.get("begins_at", ""),
                    open_price=float(h.get("open_price", 0)),
                    close_price=float(h.get("close_price", 0)),
                    high_price=float(h.get("high_price", 0)),
                    low_price=float(h.get("low_price", 0)),
                    volume=int(h.get("volume", 0)),
                    session=h.get("session", "reg"),
                    interpolated=h.get("interpolated", False),
                ))

        return candles

    def get_stock_historicals_batch(
        self,
        symbols: list[str],
        interval: str = "day",
        span: str = "year",
        bounds: str = "regular",
    ) -> dict[str, list[Candle]]:
        """Get historical data for multiple stocks in one request.

        Args:
            symbols: List of ticker symbols.
            interval: Candle interval. Default: 'day'.
            span: Time range. Default: 'year'.
            bounds: Trading hours. Default: 'regular'.

        Returns:
            Dict mapping symbol to list of Candle dataclasses.
        """
        data = self._session.get(
            urls.HISTORICALS,
            params={
                "symbols": ",".join(s.upper() for s in symbols),
                "interval": interval,
                "span": span,
                "bounds": bounds,
            },
        )

        result: dict[str, list[Candle]] = {}
        for item in data.get("results", []):
            sym = item.get("symbol", "")
            candles = []
            for h in item.get("historicals", []):
                candles.append(Candle(
                    symbol=sym,
                    begins_at=h.get("begins_at", ""),
                    open_price=float(h.get("open_price", 0)),
                    close_price=float(h.get("close_price", 0)),
                    high_price=float(h.get("high_price", 0)),
                    low_price=float(h.get("low_price", 0)),
                    volume=int(h.get("volume", 0)),
                    session=h.get("session", "reg"),
                    interpolated=h.get("interpolated", False),
                ))
            if sym:
                result[sym] = candles

        return result

    # ── Earnings ────────────────────────────────────────────────────────

    def get_earnings(
        self, symbol: str, lookahead_days: int = 14
    ) -> Earnings | None:
        """Get upcoming earnings for a symbol within lookahead window."""
        data = self._session.get(urls.EARNINGS, params={"symbol": symbol.upper()})
        results = data.get("results", []) if isinstance(data, dict) else []

        today = datetime.now().strftime("%Y-%m-%d")
        cutoff = (datetime.now() + timedelta(days=lookahead_days)).strftime("%Y-%m-%d")

        for entry in results:
            report = entry.get("report") or {}
            if not isinstance(report, dict):
                continue

            eps = entry.get("eps") or {}
            if not isinstance(eps, dict):
                eps = {}

            date = report.get("date", "")
            if today <= date <= cutoff:
                return Earnings(
                    symbol=symbol.upper(),
                    date=date,
                    timing=report.get("timing"),
                    eps_estimate=_safe_float(eps.get("estimate")),
                    eps_actual=_safe_float(eps.get("actual")),
                )
        return None

    # ── Research / Discovery ─────────────────────────────────────────

    def get_ratings(self, symbol: str) -> Rating:
        """Get analyst buy/hold/sell ratings for a symbol."""
        instrument = self._get_instrument_url(symbol)
        instrument_id = instrument.rstrip("/").split("/")[-1]
        data = self._session.get(f"{urls.RATINGS}{instrument_id}/")
        summary = data.get("summary", {})
        return Rating(
            symbol=symbol.upper(),
            num_buy=int(summary.get("num_buy_ratings", 0)),
            num_hold=int(summary.get("num_hold_ratings", 0)),
            num_sell=int(summary.get("num_sell_ratings", 0)),
            published_at=data.get("ratings_published_at") or "",
            price_target_high=_safe_float(summary.get("high_price_target")),
            price_target_low=_safe_float(summary.get("low_price_target")),
            price_target_mean=_safe_float(summary.get("mean_price_target")),
        )

    def get_news(self, symbol: str, resolve_symbols: bool = True) -> list[NewsArticle]:
        """Get news articles for a symbol.

        Args:
            symbol: Ticker to fetch news for.
            resolve_symbols: Resolve each article's related instrument IDs to
                ticker symbols. Costs one extra request per unique instrument
                (cached per call). Set False to get the raw IDs back instead.
        """
        data = self._session.get(urls.NEWS, params={"symbol": symbol.upper()})
        results = data.get("results", []) if isinstance(data, dict) else []
        # Cache instrument ID/URL -> symbol lookups to avoid repeated requests
        symbol_cache: dict[str, str] = {}
        return [
            NewsArticle(
                title=item.get("title", ""),
                source=item.get("source", ""),
                url=item.get("url", ""),
                published_at=item.get("published_at", ""),
                summary=item.get("summary", ""),
                related_instruments=self._related_symbols(
                    item.get("related_instruments", []), symbol_cache, resolve_symbols
                ),
            )
            for item in results
        ]

    def get_movers(self, direction: str = "up") -> list[Mover]:
        """Get S&P 500 top movers.

        Args:
            direction: 'up' or 'down'.
        """
        data = self._session.get(urls.MOVERS_SP500, params={"direction": direction})
        results = data.get("results", []) if isinstance(data, dict) else []
        movers: list[Mover] = []
        for item in results:
            instrument_url = item.get("instrument_url", "")
            # The mover carries its symbol. Older responses did not, and
            # for those the instrument is looked up.
            symbol = item.get("symbol", "")
            if not symbol and instrument_url:
                try:
                    inst = self._session.get(instrument_url)
                    symbol = inst.get("symbol", "")
                except Exception:
                    pass
            movement = item.get("price_movement", {})
            pct = float(movement.get("market_hours_last_movement_pct", 0) or 0)
            price = _safe_float(movement.get("market_hours_last_price"))
            change = None
            if price is not None and pct > -100:
                # price is after the move: before it was price / (1 + pct/100).
                change = round(price - price / (1 + pct / 100), 4)
            movers.append(Mover(
                symbol=symbol,
                price_change=change,
                price_change_pct=pct,
                instrument_url=instrument_url,
                price=price,
            ))
        return movers

    def get_tags(self, tag: str) -> list[str]:
        """Deprecated — Robinhood retired this endpoint.

        Raises:
            APIError: Always. `/midlands/tags/tag/<tag>/` returns 404 for
                every tag as of 2026-11-19.

        The Robinhood lists you follow in the app, such as its most popular
        list, come back from `get_watchlists()` with their symbols.
        """
        from pyhood.exceptions import APIError

        raise APIError(
            "get_tags() is no longer available: Robinhood retired "
            "/midlands/tags/tag/ and it returns 404 for every tag. The "
            "Robinhood lists you follow in the app are returned by "
            "get_watchlists()."
        )

    def get_popularity(self, symbol: str) -> int:
        """Deprecated — Robinhood retired this endpoint.

        Raises:
            APIError: Always. `/instruments/<id>/popularity/` returns 404 as
                of 2026-11-19, and pyhood knows of no replacement.
        """
        from pyhood.exceptions import APIError

        raise APIError(
            "get_popularity() is no longer available: Robinhood retired "
            "/instruments/<id>/popularity/ and it returns 404. There is no "
            "replacement."
        )

    def get_splits(self, symbol: str) -> list[StockSplit]:
        """Get stock split history for a symbol."""
        instrument = self._get_instrument_url(symbol)
        instrument_id = instrument.rstrip("/").split("/")[-1]
        url = urls.SPLITS.format(instrument_id=instrument_id)
        data = self._session.get(url)
        results = data.get("results", []) if isinstance(data, dict) else []
        return [
            StockSplit(
                instrument=item.get("instrument", ""),
                execution_date=item.get("execution_date", ""),
                multiplier=float(item.get("multiplier", 0)),
                divisor=float(item.get("divisor", 0)),
            )
            for item in results
        ]

    # ── Portfolio Historicals ─────────────────────────────────────────

    def get_portfolio_historicals(
        self,
        account_number: str | None = None,
        interval: str = "day",
        span: str = "year",
        bounds: str = "regular",
    ) -> list[PortfolioCandle]:
        """Deprecated — Robinhood retired this endpoint.

        Raises:
            APIError: Always. `/portfolios/historicals/` returns 404 for every
                parameter combination as of 2026-08-09.

        Use `get_portfolio_performance()` instead. It is not a drop-in: the
        replacement returns a chart view model whose y values are returns
        rather than equity, so it cannot be mapped onto `PortfolioCandle`
        without inventing the equity figures.
        """
        from pyhood.exceptions import APIError

        raise APIError(
            "get_portfolio_historicals() is no longer available: Robinhood "
            "retired /portfolios/historicals/ and it returns 404. Use "
            "get_portfolio_performance(), which returns the chart view model "
            "that replaced it."
        )

    def get_portfolio_performance(self, account_number: str | None = None) -> dict:
        """Get the portfolio performance chart.

        Replaces `get_portfolio_historicals()`, whose endpoint Robinhood
        retired.

        Args:
            account_number: Account number. If None, uses the first account.

        Returns:
            The raw chart view model: `lines` of plotted points with
            `x_axis`, `y_axis`, `legend_data`, `fills` and `overlays`.

        Note:
            Returned unmapped on purpose. This is a rendering payload rather
            than a time series — the y values are returns, not equity, and
            each point carries display labels. Forcing it onto a dataclass
            would mean inventing figures the endpoint does not provide.
        """
        if not account_number:
            accounts = self._session.get_paginated(urls.ACCOUNTS)
            if not accounts:
                return {}
            account_number = accounts[0].get("account_number", "")

        return self._session.get(urls.portfolio_performance_url(account_number))

    # ── Option Historicals ────────────────────────────────────────────

    def get_option_historicals(
        self,
        option_id: str,
        interval: str = "day",
        span: str = "year",
    ) -> list[Candle]:
        """Get historical pricing data for an option contract.

        Args:
            option_id: Option instrument ID.
            interval: 'day', 'week', 'hour', '5minute', '10minute'.
            span: 'day', 'week', 'month', '3month', 'year'.
        """
        data = self._session.get(
            f"{urls.OPTIONS_HISTORICALS}{option_id}/",
            params={"interval": interval, "span": span},
        )
        results = data.get("data_points", []) if isinstance(data, dict) else []
        return [
            Candle(
                symbol=option_id,
                begins_at=item.get("begins_at", ""),
                open_price=float(item.get("open_price", 0)),
                close_price=float(item.get("close_price", 0)),
                high_price=float(item.get("high_price", 0)),
                low_price=float(item.get("low_price", 0)),
                volume=int(item.get("volume", 0)),
            )
            for item in results
        ]

    # ── Documents ─────────────────────────────────────────────────────

    def get_documents(self, doc_type: str | None = None) -> list[Document]:
        """Get account documents (statements, confirmations, tax docs).

        Args:
            doc_type: Filter by type (e.g. 'account_statement', 'trade_confirm').
                If None, returns all documents.
        """
        params: dict[str, str] = {}
        if doc_type:
            params["type"] = doc_type
        data = self._session.get_paginated(urls.DOCUMENTS, params=params)
        return [
            Document(
                id=item.get("id", ""),
                type=item.get("type", ""),
                date=item.get("date", item.get("created_at", "")),
                url=item.get("url", ""),
                download_url=item.get("download_url", ""),
            )
            for item in data
        ]

    def download_document(self, document_id: str, directory: str | Path = ".") -> Path:
        """Download one account document as a PDF.

        Args:
            document_id: The document's `id`, from `get_documents()`.
            directory: Folder to save into. Created if missing, readable
                only by you, since a statement shows your account.

        Returns:
            The path of the saved file, named for the document's date and
            type, such as `2026-10-31_account_statement.pdf`.

        Raises:
            SymbolNotFound: If no document has that ID.
            APIError: If the download fails or is not a PDF.
        """
        from pyhood.exceptions import APIError
        from pyhood.secure_files import ensure_private_dir

        document = next((d for d in self.get_documents() if d.id == document_id), None)
        if document is None:
            raise SymbolNotFound(f"No document has the ID {document_id}")
        if not document.download_url:
            raise APIError(f"Document {document_id} has no download link")

        content = self._session.get_bytes(document.download_url)
        if not content.startswith(b"%PDF"):
            raise APIError(f"Document {document_id} did not download as a PDF")

        folder = Path(directory).expanduser()
        ensure_private_dir(folder)
        stem = f"{(document.date or 'undated')[:10]}_{document.type or 'document'}"
        path = folder / f"{stem}.pdf"
        if path.exists() and path.read_bytes() != content:
            # Two documents of one type on one day, such as two trade
            # confirmations: keep both.
            path = folder / f"{stem}_{document_id[:8]}.pdf"
        path.write_bytes(content)
        try:
            path.chmod(0o600)
        except OSError:  # pragma: no cover - platform dependent
            pass
        return path

    # ── Day Trades / Margin ──────────────────────────────────────────

    def get_day_trades(self, account_id: str | None = None) -> list[dict]:
        """Get recent day trade history.

        Args:
            account_id: Account ID. If None, uses first account.
        """
        if not account_id:
            accounts = self._session.get_paginated(urls.ACCOUNTS)
            if not accounts:
                return []
            account_id = accounts[0].get("url", "").rstrip("/").split("/")[-1]

        url = urls.DAY_TRADES.format(account_id=account_id)
        data = self._session.get(url)
        return data.get("equity_day_trades", []) if isinstance(data, dict) else []

    def get_margin_calls(self) -> list[dict]:
        """Get active margin calls."""
        data = self._session.get_paginated(urls.MARGIN_CALLS)
        return data

    def get_deposit_schedules(self) -> list[dict]:
        """Get all scheduled recurring deposits."""
        data = self._session.get_paginated(urls.ACH_DEPOSIT_SCHEDULES)
        return data

    # ── Settings / Notifications ──────────────────────────────────────

    def get_user_profile(self) -> UserProfile:
        """Get the authenticated user's profile."""
        data = self._session.get(urls.USER)
        return UserProfile(
            username=data.get("username", ""),
            email=data.get("email", ""),
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            id=data.get("id", ""),
            created_at=data.get("created_at", ""),
        )

    def get_notification_settings(self) -> NotificationSettings:
        """Deprecated — Robinhood retired this endpoint.

        Raises:
            APIError: Always. `/settings/notifications/` returns 404 as of
                2026-11-19, and pyhood knows of no replacement.
        """
        from pyhood.exceptions import APIError

        raise APIError(
            "get_notification_settings() is no longer available: Robinhood "
            "retired /settings/notifications/ and it returns 404. There is "
            "no replacement."
        )

    def update_notification_settings(self, **kwargs: bool) -> NotificationSettings:
        """Deprecated — Robinhood retired this endpoint.

        Raises:
            APIError: Always, before anything is sent. See
                `get_notification_settings()`.
        """
        from pyhood.exceptions import APIError

        raise APIError(
            "update_notification_settings() is no longer available: "
            "Robinhood retired /settings/notifications/ and it returns 404. "
            "There is no replacement."
        )

    # ── Banking / ACH ─────────────────────────────────────────────────

    def get_bank_accounts(self) -> list[BankAccount]:
        """Get all linked bank accounts."""
        data = self._session.get_paginated(urls.ACH_RELATIONSHIPS)
        return [
            BankAccount(
                id=item.get("id", ""),
                holder_name=item.get("bank_account_holder_name", ""),
                account_type=item.get("bank_account_type", ""),
                account_nickname=item.get("bank_account_nickname", ""),
                state=item.get("state", ""),
                url=item.get("url", ""),
                last_four=str(item.get("bank_account_number") or "")[-4:],
            )
            for item in data
        ]

    def get_transfers(self) -> list[ACHTransfer]:
        """Get all ACH transfers (deposits and withdrawals)."""
        data = self._session.get_paginated(urls.ACH_TRANSFERS)
        return [
            ACHTransfer(
                id=item.get("id", ""),
                amount=float(item.get("amount", 0)),
                direction=item.get("direction", ""),
                state=item.get("state", ""),
                created_at=item.get("created_at", ""),
                expected_landing_date=item.get("expected_landing_date", ""),
                ach_relationship=item.get("ach_relationship", ""),
            )
            for item in data
        ]

    def initiate_transfer(
        self, amount: float, direction: str, ach_relationship_url: str,
    ) -> ACHTransfer:
        """Initiate an ACH transfer (deposit or withdrawal).

        Args:
            amount: Dollar amount to transfer.
            direction: 'deposit' or 'withdraw'.
            ach_relationship_url: URL of the linked bank account.
        """
        data = self._session.post(urls.ACH_TRANSFERS, data={
            "amount": f"{amount:.2f}",
            "direction": direction,
            "ach_relationship": ach_relationship_url,
        })
        return ACHTransfer(
            id=data.get("id", ""),
            amount=float(data.get("amount", 0)),
            direction=data.get("direction", ""),
            state=data.get("state", ""),
            created_at=data.get("created_at", ""),
            expected_landing_date=data.get("expected_landing_date", ""),
            ach_relationship=data.get("ach_relationship", ""),
        )

    def cancel_transfer(self, transfer_id: str) -> dict:
        """Cancel a pending ACH transfer."""
        return self._session.post(f"{urls.ACH_TRANSFERS}{transfer_id}/cancel/")

    # ── Debit Card ────────────────────────────────────────────────────

    def get_card_transactions(
        self, card_type: str | None = None,
    ) -> list[CardTransaction]:
        """Get debit card (Cash Management) transactions.

        Args:
            card_type: Filter by type — 'pending' or 'settled'.
        """
        params: dict[str, str] = {}
        if card_type:
            params["type"] = card_type
        data = self._session.get_paginated(
            urls.CARD_TRANSACTIONS, params=params or None,
        )
        return [
            CardTransaction(
                id=item.get("id", ""),
                description=item.get("description", ""),
                amount=float(item.get("amount", 0)),
                category=item.get("category", ""),
                direction=item.get("direction", ""),
                state=item.get("state", ""),
                initiated_at=item.get("initiated_at", ""),
                completed_at=item.get("completed_at", ""),
                merchant=item.get("merchant", {}).get("name", "")
                if isinstance(item.get("merchant"), dict)
                else item.get("merchant", ""),
            )
            for item in data
        ]

    # ── Watchlists ────────────────────────────────────────────────────

    def get_watchlists(self) -> list[Watchlist]:
        """Get your watchlists with their symbols.

        Returns the lists the app shows: the ones you created and the
        Robinhood lists you follow. Makes one request for the lists and one
        more for each list that has anything in it.
        """
        return [self._watchlist(record) for record in self._watchlist_records()]

    def get_watchlist(self, name: str = "My First List") -> Watchlist:
        """Get a single watchlist by name.

        Args:
            name: Watchlist name, matched without regard to case. Defaults
                to 'My First List', the list every account starts with.

        Raises:
            SymbolNotFound: If you have no list by that name.
        """
        return self._watchlist(self._find_watchlist(name))

    def add_to_watchlist(self, symbols: list[str], name: str = "My First List") -> dict:
        """Add stocks to a watchlist.

        Args:
            symbols: Stock symbols to add.
            name: Watchlist name (default: 'My First List').

        Returns:
            Robinhood's raw response.

        Raises:
            SymbolNotFound: If the list or any symbol is not found. Nothing
                is added in that case.
        """
        return self._change_watchlist(symbols, name, "create")

    def remove_from_watchlist(
        self, symbols: list[str], name: str = "My First List",
    ) -> dict:
        """Remove stocks from a watchlist.

        Args:
            symbols: Stock symbols to remove.
            name: Watchlist name (default: 'My First List').

        Returns:
            Robinhood's raw response.

        Raises:
            SymbolNotFound: If the list or any symbol is not found. Nothing
                is removed in that case.
        """
        return self._change_watchlist(symbols, name, "delete")

    def _watchlist_records(self) -> list[dict]:
        """The raw list records, without their items."""
        return self._session.get_paginated(urls.WATCHLISTS)

    def _find_watchlist(self, name: str) -> dict:
        records = self._watchlist_records()
        for record in records:
            if record.get("display_name", "").lower() == name.lower():
                return record
        names = ", ".join(repr(r.get("display_name", "")) for r in records) or "none"
        raise SymbolNotFound(f"Watchlist not found: {name!r}. Your lists: {names}")

    def _watchlist(self, record: dict) -> Watchlist:
        """Build a Watchlist from a list record, fetching its symbols."""
        list_id = record.get("id", "")
        symbols: list[str] = []
        # The list record says how many items it has, so an empty list
        # needs no second request.
        if list_id and record.get("item_count") != 0:
            data = self._session.get(
                urls.WATCHLIST_ITEMS,
                # Without load_all_attributes=false Robinhood adds live
                # prices to every item, and rejects the request outright
                # for an options watchlist.
                params={"list_id": list_id, "load_all_attributes": "false"},
            )
            items = data.get("results", []) if isinstance(data, dict) else []
            symbols = [item["symbol"] for item in items if item.get("symbol")]
        return Watchlist(name=record.get("display_name", ""), symbols=symbols, id=list_id)

    def _change_watchlist(self, symbols: list[str], name: str, operation: str) -> dict:
        """Add ('create') or remove ('delete') stocks on a watchlist."""
        watchlist = self._find_watchlist(name)
        # Resolve every symbol first, so a bad one raises before anything
        # is changed.
        changes = [
            {
                "object_type": "instrument",
                "object_id": self._get_instrument_url(symbol).rstrip("/").split("/")[-1],
                "operation": operation,
            }
            for symbol in symbols
        ]
        return self._session.post(
            urls.WATCHLIST_ITEMS, json_data={watchlist["id"]: changes},
        )

    # ── Markets ───────────────────────────────────────────────────────

    def get_markets(self) -> list[Market]:
        """Get all available stock exchanges/markets."""
        data = self._session.get_paginated(urls.MARKETS)
        return [
            Market(
                mic=item.get("mic", ""),
                name=item.get("name", ""),
                city=item.get("city", ""),
                country=item.get("country", ""),
                acronym=item.get("acronym", ""),
                timezone=item.get("timezone", ""),
                url=item.get("url", ""),
            )
            for item in data
        ]

    def get_market_hours(self, market: str, date: str) -> MarketHours:
        """Get trading hours for a market on a specific date.

        Args:
            market: Market MIC code (e.g. 'XNYS' for NYSE, 'XNAS' for Nasdaq).
            date: Date string in YYYY-MM-DD format.
        """
        url = urls.MARKET_HOURS.format(market=market, date=date)
        data = self._session.get(url)
        return MarketHours(
            date=data.get("date", date),
            is_open=data.get("is_open", False),
            opens_at=data.get("opens_at", "") or "",
            closes_at=data.get("closes_at", "") or "",
            extended_opens_at=data.get("extended_opens_at", "") or "",
            extended_closes_at=data.get("extended_closes_at", "") or "",
        )

    def is_market_open(
        self, market: str = "XNAS", extended_hours: bool = False,
    ) -> bool:
        """Whether the market is open for trading right now.

        Args:
            market: Market MIC code. Defaults to 'XNAS' (Nasdaq).
            extended_hours: Check the extended session rather than the
                regular one.

        Returns:
            True if trading is open now. False on weekends, holidays, and
            outside session hours.

        Note:
            An order placed while closed is accepted and queued rather than
            rejected — it executes at the next open. Check this first if that
            distinction matters.
        """
        now = datetime.now(timezone.utc)
        # The trading date is the market's local date, which differs from the
        # UTC date during the evening in New York.
        local_date = now.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")

        hours = self.get_market_hours(market, local_date)
        if not hours.is_open:
            return False

        opens = hours.extended_opens_at if extended_hours else hours.opens_at
        closes = hours.extended_closes_at if extended_hours else hours.closes_at
        if not opens or not closes:
            return False

        try:
            opens_dt = datetime.fromisoformat(opens.replace("Z", "+00:00"))
            closes_dt = datetime.fromisoformat(closes.replace("Z", "+00:00"))
        except ValueError:
            return False

        return opens_dt <= now <= closes_dt

    # ── Dividends ──────────────────────────────────────────────────────

    def get_dividends(self) -> list[Dividend]:
        """Get all dividend payments."""
        data = self._session.get_paginated(urls.DIVIDENDS)
        dividends: list[Dividend] = []
        # Cache instrument URL -> symbol lookups to avoid repeated requests
        symbol_cache: dict[str, str] = {}
        for item in data:
            instrument_url = item.get("instrument", "")
            symbol = symbol_cache.get(instrument_url, "")
            if not symbol and instrument_url:
                try:
                    inst = self._session.get(instrument_url)
                    symbol = inst.get("symbol", "")
                    symbol_cache[instrument_url] = symbol
                except Exception:
                    pass

            dividends.append(Dividend(
                symbol=symbol,
                amount=float(item.get("amount", 0)),
                rate=float(item.get("rate", 0)),
                payable_date=item.get("payable_date", ""),
                record_date=item.get("record_date", ""),
                state=item.get("state", ""),
                instrument_url=instrument_url,
                id=item.get("id", ""),
            ))
        return dividends

    def get_dividends_by_symbol(self, symbol: str) -> list[Dividend]:
        """Get dividend payments for a specific symbol."""
        return [d for d in self.get_dividends() if d.symbol.upper() == symbol.upper()]

    # ── Account ─────────────────────────────────────────────────────────

    def get_all_accounts(self) -> list[dict]:
        """Get all accounts including IRA via bonfire unified endpoint.

        The standard /accounts/ endpoint never returns IRA accounts.
        This uses the bonfire API which returns all account types.
        """
        data = self._session.get("https://bonfire.robinhood.com/accounts/unified/")
        return data.get("results", [])

    def get_positions(
        self, nonzero: bool = True, account_number: str | None = None,
    ) -> list[Position]:
        """Get current stock positions.

        Args:
            nonzero: Only return positions with quantity > 0.
            account_number: Filter to a specific account (e.g. IRA).
        """
        params: dict[str, str] = {}
        if nonzero:
            params["nonzero"] = "true"
        if account_number:
            params["account_number"] = account_number
        data = self._session.get_paginated(urls.POSITIONS, params=params)

        positions: list[Position] = []
        for item in data:
            qty = float(item.get("quantity", 0))
            if qty == 0 and nonzero:
                continue
            # average_buy_price is 0 on positions the clearing system has
            # settled; clearing_average_cost carries the real figure and is
            # what the app displays.
            avg_cost = float(item.get("average_buy_price", 0) or 0)
            if not avg_cost:
                avg_cost = float(item.get("clearing_average_cost", 0) or 0)

            # The payload carries the symbol, so no instrument lookup is needed.
            symbol = item.get("symbol", "")
            current_price = 0.0
            instrument_url = item.get("instrument", "")
            try:
                if not symbol and instrument_url:
                    symbol = self._session.get(instrument_url).get("symbol", "")
                if symbol:
                    current_price = self.get_quote(symbol).price
            except Exception:
                pass

            equity = qty * current_price
            # Prefer the broker's own cost basis; it accounts for lots and
            # corporate actions that quantity x average price does not.
            cost_basis = float(item.get("clearing_cost_basis", 0) or 0) or qty * avg_cost
            unrealized_pl = equity - cost_basis
            unrealized_pl_pct = (unrealized_pl / cost_basis * 100) if cost_basis > 0 else 0.0

            positions.append(Position(
                symbol=symbol,
                quantity=qty,
                average_cost=avg_cost,
                current_price=current_price,
                equity=round(equity, 2),
                unrealized_pl=round(unrealized_pl, 2),
                unrealized_pl_pct=round(unrealized_pl_pct, 2),
            ))

        return positions

    def get_option_positions(
        self, account_number: str | None = None, nonzero: bool = True,
    ) -> list[OptionPosition]:
        """Get current option positions with fully resolved details.

        Uses aggregate_positions endpoint which returns symbol, strike, expiry
        in the legs data. Also fetches current market data for P&L and greeks.

        Args:
            account_number: Filter to a specific account, e.g. an IRA account number.
            nonzero: Only return positions with quantity > 0.
        """
        params: dict[str, str] = {}
        if nonzero:
            params["nonzero"] = "true"
        if account_number:
            params["account_numbers"] = account_number  # NOTE: plural for options endpoint

        raw_positions = list(self._session.get_paginated(
            "https://api.robinhood.com/options/aggregate_positions/",
            params=params,
        ))

        positions: list[OptionPosition] = []
        for pos in raw_positions:
            qty = int(float(pos.get("quantity", 0)))
            if qty == 0 and nonzero:
                continue

            symbol = pos.get("symbol", "")
            strategy = pos.get("strategy", "")
            # API returns per-contract, convert to per-share
            avg_open = float(pos.get("average_open_price", 0)) / 100

            # Extract details from legs
            legs = pos.get("legs", [])
            if not legs:
                continue

            leg = legs[0]  # Primary leg
            strike = float(leg.get("strike_price", 0))
            expiration = leg.get("expiration_date", "")
            option_type = leg.get("option_type", "")
            option_id = leg.get("option_id", "")
            cost_basis = float(leg.get("clearing_cost_basis_in_strategy", 0))

            # Fetch current market data
            current_mark = 0.0
            delta: float | None = None
            iv: float | None = None
            theta: float | None = None
            if option_id:
                try:
                    md = self._session.get(
                        f"https://api.robinhood.com/marketdata/options/{option_id}/"
                    )
                    current_mark = float(md.get("mark_price", 0))
                    delta = _safe_float(md.get("delta"))
                    iv = _safe_float(md.get("implied_volatility"))
                    theta = _safe_float(md.get("theta"))
                except Exception:
                    pass

            current_value = current_mark * qty * 100
            unrealized_pl = current_value - cost_basis
            unrealized_pl_pct = (unrealized_pl / cost_basis * 100) if cost_basis > 0 else 0.0

            positions.append(OptionPosition(
                symbol=symbol,
                option_type=option_type,
                strike=strike,
                expiration=expiration,
                quantity=qty,
                average_open_price=avg_open,
                cost_basis=cost_basis,
                current_mark=current_mark,
                current_value=round(current_value, 2),
                unrealized_pl=round(unrealized_pl, 2),
                unrealized_pl_pct=round(unrealized_pl_pct, 2),
                strategy=strategy,
                option_id=option_id,
                account_number=account_number or "",
                delta=delta,
                iv=iv,
                theta=theta,
            ))

        return positions

    def get_buying_power(self, account_number: str | None = None) -> float:
        """Get available buying power.

        Args:
            account_number: Specific account number (e.g. IRA account).
                If provided, fetches directly from the account URL
                (bypasses /accounts/ which doesn't show IRA accounts).
        """
        if account_number:
            data = self._session.get(
                f"https://api.robinhood.com/accounts/{account_number}/"
            )
            return float(data.get("buying_power", 0))

        data = self._session.get_paginated(urls.ACCOUNTS)
        if data:
            return float(data[0].get("buying_power", 0))
        return 0.0

    # ── Orders ──────────────────────────────────────────────────────────

    def _get_account_url(self, account_number: str | None = None) -> str:
        """Get the account URL.

        If account_number is provided, constructs the URL directly
        (bypasses /accounts/ which doesn't show IRA accounts).
        Otherwise falls back to the first account from /accounts/.
        """
        if account_number:
            return f"https://api.robinhood.com/accounts/{account_number}/"

        data = self._session.get_paginated(urls.ACCOUNTS)
        if not data:
            raise OrderError("No accounts found")
        return data[0].get("url", "")

    @staticmethod
    def _parse_start_date(start_date: str | datetime | None) -> datetime | None:
        """Normalize a start_date into an aware UTC datetime.

        Accepts a datetime or an ISO-8601 string ('2026-01-01' or a full
        timestamp). Naive values are treated as UTC.
        """
        if start_date is None:
            return None
        if isinstance(start_date, datetime):
            dt = start_date
        else:
            try:
                dt = datetime.fromisoformat(str(start_date).replace("Z", "+00:00"))
            except ValueError as e:
                raise ValueError(
                    f"start_date must be a datetime or ISO-8601 string, got {start_date!r}"
                ) from e
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _start_date_params(cutoff: datetime | None) -> dict[str, str] | None:
        """Server-side filter params for an order-history cutoff."""
        if cutoff is None:
            return None
        return {"created_at[gte]": cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")}

    @staticmethod
    def _before_cutoff(created_at: str, cutoff: datetime | None) -> bool:
        """True if an order predates the cutoff and should be dropped.

        Applied client-side as a safety net: not every orders endpoint is
        confirmed to honour created_at[gte], and an ignored filter would
        otherwise return silently unfiltered results. Unparseable timestamps
        are kept rather than dropped.
        """
        if cutoff is None or not created_at:
            return False
        try:
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            return False
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt < cutoff

    def _related_symbols(
        self, entries: Any, symbol_cache: dict[str, str], resolve: bool = True
    ) -> list[str]:
        """Normalize a news article's related_instruments into symbols.

        Robinhood returns bare instrument IDs here, but the endpoint has also
        been seen returning dicts with a 'symbol' key and instrument URLs, so
        all three are accepted. IDs and URLs are resolved via the instruments
        endpoint; anything else is treated as an already-resolved symbol.

        With resolve=False, IDs and URLs are returned as-is and no extra
        requests are made.
        """
        if not isinstance(entries, list):
            return []

        symbols: list[str] = []
        for entry in entries:
            symbol = ""
            if isinstance(entry, dict):
                symbol = entry.get("symbol", "")
            elif isinstance(entry, str) and (
                entry.startswith("http") or _INSTRUMENT_ID_RE.fullmatch(entry)
            ):
                if not resolve:
                    symbol = entry
                else:
                    symbol = symbol_cache.get(entry, "")
                    if not symbol:
                        url = entry if entry.startswith("http") else f"{urls.INSTRUMENTS}{entry}/"
                        try:
                            inst = self._session.get(url)
                            symbol = inst.get("symbol", "")
                            symbol_cache[entry] = symbol
                        except Exception:
                            pass
            elif isinstance(entry, str):
                symbol = entry
            if symbol:
                symbols.append(symbol)
        return symbols

    def _get_instrument_url(self, symbol: str) -> str:
        """Get instrument URL from INSTRUMENTS endpoint."""
        data = self._session.get(urls.INSTRUMENTS, params={"symbol": symbol.upper()})
        results = data.get("results", [])
        if not results:
            raise SymbolNotFound(f"Instrument not found for symbol: {symbol}")
        return results[0].get("url", "")

    def _get_option_id(self, symbol: str, expiration: str, strike: float, option_type: str) -> str:
        """Find option instrument ID. Works for equity and index options."""
        params = {
            "chain_symbol": self._resolve_chain_symbol(symbol),
            "expiration_dates": expiration,
            "type": option_type.lower(),
            "strike_price": str(strike),
            "state": "active",
        }
        instruments = self._session.get_paginated(urls.OPTIONS_INSTRUMENTS, params=params)

        if not instruments:
            raise SymbolNotFound(
                f"Option not found: {symbol} {expiration} ${strike} {option_type}"
            )

        return instruments[0].get("url", "")

    def buy_stock(
        self,
        symbol: str,
        quantity: float,
        price: float | None = None,
        stop_price: float | None = None,
        time_in_force: str = "gtc",
        extended_hours: bool = False,
        trail_amount: float | None = None,
        trail_percent: float | None = None,
        market_hours: str | None = None,
        account_number: str | None = None,
    ) -> Order:
        """Buy stock shares.

        Args:
            symbol: Stock ticker symbol.
            quantity: Number of shares to buy.
            price: Limit price. If None, places market order.
            stop_price: Stop price for stop/stop-limit orders.
            time_in_force: 'gtc' (good till cancelled), 'gfd' (good for day), 'ioc', 'fok'.
            extended_hours: Whether to allow extended hours trading.
            account_number: Specific account (e.g. IRA). None = default.

        Returns:
            Order object with details.
        """
        return self.order_stock(
            symbol=symbol,
            quantity=quantity,
            side="buy",
            price=price,
            stop_price=stop_price,
            time_in_force=time_in_force,
            extended_hours=extended_hours,
            account_number=account_number,
            trail_amount=trail_amount,
            trail_percent=trail_percent,
            market_hours=market_hours,
        )

    def sell_stock(
        self,
        symbol: str,
        quantity: float,
        price: float | None = None,
        stop_price: float | None = None,
        time_in_force: str = "gtc",
        extended_hours: bool = False,
        trail_amount: float | None = None,
        trail_percent: float | None = None,
        market_hours: str | None = None,
        account_number: str | None = None,
    ) -> Order:
        """Sell stock shares.

        Args:
            symbol: Stock ticker symbol.
            quantity: Number of shares to sell.
            price: Limit price. If None, places market order.
            stop_price: Stop price for stop/stop-limit orders.
            time_in_force: 'gtc' (good till cancelled), 'gfd' (good for day), 'ioc', 'fok'.
            extended_hours: Whether to allow extended hours trading.
            account_number: Specific account (e.g. IRA). None = default.

        Returns:
            Order object with details.
        """
        return self.order_stock(
            symbol=symbol,
            quantity=quantity,
            side="sell",
            price=price,
            stop_price=stop_price,
            time_in_force=time_in_force,
            extended_hours=extended_hours,
            account_number=account_number,
            trail_amount=trail_amount,
            trail_percent=trail_percent,
            market_hours=market_hours,
        )

    def order_stock(
        self,
        symbol: str,
        quantity: float,
        side: str,
        price: float | None = None,
        stop_price: float | None = None,
        time_in_force: str = "gtc",
        extended_hours: bool = False,
        account_number: str | None = None,
        trail_amount: float | None = None,
        trail_percent: float | None = None,
        market_hours: str | None = None,
    ) -> Order:
        """Place a stock order (core method).

        Args:
            symbol: Stock ticker symbol.
            quantity: Number of shares.
            side: 'buy' or 'sell'.
            price: Limit price. If None, places market order.
            stop_price: Stop price for stop/stop-limit orders.
            time_in_force: 'gtc' (good till cancelled), 'gfd' (good for day), 'ioc', 'fok'.
            extended_hours: Whether to allow extended hours trading.
            account_number: Specific account (e.g. IRA). None = default.
            trail_amount: Trail by a dollar amount, for a trailing stop.
            trail_percent: Trail by a percentage, for a trailing stop.
                Note that Robinhood currently blocks trailing stops for
                third-party clients — see the module docs.
            market_hours: Trading session — 'regular_hours', 'extended_hours'
                or 'all_day_hours'. Defaults to regular hours. Anything other
                than regular hours sets extended_hours automatically; the two
                must agree or Robinhood rejects the order.

        Returns:
            Order object with details.

        Raises:
            OrderError: If both trail_amount and trail_percent are given.
        """
        if trail_amount is not None and trail_percent is not None:
            raise OrderError("Pass trail_amount or trail_percent, not both")

        valid_sessions = ("regular_hours", "extended_hours", "all_day_hours")
        if market_hours is not None and market_hours not in valid_sessions:
            raise OrderError(f"market_hours must be one of {valid_sessions}")

        if market_hours is not None:
            # Robinhood rejects a session that disagrees with extended_hours
            # ("Extended hours and market hours mismatch"), so derive it.
            extended_hours = market_hours != "regular_hours"

        if (trail_amount is not None or trail_percent is not None) and price is not None:
            # Confirmed against the live API: "Trailing stop limit orders not
            # supported." A trailing stop is always a market order.
            raise OrderError(
                "Robinhood does not support trailing stop limit orders — "
                "omit price to place a trailing stop market order"
            )

        trailing_peg = None
        if trail_amount is not None or trail_percent is not None:
            # A trailing stop is a stop order whose stop price follows the
            # market; the initial stop is anchored off the current quote.
            last = self.get_quote(symbol).price
            if trail_amount is not None:
                margin = trail_amount
                trailing_peg = {
                    "type": "price",
                    "price": {"amount": str(trail_amount), "currency_code": "USD"},
                }
            else:
                margin = last * (trail_percent or 0) / 100
                trailing_peg = {"type": "percentage", "percentage": str(trail_percent)}

            stop_price = round(last + margin if side == "buy" else last - margin, 2)
            if side == "buy":
                # Buy stops need a limit above the stop; 5% headroom, as the
                # app itself uses.
                price = round(stop_price * 1.05, 2)

        # Determine order type and trigger
        if trailing_peg is not None:
            order_type = "market"
            trigger = "stop"
        elif price is None and stop_price is None:
            order_type = "market"
            trigger = "immediate"
        elif price is not None and stop_price is None:
            order_type = "limit"
            trigger = "immediate"
        elif price is None and stop_price is not None:
            order_type = "market"
            trigger = "stop"
            price = stop_price  # For stop market orders, price = stop_price
        else:  # both price and stop_price
            order_type = "limit"
            trigger = "stop"

        # Robinhood requires a collar price on market orders: submitting one
        # without it is rejected with "Market buy order requested, but no price
        # provided." The collar is the current ask for a buy, bid for a sell.
        ask_price = None
        bid_price = None
        collar_price = None
        if order_type == "market" and price is None:
            quote = self.get_quote(symbol)
            ask_price = quote.ask or quote.price
            bid_price = quote.bid or quote.price
            collar_price = ask_price if side == "buy" else bid_price
            if not collar_price:
                raise OrderError(f"No price available to collar a market order for {symbol}")

        payload = {
            "account": self._get_account_url(account_number),
            "instrument": self._get_instrument_url(symbol),
            "symbol": symbol.upper(),
            "price": str(price) if price else (str(collar_price) if collar_price else None),
            "stop_price": str(stop_price) if stop_price else None,
            "quantity": str(quantity),
            "side": side,
            "time_in_force": time_in_force,
            "trigger": trigger,
            "type": order_type,
            "extended_hours": extended_hours,
            "override_day_trade_checks": False,
            "override_dtbp_checks": False,
            "ref_id": str(uuid.uuid4()),
            "order_form_version": ORDER_FORM_VERSION,
        }

        if trailing_peg is not None:
            payload["trailing_peg"] = trailing_peg

        if market_hours is not None:
            payload["market_hours"] = market_hours

        # The app sends the quote alongside a market order; include it so the
        # collar price can be validated server-side.
        if ask_price is not None:
            payload["ask_price"] = str(ask_price)
            payload["bid_price"] = str(bid_price)

        # A market order carries no stop price unless it is stop-triggered.
        if order_type == "market" and trigger == "immediate":
            payload.pop("stop_price", None)

        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}

        try:
            # trailing_peg is a nested object and cannot survive form encoding,
            # so trailing stops are posted as JSON.
            if trailing_peg is not None:
                data = self._session.post(
                    urls.ORDERS, json_data=payload, accept_codes=(400,),
                )
            else:
                data = self._session.post(urls.ORDERS, data=payload, accept_codes=(400,))
        except Exception as e:
            if hasattr(e, 'response') and e.response:
                error_details = e.response
                if isinstance(error_details, dict):
                    # Extract error message from Robinhood response
                    detail = error_details.get("detail", "Order failed")
                    raise OrderError(f"Order failed: {detail}") from e
            raise OrderError(f"Order failed: {e}") from e

        # Check for error response
        if "detail" in data or "error" in data:
            error_msg = data.get("detail") or data.get("error") or "Unknown order error"
            raise OrderError(f"Order rejected: {error_msg}")

        # Field-level validation errors carry neither 'detail' nor 'error' —
        # they come back as {field: [messages]}. Without this, a rejected order
        # returns an Order with a blank id and the caller believes it worked.
        if "id" not in data:
            errors = " ".join(data.get("non_field_errors", [])) if isinstance(data, dict) else ""
            if "app version" in errors:
                raise OrderError(
                    "Robinhood rejected this order for sending an outdated order "
                    f"form version (pyhood sends {ORDER_FORM_VERSION}). Robinhood "
                    "has likely moved to a newer one — raise ORDER_FORM_VERSION in "
                    f"pyhood/client.py. Server said: {errors}"
                )
            raise OrderError(f"Order rejected: {data}")

        # Parse successful response
        created_at = None
        if data.get("created_at"):
            try:
                created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
            except ValueError:
                pass

        return Order(
            order_id=data.get("id", ""),
            symbol=symbol.upper(),
            side=side,
            order_type=order_type,
            quantity=float(quantity),
            price=price,
            status=data.get("state", "unknown"),
            created_at=created_at,
            stop_price=stop_price,
            time_in_force=time_in_force,
            trigger=trigger,
            instrument_type="stock",
        )

    def buy_option(
        self,
        symbol: str,
        strike: float,
        expiration: str,
        option_type: str,
        quantity: int,
        price: float,
        position_effect: str = "open",
        time_in_force: str = "gtc",
        account_number: str | None = None,
    ) -> Order:
        """Buy option contracts.

        Args:
            symbol: Underlying stock symbol.
            strike: Strike price.
            expiration: Expiration date (YYYY-MM-DD).
            option_type: 'call' or 'put'.
            quantity: Number of contracts.
            price: Limit price per share, which is how option prices are
                quoted. One contract is 100 shares, so a price of 1.60
                is $160 per contract.
            position_effect: 'open' or 'close'.
            time_in_force: 'gtc' (good till cancelled), 'gfd' (good for day), 'ioc', 'fok'.
            account_number: Specific account (e.g. IRA). None = default.

        Returns:
            Order object with details.
        """
        return self.order_option(
            symbol=symbol,
            strike=strike,
            expiration=expiration,
            option_type=option_type,
            quantity=quantity,
            price=price,
            side="buy",
            position_effect=position_effect,
            time_in_force=time_in_force,
            account_number=account_number,
        )

    def sell_option(
        self,
        symbol: str,
        strike: float,
        expiration: str,
        option_type: str,
        quantity: int,
        price: float,
        position_effect: str = "close",
        time_in_force: str = "gtc",
        account_number: str | None = None,
    ) -> Order:
        """Sell option contracts.

        Args:
            symbol: Underlying stock symbol.
            strike: Strike price.
            expiration: Expiration date (YYYY-MM-DD).
            option_type: 'call' or 'put'.
            quantity: Number of contracts.
            price: Limit price per share, which is how option prices are
                quoted. One contract is 100 shares, so a price of 1.60
                is $160 per contract.
            position_effect: 'open' or 'close'.
            time_in_force: 'gtc' (good till cancelled), 'gfd' (good for day), 'ioc', 'fok'.
            account_number: Specific account (e.g. IRA). None = default.

        Returns:
            Order object with details.
        """
        return self.order_option(
            symbol=symbol,
            strike=strike,
            expiration=expiration,
            option_type=option_type,
            quantity=quantity,
            price=price,
            side="sell",
            position_effect=position_effect,
            time_in_force=time_in_force,
            account_number=account_number,
        )

    def order_option(
        self,
        symbol: str,
        strike: float,
        expiration: str,
        option_type: str,
        quantity: int,
        price: float,
        side: str,
        position_effect: str,
        credit_or_debit: str | None = None,
        time_in_force: str = "gtc",
        account_number: str | None = None,
    ) -> Order:
        """Place an option order (core method).

        Args:
            symbol: Underlying stock symbol.
            strike: Strike price.
            expiration: Expiration date (YYYY-MM-DD).
            option_type: 'call' or 'put'.
            quantity: Number of contracts.
            price: Limit price per share, which is how option prices are
                quoted. One contract is 100 shares, so a price of 1.60
                is $160 per contract.
            side: 'buy' or 'sell'.
            position_effect: 'open' or 'close'.
            credit_or_debit: 'debit' or 'credit'. Auto-determined from
                side if not provided (buy→debit, sell→credit).
            time_in_force: 'gtc' (good till cancelled), 'gfd' (good for day), 'ioc', 'fok'.
            account_number: Specific account (e.g. IRA). None = default.

        Returns:
            Order object with details.
        """
        option_instrument_url = self._get_option_id(symbol, expiration, strike, option_type)

        # Auto-determine direction from side if not explicitly provided
        if credit_or_debit is None:
            credit_or_debit = "debit" if side == "buy" else "credit"

        legs = [{
            "position_effect": position_effect,
            "side": side,
            "ratio_quantity": 1,
            "option": option_instrument_url,
        }]

        payload = {
            "account": self._get_account_url(account_number),
            "legs": legs,
            "price": str(price),
            "quantity": str(quantity),
            "direction": credit_or_debit,
            "time_in_force": time_in_force,
            "trigger": "immediate",
            "type": "limit",
            "override_day_trade_checks": False,
            "override_dtbp_checks": False,
            "ref_id": str(uuid.uuid4()),
        }

        try:
            data = self._session.post(urls.OPTIONS_ORDERS, json_data=payload, accept_codes=(400,))
        except Exception as e:
            if hasattr(e, 'response') and e.response:
                error_details = e.response
                if isinstance(error_details, dict):
                    detail = error_details.get("detail", "Option order failed")
                    raise OrderError(f"Option order failed: {detail}") from e
            raise OrderError(f"Option order failed: {e}") from e

        # Check for error response
        if "detail" in data or "error" in data:
            error_msg = data.get("detail") or data.get("error") or "Unknown option order error"
            raise OrderError(f"Option order rejected: {error_msg}")

        # Field-level validation errors carry neither key; without this an
        # order with a blank id is returned as if it succeeded.
        if "id" not in data:
            raise OrderError(f"Option order rejected: {data}")

        # Parse successful response
        created_at = None
        if data.get("created_at"):
            try:
                created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
            except ValueError:
                pass

        return Order(
            order_id=data.get("id", ""),
            symbol=symbol.upper(),
            side=side,
            order_type="limit",
            quantity=float(quantity),
            price=price,
            status=data.get("state", "unknown"),
            created_at=created_at,
            time_in_force=time_in_force,
            trigger="immediate",
            instrument_type="option",
            leg_count=1,
            position_effect=position_effect,
            option_type=option_type,
            strike=float(strike),
            expiration=expiration,
        )

    def order_option_spread(
        self,
        symbol: str,
        quantity: int,
        price: float,
        legs: list[dict],
        direction: str,
        time_in_force: str = "gtc",
        account_number: str | None = None,
    ) -> Order:
        """Place a multi-leg option spread order.

        Args:
            symbol: Underlying stock symbol.
            quantity: Number of spreads.
            price: Net limit price per spread.
            legs: One dict per leg, each with `strike`, `expiration`,
                `option_type` ('call'/'put'), `side` ('buy'/'sell') and
                `effect` ('open'/'close').
            direction: 'debit' or 'credit'.
            time_in_force: 'gtc', 'gfd', 'ioc' or 'fok'.
            account_number: Specific account (e.g. IRA). None = default.

        Returns:
            Order object with details.

        Raises:
            OrderError: If fewer than two legs are given, or a leg is missing
                a required key.

        Note:
            The payload shape matches what robin_stocks sends in production,
            but placing a spread has not been verified against the live API —
            that would mean opening a real position.
        """
        if len(legs) < 2:
            raise OrderError("A spread needs at least two legs")

        # Validate every leg before any instrument lookup, so a malformed
        # spread fails without making network calls.
        required = {"strike", "expiration", "option_type", "side", "effect"}
        for i, leg in enumerate(legs):
            missing = required - set(leg)
            if missing:
                raise OrderError(f"Leg {i} missing {sorted(missing)}")

        built_legs = []
        for leg in legs:
            built_legs.append({
                "position_effect": leg["effect"],
                "side": leg["side"],
                "ratio_quantity": leg.get("ratio", 1),
                "option": self._get_option_id(
                    symbol, leg["expiration"], leg["strike"], leg["option_type"],
                ),
            })

        payload = {
            "account": self._get_account_url(account_number),
            "legs": built_legs,
            "price": str(price),
            "quantity": str(quantity),
            "direction": direction,
            "time_in_force": time_in_force,
            "trigger": "immediate",
            "type": "limit",
            "override_day_trade_checks": False,
            "override_dtbp_checks": False,
            "ref_id": str(uuid.uuid4()),
        }

        data = self._session.post(
            urls.OPTIONS_ORDERS, json_data=payload, accept_codes=(400,),
        )
        if "id" not in data:
            raise OrderError(f"Spread order failed: {data.get('detail', data)}")

        created_at = None
        if data.get("created_at"):
            try:
                created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
            except ValueError:
                pass

        return Order(
            order_id=data.get("id", ""),
            symbol=symbol.upper(),
            side={"debit": "buy", "credit": "sell"}.get(direction, direction),
            order_type="limit",
            quantity=float(quantity),
            price=price,
            status=data.get("state", "unknown"),
            created_at=created_at,
            time_in_force=time_in_force,
            trigger="immediate",
            instrument_type="option",
            leg_count=len(legs),
        )

    def buy_stock_by_price(
        self,
        symbol: str,
        amount_in_dollars: float,
        account_number: str | None = None,
        time_in_force: str = "gfd",
    ) -> Order:
        """Buy fractional shares by dollar amount.

        Args:
            symbol: Stock ticker symbol.
            amount_in_dollars: Dollar amount to buy (minimum $1).
            account_number: Specific account (e.g. IRA). None = default.
            time_in_force: Defaults to 'gfd', which fractional orders require.

        Returns:
            Order object with details.

        Raises:
            OrderError: If the amount is below $1 or the quote is unusable.

        Note:
            Fractional quantities require a market order — Robinhood rejects
            a fractional limit order with "Limit order quantity cannot include
            fractional shares". Market orders were themselves being rejected
            until `ORDER_FORM_VERSION` was found and sent, which is fixed.

            End to end this is unverified. A fractional order is a market
            order, so it executes immediately and cannot be exercised with a
            resting non-marketable limit the way the other order paths were.
            The payload and the rounding are covered by tests; the fill is
            not.
        """
        return self._order_stock_by_price(
            symbol, amount_in_dollars, "buy", account_number, time_in_force,
        )

    def sell_stock_by_price(
        self,
        symbol: str,
        amount_in_dollars: float,
        account_number: str | None = None,
        time_in_force: str = "gfd",
    ) -> Order:
        """Sell fractional shares by dollar amount.

        Args:
            symbol: Stock ticker symbol.
            amount_in_dollars: Dollar amount to sell (minimum $1).
            account_number: Specific account (e.g. IRA). None = default.
            time_in_force: Defaults to 'gfd', which fractional orders require.

        Returns:
            Order object with details.
        """
        return self._order_stock_by_price(
            symbol, amount_in_dollars, "sell", account_number, time_in_force,
        )

    def _order_stock_by_price(
        self, symbol: str, amount_in_dollars: float, side: str,
        account_number: str | None, time_in_force: str,
    ) -> Order:
        """Convert a dollar amount to fractional shares and place the order."""
        if amount_in_dollars < 1:
            raise OrderError("Fractional orders must be at least $1")

        quote = self.get_quote(symbol)
        # Size against the lowest plausible execution price so the notional
        # still clears Robinhood's $1 minimum if the order fills at the bid.
        # Rounding down against the last price puts a $1 order under the
        # minimum and it is rejected.
        price = min(p for p in (quote.price, quote.bid, quote.ask) if p and p > 0) \
            if any(p and p > 0 for p in (quote.price, quote.bid, quote.ask)) else 0
        if price <= 0:
            raise OrderError(f"Cannot price fractional order for {symbol}")

        shares = math.ceil(amount_in_dollars / price * 1_000_000) / 1_000_000
        return self.order_stock(
            symbol=symbol,
            quantity=shares,
            side=side,
            time_in_force=time_in_force,
            account_number=account_number,
        )

    def get_stock_orders(self, start_date: str | datetime | None = None) -> list[Order]:
        """Get all stock orders (not options).

        Args:
            start_date: Only return orders created on or after this point.
                Accepts a datetime or ISO-8601 string ('2026-01-01'); naive
                values are treated as UTC. Filtering is requested server-side
                to avoid paging through a long history, and re-applied locally.

        Returns:
            List of Order objects for stock orders.
        """
        cutoff = self._parse_start_date(start_date)
        data = self._session.get_paginated(
            urls.ORDERS, params=self._start_date_params(cutoff),
        )
        symbol_cache: dict[str, str] = {}
        orders = []

        for item in data:
            # Skip option orders (they have legs)
            if "legs" in item or item.get("legs"):
                continue

            if self._before_cutoff(item.get("created_at", ""), cutoff):
                continue

            orders.append(self._stock_order(item, symbol_cache))

        return orders

    def get_option_orders(self, start_date: str | datetime | None = None) -> list[Order]:
        """Get all option orders.

        Args:
            start_date: Only return orders created on or after this point.
                Accepts a datetime or ISO-8601 string ('2026-01-01'); naive
                values are treated as UTC. Filtering is requested server-side
                to avoid paging through a long history, and re-applied locally.

        Returns:
            List of Order objects for option orders.
        """
        cutoff = self._parse_start_date(start_date)
        data = self._session.get_paginated(
            urls.OPTIONS_ORDERS, params=self._start_date_params(cutoff),
        )
        orders = []

        for item in data:
            if self._before_cutoff(item.get("created_at", ""), cutoff):
                continue

            orders.append(self._option_order(item))

        return orders

    def get_order(self, order_id: str) -> Order:
        """Get a specific order by ID.

        Args:
            order_id: The order ID to fetch.

        Returns:
            Order object with details.
        """
        # Try stock orders first
        try:
            data = self._session.get(f"{urls.ORDERS}{order_id}/")
            return self._stock_order(data, {})
        except Exception:
            # Try option orders
            try:
                data = self._session.get(f"{urls.OPTIONS_ORDERS}{order_id}/")
                return self._option_order(data)
            except Exception as e:
                raise OrderError(f"Order {order_id} not found") from e

    def _stock_order(self, item: dict, symbol_cache: dict[str, str]) -> Order:
        """Map a raw stock order onto an Order.

        The orders endpoint sends no symbol, only the instrument URL, so the
        symbol is looked up once per instrument and cached for the caller.
        """
        instrument_url = item.get("instrument", "")
        if instrument_url and instrument_url not in symbol_cache:
            try:
                symbol_cache[instrument_url] = self._session.get(instrument_url).get("symbol", "")
            except Exception:
                symbol_cache[instrument_url] = ""

        filled_quantity = _safe_float(item.get("cumulative_quantity"))
        return Order(
            order_id=item.get("id", ""),
            symbol=symbol_cache.get(instrument_url, "").upper(),
            side=item.get("side", ""),
            order_type=item.get("type", ""),
            quantity=float(item.get("quantity", 0)),
            price=_safe_float(item.get("price")),
            status=item.get("state", "unknown"),
            created_at=_parse_time(item.get("created_at")),
            filled_at=_filled_at(item, filled_quantity, item.get("last_transaction_at")),
            stop_price=_safe_float(item.get("stop_price")),
            time_in_force=item.get("time_in_force", "gtc"),
            trigger=item.get("trigger", "immediate"),
            instrument_type="stock",
            average_price=_safe_float(item.get("average_price")),
            fees=_safe_float(item.get("fees")),
            filled_quantity=filled_quantity,
        )

    def _option_order(self, item: dict) -> Order:
        """Map a raw option order onto an Order.

        The symbol is `chain_symbol` on the order itself. Older responses
        lacking it fall back to looking up the first leg's instrument.
        """
        legs = item.get("legs") or []
        symbol = item.get("chain_symbol", "")
        if not symbol and legs and legs[0].get("option"):
            try:
                symbol = self._session.get(legs[0]["option"]).get("chain_symbol", "")
            except Exception:
                pass

        executions = [e for leg in legs for e in leg.get("executions") or []]
        last_execution = max((e.get("timestamp") or "" for e in executions), default="")
        filled_quantity = _safe_float(item.get("processed_quantity"))
        return Order(
            order_id=item.get("id", ""),
            symbol=symbol.upper(),
            side=_option_side(item, legs),
            order_type=item.get("type", ""),
            quantity=float(item.get("quantity", 0)),
            price=_safe_float(item.get("price")),
            status=item.get("state", "unknown"),
            created_at=_parse_time(item.get("created_at")),
            filled_at=_filled_at(item, filled_quantity, last_execution),
            time_in_force=item.get("time_in_force", "gtc"),
            trigger=item.get("trigger", "immediate"),
            instrument_type="option",
            # Per-share fill price, only for a single leg: a spread has no
            # single price, and the order-level premium fields are per
            # contract and signed.
            average_price=_average_execution_price(executions) if len(legs) == 1 else None,
            fees=_option_fees(item),
            filled_quantity=filled_quantity,
            **_option_contract(legs),
        )

    def cancel_order(self, order_id: str) -> dict:
        """Cancel a specific order.

        Args:
            order_id: The order ID to cancel.

        Returns:
            Response dict from the cancellation.
        """
        # Try stock orders first
        try:
            data = self._session.post(f"{urls.ORDERS}{order_id}/cancel/")
            return data
        except Exception:
            # Try option orders
            try:
                data = self._session.post(f"{urls.OPTIONS_ORDERS}{order_id}/cancel/")
                return data
            except Exception as e:
                raise OrderError(f"Failed to cancel order {order_id}") from e

    def cancel_all_stock_orders(self) -> list[dict]:
        """Cancel all pending stock orders.

        Returns:
            List of response dicts from cancellations.
        """
        orders = self.get_stock_orders()
        results = []

        for order in orders:
            if order.status in ("pending", "unconfirmed", "queued"):
                try:
                    result = self.cancel_order(order.order_id)
                    results.append(result)
                except Exception as e:
                    logger.warning(f"Failed to cancel order {order.order_id}: {e}")
                    results.append({"error": str(e), "order_id": order.order_id})

        return results

    # ── Export ───────────────────────────────────────────────────────────

    def export_stock_orders(
        self, path: str | Path, start_date: str | datetime | None = None,
    ) -> Path:
        """Write completed stock orders to a CSV file.

        Args:
            path: Destination file, or a directory to write a default filename into.
            start_date: Only include orders created on or after this point.

        Returns:
            The path written.
        """
        orders = [o for o in self.get_stock_orders(start_date=start_date) if o.status == "filled"]
        return self._write_orders_csv(path, orders, "stock_orders")

    def export_option_orders(
        self, path: str | Path, start_date: str | datetime | None = None,
    ) -> Path:
        """Write completed option orders to a CSV file.

        Args:
            path: Destination file, or a directory to write a default filename into.
            start_date: Only include orders created on or after this point.

        Returns:
            The path written.
        """
        orders = [o for o in self.get_option_orders(start_date=start_date) if o.status == "filled"]
        return self._write_orders_csv(path, orders, "option_orders")

    @staticmethod
    def _write_orders_csv(path: str | Path, orders: list[Order], stem: str) -> Path:
        """Write orders to CSV, accepting either a file or a directory path."""
        target = Path(path)
        if target.is_dir():
            target = target / f"{stem}.csv"
        target.parent.mkdir(parents=True, exist_ok=True)

        fields = [
            "order_id", "symbol", "side", "order_type", "quantity", "price",
            "average_price", "status", "created_at", "filled_at",
            "time_in_force", "instrument_type",
        ]
        with open(target, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for o in orders:
                row = {f: getattr(o, f, "") for f in fields}
                for k, v in row.items():
                    if isinstance(v, datetime):
                        row[k] = v.isoformat()
                    elif v is None:
                        row[k] = ""
                writer.writerow(row)
        return target

    def unlink_bank_account(self, relationship_id: str) -> dict:
        """Unlink a connected bank account.

        Args:
            relationship_id: ACH relationship ID from `get_bank_accounts()`.

        Returns:
            The API response.

        Warning:
            This is irreversible — relinking requires re-verifying the account
            with Robinhood. Not exercised against a live account.
        """
        return self._session.post(f"{urls.ACH_RELATIONSHIPS}{relationship_id}/unlink/")

    # ── Interest / Fees ──────────────────────────────────────────────────

    def get_interest_payments(self) -> list[InterestPayment]:
        """Get cash sweep interest payments.

        Returns:
            List of InterestPayment, newest first as returned by the API.
        """
        data = self._session.get_paginated(urls.INTEREST_PAYMENTS)
        payments: list[InterestPayment] = []
        for item in data:
            amount = item.get("amount") or {}
            payments.append(InterestPayment(
                id=item.get("id", ""),
                amount=float(amount.get("amount", 0) or 0),
                currency=amount.get("currency_code", "USD"),
                direction=item.get("direction", ""),
                pay_date=item.get("pay_date", ""),
                pay_period_start=item.get("pay_period_start", ""),
                pay_period_end=item.get("pay_period_end", ""),
                payout_type=item.get("payout_type", ""),
                reason=item.get("reason", ""),
                account_number=item.get("account_number", ""),
            ))
        return payments

    def get_margin_interest(self) -> list[dict]:
        """Get margin interest charges.

        Returns:
            List of raw charge dicts.

        Note:
            The endpoint and its `results` envelope are verified, but the test
            account has never been charged margin interest, so no populated
            record has been observed. Records are returned unmapped rather
            than forced onto a dataclass built from guessed field names.
        """
        return self._session.get_paginated(urls.MARGIN_INTEREST)

    def get_subscription_fees(self) -> list[SubscriptionFee]:
        """Get Robinhood Gold subscription fees.

        Returns:
            List of SubscriptionFee.
        """
        data = self._session.get_paginated(urls.SUBSCRIPTION_FEES)
        return [
            SubscriptionFee(
                id=item.get("id", ""),
                amount=float(item.get("amount", 0) or 0),
                date=item.get("date", ""),
                state=item.get("state", ""),
                credit=float(item.get("credit", 0) or 0),
                carry_forward_credit=float(item.get("carry_forward_credit", 0) or 0),
                created_at=item.get("created_at", ""),
                account_number=item.get("account_number", ""),
            )
            for item in data
        ]

    def get_unified_transfers(self) -> list[UnifiedTransfer]:
        """Get transfers from the unified payment hub.

        Broader than `get_transfers()`, which covers ACH only — this also
        includes internal transfers such as brokerage to IRA.

        Returns:
            List of UnifiedTransfer.
        """
        data = self._session.get_paginated(urls.UNIFIED_TRANSFERS)
        return [
            UnifiedTransfer(
                id=item.get("id", ""),
                amount=float(item.get("amount", 0) or 0),
                currency=item.get("currency", "usd"),
                direction=item.get("direction", ""),
                transfer_type=item.get("transfer_type", ""),
                state=item.get("state", ""),
                description=item.get("description", ""),
                originating_account_id=item.get("originating_account_id", ""),
                originating_account_type=item.get("originating_account_type", ""),
                receiving_account_id=item.get("receiving_account_id", ""),
                receiving_account_type=item.get("receiving_account_type", ""),
                created_at=item.get("created_at", ""),
                completed_at=item.get("completed_at", ""),
            )
            for item in data
        ]

    # ── IPO Access ───────────────────────────────────────────────────────

    def get_ipo_access_list(self) -> dict:
        """Get the IPO Access list — offerings currently available to you.

        When Robinhood has no offerings, the response carries an `empty_state`
        section instead of any offering.

        Returns:
            The raw list view model. These are UI view models with deeply
            nested, offering-dependent structure, so they are returned as-is
            rather than mapped onto a dataclass.
        """
        return self._session.get(urls.IPO_ACCESS_LIST)

    def has_ipo_offerings(self) -> bool:
        """Whether any IPO Access offering is open for share requests.

        Note:
            This is narrower than "an IPO exists". The list only carries
            offerings whose order book is still open, so an upcoming IPO
            reports False once its book closes. Verified against RVII on
            2026-08-12: the instrument was live at `ipo_access_status`
            `price_finalized` and listing the next day, while this returned
            False. To detect an offering regardless of stage, look for
            instruments with `type` `pre_ipo` and an `ipo_access_status`.
        """
        data = self.get_ipo_access_list()
        return bool(data) and "empty_state" not in data

    def get_ipo_access_cards(self, instrument_ids: str | list[str]) -> list[dict]:
        """Get IPO Access cards for one or more instruments.

        Args:
            instrument_ids: An instrument ID, or a list of them.

        Returns:
            List of card dicts. Shape verified against a live offering
            (RVII, 2026-08-12): `instrument_id`, `name`, `title` (the
            ticker), `subtitle` (the price, e.g. `'$25.00'`), `accent_color`,
            `action` (a deeplink) and `logo_images`.

        Note:
            Cards resolve by instrument ID at any stage, including after the
            order book has closed and `has_ipo_offerings()` reports False.
        """
        data = self._session.get(urls.ipo_access_cards_url(instrument_ids))
        return data.get("results", []) if isinstance(data, dict) else []

    def get_ipo_access_summary(self, instrument_id: str) -> dict:
        """Get an IPO's summary view model — company, dates and price range.

        Warning:
            Unconfirmed. This returned 404 against a live offering (RVII,
            2026-08-12, phase `price_finalized`), as did seven other spellings
            of the path on the same base that serves `web_order_entry`
            successfully. Either the route is stage-specific — reachable only
            while the order book is open — or this path is wrong. Prefer
            `get_ipo_access_order_entry()`, whose `context` carries the
            symbol, phase, cut-off deadline and enrolment state.
        """
        return self._session.get(urls.ipo_access_summary_url(instrument_id))

    def get_ipo_access_order_entry(
        self, instrument_id: str, account_number: str | None = None,
    ) -> dict:
        """Get an IPO's order-entry view model — eligibility and price range.

        Returns:
            The raw view model. Shape verified against a live offering (RVII,
            2026-08-12): `account_number`, `instrument_id`, `context`,
            `form_state`, `order_entry_view_model`, `trade_receipt_view_model`,
            `action_required_view_model` and `ipoa_new_orders_blocked_details`.

            `context` is the useful part: `phase` (e.g. `'price_finalized'`),
            `instrument_symbol`, `instrument_url`, `ipo_access_quote`,
            `ipo_access_cob_deadline`, `has_cob_deadline_passed`,
            `user_is_enrolled`, `account_type`, `existing_order` and
            `available_buying_power`.

            `trade_receipt_view_model` is None until an order exists. Once it
            does, `context.existing_order` carries the order's ID, quantity,
            state and price, and that state stays current: it read
            `partially_filled_rest_cancelled` after an allocation (ANT,
            2026-11-19). The receipt view model does not: it still said
            "Allocation is pending" after the order filled. Read the state
            from `existing_order` or the order itself, never the receipt.

        Note:
            This is the most informative of the IPO endpoints and the one to
            reach for — it resolves after the order book closes, when
            `get_ipo_access_list()` has already reverted to its empty state.
            Requesting shares is not wrapped; an IPO Access order is an
            ordinary equity order.
        """
        return self._session.get(
            urls.ipo_access_order_entry_url(instrument_id, account_number)
        )

    def get_ipo_access_allocation_results(self, instrument_id: str) -> dict:
        """Get whether you were allocated shares in an IPO you requested.

        Returns:
            The raw view model. Shape verified against a filled request (ANT,
            2026-11-19): `instrument_id`, `order_id`, `result` (e.g.
            `'allocated'`) and, under the key named by `result`, a `card`
            whose `primary_text` gives your rank among allocated investors
            and whose `footer_detail` is the price per share, plus buttons
            and animation assets for the app.

        Note:
            This says whether you were allocated, not how many shares. For
            the count, use `filled_quantity` on the order from
            `get_ipo_access_orders()`; `quantity` there is what was
            requested. In the raw order, each execution also carries an
            `ipo_access_execution_rank`. The order's state was
            `partially_filled_rest_cancelled`, meaning the unallocated part of
            the request was cancelled and will not fill later.

            Returns 404 before allocations are decided, confirmed the day
            before a listing (RVII, 2026-08-12). That is correct behaviour:
            there is nothing to report until after pricing.
        """
        return self._session.get(urls.ipo_access_allocation_results_url(instrument_id))

    def get_ipo_access_trade_receipt(self, order_id: str) -> dict:
        """Get the trade receipt for an IPO Access order.

        Returns:
            The raw view model. Shape verified against a real request (ANT,
            2026-11-19): `id`, `title`, `order_summary` (a sentence),
            `order_detail_items` (label and value rows such as "Request
            status" and "Shares requested") and `footer_buttons`.

        Warning:
            This is the receipt shown when the request was made, and it is not
            updated afterwards. After the request was allocated and filled it
            still read "request queued", with a "Request status" of
            "Queued". Use `get_ipo_access_allocation_results()` for the
            outcome and the order itself for the shares received.
        """
        return self._session.get(urls.ipo_access_trade_receipt_url(order_id))

    def get_ipo_access_orders(
        self, start_date: str | datetime | None = None,
    ) -> list[Order]:
        """Get stock orders placed through IPO Access.

        IPO Access orders are ordinary equity orders flagged with
        `is_ipo_access_order`, so this filters the stock order history.

        Args:
            start_date: Only return orders created on or after this point.
                See `get_stock_orders` for accepted formats.

        Returns:
            List of Order objects for IPO Access orders.
        """
        cutoff = self._parse_start_date(start_date)
        data = self._session.get_paginated(
            urls.ORDERS, params=self._start_date_params(cutoff),
        )
        ipo_ids = {
            item.get("id")
            for item in data
            if item.get("is_ipo_access_order")
        }
        if not ipo_ids:
            return []
        return [
            o for o in self.get_stock_orders(start_date=start_date)
            if o.order_id in ipo_ids
        ]

    def cancel_all_option_orders(self) -> list[dict]:
        """Cancel all pending option orders.

        Returns:
            List of response dicts from cancellations.
        """
        orders = self.get_option_orders()
        results = []

        for order in orders:
            if order.status in ("pending", "unconfirmed", "queued"):
                try:
                    result = self.cancel_order(order.order_id)
                    results.append(result)
                except Exception as e:
                    logger.warning(f"Failed to cancel option order {order.order_id}: {e}")
                    results.append({"error": str(e), "order_id": order.order_id})

        return results

    # ── Futures ──────────────────────────────────────────────────────────

    def _set_futures_header(self) -> None:
        """Set the Rh-Contract-Protected header required by futures endpoints."""
        self._session._session.headers["Rh-Contract-Protected"] = "true"

    def get_futures_account_id(self) -> str:
        """Auto-discover the futures account ID.

        Fetches all Ceres accounts and returns the first with
        accountType == 'FUTURES'.

        Returns:
            The futures account ID string.

        Raises:
            APIError: If no futures account is found.
        """
        from pyhood.exceptions import APIError

        self._set_futures_header()
        data = self._session.get(urls.FUTURES_ACCOUNTS)
        for account in data.get("results", []):
            if account.get("accountType") == "FUTURES":
                return account.get("id", "")
        raise APIError("No futures account found")

    def get_futures_contract(self, symbol: str) -> FuturesContract:
        """Get futures contract details by symbol.

        Args:
            symbol: Futures symbol (e.g. 'ESH26' for E-mini S&P 500 Mar 2026).

        Returns:
            FuturesContract with contract details.

        Raises:
            SymbolNotFound: If symbol not recognized.
        """
        item = self._futures_contract_item(symbol)
        # Tick size, underlying and asset class belong to the product (/ES),
        # not the contract (/ESZ26), so they take a second request.
        product = self._futures_product(item.get("productId", ""))
        return FuturesContract(
            symbol=self._clean_futures_symbol(item, symbol),
            name=item.get("description", ""),
            contract_id=item.get("id", ""),
            expiration=item.get("expiration", ""),
            tick_size=_safe_float(product.get("priceIncrements")),
            multiplier=float(item.get("multiplier", 0) or 0),
            status=self._clean_futures_state(item.get("state", "")),
            underlying=self._clean_futures_symbol(product, "") if product else "",
            asset_class=product.get("rhdProductGroup", "")
            .removeprefix("RHD_PRODUCT_GROUP_").lower(),
        )

    def get_futures_product_contracts(self, product: str) -> list[FuturesContract]:
        """Get the active contracts of a futures product, nearest expiration first.

        A product is the thing traded, such as 'ES' for the E-mini S&P 500.
        A contract is one delivery month of it, such as 'ESZ26'. The first
        contract returned is the front month, which is the one a quote for
        "the S&P futures" usually means.

        Args:
            product: Product symbol, with or without the slash: 'ES' or '/ES'.

        Returns:
            The product's active contracts, each with the product's tick
            size, underlying and asset class filled in.

        Raises:
            SymbolNotFound: If Robinhood lists no such product.
        """
        self._set_futures_header()
        wanted = product.upper().lstrip("/")
        data = self._session.get(urls.FUTURES_PRODUCTS)
        listed = data.get("results", data.get("result", [])) if isinstance(data, dict) else data
        record = next(
            (p for p in listed or [] if self._clean_futures_symbol(p, "") == wanted), None,
        )
        if record is None:
            raise SymbolNotFound(f"No futures product {wanted}")

        data = self._session.get(urls.FUTURES_CONTRACTS, params={"productIds": record["id"]})
        items = data.get("results", data.get("result", [])) if isinstance(data, dict) else data
        contracts = [
            FuturesContract(
                symbol=self._clean_futures_symbol(item, ""),
                name=item.get("description", ""),
                contract_id=item.get("id", ""),
                expiration=item.get("expiration", ""),
                tick_size=_safe_float(record.get("priceIncrements")),
                multiplier=float(item.get("multiplier", 0) or 0),
                status=self._clean_futures_state(item.get("state", "")),
                underlying=wanted,
                asset_class=record.get("rhdProductGroup", "")
                .removeprefix("RHD_PRODUCT_GROUP_").lower(),
            )
            for item in items or []
        ]
        return sorted(
            (c for c in contracts if c.status == "active"), key=lambda c: c.expiration,
        )

    def _futures_contract_item(self, symbol: str) -> dict:
        """Fetch the raw contract record for a futures symbol.

        Raises:
            SymbolNotFound: If symbol not recognized.
        """
        self._set_futures_header()
        data = self._session.get(urls.futures_contract_url(symbol.upper()))
        # The arsenal endpoint wraps the contract in a "result" envelope and
        # uses camelCase keys; accept an unwrapped body too in case it changes.
        item = data.get("result", data) if isinstance(data, dict) else {}
        if not item or "id" not in item:
            raise SymbolNotFound(f"No futures contract for {symbol}")
        return item

    def _futures_product(self, product_id: str) -> dict:
        """Fetch the raw product record a contract belongs to, or {}.

        A failed lookup is not fatal: the contract is still usable without
        its tick size.
        """
        if not product_id:
            return {}
        try:
            data = self._session.get(f"{urls.FUTURES_PRODUCTS}{product_id}/")
        except Exception:
            logger.warning(f"Failed to fetch futures product {product_id}")
            return {}
        return data.get("result", data) if isinstance(data, dict) else {}

    @staticmethod
    def _clean_futures_symbol(item: dict, fallback: str) -> str:
        """Normalize '/ESZ26:XCME' or '/ESZ26' to 'ESZ26'."""
        raw = item.get("displaySymbol") or item.get("symbol") or fallback
        return raw.lstrip("/").split(":")[0].upper()

    @staticmethod
    def _clean_futures_state(state: str) -> str:
        """Normalize 'FUTURES_STATE_ACTIVE' to 'active'."""
        if not state:
            return "active"
        return state.removeprefix("FUTURES_STATE_").lower()

    def get_futures_contracts(self, symbols: list[str]) -> dict[str, FuturesContract]:
        """Get futures contract details for multiple symbols.

        Args:
            symbols: List of futures symbols (e.g. ['ESH26', 'NQH26']).

        Returns:
            Dict mapping symbol to FuturesContract.
        """
        results: dict[str, FuturesContract] = {}
        for sym in symbols:
            try:
                results[sym.upper()] = self.get_futures_contract(sym)
            except Exception:
                logger.warning(f"Failed to fetch futures contract for {sym}")
        return results

    def get_futures_quote(
        self, symbol: str, include_fundamentals: bool = False,
    ) -> FuturesQuote:
        """Get a real-time futures quote.

        Args:
            symbol: Futures symbol (e.g. 'ESH26').
            include_fundamentals: Also fetch the session's `high`, `low`,
                `prev_close` and `volume`. Robinhood's futures quote does
                not carry them, so they are None without this. Costs one
                more request.

        Returns:
            FuturesQuote with bid/ask/last price.

        Raises:
            SymbolNotFound: If symbol not recognized.
        """
        item = self._futures_contract_item(symbol)
        return self.get_futures_quote_by_id(
            item["id"],
            symbol=self._clean_futures_symbol(item, symbol),
            include_fundamentals=include_fundamentals,
        )

    def get_futures_quote_by_id(
        self, contract_id: str, symbol: str = "", include_fundamentals: bool = False,
    ) -> FuturesQuote:
        """Get a real-time futures quote by contract ID.

        Avoids the contract lookup that `get_futures_quote` performs when the
        contract ID is already known.

        Args:
            contract_id: Futures contract instrument ID.
            symbol: Optional symbol to label the quote with.
            include_fundamentals: Also fetch the session's `high`, `low`,
                `prev_close` and `volume`, which are None without this.
                Costs one more request.

        Returns:
            FuturesQuote with bid/ask/last price.

        Raises:
            SymbolNotFound: If no quote is returned for the contract.
        """
        self._set_futures_header()
        data = self._session.get(urls.FUTURES_QUOTES, params={"ids": contract_id})
        q = self._unwrap_futures_quote(data)
        if not q:
            raise SymbolNotFound(f"No futures quote for {symbol or contract_id}")

        # Same envelope as the quote. Robinhood publishes no open interest.
        fundamentals = (
            self._unwrap_futures_quote(
                self._session.get(urls.FUTURES_FUNDAMENTALS, params={"ids": contract_id})
            )
            if include_fundamentals else {}
        )
        return FuturesQuote(
            symbol=self._clean_futures_symbol(q, symbol or contract_id),
            last_price=float(q.get("last_trade_price", 0) or 0),
            bid=float(q.get("bid_price", 0) or 0),
            ask=float(q.get("ask_price", 0) or 0),
            high=_safe_float(fundamentals.get("high")),
            low=_safe_float(fundamentals.get("low")),
            prev_close=_safe_float(fundamentals.get("previous_close_price")),
            volume=_safe_int(fundamentals.get("volume")),
            contract_id=q.get("instrument_id", "") or contract_id,
        )

    @staticmethod
    def _unwrap_futures_quote(data: Any) -> dict:
        """Pull the quote body out of the futures marketdata envelope.

        The endpoint returns {"status": ..., "data": [{"status": ..., "data": {...}}]}.
        A flat "results" list is also accepted in case the shape changes.
        """
        if not isinstance(data, dict):
            return {}
        entries = data.get("data")
        if isinstance(entries, list) and entries:
            inner = entries[0]
            if isinstance(inner, dict):
                body = inner.get("data")
                if isinstance(body, dict):
                    return body
                return inner
        results = data.get("results")
        if isinstance(results, list) and results and isinstance(results[0], dict):
            return results[0]
        return {}

    def get_futures_quotes(
        self, symbols: list[str], include_fundamentals: bool = False,
    ) -> dict[str, FuturesQuote]:
        """Get real-time futures quotes for multiple symbols.

        Args:
            symbols: List of futures symbols.
            include_fundamentals: Also fetch each contract's `high`, `low`,
                `prev_close` and `volume`, which are None without this.
                Costs one more request per symbol.

        Returns:
            Dict mapping symbol to FuturesQuote.
        """
        results: dict[str, FuturesQuote] = {}
        for sym in symbols:
            try:
                results[sym.upper()] = self.get_futures_quote(sym, include_fundamentals)
            except Exception:
                logger.warning(f"Failed to fetch futures quote for {sym}")
        return results

    def get_futures_orders(
        self, account_id: str | None = None,
        start_date: str | datetime | None = None,
    ) -> list[FuturesOrder]:
        """Get all historical futures orders.

        Uses cursor-based pagination (different from standard Robinhood
        pagination). Automatically discovers futures account if not provided.

        Args:
            account_id: Futures account ID. Auto-discovered if None.
            start_date: Only return orders created on or after this point.
                Accepts a datetime or ISO-8601 string ('2026-01-01'); naive
                values are treated as UTC. The futures service is not confirmed
                to support server-side date filtering, so this may only filter
                locally rather than reduce the number of pages fetched.

        Returns:
            List of FuturesOrder objects.
        """
        cutoff = self._parse_start_date(start_date)
        if not account_id:
            account_id = self.get_futures_account_id()

        self._set_futures_header()
        orders: list[FuturesOrder] = []
        url: str | None = urls.futures_orders_url(account_id)

        params = self._start_date_params(cutoff)
        while url:
            data = self._session.get(url, params=params)
            params = None  # Only sent on the first request; cursors carry it after
            for item in data.get("results", []):
                if self._before_cutoff(item.get("created_at", ""), cutoff):
                    continue
                pnl = self._extract_futures_pnl(item)
                orders.append(FuturesOrder(
                    order_id=item.get("id", ""),
                    symbol=item.get("symbol", ""),
                    side=item.get("side", ""),
                    order_type=item.get("type", ""),
                    quantity=float(item.get("quantity", 0) or 0),
                    price=float(item["price"]) if item.get("price") else None,
                    status=item.get("state", "unknown"),
                    created_at=item.get("created_at", ""),
                    direction=item.get("opening_strategy", "")
                    or item.get("closing_strategy", ""),
                    realized_pnl=pnl.realized_pnl if pnl else None,
                    account_id=account_id,
                ))
            # Cursor-based pagination
            url = data.get("next")

        return orders

    def get_futures_positions(self, account_id: str | None = None) -> list[dict]:
        """Get open futures positions.

        Args:
            account_id: Futures account ID. Auto-discovered if None.

        Returns:
            List of raw position dicts.

        Note:
            The endpoint and its `results` envelope are verified, but no
            populated position record has been observed — the test account
            holds no futures positions. Records are therefore returned
            unmapped rather than forced onto a dataclass whose field names
            would be guesswork.
        """
        if not account_id:
            account_id = self.get_futures_account_id()

        self._set_futures_header()
        positions: list[dict] = []
        url: str | None = urls.futures_positions_url(account_id)
        while url:
            data = self._session.get(url)
            if not isinstance(data, dict):
                break
            positions.extend(data.get("results", []))
            url = data.get("next")
        return positions

    def get_futures_order_info(
        self, order_id: str, account_id: str | None = None,
    ) -> FuturesOrder | None:
        """Get a single futures order by ID.

        The futures service has no single-order endpoint, so this scans the
        order history client-side.

        Args:
            order_id: Futures order ID.
            account_id: Futures account ID. Auto-discovered if None.

        Returns:
            The matching FuturesOrder, or None if not found.
        """
        for order in self.get_futures_orders(account_id=account_id):
            if order.order_id == order_id:
                return order
        return None

    def get_filled_futures_orders(
        self, account_id: str | None = None,
        start_date: str | datetime | None = None,
    ) -> list[FuturesOrder]:
        """Get only filled futures orders.

        Args:
            account_id: Futures account ID. Auto-discovered if None.
            start_date: Only return orders created on or after this point.
                See `get_futures_orders` for accepted formats.

        Returns:
            List of filled FuturesOrder objects.
        """
        all_orders = self.get_futures_orders(account_id=account_id, start_date=start_date)
        return [o for o in all_orders if o.status == "filled"]

    @staticmethod
    def _extract_futures_pnl(order: dict) -> FuturesPnL | None:
        """Extract P&L from a futures order's nested structure.

        Robinhood nests P&L inside order → legs → executions → settlement.
        Returns None if no P&L data found.
        """
        try:
            legs = order.get("legs", [])
            if not legs:
                return None
            executions = legs[0].get("executions", [])
            if not executions:
                return None
            settlement = executions[0].get("settlement", {})
            pnl = float(settlement.get("realized_pnl", 0) or 0)
            return FuturesPnL(
                realized_pnl=pnl,
                direction="CLOSING" if order.get("closing_strategy") else "OPENING",
                order_id=order.get("id", ""),
            )
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    def calculate_futures_pnl(
        self, orders: list[FuturesOrder] | None = None, account_id: str | None = None,
    ) -> float:
        """Calculate total realized P&L across futures orders.

        Only counts CLOSING orders to avoid double-counting.

        Args:
            orders: Pre-fetched orders. If None, fetches all filled orders.
            account_id: Futures account ID (used if orders is None).

        Returns:
            Total realized P&L as a float.
        """
        if orders is None:
            orders = self.get_filled_futures_orders(account_id=account_id)
        return sum(
            o.realized_pnl
            for o in orders
            if o.realized_pnl is not None and "CLOS" in (o.direction or "").upper()
        )


def _safe_float(val: Any) -> float | None:
    """Convert to float or return None."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> int | None:
    """Convert a number or numeric string to int, or return None."""
    number = _safe_float(val)
    return int(number) if number is not None else None


def _quote(item: dict, symbol: str, fundamentals: dict | None = None) -> Quote:
    """Build a Quote from a quote response and, optionally, fundamentals.

    Volume, P/E, market cap and the 52-week range are not in the quote
    response. They are filled from `fundamentals` when it is given.
    """
    price = float(item.get("last_trade_price", 0))
    prev_close = float(item.get("previous_close", 0))
    change_pct = ((price - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
    fundamentals = fundamentals or {}
    return Quote(
        symbol=symbol,
        price=price,
        prev_close=prev_close,
        change_pct=round(change_pct, 2),
        bid=float(item.get("bid_price", 0) or 0),
        ask=float(item.get("ask_price", 0) or 0),
        volume=_safe_int(fundamentals.get("volume")),
        pe_ratio=_safe_float(fundamentals.get("pe_ratio")),
        market_cap=_safe_float(fundamentals.get("market_cap")),
        high_52w=_safe_float(fundamentals.get("high_52_weeks")),
        low_52w=_safe_float(fundamentals.get("low_52_weeks")),
        timestamp=_parse_time(item.get("updated_at")),
    )


def _option_side(item: dict, legs: list[dict]) -> str:
    """'buy' or 'sell' for an option order.

    Robinhood gives the order a `direction` of 'debit' or 'credit', and
    only the legs a side. One leg's side is the order's. A spread has a
    leg each way, so it goes by direction: paying a debit is buying it.
    """
    if len(legs) == 1 and legs[0].get("side"):
        return legs[0]["side"]
    direction = item.get("direction", "")
    return {"debit": "buy", "credit": "sell"}.get(direction, direction)


def _option_contract(legs: list[dict]) -> dict[str, Any]:
    """The Order fields that describe an option order's legs."""
    if not legs:
        return {}
    effects = {leg.get("position_effect") for leg in legs}
    fields: dict[str, Any] = {
        "leg_count": len(legs),
        "position_effect": effects.pop() if len(effects) == 1 else None,
    }
    if len(legs) == 1:
        fields.update(
            option_type=legs[0].get("option_type"),
            strike=_safe_float(legs[0].get("strike_price")),
            expiration=legs[0].get("expiration_date"),
        )
    return fields


def _option_fees(item: dict) -> float | None:
    """Total fees on an option order, or None when it reports none.

    Option orders have no `fees` field. They split fees three ways, and
    the total is what `fees` means on a stock order.
    """
    parts = [
        _safe_float(item.get(key))
        for key in ("contract_fees", "regulatory_fees", "pro_trader_fees")
    ]
    present = [part for part in parts if part is not None]
    return round(sum(present), 6) if present else None


def _parse_time(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp from the API, or return None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _filled_at(item: dict, filled_quantity: float | None, last_fill: Any) -> datetime | None:
    """When an order last filled, including a partial fill.

    Uses the time of the last fill when the order carries one. Responses
    without one fall back to `updated_at`, but only for a completely filled
    order, since an unfilled order is updated by cancellation too.
    """
    if filled_quantity and last_fill:
        return _parse_time(last_fill)
    if item.get("state") == "filled":
        return _parse_time(item.get("updated_at"))
    return None


def _average_execution_price(executions: list[dict]) -> float | None:
    """Quantity-weighted average price across executions, or None."""
    total = quantity = 0.0
    for e in executions:
        price, qty = _safe_float(e.get("price")), _safe_float(e.get("quantity"))
        if price is None or not qty:
            continue
        total += price * qty
        quantity += qty
    return total / quantity if quantity else None
