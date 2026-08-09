# Setup

pyhood needs two unrelated kinds of credential, depending on what you trade.

| | Session tokens | Crypto API key pair |
|---|---|---|
| **Used for** | Stocks, options, futures | Crypto Trading API |
| **Stored at** | `~/.pyhood/session.json` | `~/.pyhood/crypto.env` |
| **Obtained by** | Logging in | Generating a key pair and registering the public half |
| **Lifetime** | Short, refreshes automatically | Long-lived; cannot be refreshed, only revoked |
| **Set up with** | `python -m pyhood setup login` | `python -m pyhood setup crypto` |

Both are written `0600` inside a `0700` directory, with the mode applied at creation so the contents are never briefly readable by other users on the machine.

## Checking what is configured

```bash
python -m pyhood setup
```

```
Session (main API — stocks, options, futures)
    /Users/you/.pyhood/session.json (refreshable, saved 1.2h ago)

Crypto API (official Crypto Trading API)
    source: file
    /Users/you/.pyhood/crypto.env
    api key: 43 chars
    private key: valid Ed25519, 32 bytes
```

This makes no network calls and prints no secret values — only lengths, byte counts and validity. It exits non-zero when something is missing or malformed, so it works in a health check.

It reports three things that are easy to get wrong and hard to diagnose:

- **Which source is in use.** `RH_CRYPTO_API_KEY` and `RH_CRYPTO_PRIVATE_KEY` take precedence over the file, so a stale `export` left in a shell profile silently shadows correct credentials on disk. The symptom is an authentication failure that looks like a server problem.
- **Whether the private key is real.** A placeholder pasted from documentation is valid text but not a valid Ed25519 key. This shows up as `not valid base64` or a byte count other than 32.
- **Whether the files are owner-only.** A credential file readable by other users is reported with the `chmod` to fix it.

## Logging in

```bash
python -m pyhood setup login
```

The stored session is tried first — if it is valid, or can be refreshed, no password is needed at all. Only when that fails does it prompt:

```
Robinhood needs your username and password for a fresh login.
The password is read without echoing, is not stored, and is not
written anywhere — only the resulting tokens are saved to disk.

Robinhood email/username: you@email.com
Password (hidden):
```

Robinhood then sends a device approval prompt to your phone. Tap **"Yes, it's me"**. If your account uses MFA, the command asks for the code and retries.

Only the resulting tokens are written to disk. The password is not stored anywhere.

## Setting up crypto keys

```bash
python -m pyhood setup crypto
```

Robinhood does not issue you a key pair. You generate one, register the public half, and Robinhood issues an API key that identifies it. The command runs the whole exchange:

1. **Generates an Ed25519 key pair** on your machine. The private key is written straight to the credentials file and is never displayed.
2. **Prints the public key** with the URL to register it: [robinhood.com/account/crypto](https://robinhood.com/account/crypto) → API Trading → Add key.
3. **Reads the API key** Robinhood issues, without echoing it.
4. **Writes both** to `~/.pyhood/crypto.env` at mode `0600`.
5. **Verifies** with one signed read-only call, reporting the account status and fee tier.

Step 5 is the point of the command. Writing a file proves nothing; the question is whether Robinhood accepts the pair. Without it, a mistyped or placeholder key is not discovered until your first real request fails with an authentication error that reads like a service problem.

If credentials already exist, the command refuses to run rather than replacing them — overwriting would orphan a key that still works. Pass `--force` when you actually intend to rotate.

```bash
python -m pyhood setup crypto --force
```

Use `--no-verify` to skip the live check, for example when registering the public key on a different machine from the one that will use it.

## Doing it by hand

Neither command is required. `~/.pyhood/crypto.env` is a plain env file:

```
RH_CRYPTO_API_KEY=the-key-robinhood-issued
RH_CRYPTO_PRIVATE_KEY=the-private-key-you-generated
```

```bash
chmod 600 ~/.pyhood/crypto.env
```

and the session can be established from code:

```python
import pyhood

session = pyhood.login(username="you@email.com", password="...", timeout=90)
```

## How secrets are handled

The behaviour these commands commit to:

- Secrets are read with `getpass`, so they do not echo and do not enter shell history.
- **There are no options for passing secrets.** No `--password`, no `--api-key`. Command-line arguments are visible to every process on the machine through `ps`, and your shell records them.
- The crypto private key goes from generation directly to disk. It is never printed, not once.
- Nothing secret is printed back. Reports show lengths, byte counts and validity.
- Credential files are created `0600` inside a `0700` directory, with the mode applied at `open()` rather than by a `chmod` afterwards, so there is no window where the contents are world-readable.

## Programmatic use

The same functions are importable, which is what the tests use:

```python
from pyhood.onboarding import crypto_status, session_status, print_status

if not session_status()["exists"]:
    raise SystemExit("run: python -m pyhood setup login")

status = crypto_status()
if not status["private_key_valid"]:
    raise SystemExit(f"crypto credentials at {status['path']} are not usable")
```

Neither `crypto_status()` nor `session_status()` returns a secret value.
