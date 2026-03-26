"""PyhoodClient — high-level API for Robinhood operations.

All methods return typed dataclasses, not raw dicts.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from pyhood import urls
from pyhood.auth import get_session
from pyhood.exceptions import OrderError, SymbolNotFound
from pyhood.http import Session
from pyhood.models import (
    Candle,
    Earnings,
    OptionContract,
    OptionPosition,
    OptionsChain,
    Order,
    Position,
    Quote,
)

logger = logging.getLogger("pyhood")


class PyhoodClient:
    """High-level Robinhood API client.

    Usage:
        client = PyhoodClient(session)  # explicit session
        client = PyhoodClient()         # uses active session from pyhood.login()
    """

    def __init__(self, session: Session | None = None):
        self._session = session or get_session()

    # ── Stocks ──────────────────────────────────────────────────────────

    def get_quote(self, symbol: str) -> Quote:
        """Get a stock quote."""
        data = self._session.get(f"{urls.QUOTES}{symbol.upper()}/")
        if not data or "last_trade_price" not in data:
            raise SymbolNotFound(f"No quote data for {symbol}")

        price = float(data.get("last_trade_price", 0))
        prev_close = float(data.get("previous_close", 0))
        change_pct = ((price - prev_close) / prev_close * 100) if prev_close > 0 else 0.0

        return Quote(
            symbol=symbol.upper(),
            price=price,
            prev_close=prev_close,
            change_pct=round(change_pct, 2),
            bid=float(data.get("bid_price", 0) or 0),
            ask=float(data.get("ask_price", 0) or 0),
            volume=int(float(data.get("last_trade_volume", 0) or 0)),
        )

    def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Get quotes for multiple symbols (batched).

        Robinhood's quotes endpoint supports up to ~1,000 symbols per
        request (limited by URL length ~5,700 chars). We use 1,000 as
        a safe batch size.
        """
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
                price = float(item.get("last_trade_price", 0))
                prev_close = float(item.get("previous_close", 0))
                change_pct = ((price - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
                results[sym] = Quote(
                    symbol=sym,
                    price=price,
                    prev_close=prev_close,
                    change_pct=round(change_pct, 2),
                    bid=float(item.get("bid_price", 0) or 0),
                    ask=float(item.get("ask_price", 0) or 0),
                    volume=int(float(item.get("last_trade_volume", 0) or 0)),
                )
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

    def get_options_expirations(self, symbol: str) -> list[str]:
        """Get available options expiration dates for a symbol."""
        # Get instrument ID first
        inst_data = self._session.get(
            urls.INSTRUMENTS, params={"symbol": symbol.upper()}
        )
        inst_results = inst_data.get("results", [])
        if not inst_results:
            return []

        inst_id = inst_results[0].get("id", "")
        if not inst_id:
            return []

        # Get chains using instrument ID
        chains = self._session.get(
            urls.OPTIONS_CHAINS,
            params={"equity_instrument_ids": inst_id},
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

        Args:
            symbol: Ticker symbol.
            expiration: Expiration date (YYYY-MM-DD).
            option_type: Filter by 'call' or 'put'. None = both.
        """
        params: dict[str, str] = {
            "chain_symbol": symbol.upper(),
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
                    iv=float(md.get("implied_volatility", 0) or 0),
                    delta=float(md.get("delta", 0) or 0),
                    gamma=float(md.get("gamma", 0) or 0),
                    theta=float(md.get("theta", 0) or 0),
                    vega=float(md.get("vega", 0) or 0),
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
            report = entry.get("report", {})
            date = report.get("date", "")
            if today <= date <= cutoff:
                return Earnings(
                    symbol=symbol.upper(),
                    date=date,
                    timing=report.get("timing"),
                    eps_estimate=_safe_float(entry.get("eps", {}).get("estimate")),
                    eps_actual=_safe_float(entry.get("eps", {}).get("actual")),
                )
        return None

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
            avg_cost = float(item.get("average_buy_price", 0))

            # Get current price from the instrument
            instrument_url = item.get("instrument", "")
            current_price = 0.0
            if instrument_url:
                try:
                    inst_data = self._session.get(instrument_url)
                    symbol = inst_data.get("symbol", "")
                    quote = self.get_quote(symbol)
                    current_price = quote.price
                except Exception:
                    symbol = ""

            equity = qty * current_price
            cost_basis = qty * avg_cost
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
            account_number: Filter to specific account (e.g. '915060792' for IRA).
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
            avg_open = float(pos.get("average_open_price", 0)) / 100  # API returns per-contract, convert to per-share

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
            delta = 0.0
            iv = 0.0
            theta = 0.0
            if option_id:
                try:
                    md = self._session.get(
                        f"https://api.robinhood.com/marketdata/options/{option_id}/"
                    )
                    current_mark = float(md.get("mark_price", 0))
                    delta = float(md.get("delta", 0) or 0)
                    iv = float(md.get("implied_volatility", 0) or 0)
                    theta = float(md.get("theta", 0) or 0)
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

    def _get_instrument_url(self, symbol: str) -> str:
        """Get instrument URL from INSTRUMENTS endpoint."""
        data = self._session.get(urls.INSTRUMENTS, params={"symbol": symbol.upper()})
        results = data.get("results", [])
        if not results:
            raise SymbolNotFound(f"Instrument not found for symbol: {symbol}")
        return results[0].get("url", "")

    def _get_option_id(self, symbol: str, expiration: str, strike: float, option_type: str) -> str:
        """Find option instrument ID."""
        params = {
            "chain_symbol": symbol.upper(),
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
        account_number: str | None = None,
    ) -> Order:
        """Buy stock shares.

        Args:
            symbol: Stock ticker symbol.
            quantity: Number of shares to buy.
            price: Limit price. If None, places market order.
            stop_price: Stop price for stop/stop-limit orders.
            time_in_force: 'gtc' (good till cancelled), 'gtd', 'ioc', 'fok'.
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
        )

    def sell_stock(
        self,
        symbol: str,
        quantity: float,
        price: float | None = None,
        stop_price: float | None = None,
        time_in_force: str = "gtc",
        extended_hours: bool = False,
        account_number: str | None = None,
    ) -> Order:
        """Sell stock shares.

        Args:
            symbol: Stock ticker symbol.
            quantity: Number of shares to sell.
            price: Limit price. If None, places market order.
            stop_price: Stop price for stop/stop-limit orders.
            time_in_force: 'gtc' (good till cancelled), 'gtd', 'ioc', 'fok'.
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
    ) -> Order:
        """Place a stock order (core method).

        Args:
            symbol: Stock ticker symbol.
            quantity: Number of shares.
            side: 'buy' or 'sell'.
            price: Limit price. If None, places market order.
            stop_price: Stop price for stop/stop-limit orders.
            time_in_force: 'gtc' (good till cancelled), 'gtd', 'ioc', 'fok'.
            extended_hours: Whether to allow extended hours trading.
            account_number: Specific account (e.g. IRA). None = default.

        Returns:
            Order object with details.
        """
        # Determine order type and trigger
        if price is None and stop_price is None:
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

        payload = {
            "account": self._get_account_url(account_number),
            "instrument": self._get_instrument_url(symbol),
            "symbol": symbol.upper(),
            "price": str(price) if price else None,
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
        }

        # Remove None values
        payload = {k: v for k, v in payload.items() if v is not None}

        try:
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
            price: Limit price per contract.
            position_effect: 'open' or 'close'.
            time_in_force: 'gtc' (good till cancelled), 'gtd', 'ioc', 'fok'.
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
            price: Limit price per contract.
            position_effect: 'open' or 'close'.
            time_in_force: 'gtc' (good till cancelled), 'gtd', 'ioc', 'fok'.
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
            price: Limit price per contract.
            side: 'buy' or 'sell'.
            position_effect: 'open' or 'close'.
            credit_or_debit: 'debit' or 'credit'. Auto-determined from
                side if not provided (buy→debit, sell→credit).
            time_in_force: 'gtc' (good till cancelled), 'gtd', 'ioc', 'fok'.
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
        )

    def get_stock_orders(self) -> list[Order]:
        """Get all stock orders (not options).

        Returns:
            List of Order objects for stock orders.
        """
        data = self._session.get_paginated(urls.ORDERS)
        orders = []

        for item in data:
            # Skip option orders (they have legs)
            if "legs" in item or item.get("legs"):
                continue

            created_at = None
            filled_at = None

            if item.get("created_at"):
                try:
                    created_at = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
                except ValueError:
                    pass

            if item.get("updated_at") and item.get("state") == "filled":
                try:
                    filled_at = datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))
                except ValueError:
                    pass

            avg_price = None
            if item.get("average_filled_price"):
                avg_price = float(item["average_filled_price"])

            fees = None
            if item.get("fees"):
                fees = float(item["fees"])

            orders.append(Order(
                order_id=item.get("id", ""),
                symbol=item.get("symbol", "").upper(),
                side=item.get("side", ""),
                order_type=item.get("type", ""),
                quantity=float(item.get("quantity", 0)),
                price=float(item["price"]) if item.get("price") else None,
                status=item.get("state", "unknown"),
                created_at=created_at,
                filled_at=filled_at,
                stop_price=float(item["stop_price"]) if item.get("stop_price") else None,
                time_in_force=item.get("time_in_force", "gtc"),
                trigger=item.get("trigger", "immediate"),
                instrument_type="stock",
                average_price=avg_price,
                fees=fees,
            ))

        return orders

    def get_option_orders(self) -> list[Order]:
        """Get all option orders.

        Returns:
            List of Order objects for option orders.
        """
        data = self._session.get_paginated(urls.OPTIONS_ORDERS)
        orders = []

        for item in data:
            created_at = None
            filled_at = None

            if item.get("created_at"):
                try:
                    created_at = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
                except ValueError:
                    pass

            if item.get("updated_at") and item.get("state") == "filled":
                try:
                    filled_at = datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))
                except ValueError:
                    pass

            # Extract symbol from legs if available
            symbol = ""
            legs = item.get("legs", [])
            if legs and len(legs) > 0:
                leg = legs[0]
                option_url = leg.get("option", "")
                if option_url:
                    try:
                        option_data = self._session.get(option_url)
                        chain_symbol = option_data.get("chain_symbol", "")
                        symbol = chain_symbol.upper()
                    except Exception:
                        pass

            avg_price = None
            if item.get("average_filled_price"):
                avg_price = float(item["average_filled_price"])

            fees = None
            if item.get("fees"):
                fees = float(item["fees"])

            orders.append(Order(
                order_id=item.get("id", ""),
                symbol=symbol,
                side=item.get("direction", ""),  # options use 'direction' not 'side'
                order_type=item.get("type", ""),
                quantity=float(item.get("quantity", 0)),
                price=float(item["price"]) if item.get("price") else None,
                status=item.get("state", "unknown"),
                created_at=created_at,
                filled_at=filled_at,
                time_in_force=item.get("time_in_force", "gtc"),
                trigger=item.get("trigger", "immediate"),
                instrument_type="option",
                average_price=avg_price,
                fees=fees,
            ))

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

            created_at = None
            filled_at = None

            if data.get("created_at"):
                try:
                    created_at = datetime.fromisoformat(
                        data["created_at"].replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            if data.get("updated_at") and data.get("state") == "filled":
                try:
                    filled_at = datetime.fromisoformat(
                        data["updated_at"].replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            avg_price = None
            if data.get("average_filled_price"):
                avg_price = float(data["average_filled_price"])

            fees = None
            if data.get("fees"):
                fees = float(data["fees"])

            return Order(
                order_id=data.get("id", ""),
                symbol=data.get("symbol", "").upper(),
                side=data.get("side", ""),
                order_type=data.get("type", ""),
                quantity=float(data.get("quantity", 0)),
                price=float(data["price"]) if data.get("price") else None,
                status=data.get("state", "unknown"),
                created_at=created_at,
                filled_at=filled_at,
                stop_price=float(data["stop_price"]) if data.get("stop_price") else None,
                time_in_force=data.get("time_in_force", "gtc"),
                trigger=data.get("trigger", "immediate"),
                instrument_type="stock",
                average_price=avg_price,
                fees=fees,
            )
        except Exception:
            # Try option orders
            try:
                data = self._session.get(f"{urls.OPTIONS_ORDERS}{order_id}/")

                created_at = None
                filled_at = None

                if data.get("created_at"):
                    try:
                        created_at = datetime.fromisoformat(
                            data["created_at"].replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass

                if data.get("updated_at") and data.get("state") == "filled":
                    try:
                        filled_at = datetime.fromisoformat(
                            data["updated_at"].replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass

                # Extract symbol from legs if available
                symbol = ""
                legs = data.get("legs", [])
                if legs and len(legs) > 0:
                    leg = legs[0]
                    option_url = leg.get("option", "")
                    if option_url:
                        try:
                            option_data = self._session.get(option_url)
                            chain_symbol = option_data.get("chain_symbol", "")
                            symbol = chain_symbol.upper()
                        except Exception:
                            pass

                avg_price = None
                if data.get("average_filled_price"):
                    avg_price = float(data["average_filled_price"])

                fees = None
                if data.get("fees"):
                    fees = float(data["fees"])

                return Order(
                    order_id=data.get("id", ""),
                    symbol=symbol,
                    side=data.get("direction", ""),
                    order_type=data.get("type", ""),
                    quantity=float(data.get("quantity", 0)),
                    price=float(data["price"]) if data.get("price") else None,
                    status=data.get("state", "unknown"),
                    created_at=created_at,
                    filled_at=filled_at,
                    time_in_force=data.get("time_in_force", "gtc"),
                    trigger=data.get("trigger", "immediate"),
                    instrument_type="option",
                    average_price=avg_price,
                    fees=fees,
                )
            except Exception as e:
                raise OrderError(f"Order {order_id} not found") from e

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


def _safe_float(val: Any) -> float | None:
    """Convert to float or return None."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
