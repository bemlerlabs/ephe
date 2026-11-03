"""F1 contract: ephemerality has to be shown by the device folder, not promised by the copy.

The product says Ephe forgets. The cell runtime is the one place where such a claim is
already an artifact: `core/cpython_cell.py:62-64` writes the WASIConfig from its own
`DEFAULT_MAX_FUEL` / `DEFAULT_MAX_MEMORY_MB` / `DEFAULT_TIMEOUT_SECONDS`, and
`core/cell_policy.policy_snapshot()` reports exactly those numbers to the settings card,
`ephe doctor` and the status page under one rule, report == enforced, fenced to the single
release whose enforcement was read (`.github/cell-runtime-fence.json`, ephemora-cell
1.0.4.3, wheel_sha256 556e9fca…). Nothing in Ephe applies that same rule to what a session
leaves on disk.

Measured on the owner's Mac — first on 2026-10-11, re-read on 2026-11-03 wherever a step of
this wave has landed. These are the numbers the contract carries:

* 50 entries live in the device folder and 21 of them answer to no config-root expression
  the code carries.
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

These tests are the contract. One row is still marked `xfail(strict=True)`, and the
folder-count row keeps its non-strict mark: they must not be weakened to pass, and once the
product satisfies one, the run turns red at XPASS and the mark has to come off. Widening the
declared set here would be the same error as an unenforced cap — a claim that grades itself.

Sources: `docs/EPHEMERAL_PROOF_2026-10-11.md`.
"""
from __future__ import annotations

import ast
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

MEASURED_UNDECLARED = 21


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
                found.add(match.group(1).split("/")[0])
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


@pytest.mark.xfail(strict=True, reason=(
    f"no declaration exists to check a session against: the product publishes cell caps "
    f"through policy_snapshot() but nothing that names what persists per device, so the "
    f"only available declared set has to be reverse-engineered from {len(declared_names())} "
    f"code expressions. F1 owes the product a machine-readable manifest the settings card, "
    f"doctor and status page can render, the way the caps are rendered"))
def test_a_persistence_declaration_exists():
    manifest = [path for path in product_files()
                if any(isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name)
                               and target.id in {"PERSISTED_PATHS", "EPHE_PERSISTENCE"}
                               for target in node.targets)
                       for node in ast.walk(ast.parse(path.read_text(errors="ignore"))))]
    assert manifest, "the device folder has no declared set the product itself publishes"


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
    f"names. Measured on the owner's device folder on 2026-11-03: {MEASURED_UNDECLARED} of 50 "
    f"top-level entries are outside every set the code can name — some written by product "
    f"code through an expression shape this scan does not read, some left behind by build "
    f"agents and manual backups. Until the folder can be listed from a declaration and emptied "
    f"by a delete, the product's ephemerality claim is a sentence"))
def test_the_device_folder_holds_nothing_unnamed():
    root = device_folder()
    if root is None:
        pytest.skip(f"no device folder on this host; the measured count is "
                    f"{MEASURED_UNDECLARED} on the owner's Mac")
    declared = declared_names()
    entries = sorted(name for name in os.listdir(root) if not name.startswith("."))
    unknown = [name for name in entries if name not in declared]
    assert not unknown, (f"{len(unknown)} of {len(entries)} entries in {root} are unnamed "
                         f"by the code: {unknown}")
