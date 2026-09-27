.PHONY: setup test lint sync verify-dist

setup:
	pip install -e ".[dev]"
	pre-commit install

test:
	pytest tests/

coverage:
	coverage run -m pytest && coverage lcov

lint:
	pre-commit run --all-files

sync:
	python setup.py build_py

# Build the wheel and prove it is importable in a clean venv. The test suite
# runs against src/, so only this catches packaging regressions.
verify-dist:
	rm -rf dist
	python -m build
	python scripts/verify_dist.py dist
