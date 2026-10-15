# Contributing

## Prerequisites

- Python 3.10+
- [pre-commit](https://pre-commit.com/)

## Setup

```bash
git clone https://github.com/Pyhive/Pyhiveapi.git
cd Pyhiveapi
make setup
```

Or manually:

```bash
pip install -e ".[dev]"
pre-commit install
```

## Running tests

```bash
pytest tests/
```

With coverage:

```bash
pytest tests/ --cov
```

## Running linters

```bash
pre-commit run --all-files
```

Individual tools:

```bash
ruff check src/          # lint
ruff format src/         # format
mypy src/                # type check
```

## Generating the sync package

The `pyhiveapi` (sync) package is auto-generated from the async source in `src/`:

```bash
python setup.py build_py
```

Never edit files under `pyhiveapi/` directly — edit `src/` only.

## Submitting a PR

1. Branch off `dev` (not `master`)
2. Make your changes and ensure `pre-commit run --all-files` passes
3. Push and open a PR against `dev`
4. Direct PRs to `master` are blocked

Please read our [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.
