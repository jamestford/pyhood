"""PyhoodClient — high-level API for Robinhood operations.

All methods return typed dataclasses, not raw dicts.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from pyhood import urls
from pyhood.auth import get_session
from pyhood.exceptions import SymbolNotFound
from pyhood.http import Session
from pyhood.models import Earnings, OptionContract, OptionsChain, Position, Quote

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
        """Get quotes for multiple symbols (batched)."""
        results: dict[str, Quote] = {}
        # Robinhood supports comma-separated symbols
        batch_size = 25
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

    # ── Options ─────────────────────────────────────────────────────────

    def get_options_expirations(self, symbol: str) -> list[str]:
        """Get available options expiration dates for a symbol."""
        # Get chain info for the symbol
        chains = self._session.get(
            urls.OPTIONS_CHAINS, params={"symbol": symbol.upper()}
        )
        results = chains.get("results", [chains] if "expiration_dates" in chains else [])
        for chain in results:
            if chain.get("symbol", "").upper() == symbol.upper():
                return chain.get("expiration_dates", [])
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
        inst_ids = [inst.get("id", "") for inst in instruments if inst.get("id")]
        market_data_map: dict[str, dict] = {}

        batch_size = 50
        for i in range(0, len(inst_ids), batch_size):
            batch = inst_ids[i : i + batch_size]
            md_url = f"{urls.OPTIONS_MARKET_DATA}"
            md_data = self._session.get(md_url, params={"instruments": ",".join(batch)})
            for item in md_data.get("results", []):
                if item and item.get("instrument_id"):
                    market_data_map[item["instrument_id"]] = item

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

    def get_positions(self, nonzero: bool = True) -> list[Position]:
        """Get current stock positions."""
        params = {"nonzero": "true"} if nonzero else {}
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

    def get_buying_power(self) -> float:
        """Get available buying power."""
        data = self._session.get_paginated(urls.ACCOUNTS)
        if data:
            return float(data[0].get("buying_power", 0))
        return 0.0


def _safe_float(val: Any) -> float | None:
    """Convert to float or return None."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
