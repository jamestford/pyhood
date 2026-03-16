# pyhood

**A modern, reliable Python client for the Robinhood API.**

Built for automated trading — with auth that doesn't break, proper error handling, and sane defaults.

## Features

- 🔐 **Auth that just works** — Login with timeouts, automatic token refresh, and session persistence.
- 🔄 **Automatic token refresh** — OAuth refresh tokens renew your session silently — no credentials, no device approval, no human in the loop.
- 🏷️ **Type hints everywhere** — Full type annotations, dataclass responses, IDE-friendly.
- 🛡️ **Built-in rate limiting** — Automatic request throttling and retry logic.
- 📊 **Options-first** — Deep options chain support with Greeks, volume/OI analysis, and earnings integration.
- 🧪 **Tested and maintained** — 58+ tests, CI across Python 3.10-3.13, linted with ruff.

## Quick Example

```python
import hood
from hood.client import HoodClient

session = hood.login(username="you@email.com", password="...", timeout=90)
client = HoodClient(session)

quote = client.get_quote("AAPL")
print(f"AAPL: ${quote.price:.2f} ({quote.change_pct:+.1f}%)")
```

## Next Steps

- [Getting Started](getting-started.md) — Install and authenticate
- [Authentication](authentication.md) — Deep dive on login, refresh, and device approval
- [Stock Quotes](quotes.md) — Fetching market data
- [Options Chains](options.md) — Options with Greeks
- [API Reference](api/client.md) — Full API docs
