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
    stop_price: float | None = None
    time_in_force: str = "gtc"  # 'gtc', 'gtd', 'ioc', 'fok'
    trigger: str = "immediate"  # 'immediate', 'stop'
    instrument_type: str = "stock"  # 'stock', 'option'
    average_price: float | None = None
    fees: float | None = None


@dataclass(frozen=True)
class Candle:
    """Single OHLCV price candle."""
    symbol: str
    begins_at: str
    open_price: float
    close_price: float
    high_price: float
    low_price: float
    volume: int
    session: str = "reg"
    interpolated: bool = False


@dataclass(frozen=True)
class OptionPosition:
    """Open option position with resolved details."""
    symbol: str
    option_type: str  # 'call' or 'put'
    strike: float
    expiration: str
    quantity: int
    average_open_price: float  # per-share (not per-contract)
    cost_basis: float  # total cost
    current_mark: float  # per-share
    current_value: float  # mark * quantity * 100
    unrealized_pl: float
    unrealized_pl_pct: float
    strategy: str  # e.g. 'long_call'
    option_id: str = ""
    account_number: str = ""
    # Greeks (from market data)
    delta: float = 0.0
    iv: float = 0.0
    theta: float = 0.0


@dataclass(frozen=True)
class Earnings:
    """Upcoming earnings info."""
    symbol: str
    date: str
    timing: str | None = None  # 'am', 'pm'
    eps_estimate: float | None = None
    eps_actual: float | None = None


# ── Settings / Notifications ─────────────────────────────────────────


@dataclass(frozen=True)
class NotificationSettings:
    """User notification preferences (raw key-value pairs from API)."""
    settings: dict = field(default_factory=dict)

    def is_enabled(self, key: str) -> bool:
        """Check if a specific notification type is enabled."""
        return self.settings.get(key, False)


@dataclass(frozen=True)
class UserProfile:
    """Basic user profile information."""
    username: str
    email: str
    first_name: str = ""
    last_name: str = ""
    id: str = ""
    created_at: str = ""


# ── Banking / ACH ────────────────────────────────────────────────────


@dataclass(frozen=True)
class BankAccount:
    """Linked bank account (ACH relationship)."""
    id: str
    bank_name: str
    account_type: str  # 'checking' or 'savings'
    account_nickname: str = ""
    state: str = ""  # 'approved', 'pending', etc.
    url: str = ""


@dataclass(frozen=True)
class ACHTransfer:
    """ACH transfer record (deposit or withdrawal)."""
    id: str
    amount: float
    direction: str  # 'deposit' or 'withdraw'
    state: str  # 'pending', 'completed', 'cancelled'
    created_at: str = ""
    expected_landing_date: str = ""
    ach_relationship: str = ""


# ── Watchlists ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Watchlist:
    """User watchlist."""
    name: str
    symbols: list[str] = field(default_factory=list)
    url: str = ""


# ── Markets ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Market:
    """Stock exchange / market info."""
    mic: str  # Market Identifier Code (e.g. 'XNYS', 'XNAS')
    name: str
    city: str
    country: str
    acronym: str = ""
    timezone: str = ""
    url: str = ""


@dataclass(frozen=True)
class MarketHours:
    """Trading hours for a market on a specific date."""
    date: str
    is_open: bool
    opens_at: str = ""
    closes_at: str = ""
    extended_opens_at: str = ""
    extended_closes_at: str = ""


# ── Dividends ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Dividend:
    """Dividend payment record."""
    symbol: str
    amount: float
    rate: float
    payable_date: str
    record_date: str
    state: str  # 'paid', 'pending', 'voided'
    instrument_url: str = ""
    id: str = ""


# ── Futures ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FuturesContract:
    """Futures contract details."""
    symbol: str
    name: str
    contract_id: str
    expiration: str
    tick_size: float
    multiplier: float
    status: str = "active"
    underlying: str = ""
    asset_class: str = ""


@dataclass(frozen=True)
class FuturesQuote:
    """Real-time futures quote."""
    symbol: str
    last_price: float
    bid: float = 0.0
    ask: float = 0.0
    high: float = 0.0
    low: float = 0.0
    prev_close: float = 0.0
    volume: int = 0
    open_interest: int = 0
    contract_id: str = ""


@dataclass(frozen=True)
class FuturesPnL:
    """P&L extracted from a futures order."""
    realized_pnl: float
    direction: str  # 'OPENING' or 'CLOSING'
    order_id: str = ""


@dataclass(frozen=True)
class FuturesOrder:
    """Futures order with status and P&L."""
    order_id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    order_type: str
    quantity: float
    price: float | None
    status: str
    created_at: str = ""
    direction: str = ""  # 'OPENING' or 'CLOSING'
    realized_pnl: float | None = None
    account_id: str = ""
