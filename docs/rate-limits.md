# Rate Limits

Robinhood has no documented rate limits. Everything here is based on observed behavior and may change without notice.

## Authentication

| Behavior | Observed Limit |
|----------|---------------|
| Failed login attempts | 2-3 before lockout |
| Lockout duration | 5-10 minutes |
| Lockout scope | Account-wide (all endpoints) |
| Approval polling | Same rate limit pool as login |

!!! danger "Do not retry failed logins"
    After a failed login attempt, wait **at least 5 minutes** before trying again. Rapid retries will lock out your entire account's API access.

### Best Practices

1. **One login attempt at a time** — never run concurrent logins
2. **Wait for explicit approval** — don't assume device approval succeeded
3. **Use `hood.refresh()`** — avoids the login flow entirely
4. **If rate limited, stop** — wait 5+ minutes, don't keep hitting the endpoint

## Market Data

| Endpoint | Observed Safe Rate |
|----------|-------------------|
| Stock quotes | ~10-20 req/sec |
| Fundamentals | ~10-20 req/sec |
| Options chains | ~2 req/sec (heavier payload) |
| Earnings | ~10 req/sec |
| Positions/Account | ~5 req/sec |

hood enforces a **250ms minimum** between all requests by default, which keeps you well within safe limits.

## How hood Handles Rate Limits

1. **Minimum delay** — 250ms between all requests (configurable)
2. **429 detection** — Automatically retries with backoff when rate limited
3. **Max retries** — 2 retries before raising `RateLimitError`
4. **Retry-After header** — Respected when Robinhood provides it

## General Notes

- Rate limits appear to be **per-account**, not per-IP
- 429s during authentication block **all** API endpoints
- The `Retry-After` header is sometimes present, sometimes not
- No official documentation exists — these observations may become outdated
