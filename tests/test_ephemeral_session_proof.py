"""F1 contract: ephemerality has to be shown by the device folder, not promised by the copy.

The product says Ephe forgets. The cell runtime is the one place where such a claim is
already an artifact: `core/cpython_cell.py:62-64` writes the WASIConfig from its own
`DEFAULT_MAX_FUEL` / `DEFAULT_MAX_MEMORY_MB` / `DEFAULT_TIMEOUT_SECONDS`, and
`core/cell_policy.policy_snapshot()` reports exactly those numbers to the settings card,
`ephe doctor` and the status page under one rule, report == enforced, fenced to the single
release whose enforcement was read (`.github/cell-runtime-fence.json`, ephemora-cell
1.0.4.3, wheel_sha256 556e9fca…). Nothing in Ephe applied that same rule to what a session
leaves on disk until this wave wrote `core/persistence.py`; these tests are what made the
gap measurable.

Measured on the owner's Mac — first on 2026-10-11, re-read on 2026-11-03 wherever a step of
this wave has landed. These are the numbers the contract carries:

* **The device keeps a declaration**: `core/persistence.py` carries 57 rows, each naming the
  code that writes it, and `ephe doctor` renders them as one row. Measured on the owner's
  folder, 44 of the 57 are present and 6 entries answer to nobody — five config and key
  backups a hand kept and one private signing key. Retention in `core/store_retention.py`
  is cross-checked against the same list, so the two cannot drift.
* **The state accessors honour the device root** (`ACCESSORS`, ten of them). Seven of the
  ten resolved into the real home when this contract was first written — `core/session.py`,
  `core/usage_ledger.py`, `core/feedback.py`, `core/vision_memory.py`, `core/profile.py`,
  `core/session_search.py`, `core/persona.py` — and were moved onto `config_root()` /
  `config_subdir()`; `core/audit_log.py` now shares that root instead of carrying a private
  reading of the same env name. The tenth slot names `core.memory_provider`, because the
  `DEFAULT_CHROMA_PATH` it used to check left the tree with the vector client.
* 25 sites held their own copy of the root's rule — read `EPHE_CONFIG_DIR`, otherwise
  `~/.ephe` — and are folded onto `config_root()` / `config_subdir()`. Two expressions that
  spell the folder out of the home directory remain, both in `core/engine_config.py`, which
  is where the root is defined; the scan reads the expression tree, so a docstring that
  names the literal is no longer counted as a path.
* `evals/bench_option_b.py` sets no `EPHE_CONFIG_DIR` (its own root is `SCRATCH`,
  `:75`), so bench reps read and append the owner's real memory store.

These tests are the contract. Every row passes except the folder-count one, which keeps a
non-strict mark because a runner whose device folder is clean would otherwise read a passing
walk as a red. The strict marks came off as the product satisfied each row, which is what a
strict mark exists to force. Widening the declared set here would be the same error as an
unenforced cap — a claim that grades itself.

Sources: `docs/EPHEMERAL_PROOF_2026-10-11.md`.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))
from subprocess_env import hermetic_env  # noqa: E402

#: Expressions that resolve through the device root, which `core/engine_config.py:243`
#: lets `EPHE_CONFIG_DIR` move. A state file reached any other way escapes the folder the
#: user is told about, and a per-device reset cannot remove it.
ROOT_PATTERNS = [
    re.compile(r'config_subdir\(\s*"([^"/]+)"'),
    re.compile(r'CONFIG_DIR\s*/\s*"([^"/]+)"'),
    re.compile(r'config_root\(\)\s*/\s*"([^"/]+)"'),
    re.compile(r'"\.ephe"\s*/\s*"([^"/]+)"'),
    re.compile(r'\.ephe/([A-Za-z0-9_.-]+)'),
]

#: State the product keeps per device, as the modules themselves name it.
#: `core.vision_memory` held this list's tenth entry as `DEFAULT_CHROMA_PATH` until the
#: vector client was retired (its own docstring records the removal); the rules it stores
#: now travel through `core.memory_provider`, which names the file the provider reads and
#: writes next to them, so the slot moved to a name that exists and covers one more module.
ACCESSORS = [
    ("core.engine_config", "config_root"),
    ("core.settings_schema", "settings_path"),
    ("core.trajectory", "_path"),
    ("core.session", "SESSION_DIR"),
    ("core.usage_ledger", "default_store"),
    ("core.session_search", "_db_path"),
    ("core.persona", "_persona_dir"),
    ("core.feedback", "DEFAULT_BASE_DIR"),
    ("core.profile", "DEFAULT_PROFILE_PATH"),
    ("core.memory_provider", "provider_record_path"),
]

MEASURED_UNDECLARED = 6


#: The one file allowed to spell the device folder out of the home directory: it is where
#: `config_root()` is defined, so the expression has to live there.
ROOT_DEFINITION_FILE = "core/engine_config.py"


def product_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "core", "server", "ephe_cli.py"],
                         cwd=str(REPO), capture_output=True, text=True).stdout.split()
    files = [REPO / name for name in out if name.endswith(".py")]
    # A tracked file can be deleted in the working tree before the deletion lands;
    # reading it would abort collection, so the tree's real state is what counts.
    return [path for path in files if path.is_file()]


def _is_home_ephe(node: ast.AST) -> bool:
    """True for the expression `Path.home() / ".ephe"`, and nothing else."""
    if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)):
        return False
    right = node.right
    if not (isinstance(right, ast.Constant) and right.value == ".ephe"):
        return False
    left = node.left
    return (
        isinstance(left, ast.Call)
        and isinstance(left.func, ast.Attribute)
        and left.func.attr == "home"
        and isinstance(left.func.value, ast.Name)
        and left.func.value.id == "Path"
        and not left.args
    )


def device_root_expressions() -> list[str]:
    """Every place the code builds the device folder beside the root, read off the tree.

    The scan used to read lines, which counted a docstring that merely names the expression
    and missed an expression wrapped across two lines. The tree is what the interpreter runs:
    a string in prose is not a path, and a path in prose would be found nowhere else.
    """
    sites: list[str] = []
    unparsed: list[str] = []
    for path in product_files():
        rel = path.relative_to(REPO).as_posix()
        try:
            tree = ast.parse(path.read_text(errors="ignore"))
        except SyntaxError:
            unparsed.append(rel)  # a product file the interpreter itself could not read
            continue
        for node in ast.walk(tree):
            if _is_home_ephe(node):
                sites.append(f"{rel}:{node.lineno}")
    return sorted(sites) + [f"{rel}:0 (unparseable)" for rel in sorted(unparsed)]


def root_expressions_outside_the_definition() -> list[str]:
    """The device folder built anywhere other than the file that defines the root."""
    return [site for site in device_root_expressions()
            if not site.startswith(ROOT_DEFINITION_FILE + ":")]


def declared_names() -> set[str]:
    """The top-level names the code can reach through the device root."""
    found: set[str] = set()
    for path in product_files():
        for pattern in ROOT_PATTERNS:
            for match in pattern.finditer(path.read_text(errors="ignore")):
                # `~/.ephe/engine.json.` at the end of a sentence names the file, and the
                # period belongs to the prose: the character class runs over both.
                name = match.group(1).split("/")[0].rstrip(".")
                found.add(name)
    return {name for name in found if name}


def resolve_in_child(temp_home: Path) -> dict[str, str]:
    """Ask a fresh interpreter where each state file lives, without letting it write."""
    script = (
        "import importlib, json, sys\n"
        "from pathlib import Path\n"
        "out = {}\n"
        f"for mod, attr in {ACCESSORS!r}:\n"
        "    try:\n"
        "        value = getattr(importlib.import_module(mod), attr)\n"
        "        out[f'{mod}.{attr}'] = str(value() if callable(value) else value)\n"
        "    except Exception as exc:\n"
        "        out['import-fail ' + mod] = type(exc).__name__\n"
        "print(json.dumps(out))\n"
    )
    # HOME stays the host's: the escape lands in the real home, which a redirected HOME would hide.
    env = hermetic_env(PATH=os.environ.get("PATH", ""),
                      EPHE_CONFIG_DIR=str(temp_home),
                      PYTHONPATH=str(REPO), PYTHONDONTWRITEBYTECODE="1")
    proc = subprocess.run([sys.executable, "-c", script], cwd=str(REPO), env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, f"the child could not answer: {proc.stderr[:400]}"
    return __import__("json").loads(proc.stdout.strip().splitlines()[-1])


def device_folder() -> Path | None:
    """The real device folder when this machine has one, so the count is a measurement."""
    configured = os.environ.get("EPHE_HOME_INSPECT")
    root = Path(configured) if configured else Path.home() / ".ephe"
    return root if root.is_dir() else None


def test_a_persistence_declaration_exists():
    """The declaration the contract asked for, found where the product keeps it.

    `core/persistence.py` carries it, and `ephe doctor` renders it as a row, so the numbers
    a person reads about their own disk come from the code that writes that disk.
    """
    def assigned_names(node: ast.AST) -> set[str]:
        """The names a binding gives a value, whether or not the target carries a type."""
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            return set()
        return {t.id for t in targets if isinstance(t, ast.Name)}

    manifest = [
        path for path in product_files()
        if {"PERSISTED_PATHS", "EPHE_PERSISTENCE"} & {
            name
            for node in ast.walk(ast.parse(path.read_text(errors="ignore")))
            for name in assigned_names(node)
        }
    ]
    assert manifest, "the device folder has no declared set the product itself publishes"


def test_every_declared_entry_names_code_that_is_in_the_tree():
    """A row with no writer is a claim, so the writer is checked to exist.

    The path in `writer` is the file that resolves the entry; `app/src-tauri/src/instance.rs`
    is the one row whose writer is the desktop shell, which is honest about a socket Python
    never opens.
    """
    from core.persistence import EPHE_PERSISTENCE

    missing = []
    for entry in EPHE_PERSISTENCE:
        if entry.kind not in {"dir", "file", "socket"}:
            missing.append(f"{entry.name}: kind {entry.kind!r}")
        elif not entry.holds or not entry.writer:
            missing.append(f"{entry.name}: an empty field")
        elif not (REPO / entry.writer).exists():
            missing.append(f"{entry.name}: no such writer {entry.writer}")
    assert not missing, f"{len(missing)} declaration rows are unsupported: {missing}"
    names = [entry.name for entry in EPHE_PERSISTENCE]
    assert len(set(names)) == len(names), "one name declared twice resolves to one path"


def test_the_code_declares_nothing_the_manifest_does_not_cover():
    """The reverse-engineered set and the written one have to answer the same question.

    Names come from prose about a *project's* own `.ephe` folder — a workspace keeps its
    search index, its rules and its context overlays beside itself, and the scan reads a
    mention of `.ephe/<name>` the same way it reads a `config_root() / <name>` expression.
    They are excluded here with their reason rather than by teaching the scan to guess
    which sentence is a path.
    """
    from core.persistence import declared_names as manifest_names

    # The other workspace-local names are the context overlays a project may keep beside
    # itself (`core/workspace_rules.py`): they live in the user's workspace, never in the
    # device folder this declaration describes.
    workspace_local = {"index.db", "rules", "user.md", "persona.md"}
    scanned = declared_names() - workspace_local
    undeclared = sorted(scanned - set(manifest_names()))
    assert not undeclared, f"{len(undeclared)} names the code reaches are undeclared: {undeclared}"


def test_the_retention_verdicts_answer_to_the_declaration():
    """`core/store_retention.py` decides how long a store lives; it may not invent one.

    Retention and persistence are two questions about the same folder, and a store that
    only one of them knows about is a folder someone will prune, or forget, by accident.
    """
    from core import store_retention
    from core.persistence import declared_names

    relatives = {store.relative.split("/")[0] for store in store_retention.STORES}
    unexplained = sorted(relatives - set(declared_names()))
    assert not unexplained, f"retention walks stores nobody declared: {unexplained}"


def test_the_doctor_row_reads_the_declaration(tmp_path, monkeypatch):
    """One line, three numbers and the names of whatever does not belong.

    The row is measured against a folder the test builds, so the counts are the module's
    arithmetic over a known ground rather than a photograph of the owner's disk.
    """
    import ephe_cli
    from core.persistence import EPHE_PERSISTENCE

    device = tmp_path / "ephe"
    (device / "sessions").mkdir(parents=True)
    (device / "settings.json").write_text("{}\n", encoding="utf-8")
    # One hand the declaration cannot name, and one leftover the doctor recognises:
    # the unknown gets named on the row, the recognised is counted toward the repair.
    (device / "handwritten.txt").write_text("x\n", encoding="utf-8")
    (device / "engine.json.bak-2").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(device))

    line = ephe_cli._doctor_device_state()
    assert str(device) in line
    assert f"{len(EPHE_PERSISTENCE)} declared, 2 present" in line
    assert "1 unnamed (handwritten.txt)" in line
    assert "1 stale" in line

    # A device that never ran anything still gets a line, and it says nothing about leftovers.
    quiet = tmp_path / "quiet"
    quiet.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(quiet))
    assert "unnamed" not in ephe_cli._doctor_device_state()


def test_a_long_unnamed_list_is_counted_and_cut(tmp_path, monkeypatch):
    """Five leftovers read as three names and a count, because the row is one line."""
    import ephe_cli

    device = tmp_path / "ephe"
    device.mkdir()
    for index in range(5):
        (device / f"leftover-{index}").write_text("", encoding="utf-8")
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(device))

    line = ephe_cli._doctor_device_state()
    assert "5 unnamed (leftover-0, leftover-1, leftover-2, +2 more)" in line


def test_the_recorded_checkout_answers_with_the_version_inside_it(tmp_path, monkeypatch):
    """A folder's name is a label; the number comes from the manifest sitting in that folder.

    The shape is the one measured on the machine that ships Ephe on 2026-11-03: a checkout
    named after the release that first provisioned it, holding a tree whose manifest has
    moved on since. The read answers with what the tree reports.
    """
    from core.persistence import installed_checkout

    device = tmp_path / "ephe"
    device.mkdir()
    checkout = tmp_path / "0.1.4"
    checkout.mkdir()
    (checkout / "pyproject.toml").write_text('[project]\nversion = "9.9.9"\n', encoding="utf-8")
    (device / "desktop.json").write_text(
        json.dumps({"project_root": str(checkout)}), encoding="utf-8"
    )
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(device))

    state = installed_checkout()
    assert state["root"] == str(checkout)
    assert state["present"] is True
    assert state["version"] == "9.9.9"
    assert state["unreadable"] == ""


def test_a_recorded_checkout_that_is_gone_says_so(tmp_path, monkeypatch):
    """The record may name a folder that no longer exists, and then no version is knowable."""
    from core.persistence import installed_checkout

    device = tmp_path / "ephe"
    device.mkdir()
    (device / "desktop.json").write_text(
        json.dumps({"project_root": str(tmp_path / "removed")}), encoding="utf-8"
    )
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(device))

    state = installed_checkout()
    assert state["root"] == str(tmp_path / "removed")
    assert state["present"] is False
    assert state["version"] == ""
    assert state["unreadable"] == "is not a folder on this machine"


def test_a_checkout_whose_manifest_answers_nothing_is_read_as_a_failed_read(tmp_path, monkeypatch):
    """A folder that is there and reports nothing stays a failure the surface has to show.

    An unparsable manifest is the same answer as a missing one, and neither may come back as
    an empty version a reader would take for a machine that is up to date.
    """
    from core.persistence import installed_checkout

    device = tmp_path / "ephe"
    device.mkdir()
    checkout = tmp_path / "current"
    checkout.mkdir()
    (checkout / "pyproject.toml").write_text("[project\nversion =", encoding="utf-8")
    (device / "desktop.json").write_text(
        json.dumps({"project_root": str(checkout)}), encoding="utf-8"
    )
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(device))

    state = installed_checkout()
    assert state["present"] is True
    assert state["version"] == ""
    assert state["unreadable"] == "reports no version for itself"


def test_a_record_that_names_no_checkout_is_refused_in_either_shape(tmp_path, monkeypatch):
    """A record with no `project_root` answers nothing, whether it is an object or a list."""
    from core.persistence import installed_checkout

    device = tmp_path / "ephe"
    device.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(device))
    record = device / "desktop.json"
    for payload in ({}, ["project_root"]):
        record.write_text(json.dumps(payload), encoding="utf-8")
        state = installed_checkout()
        assert state["root"] == ""
        assert state["unreadable"] == "names no project_root"


def test_a_record_that_is_not_json_names_the_read_that_failed(tmp_path, monkeypatch):
    """A torn file is a failed read with the reader's own reason attached."""
    from core.persistence import installed_checkout

    device = tmp_path / "ephe"
    device.mkdir()
    (device / "desktop.json").write_text("{ project_root ", encoding="utf-8")
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(device))

    state = installed_checkout()
    assert state["record"] == str(device / "desktop.json")
    assert state["unreadable"].startswith("could not be read (")


