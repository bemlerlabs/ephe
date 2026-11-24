"""The worker's 0.0 % is a design statement, and this file is the fence holding it.

`core/sandbox/worker_launcher.py` runs in a child started with `child_env()`, whose allow-list
(`core/secret_broker.py:_CHILD_ENV_NAMES`) hands a child `PATH`, `HOME`, `USER`, `LOGNAME`, `SHELL`,
`PWD`, `TMPDIR`, `TEMP`, `TMP`, `LANG`, `LANGUAGE` and `LC_*` and nothing else. No coverage key is on
that list, so a worker started while the parent is traced loads no `sitecustomize`, writes no data
file and stays at the 0.0 % `docs/COVERAGE_GAPS.md` records for it. Tracing that child would mean
adding the instrument's keys to a list whose whole purpose is to keep a host variable out of a plugin
or sandbox child, which is a product-code decision; nothing here asks for one. What these tests hold
is that the trace cannot arrive by inheritance.

The allow-list is asserted beside the behaviour because a normal suite run starts with no coverage key
in its parent environment, where a purely behavioural test would pass with the guard already gone.
"""

from __future__ import annotations

from core import secret_broker
from core.secret_broker import child_env

# The three names coverage.py uses to reach a subprocess: the hook loader, the start-up config and
# the data file. A fourth route is a `.pth` file in a directory PYTHONPATH points at.
COVERAGE_KEYS = ("PYTHONPATH", "COVERAGE_PROCESS_START", "COVERAGE_FILE")


class TestChildEnvCarriesNoTrace:
    def test_a_traced_parent_hands_the_child_no_instrument(self, monkeypatch):
        monkeypatch.setenv("PYTHONPATH", "/opt/coverthook:/opt/site-packages")
        monkeypatch.setenv("COVERAGE_PROCESS_START", "/tmp/covrc/.coveragerc")
        monkeypatch.setenv("COVERAGE_FILE", "/tmp/covdata/.coverage")
        monkeypatch.setenv("COVERAGE_XML", "1")

        env = child_env()

        inherited = sorted(set(COVERAGE_KEYS) & set(env))
        assert inherited == [], f"coverage keys inherited by the child: {inherited}"
        # A renamed key carrying the same value is the same leak.
        planted = ("/opt/coverthook", "/tmp/covrc/.coveragerc", "/tmp/covdata/.coverage")
        leaked = sorted(
            f"{name}={value}"
            for name, value in env.items()
            if any(needle in value for needle in planted)
        )
        assert leaked == [], f"child env carries a planted instrument value: {leaked}"

    def test_a_directory_holding_a_pth_file_reaches_neither_key_nor_path(self, tmp_path, monkeypatch):
        hook_dir = tmp_path / "site-packages"
        hook_dir.mkdir()
        (hook_dir / "coverage.pth").write_text(
            "import coverage; coverage.process_startup()\n", encoding="utf-8"
        )
        monkeypatch.setenv("PYTHONPATH", str(hook_dir))

        env = child_env()

        assert "PYTHONPATH" not in env, "the child inherits PYTHONPATH, so a .pth hook would load"
        joined = "\n".join(env.values())
        assert str(hook_dir) not in joined
        assert ".pth" not in joined

    def test_the_allow_list_admits_no_instrument_key_by_name_or_prefix(self):
        names = {str(name).upper() for name in secret_broker._CHILD_ENV_NAMES}
        prefixes = tuple(str(prefix).upper() for prefix in secret_broker._CHILD_ENV_PREFIXES)
        banned = {*COVERAGE_KEYS, "COVERAGE_XML", "COVERAGE_HTML", "COVERAGE_PROCESS_CONFIG"}

        admitted = sorted(names & banned)
        assert admitted == [], f"instrument keys on the child allow-list: {admitted}"
        swallowed = sorted(
            name for name in banned if any(name.startswith(prefix) for prefix in prefixes)
        )
        assert swallowed == [], f"an allow-list prefix admits an instrument key: {swallowed}"

    def test_extra_stays_the_one_way_such_a_key_reaches_a_child(self):
        """`extra` is the trusted path, named by the code that owns the connector."""
        env = child_env({"COVERAGE_PROCESS_START": "/tmp/covrc/.coveragerc"})

        assert env["COVERAGE_PROCESS_START"] == "/tmp/covrc/.coveragerc"
