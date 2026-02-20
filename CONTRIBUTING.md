# Contributing to SuperScrape

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/PHY041/superscrape.git
cd superscrape

# Create a virtual environment
python -m venv venv
source venv/bin/activate

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Install the Camoufox browser binary
python -c "from camoufox.sync_api import Camoufox; print('ready')"
```

## Code Style

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
# Lint
ruff check .

# Format
ruff format .

# Type check
mypy superscrape/
```

Before submitting a PR, make sure all checks pass:

```bash
ruff check . && ruff format --check . && pytest tests/ -x
```

## Running Tests

```bash
# Unit tests (no API key or browser needed)
pytest tests/ -x

# Verbose output
pytest tests/ -xvs
```

## Adding a New Platform Scraper

1. Create `superscrape/sites/your_platform.py`
2. Inherit from `BaseScraper` in `superscrape/sites/base.py`
3. Implement the required methods (see `amazon.py` as reference)
4. Add a CLI command in `superscrape/cli/main.py`
5. Add tests in `tests/test_your_platform.py`

## Pull Request Process

1. Fork the repo and create a feature branch
2. Make your changes with tests
3. Ensure `ruff check .` and `pytest tests/` pass
4. Submit a PR with a clear description of changes

## Reporting Issues

Open an issue at https://github.com/PHY041/superscrape/issues with:
- Steps to reproduce
- Expected vs actual behavior
- Python version and OS
