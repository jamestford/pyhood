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
    pyhood setup login     # obtain session tokens
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
        out(f"    not configured — run: {invocation()} setup login")

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

    usable = session["exists"] and crypto["source"] != "none" and crypto["private_key_valid"]
    return 0 if usable else 1


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


def setup_login(
    prompt: Prompt = input,
    secret_prompt: Prompt = getpass.getpass,
    out: Printer = print,
) -> int:
    """Obtain session tokens, reusing an existing session where possible.

    A stored session that is still valid, or that can be refreshed, needs no
    password at all — so that is tried first.

    Args:
        prompt: Reads the username and any MFA code. Injected for testing.
        secret_prompt: Reads the password. Injected for testing.
        out: Receives progress output. Injected for testing.

    Returns:
        Process exit code — 0 on success.
    """
    from pyhood import login
    from pyhood.exceptions import AuthError, MFARequiredError

    status = session_status()
    if status["exists"]:
        out(f"Found a stored session at {status['path']}.")
        out("Trying it first — a valid or refreshable session needs no password.")
        try:
            login()
        except Exception as e:
            out(f"    Could not reuse it ({type(e).__name__}). Falling back to a full login.")
        else:
            out("    OK — the stored session works. Nothing else to do.")
            return 0
        out("")

    out("Robinhood needs your username and password for a fresh login.")
    out("The password is read without echoing, is not stored, and is not")
    out("written anywhere — only the resulting tokens are saved to disk.")
    out("")
    out("Afterwards Robinhood sends a device approval prompt to your phone —")
    out("open the Robinhood app and tap 'Yes, it's me' when it appears.")
    out("")

    try:
        username = _ask(prompt, "Robinhood email/username: ").strip()
        if not username:
            out("Nothing entered — no login attempted.")
            return 1
        password = _ask(secret_prompt, "Password (hidden): ")
        if not password:
            out("Nothing entered — no login attempted.")
            return 1
    except CancelledError:
        out("")
        out("Cancelled — no login attempted. Nothing was saved.")
        out("Run this again when you have the Robinhood app to hand.")
        return 1

    out("")
    out("Logging in. Approve the device in your Robinhood app if prompted.")
    try:
        try:
            login(username, password)
        except MFARequiredError:
            code = _ask(prompt, "MFA code: ").strip()
            login(username, password, mfa_code=code)
    except CancelledError:
        out("")
        out("Cancelled — no login attempted.")
        return 1
    except AuthError as e:
        out(f"    FAILED — {type(e).__name__}: {e}")
        return 1

    saved = session_status()
    out("")
    out(f"Logged in. Session saved to {saved['path']}, readable only by you.")
    return 0


# ── Command line ─────────────────────────────────────────────────────


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


def build_parser() -> argparse.ArgumentParser:
    """The command-line parser for `pyhood` / `python -m pyhood`."""
    parser = argparse.ArgumentParser(
        prog=invocation(),
        description="Set up the credentials pyhood needs.",
    )
    from pyhood import __version__

    parser.add_argument("--version", action="version", version=f"pyhood {__version__}")

    commands = parser.add_subparsers(dest="command")
    commands.add_parser("version", help="print the installed pyhood version")
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
        choices=("crypto", "login"),
        help="crypto: generate a Crypto API key pair. login: obtain session tokens.",
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
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for `pyhood` and `python -m pyhood`."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        from pyhood import __version__

        print(f"pyhood {__version__}")
        return 0
    if args.command != "setup":
        parser.print_help()
        return 0
    if args.target == "crypto":
        return setup_crypto(force=args.force, verify=not args.no_verify)
    if args.target == "login":
        return setup_login()
    return print_status()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
