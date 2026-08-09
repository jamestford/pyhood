# Getting Started

## Installation

pyhood needs **Python 3.10 or newer**. Install it into a virtual environment rather than your system Python:

```bash
python3.14 -m venv pyhood-env
source pyhood-env/bin/activate
python -m pip install --upgrade pip
python -m pip install pyhood
```

Substitute whichever interpreter you have — 3.10 through 3.14 are tested in CI. On Windows the activate line is `pyhood-env\Scripts\activate`.

!!! warning "Name the Python version explicitly"
    A virtual environment inherits the version of the interpreter that creates it, and `python3` on macOS is still 3.9. Using bare `python3` there produces a 3.9 environment where the install fails with `no matching distribution found` — which reads like the package is missing rather than a version problem.

    ```bash
    brew install python@3.14
    ```

!!! note "Why the virtual environment is not optional"
    Homebrew and Debian-based distributions mark their Python as [externally managed](https://peps.python.org/pep-0668/), so installing into it is refused outright. Overriding that with `--break-system-packages` can break OS tooling that depends on the system packages.

    A virtual environment also keeps pyhood's dependencies — `requests`, `cryptography`, `pynacl` — from colliding with other projects, and `rm -rf pyhood-env` undoes the whole install.

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
