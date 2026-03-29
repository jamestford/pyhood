# Pyhood Project Status

## Overview
Modern Robinhood API client library. Public package on PyPI replacing abandoned robin_stocks.

## Repository & Distribution
- **Repo:** github.com/jamestford/pyhood (public)
- **PyPI:** pyhood package
- **Local:** ~/Projects/pyhood
- **Venv:** .venv (Python 3.14)

## Authentication & Session
- **Token Storage:** ~/.pyhood/session.json
- **Session Fields:** access_token, token_type, refresh_token, device_token, saved_at
- **Account:** ~$16K balance, authenticated and working

## Key Features

### Authentication (Major Improvement)
- **Login:** With timeouts, device approval handling
- **Token Refresh:** `pyhood.refresh()` — NO device approval needed!
- **Token Lifetime:** ~5-8 days (not 24h as commonly assumed)
- **Auto-Recovery:** `login()` tries refresh first, falls back to full re-login
- **Rate Limit Protection:** Aggressive safeguards against Robinhood's auth rate limits

### Trading Features
- Stocks/options quotes with Greeks
- Options chains with full contract details (equity + index options: SPX, NDX, VIX, RUT, XSP)
- Stock historical data (5-year lookback)
- Order placement (market/limit/stop/stop-limit)
- Options orders
- Buying power and positions
- Account information
- Futures trading (contracts, quotes, orders, P&L)

### Banking & Account Features
- ACH bank account listing and management
- ACH transfer history (deposits/withdrawals)
- Initiate and cancel transfers
- Dividend history with symbol filtering
- Watchlist management (list, add, remove)
- Markets and trading hours lookup
- User profile and notification settings

### Crypto Features
- **Official Crypto API:** ED25519 key-based authentication
- **Separate from stock auth:** Uses crypto-specific credentials
- **Full trading support:** Orders, quotes, portfolios
- **Keys stored separately:** Crypto keys in pyhood config

## Testing & Quality
- **Test Coverage:** ~79% (197 tests passing)
- **CI Pipeline:** GitHub Actions on Python 3.10-3.13
- **Linting:** ruff for code style
- **HTTP Mocking:** responses library for reliable tests

## Authentication Lessons (Critical)
- **Rate Limits:** 2-3 failed auth attempts → 5+ minute account-wide lockout
- **Device Approval TTL:** Each verification workflow has short expiration
- **Headers Matter:** Must use robin_stocks style headers (`Accept: */*`, `User-Agent: *`)
- **NEVER retry without human confirmation** of device approval
- **Refresh tokens work!** — Key differentiator from robin_stocks

## IRA Support (v0.3.0)
- **Roth IRA Account:** 915060792 (ira_roth, cash account, option_level_2)
- **Individual Account:** 946351343 (margin)
- **Discovery:** `get_all_accounts()` via bonfire `/accounts/unified/`
- **IRA Positions:** Use `account_number` param for stocks, `account_numbers` (plural) for options
- **IRA Orders:** Standard endpoints work with IRA account URL in payload
- **Docs:** `docs/ira-api-notes.md` — full reverse-engineering notes
- **Key gotcha:** `/accounts/` never shows IRA — must use bonfire or direct URL

## Current Projects

### Nightly Scanner Integration
- **Challenge:** Scanner broken due to pyhood OptionContract model changes
- **Solution:** Migrate scanner from robin_stocks to pyhood
- **Advantage:** `pyhood.refresh()` enables self-healing auth

## API Architecture
- `pyhood/auth.py` — Login, refresh, device approval
- `pyhood/client.py` — Main HoodClient class
- `pyhood/http.py` — Rate-limited HTTP with retries
- `pyhood/models.py` — Typed dataclasses for all responses
- `pyhood/exceptions.py` — Complete exception hierarchy
- `pyhood/urls.py` — All Robinhood API endpoints

## Token Refresh Discovery
**Game-changing finding:** Robinhood refresh tokens actually work!
- Exchange refresh_token for new access+refresh pair
- No device approval required
- Tokens rotate on refresh (old ones invalidated)
- This enables automated systems to self-heal
- robin_stocks never implemented this critical feature

## Recent Fixes
- **Linting:** All ruff failures resolved
- **CI status:** All tests passing across Python 3.10-3.13