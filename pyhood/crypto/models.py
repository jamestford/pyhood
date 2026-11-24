"""Crypto data models — typed dataclasses for Robinhood Crypto API responses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pyhood._model import Model


@dataclass(frozen=True)
class CryptoQuote(Model):
    """Crypto quote data with best bid/ask."""
    symbol: str
    bid: float
    ask: float
    timestamp: datetime


@dataclass(frozen=True)
class CryptoHolding(Model):
    """Crypto asset holding information."""
    asset_code: str
    quantity: float
    available_quantity: float


@dataclass(frozen=True)
class CryptoAccount(Model):
    """Crypto trading account information.

    Fee information arrives as a `fee_tier_status` object rather than a tier
    name, so `fee_tier` is rendered from `fee_ratio` — e.g. `'0.95%'`.
    """
    account_number: str
    buying_power: float
    status: str
    fee_tier: str = ""
    fee_ratio: float = 0.0
    thirty_day_volume: float = 0.0
    next_fee_tier_ratio: float = 0.0
    next_fee_tier_threshold: float = 0.0
    api_tradable: bool = False


@dataclass(frozen=True)
class TradingPair(Model):
    """Trading pair configuration and limits.

    `tradable` reflects Robinhood's `status`; `api_tradable` reflects
    `is_api_tradable`, which is the one that governs API orders. A pair can be
    tradable in the app but not through the API.
    """
    symbol: str
    tradable: bool
    # Robinhood sends the smallest order as a value in the quote currency,
    # min_order_amount below, and no smallest quantity of the coin. So
    # this is None unless a response carries one.
    min_order_size: float | None
    max_order_size: float
    price_increment: float
    quantity_increment: float
    base_currency: str
    quote_currency: str
    api_tradable: bool = False
    status: str = ""
    min_order_amount: float | None = None  # smallest order, in the quote currency


@dataclass(frozen=True)
class EstimatedPrice(Model):
    """Estimated price for a crypto trade."""
    symbol: str
    side: str  # 'buy' or 'sell'
    quantity: float
    bid_price: float
    ask_price: float
    fee: float


@dataclass(frozen=True)
class CryptoCandle(Model):
    """Single OHLCV price candle for a crypto asset."""
    symbol: str
    begins_at: str
    open_price: float
    close_price: float
    high_price: float
    low_price: float
    volume: float


@dataclass(frozen=True)
class CryptoOrder(Model):
    """Crypto order information."""
    order_id: str
    client_order_id: str | None
    side: str  # 'buy' or 'sell'
    order_type: str  # 'market' or 'limit'
    symbol: str
    status: str
    price: float | None
    quantity: float
    filled_quantity: float
    remaining_quantity: float
    average_filled_price: float | None
    fee: float | None
    created_at: datetime
    updated_at: datetime
