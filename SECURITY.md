# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | ✅ Yes             |

## Reporting a Vulnerability

If you discover a security vulnerability in hood, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please email **security@pyhood.dev** (or use [GitHub's private vulnerability reporting](https://github.com/jamestford/pyhood/security/advisories/new)) with:

1. A description of the vulnerability
2. Steps to reproduce
3. Potential impact
4. Suggested fix (if any)

We will acknowledge receipt within 48 hours and aim to provide a fix within 7 days for critical issues.

## Security Considerations

### Credential Storage

- pyhood stores OAuth tokens in `~/.pyhood/session.json` with standard file permissions
- **Never commit** token files, `.env` files, or credentials to version control
- hood's `.gitignore` blocks `*.json` and `.env` by default
- Tokens are stored as plaintext JSON — ensure your machine has appropriate access controls

### Token Lifecycle

- Access tokens expire after several days (observed 5-8 days)
- Refresh tokens have a longer lifetime but will eventually expire
- hood rotates both tokens on each refresh — old tokens are invalidated
- Call `hood.logout()` to revoke tokens and delete stored credentials

### Network Security

- All API communication uses HTTPS (TLS) to `api.robinhood.com`
- pyhood does not disable certificate verification
- No credentials are sent in URL parameters — all auth data is in POST bodies or headers

### Dependencies

- hood uses a minimal dependency set: `requests`, `python-dotenv`, `cryptography`
- Dependencies are monitored via GitHub Dependabot (see `.github/dependabot.yml`)
- We recommend running `pip audit` periodically to check for known vulnerabilities

### What pyhood Does NOT Do

- pyhood does not store your Robinhood username or password
- pyhood does not transmit data to any server other than `api.robinhood.com`
- pyhood does not include telemetry, analytics, or tracking of any kind
