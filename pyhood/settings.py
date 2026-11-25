"""Settings the user chooses for this install, kept in ~/.pyhood/settings.json.

There is one so far: whether an order needs the user's confirmation.

- Confirmation on, the default: every order takes two steps. The first
  shows what would be sent and prints a code; the second, with the code,
  sends it.
- Confirmation off: an order is sent at once, unless it is worth more than
  an amount the user sets. Above that it still takes the two steps.

The file holds no secrets. A file that is missing or cannot be read means
the defaults, so a damaged file can never turn confirmation off.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from pyhood.auth import DEFAULT_TOKEN_DIR

# With confirmation off, an order above this many dollars still asks.
DEFAULT_ABOVE = 5000.0


@dataclass(frozen=True)
class Settings:
    """What the user has chosen. The defaults ask before every order."""

    confirmation: bool = True
    above: float = DEFAULT_ABOVE

    def asks(self, value: float | None) -> bool:
        """Whether an order worth `value` dollars needs confirming.

        A value of None is an order whose worth could not be worked out,
        which is treated as too large to send unasked.
        """
        if self.confirmation or value is None:
            return True
        return value > self.above


def path() -> Path:
    """Where the settings are kept. PYHOOD_SETTINGS overrides it, for tests."""
    override = os.environ.get("PYHOOD_SETTINGS")
    return Path(override) if override else DEFAULT_TOKEN_DIR / "settings.json"


def load() -> Settings:
    """The saved settings, or the defaults if there are none that can be read."""
    try:
        data = json.loads(path().read_text())
    except (OSError, ValueError):
        return Settings()
    if not isinstance(data, dict):
        return Settings()
    confirmation = data.get("confirmation")
    above = data.get("confirm_above")
    return Settings(
        # Anything but an explicit false leaves confirmation on.
        confirmation=confirmation is not False,
        above=float(above) if isinstance(above, (int, float)) and not isinstance(above, bool)
        and above >= 0 else DEFAULT_ABOVE,
    )


def save(settings: Settings) -> None:
    """Write the settings where only the user can read them."""
    target = path()
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    target.write_text(json.dumps(
        {"confirmation": settings.confirmation, "confirm_above": settings.above}, indent=2,
    ) + "\n")
    target.chmod(0o600)
