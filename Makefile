.PHONY: help setup test coverage lint sync verify-dist run-file run-live simulate-file simulate-live live-forget logs status stop call

# Describe every target. `setup` stays the default goal (see .DEFAULT_GOAL).
help:
	@echo "Usage: make <target> [OPTION=value ...]"
	@echo ""
	@echo "Development"
	@echo "  setup          Install the package in editable mode and the pre-commit hooks"
	@echo "  test           Run the full test suite (coverage needs the whole suite)"
	@echo "  coverage       Run the tests under coverage and write an lcov report"
	@echo "  lint           Run every linter through pre-commit"
	@echo "  sync           Generate the sync pyhiveapi package from the async source"
	@echo "  verify-dist    Build the wheel and check it imports in a clean venv"
	@echo ""
	@echo "Local session runner (read-only unless started with WRITE=1)"
	@echo "Each run-*/simulate-* target starts a background process that keeps"
	@echo "polling until 'make stop', and writes to logs/<name>.log (gitignored)."
	@echo "  run-file       Session against the bundled fixture (no account, no network)"
	@echo "  run-live       Session against a real Hive account. Asks for email and"
	@echo "                 password (hidden, not stored) and, on the first run, the SMS"
	@echo "                 code, then moves to the background"
	@echo "  simulate-file  As run-file, but strips a state key from every poll after"
	@echo "                 the first, to imitate Hive returning incomplete state"
	@echo "  simulate-live  As run-live, with the same stripping applied to real data"
	@echo "  logs           Follow the runner logs (Ctrl-C stops following, not the runners)"
	@echo "  status         List the runners that are running"
	@echo "  stop           Stop the runners"
	@echo "  call           Run an admin command inside a running session, e.g."
	@echo "                 CMD=\"mode Hallway\". With no CMD it lists the commands"
	@echo "  live-forget    Delete the device credentials run-live saved in the macOS Keychain"
	@echo ""
	@echo "Options"
	@echo "  INTERVAL=<s>   Seconds between polls (default 120; simulate-file 5, simulate-live 30)"
	@echo "  POLLS=<n>      Stop after n polls (default: run until stopped)"
	@echo "  DROP=<key>     State key the simulate-* targets strip (default mode)"
	@echo "  DEBUG=1        Turn on the library's debug logging"
	@echo "  WRITE=1        Start a session whose admin commands may change devices"
	@echo "  CMD=\"...\"      The admin command for 'make call'"
	@echo "  NAME=<runner>  Limit logs/stop/call to one of: file, live, simulate-file, simulate-live"
	@echo ""
	@echo "Admin commands (make call CMD=\"<command>\")"
	@echo "DEVICE is a name or the 8-character ID shown by 'devices'."
	@echo "  help                      List the commands and whether writes are allowed"
	@echo "  devices                   List the devices the other commands can address"
	@echo "  poll                      Poll Hive now"
	@echo "  mode DEVICE               The mode the library reports (heating, hot water)"
	@echo "  state DEVICE              The state as last received, without its schedule"
	@echo "  drop KEY... | off         Start or stop stripping state keys from polls"
	@echo "  debug on | off            Library debug logging"
	@echo "  interval SECONDS          Seconds between polls, from the next wait"
	@echo "Only in a session started with WRITE=1 (these change real devices):"
	@echo "  set-mode DEVICE MODE      Set a heating or hot water mode"
	@echo "  set-temp DEVICE TEMP      Set a heating target temperature"
	@echo "  boost DEVICE MINS [TEMP]  Start a boost (heating needs TEMP)"
	@echo "  boost-off DEVICE          Cancel a boost"
	@echo "  turn-on DEVICE            Turn a light or plug on"
	@echo "  turn-off DEVICE           Turn a light or plug off"
	@echo ""
	@echo "Examples"
	@echo "  make simulate-file INTERVAL=2 POLLS=8"
	@echo "  make logs NAME=simulate-file"
	@echo "  make stop NAME=live"
	@echo "  make call CMD=\"drop mode\"       # start stripping mode from polls"
	@echo "  make run-live WRITE=1            # then: make call CMD=\"set-mode Hallway OFF\""

.DEFAULT_GOAL := setup

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
# Each run-*/simulate-* target starts a background process that polls until
# `make stop`, and writes to logs/ (gitignored). They are read-only unless
# started with WRITE=1, which lets `make call` commands change devices.
# Options: INTERVAL=<seconds between polls>, DROP=<state key>,
# DEBUG=1 (library debug logging), POLLS=<n> (stop after n polls).
RUN_SESSION = python3 scripts/run_session.py
RUN_FLAGS = $(if $(POLLS),--polls $(POLLS)) $(if $(DEBUG),--debug) \
	$(if $(WRITE),--allow-writes)
RUN_OPTS = $(RUN_FLAGS) $(if $(INTERVAL),--interval $(INTERVAL))

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
		$(RUN_FLAGS)

simulate-live:
	$(RUN_SESSION) --live --drop $(or $(DROP),mode) --interval $(or $(INTERVAL),30) \
		$(RUN_FLAGS)

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

# Run an admin command inside a running session: make call CMD="mode Hallway".
# `make call` alone lists the commands. NAME=<runner> picks the session when
# more than one is running.
call:
	@$(RUN_SESSION) $(if $(NAME),--name $(NAME)) --call $(or $(CMD),help)

# Remove the device credentials saved in the macOS Keychain by run-live.
live-forget:
	$(RUN_SESSION) --forget
