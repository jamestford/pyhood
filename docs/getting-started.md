# Getting Started

## Installation

The quickest way is with [uv](https://docs.astral.sh/uv/getting-started/installation/) (`brew install uv` on macOS). One command installs pyhood with its own copy of Python and puts the `pyhood` command on your PATH:

```bash
uv tool install --managed-python --python 3.14 pyhood
```

There is no Python version to find first and no environment to activate: `pyhood` works from any terminal.

!!! note "Why `--managed-python`"
    It tells uv to use a Python that it downloads and keeps for itself. Without it uv may borrow your system's or Homebrew's Python, and the install then breaks when that Python is upgraded or removed. Homebrew does remove old versions: an environment built on its Python 3.14 stopped working the day Homebrew moved to 3.15.

Check it worked, and upgrade later, with:

```bash
pyhood version
uv tool upgrade pyhood
```

### Running your scripts

A tool install is isolated: the `pyhood` command is on your PATH, but a plain `python` cannot `import pyhood`. Run scripts with:

```bash
pyhood run script.py
```

That uses the Python pyhood is installed in, and works the same however pyhood was installed.

### Installing with pip instead

Use this when you are adding pyhood to a project that already has its own environment. pyhood needs **Python 3.10 or newer**. Install it into a virtual environment rather than your system Python:

```bash
python3.14 -m venv pyhood-env
source pyhood-env/bin/activate
python -m pip install --upgrade pip
python -m pip install pyhood
```

Substitute whichever interpreter you have; 3.10 through 3.14 are tested in CI. On Windows the activate line is `pyhood-env\Scripts\activate`.

!!! warning "Name the Python version explicitly"
    A virtual environment inherits the version of the interpreter that creates it, and `python3` on macOS is still 3.9. Using bare `python3` there produces a 3.9 environment where the install fails with `no matching distribution found`, which reads like the package is missing rather than a version problem.

!!! warning "The environment depends on the Python that created it"
    If that Python is later removed, the environment stops working and has to be rebuilt. The `pyhood` command also exists only while the environment is activated, so a new terminal, or an AI agent running commands, will not find it.

!!! note "Why the virtual environment is not optional"
    Homebrew and Debian-based distributions mark their Python as [externally managed](https://peps.python.org/pep-0668/), so installing into it is refused outright. Overriding that with `--break-system-packages` can break OS tooling that depends on the system packages.

For development:

```bash
git clone https://github.com/jamestford/pyhood.git
cd pyhood
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## First Login

pyhood requires a one-time device approval through the Robinhood mobile app. After that, sessions refresh automatically.

### Step 1: Have Your Phone Ready

Open the Robinhood app on your phone. You'll need to tap "Yes, it's me" when prompted.

### Step 2: Login

```bash
pyhood setup login
```

It prompts for your username and password — the password is read without echoing and is never stored — then Robinhood sends a device approval push notification to your phone. Tap **"Yes, it's me"** to approve. The session is saved to `~/.pyhood/session.json`, readable only by you.

To log in from code instead:

```python
import pyhood

session = pyhood.login(
    username="you@email.com",
    password="your_password",
    timeout=90,  # seconds to wait for device approval
)
```

Prefer the command where you can. A password written into a script tends to end up committed.

### Step 3: Use the Client

```python
import pyhood
from pyhood.client import PyhoodClient

# No credentials needed — reuses the stored session.
client = PyhoodClient(pyhood.login())

# Get a stock quote
quote = client.get_quote("AAPL")
print(f"AAPL: ${quote.price:.2f}")

# Check your buying power
power = client.get_buying_power()
print(f"Buying power: ${power:,.2f}")
```

### Step 4: There Is No Step 4

Your session is cached at `~/.pyhood/session.json`. Next time you call `pyhood.login()` or `pyhood.refresh()`, it reuses or refreshes the cached token automatically. No device approval needed.

```python
# Subsequent runs — instant, no approval
session = pyhood.refresh()
client = PyhoodClient(session)
```

## Using pyhood With an AI Agent

pyhood is built to be driven by an AI agent that writes and runs Python. Put one line in the agent's instructions file (`AGENTS.md`, `CLAUDE.md` or similar):

```text
pyhood is installed on this machine. Run `pyhood guide` before using it.
```

`pyhood guide` prints the read-only commands (`pyhood positions`, `pyhood orders` and so on), how to run a script, how to log in, the main methods with their arguments, and the fields of what they return, all for the installed version. For anything the commands do not cover, `pyhood run script.py` runs the agent's script with the right Python. See [Command Line](cli.md).

An agent with your session can place real orders. The guide tells it to show you the exact call and wait for a yes first, but that is an instruction, not a lock.

## Environment Variables

For scripts and automation, store credentials in a `.env` file:

```bash
# .env
RH_USERNAME=you@email.com
RH_PASSWORD=your_password
```

```python
import os
import pyhood
from dotenv import load_dotenv

load_dotenv()
session = pyhood.login(
    username=os.getenv("RH_USERNAME"),
    password=os.getenv("RH_PASSWORD"),
)
```

!!! warning "Never commit `.env` files"
    pyhood's `.gitignore` blocks `.env` and `*.json` by default. Double-check before pushing to a remote repo.
