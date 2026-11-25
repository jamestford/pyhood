"""Guided setup for the credentials pyhood needs.

pyhood uses two unrelated kinds of credential:

- **Session tokens** (``~/.pyhood/session.json``) for the main Robinhood API,
  obtained by logging in. Short-lived and refreshable.
- **A Crypto API key pair** (``~/.pyhood/crypto.env``) for the official Crypto
  Trading API. Long-lived and *not* refreshable — a leaked private key can
  trade until it is revoked.

Run interactively, either as the ``pyhood`` console script or as a module
(``python -m pyhood``) — the two are equivalent::

    pyhood version         # the installed version
    pyhood setup           # what is configured, and what is not
    pyhood authorize       # log in, so pyhood may use the account
    pyhood authorize --window     # open a window for the user to do that in
    pyhood setup crypto    # generate and register a key pair

Handling of secrets, which the rest of this module is built around:

- Secrets are read with :func:`getpass.getpass`, so they do not echo and do not
  enter shell history. There are deliberately no ``--api-key`` or ``--password``
  options: command-line arguments are visible to every process on the machine
  via ``ps`` and are recorded by the shell.
- The crypto private key is generated locally and written straight to disk. It
  is never displayed, not even once.
- Nothing secret is printed back. Reports show lengths, byte counts and
  validity — never values.
- Credential files are written ``0600`` inside a ``0700`` directory.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import stat
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pyhood.crypto.credentials import (
    API_KEY_VAR,
    PRIVATE_KEY_VAR,
    credentials_path,
    credentials_source,
    load_credentials,
)
from pyhood.secure_files import write_private

#: Where Robinhood manages Crypto API keys.
KEY_MANAGEMENT_URL = "https://robinhood.com/account/crypto"

#: Valid raw sizes for an Ed25519 private key: a 32-byte seed, or a seed
#: concatenated with its public key.
ED25519_KEY_SIZES = (32, 64)

Printer = Callable[[str], Any]
Prompt = Callable[[str], str]


class CancelledError(Exception):
    """The operator interrupted a prompt."""


def _ask(prompt: Prompt, question: str) -> str:
    """Read an answer, turning an interrupt into a clean exit.

    Ctrl-C at a credential prompt is an ordinary way to back out, so it
    should print one line rather than a traceback — which on a shared screen
    would also expose local paths.
    """
    try:
        return prompt(question)
    except (KeyboardInterrupt, EOFError) as e:
        raise CancelledError from e


# ── Status ───────────────────────────────────────────────────────────


def _file_mode(path: Path) -> int | None:
    """Permission bits of a file, or None if it does not exist."""
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return None


def _owner_only(mode: int | None) -> bool:
    """Whether a mode denies all access to group and other."""
    return mode is not None and not mode & 0o077


def crypto_status() -> dict[str, Any]:
    """Describe the stored crypto credentials without revealing them.

    Returns:
        Keys: ``source`` ('environment', 'file' or 'none'), ``path``,
        ``exists``, ``mode``, ``owner_only``, ``api_key_chars``,
        ``private_key_bytes`` and ``private_key_valid``.
    """
    path = credentials_path()
    mode = _file_mode(path)
    info: dict[str, Any] = {
        "source": credentials_source(),
        "path": path,
        "exists": path.is_file(),
        "mode": mode,
        "owner_only": _owner_only(mode),
        "api_key_chars": 0,
        "private_key_bytes": None,
        "private_key_valid": False,
    }

    try:
        api_key, private_key = load_credentials()
    except FileNotFoundError:
        return info

    info["api_key_chars"] = len(api_key)
    try:
        raw = base64.b64decode(private_key, validate=True)
    except Exception:
        return info
    info["private_key_bytes"] = len(raw)
    info["private_key_valid"] = len(raw) in ED25519_KEY_SIZES
    return info


def session_status() -> dict[str, Any]:
    """Describe the stored session without revealing any token."""
    from pyhood.auth import DEFAULT_TOKEN_DIR, DEFAULT_TOKEN_FILE

    path = DEFAULT_TOKEN_DIR / DEFAULT_TOKEN_FILE
    mode = _file_mode(path)
    info: dict[str, Any] = {
        "path": path,
        "exists": path.is_file(),
        "mode": mode,
        "owner_only": _owner_only(mode),
        "has_refresh_token": False,
        "age_hours": None,
    }
    if not info["exists"]:
        return info

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return info

    info["has_refresh_token"] = bool(data.get("refresh_token"))
    saved_at = data.get("saved_at")
    if isinstance(saved_at, (int, float)):
        info["age_hours"] = round((time.time() - saved_at) / 3600, 1)
    return info


def _permissions_note(info: dict[str, Any]) -> str:
    """A warning line when a credential file is readable by others."""
    if not info["exists"] or info["owner_only"]:
        return ""
    return (
        f"    ! mode {info['mode']:04o} — readable by other users on this "
        f"machine. Run: chmod 600 {info['path']}"
    )


def print_status(out: Printer = print) -> int:
    """Report what is configured. Reads nothing over the network.

    Returns:
        0 if both credential kinds are usable, 1 otherwise.
    """
    session = session_status()
    crypto = crypto_status()

    out("Session (main API — stocks, options, futures)")
    if session["exists"]:
        age = session["age_hours"]
        age_text = f", saved {age}h ago" if age is not None else ""
        refresh = "refreshable" if session["has_refresh_token"] else "no refresh token"
        out(f"    {session['path']} ({refresh}{age_text})")
        note = _permissions_note(session)
        if note:
            out(note)
    else:
        out(f"    not configured — run: {invocation()} authorize")

    out("")
    out("Crypto API (official Crypto Trading API)")
    if crypto["source"] == "none":
        out(f"    not configured — run: {invocation()} setup crypto")
    else:
        out(f"    source: {crypto['source']}")
        if crypto["source"] == "file":
            out(f"    {crypto['path']}")
            note = _permissions_note(crypto)
            if note:
                out(note)
        out(f"    api key: {crypto['api_key_chars']} chars")
        if crypto["private_key_valid"]:
            out(f"    private key: valid Ed25519, {crypto['private_key_bytes']} bytes")
        elif crypto["private_key_bytes"] is not None:
            out(
                f"    ! private key: {crypto['private_key_bytes']} bytes — expected "
                f"{' or '.join(str(n) for n in ED25519_KEY_SIZES)}. This is not a real key."
            )
        else:
            out("    ! private key: not valid base64. This is a placeholder, not a real key.")

    if crypto["source"] == "environment" and crypto["path"].is_file():
        out("")
        out(
            f"    Note: {API_KEY_VAR}/{PRIVATE_KEY_VAR} are set in the environment, "
            f"so {crypto['path']} is being ignored."
        )

    out("")
    out("Confirmation (whether an order asks before it is placed)")
    out(f"    {confirmation_summary()}")

    usable = session["exists"] and crypto["source"] != "none" and crypto["private_key_valid"]
    return 0 if usable else 1


# ── Confirmation setting ─────────────────────────────────────────────


def confirmation_summary() -> str:
    """The confirmation setting in one line."""
    from pyhood import settings

    chosen = settings.load()
    if chosen.confirmation:
        return "on: every order asks first."
    return f"off: orders are placed at once, except those above ${chosen.above:,.2f}."


def setup_confirmation(
    values: list[str],
    prompt: Prompt = input,
    out: Printer = print,
    at_terminal: Callable[[], bool] | None = None,
) -> int:
    """Show or change whether orders ask before they are placed.

    Showing it, and turning confirmation on, work anywhere. Turning it off,
    or changing the amount above which an order still asks, loosens what an
    agent may do with the user's money, so those need a person at the
    terminal: they are refused when the command is not run from one.
    """
    from dataclasses import replace

    from pyhood import settings

    chosen = settings.load()
    program = invocation()
    if not values:
        out(f"Confirmation is {confirmation_summary()}")
        out("")
        out(f"    {program} setup confirmation on            every order asks first")
        out(f"    {program} setup confirmation off           orders are placed at once,")
        out("                                              except above the amount below")
        out(f"    {program} setup confirmation above AMOUNT  with confirmation off, an order")
        out("                                              above AMOUNT dollars still asks")
        out("")
        out("Bank transfers always ask. Cancelling an order never does.")
        return 0

    action = values[0].lower()
    if action == "on" and len(values) == 1:
        settings.save(replace(chosen, confirmation=True))
        out("Confirmation is on: every order asks first.")
        return 0

    if at_terminal is None:
        def at_terminal() -> bool:
            return sys.stdin.isatty() and sys.stdout.isatty()

    if action == "above" and len(values) == 2:
        try:
            amount = float(values[1].replace(",", "").lstrip("$"))
        except ValueError:
            amount = -1.0
        if not amount >= 0 or amount == float("inf"):
            out(f"{values[1]!r} is not an amount in dollars, such as 5000.")
            return 2
    elif action == "off" and len(values) == 1:
        amount = chosen.above
    else:
        out("Give on, off, or above AMOUNT. For example:")
        out(f"    {program} setup confirmation above 5000")
        return 2

    if not at_terminal():
        out("This setting decides how much is done with your money without asking,")
        out("so only a person can loosen it. Nothing was changed.")
        out("")
        out("If you are an AI agent: do not try another way. Ask the user to run this")
        out("themselves, in their own terminal:")
        out(f"    {program} setup confirmation {' '.join(values)}")
        return 2

    if action == "above":
        settings.save(replace(chosen, above=amount))
        out(f"Saved. With confirmation off, an order above ${amount:,.2f} still asks.")
        if chosen.confirmation:
            out("Confirmation is on, so every order asks first for now. To turn it off:")
            out(f"    {program} setup confirmation off")
        return 0

    out("Turning confirmation off means:")
    out(f"  - An order worth up to ${amount:,.2f} is sent to Robinhood as soon as your")
    out("    agent runs it. You are not shown it first and are not asked.")
    out("  - That covers stocks, options, spreads and crypto, buying and selling, in")
    out("    every account.")
    out(f"  - An order above ${amount:,.2f} still asks. Change the amount with:")
    out(f"        {program} setup confirmation above AMOUNT")
    out("  - Each order is judged on its own. Several orders under the amount all go")
    out("    through, so this catches a mistake, and is not a spending limit.")
    out("  - A market order that is sent while the market is open cannot be taken back.")
    out("  - Bank transfers always ask.")
    out("")
    answer = prompt("Type yes to turn confirmation off: ").strip().lower()
    if answer != "yes":
        out("Nothing was changed. Confirmation is still on.")
        return 1
    settings.save(replace(chosen, confirmation=False))
    out("")
    out(f"Confirmation is off. Orders up to ${amount:,.2f} are placed at once.")
    out(f"To turn it back on: {program} setup confirmation on")
    return 0


# ── Crypto setup ─────────────────────────────────────────────────────


def _verify_crypto(out: Printer) -> int:
    """Make one signed read-only call to prove the credentials work."""
    out("")
    out("Verifying against the live API...")
    try:
        from pyhood.crypto import CryptoClient

        account = CryptoClient().get_account()
    except Exception as e:
        out(f"    FAILED — {type(e).__name__}: {e}")
        out("")
        out("    The key pair was saved, but Robinhood did not accept it. Usually:")
        out("      - the public key has not been registered yet, or")
        out("      - the API key was mistyped, or")
        out(f"      - stale {API_KEY_VAR}/{PRIVATE_KEY_VAR} exports are shadowing the file.")
        return 1
    out(f"    OK — authenticated. Account status: {account.status}, fee tier: {account.fee_tier}.")
    return 0


def setup_crypto(
    force: bool = False,
    verify: bool = True,
    secret_prompt: Prompt = getpass.getpass,
    out: Printer = print,
) -> int:
    """Generate a Crypto API key pair and store it.

    The private key is generated on this machine and written directly to the
    credentials file — it is never displayed. Only the public key is shown,
    which is the half Robinhood needs.

    Args:
        force: Replace an existing credentials file. Without this, an existing
            file is left alone, since overwriting it would revoke working keys.
        verify: Make one signed read-only call afterwards to confirm the pair
            is accepted.
        secret_prompt: Reads the API key. Injected for testing.
        out: Receives progress output. Injected for testing.

    Returns:
        Process exit code — 0 on success.
    """
    from pyhood.crypto.auth import generate_keypair

    path = credentials_path()
    if path.is_file() and not force:
        out(f"{path} already exists.")
        out("Re-run with --force to replace it. Your existing keys keep working until you do.")
        return 1

    if credentials_source() == "environment":
        out(
            f"Note: {API_KEY_VAR} and {PRIVATE_KEY_VAR} are set in your environment. "
            f"They take precedence over the file this writes, so unset them "
            f"afterwards or the new key pair will be ignored."
        )
        out("")

    out("Step 1 — generating an Ed25519 key pair on this machine.")
    out("")
    private_key, public_key = generate_keypair()

    out("Step 2 — register this PUBLIC key with Robinhood:")
    out(f"    {KEY_MANAGEMENT_URL}  ->  API Trading  ->  Add key")
    out("")
    out(f"    {public_key}")
    out("")
    out("Robinhood will then show you an API key. Copy it.")
    out("")

    try:
        prompt_text = "Step 3 — paste the API key Robinhood issued (hidden): "
        api_key = _ask(secret_prompt, prompt_text).strip()
    except CancelledError:
        out("")
        out("Cancelled — no credentials were saved.")
        return 1
    if not api_key:
        out("Nothing entered — no credentials were saved.")
        return 1

    write_private(path, f"{API_KEY_VAR}={api_key}\n{PRIVATE_KEY_VAR}={private_key}\n")
    out("")
    out(f"Saved to {path}, readable only by you.")
    out("The private key went straight from generation to disk and was never displayed.")

    if verify:
        return _verify_crypto(out)
    return 0


# ── Login setup ──────────────────────────────────────────────────────


def _has_terminal() -> bool:
    """True when a person can type an answer."""
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


IN_WINDOW_VARIABLE = "PYHOOD_AUTHORIZATION_WINDOW"
"""Set by the window `pyhood authorize --window` opens, so that the text
can tell the user what to do with the window."""

TITLE = "pyhood Authorization"


def setup_login(
    prompt: Prompt = input,
    secret_prompt: Prompt = getpass.getpass,
    out: Printer = print,
) -> int:
    """Authorize pyhood to use the user's Robinhood account.

    The user logs in, Robinhood hands back tokens, and the tokens are saved.
    A saved authorization that still works, or that can be renewed, needs no
    password at all, so that is tried first.

    Args:
        prompt: Reads the username and any code. Injected for testing.
        secret_prompt: Reads the password. Injected for testing.
        out: Receives progress output. Injected for testing.

    Returns:
        Process exit code: 0 on success.
    """
    from pyhood import login
    from pyhood.exceptions import (
        AuthError,
        DeviceApprovalRequiredError,
        LoginTimeoutError,
        MFARequiredError,
    )

    in_window = os.environ.get(IN_WINDOW_VARIABLE) == "1"
    close = " You can close this window." if in_window else ""
    again = " Close this window and try again." if in_window else " Run this again to retry."

    out(TITLE)
    out("")

    expired = False
    if session_status()["exists"]:
        try:
            login()
        except Exception:
            expired = True
        else:
            out(f"pyhood is already authorized. There is nothing to do.{close}")
            return 0

    if prompt is input and not _has_terminal():
        # Run by an AI agent, or from a script: nobody can type here.
        out("There is no terminal here to type a password into.")
        out("An AI agent can open an authorization window on the user's screen with:")
        out(f"    {invocation()} authorize --window")
        out("Otherwise, run this in a terminal of your own.")
        return 1

    if expired:
        out("The saved authorization no longer works, so it has to be made again.")
        out("")
    out("pyhood needs you to log in and authorize the connection between pyhood")
    out("and Robinhood. pyhood sends your password to Robinhood and does not save")
    out("it. Do not share your password with your agent or anyone else.")
    out("")
    out("Once authorized, you will not be asked for your username and password")
    out("again. To remove this authorization, open the Robinhood app and go to")
    out("Account > Menu > Security and privacy > Devices, then remove the device.")
    out("")

    try:
        username = _ask(prompt, "Robinhood email or username: ").strip()
        if not username:
            out(f"Nothing was entered, so nothing was sent.{again}")
            return 1
        password = _ask(secret_prompt, "Password (nothing shows as you type): ")
        if not password:
            out(f"Nothing was entered, so nothing was sent.{again}")
            return 1
    except CancelledError:
        out("")
        out(f"Cancelled. Nothing was saved.{close}")
        return 1

    out("")
    out('Now open the Robinhood app on your phone and tap "Yes, it\'s me".')
    out("Waiting for you...")
    try:
        try:
            login(username, password)
        except MFARequiredError:
            code = _ask(prompt, "Robinhood sent you a code. Enter it here: ").strip()
            login(username, password, mfa_code=code)
    except CancelledError:
        out("")
        out(f"Cancelled. Nothing was saved.{close}")
        return 1
    except (LoginTimeoutError, DeviceApprovalRequiredError):
        out("")
        out("Robinhood did not get an approval from your phone in time.")
        out(f"Nothing was saved.{again}")
        return 1
    except AuthError as e:
        out("")
        out("Robinhood did not accept the login.")
        out(f"    {e}")
        out(f"Nothing was saved.{again}")
        return 1

    out("")
    out(f"Authorized.{close}")
    return 0


def invocation() -> str:
    """How pyhood was invoked, for help text and hints.

    Installed as a console script this is ``pyhood``; run as a module it is
    ``python -m pyhood``. Messages that suggest a command should match what
    the reader actually typed.
    """
    try:
        name = Path(sys.argv[0]).name
    except (IndexError, TypeError):  # pragma: no cover - defensive
        return "python -m pyhood"
    return "pyhood" if name == "pyhood" else "python -m pyhood"


def _add_window_options(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--window",
        action="store_true",
        help=(
            "open a terminal window on the user's screen for them to log in, and "
            "wait. For an AI agent, which has no terminal to type in"
        ),
    )
    command.add_argument(
        "--wait", type=float, default=None, metavar="SECONDS",
        help=(
            "with --window: how long to wait for the user before handing back "
            "(default 90). Run the command again to keep waiting"
        ),
    )


def _authorize(parser: argparse.ArgumentParser, args: argparse.Namespace) -> int:
    """Run `pyhood authorize`, or its older name `pyhood setup login`."""
    if args.window:
        from pyhood import login_window

        return login_window.login_in_window(
            wait=login_window.DEFAULT_WAIT if args.wait is None else args.wait,
            program=invocation(),
        )
    if args.wait is not None:
        parser.error("--wait goes with --window")
    return setup_login()


def build_parser() -> argparse.ArgumentParser:
    """The command-line parser for `pyhood` / `python -m pyhood`."""
    parser = argparse.ArgumentParser(
        prog=invocation(),
        description=(
            "pyhood, a Python client for Robinhood. Set up a login, check it "
            "works, and run scripts that use it. AI agents: start with "
            "`pyhood guide`."
        ),
    )
    from pyhood import __version__

    parser.add_argument("--version", action="version", version=f"pyhood {__version__}")

    commands = parser.add_subparsers(dest="command")
    commands.add_parser("version", help="print the installed pyhood version")
    authorize = commands.add_parser(
        "authorize",
        help="log in to Robinhood, so that pyhood may use the account",
        description=(
            "Authorizes pyhood to use your Robinhood account. You log in, "
            "Robinhood hands pyhood a key, and pyhood saves the key so that you "
            "are not asked again. Your password is sent to Robinhood and is not "
            "saved. An AI agent has no terminal to type in, so it adds --window."
        ),
    )
    _add_window_options(authorize)
    setup = commands.add_parser(
        "setup",
        help="configure credentials, or report what is configured",
        description=(
            "With no target, reports what is configured. Secrets are always "
            "read interactively — there are no options for passing them, "
            "because command-line arguments are visible to other processes."
        ),
    )
    setup.add_argument(
        "target",
        nargs="?",
        choices=("crypto", "login", "confirmation"),
        help=(
            "crypto: generate a Crypto API key pair. login: the same as "
            "`pyhood authorize`. "
            "confirmation: show or change whether orders ask before they are placed"
        ),
    )
    setup.add_argument(
        "values", nargs="*", metavar="VALUE",
        help=(
            "for confirmation: on, off, or above AMOUNT. With confirmation off, an "
            "order worth more than AMOUNT dollars still asks"
        ),
    )
    setup.add_argument(
        "--force",
        action="store_true",
        help="replace existing crypto credentials instead of leaving them alone",
    )
    setup.add_argument(
        "--no-verify",
        action="store_true",
        help="skip the signed read-only call that confirms new crypto keys work",
    )
    _add_window_options(setup)
    verify = commands.add_parser(
        "verify",
        help="read live data to confirm a saved login works (read-only)",
        description=(
            "Reads live market data to confirm a saved login works. Places "
            "no orders and changes nothing."
        ),
    )
    verify.add_argument(
        "target",
        nargs="?",
        choices=("stocks", "crypto"),
        default="stocks",
        help="stocks (default): the main session. crypto: the Crypto API key pair.",
    )
    as_json = argparse.ArgumentParser(add_help=False)
    as_json.add_argument(
        "--json", action="store_true",
        help="print exact values as JSON instead of a table",
    )
    in_account = argparse.ArgumentParser(add_help=False)
    in_account.add_argument(
        "--account", metavar="WHICH",
        help=(
            "which account: part of its type, such as roth, ira or individual, or the "
            "last four characters of its number. See `pyhood accounts`. "
            "Default: the first account"
        ),
    )
    commands.add_parser(
        "accounts",
        parents=[as_json],
        help="show your accounts and what each is worth (read-only)",
        description=(
            "Lists the accounts under this login, such as an individual account and an "
            "IRA, with value, cash and buying power. Account numbers are shown by their "
            "last four characters; --json gives them in full."
        ),
    )
    positions = commands.add_parser(
        "positions",
        parents=[as_json],
        help="show the stocks and options you hold, in each account (read-only)",
        description=(
            "Shows open stock and option positions with cost and unrealized profit, "
            "for every account under this login, such as an individual account and "
            "an IRA."
        ),
    )
    positions.add_argument(
        "--account", metavar="WHICH",
        help="only this account's positions: part of its type, such as roth, or "
             "the last four characters of its number",
    )
    orders = commands.add_parser(
        "orders",
        parents=[as_json],
        help="show recent stock and option orders (read-only)",
        description=(
            "Shows stock and option orders in every account, newest first, with "
            "what was ordered and what actually filled. Covers the last 30 days "
            "unless told otherwise. Times are shown in this computer's time zone."
        ),
    )
    orders.add_argument(
        "--account", metavar="WHICH",
        help="only this account's orders: part of its type, such as roth, or the "
             "last four characters of its number",
    )
    orders.add_argument(
        "--since", type=_date, metavar="YYYY-MM-DD",
        help="show orders placed on or after this date",
    )
    orders.add_argument("--all", action="store_true", help="show every order on record")
    orders.add_argument("--symbol", help="show orders for one symbol only")
    orders.add_argument(
        "--open", action="store_true",
        help="show only orders that can still fill, which are the ones that can be cancelled",
    )
    two_steps = (
        " Takes two steps, unless the user has turned confirmation off. Run "
        "without --confirm it sends nothing: it shows the order and prints a "
        "confirmation code. Show the user what it printed and ask; on a yes, run "
        "it again with --confirm and that code. If the user has turned "
        "confirmation off, an order up to the amount they set is sent on the "
        "first run. `pyhood setup confirmation` shows the setting."
    )
    always_two_steps = (
        " Always takes two steps, whatever the confirmation setting. Run without "
        "--confirm it sends nothing: it shows the transfer and prints a "
        "confirmation code. Show the user what it printed and ask; on a yes, run "
        "it again with --confirm and that code."
    )
    ask_help = (
        "ask before placing this order, even if the user has turned confirmation off"
    )
    for side in ("buy", "sell"):
        order = commands.add_parser(
            side,
            parents=[in_account],
            help=f"{side} a stock; asks first unless confirmation is off",
            description=f"Places an order to {side} a stock." + two_steps,
        )
        order.add_argument("symbol", metavar="SYMBOL", help="the stock's ticker")
        order.add_argument(
            "quantity", type=_positive, nargs="?", metavar="QUANTITY",
            help="number of shares; leave out when using --dollars",
        )
        order.add_argument(
            "--dollars", type=_positive, metavar="AMOUNT",
            help=(
                f"{side} this many dollars' worth in place of a number of shares; "
                "a market order, usually for a fraction of a share"
            ),
        )
        price = order.add_mutually_exclusive_group(required=True)
        price.add_argument(
            "--limit", type=_positive, metavar="PRICE",
            help=f"{side} at this price or better",
        )
        price.add_argument(
            "--market", action="store_true",
            help=f"{side} at the best price available, whatever it is",
        )
        order.add_argument(
            "--stop", type=_positive, metavar="PRICE",
            help=(
                "make it a stop order: wait until the price reaches this, then "
                "place the --market or --limit order"
            ),
        )
        order.add_argument(
            "--trail-percent", type=_positive, metavar="PERCENT",
            help=(
                "make it a trailing stop that follows the price this many percent "
                "behind; needs --market"
            ),
        )
        order.add_argument(
            "--trail-amount", type=_positive, metavar="DOLLARS",
            help="the same, with the trail as a dollar amount",
        )
        order.add_argument(
            "--tif", choices=("gfd", "gtc"), default="gfd",
            help="gfd (default): good for day. gtc: good till cancelled",
        )
        order.add_argument(
            "--extended-hours", action="store_true",
            help="allow the order to trade outside regular hours",
        )
        order.add_argument(
            "--confirm", metavar="CODE",
            help="the code the first step printed for this exact order; places the order",
        )
        order.add_argument("--ask", action="store_true", help=ask_help)
    chain = commands.add_parser(
        "options",
        parents=[as_json],
        help="show a stock's option expirations, or the contracts for one (read-only)",
        description=(
            "With only a symbol, lists the expiration dates. With --expires, shows "
            "the contracts for that date nearest the stock's price: bid, ask, mark, "
            "delta and implied volatility. Prices are per share."
        ),
    )
    chain.add_argument("symbol", metavar="SYMBOL", help="the underlying stock's ticker")
    chain.add_argument("--expires", type=_date, metavar="YYYY-MM-DD", help="an expiration date")
    kind = chain.add_mutually_exclusive_group()
    kind.add_argument("--call", dest="option_type", action="store_const", const="call",
                      help="show calls only")
    kind.add_argument("--put", dest="option_type", action="store_const", const="put",
                      help="show puts only")
    chain.add_argument(
        "--strikes", type=_count, default=10, metavar="N",
        help="how many strikes nearest the price to show (default 10)",
    )
    for side in ("buy", "sell"):
        usual = "open" if side == "buy" else "close"
        option = commands.add_parser(
            f"{side}-option",
            parents=[in_account],
            help=f"{side} option contracts; asks first unless confirmation is off",
            description=(
                f"Places a limit order to {side} contracts of one option." + two_steps
                + " Find contracts with `pyhood options SYMBOL --expires DATE`."
            ),
        )
        option.add_argument("symbol", metavar="SYMBOL", help="the underlying stock's ticker")
        option.add_argument(
            "--expires", type=_date, required=True, metavar="YYYY-MM-DD",
            help="the contract's expiration date",
        )
        option.add_argument(
            "--strike", type=_positive, required=True, metavar="PRICE",
            help="the contract's strike price",
        )
        kind = option.add_mutually_exclusive_group(required=True)
        kind.add_argument("--call", dest="option_type", action="store_const", const="call",
                          help="a call")
        kind.add_argument("--put", dest="option_type", action="store_const", const="put",
                          help="a put")
        option.add_argument(
            "--contracts", type=_count, required=True, metavar="N",
            help="how many contracts; each is 100 shares",
        )
        option.add_argument(
            "--limit", type=_positive, required=True, metavar="PRICE",
            help="the most to pay or least to accept, per share: 2.50 is $250 a contract",
        )
        option.add_argument(
            "--to", dest="effect", choices=("open", "close"),
            help=f"open a position or close one (default: {usual})",
        )
        option.add_argument(
            "--tif", choices=("gfd", "gtc"), default="gfd",
            help="gfd (default): good for day. gtc: good till cancelled",
        )
        option.add_argument(
            "--confirm", metavar="CODE",
            help="the code the first step printed for this exact order; places the order",
        )
        option.add_argument("--ask", action="store_true", help=ask_help)
    earnings = commands.add_parser(
        "earnings", parents=[as_json],
        help="show when companies next report earnings (read-only)",
        description="Shows each symbol's next earnings date, with the estimate.",
    )
    earnings.add_argument("symbols", nargs="+", metavar="SYMBOL")
    earnings.add_argument(
        "--days", type=_count, default=90, metavar="N",
        help="how far ahead to look (default 90)",
    )
    ratings = commands.add_parser(
        "ratings", parents=[as_json],
        help="show analyst ratings and price targets (read-only)",
        description="Shows analysts' buy, hold and sell counts and their price targets.",
    )
    ratings.add_argument("symbols", nargs="+", metavar="SYMBOL")
    news = commands.add_parser(
        "news", parents=[as_json],
        help="show recent headlines for a stock (read-only)",
        description="Shows recent headlines for a symbol, newest first, with links.",
    )
    news.add_argument("symbol", metavar="SYMBOL")
    news.add_argument(
        "--count", type=_count, default=5, metavar="N", help="how many headlines (default 5)",
    )
    movers = commands.add_parser(
        "movers", parents=[as_json],
        help="show the S&P 500's biggest moves today (read-only)",
        description="Shows the S&P 500 stocks that have risen most today, or fallen most.",
    )
    movers.add_argument("--down", action="store_true", help="show the biggest falls")
    history = commands.add_parser(
        "history", parents=[as_json],
        help="show a stock's past prices (read-only)",
        description=(
            "Shows open, high, low, close and volume: one row a day for a week, a "
            "month or three months, one a week for a year or five."
        ),
    )
    history.add_argument("symbol", metavar="SYMBOL")
    history.add_argument(
        "--span", choices=("week", "month", "3month", "year", "5year"), default="month",
        help="how far back (default month)",
    )
    dividends = commands.add_parser(
        "dividends", parents=[as_json],
        help="show dividends paid and pending (read-only)",
        description="Shows dividends, newest first, and the total paid.",
    )
    dividends.add_argument("--symbol", help="show dividends for one symbol only")
    commands.add_parser(
        "transfers", parents=[as_json],
        help="show money moved in, out and between accounts (read-only)",
        description="Shows transfers, newest first. It cannot make one.",
    )
    commands.add_parser(
        "watchlists", parents=[as_json],
        help="show your watchlists (read-only)",
        description="Shows the lists you created and the Robinhood lists you follow.",
    )
    for name, verb in (("watch", "Adds stocks to"), ("unwatch", "Takes stocks off")):
        change = commands.add_parser(
            name,
            help=f"{verb.lower()} a watchlist",
            description=f"{verb} a watchlist, at once. No money is involved.",
        )
        change.add_argument("symbols", nargs="+", metavar="SYMBOL")
        change.add_argument(
            "--list", dest="list_name", default="My First List", metavar="NAME",
            help="which watchlist (default: 'My First List')",
        )
    spread = commands.add_parser(
        "spread",
        parents=[in_account],
        help="trade an option spread; asks first unless confirmation is off",
        description=(
            "Places two to four option contracts as one order, for one net price."
            + two_steps
        ),
    )
    spread.add_argument("symbol", metavar="SYMBOL", help="the underlying stock's ticker")
    spread.add_argument(
        "--expires", type=_date, required=True, metavar="YYYY-MM-DD",
        help="the expiration of every leg that does not name its own",
    )
    spread.add_argument(
        "--leg", dest="legs", type=_spread_leg, action="append", required=True,
        metavar="SIDE:TYPE:STRIKE",
        help=(
            "one contract of the spread, as in buy:call:350 or sell:put:340. Give it "
            "two to four times. Add :YYYY-MM-DD for a leg with its own expiration"
        ),
    )
    spread.add_argument(
        "--contracts", type=_count, required=True, metavar="N", help="how many spreads",
    )
    net = spread.add_mutually_exclusive_group(required=True)
    net.add_argument(
        "--debit", type=_positive, metavar="PRICE",
        help="the most to pay for the spread, per share: 2.50 is $250 a spread",
    )
    net.add_argument(
        "--credit", type=_positive, metavar="PRICE",
        help="the least to accept for the spread, per share",
    )
    spread.add_argument(
        "--to", dest="effect", choices=("open", "close"), default="open",
        help="open a position (default) or close one",
    )
    spread.add_argument(
        "--tif", choices=("gfd", "gtc"), default="gfd",
        help="gfd (default): good for day. gtc: good till cancelled",
    )
    spread.add_argument(
        "--confirm", metavar="CODE",
        help="the code the first step printed for this exact spread; places the order",
    )
    spread.add_argument("--ask", action="store_true", help=ask_help)

    documents = commands.add_parser(
        "documents", parents=[as_json],
        help="list statements, trade confirmations and tax forms (read-only)",
        description="Lists account documents, newest first, with the ID that saves each.",
    )
    documents.add_argument(
        "--type", dest="kind", metavar="TYPE",
        help="only this kind: statement, confirm, 1099, 5498, or any part of a type's name",
    )
    documents.add_argument(
        "--year", type=_count, metavar="YYYY", help="only documents dated in this year",
    )
    document = commands.add_parser(
        "document",
        help="save one document as a PDF",
        description=(
            "Downloads one document as a PDF into a folder that only you can read. "
            "Nothing in your account changes."
        ),
    )
    document.add_argument("document_id", metavar="DOCUMENT_ID", help="from `pyhood documents`")
    document.add_argument(
        "--to", default="documents", metavar="FOLDER",
        help="where to save it (default: a `documents` folder here)",
    )
    commands.add_parser(
        "banks", parents=[as_json],
        help="show the bank accounts linked to Robinhood (read-only)",
        description="Shows linked bank accounts by nickname, type and last four digits.",
    )
    for direction, sense in (
        ("deposit", "from your bank into Robinhood"),
        ("withdraw", "from Robinhood to your bank"),
    ):
        move = commands.add_parser(
            direction,
            help=f"move money {sense}; always asks first",
            description=f"Moves money {sense}." + always_two_steps,
        )
        move.add_argument("amount", type=_positive, metavar="AMOUNT", help="dollars")
        move.add_argument(
            "--bank", metavar="WHICH",
            help=(
                "which linked bank: part of its nickname or type, or its last four "
                "digits. Needed only if more than one is linked. See `pyhood banks`"
            ),
        )
        move.add_argument(
            "--confirm", metavar="CODE",
            help="the code the first step printed for this exact transfer; makes the transfer",
        )
    cancel_transfer = commands.add_parser(
        "cancel-transfer",
        help="cancel a bank transfer that has not gone through yet",
        description="Cancels a pending deposit or withdrawal, at once.",
    )
    cancel_transfer.add_argument(
        "transfer_id", metavar="TRANSFER_ID", help="printed when the transfer was made",
    )

    crypto = commands.add_parser(
        "crypto",
        help="crypto prices, holdings and orders, through Robinhood's Crypto API",
        description=(
            "Crypto, through Robinhood's official Crypto Trading API. It has its own "
            "credentials: set them up with `pyhood setup crypto`. Symbols may be "
            "written BTC or BTC-USD."
        ),
    )
    crypto_commands = crypto.add_subparsers(dest="crypto_command", required=True)
    crypto_quote = crypto_commands.add_parser(
        "quote", parents=[as_json], help="best bid and ask for coins (read-only)",
    )
    crypto_quote.add_argument("symbols", nargs="+", metavar="SYMBOL")
    crypto_commands.add_parser(
        "holdings", parents=[as_json],
        help="the coins you hold and your crypto buying power (read-only)",
    )
    crypto_orders = crypto_commands.add_parser(
        "orders", parents=[as_json], help="crypto orders, newest first (read-only)",
    )
    crypto_orders.add_argument(
        "--open", action="store_true", help="show only orders that can still fill",
    )
    for side in ("buy", "sell"):
        trade = crypto_commands.add_parser(
            side,
            help=f"{side} a coin; asks first unless confirmation is off",
            description=f"Places an order to {side} a coin." + two_steps,
        )
        trade.add_argument("symbol", metavar="SYMBOL", help="the coin, such as BTC")
        trade.add_argument(
            "quantity", type=_positive, metavar="QUANTITY",
            help="how much of the coin, not dollars: 0.001 is a thousandth of a bitcoin",
        )
        price = trade.add_mutually_exclusive_group(required=True)
        price.add_argument(
            "--limit", type=_positive, metavar="PRICE",
            help=f"{side} at this price per coin or better",
        )
        price.add_argument(
            "--market", action="store_true",
            help=f"{side} at the best price available, whatever it is",
        )
        trade.add_argument(
            "--confirm", metavar="CODE",
            help="the code the first step printed for this exact order; places the order",
        )
        trade.add_argument("--ask", action="store_true", help=ask_help)
    crypto_cancel = crypto_commands.add_parser(
        "cancel", help="cancel an open crypto order, at once",
    )
    crypto_cancel.add_argument(
        "order_id", metavar="ORDER_ID", help="from `pyhood crypto orders --open`",
    )

    futures = commands.add_parser(
        "futures",
        help="futures quotes, contracts, orders, and an estimate for an order",
        description=(
            "Futures. Name a product, such as ES for the E-mini S&P 500, and the "
            "nearest contract is used. Or name a contract by product, month and "
            "year: ESZ26 is ES for December 2026. An order can be estimated with "
            "buy or sell, but not placed."
        ),
    )
    futures_commands = futures.add_subparsers(dest="futures_command", required=True)
    futures_quote = futures_commands.add_parser(
        "quote", parents=[as_json], help="quotes for futures contracts",
    )
    futures_quote.add_argument("symbols", nargs="+", metavar="PRODUCT_OR_CONTRACT")
    futures_contract = futures_commands.add_parser(
        "contract", parents=[as_json],
        help="a contract's size, tick and expiration, or a product's contracts",
    )
    futures_contract.add_argument("symbol", metavar="PRODUCT_OR_CONTRACT")
    for side in ("buy", "sell"):
        futures_order = futures_commands.add_parser(
            side, parents=[as_json],
            help=f"estimate a futures order to {side}: margin, fees and Robinhood's verdict",
            description=(
                f"Estimates an order to {side} futures. It shows the margin the order "
                "ties up, the fees, and whether Robinhood would accept it, all as "
                "Robinhood reports them. It cannot place the order, and there is no "
                "--confirm: use the Robinhood app or Robinhood Legend for that."
            ),
        )
        futures_order.add_argument("symbol", metavar="PRODUCT_OR_CONTRACT")
        futures_order.add_argument(
            "quantity", type=_count, metavar="CONTRACTS", help="how many contracts",
        )
        futures_price = futures_order.add_mutually_exclusive_group(required=True)
        futures_price.add_argument(
            "--limit", type=_positive, metavar="PRICE",
            help="the limit price, in the contract's points",
        )
        futures_price.add_argument(
            "--market", action="store_true", help="at the best price available",
        )
        futures_order.add_argument(
            "--stop", type=_positive, metavar="PRICE",
            help="wait until the price reaches this, then trade at market; needs --market",
        )
        futures_order.add_argument(
            "--tif", choices=("gfd", "gtc"), default="gfd",
            help="gfd: good for day (the default). gtc: good till cancelled",
        )
    futures_commands.add_parser(
        "orders", parents=[as_json], help="futures orders, with realized profit and loss",
    )
    futures_commands.add_parser(
        "positions", parents=[as_json], help="open futures positions, as Robinhood sends them",
    )
    cancel = commands.add_parser(
        "cancel",
        help="cancel an open order",
        description=(
            "Cancels an order that has not finished filling, at once, and "
            "reports what became of it. Find order IDs with `pyhood orders --open`."
        ),
    )
    cancel.add_argument("order_id", metavar="ORDER_ID", help="from `pyhood orders --open`")
    buying_power = commands.add_parser(
        "buying-power",
        parents=[as_json],
        help="show the cash available to trade with, in each account (read-only)",
        description=(
            "Shows the buying power of every account under this login, such as an "
            "individual account and an IRA. An account spends only its own cash, "
            "so the figures are not added up."
        ),
    )
    buying_power.add_argument(
        "--account", metavar="WHICH",
        help="only this account's buying power: part of its type, such as roth, or "
             "the last four characters of its number",
    )
    quote = commands.add_parser(
        "quote",
        parents=[as_json],
        help="show current prices for one or more stocks (read-only)",
        description="Shows price, change, bid and ask for each symbol.",
    )
    quote.add_argument("symbols", nargs="+", metavar="SYMBOL", help="one or more tickers")
    quote.add_argument(
        "--fundamentals", action="store_true",
        help="add volume, P/E, market cap and the 52-week range (one more request)",
    )
    guide = commands.add_parser(
        "guide",
        help="print how to use pyhood, written for an AI agent",
        description=(
            "Prints the commands an agent uses and the rules for orders, for the "
            "installed version. `pyhood guide python` prints the reference for "
            "writing a script: methods, and the fields of what they return."
        ),
    )
    guide.add_argument(
        "topic", nargs="?", choices=("python",),
        help="python: the reference for writing a script",
    )
    run = commands.add_parser(
        "run",
        help="run a Python script with the Python pyhood is installed in",
        description=(
            "Runs Python with the interpreter pyhood is installed in, so "
            "`import pyhood` works however pyhood was installed. Everything "
            "after `run` is passed to Python unchanged."
        ),
        usage="pyhood run script.py [args ...]  |  pyhood run -c \"code\"",
    )
    run.add_argument("python_args", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    return parser


def _positive(value: str) -> float:
    """An argparse type: a number greater than zero."""
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a number") from None
    # `not number > 0` also refuses nan.
    if not number > 0 or number == float("inf"):
        raise argparse.ArgumentTypeError(f"{value!r} must be greater than zero")
    return number


def _spread_leg(value: str) -> dict:
    """An argparse type: one leg of a spread. Parsed in pyhood.cli_spreads."""
    from pyhood.cli_spreads import leg

    return leg(value)


def _count(value: str) -> int:
    """An argparse type: a whole number greater than zero."""
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a whole number") from None
    if number < 1:
        raise argparse.ArgumentTypeError(f"{value!r} must be at least 1")
    return number


def _date(value: str) -> str:
    """An argparse type: a YYYY-MM-DD date, returned as given."""
    from datetime import datetime

    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a date in YYYY-MM-DD form, such as 2026-11-01"
        ) from None
    return value


def run_python(python_args: list[str]) -> int:
    """Run Python, the interpreter this package is installed in, with args.

    An isolated install (pipx, `uv tool install`) puts the `pyhood` command
    on the PATH but not a Python that can import pyhood. This is the one
    way to run a script that works for every kind of install.
    """
    import subprocess

    if not python_args:
        print("usage: pyhood run script.py [args ...]  |  pyhood run -c \"code\"")
        return 2
    # The arguments are the user's own command line, passed straight to the
    # same Python that is running this, without a shell.
    return subprocess.call([sys.executable, *python_args])  # nosec B603


def main(argv: list[str] | None = None) -> int:
    """Entry point for `pyhood` and `python -m pyhood`."""
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    # `run` hands everything after it to Python untouched, including options
    # such as -c and -m that argparse would otherwise claim as its own.
    if argv[:1] == ["run"]:
        return run_python(argv[1:])
    args = parser.parse_args(argv)

    if args.command == "version":
        from pyhood import __version__

        print(f"pyhood {__version__}")
        return 0
    if args.command == "guide":
        from pyhood import guide

        return guide.main(args.topic)
    simple = {
        "accounts": lambda a: {},
        "earnings": lambda a: {"symbols": a.symbols, "days": a.days},
        "ratings": lambda a: {"symbols": a.symbols},
        "news": lambda a: {"symbol": a.symbol, "count": a.count},
        "movers": lambda a: {"down": a.down},
        "history": lambda a: {"symbol": a.symbol, "span": a.span},
        "dividends": lambda a: {"symbol": a.symbol},
        "transfers": lambda a: {},
        "watchlists": lambda a: {},
    }
    if args.command in simple:
        from pyhood import cli

        return cli.run(
            getattr(cli, args.command), **simple[args.command](args),
            as_json_output=args.json,
        )
    if args.command == "spread":
        from pyhood import cli, cli_spreads

        return cli.run(
            cli.place_or_ask, order_command=cli_spreads.spread, ask=args.ask,
            symbol=args.symbol, expires=args.expires, legs=args.legs,
            contracts=args.contracts, debit=args.debit, credit=args.credit,
            effect=args.effect, time_in_force=args.tif, account=args.account,
            confirm=args.confirm,
        )
    if args.command in ("banks", "deposit", "withdraw", "cancel-transfer"):
        from pyhood import cli, cli_transfers

        if args.command == "banks":
            return cli.run(cli_transfers.banks, as_json_output=args.json)
        if args.command == "cancel-transfer":
            return cli.run(cli_transfers.cancel_transfer, transfer_id=args.transfer_id)
        return cli.run(
            cli_transfers.transfer, direction=args.command, amount=args.amount,
            bank=args.bank, confirm=args.confirm,
        )
    if args.command == "crypto":
        from pyhood import cli_markets as markets

        which = args.crypto_command
        if which == "quote":
            return markets.run_crypto(
                markets.crypto_quote, symbols=args.symbols, as_json_output=args.json,
            )
        if which == "holdings":
            return markets.run_crypto(markets.crypto_holdings, as_json_output=args.json)
        if which == "orders":
            return markets.run_crypto(
                markets.crypto_orders, open_only=args.open, as_json_output=args.json,
            )
        if which == "cancel":
            return markets.run_crypto(markets.crypto_cancel, order_id=args.order_id)
        from pyhood import cli

        return markets.run_crypto(
            cli.place_or_ask, order_command=markets.crypto_order, ask=args.ask,
            side=which, symbol=args.symbol, quantity=args.quantity,
            limit=args.limit, confirm=args.confirm,
        )
    if args.command == "futures":
        from pyhood import cli
        from pyhood import cli_markets as markets

        which = args.futures_command
        if which == "quote":
            return cli.run(
                markets.futures_quote, symbols=args.symbols, as_json_output=args.json,
            )
        if which == "contract":
            return cli.run(
                markets.futures_contract, symbol=args.symbol, as_json_output=args.json,
            )
        if which in ("buy", "sell"):
            return cli.run(
                markets.futures_order, side=which, symbol=args.symbol,
                quantity=args.quantity, limit=args.limit, stop=args.stop,
                time_in_force=args.tif, as_json_output=args.json,
            )
        if which == "orders":
            return cli.run(markets.futures_orders, as_json_output=args.json)
        return cli.run(markets.futures_positions, as_json_output=args.json)
    if args.command == "documents":
        from pyhood import cli

        return cli.run(
            cli.documents, kind=args.kind, year=args.year, as_json_output=args.json,
        )
    if args.command == "document":
        from pyhood import cli

        return cli.run(cli.document, document_id=args.document_id, to=args.to)
    if args.command in ("watch", "unwatch"):
        from pyhood import cli

        return cli.run(
            cli.watch, symbols=args.symbols, list_name=args.list_name,
            remove=args.command == "unwatch",
        )
    if args.command in ("buy-option", "sell-option"):
        from pyhood import cli

        return cli.run(
            cli.place_or_ask, order_command=cli.option_order, ask=args.ask,
            side=args.command.split("-")[0], symbol=args.symbol,
            expiration=args.expires, strike=args.strike, option_type=args.option_type,
            contracts=args.contracts, limit=args.limit, effect=args.effect,
            time_in_force=args.tif, account=args.account, confirm=args.confirm,
        )
    if args.command == "options":
        from pyhood import cli

        return cli.run(
            cli.options, symbol=args.symbol, expires=args.expires,
            option_type=args.option_type, strikes=args.strikes, as_json_output=args.json,
        )
    if args.command in ("buy", "sell", "cancel"):
        from pyhood import cli

        if args.command == "cancel":
            return cli.run(cli.cancel, order_id=args.order_id)
        return cli.run(
            cli.place_or_ask, order_command=cli.stock_order, ask=args.ask,
            side=args.command, symbol=args.symbol, quantity=args.quantity,
            limit=args.limit, stop=args.stop, time_in_force=args.tif,
            extended_hours=args.extended_hours, account=args.account, confirm=args.confirm,
            dollars=args.dollars, trail_percent=args.trail_percent,
            trail_amount=args.trail_amount,
        )
    if args.command in ("positions", "orders", "buying-power", "quote"):
        from pyhood import cli

        if args.command == "positions":
            return cli.run(cli.positions, account=args.account, as_json_output=args.json)
        if args.command == "orders":
            return cli.run(
                cli.orders, since=args.since, symbol=args.symbol,
                everything=args.all, open_only=args.open, as_json_output=args.json,
                account=args.account,
            )
        if args.command == "buying-power":
            return cli.run(cli.buying_power, account=args.account, as_json_output=args.json)
        return cli.run(
            cli.quote, symbols=args.symbols, fundamentals=args.fundamentals,
            as_json_output=args.json,
        )
    if args.command == "verify":
        from pyhood import verify

        return verify.verify_crypto() if args.target == "crypto" else verify.verify_stocks()
    if args.command == "authorize":
        return _authorize(parser, args)
    if args.command != "setup":
        parser.print_help()
        return 0
    if (args.window or args.wait is not None) and args.target != "login":
        parser.error("--window and --wait go with: authorize")
    if args.target == "crypto":
        return setup_crypto(force=args.force, verify=not args.no_verify)
    if args.target == "login":
        return _authorize(parser, args)
    if args.target == "confirmation":
        return setup_confirmation(args.values)
    if args.values:
        parser.error(f"unrecognized arguments: {' '.join(args.values)}")
    return print_status()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
