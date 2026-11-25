"""Data models — typed dataclasses instead of raw dicts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pyhood._model import Model


@dataclass(frozen=True)
class Quote(Model):
    """Stock quote data."""
    symbol: str
    price: float
    prev_close: float
    change_pct: float
    bid: float = 0.0
    ask: float = 0.0
    # The next five come from the fundamentals endpoint, not the quote, so
    # they are None unless the quote was fetched with
    # include_fundamentals=True.
    volume: int | None = None
    pe_ratio: float | None = None
    market_cap: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    timestamp: datetime | None = None  # when Robinhood last updated the quote


@dataclass(frozen=True)
class OptionContract(Model):
    """Single option contract with Greeks."""
    symbol: str
    option_type: str  # 'call' or 'put'
    strike: float
    expiration: str
    mark: float
    bid: float = 0.0
    ask: float = 0.0
    # Greeks are None when Robinhood publishes none, as it does on a
    # contract's expiration day. 0.0 is a real value, not a placeholder.
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
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
class OptionsChain(Model):
    """Full options chain for a symbol + expiration."""
    symbol: str
    expiration: str
    calls: list[OptionContract] = field(default_factory=list)
    puts: list[OptionContract] = field(default_factory=list)


@dataclass(frozen=True)
class Position(Model):
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
class Order(Model):
    """Order receipt."""
    order_id: str
    symbol: str
    # 'buy' or 'sell', for option orders too. Robinhood calls an option
    # order a 'debit' or a 'credit'; a debit is a buy and a credit a sell.
    side: str
    order_type: str  # 'market', 'limit', 'stop', 'stop_limit'
    quantity: float
    price: float | None
    status: str  # 'pending', 'filled', 'cancelled', 'rejected'
    created_at: datetime | None = None
    filled_at: datetime | None = None
    stop_price: float | None = None
    time_in_force: str = "gtc"  # 'gtc', 'gfd', 'ioc', 'fok'
    trigger: str = "immediate"  # 'immediate', 'stop'
    instrument_type: str = "stock"  # 'stock', 'option'
    average_price: float | None = None
    fees: float | None = None
    # Shares or contracts actually filled; `quantity` is what was ordered.
    # They differ on a partial fill, such as an IPO Access allocation.
    filled_quantity: float | None = None
    # The next five are for option orders, and None on stock orders.
    # leg_count is 1 for a single contract and more for a spread. The other
    # four describe the contract of a single-leg order. On a spread the legs
    # differ, so strike, expiration and option_type are None, and
    # position_effect is set only if every leg shares it.
    leg_count: int | None = None
    position_effect: str | None = None  # 'open' or 'close'
    option_type: str | None = None  # 'call' or 'put'
    strike: float | None = None
    expiration: str | None = None
    # The account the order is in. None if Robinhood did not say.
    account_number: str | None = None


@dataclass(frozen=True)
class Candle(Model):
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
class OptionPosition(Model):
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
    # Greeks (from market data); None when unpublished or the lookup failed
    delta: float | None = None
    iv: float | None = None
    theta: float | None = None


@dataclass(frozen=True)
class Earnings(Model):
    """Upcoming earnings info."""
    symbol: str
    date: str
    timing: str | None = None  # 'am', 'pm'
    eps_estimate: float | None = None
    eps_actual: float | None = None


# ── Settings / Notifications ─────────────────────────────────────────


@dataclass(frozen=True)
class NotificationSettings(Model):
    """User notification preferences (raw key-value pairs from API)."""
    settings: dict = field(default_factory=dict)

    def is_enabled(self, key: str) -> bool:
        """Check if a specific notification type is enabled."""
        return self.settings.get(key, False)


@dataclass(frozen=True)
class UserProfile(Model):
    """Basic user profile information."""
    username: str
    email: str
    first_name: str = ""
    last_name: str = ""
    id: str = ""
    created_at: str = ""


# ── Banking / ACH ────────────────────────────────────────────────────


@dataclass(frozen=True)
class BankAccount(Model):
    """Linked bank account (ACH relationship).

    Robinhood does not send the bank's name. `account_nickname` is the
    closest thing to one.
    """
    id: str
    holder_name: str  # the name on the bank account
    account_type: str  # 'checking' or 'savings'
    account_nickname: str = ""
    state: str = ""  # 'approved', 'pending', etc.
    url: str = ""
    last_four: str = ""  # the end of the bank account number; all Robinhood sends


@dataclass(frozen=True)
class ACHTransfer(Model):
    """ACH transfer record (deposit or withdrawal)."""
    id: str
    amount: float
    direction: str  # 'deposit' or 'withdraw'
    state: str  # 'pending', 'completed', 'cancelled'
    created_at: str = ""
    expected_landing_date: str = ""
    ach_relationship: str = ""


# ── Interest / Fees ──────────────────────────────────────────────────


@dataclass(frozen=True)
class InterestPayment(Model):
    """Cash sweep interest payment."""
    id: str
    amount: float
    currency: str = "USD"
    direction: str = ""  # 'credit' or 'debit'
    pay_date: str = ""
    pay_period_start: str = ""
    pay_period_end: str = ""
    payout_type: str = ""
    reason: str = ""
    account_number: str = ""


@dataclass(frozen=True)
class SubscriptionFee(Model):
    """Robinhood Gold subscription fee."""
    id: str
    amount: float
    date: str = ""
    state: str = ""
    credit: float = 0.0
    carry_forward_credit: float = 0.0
    created_at: str = ""
    account_number: str = ""


@dataclass(frozen=True)
class UnifiedTransfer(Model):
    """Transfer from the unified payment hub — ACH, internal, and others."""
    id: str
    amount: float
    currency: str = "usd"
    direction: str = ""
    transfer_type: str = ""
    state: str = ""
    description: str = ""
    originating_account_id: str = ""
    originating_account_type: str = ""
    receiving_account_id: str = ""
    receiving_account_type: str = ""
    created_at: str = ""
    completed_at: str = ""


# ── Debit Card ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class CardTransaction(Model):
    """Debit card (Cash Management) transaction."""
    id: str
    description: str
    amount: float
    category: str = ""
    direction: str = ""  # 'debit' or 'credit'
    state: str = ""  # 'completed', 'pending'
    initiated_at: str = ""
    completed_at: str = ""
    merchant: str = ""


# ── Watchlists ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Watchlist(Model):
    """A watchlist: one you created, or a Robinhood list you follow."""
    name: str
    symbols: list[str] = field(default_factory=list)
    id: str = ""


# ── Markets ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Market(Model):
    """Stock exchange / market info."""
    mic: str  # Market Identifier Code (e.g. 'XNYS', 'XNAS')
    name: str
    city: str
    country: str
    acronym: str = ""
    timezone: str = ""
    url: str = ""


@dataclass(frozen=True)
class MarketHours(Model):
    """Trading hours for a market on a specific date."""
    date: str
    is_open: bool
    opens_at: str = ""
    closes_at: str = ""
    extended_opens_at: str = ""
    extended_closes_at: str = ""


# ── Dividends ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Dividend(Model):
    """Dividend payment record."""
    symbol: str
    amount: float
    rate: float
    payable_date: str
    record_date: str
    state: str  # 'paid', 'pending', 'voided'
    instrument_url: str = ""
    id: str = ""


# ── Research / Discovery ─────────────────────────────────────────────


@dataclass(frozen=True)
class Rating(Model):
    """Analyst rating summary for a stock."""
    symbol: str
    num_buy: int = 0
    num_hold: int = 0
    num_sell: int = 0
    published_at: str = ""  # when the ratings were published, ISO-8601
    # Analysts' price targets, None when Robinhood publishes none.
    price_target_high: float | None = None
    price_target_low: float | None = None
    price_target_mean: float | None = None

    @property
    def total(self) -> int:
        return self.num_buy + self.num_hold + self.num_sell

    @property
    def buy_pct(self) -> float:
        return self.num_buy / self.total * 100 if self.total > 0 else 0.0


@dataclass(frozen=True)
class NewsArticle(Model):
    """News article for a stock."""
    title: str
    source: str
    url: str
    published_at: str = ""
    summary: str = ""
    related_instruments: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Mover(Model):
    """S&P 500 mover."""
    symbol: str
    # The move in dollars. Robinhood sends the percentage and the last
    # price, so this is worked out from those, and None without a price.
    price_change: float | None = None
    price_change_pct: float = 0.0
    instrument_url: str = ""
    price: float | None = None  # last price in regular hours


@dataclass(frozen=True)
class PortfolioCandle(Model):
    """Portfolio value at a point in time."""
    begins_at: str
    adjusted_open_equity: float
    adjusted_close_equity: float
    open_equity: float
    close_equity: float
    open_market_value: float
    close_market_value: float


@dataclass(frozen=True)
class Document(Model):
    """Account document (statement, confirmation, tax doc)."""
    id: str
    type: str
    date: str
    url: str = ""
    download_url: str = ""


@dataclass(frozen=True)
class StockSplit(Model):
    """Stock split record."""
    instrument: str
    execution_date: str
    multiplier: float
    divisor: float


# ── Futures ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FuturesContract(Model):
    """Futures contract details."""
    symbol: str
    name: str
    contract_id: str
    expiration: str
    # tick_size, underlying and asset_class come from the contract's product
    # record. They are None or empty if that lookup fails.
    tick_size: float | None
    multiplier: float
    status: str = "active"
    underlying: str = ""  # product symbol, e.g. 'ES'
    asset_class: str = ""  # e.g. 'stock_index', 'energy', 'metals'


@dataclass(frozen=True)
class FuturesOrderCheck(Model):
    """What Robinhood says about a futures order before it is placed.

    Every amount is None if Robinhood did not send it. `accepted` is None
    when the result is one pyhood has not seen and cannot read either way.
    """
    symbol: str
    side: str
    quantity: int
    result: str  # Robinhood's own word, e.g. VALIDATE_ORDER_RESULT_FAILURE_INSUFFICIENT_BP
    accepted: bool | None
    margin_required: float | None = None
    buying_power_effect: float | None = None  # negative: what the order ties up
    buying_power_after: float | None = None
    fees: float | None = None
    commission: float | None = None
    gold_savings: float | None = None


@dataclass(frozen=True)
class FuturesQuote(Model):
    """Real-time futures quote."""
    symbol: str
    last_price: float
    bid: float = 0.0
    ask: float = 0.0
    # The next four come from the futures fundamentals endpoint, not the
    # quote, so they are None unless the quote was fetched with
    # include_fundamentals=True.
    high: float | None = None
    low: float | None = None
    prev_close: float | None = None
    volume: int | None = None
    contract_id: str = ""


@dataclass(frozen=True)
class FuturesPnL(Model):
    """P&L extracted from a futures order."""
    realized_pnl: float
    direction: str  # 'OPENING' or 'CLOSING'
    order_id: str = ""


@dataclass(frozen=True)
class FuturesOrder(Model):
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
