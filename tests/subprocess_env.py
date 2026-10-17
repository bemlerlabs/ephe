"""Base environment for a test subprocess that execs a Python interpreter.

A child built from scratch must differ from its parent in application state only. Two
things therefore cross over, both because they say how the interpreter is loaded and found
rather than what the application believes:

* The loader variables. The Linux CI legs run on a self-hosted runner, where
  `actions/setup-python` installs a **shared-linked** arm64 CPython into the runner's
  tool cache (`<runner-work>/_tool/Python/<version>/arm64`): `ldd` on that binary reports
  `libpython3.13.so.1.0 => not found` unless `LD_LIBRARY_PATH` names the sibling `lib/`, and
  the action exports the variable into the *job* environment. So the pytest parent starts
  fine and only a child built from scratch dies — exit 127, `error while loading shared
  libraries`, measured on the box. A hosted runner cannot show this class of failure: its
  CPython build carries an rpath, so the same from-scratch environment execs cleanly there.
* A package root — but only as `python_path_for()` below derives it from the parent's own
  imports, never copied from the host's `PYTHONPATH`.

Everything that really is host state (`EPHE_*`, locale, a foreign import path) stays out,
which is why these tests build a minimal environment in the first place. `os.environ.copy()`
would fix the 127 and re-open that leak: the worse defect.

`env_without_tools()` below takes the opposite posture on purpose, for the tests that need the
host's application state (a real server child reading its config dir) and only one tool out of
reach.
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path

#: Dynamic-loader variables: ELF on Linux, Mach-O (dyld) on macOS.
LOADER_KEYS = ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH")


def hermetic_env(**overrides: str) -> dict[str, str]:
    """A subprocess environment holding the loader keys plus exactly what `overrides` names.

    Callers name the keys they mean to control — `PATH`, `HOME`, `PYTHONPATH`, the
    `EPHE_*` switch under test — and nothing else reaches the child. A loader key
    copied from the host is overridable, so a test can pin its own loader view.
    """
    env = {key: value for key in LOADER_KEYS if (value := os.environ.get(key)) is not None}
    env.update(overrides)
    return env


def env_without_tools(*tools: str) -> dict[str, str]:
    """This run's environment with every PATH entry that ships `tools` removed.

    For a child that must reach a documented "tool not found" branch instead of running the
    tool. Removing the directory is what makes that deterministic: a PATH stub earlier in the
    path still lets the child find the real binary through a name the test did not think of.

    Two builds this stopped, both measured:
    * `ephe desktop` with the unfiltered environment ran a real `npm run tauri build` out of a
      unit test — 24 s, it rebuilt `app/dist`, bundled `Ephe.app`, installed it into
      `/Applications` and started the backend.
    * `ephe start` reaches `ensure_pwa_built()`, which since 2026-10-09 calls **pnpm** (not
      npm): a child whose PATH only lacked `npm` still did a real `pnpm install` in `app/` and
      created `app/node_modules` in the CI checkout — three legs of run 38046942987 died on
      another test's teardown witness for it.
    """
    entries = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    clean = [
        entry
        for entry in entries
        if not any((Path(entry) / f"{tool}{suffix}").exists()
                   for tool in tools for suffix in ("", ".exe"))
    ]
    return {**os.environ, "PATH": os.pathsep.join(clean)}


def python_path_for(*modules: str) -> str:
    """The `PYTHONPATH` value that lets a child import `modules` the way this process can.

    Derived from the imports themselves (`module.__file__`) and never copied from
    `os.environ` or hard-coded, so it is the real root whatever the layout is: a venv, a
    `site-packages`, or a Debian-style `dist-packages`.

    WHY this belongs in a scrubbed environment: the child must not see a different package
    offer than the interpreter it runs. If it does, the test measures the machine instead of
    the switch it pins. Measured on the py3.12 leg of run 37954384269 — that tool-cache
    `python` does not list its own `lib/python3.12/site-packages` in `sys.path` at all
    (`site.getsitepackages()` names three Debian-style `dist-packages` roots that do not
    exist there, while pip installed the packages into `site-packages`), so a child without
    this entry answered `No module named pytest` while the parent had just run 3499 tests.
    Same reason the loader keys pass through: not application state, but how the interpreter
    and its packages are found.
    """
    roots: list[str] = []
    for name in modules:
        module = importlib.import_module(name)
        module_file = getattr(module, "__file__", None)
        if module_file is None:
            continue  # a frozen or namespace module has no file to derive a root from
        # A package lives in <root>/pkg/__init__.py, a module in <root>/pkg.py: one level
        # apart, so the package keeps its own name as a step and the module file does not.
        steps = len(name.split(".")) + (0 if hasattr(module, "__path__") else -1)
        root = str(Path(module_file).resolve().parents[steps])
        if root not in roots:
            roots.append(root)
    return os.pathsep.join(roots)
