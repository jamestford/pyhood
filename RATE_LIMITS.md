# Robinhood Rate Limits (Observed)

Robinhood has no documented rate limits. These are observed behaviors.

## Authentication

- **Login attempts:** 2-3 failed/timed-out attempts triggers account-wide 429 for 5+ minutes
- **Approval polling:** Same rate limit pool as login — if you're 429'd on login, you're 429'd everywhere
- **Cooldown:** Observed 5-10 minute lockout after hitting the limit
- **Device approval TTL:** Each `verification_workflow` has a short lifespan. New login = new workflow. Old approvals don't carry over.

### Best Practice
1. ONE login attempt at a time
2. Wait for explicit human confirmation of device approval before proceeding
3. If rate limited, wait **at least 5 minutes** before any retry
4. Never auto-retry auth flows

## Market Data

- **Quotes/fundamentals:** ~10-20 req/sec sustained appears safe
- **Options chains:** Heavier endpoints, use 0.5s delays between symbols
- **Earnings:** Lightweight, no observed issues

## General

- No `Retry-After` header is reliable — sometimes present, sometimes not
- 429s during auth block ALL API endpoints, not just auth
- Rate limits appear to be per-account, not per-IP
