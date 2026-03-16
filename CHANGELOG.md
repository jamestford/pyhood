# Changelog

All notable changes to pyhood will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-16

### Added
- **Authentication** — Login with configurable timeouts, device approval handling, MFA support
- **Token Refresh** — `pyhood.refresh()` renews sessions via OAuth refresh tokens — no credentials or device approval needed
- **Auto-refresh on login** — `pyhood.login()` automatically tries refresh before falling back to full re-login
- **Stock Quotes** — `get_quote()` and `get_quotes()` with typed `Quote` dataclass responses
- **Options Chains** — `get_options_chain()` with full Greeks (IV, delta, gamma, theta, vega), volume/OI
- **Earnings** — `get_earnings()` with lookahead window
- **Account** — `get_positions()` with P/L calculations, `get_buying_power()`
- **Error Handling** — Full exception hierarchy: `LoginTimeoutError`, `TokenExpiredError`, `DeviceApprovalRequiredError`, `MFARequiredError`, `RateLimitError`, `APIError`, `SymbolNotFoundError`
- **Rate Limiting** — Built-in 250ms request throttling, automatic retry on 429
- **HTTP Session** — Managed session with pagination, retries, auth header management
- **Token Storage** — Persistent session at `~/.pyhood/session.json` with device token reuse
- **Type Hints** — Full annotations on all public APIs, frozen dataclasses
- **CI/CD** — GitHub Actions on Python 3.10-3.13, ruff linting, 58 tests
- **Security Scanning** — CodeQL, Bandit, pip-audit on every push
- **Documentation** — MkDocs Material site at jamestford.github.io/pyhood
- **Published on PyPI** — `pip install pyhood`

[0.1.0]: https://github.com/jamestford/pyhood/releases/tag/v0.1.0