def test_the_checkout_row_prints_the_path_next_to_the_version(tmp_path, monkeypatch):
    """One line, two facts: where this install reads from, and what that place reports."""
    import ephe_cli

    device = tmp_path / "ephe"
    device.mkdir()
    checkout = tmp_path / "0.1.4"
    checkout.mkdir()
    (checkout / "pyproject.toml").write_text('[project]\nversion = "9.9.9"\n', encoding="utf-8")
    (device / "desktop.json").write_text(
        json.dumps({"project_root": str(checkout)}), encoding="utf-8"
    )
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(device))

    assert ephe_cli._doctor_installed_checkout() == f"{checkout} — reports 9.9.9"


def test_the_checkout_row_names_the_record_it_could_not_read(tmp_path, monkeypatch):
    """An empty device folder gets the sentence about the record that is missing.

    The row is the instrument for a question about the machine, so a machine it cannot read
    is answered with the path it looked at and the read that came back empty.
    """
    import ephe_cli

    device = tmp_path / "ephe"
    device.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(device))

    line = ephe_cli._doctor_installed_checkout()
    assert str(device / "desktop.json") in line
    assert "holds no record" in line


def test_a_temp_device_root_captures_every_state_writer(tmp_path):
    """The writer half of the contract, green since 2026-11-03.

    Ten accessors are asked, in a fresh interpreter whose `EPHE_CONFIG_DIR` points at an
    empty folder while `HOME` stays the host's. A redirected `HOME` would hide the escape,
    so the test keeps the home real and watches where each module puts its file: any answer
    outside the declared root is a second writer into the owner's folder, and a run that
    promises ephemerality while doing that is the claim this file exists to refuse.
    """
    home = tmp_path / "home"
    home.mkdir()
    resolved = resolve_in_child(home)
    outside = {name: value for name, value in resolved.items()
               if not value.startswith(str(home.resolve()) + os.sep) and value != str(home.resolve())}
    assert not outside, f"{len(outside)} state paths escape the root: {outside}"


