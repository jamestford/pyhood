# Error Handling

pyhood uses a clear exception hierarchy so you can catch errors at the right level of specificity.

## Exception Hierarchy

```
PyhoodError
├── AuthError
│   ├── LoginTimeoutError      — Login hung (device approval timeout)
│   ├── TokenExpiredError       — Refresh token expired, full re-login needed
│   ├── DeviceApprovalRequiredError — Approval sent but not completed
│   └── MFARequiredError        — SMS/email code needed
├── RateLimitError              — Too many requests (429)
├── APIError                    — Robinhood API returned an error
├── OrderError                  — Order placement/modification failed
└── SymbolNotFoundError         — Ticker not recognized
```

## Catching Errors

### Catch Everything

```python
from pyhood.exceptions import PyhoodError

try:
    quote = client.get_quote("AAPL")
except PyhoodError as e:
    print(f"Something went wrong: {e}")
```

### Catch Specific Auth Errors

```python
from pyhood.exceptions import LoginTimeoutError, MFARequiredError, TokenExpiredError

try:
    session = pyhood.login(username="...", password="...", timeout=90)
except LoginTimeoutError:
    print("Timed out — approve on your phone and try again")
except MFARequiredError:
    code = input("Enter MFA code: ")
    session = pyhood.login(username="...", password="...", mfa_code=code)
except TokenExpiredError:
    print("Refresh token expired — full re-login needed")
```

### Handle Rate Limits

```python
from pyhood.exceptions import RateLimitError

try:
    quote = client.get_quote("AAPL")
except RateLimitError as e:
    print(f"Rate limited. Retry after: {e.retry_after}s")
```

### API Errors

```python
from pyhood.exceptions import APIError

try:
    data = client.get_fundamentals("INVALID")
except APIError as e:
    print(f"API error {e.status_code}: {e}")
    print(f"Response: {e.response}")
```

## Convenience Aliases

For those who prefer shorter names:

```python
from pyhood.exceptions import (
    LoginTimeout,          # → LoginTimeoutError
    TokenExpired,          # → TokenExpiredError
    DeviceApprovalRequired,# → DeviceApprovalRequiredError
    MFARequired,           # → MFARequiredError
    SymbolNotFound,        # → SymbolNotFoundError
)
```

## Automation Pattern

For unattended scripts (cron jobs, scanners), use this pattern:

```python
import pyhood
from pyhood.exceptions import TokenExpiredError, AuthError

def get_session():
    """Get an authenticated session, refreshing if needed."""
    try:
        return pyhood.refresh()
    except TokenExpiredError:
        # Refresh token expired — need human intervention
        # Alert via email/SMS/Telegram
        raise
    except AuthError:
        # No stored session — need initial login
        raise

session = get_session()
client = pyhood.PyhoodClient(session)
```
