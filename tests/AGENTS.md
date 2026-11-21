# Tests

The pytest suite: its runner, its isolation and what a test may assert.

Applies on top of the root AGENTS.md.

## Runner

```bash
make test-python                                             # the suite CI runs
.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
.venv/bin/python -m pytest tests/test_language_gate.py -q -p no:cacheprovider   # one file
```

`-p no:cacheprovider` stays on: a shared checkout keeps no `.pytest_cache`, and a second run does not
depend on the first. CI runs a parallel leg with `-n auto`, so a test that only passes serially is
not finished.

## Isolation

The suite has to run on a machine where Ephe is installed and in use, so every test starts from a
hermetic state rather than from the developer's home:

- `EPHE_CONFIG_DIR` points at a per-test directory. The autouse fixtures in `tests/conftest.py` pin
  the artifact store, the skills directory and the security store to `tmp_path`; a test body that
  overrides `EPHE_CONFIG_DIR` runs after them and wins.
- A module that binds its path at import time (`DEFAULT_USER_SKILLS_DIR`, `engine_config.CONFIG_DIR`)
  needs the constant patched directly, because the environment variable alone arrives too late.
  `_hermetic_skills_state` is the example.
- `_home_isolation_attribution` tells `tests/test_home_isolation.py` which test is running, so a
  write into the real `~/.ephe` fails that test by name. Do not route around the tripwire; pass the
  directory the code needs, or patch the constant.

## What a test may assert

- Behavior at a seam: a function, a route, a CLI call, a rendered card. A change-detector test — one
  that pins the current shape of the code, a line number, a count nothing reads — breaks on every
  rename and proves nothing about the product.
- The source text of a module is not a seam. Two files read it on purpose, because the constraint
  exists only in a file the product cannot import: `tests/test_macos_usage_strings.py` reads the
  Info.plist usage strings, and `tests/test_dev_handle_gate.py` reads the shipped bundle. A new test
  that reads source needs the same reason.
- No real engine turn. The suite runs offline against the mock Ollama fixtures in
  `tests/conftest.py` or an injected fake client; a test that wants a remote shape asserts the
  request the client would send.
- German is product text. A fixture that carries it may assert what the German surface shows; the
  developer prose in a test stays English, and the German bundle is never the thing translated to
  make a test easier.

## Network

`tests/conftest.py` patches the update feed off for every test and clears the proxy variables, so a
boot path cannot dial out from a unit test. A test that needs the network is testing the wrong layer:
inject the client, or mark the capability through `tests/support/capabilities.py` and let the host
decide whether it runs.

## xdist

Every worker gets its own fixtures and its own temp directory. A test that shares state across
workers — a fixed port, a file under the checkout, a module-level registry — is a flake in CI and
green on the developer's serial run, which is the worst combination. Pin a free port, or run the
case serial with a reason.

The serial timing segment stands down when workers are present (`tests/timing_segment.py`), so a wall
clock read under `-n auto` is not evidence. Measure timing serial, on a named machine, and record the
number with the engine that produced it.
