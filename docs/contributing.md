# Contributing

hood is in early development and we welcome contributions.

## Development Setup

```bash
git clone https://github.com/jamestford/pyhood.git
cd hood
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pip install responses  # for tests
```

## Running Tests

```bash
# All tests
pytest -v

# With coverage
pytest --cov=hood --cov-report=term-missing -v

# Single test file
pytest tests/test_auth.py -v
```

## Linting

```bash
# Check
ruff check hood/

# Auto-fix
ruff check --fix hood/
```

## Project Structure

```
hood/
├── hood/
│   ├── __init__.py      # Public API (login, logout, refresh)
│   ├── auth.py          # Authentication + token management
│   ├── client.py        # HoodClient — high-level API
│   ├── exceptions.py    # Exception hierarchy
│   ├── http.py          # HTTP session, rate limiting, retries
│   ├── models.py        # Typed dataclasses
│   └── urls.py          # Robinhood API endpoints
├── tests/               # Test suite (responses-based mocking)
├── docs/                # MkDocs documentation
└── .github/
    └── workflows/
        └── ci.yml       # GitHub Actions CI
```

## Guidelines

- **Type hints** on all public functions and methods
- **Docstrings** in Google style
- **Tests** for new functionality (aim for >80% coverage)
- **No credentials** in code, tests, or docs — use placeholder values
- Run `ruff check` and `pytest` before submitting a PR

## Reporting Issues

- **Bugs**: Open a [GitHub issue](https://github.com/jamestford/pyhood/issues)
- **Security**: See [SECURITY.md](https://github.com/jamestford/pyhood/blob/main/SECURITY.md)
- **Questions**: Open a discussion or issue
