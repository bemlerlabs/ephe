# The contributor's gate. Targets here run with tools this repository carries, so a
# clone plus an engine-free checkout is enough to check a change before opening a pull
# request. The project's own quality gates — prose, language, token and architecture
# ratchets — live in the working repository and are not published here.

PY ?= .venv/bin/python
UI ?= npm --prefix app

.PHONY: help verify test test-python test-web build doctor clean

help:
	@echo "verify        everything a pull request has to pass"
	@echo "test          both suites without the type check"
	@echo "test-python   pytest over tests/"
	@echo "test-web      vitest over app/src"
	@echo "build         type-check and build the web app"
	@echo "doctor        report the toolchain versions this repository expects"

verify: test build

test: test-python test-web

test-python:
	$(PY) -m pytest tests/ -q -p no:cacheprovider

test-web:
	$(UI) run test

build:
	$(UI) run build

doctor:
	@echo "python : $$($(PY) -V 2>&1 || echo 'not found — create .venv and run uv sync')"
	@echo "node   : $$(node -v 2>&1 || echo 'not found')"
	@echo "npm    : $$(npm -v 2>&1 || echo 'not found')"
	@echo "cargo  : $$(cargo --version 2>&1 || echo 'not found — only needed for the desktop app')"

clean:
	rm -rf app/dist
