# Getting Started

## Installation

### Have your AI agent do it

pyhood is built to be driven by an AI agent, so the quickest install is to hand it the job. Paste this into your agent:

```text
Install pyhood for me. Follow the install steps in https://raw.githubusercontent.com/jamestford/pyhood/main/AGENTS.md
```

[That file](https://github.com/jamestford/pyhood/blob/main/AGENTS.md) is written for AI agents. It tells yours to run the install script described under [One command](#one-command), and gives it rules that keep it from improvising: stop if a step fails, do not use `pip` or `sudo`, and do not install anything else.

An agent cannot log in for you. The login needs your password, which the agent must never see, and an approval on your phone. So the agent runs `pyhood setup login --window`, which opens a terminal window on your screen with the login in it, and waits for you. You type in that window, and nothing you type passes through the agent. See [First Login](#first-login).

It needs [uv](https://docs.astral.sh/uv/getting-started/installation/) (`brew install uv` on macOS). If uv is missing, the agent stops and asks you.

### One command

To do it yourself, run this in your own terminal, on macOS or Linux:

```bash
curl -LsSf https://raw.githubusercontent.com/jamestford/pyhood/main/install.sh | sh
```

[The script](https://github.com/jamestford/pyhood/blob/main/install.sh) does five things, in order:

1. Looks for [uv](https://docs.astral.sh/uv/getting-started/installation/), the tool pyhood is installed with. If uv is missing, it asks before installing it.
2. Creates `~/pyhood` and installs pyhood into it, with the two commands under [By hand](#by-hand). If pyhood is already there, it upgrades it.
3. Links the command into `~/.local/bin`, so that `pyhood` works from any folder.
4. Runs `pyhood setup login`. See [First Login](#first-login).
5. Runs `pyhood verify`, which reads live prices and changes nothing.

It never uses `sudo`. It installs pyhood, and uv only if you say yes.

Then open your AI agent in `~/pyhood` and ask it something.

| If | Then |
|---|---|
| uv is missing and you answer no | Nothing is installed |
| `~/pyhood` exists and is not a pyhood install | The script stops and changes nothing |
| `~/.local/bin/pyhood` is already something else | It is left alone, and the script tells you to use `~/pyhood/bin/pyhood` |
| `~/.local/bin` is not on your PATH | The script says so. Add it to your PATH to type just `pyhood` |
| The login does not finish | pyhood stays installed. Log in later with `pyhood setup login` |
| No terminal is attached, as when an agent runs it | It installs pyhood and leaves the login alone. The agent then opens a login window with `pyhood setup login --window` |

A download that is cut off partway runs nothing: the script does its work only on its last line.

### By hand

The same steps, typed yourself. pyhood installs into a folder of its own, and that folder is also where you work from:

```bash
uv venv --managed-python --python 3.14 ~/pyhood
uv pip install --python ~/pyhood/bin/python pyhood
```

That creates `~/pyhood`:

| In `~/pyhood` | What it is |
|---|---|
| `bin/pyhood` | The command |
| `bin/python` | A link to the Python pyhood runs on, which uv keeps in its own folder |
| `lib/` | pyhood and what it depends on |
| `AGENTS.md` | Instructions an AI agent reads when it starts in this folder |

Check it worked:

```bash
~/pyhood/bin/pyhood version
```

!!! note "Why `--managed-python`"
    It tells uv to use a Python that it downloads and keeps for itself. Without it uv may borrow your system's or Homebrew's Python, and the install then breaks when that Python is upgraded or removed. Homebrew does remove old versions: an environment built on its Python 3.14 stopped working the day Homebrew moved to 3.15.

### Typing just `pyhood`

The install script does this for you. After the other installs, link the command into a folder that is on your PATH, and it works from anywhere:

```bash
ln -s ~/pyhood/bin/pyhood ~/.local/bin/pyhood
```

The rest of these docs write `pyhood`. If you skip the link, type `~/pyhood/bin/pyhood`. Do not add `~/pyhood/bin` itself to your PATH: that would also put its `python` ahead of your own.

### Upgrading

Run the install command again, or:

```bash
uv pip install --python ~/pyhood/bin/python --upgrade pyhood
```

### Running your scripts

A plain `python` cannot `import pyhood`, because pyhood lives in its own folder. Run scripts with:

```bash
pyhood run script.py
```

That uses the Python pyhood is installed in.

### Installing with pip instead

pyhood needs **Python 3.10 or newer**.

```bash
python3.14 -m venv ~/pyhood
~/pyhood/bin/python -m pip install --upgrade pip
~/pyhood/bin/python -m pip install pyhood
```

Substitute whichever interpreter you have; 3.10 through 3.14 are tested in CI. On Windows the commands are in `pyhood\Scripts` rather than `pyhood/bin`.

!!! warning "Name the Python version explicitly"
    A virtual environment inherits the version of the interpreter that creates it, and `python3` on macOS is still 3.9. Using bare `python3` there produces a 3.9 environment where the install fails with `no matching distribution found`, which reads like the package is missing rather than a version problem.

!!! warning "The environment depends on the Python that created it"
    If that Python is later removed, the environment stops working and has to be rebuilt.

!!! note "Why not the system Python"
    Homebrew and Debian-based distributions mark their Python as [externally managed](https://peps.python.org/pep-0668/), so installing into it is refused outright. Overriding that with `--break-system-packages` can break OS tooling that depends on the system packages.

To add pyhood to a project that already has its own environment, `pip install pyhood` there as usual.

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

An AI agent runs `pyhood setup login --window` instead, which opens a terminal window on your screen with the same login in it. See [Setup](setup.md#logging-in-from-an-ai-agent).

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

pyhood is built to be driven by an AI agent. Open your agent in the install folder:

```bash
cd ~/pyhood
```

The install put an `AGENTS.md` there, which agents that follow that convention read when they start. It tells the agent to run `pyhood guide`. The guide prints the read-only commands (`pyhood positions`, `pyhood orders` and so on), the order commands and their rules, how to run a script, and the fields of what the methods return, all for the installed version. See [Command Line](cli.md).

To use pyhood from some other folder, put one line in that folder's `AGENTS.md` (or `CLAUDE.md`):

```text
pyhood is installed on this machine. Run `pyhood guide` before using it.
```

An agent with your session can place real orders. Unless you have turned confirmation off, the guide tells it to show you an order and wait for a yes, but that is an instruction, not a lock.

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
