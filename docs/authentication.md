# Authentication

pyhood handles Robinhood's OAuth2 authentication with three layers of session management:

1. **Cached session** — Reuse a valid stored token (instant)
2. **Token refresh** — Exchange a refresh token for new credentials (no human needed)
3. **Full login** — Username + password + device approval (requires phone)

When you call `pyhood.login()`, it tries each layer in order, falling back only when necessary.

## Login Flow

```python
import pyhood

session = pyhood.login(
    username="you@email.com",
    password="your_password",
    timeout=90,
)
```

What happens internally:

1. Check `~/.pyhood/session.json` for a cached token
2. If found, validate it against Robinhood's API
3. If expired, try refreshing with the stored refresh token
4. If refresh fails, perform a full login with device approval

## Token Refresh

This is pyhood's killer feature. The refresh token lets you renew your session without any human interaction:

```python
import pyhood

# No username or password needed
session = pyhood.refresh()
```

Internally, this:

- Sends the stored `refresh_token` to Robinhood's OAuth endpoint
- Receives a **new** `access_token` and **new** `refresh_token`
- Saves both to `~/.pyhood/session.json`
- Invalidates the old tokens (they rotate on each refresh)

!!! tip "Use `pyhood.refresh()` in cron jobs and automation"
    Since refresh requires no credentials and no device approval, it's the ideal entry point for unattended scripts. Only fall back to `pyhood.login()` if refresh raises `TokenExpiredError`.

## Token Lifetime

| Token | Observed Lifetime | Notes |
|-------|------------------|-------|
| Access token | 5-8 days | Robinhood sets this server-side; the `expires_in` parameter in the login request is ignored |
| Refresh token | Unknown (weeks+) | Expires eventually; triggers `TokenExpiredError` |

!!! note
    Robinhood's token lifetimes are not documented and may change. pyhood handles expiration gracefully regardless of the actual lifetime.

## Device Approval

On first login (or when the refresh token expires), Robinhood requires device approval:

1. pyhood sends your credentials to Robinhood
2. Robinhood pushes a notification to your phone
3. You tap **"Yes, it's me"** in the Robinhood app
4. pyhood detects the approval and completes login

Device approval is **phone app only** — it's not available through the web interface.

### Timeouts

The `timeout` parameter controls how long pyhood waits for approval:

```python
# Wait up to 2 minutes
session = pyhood.login(username="...", password="...", timeout=120)
```

If you don't approve in time, pyhood raises `LoginTimeoutError`.

## Session Storage

Tokens are stored in `~/.pyhood/session.json`:

```json
{
  "access_token": "eyJ...",
  "token_type": "Bearer",
  "refresh_token": "abc...",
  "device_token": "12345-6789-...",
  "saved_at": 1710600000.0
}
```

- **`device_token`** is preserved across sessions to minimize re-verification
- **`saved_at`** tracks when tokens were last written
- File permissions are your OS defaults — secure your machine accordingly

## Logout

To revoke tokens and delete stored credentials:

```python
pyhood.logout()
```

This clears the session, removes `~/.pyhood/session.json`, and attempts to revoke the token server-side.

## MFA / Two-Factor Authentication

If your Robinhood account uses SMS or email-based MFA:

```python
from pyhood.exceptions import MFARequiredError

try:
    session = pyhood.login(username="...", password="...")
except MFARequiredError:
    code = input("Enter MFA code: ")
    session = pyhood.login(username="...", password="...", mfa_code=code)
```
