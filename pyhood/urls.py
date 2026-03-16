"""Robinhood API URL definitions — single source of truth."""

BASE = "https://api.robinhood.com"
OAUTH = "https://api.robinhood.com/oauth2"

# Auth
LOGIN = f"{OAUTH}/token/"
LOGOUT = f"{OAUTH}/revoke_token/"

# Account
ACCOUNTS = f"{BASE}/accounts/"
POSITIONS = f"{BASE}/positions/"
PORTFOLIOS = f"{BASE}/portfolios/"

# Stocks
QUOTES = f"{BASE}/quotes/"
INSTRUMENTS = f"{BASE}/instruments/"
FUNDAMENTALS = f"{BASE}/fundamentals/"
HISTORICALS = f"{BASE}/marketdata/historicals/"

# Options
OPTIONS_BASE = f"{BASE}/options/"
OPTIONS_CHAINS = f"{OPTIONS_BASE}chains/"
OPTIONS_INSTRUMENTS = f"{OPTIONS_BASE}instruments/"
OPTIONS_ORDERS = f"{OPTIONS_BASE}orders/"
OPTIONS_MARKET_DATA = f"{BASE}/marketdata/options/"

# Orders
ORDERS = f"{BASE}/orders/"

# Markets
MARKETS = f"{BASE}/markets/"
MARKET_HOURS = f"{BASE}/markets/{{market}}/hours/{{date}}/"

# Earnings
EARNINGS = f"{BASE}/marketdata/earnings/"

# Watchlists
WATCHLISTS = f"{BASE}/midlands/lists/default/"
