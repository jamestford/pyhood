# pyhood

**A modern, reliable Python client for the Robinhood API.**

Built for automated trading — with auth that doesn't break, proper error handling, and sane defaults.

## Features

- 🔐 **Auth that just works** — Login with timeouts, automatic token refresh, and session persistence.
- 🔄 **Automatic token refresh** — OAuth refresh tokens renew your session silently — no credentials, no device approval, no human in the loop.
- 🏷️ **Type hints everywhere** — Full type annotations, dataclass responses, IDE-friendly.
- 🛡️ **Built-in rate limiting** — Automatic request throttling and retry logic.
- 📊 **Options-first** — Deep options chain support with Greeks, volume/OI analysis, and earnings integration.
- 📈 **Futures trading** — Contract details, real-time quotes, order history, and P&L calculation for futures.
- 🪙 **Dual API support** — Wraps both Robinhood's unofficial stocks/options API and their official Crypto Trading API.
- 🧪 **Tested and maintained** — 360 tests, CI across Python 3.10-3.14, linted with ruff.

## Quick Example

```python
import pyhood
from pyhood.client import PyhoodClient

session = pyhood.login(username="you@email.com", password="...", timeout=90)
client = PyhoodClient(session)

quote = client.get_quote("AAPL")
print(f"AAPL: ${quote.price:.2f} ({quote.change_pct:+.1f}%)")
```

## Next Steps

### Getting Started
- [Getting Started](getting-started.md) — Install and authenticate
- [Authentication](authentication.md) — Deep dive on login, refresh, and device approval

### Market Data
- [Stock Quotes](quotes.md) — Fetching market data
- [Options Chains](options.md) — Options with Greeks
- [Futures Trading](futures.md) — Contracts, quotes, orders, and P&L
- [Crypto Trading](crypto.md) — Official crypto API with API key auth
- [Fundamentals](fundamentals.md) — Fundamental data and screening

### Reference
- [API Reference](api/client.md) — Full API docs
- [Error Handling](error-handling.md) — Exception reference
- [Rate Limits](rate-limits.md) — Request throttling
- [Contributing](contributing.md) — Development guide
