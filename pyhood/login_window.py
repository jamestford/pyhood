"""Open a terminal window for the user to authorize pyhood, and wait for them.

An AI agent cannot log in. The login needs a password, which the agent must
never see, and an approval on the user's phone. An agent's commands also run
without a terminal, so there is nowhere for anyone to type.

``pyhood authorize --window`` closes that gap. It opens a terminal window
on the user's own screen with the ordinary login running in it, and waits.
The user types in that window. Nothing they type passes through this
process, or through the agent that started it.

Agents stop commands that run too long, so the wait is short and the command
can be run again: a second run finds the window already open and goes back
to waiting, without opening another.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from pyhood.onboarding import IN_WINDOW_VARIABLE, TITLE

DEFAULT_WAIT = 90
"""Seconds to wait before handing back to the agent. Under two minutes,
which is where several agents stop a command."""

STALE_AFTER = 15 * 60
"""Seconds after which a window nobody finished is taken to be gone."""

LOGGED_IN = 0
NOT_FINISHED = 1
NO_WINDOW = 2
STILL_WAITING = 3

Printer = Callable[[str], None]


def _say(line: str = "") -> None:
    # Flushed, so the agent has the instructions even if it stops the wait.
    print(line, flush=True)


def state_dir() -> Path:
    """Where the window's script and its result are kept."""
    from pyhood.auth import DEFAULT_TOKEN_DIR

    return DEFAULT_TOKEN_DIR / "login-window"


def _login_command() -> list[str]:
    """The login, run with the Python this pyhood is installed in."""
    beside = Path(sys.executable).parent / "pyhood"
    if beside.is_file():
        return [str(beside), "authorize"]
    return [sys.executable, "-m", "pyhood", "authorize"]


def script_text(status: Path) -> str:
    """The shell script the window runs.

    It runs the login, then writes the login's exit code where the waiting
    command looks for it. Closing the window counts as not finishing.
    """
    command = " ".join(shlex.quote(part) for part in _login_command())
    return f"""#!/bin/sh
# Written by `pyhood authorize --window`. Safe to delete.
status={shlex.quote(str(status))}
# Save the login where the command that opened this window will look.
HOME={shlex.quote(str(Path.home()))}
export HOME
# Tells the login it is in this window, so its text says what to do with it.
{IN_WINDOW_VARIABLE}=1
export {IN_WINDOW_VARIABLE}
trap 'echo 130 > "$status"; exit 130' HUP INT TERM
printf '\\033]0;{TITLE}\\007'
clear
{command}
echo "$?" > "$status"
"""


def window_commands(script: Path, platform: str | None = None,
                    environ: dict[str, str] | None = None) -> list[list[str]]:
    """Commands that would each open a terminal window running `script`.

    Empty when there is no screen to open one on. They are tried in order.
    """
    platform = sys.platform if platform is None else platform
    environ = dict(os.environ) if environ is None else environ

    # Over SSH a window would open on a screen the user is not sitting at.
    if environ.get("SSH_CONNECTION") or environ.get("SSH_TTY"):
        return []
    if platform == "darwin":
        # macOS opens a .command file in the user's terminal program.
        return [["open", str(script)]]
    if platform.startswith("linux"):
        if not (environ.get("DISPLAY") or environ.get("WAYLAND_DISPLAY")):
            return []
        run = ["sh", str(script)]
        return [
            ["x-terminal-emulator", "-e", *run],
            ["gnome-terminal", "--", *run],
            ["konsole", "-e", *run],
            ["xfce4-terminal", "-x", *run],
            ["xterm", "-e", *run],
        ]
    return []


def open_window(script: Path, platform: str | None = None,
                environ: dict[str, str] | None = None) -> bool:
    """Open a terminal window running `script`. False if none could be opened."""
    platform = sys.platform if platform is None else platform
    for command in window_commands(script, platform, environ):
        if shutil.which(command[0]) is None:
            continue
        try:
            if platform == "darwin":
                # `open` hands the file over and returns at once.
                done = subprocess.run(command, capture_output=True, timeout=20)
                if done.returncode == 0:
                    return True
            else:
                # A terminal program runs for as long as its window is open.
                subprocess.Popen(
                    command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True,
                )
                return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


def _saved_login_works() -> bool:
    from pyhood import login
    from pyhood.onboarding import session_status

    if not session_status()["exists"]:
        return False
    try:
        login()
    except Exception:
        return False
    return True


def _read_status(status: Path) -> int | None:
    """The login's exit code, once the window has written it."""
    try:
        text = status.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text:
        return None  # caught between the file being created and written
    try:
        return int(text)
    except ValueError:
        return NOT_FINISHED


def _clear(folder: Path) -> None:
    for name in ("login.command", "status"):
        try:
            (folder / name).unlink()
        except OSError:
            pass


def _window_is_open(script: Path, now: float) -> bool:
    """True when an earlier run opened a window the user may still be in."""
    try:
        return now - script.stat().st_mtime < STALE_AFTER
    except OSError:
        return False


def login_in_window(
    wait: float = DEFAULT_WAIT,
    program: str = "pyhood",
    out: Printer = _say,
    opener: Callable[[Path], bool] = open_window,
    saved_login_works: Callable[[], bool] = _saved_login_works,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    now: Callable[[], float] = time.time,
) -> int:
    """Open a login window for the user and wait for them to finish.

    Returns:
        0 logged in, 1 the login did not finish, 2 no window could be
        opened, 3 the user has not finished yet.
    """
    from pyhood.secure_files import OWNER_ONLY_DIR, ensure_private_dir

    again = f"{program} authorize --window"

    folder = state_dir()
    script, status = folder / "login.command", folder / "status"

    if saved_login_works():
        _clear(folder)  # what an earlier run left, if the user finished after it
        out("pyhood is already authorized. No window was needed.")
        out(f"Check it with: {program} verify")
        return LOGGED_IN

    if _read_status(status) is not None:
        # An earlier run's window has finished. Its result is reported below,
        # so a login that failed is not answered with a window popping up.
        pass
    elif _window_is_open(script, now()):
        out(f'The "{TITLE}" window is already open on the user\'s screen.')
        out("Not opening another.")
        out(f"Waiting up to {wait:g} seconds for them to finish.")
    else:
        ensure_private_dir(folder)
        _clear(folder)
        script.write_text(script_text(status), encoding="utf-8")
        os.chmod(script, OWNER_ONLY_DIR)
        if not opener(script):
            _clear(folder)
            out("Could not open a terminal window here.")
            out("Ask the user to run this themselves, in their own terminal, and to")
            out("tell you when they have:")
            out(f"    {program} authorize")
            out("Never ask for, read or type their password.")
            return NO_WINDOW
        out(f'A terminal window titled "{TITLE}" has opened on the user\'s screen.')
        out("Tell the user: type your Robinhood username and password in that window,")
        out("then approve the request in the Robinhood app on your phone.")
        out("Never ask for, read or type their password.")
        out(f"Waiting up to {wait:g} seconds for them to finish.")

    deadline = clock() + wait
    while True:
        code = _read_status(status)
        if code is not None:
            _clear(folder)
            if code == 0:
                out("Authorized.")
                out(f"Check it with: {program} verify")
                return LOGGED_IN
            out("The authorization in the window did not finish. Ask the user what happened.")
            out(f"To open the window again: {again}")
            return NOT_FINISHED
        if clock() >= deadline:
            break
        sleep(0.5)

    out("The user has not finished yet. Run this again to keep waiting.")
    out("It will not open a second window:")
    out(f"    {again}")
    return STILL_WAITING
