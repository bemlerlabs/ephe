"""One TOML reader for every Python this project supports.

`tomllib` is stdlib only from 3.11, while `requires-python` says `>=3.10` and
`setup.sh` still probes 3.10 — so five test modules used to fail CI's 3.10 job
during collection with `ModuleNotFoundError: No module named 'tomllib'`, and the
product's own reader degrades instead of importing it
(`core/environment_mirror.py:85`).

`tomli` is the stdlib backport with the same API. It is declared in the **main
dependencies** under a `python_version < "3.11"` marker (2026-10-09): the product
reader `core/environment_mirror.py` needs it too, and an optional dev-only backport
left every TOML tool config unread on 3.10. Nothing installs it on 3.11+.
"""
from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # only reachable on Python 3.10

__all__ = ["tomllib"]
