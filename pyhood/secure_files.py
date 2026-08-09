"""Owner-only file handling for stored credentials.

Session tokens and Crypto API keys are credentials: anyone who can read them
can act on the account. Files holding them are created 0600 and their
directory 0700, and a warning is logged if an existing file is looser.
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

logger = logging.getLogger("pyhood")

OWNER_ONLY_FILE = 0o600
OWNER_ONLY_DIR = 0o700


def ensure_private_dir(path: Path) -> None:
    """Create a directory that only the owner can read."""
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, OWNER_ONLY_DIR)
    except OSError as e:  # pragma: no cover - platform dependent
        logger.debug(f"Could not tighten permissions on {path}: {e}")


def write_private(path: Path, content: str) -> None:
    """Write a file only the owner can read.

    The mode is applied at creation so the content is never briefly readable
    by others, and reapplied afterwards in case the file already existed.
    """
    ensure_private_dir(path.parent)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, OWNER_ONLY_FILE)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
    finally:
        try:
            os.chmod(path, OWNER_ONLY_FILE)
        except OSError as e:  # pragma: no cover - platform dependent
            logger.debug(f"Could not tighten permissions on {path}: {e}")


def warn_if_readable_by_others(path: Path) -> bool:
    """Warn when a credential file is group or world readable.

    Returns:
        True if the permissions are too open.
    """
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    if mode & (stat.S_IRGRP | stat.S_IROTH | stat.S_IWGRP | stat.S_IWOTH):
        logger.warning(
            f"{path} is accessible to other users on this machine. It holds "
            f"credentials that can act on your account — run: chmod 600 {path}"
        )
        return True
    return False
