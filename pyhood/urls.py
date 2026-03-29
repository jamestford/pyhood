"""Robinhood API URL definitions — single source of truth.

Batch limits (tested & verified):
- /fundamentals/ — 100 symbols max (hard count limit)
- /quotes/ — ~1,220 symbols max (URL length ~5,700 chars)
- /marketdata/options/ — ~17 instrument URLs max (URL length)
"""

BASE = "https://api.robinhood.com"
OAUTH = "https://api.robinhood.com/oauth2"

# Auth
LOGIN = f"{OAUTH}/token/"
LOGOUT = f"{OAUTH}/revoke_token/"

# Account
ACCOUNTS = f"{BASE}/accounts/"
POSITIONS = f"{BASE}/positions/"
PORTFOLIOS = f"{BASE}/portfolios/"

# Stocks — Market Data
QUOTES = f"{BASE}/quotes/"
INSTRUMENTS = f"{BASE}/instruments/"
INDEXES = f"{BASE}/indexes/"
FUNDAMENTALS = f"{BASE}/fundamentals/"
HISTORICALS = f"{BASE}/marketdata/historicals/"
RATINGS = f"{BASE}/midlands/ratings/"
NEWS = f"{BASE}/midlands/news/"
EARNINGS = f"{BASE}/marketdata/earnings/"

# Options
OPTIONS_BASE = f"{BASE}/options/"
OPTIONS_CHAINS = f"{OPTIONS_BASE}chains/"
OPTIONS_INSTRUMENTS = f"{OPTIONS_BASE}instruments/"
OPTIONS_ORDERS = f"{OPTIONS_BASE}orders/"
OPTIONS_POSITIONS = f"{OPTIONS_BASE}aggregate_positions/"
OPTIONS_MARKET_DATA = f"{BASE}/marketdata/options/"

# Orders
ORDERS = f"{BASE}/orders/"

# Markets
MARKETS = f"{BASE}/markets/"
MARKET_HOURS = f"{BASE}/markets/{{market}}/hours/{{date}}/"

# Discovery & Lists
MOVERS_SP500 = f"{BASE}/midlands/movers/sp500/"
TAGS = f"{BASE}/midlands/tags/tag/"
WATCHLISTS = f"{BASE}/midlands/lists/default/"
WATCHLISTS_V2 = f"{BASE}/midlands/lists/"

# Banking / ACH
ACH_RELATIONSHIPS = f"{BASE}/ach/relationships/"
ACH_TRANSFERS = f"{BASE}/ach/transfers/"
ACH_DEPOSIT_SCHEDULES = f"{BASE}/ach/deposit_schedules/"

# Profile & Settings
USER = f"{BASE}/user/"
INVESTMENT_PROFILE = f"{BASE}/user/investment_profile/"
NOTIFICATION_SETTINGS = f"{BASE}/settings/notifications/"
NOTIFICATION_DEVICES = f"{BASE}/notifications/devices/"

# Dividends
DIVIDENDS = f"{BASE}/dividends/"

# Documents
DOCUMENTS = f"{BASE}/documents/"

# Portfolio Historicals
PORTFOLIO_HISTORICALS = f"{BASE}/portfolios/historicals/{{account_number}}/"

# Options Historicals
OPTIONS_HISTORICALS = f"{BASE}/marketdata/options/historicals/"

# Popularity / Splits
POPULARITY = f"{BASE}/instruments/{{instrument_id}}/popularity/"
SPLITS = f"{BASE}/instruments/{{instrument_id}}/splits/"

# Day Trades / Margin
DAY_TRADES = f"{BASE}/accounts/{{account_id}}/recent_day_trades/"
MARGIN_CALLS = f"{BASE}/margin/calls/"

# Futures
FUTURES_CONTRACTS = f"{BASE}/arsenal/v1/futures/contracts/"
FUTURES_QUOTES = f"{BASE}/marketdata/futures/quotes/v1/"
FUTURES_ACCOUNTS = f"{BASE}/ceres/v1/accounts/"


def index_market_data_url(index_id: str) -> str:
    """URL for index market data (e.g. SPX, NDX)."""
    return f"{BASE}/marketdata/indexes/values/v1/{index_id}/"


def futures_contract_url(symbol: str) -> str:
    """URL for a single futures contract by symbol (e.g. 'ESH26')."""
    return f"{FUTURES_CONTRACTS}symbol/{symbol}/"


def futures_orders_url(account_id: str) -> str:
    """URL for futures orders on a specific account."""
    return f"{FUTURES_ACCOUNTS}{account_id}/orders/"
