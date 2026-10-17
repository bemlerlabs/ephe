"""One source for the lint rule sets, and every code in it is a code ruff accepts.

Three readers use `scripts/lint_policy.sh`: the shell steps of `.github/workflows/lint.yml`,
`scripts/ci_local.sh`, and that leg's compare step, which parses the assignments with the shape
asserted below.

The test exists because the first draft of the blocking set carried F831, PIE700, PIE701 and
PIE702, and none of those exist in ruff 0.16.10. One unknown code makes `ruff check --select`
exit 2 for the whole invocation, which reaches the report as a red leg with no finding inside it.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from tests.subprocess_env import LOADER_KEYS, hermetic_env

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "scripts" / "lint_policy.sh"
LINT_LEG = ROOT / ".github" / "workflows" / "lint.yml"
CI_LOCAL = ROOT / "scripts" / "ci_local.sh"

#: The same binary `scripts/ci_local.sh` resolves: the repository's venv carries the pinned release
#: the counts in the policy file were measured with, and counts do move between releases -- I001
#: measured 424 on the host's 0.15.7 and 425 on the pinned 0.16.10, on the same tree.
#:
#: "exists" is not the test, "runs" is. `.venv` is a directory of binaries for the machine that built
#: it, so a checkout mounted into a Linux container -- or any venv whose interpreter was removed --
#: would hand this file a Mach-O ruff and the refusals below would be exec errors. A candidate that
#: cannot answer `--version` is passed over for the next one.
def _runnable(candidate: str) -> str:
    if not candidate:
        return ""
    try:
        done = subprocess.run([candidate, "--version"], capture_output=True, text=True, check=False)
    except OSError:
        # A foreign binary does not exit non-zero, it refuses to exec: copying this tree into a Linux
        # container raised `OSError: [Errno 8] Exec format error` out of a module-level constant,
        # which turned into a collection error for the whole file.
        return ""
    return candidate if done.returncode == 0 else ""


def _resolve_ruff() -> str:
    for candidate in (str(ROOT / ".venv" / "bin" / "ruff"), shutil.which("ruff") or ""):
        found = _runnable(candidate)
        if found:
            return found
    return ""


RUFF_BIN = _resolve_ruff()

ASSIGNMENT = re.compile(r'^([A-Z][A-Z0-9_]*)="([^"]*)"$')
PATH_LIKE = re.compile(r"^[a-z0-9_./-]+$")

# Two fixture bodies for the scoped prose pass. The first carries a filler header, a marketing
# adjective and a stacked figure, so any single one of them is enough to make it a finding; the
# second has no comment and no docstring, so nothing is measurable in it.
TELLING_BODY = (
    "# Note: important, this robust helper delves into the details of a stacked figure,\n"
    "# rather than stating a constraint.\n"
    "def helper():\n"
    "    return 1\n"
)
QUIET_BODY = "def helper():\n    return 1\n"


def _staged_repo(tmp_path: Path, rel: str, body: str) -> Path:
    """A throwaway checkout with one path staged, so the pass under test reads a real index blob."""
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    for args in (
        ["init", "-q"],
        ["config", "user.email", "plant@example.invalid"],
        ["config", "user.name", "plant"],
        ["add", rel],
    ):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


def _run_scope_check(repo: Path, rel: str) -> subprocess.CompletedProcess[str]:
    """The scoped pass as the hook runs it: `sys.executable`, and `hermetic_env` for the child.

    `TestTheChildEnvironmentIsTheJobs` holds the measurement and the two assertions that keep this
    shape, because neither symptom is reproducible on the machine writing the test.
    """
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "prose_scope_check.py")],
        cwd=repo, text=True, capture_output=True, check=False,
        env=hermetic_env(PATH=os.environ["PATH"], EPHE_STAGED_PATHS=rel),
    )


def assignments() -> dict[str, str]:
    """Every policy line that is not a comment, as name and value."""
    out: dict[str, str] = {}
    for line in POLICY.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ASSIGNMENT.match(stripped)
        assert match, f"not a flat NAME=\"value\" assignment: {line!r}"
        out[match.group(1)] = match.group(2)
    return out


def ruff_accepts(code: str) -> bool:
    """True when ruff parses the code, judged on an empty document so nothing is linted.

    Exit 0 is accepted (a rule or a category prefix), exit 1 would mean a finding on the empty
    document, and exit 2 is the usage error that poisons a whole leg.
    """
    done = subprocess.run(
        [RUFF_BIN, "check", "--select", code, "--output-format", "concise", "-"],
        input="", text=True, capture_output=True, check=False, cwd=ROOT,
    )
    return done.returncode == 0


class TestPolicyFile:
    def test_the_assignment_shape_holds_for_all_three_readers(self):
        values = assignments()
        assert set(values) == {
            "EPHE_RUFF_VERSION", "EPHE_MYPY_VERSION", "EPHE_RUFF_BLOCKING",
            "EPHE_RUFF_ADVISORY", "EPHE_LINT_EXCLUDE",
        }

    def test_the_pinned_versions_are_exact(self):
        """A range here would decide the lint verdict by which release shipped that day."""
        values = assignments()
        for name in ("EPHE_RUFF_VERSION", "EPHE_MYPY_VERSION"):
            assert re.fullmatch(r"\d+\.\d+\.\d+", values[name]), f"{name} = {values[name]!r}"

    def test_the_excluded_path_is_a_real_directory(self):
        """A stale exclude would re-admit the fixture whose single finding is the reason for it."""
        value = assignments()["EPHE_LINT_EXCLUDE"]
        assert PATH_LIKE.fullmatch(value), f"unparsable exclude: {value!r}"
        # The held-out eval tree is a workshop artefact. A tree that does not carry the
        # publication policy is the publication, and there the exclusion names a path the tree
        # withholds by design rather than one it lost.
        assert (ROOT / value).is_dir() or not (ROOT / ".publish-exclude").is_file(), (
            f"{value} is not a directory in this tree"
        )

    def test_no_rule_code_is_repeated_across_the_two_sets(self):
        values = assignments()
        blocking = {c for c in values["EPHE_RUFF_BLOCKING"].split(",") if c}
        advisory = {c for c in values["EPHE_RUFF_ADVISORY"].split(",") if c}
        assert not blocking & advisory, f"in both sets: {sorted(blocking & advisory)}"
        assert blocking and advisory


class TestRuleCodesResolve:
    def test_every_code_in_both_sets_is_understood_by_the_pinned_ruff(self):
        if not RUFF_BIN:
            raise AssertionError(
                "no ruff in .venv or on PATH. It is a dev extra dependency (`ruff>=0.15` in "
                "pyproject.toml); install with `pip install -e \".[dev,tui]\"` or `uv sync --extra dev`."
            )
        values = assignments()
        for name in ("EPHE_RUFF_BLOCKING", "EPHE_RUFF_ADVISORY"):
            for code in (c for c in values[name].split(",") if c):
                assert ruff_accepts(code), f"{name} carries {code}, which ruff rejects"

    def test_the_leg_that_gates_the_tree_still_selects_the_blocking_set(self):
        """The zero-count premise is the leg's to hold, on a clean checkout.

        An earlier version of this test ran the blocking set over the working tree, and that is the
        coupling the same wave removed from the pre-commit hook: on 2026-10-11 it went red on
        `tests/test_desktop_spawn_reaches_keyed_engine.py`, a file another lane had open mid-edit, so
        the refusal named this lane for a syntax state that no commit of this one carries. The
        premise is asserted where the checkout is one commit, in the whole-tree step of the leg, and
        the guard here is only that the step exists and reads the shared set.
        """
        text = LINT_LEG.read_text(encoding="utf-8")
        assert "ruff check ." in text, "the leg no longer runs the tree"
        assert '--select "$EPHE_RUFF_BLOCKING"' in text, "the leg selects its own list again"


class TestTheLanesSpawnShapes:
    """A text scan over this lane's files, for the one case the AST guard declares itself blind to.

    `tests/test_subprocess_env_guard.py` decides an interpreter child by its argv head. The
    attribution leg hands its environment to `bash`, and the script bash then execs is
    `python3 scripts/attribution_check.py`, so the interpreter appears one level down and the scan
    stays silent by design -- it lists that as a blind spot rather than guessing. This is the
    complement, scoped on purpose to the files this lane owns: a spawn of an interpreter by name, or
    an environment dict assembled from literals with no loader key anywhere near it, fails here.
    """

    LANE_FILES = (
        "test_lint_policy_consistency.py", "test_attribution_leg.py", "test_docker_lint_ratchet.py",
        "test_shipped_asset_and_catalog_checks.py", "test_hygiene_check.py", "test_lockfile_check.py",
        "test_ci_timing_report.py", "test_workflow_env_scopes.py",
    )
    INTERPRETER_HEAD = re.compile(r"\[\s*[\'\"]python3?[\'\"]\s*,")
    ENV_BUILT = ("hermetic_env", "env_without_tools", "os.environ")

    def _sources(self) -> dict[str, str]:
        # A lane file this tree does not hold cannot spawn anything: the attribution leg is a
        # workshop test, and the published tree is built without it.
        return {
            name: path.read_text(encoding="utf-8")
            for name in self.LANE_FILES
            if (path := ROOT / "tests" / name).is_file()
        }

    def test_no_interpreter_is_spawned_by_its_path_name(self):
        offenders = []
        for name, text in self._sources().items():
            for number, line in enumerate(text.splitlines(), 1):
                if self.INTERPRETER_HEAD.search(line):
                    offenders.append(f"tests/{name}:{number}")
        assert not offenders, f"spawn by name instead of sys.executable: {offenders}"

    def test_the_two_predicates_fire_on_the_shapes_they_refuse(self):
        """A guard that cannot be made to fail is decoration; both patterns are checked here.

        The strings are built by concatenation so the planted text does not appear in this file in the
        form the scan looks for, which would make the assertions above fail on their own source.
        """
        spawn = "[" + "'python3'" + ", 'script.py']"
        # Concatenated for the same reason as `spawn`: a literal here would be the shape the scan
        # above searches the file for.
        literal_env = ("env" + " = {") + "\n        \"PATH\": \"/usr/bin\",\n    }"
        assert self.INTERPRETER_HEAD.search(spawn), "the spawn scan no longer matches the shape"
        offenders = [
            number for number, line in enumerate(literal_env.splitlines(), 1)
            if re.search(r"env\s*=\s*\{", line)
            and not any(marker in literal_env for marker in self.ENV_BUILT)
        ]
        assert offenders == [1], offenders

    def test_every_environment_dict_in_the_lane_carries_the_loader_view(self):
        offenders = []
        for name, text in self._sources().items():
            lines = text.splitlines()
            for number, line in enumerate(lines, 1):
                if not re.search(r"env\s*=\s*\{", line):
                    continue
                window = "\n".join(lines[max(0, number - 7):number + 6])
                if not any(marker in window for marker in self.ENV_BUILT):
                    offenders.append(f"tests/{name}:{number}")
        assert not offenders, f"literal environment without a loader carrier: {offenders}"


class TestOneSource:
    def test_both_consumers_read_the_policy_instead_of_retyping_it(self):
        for path in (LINT_LEG, CI_LOCAL):
            text = path.read_text(encoding="utf-8")
            assert "scripts/lint_policy.sh" in text, f"{path.name} never sources the policy"
            assert not re.search(r"--select\s+[A-Z]", text), f"{path.name} hardcodes a rule list"

    def test_the_retired_hook_config_stays_retired(self):
        """`.pre-commit-config.yaml` listed ruff, ruff-format, mypy and pytest while core.hooksPath
        pointed at `.husky`, so no machine ever ran it. Its replacement is scripts/ci_local.sh.
        """
        assert not (ROOT / ".pre-commit-config.yaml").exists()
        hook = (ROOT / ".husky" / "pre-commit").read_text(encoding="utf-8")
        assert "scripts/ci_local.sh" in hook


class TestTheChildEnvironmentIsTheJobs:
    """The two things that made these plants red on Linux and green on this Mac.

    `pytest-linux (py3.10..3.13)` runs a shared-linked `python3.13` from
    `_work/_tool/Python/<ver>/arm64`: `ldd` resolves `libpython3.13.so.1.0` only because the job
    environment carries `LD_LIBRARY_PATH`. Reproduced in a Linux arm64 container on 2026-10-11 by
    moving that library out of the interpreter's own reach and starting the parent with the loader
    variable set, exactly as `actions/setup-python` does: a child built from `{"PATH": ...}` answered
    `error while loading shared libraries: libpython3.13.so.1.0` with **exit 127**, and the same child
    with the key carried printed its result and exited 0.

    Neither condition exists on this MacBook (its interpreter carries an rpath), so these two
    assertions pin the shape rather than the symptom; the Linux legs are where the symptom is
    exercised for real.
    """

    def test_the_child_gets_every_loader_key_the_parent_has(self):
        env = hermetic_env(PATH=os.environ["PATH"], EPHE_STAGED_PATHS="scripts/planted.py")
        inherited = {key for key in LOADER_KEYS if key in os.environ}
        assert inherited <= set(env), f"dropped {sorted(inherited - set(env))}"
        assert env["PATH"] == os.environ["PATH"]

    def test_the_child_is_the_interpreter_running_the_tests(self):
        """A bare `python3` on a sanitised PATH resolves to whatever the machine front-loads."""
        text = Path(__file__).read_text(encoding="utf-8")
        # The pattern is a regex rather than a substring so the assertion does not match its own
        # source line.
        spawn_by_name = re.search(r"\[\s*" + '"python3"' + r"\s*,", text)
        assert spawn_by_name is None, (
            "a child spawned by the name `python3` instead of sys.executable came back, at line "
            f"{text[:spawn_by_name.start()].count(chr(10)) + 1}"
        )


class TestLocalPassJudgesOnlyStagedContent:
    """The hook must not be able to refuse a commit over a file that commit does not carry.

    Measured 2026-10-11 while this wave was being written: `prose_tells.py --strict` takes 5.4 s
    and went RED on `tests/test_server_reason_code_channel.py`, a file in another lane, which under
    the earlier draft of the hook would have blocked every commit in a worktree holding dirty files
    from nineteen strands. Whole-tree runs belong to ci-gates.yml, where the checkout is one commit.
    """

    def test_ci_local_invokes_no_tree_wide_instrument(self):
        text = CI_LOCAL.read_text(encoding="utf-8")
        for tree_wide in ("prose_tells.py", "architecture_check.mjs", "language_gate.py"):
            assert tree_wide not in text, f"ci_local.sh still runs the whole-tree {tree_wide}"
        assert "scripts/prose_scope_check.py" in text

    def test_the_scoped_pass_refuses_a_planted_blob(self, tmp_path):
        repo = _staged_repo(tmp_path, "scripts/planted.py", TELLING_BODY)
        done = _run_scope_check(repo, "scripts/planted.py")
        assert done.returncode == 1, done.stdout + done.stderr
        assert "scripts/planted.py: 0 -> 1" in done.stdout, done.stdout

    def test_the_scoped_pass_is_green_on_a_blob_with_no_prose(self, tmp_path):
        repo = _staged_repo(tmp_path, "tests/quiet.py", QUIET_BODY)
        done = _run_scope_check(repo, "tests/quiet.py")
        assert done.returncode == 0, done.stdout + done.stderr

    def test_a_path_outside_the_measured_roots_is_not_refused(self, tmp_path):
        """`prose_tells.tracked()` asks git for PROSE_ROOTS, so a path under `docs/` that the
        tree-wide ratchet never measures stays out of this one too. The first version of the
        scoped pass filtered on extension alone and went red on a file the roots exclude, which
        would have refused a commit over content CI ignores.
        """
        repo = _staged_repo(tmp_path, "docs/planted.md", "# Note: important, this robust guide\n")
        done = _run_scope_check(repo, "docs/planted.md")
        assert done.returncode == 0, done.stdout + done.stderr
        assert "1 path(s) in scope, none of them prose the ratchet measures" in done.stdout, done.stdout

    def test_the_scoped_pass_reads_the_index_and_ignores_a_dirty_worktree(self, tmp_path):
        """A second strand's unstaged edit in the same file must not change this commit's verdict."""
        repo = _staged_repo(tmp_path, "tests/quiet.py", QUIET_BODY)
        (repo / "tests" / "quiet.py").write_text(TELLING_BODY, encoding="utf-8")
        done = _run_scope_check(repo, "tests/quiet.py")
        assert done.returncode == 0, done.stdout + done.stderr
        # The worktree really does carry the tell now, so a green verdict can only have come from
        # the blob the index holds.
        assert TELLING_BODY.strip() in (repo / "tests" / "quiet.py").read_text(encoding="utf-8")


class TestDeadIgnoreFlags:
    def test_no_leg_carries_an_ignore_flag_for_a_path_that_does_not_exist(self):
        """`--ignore=tests/playwright` names nothing from the repository root: the specs live in
        `app/tests/playwright/`, so the flag excluded no test and read like a decision had been made.
        The lane that runs those specs is wave II of docs/CI_HYBRID_CAPACITY_2026-10-11.md.
        """
        offenders: list[str] = []
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            if "--ignore=tests/playwright" in path.read_text(encoding="utf-8"):
                offenders.append(path.name)
        assert not offenders, f"dead ignore flag still in {offenders}"
        assert not (ROOT / "tests" / "playwright").exists()
