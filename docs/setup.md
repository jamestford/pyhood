# Setup

pyhood needs two unrelated kinds of credential, depending on what you trade.

| | Session tokens | Crypto API key pair |
|---|---|---|
| **Used for** | Stocks, options, futures | Crypto Trading API |
| **Stored at** | `~/.pyhood/session.json` | `~/.pyhood/crypto.env` |
| **Obtained by** | Logging in | Generating a key pair and registering the public half |
| **Lifetime** | Short, refreshes automatically | Long-lived; cannot be refreshed, only revoked |
| **Set up with** | `pyhood authorize` | `pyhood setup crypto` |

Both are written `0600` inside a `0700` directory, with the mode applied at creation so the contents are never briefly readable by other users on the machine.

## Checking what is configured

```bash
pyhood setup
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

## Authorizing pyhood

```bash
pyhood authorize
```

A saved authorization is tried first. If it still works, or can be renewed, no password is needed and the command says pyhood is already authorized. Otherwise it asks:

```text
pyhood Authorization

pyhood needs you to log in and authorize the connection between pyhood
and Robinhood. pyhood sends your password to Robinhood and does not save
it. Do not share your password with your agent or anyone else.

Once authorized, you will not be asked for your username and password
again. To remove this authorization, open the Robinhood app and go to
Account > Menu > Security and privacy > Devices, then remove the device.

Robinhood email or username:
Password (nothing shows as you type):

Sending your login to Robinhood...

Now open the Robinhood app on your phone and tap "Yes, it's me".
Waiting for you...

Authorized.
```

- **Your password is sent to Robinhood and is not saved.** What is saved is the key Robinhood hands back, in `~/.pyhood/session.json`.
- **The approval is on your phone.** Robinhood sends a prompt to its app, and you tap **"Yes, it's me"**. The command tells you to pick up your phone only once Robinhood has sent the prompt, and then waits up to five minutes. If Robinhood sends a code instead, the command asks for it.
- **Robinhood chooses the check, not pyhood.** For a new login it may ask for an approval in its app, a code, a bank verification, a selfie, or a photo of an ID. pyhood can finish the first two. For the others it stops and says which one Robinhood asked for.
- **To remove the authorization,** open the Robinhood app and go to Account, then Menu, then Security and privacy, then Devices, and remove the device.

`pyhood setup login` is an older name for the same command, and still works.

| If | It says |
|---|---|
| Nothing is typed | Nothing was entered, so nothing was sent |
| You press Ctrl-C | Cancelled. Nothing was saved |
| No approval arrives from your phone in time | Robinhood did not get an approval from your phone in time. Nothing was saved |
| Robinhood asks for a check pyhood cannot do | Robinhood did not send an approval request to your phone. It asked for a bank verification instead, which pyhood cannot do. Nothing was saved |
| Robinhood refuses the login | Robinhood did not accept the login, with Robinhood's reason. Nothing was saved |

### Authorizing from an AI agent

An agent cannot log in. The login needs your password, which the agent must never see, and an approval on your phone. An agent's commands also run without a terminal, so there is nowhere to type.

```bash
pyhood authorize --window
```

Run by the agent, this opens a terminal window on your screen, titled "pyhood Authorization", with the text above in it, and waits. You type in that window. Nothing you type passes through the agent, or through the chat. The agent is told:

```text
A terminal window titled "pyhood Authorization" has opened on the user's screen.
Tell the user: type your Robinhood username and password in that window,
then approve the request in the Robinhood app on your phone.
Never ask for, read or type their password.
Waiting up to 90 seconds for them to finish.
Authorized.
Check it with: pyhood verify
```

Agents stop a command that runs too long, so the wait is short and the command can be run again. `--wait SECONDS` changes how long it waits.

| What happens | What the command does | Exit code |
|---|---|---|
| pyhood is already authorized | Opens no window and says so | 0 |
| You log in | Says so | 0 |
| The login fails, or you close the window | Says the authorization did not finish | 1 |
| No window can be opened | Prints `pyhood authorize` for you to run yourself | 2 |
| You have not finished when the wait ends | Tells the agent to run it again | 3 |
| Robinhood asks for a check pyhood cannot do | Tells the agent to stop and tell you, and not to run it again | 4 |

- **Run again, it does not open a second window.** It goes back to waiting on the one that is open. A window nobody finished is taken to be gone after 15 minutes.
- **A window you closed does not come back by itself.** The next run reports that the authorization did not finish. Only the run after that opens a new one.
- **The window opens on macOS, and on Linux with a desktop.** On Windows, over SSH, or with no screen, the command prints `pyhood authorize` for you to run.
- **Run without a terminal, plain `pyhood authorize` says so** and points at `--window`.

## Setting up crypto keys

```bash
pyhood setup crypto
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
pyhood setup crypto --force
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
    raise SystemExit("run: pyhood authorize")

status = crypto_status()
if not status["private_key_valid"]:
    raise SystemExit(f"crypto credentials at {status['path']} are not usable")
```

Neither `crypto_status()` nor `session_status()` returns a secret value.
