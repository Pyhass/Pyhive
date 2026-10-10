.PHONY: setup test lint sync verify-dist run-file run-live simulate-file simulate-live live-forget logs status stop

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

# --- Local session runner (scripts/run_session.py) --------------------------
# Read-only: each run-*/simulate-* target starts a background process that
# polls until `make stop`, and writes to logs/ (gitignored). They never change
# a device. Options: INTERVAL=<seconds between polls>, DROP=<state key>,
# DEBUG=1 (library debug logging), POLLS=<n> (stop after n polls).
RUN_SESSION = python3 scripts/run_session.py
RUN_OPTS = $(if $(POLLS),--polls $(POLLS)) $(if $(INTERVAL),--interval $(INTERVAL)) \
	$(if $(DEBUG),--debug)

# Session against the bundled fixture (no account, no network).
run-file:
	$(RUN_SESSION) --file $(RUN_OPTS)

# Session against a real Hive account. Prompts for the password (hidden, never
# stored) and, on the first run, the SMS code, then moves to the background.
run-live:
	$(RUN_SESSION) --live $(RUN_OPTS)

# Simulate Hive returning incomplete state: DROP (default `mode`) is stripped
# from every poll after the first.
simulate-file:
	$(RUN_SESSION) --file --drop $(or $(DROP),mode) --interval $(or $(INTERVAL),5) \
		$(if $(POLLS),--polls $(POLLS)) $(if $(DEBUG),--debug)

simulate-live:
	$(RUN_SESSION) --live --drop $(or $(DROP),mode) --interval $(or $(INTERVAL),30) \
		$(if $(POLLS),--polls $(POLLS)) $(if $(DEBUG),--debug)

# Follow the logs of every runner (Ctrl-C stops following, not the runners).
# NAME=<file|live|simulate-file|simulate-live> follows just one.
logs:
	@mkdir -p logs && touch logs/$(or $(NAME),file).log
	tail -n 40 -F logs/$(or $(NAME),*).log

# List the running background runners.
status:
	@$(RUN_SESSION) --status

# Stop every runner, or just NAME=<runner>.
stop:
	@$(RUN_SESSION) --stop $(if $(NAME),--name $(NAME))

# Remove the device credentials saved in the macOS Keychain by run-live.
live-forget:
	$(RUN_SESSION) --forget
