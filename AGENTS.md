# Instructions for AI agents

## If you want to use pyhood

Do not run pyhood from this folder. This is its source code, not an install. It has no dependencies installed, and importing it from here fails.

1. Check whether pyhood is installed: `pyhood version`.
2. If it is, run `pyhood guide` and follow it. It covers running scripts, logging in, the main methods and the fields they return.
3. If it is not, ask the user before installing anything. The install command is in `README.md`. Never use `pip install --break-system-packages`.

Never ask for, read or type a password or API key. Never place, change or cancel an order without showing the user the exact call first and getting a yes.

## If you are changing pyhood

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]" responses
pytest
ruff check .
```

- **Build test mocks from real responses, not from the fields the parser reads.** Parsers here have shipped reading field names Robinhood never sends, with tests that mocked the same made-up names and passed. `python scripts/field_audit.py` checks the parsers against a live account; it makes GET requests only and prints field names, never values.
- **`None` means unknown.** Do not turn a missing or null value into `0` or `""`.
- **No credentials, account numbers or order IDs** in code, tests or docs. Use placeholders.
- **The README is also the PyPI page**, so every link in it must be absolute.
- **`pyhood guide` is generated from the code.** When you add a method an agent should know about, add its name to `pyhood/guide.py`.
- Add an entry to `CHANGELOG.md` under `[Unreleased]`.
