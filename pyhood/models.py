"""Data models — typed dataclasses instead of raw dicts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Quote:
    """Stock quote data."""
    symbol: str
    price: float
    prev_close: float
    change_pct: float
    bid: float = 0.0
    ask: float = 0.0
    volume: int = 0
    pe_ratio: float | None = None
    market_cap: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    timestamp: datetime | None = None


@dataclass(frozen=True)
class OptionContract:
    """Single option contract with Greeks."""
    symbol: str
    option_type: str  # 'call' or 'put'
    strike: float
    expiration: str
    mark: float
    bid: float = 0.0
    ask: float = 0.0
    iv: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    volume: int = 0
    open_interest: int = 0
    option_id: str = ""

    @property
    def vol_oi_ratio(self) -> float:
        return self.volume / self.open_interest if self.open_interest > 0 else 0.0

    @property
    def cost_per_contract(self) -> float:
        return round(self.mark * 100, 2)


@dataclass(frozen=True)
class OptionsChain:
    """Full options chain for a symbol + expiration."""
    symbol: str
    expiration: str
    calls: list[OptionContract] = field(default_factory=list)
    puts: list[OptionContract] = field(default_factory=list)


@dataclass(frozen=True)
class Position:
    """Account position."""
    symbol: str
    quantity: float
    average_cost: float
    current_price: float
    equity: float
    unrealized_pl: float
    unrealized_pl_pct: float
    instrument_type: str = "stock"  # 'stock' or 'option'


@dataclass(frozen=True)
class Order:
    """Order receipt."""
    order_id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    order_type: str  # 'market', 'limit', 'stop', 'stop_limit'
    quantity: float
    price: float | None
    status: str  # 'pending', 'filled', 'cancelled', 'rejected'
    created_at: datetime | None = None
    filled_at: datetime | None = None


@dataclass(frozen=True)
class Earnings:
    """Upcoming earnings info."""
    symbol: str
    date: str
    timing: str | None = None  # 'am', 'pm'
    eps_estimate: float | None = None
    eps_actual: float | None = None
