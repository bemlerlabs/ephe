"""F1 contract: ephemerality has to be shown by the device folder, not promised by the copy.

The product says Ephe forgets. The cell runtime is the one place where such a claim is
already an artifact: `core/cpython_cell.py:62-64` writes the WASIConfig from its own
`DEFAULT_MAX_FUEL` / `DEFAULT_MAX_MEMORY_MB` / `DEFAULT_TIMEOUT_SECONDS`, and
`core/cell_policy.policy_snapshot()` reports exactly those numbers to the settings card,
`ephe doctor` and the status page under one rule, report == enforced, fenced to the single
release whose enforcement was read (`.github/cell-runtime-fence.json`, ephemora-cell
1.0.4.3, wheel_sha256 556e9fca…). Nothing in Ephe applies that same rule to what a session
leaves on disk.

Measured on the owner's Mac on 2026-10-11, which is the number this contract carries:

* 46 entries live in the device folder, 36 of them nameable through a config-root
  expression; **19 are not** — 5 written by product code through another expression shape
  (`settings.json`, `desktop.json`, `plugins.json`, `skills_state.json`,
  `ephe-desktop.sock`) and 14 that no product code writes at all.
* **7 of 10 state accessors still resolve into the real home when `EPHE_CONFIG_DIR` points
  somewhere else**: `core/session.py:25`, `core/usage_ledger.py:28`, `core/feedback.py:24`,
  `core/vision_memory.py:14`, `core/profile.py:20`, `core/session_search.py:44`,
  `core/persona.py:108`. `core/audit_log.py:32` is an eighth that honours only its own
  `EPHE_AUDIT_LOG`.
* 42 `Path.home() / ".ephe"` literals exist in `core/`, `server/` and `ephe_cli.py`, and
  23 of them carry no env fallback at all.
* `evals/bench_option_b.py` sets no `EPHE_CONFIG_DIR` (its own root is `SCRATCH`,
  `:75`), so bench reps read and append the owner's real memory store.

These tests are the contract. They are marked `xfail(strict=True)`: they must not be
weakened to pass, and once the product satisfies one, the run turns red at XPASS and the
mark has to come off. Widening the declared set here would be the same error as an
unenforced cap — a claim that grades itself.

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
ACCESSORS = [
    ("core.engine_config", "config_root"),
    ("core.settings_schema", "settings_path"),
    ("core.trajectory", "_path"),
    ("core.session", "SESSION_DIR"),
    ("core.usage_ledger", "default_store"),
    ("core.session_search", "_db_path"),
    ("core.persona", "_persona_dir"),
    ("core.feedback", "DEFAULT_BASE_DIR"),
    ("core.vision_memory", "DEFAULT_CHROMA_PATH"),
    ("core.profile", "DEFAULT_PROFILE_PATH"),
]

MEASURED_UNDECLARED = 19
MEASURED_OUTSIDE_ROOT = 7


def product_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "core", "server", "ephe_cli.py"],
                         cwd=str(REPO), capture_output=True, text=True).stdout.split()
    files = [REPO / name for name in out if name.endswith(".py")]
    # A tracked file can be deleted in the working tree before the deletion lands;
    # reading it would abort collection, so the tree's real state is what counts.
    return [path for path in files if path.is_file()]


def declared_names() -> set[str]:
    """The top-level names the code can reach through the device root."""
    found: set[str] = set()
    for path in product_files():
        for pattern in ROOT_PATTERNS:
            for match in pattern.finditer(path.read_text(errors="ignore")):
                found.add(match.group(1).split("/")[0])
    return {name for name in found if name}


def all_home_literals() -> list[str]:
    """Every `Path.home() / ".ephe"` site in the product, whatever it does with the root."""
    sites: list[str] = []
    for path in product_files():
        rel = path.relative_to(REPO).as_posix()
        for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            if 'Path.home() / ".ephe"' in line:
                sites.append(f"{rel}:{number}")
    return sorted(sites)


def home_literals_bypassing_the_root() -> list[str]:
    """`Path.home() / ".ephe"` uses that are not the fallback half of an env read."""
    offenders: list[str] = []
    for path in product_files():
        rel = path.relative_to(REPO).as_posix()
        for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            if 'Path.home() / ".ephe"' not in line:
                continue
            if "EPHE_CONFIG_DIR" in line or "EPHE_AUDIT_LOG" in line or "EPHE_IMAGE_DIR" in line \
                    or "EPHE_PERSONA_DIR" in line:
                continue
            offenders.append(f"{rel}:{number}")
    return sorted(offenders)


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


@pytest.mark.xfail(strict=True, reason=(
    f"state writers ignore the device root: {MEASURED_OUTSIDE_ROOT} of {len(ACCESSORS)} "
    f"accessors resolve into the real home under a temp EPHE_CONFIG_DIR "
    f"(core/session.py:25, core/usage_ledger.py:28, core/feedback.py:24, "
    f"core/vision_memory.py:14, core/profile.py:20, core/session_search.py:44, "
    f"core/persona.py:108; core/audit_log.py:32 honours only EPHE_AUDIT_LOG). A run that "
    f"sets EPHE_CONFIG_DIR somewhere else is therefore not ephemeral, it is a second writer "
    f"into the owner's folder"))
def test_a_temp_device_root_captures_every_state_writer(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    resolved = resolve_in_child(home)
    outside = {name: value for name, value in resolved.items()
               if not value.startswith(str(home.resolve()) + os.sep) and value != str(home.resolve())}
    assert not outside, f"{len(outside)} state paths escape the root: {outside}"


@pytest.mark.xfail(strict=True, reason=(
    f"{len(all_home_literals())} literals reach the device folder and "
    f"{len(home_literals_bypassing_the_root())} of them do it without an env fallback; the "
    f"scan prints the file:line pairs, so the fix is a list rather than a hunt"))
def test_state_paths_reach_the_device_folder_only_through_the_root():
    offenders = home_literals_bypassing_the_root()
    assert not offenders, f"{len(offenders)} sites build an .ephe path with no env fallback"


@pytest.mark.xfail(strict=False, reason=(
    "not strict: a CI runner whose device folder is clean would turn a passing walk into a "
    "false red, and this test exists to report a count. Run it with --runxfail to see the "
    f"names. Measured on the owner's device folder on 2026-10-11: {MEASURED_UNDECLARED} of 46 "
    f"top-level entries are outside every set the code can name — 5 written by product code "
    f"(settings.json, desktop.json, plugins.json, skills_state.json, ephe-desktop.sock) and "
    f"14 left behind by build agents and manual backups (bench, build, ci-probe.4ZFeiD, "
    f"ci-probe.uv.lock.new, ci-probe310, ci_probe_dir, engine.json.bak2, engine.json.bak3, "
    f"engine.json.openrouter-backup, headcheck2, lang-sweep, mcp.json.test-debris-2026-10-09, "
    f"output, wt-arch-5820). Until the folder can be listed from a declaration and emptied "
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
