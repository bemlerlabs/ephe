# The contributor's gate. Targets here run with tools this repository carries, so a
# clone plus an engine-free checkout is enough to check a change before opening a pull
# request. The project's own quality gates — prose, language, token and architecture
# ratchets — live in the working repository and are not published here.

PY ?= .venv/bin/python
UI ?= npm --prefix app

.PHONY: help verify test test-python test-web build hooks doctor agents-md clean

help:
	@echo "verify        everything a pull request has to pass"
	@echo "test          both suites without the type check"
	@echo "test-python   pytest over tests/"
	@echo "test-web      vitest over app/src"
	@echo "build         type-check and build the web app"
	@echo "hooks         point this checkout's git hooks at .husky, once per clone"
	@echo "agents-md     check the agent instruction hub and its area files"
	@echo "doctor        report the toolchain versions this repository expects"

verify: test build agents-md

test: test-python test-web

test-python:
	$(PY) -m pytest tests/ -q -p no:cacheprovider

test-web:
	$(UI) run test

build:
	$(UI) run build

# The hook content is checked in under .husky; git only runs it when core.hooksPath says so, and
# nothing in this tree ever said so — app/package.json carries husky as a devDependency with no
# prepare script, so `pnpm install` never wired it and a clone committed unchecked. A copy in
# .git/hooks would be the second home of one fact, so this target points git at the checked-in
# file instead. Relative, so each linked worktree gets its own checked-out hook.
hooks:
	@test -x .husky/pre-commit || { \
		echo "hooks: .husky/pre-commit is not executable — restore the tracked bit with 'chmod +x .husky/pre-commit .husky/pre-push'" >&2; \
		exit 1; }
	@git config core.hooksPath .husky
	@echo "hooks: core.hooksPath = .husky — every commit here now runs .husky/pre-commit"

agents-md:
	$(PY) scripts/agents_md_check.py

doctor:
	@echo "python : $$($(PY) -V 2>&1 || echo 'not found — create .venv and run uv sync')"
	@echo "node   : $$(node -v 2>&1 || echo 'not found')"
	@echo "npm    : $$(npm -v 2>&1 || echo 'not found')"
	@echo "cargo  : $$(cargo --version 2>&1 || echo 'not found — only needed for the desktop app')"
	@echo "hooks  : $$(git config --get core.hooksPath 2>/dev/null || echo 'OFF — no hook runs on commit; run make hooks')"

clean:
	rm -rf app/dist