def test_state_paths_reach_the_device_folder_only_through_the_root():
    """One file may spell the folder out of the home directory: the one that defines it.

    Twenty-five sites re-implemented the root's own rule — read `EPHE_CONFIG_DIR`,
    otherwise `~/.ephe` — as an expression of their own. Each agreed with `config_root()`
    on the day it was written and owed that agreement to nobody afterwards, so a change to
    the rule would have landed in one place out of twenty-six while the other twenty-five
    kept answering for the old one. Every state path now comes from `config_root()` or
    `config_subdir()`, and the scan reads the expression tree, which is what the
    interpreter runs: prose that names the literal is a sentence, and a path built across
    two lines is a path.
    """
    offenders = root_expressions_outside_the_definition()
    assert not offenders, f"{len(offenders)} sites build the device folder beside the root: {offenders}"


@pytest.mark.xfail(strict=False, reason=(
    "not strict: a CI runner whose device folder is clean would turn a passing walk into a "
    "false red, and this test exists to report a count. Run it with --runxfail to see the "
    f"names. Measured on the owner's device folder on 2026-11-03: {MEASURED_UNDECLARED} entries "
    f"answer to no row in `core.persistence.EPHE_PERSISTENCE` — five engine-config and key "
    f"backups a hand kept, and one private signing key. Those are the entries a person should "
    f"be able to list from the declaration and clear with one word, which is the fourth step "
    f"of this wave; until that verb exists the product's ephemerality claim is a sentence"))
def test_the_device_folder_holds_nothing_unnamed():
    """The folder read against the declaration it is supposed to match.

    The scan in `declared_names()` answers what the code can reach; this answers what the
    product says it keeps. The two agree by `test_the_code_declares_nothing_the_manifest_does_not_cover`,
    so a leftover named here is a leftover nobody declared.
    """
    from core.persistence import declared_names as manifest_names

    root = device_folder()
    if root is None:
        pytest.skip(f"no device folder on this host; the measured count is "
                    f"{MEASURED_UNDECLARED} on the owner's Mac")
    declared = set(manifest_names())
    entries = sorted(name for name in os.listdir(root) if not name.startswith("."))
    unknown = [name for name in entries if name not in declared]
    assert not unknown, (f"{len(unknown)} of {len(entries)} entries in {root} are unnamed "
                         f"by the declaration: {unknown}")
