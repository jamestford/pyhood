"""Loading Crypto API credentials from disk or the environment.

Crypto API credentials are long-lived and, unlike a session token, cannot be
refreshed — a leaked private key can trade until it is revoked. They should
never be hardcoded or committed.

Resolution order:

1. ``RH_CRYPTO_API_KEY`` / ``RH_CRYPTO_PRIVATE_KEY`` environment variables
2. ``~/.pyhood/crypto.env`` (override with ``PYHOOD_CRYPTO_ENV``)

The file is a plain ``KEY=value`` env file:

    RH_CRYPTO_API_KEY=your-api-key
    RH_CRYPTO_PRIVATE_KEY=your-base64-ed25519-private-key

It should be readable only by you (``chmod 600``); `load_credentials` warns
if it is not.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from pyhood.secure_files import warn_if_readable_by_others

logger = logging.getLogger("pyhood")

API_KEY_VAR = "RH_CRYPTO_API_KEY"
PRIVATE_KEY_VAR = "RH_CRYPTO_PRIVATE_KEY"
DEFAULT_CREDENTIALS_FILE = Path.home() / ".pyhood" / "crypto.env"


def credentials_path() -> Path:
    """Where credentials are read from, honouring PYHOOD_CRYPTO_ENV."""
    override = os.environ.get("PYHOOD_CRYPTO_ENV")
    return Path(override) if override else DEFAULT_CREDENTIALS_FILE


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a KEY=value file. Ignores blanks, comments and malformed lines."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def load_credentials(
    api_key: str | None = None, private_key_base64: str | None = None,
) -> tuple[str, str]:
    """Resolve Crypto API credentials.

    Args:
        api_key: Explicit API key. Skips lookup when both are given.
        private_key_base64: Explicit private key.

    Returns:
        Tuple of (api_key, private_key_base64).

    Raises:
        FileNotFoundError: If neither the environment nor the file supplies
            both values.
    """
    if api_key and private_key_base64:
        return api_key, private_key_base64

    resolved_key = api_key or os.environ.get(API_KEY_VAR, "")
    resolved_private = private_key_base64 or os.environ.get(PRIVATE_KEY_VAR, "")

    if not (resolved_key and resolved_private):
        path = credentials_path()
        if path.exists():
            warn_if_readable_by_others(path)
            values = _parse_env_file(path)
            resolved_key = resolved_key or values.get(API_KEY_VAR, "")
            resolved_private = resolved_private or values.get(PRIVATE_KEY_VAR, "")

    if not (resolved_key and resolved_private):
        raise FileNotFoundError(
            f"No crypto credentials found. Set {API_KEY_VAR} and "
            f"{PRIVATE_KEY_VAR}, or create {credentials_path()} containing "
            f"both (chmod 600). See the README for how to generate a key pair."
        )

    return resolved_key, resolved_private


def credentials_available() -> bool:
    """Whether credentials can be resolved, without returning them."""
    try:
        load_credentials()
        return True
    except FileNotFoundError:
        return False
