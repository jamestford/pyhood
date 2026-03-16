# Getting Started

## Installation

```bash
pip install pyhood
```

For development:

```bash
git clone https://github.com/jamestford/pyhood.git
cd hood
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## First Login

hood requires a one-time device approval through the Robinhood mobile app. After that, sessions refresh automatically.

### Step 1: Have Your Phone Ready

Open the Robinhood app on your phone. You'll need to tap "Yes, it's me" when prompted.

### Step 2: Login

```python
import pyhood

session = pyhood.login(
    username="you@email.com",
    password="your_password",
    timeout=90,  # seconds to wait for device approval
)
```

When you run this, Robinhood will send a device approval push notification to your phone. Tap **"Yes, it's me"** to approve.

### Step 3: Use the Client

```python
from pyhood.client import HoodClient

client = HoodClient(session)

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
client = HoodClient(session)
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
    hood's `.gitignore` blocks `.env` and `*.json` by default. Double-check before pushing to a remote repo.
