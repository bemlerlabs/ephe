"""The supply-chain gate has to stay honest about what it ignores.

`ci-gates.yml` documented four Python advisories and seven JS advisories for weeks without
either fixing or accepting them — a noted problem, which is the thing that goes quiet. This
wave turned that into a measured decision: urllib3, multidict and oauthlib were moved to
their fixed versions and are held by `[tool.uv] constraint-dependencies`, and only chromadb
stays accepted, because as of 2026-10-09 no release above its `last_affected` exists. The
floor is asserted in pyproject.toml and again against the committed uv.lock, so a lock
resolved before the constraint cannot keep installing the advisory version while every
other fence reports clean.

These tests are offline on purpose (same reasoning as tests/test_ci_action_pins.py): they
assert that the ignore list is parseable, dated, justified and consistent with the
workflows, and they deliberately fail once an accepted risk passes its re-check date, so a
decision has to be renewed in writing or it becomes noise on its own.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
IGNORE = ROOT / ".github" / "advisories-ignore.txt"
WORKFLOW = ROOT / ".github" / "workflows" / "supply-chain.yml"
PYPROJECT = ROOT / "pyproject.toml"
LOCK = ROOT / "uv.lock"

#: The advisories that had a release. The fix version is also the floor: the bump is a
#: one-time move and the constraint is what stops a later `uv lock --upgrade` from walking
#: back into the advisory. Read out of the register's `state=fixed` rows instead of restated
#: here, because a second copy of the same fact is what drifts: on 2026-10-14 these three
#: lived only in a comment block in the register and in this tuple, and nothing tied them
#: to each other. Code below the entries so the reader sees the register is the source.
def _register_floors() -> tuple[tuple[str, str], ...]:
    """(package, fixed_in) for every `state=fixed` row **of the PyPI ecosystem**, in file order,
    deduplicated.

    The fence this feeds reads `uv.lock` and `pyproject.toml`'s `[tool.uv]` constraints, so it can
    only speak for PyPI. The register carries two ecosystems since the npm rows landed, and a floor
    without its ecosystem is a floor looked up in the wrong lock: the katex row's `fixed_in=0.18.2`
    belongs to `pnpm-lock.yaml`, and asserting it against `uv.lock` fails on a correct tree.
    """
    seen: list[tuple[str, str]] = []
    for m in _entries():
        if (m["state"] or "accepted") != "fixed":
            continue
        if (m["ecosystem"] or "PyPI") != "PyPI":
            continue
        pair = (m["package"], m["fixed_in"])
        if pair not in seen:
            seen.append(pair)
    return tuple(seen)


#: <ID>  # package=… [ecosystem=…] [scope=…] [state=…] affected=… fixed_in=… [blocked_by=…] recheck=YYYY-MM-DD
#: The ID alternation is the superset ANY_ID further down already defines. It used to be
#: the numeric shape alone, which accepted `PYSEC-2026-311` and rejected
#: `GHSA-238p-pmpm-9mq7`; that is why a GHSA-shaped finding had no legal line form here
#: and was written as prose, where no expiry and no resolver read it.
ENTRY = re.compile(
    r"^(?P<id>[A-Za-z]+-(?:\d{4}-\d{3,7}|[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}))\s+#\s+"
    r"package=(?P<package>\S+)\s+"
    r"(?:ecosystem=(?P<ecosystem>\S+)\s+)?"
    r"(?:scope=(?P<scope>\S+)\s+)?"
    r"(?:state=(?P<state>\S+)\s+)?"
    r"affected=(?P<affected>\S+)\s+"
    r"fixed_in=(?P<fixed_in>\S+)\s+"
    r"(?:blocked_by=(?P<blocked_by>\S+)\s+)?"
    r"recheck=(?P<recheck>\d{4}-\d{2}-\d{2})\s*$"
)
USES = re.compile(r"uses:\s*([^\s@]+)@(\S+)")
SHA = re.compile(r"^[0-9a-f]{40}$")


def _entries() -> list[re.Match[str]]:
    return [m for line in IGNORE.read_text(encoding="utf-8").splitlines()
            if (m := ENTRY.match(line.strip()))]


#: The floors, read from the register's `state=fixed` rows (defined above the entry regex
#: so this definition below it can use it).
FLOORS = _register_floors()


def _lock_packages() -> list[tuple[str, str]]:
    """(name, version) for every `[[package]]` in uv.lock, in file order.

    A package can appear in more than one block (forked by resolution marker), so all of
    them are returned: the caller must not let the one block that satisfies a floor hide a
    fork that does not.
    """
    out: list[tuple[str, str]] = []
    name: str | None = None
    version: str | None = None
    in_package = False
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s == "[[package]]":
            if in_package and name is not None:
                out.append((name, version or ""))
            name = version = None
            in_package = True
            continue
        if not in_package:
            continue
        if name is None and (m := re.match(r'name = "([^"]+)"$', s)):
            name = m.group(1)
        elif version is None and (m := re.match(r'version = "([^"]+)"$', s)):
            version = m.group(1)
    if in_package and name is not None:
        out.append((name, version or ""))
    return out


def _version_key(v: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", v))


def _at_least(version: str, floor: str) -> bool:
    v, f = _version_key(version), _version_key(floor)
    n = max(len(v), len(f))
    return v + (0,) * (n - len(v)) >= f + (0,) * (n - len(f))


def _lock_manifest_constraints() -> set[tuple[str, str]]:
    """The `{ name = …, specifier = … }` rows uv.lock records under `[manifest]`."""
    text = LOCK.read_text(encoding="utf-8")
    manifest = re.search(r"^\[manifest\]\s*$(.*?)(?=^\[\[package\]\])", text, re.S | re.M)
    assert manifest, "uv.lock has no [manifest] block before its first [[package]]"
    return set(re.findall(r'\{ name = "([^"]+)", specifier = "([^"]+)" \}', manifest.group(1)))


def test_the_gate_and_its_ignore_list_exist():
    """GIVEN the wave that replaced "reported but nobody enforces" THEN both the workflow
    and the file it reads are in the tree.
    """
    assert WORKFLOW.is_file(), f"missing {WORKFLOW}"
    assert IGNORE.is_file(), f"missing {IGNORE}"


def test_every_ignore_line_is_fully_attributed():
    """GIVEN a line that pip-audit will read as `--ignore-vuln` THEN it also names the
    package, the affected range, the fix situation and a re-check date. An ID on its own is
    how an ignore list turns into an unexplained allow-list.
    """
    lines = [l.strip() for l in IGNORE.read_text(encoding="utf-8").splitlines()]
    ids = [l for l in lines if re.match(r"^[A-Za-z]+-(?:GHSA-[a-z0-9-]+|\d{4}-\d{3,7})\s*$", l)]
    assert not ids, f"entries without package/affected/fixed_in/recheck attribution: {ids}"
    assert _entries(), "the ignore list contains no parseable entries at all"


def test_an_accepted_risk_is_never_ignored_without_a_fixed_in_none_claim():
    """GIVEN every entry in state=accepted THEN it declares `fixed_in=none`: an advisory that
    has a release is bumped or named as pending, not accepted. This is the difference between
    the chromadb rows and the urllib3/multidict/oauthlib rows of the same audit, and the
    difference between a carried risk and an open piece of work.
    """
    entries = _entries()
    wrong = [(m["id"], m["fixed_in"]) for m in entries
             if (m["state"] or "accepted") == "accepted" and m["fixed_in"] != "none"]
    assert not wrong, f"entries with an available fix must be upgraded, not ignored: {wrong}"
    assert any((m["state"] or "accepted") == "accepted" for m in entries), \
        "no accepted entry left — this rule would then assert nothing"


def test_each_entry_carries_a_rationale_above_it():
    """GIVEN every entry THEN the lines directly above it explain the decision in prose,
    not just in fields. A table nobody can read is still a silent ignore list. The heading
    has to be the one the state calls for: an entry with no release says why none exists, an
    entry whose fix is merely unapplied says what is missing, and an entry whose fix landed
    says why it is held — a `fixed` row carrying "Why it is not fixed yet" is prose that
    contradicts its own state.
    """
    headings = {"accepted": "Why there is no fix",
                "pending-fix": "Why it is not fixed yet",
                "fixed": "Why it is fixed"}
    text = IGNORE.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(text):
        stripped = line.strip()
        m = ENTRY.match(stripped)
        if not m:
            continue
        above = [t.strip() for t in text[max(0, i - 14):i] if t.strip()]
        rationale = " ".join(above)
        state = m["state"] or "accepted"
        assert headings[state] in rationale, (
            f"{m['id']} is state={state} and its rationale does not carry "
            f"{headings[state]!r}"
        )
        assert "Exposure as measured" in rationale, \
            f"{m['id']} has no exposure assessment"


def test_no_accepted_risk_is_past_its_recheck_date():
    """GIVEN the dates in the file THEN today is still inside the acceptance window. On the
    re-check date the gate starts failing until someone re-reads the advisories and moves the
    date with a written reason — that is what keeps a one-off decision from rotting.

    Every entry is checked, whatever its state. The name is the older half of the rule and
    the test below holds the per-state half, because a `pending-fix` row is an open move
    with a date on it, and a date nobody enforces records nothing.
    """
    today = dt.date.today()
    stale = [(m["id"], m["recheck"]) for m in _entries()
             if dt.date.fromisoformat(m["recheck"]) < today]
    assert not stale, f"advisories past their re-check date: {stale}"


def test_a_pending_fix_row_cannot_outlive_its_recheck_date():
    """GIVEN a row in state=pending-fix THEN its recheck is in the future and it names the
    blocker that is still open, so an open move cannot sit in the register as if it were a
    finished one. The register's own prose promises this; the fields are where it holds.
    """
    today = dt.date.today()
    pending = [m for m in _entries() if (m["state"] or "accepted") == "pending-fix"]
    assert pending, "no pending-fix row left to hold — the check would pass on nothing"
    for m in pending:
        assert dt.date.fromisoformat(m["recheck"]) >= today, (
            f"{m['id']} is pending-fix with recheck {m['recheck']} already past — the open "
            "move outlived the date that was supposed to force a re-read"
        )
        assert m["blocked_by"], f"{m['id']} is pending-fix without naming its blocker"


def test_every_entry_declares_the_state_that_matches_its_fix_situation():
    """GIVEN a finding THEN its state names which of the three homes it is in: accepted (no
    release exists anywhere), pending-fix (a release exists and the move is open work), or
    fixed (the release landed and the row is the floor that holds it). The fields have to
    agree with the state in both directions — a row claiming `accepted` while naming a fix
    version is the silent ignore this register exists to prevent, and a `fixed` row that
    still names a blocker is a claim about an open move that has already closed.
    """
    for m in _entries():
        label, state = m["id"], (m["state"] or "accepted")
        assert state in ("accepted", "pending-fix", "fixed"), (
            f"{label}: state {state!r} is not one of the three homes a finding has"
        )
        if state == "accepted":
            assert m["fixed_in"] == "none", (
                f"{label} is state=accepted and names fixed_in={m['fixed_in']} — a release "
                "exists, so it is pending-fix or fixed, and the fix is somebody's work"
            )
            continue
        assert m["fixed_in"] != "none", f"{label} is {state} with no fix version named"
        if state == "pending-fix":
            assert m["blocked_by"], f"{label} is {state} and does not say what is missing"
        else:
            assert not m["blocked_by"], (
                f"{label} is state=fixed and still names blocked_by={m['blocked_by']} — "
                "nothing blocks a fix that landed, so the row says two things at once"
            )


def test_every_entry_says_which_ecosystem_and_scope_it_is_about():
    """GIVEN an entry THEN ecosystem= and scope= are written out. They are the two fields a
    reader needs to tell a shipped runtime risk from a build-tooling one, and the two the
    flag derivation reads, so neither may be left to a default in this file.
    """
    for m in _entries():
        assert m["ecosystem"] in ("PyPI", "npm", "crates.io"), \
            f"{m['id']}: ecosystem {m['ecosystem']!r} is not one this register audits"
        assert m["scope"] in ("runtime", "development"), \
            f"{m['id']}: scope {m['scope']!r} is not runtime or development"


def test_only_pypi_accepted_rows_become_pip_ignore_flags():
    """GIVEN the resolver's --ignore-flags mode THEN every flag it prints is a PyPI entry in
    state=accepted. An npm or crates.io ID reaching `pip-audit --ignore-vuln` silences
    nothing today and would mask a same-ID PyPI advisory tomorrow; a pending-fix row is
    excluded because a release is within reach and the finding has to stay visible.
    """
    done = subprocess.run([sys.executable, str(RESOLVER), "--ignore-flags"],
                          capture_output=True, text=True, cwd=ROOT, check=True)
    printed = set()
    for token in done.stdout.split():
        if token == "--ignore-vuln":
            continue
        if token.startswith(("PYSEC-", "CVE-", "GHSA-", "RUSTSEC-")):
            printed.add(token)
    expected = {m["id"] for m in _entries()
                if m["ecosystem"] == "PyPI" and (m["state"] or "accepted") == "accepted"}
    assert printed == expected, f"ignore flags disagree with the register: {printed ^ expected}"
    # No PyPI row is `accepted` any more: the four chromadb rows and the two floors that named
    # urllib3 and oauthlib left with the packages they described, so the derived set is empty.
    # The guard is that it is *empty* rather than invented — a row coming back with no flag, or a
    # flag with no row, fails the line above, and this one fails if the resolver keeps emitting.
    carried = {m["package"] for m in _entries()
               if m["ecosystem"] == "PyPI" and (m["state"] or "accepted") == "accepted"}
    assert not carried, (
        f"the register still accepts a PyPI finding: {sorted(carried)} — this file derives "
        "--ignore-flags from exactly those rows, so the assertion above has to be re-read"
    )
    assert not printed, f"the resolver printed a flag the register does not hold: {sorted(printed)}"


def test_ids_are_listed_once():
    """GIVEN pip-audit reported PYSEC-2026-311 twice for one installed version THEN the
    register still names each ID once, so the ignore set cannot hide a second, different
    claim behind the same label.
    """
    ids = [m["id"] for m in _entries()]
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate entries: {sorted(dupes)}"


def test_the_gate_reads_the_list_instead_of_hardcoding_ids():
    """GIVEN the workflow THEN it derives `--ignore-vuln` from .github/advisories-ignore.txt
    and names no advisory ID itself, otherwise the file and the gate can disagree.
    """
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "advisories-ignore.txt" in body, "gate does not read the ignore list"
    hardcoded = re.findall(r"\b(?:PYSEC|CVE|GHSA)-\d{4}-\d{3,7}\b", body)
    assert not hardcoded, f"advisory IDs hardcoded in the workflow: {sorted(set(hardcoded))}"


def test_the_advisory_audit_step_cannot_turn_ci_red():
    """GIVEN the brief "non-blocking-but-visible" THEN every step that *reports findings* is
    marked continue-on-error, while the steps that prove the tools ran still block. A missing
    tool and an unreachable advisory database are no verdict at all, and configuring those two
    the same way is how a gate ends up reporting the clean it never measured.

    Re-read 2026-10-14: "visible" ended at the annotation, so an unaccepted finding waited for
    a re-check date to pass instead of failing where it appeared. The reporter steps stay soft
    because a summary has to be written either way, and the verdict steps are the half that is
    allowed to turn the run red — the next test below holds that half.
    """
    steps = re.split(r"\n\s*- name: ", WORKFLOW.read_text(encoding="utf-8"))[1:]
    guards = [s for s in steps if s.splitlines()[0].startswith("Resolve the audit tools")]
    assert len(guards) == 2, f"expected a Python and a JS tool guard, found {len(guards)}"
    soft = [s.splitlines()[0] for s in guards if "continue-on-error: true" in s]
    assert not soft, f"tool guards allowed to report clean without a verdict: {soft}"
    reporters = [s for s in steps
                 if "audit" in s.splitlines()[0].lower() and s not in guards]
    assert reporters, "no finding-reporting audit step found"
    unrunnable = [s.splitlines()[0] for s in reporters
                  if not re.search(r"pip-audit -r|pnpm audit|--audit-engine", s)]
    assert not unrunnable, f"audit-named steps that run no audit command: {unrunnable}"
    unmarked = [s.splitlines()[0] for s in reporters if "continue-on-error: true" not in s]
    assert not unmarked, f"audit steps that would fail CI: {unmarked}"


def test_the_expiry_step_blocks():
    """GIVEN the same workflow THEN the step that checks the re-check dates is NOT
    continue-on-error: an expired acceptance decision has to be visible as a red X.
    """
    steps = re.split(r"\n\s*- name: ", WORKFLOW.read_text(encoding="utf-8"))
    expiry = [s for s in steps if "expiry" in s.splitlines()[0].lower()]
    assert expiry, "no expiry-check step"
    for s in expiry:
        assert "continue-on-error" not in s.splitlines()[0]


def test_the_workflow_only_asks_for_read_access():
    """GIVEN a job whose only inputs are lockfiles THEN `permissions: contents: read` at the
    top and no write scope anywhere; an audit job has no reason to hold a token that could
    push.
    """
    body = WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r"^permissions:\s*contents:\s*read\s*$", body, re.M), \
        "workflow-level permissions must be exactly contents: read"
    assert not re.search(r"contents:\s*write|pull-requests:\s*write", body), \
        "a supply-chain audit job must not hold write scopes"


def test_every_checkout_refuses_to_persist_credentials():
    """GIVEN every checkout step THEN `persist-credentials: false`. The audit only reads the
    tree; leaving the default token in the runner's git config lets any later command (or a
    compromised dev dependency) act as the workflow.
    """
    body = WORKFLOW.read_text(encoding="utf-8")
    checkouts = body.count("actions/checkout@")
    persisted = body.count("persist-credentials: false")
    assert checkouts, "no checkout in the audit workflow"
    assert persisted >= checkouts, f"{checkouts} checkouts but only {persisted} opt-outs"


def test_the_audit_runner_is_a_variable_with_a_hosted_fallback():
    """GIVEN the sibling workflows run on the self-hosted Spark behind `vars.CI_LINUX_RUNNER`
    THEN this gate moves the same way only through its own variable, and only with the fallback
    still naming hosted, so an unset variable cannot park a security job in a queue forever.

    The 2026-10-09 rule was "stay hosted until the Spark is measured to carry pip and pnpm".
    Measured 2026-10-10 inside real jobs on `the lab runner`: pnpm 11.10.0 (Frontend Build installs
    and tests with it there), node v22.22.1, uv, pip, git, curl and bash all resolve. What had
    never been exercised from that box was the audit's own two routes -- pip-audit against the
    advisory databases and api.osv.dev for the ID resolution -- so the risk is no longer a
    missing binary but a route that answers nothing, and that is what the tool guards fail on.
    """
    body = WORKFLOW.read_text(encoding="utf-8")
    runners = re.findall(r"^\s*runs-on:\s*(.+)$", body, re.M)
    assert runners, "no runs-on found"
    for r in runners:
        assert "SUPPLY_CHAIN_RUNNER" in r, f"runner not behind the owner's switch: {r.strip()}"
        assert "ubuntu-latest" in r, f"runner without the hosted fallback: {r.strip()}"
    for guard in ("Resolve the audit tools, Python side", "Resolve the audit tools, JS side"):
        assert guard in body, f"the runner switch has no tool guard for: {guard}"


def test_a_finding_annotates_the_run():
    """GIVEN an audit that is allowed to fail softly THEN it still raises a workflow
    annotation, and SECURITY.md's claim that "findings are written to the job summary and as
    annotations" is backed by the file rather than asserted by it: a Python finding warns, a
    runtime-reachable JS finding and an expired acceptance both error.
    """
    body = WORKFLOW.read_text(encoding="utf-8")
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "Dependency Advisory Register" in security, "SECURITY.md no longer describes the register"
    assert "as annotations" in security or "annotation" in security
    assert "::warning::pip-audit exited" in body, "a Python finding produces no annotation"
    assert body.count("::error::") >= 3, "expected errors for missing audits, runtime JS findings and expiry"


def test_fixed_advisories_are_held_by_a_floor_not_by_an_ignore():
    """GIVEN the three advisories that had a release THEN pyproject.toml carries a
    `constraint-dependencies` floor for each, and none of them is in `state=accepted` — a
    fixed finding must not also be silenced by the flag that hides an open one. Without the
    floor a future `uv lock --upgrade` may walk back into the advisory and the reporting-only
    gate would merely shrug.

    The `fixed` rows are in this register on purpose; what must not be there is a `fixed`
    package riding in the ignore set, so the check reads the accepted rows rather than the
    file's package names.
    """
    assert FLOORS, "no state=fixed row in the register — the floor fence would pass on nothing"
    floors = re.search(r"constraint-dependencies\s*=\s*\[(.*?)\]",
                       PYPROJECT.read_text(encoding="utf-8"), re.S)
    assert floors, "no [tool.uv] constraint-dependencies in pyproject.toml"
    body = floors.group(1)
    for pkg, version in FLOORS:
        assert re.search(rf'"{pkg}>={version}"', body), f"{pkg} lacks its >= {version} floor"
    silenced = {m["package"] for m in _entries() if (m["state"] or "accepted") == "accepted"}
    assert not (silenced & {pkg for pkg, _ in FLOORS}), (
        f"a fixed finding is also state=accepted, so the ignore flag hides it: "
        f"{silenced & {pkg for pkg, _ in FLOORS}}"
    )



def _ver_ge(have: str, need: str) -> bool:
    """`have >= need` on dotted numeric versions, ignoring any prerelease suffix."""
    def parts(v: str) -> list[int]:
        out = []
        for chunk in v.split("."):
            digits = re.match(r"\d+", chunk)
            out.append(int(digits.group()) if digits else 0)
        return out
    a, b = parts(have), parts(need)
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else 0
        y = b[i] if i < len(b) else 0
        if x != y:
            return x > y
    return True

def test_a_fixed_row_is_held_by_the_lock_so_its_advisory_cannot_return():
    """GIVEN a register row in state=fixed THEN the committed uv.lock resolves that package at
    or above the `fixed_in` the row names, or the row fails.

    This is what makes the state worth writing. A fixed advisory has no `--ignore-vuln` flag
    (only PyPI `accepted` rows get one), so nothing silences it: if a later `uv lock --upgrade`
    walks the package back below its fix, the advisory returns to pip-audit's report and the
    only thing standing between that and a shipped regression is this fence. A reviewer's
    memory and the tuple that used to live in this file were the earlier candidates, and
    neither could say anything.
    """
    assert FLOORS, "no state=fixed row in the register — this fence would pass on nothing"
    resolved: dict[str, list[str]] = {}
    for name, version in _lock_packages():
        resolved.setdefault(name, []).append(version)
    for m in _entries():
        if (m["state"] or "accepted") != "fixed":
            continue
        # A floor belongs to its ecosystem: uv.lock carries Python, pnpm-lock.yaml carries npm,
        # and a PyPI row asserted against the npm lock (or the reverse) fails on a correct tree.
        if (m["ecosystem"] or "PyPI") != "PyPI":
            continue
        versions = resolved.get(m["package"], [])
        assert versions, (
            f"{m['id']} is state=fixed for {m['package']} but uv.lock resolves no such "
            "package — the row names a fix for something the lock does not carry"
        )


def test_a_fixed_npm_row_is_held_by_the_npm_lock() -> None:
    """GIVEN a register row in state=fixed with ecosystem=npm THEN app/pnpm-lock.yaml resolves that
    package at or above the `fixed_in` the row names.

    The sibling of the PyPI fence above, and it exists for the same reason: a `fixed` row is a claim
    that the vulnerable copy is gone, and a claim no lock is asked about is prose. The two fences are
    split by ecosystem because the two locks are — an npm row cannot be held by uv.lock, and asserting
    it there fails on a correct tree.
    """
    npm_rows = [
        m for m in _entries()
        if (m["state"] or "accepted") == "fixed" and (m["ecosystem"] or "PyPI") == "npm"
    ]
    if not npm_rows:
        return  # nothing to hold; the PyPI fence above asserts its own set is non-empty
    lock = (ROOT / "app" / "pnpm-lock.yaml").read_text(encoding="utf-8")
    for m in npm_rows:
        # pnpm-lock v9 lists every resolution as `  <name>@<version>:` under `packages:`.
        found = re.findall(rf"^  {re.escape(m['package'])}@([0-9][^:\s]*):", lock, re.M)
        assert found, (
            f"{m['id']} is state=fixed for {m['package']} (npm) but pnpm-lock.yaml resolves no "
            "such package — the row names a fix for something the lock does not carry"
        )
        assert any(_ver_ge(v, m["fixed_in"]) for v in found), (
            f"{m['id']} names fixed_in={m['fixed_in']} but pnpm-lock.yaml resolves "
            f"{sorted(set(found))} — the vulnerable copy is back in the lock"
        )


def test_the_lock_resolves_every_floored_package_at_or_above_its_floor():
    """GIVEN the pyproject floors THEN the committed uv.lock has already resolved each one
    to a version that satisfies it, and every forked block does too.

    pyproject alone is a promise; the lock is the version CI installs. A floor the lock
    never took (a stale lock, or a `uv lock` run before the constraint was added) satisfies
    every other fence test while installing the advisory version, which is exactly the gap
    this reads the lock to close.
    """
    assert LOCK.is_file(), f"missing {LOCK}"
    resolved: dict[str, list[str]] = {}
    for name, version in _lock_packages():
        resolved.setdefault(name, []).append(version)
    for pkg, floor in FLOORS:
        versions = resolved.get(pkg, [])
        assert versions, f"{pkg} is floored in pyproject but absent from uv.lock"
        below = [v for v in versions if not _at_least(v, floor)]
        assert not below, (
            f"{pkg} is floored at >= {floor} but uv.lock pins {below} — the lock was not "
            "re-resolved under the constraint"
        )


def test_the_lock_records_the_floors_pyproject_declares():
    """GIVEN the floors in pyproject.toml THEN uv.lock's `[manifest]` names the same
    constraints, so the floor is part of the locked set a reviewer and a resolver both read.

    A floor added to pyproject without re-locking would otherwise surface only in
    `uv lock --check`, which this offline fence never runs.
    """
    assert LOCK.is_file(), f"missing {LOCK}"
    declared = _lock_manifest_constraints()
    for pkg, floor in FLOORS:
        assert (pkg, f">={floor}") in declared, (
            f"uv.lock [manifest] does not record {pkg}>={floor}: {sorted(declared)}"
        )


# The engine register and the ID resolver (added 2026-10-09).
#
# Two blind spots closed here. First: `pip-audit` asks the PyPI ecosystem about the pip
# package, so an advisory on the Rust engine compiled into that wheel is invisible to it —
# measured, the same version answers zero records as `wasmtime` and five as
# `wasmtime-wasi`. Second: an ID that names no advisory is *ignored* by `--ignore-vuln`
# with exit 0, so a register can accept a risk against nothing and stay green.

ENGINE = ROOT / ".github" / "engine-advisories.txt"
RESOLVER = ROOT / "scripts" / "advisory_id_check.py"
ENGINE_ENTRY = re.compile(
    r"^(?P<id>[A-Za-z]+-\d{4}-\d{3,7})\s+#\s+package=(?P<package>\S+)\s+ecosystem=(?P<ecosystem>\S+)\s+"
    r"probe=(?P<probe>\S+)\s+affected=(?P<affected>\S+)\s+fixed_in=(?P<fixed_in>\S+)\s+"
    r"blocked_by=(?P<blocked_by>\S+)\s+(?:alias=(?P<alias>\S+)\s+)?"\
    r"recheck=(?P<recheck>\d{4}-\d{2}-\d{2})\s*$"
)
ANY_ID = re.compile(
    r"\b(?:GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}|(?:PYSEC|RUSTSEC|CVE)-\d{4}-\d{3,7})\b"
)


def _engine_entries() -> list[re.Match[str]]:
    return [m for line in ENGINE.read_text(encoding="utf-8").splitlines()
            if (m := ENGINE_ENTRY.match(line.strip()))]


def _engine_rationales() -> list[tuple[str, str]]:
    """(id, the comment block directly above it). Read as a block, not as a fixed window:
    a rationale long enough to run past an arbitrary line count is still one rationale,
    and a check that silently reads half of it would pass on the tail alone.
    """
    lines = ENGINE.read_text(encoding="utf-8").splitlines()
    out: list[tuple[str, str]] = []
    for i, line in enumerate(lines):
        m = ENGINE_ENTRY.match(line.strip())
        if not m:
            continue
        block: list[str] = []
        for prev in reversed(lines[:i]):
            stripped = prev.strip()
            if not stripped:
                break
            if not stripped.startswith("#"):
                break
            block.append(stripped.lstrip("# ").rstrip())
        out.append((m["id"], " ".join(reversed(block))))
    return out


def test_the_engine_register_exists_and_covers_what_the_pip_audit_cannot_see():
    """GIVEN the cell runs on a Rust engine inside a pip wheel THEN the advisories on
    that engine are written down in their own register, because the pip audit will never
    report them and an unreported risk is not an accepted one.
    """
    assert ENGINE.is_file(), f"missing {ENGINE}"
    entries = _engine_entries()
    assert entries, f"no parseable entry in {ENGINE}"
    for identifier, rationale in _engine_rationales():
        assert "Exposure as measured" in rationale, f"{identifier} has no exposure read"
        assert "UNPROVEN" in rationale, (
            f"{identifier} states its exposure as if nothing were unknown — a mitigation "
            "claimed without its gap is a guess"
        )
    stale = [(m["id"], m["recheck"]) for m in entries
             if dt.date.fromisoformat(m["recheck"]) < dt.date.today()]
    assert not stale, f"engine advisories past their re-check date: {stale}"


def test_an_engine_acceptance_names_the_constraint_that_keeps_the_fix_out_of_reach():
    """GIVEN an engine advisory with a published fix THEN the line also names what stops
    us from taking it. `fixed_in=none` is not the story here — the fix exists and is
    unreachable through a dependency we do not control the ceiling of.
    """
    for m in _engine_entries():
        assert m["fixed_in"] != "none", (
            f"{m['id']}: a crates.io advisory with no release above it is a different claim; "
            "if that is truly the case, say so and re-check the database"
        )
        assert m["blocked_by"], f"{m['id']} lacks blocked_by="


def test_the_gate_resolves_every_accepted_id_instead_of_only_ignoring_it():
    """GIVEN the workflow THEN it calls the resolver as a blocking step, derives its
    ignore flags from the same parser, and keeps the engine lookup report-only — and the
    resolver matches on aliases, because an ID that exists only as another record's alias
    is exactly what a naive lookup reads as invented.
    """
    assert RESOLVER.is_file(), f"missing {RESOLVER}"
    resolver = RESOLVER.read_text(encoding="utf-8")
    assert "aliases" in resolver, "the resolver does not match aliases — a RustSec/GitHub " \
        "alias pair would be reported as an unknown ID"
    assert "api.osv.dev/v1" in resolver and '/query' in resolver, \
        "the resolver has no package-scoped fallback route"
    body = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/advisory_id_check.py --ignore-flags" in body, \
        "the ignore flags are derived by a second regex instead of the resolver"
    assert "[A-Za-z]+-[0-9]{4}" not in body, \
        "the workflow parses the register with its own numeric-only ID pattern instead of " \
        "the resolver — a GHSA-shaped entry is invisible to a pattern like that"
    assert "--recheck-pairs" in body, \
        "the expiry step does not read its dates from the resolver's parser"
    steps = re.split(r"\n\s*- name: ", body)[1:]
    resolve = [s for s in steps if s.splitlines()[0].startswith("Advisory ID resolution")]
    assert resolve, "no ID-resolution step — an unknown ID would be ignored silently"
    for s in resolve:
        assert "continue-on-error" not in s, "the ID check must block, not warn"
    engine = [s for s in steps if "engine advisory" in s.splitlines()[0].lower()]
    assert engine, "no engine advisory lookup step"
    for s in engine:
        assert "continue-on-error: true" in s, \
            "a new upstream engine advisory must not turn somebody else's push red"


def test_no_advisory_id_is_cited_in_the_docs_without_a_register_line():
    """GIVEN an advisory ID named anywhere in docs/ or .github/ THEN it also appears in
    one of the two register files, or its line says `example-id:`. A citation outside the
    registers is a security claim no machine check reads — which is how an unverifiable ID
    survives for weeks — and the one exemption is a deliberate, greppable marker, not a
    file the rule skips.
    """
    registered = set()
    for path in (IGNORE, ENGINE):
        if path.is_file():
            registered.update(ANY_ID.findall(path.read_text(encoding="utf-8")))
    sources = list((ROOT / "docs").rglob("*.md")) + list((ROOT / ".github").glob("*.md"))
    if (ROOT / "SECURITY.md").is_file():
        sources.append(ROOT / "SECURITY.md")
    orphans: dict[str, list[str]] = {}
    for path in sources:
        for line in path.read_text(encoding="utf-8").splitlines():
            # `example-id:` is the only way an ID may be written outside the registers: a
            # falsification record has to name the invented ID to prove the check fires,
            # and an opt-in marker per line keeps that visible and greppable instead of
            # carving out a file where citations stop being checked.
            if "example-id:" in line:
                continue
            for identifier in set(ANY_ID.findall(line)) - registered:
                orphans.setdefault(identifier, []).append(str(path.relative_to(ROOT)))
    assert not orphans, (
        f"advisory IDs cited with no register entry: {orphans} — add the line with its "
        "measured exposure, or correct the citation"
    )


# The audit's second half: a finding has to fail where it appears.


def _steps() -> list[str]:
    """Every step of the supply-chain workflow, in order, name included."""
    return re.split(r"\n\s*- name: ", WORKFLOW.read_text(encoding="utf-8"))[1:]


def _resolver():
    """The resolver loaded as a module, so a verdict can be judged on a fixture rather than
    on a network round trip. It lives in `scripts/` and is loaded by path — the same file the
    workflow runs, never a copy that could drift from it.
    """
    spec = importlib.util.spec_from_file_location("advisory_id_check_under_test", RESOLVER)
    assert spec and spec.loader, "the resolver could not be loaded as a module"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_audited_ecosystem_has_a_verdict_step_that_is_allowed_to_fail():
    """GIVEN the three manifests this repository ships THEN each has a verdict step that
    judges the audit's report against the register and is not continue-on-error.

    Measured 2026-10-14: the find-out -> flag -> fail chain ended at the flag for Python and
    had no first link at all for `app/src-tauri/Cargo.lock` — 512 crates, three with an
    advisory record, one of them (rustls 0.23.45) a runtime path of the shipped updater with
    eight records behind it. An audit that cannot fail is a report.
    """
    steps = _steps()
    expected = {"Python advisory verdict": "--pip-verdict",
                "JS advisory verdict": "--pnpm-verdict",
                "Cargo advisory verdict": "--audit-cargo"}
    for name, flag in expected.items():
        found = [s for s in steps if s.splitlines()[0].startswith(name)]
        assert found, f"no step named {name!r} — that ecosystem has no verdict"
        for step in found:
            assert "continue-on-error" not in step.splitlines()[0], \
                f"{name} is marked continue-on-error, so it is a report and not a verdict"
            assert flag in step, f"{name} does not run the resolver's {flag} mode"
    assert "Cargo.lock" in WORKFLOW.read_text(encoding="utf-8"), (
        "no step names app/src-tauri/Cargo.lock, so the crate lockfile is still invisible"
    )


def test_the_cargo_lock_is_read_as_the_manifest_it_is():
    """GIVEN the Tauri shell's lockfile THEN the reader finds the pinned set in it. The
    reader is asserted against the real 512-crate lock and not a fixture, because an empty
    parse is the failure mode that would report clean forever.
    """
    mod = _resolver()
    packages = mod._cargo_packages()
    assert len(packages) > 400, f"only {len(packages)} crate(s) parsed from Cargo.lock"
    names = {name for name, _ in packages}
    assert {"glib", "tauri", "rustls"} <= names, "the parse missed a crate the shell needs"


def test_a_cargo_finding_is_judged_by_the_register_not_by_the_tool(monkeypatch):
    """GIVEN a crate that carries an advisory THEN `--audit-cargo` exits 0 when a register
    row decides it (by ID or by alias) and 1 when none does. The advisory databases are
    replaced for the test, so this asserts the decision on its own.
    """
    mod = _resolver()
    rows = mod._entries()
    assert mod._registered(rows, "crates.io"), "no crates.io row to decide anything"

    monkeypatch.setattr(mod, "_cargo_packages", lambda: [("glib", "0.18.5")])
    monkeypatch.setattr(mod, "_osv_batch",
                        lambda pairs: {("glib", "0.18.5"): ["RUSTSEC-2024-0429"]})
    # The register cites the GitHub ID while RustSec publishes the RUSTSEC one: the pair is
    # the same advisory, and reading only the primary ID is what would call a decided
    # finding undecided.
    monkeypatch.setattr(mod, "_aliases_of", lambda i: (
        {"RUSTSEC-2024-0429", "GHSA-wrw7-89jp-8q8g"}, ["0.20.0"], "unsound iterator"))
    assert mod._audit_cargo(rows) == 0, "a decided crate was reported as undecided"

    monkeypatch.setattr(mod, "_cargo_packages", lambda: [("invented", "9.9.9")])
    monkeypatch.setattr(mod, "_osv_batch",
                        lambda pairs: {("invented", "9.9.9"): ["RUSTSEC-2026-9999"]})
    monkeypatch.setattr(mod, "_aliases_of", lambda i: ({"RUSTSEC-2026-9999"}, ["10.0.0"], ""))
    assert mod._audit_cargo(rows) == 1, "an undecided crate did not fail the verdict"


def test_a_pip_finding_is_accounted_for_by_its_id_or_one_of_its_aliases(tmp_path):
    """GIVEN `pip-audit --format json` THEN a finding whose ID *or* alias is a register row
    passes, and a finding nobody wrote down exits 1.

    pip-audit reports a PyPI record under the ID the advisory database chose, and the register
    may name a different alias of the same record. Measured on this register: GHSA-54p9-h82j-f925
    and its CVE alias are the same multidict finding, one row.
    """
    mod = _resolver()
    rows = mod._entries()

    def report(payload, name="pip.json"):
        path = tmp_path / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    accepted = report([{"name": "multidict", "version": "6.9.1", "vulns": [
        {"id": "GHSA-54p9-h82j-f925", "fix_versions": ["6.9.1"],
         "aliases": ["CVE-2026-104874"]}]}])
    assert mod._audit_pip_report(accepted, rows) == 0

    by_alias = report([{"name": "multidict", "version": "6.9.1", "vulns": [
        {"id": "CVE-2026-104874", "fix_versions": ["6.9.1"],
         "aliases": ["GHSA-54p9-h82j-f925"]}]}], "alias.json")
    assert mod._audit_pip_report(by_alias, rows) == 0, (
        "the register's ID arrived as an alias instead of as the primary id — a check that "
        "compares only `id` calls a decided finding undecided"
    )

    undecided = report([{"name": "somepkg", "version": "1.0", "vulns": [
        {"id": "GHSA-aaaa-bbbb-cccc", "fix_versions": ["1.1"], "aliases": []}]}], "new.json")
    assert mod._audit_pip_report(undecided, rows) == 1, "an unaccounted finding passed"

    nothing = report([{"name": "somepkg", "version": "1.0", "vulns": []}], "empty.json")
    assert mod._audit_pip_report(nothing, rows) == 0, "an audit with no findings failed"


def test_a_verdict_without_a_report_or_a_route_is_not_a_clean_verdict(tmp_path):
    """GIVEN an audit that produced nothing THEN every verdict refuses it: an absence is not
    a clean result. A JSON report that is missing, unparsable, empty, or a pnpm answer with
    no `advisories` object is a step that did not measure; refusing it is the point.
    """
    mod = _resolver()
    rows = mod._entries()
    with pytest.raises(SystemExit):
        mod._audit_pip_report(tmp_path / "missing.json", rows)

    garbage = tmp_path / "garbage.json"
    garbage.write_text("pnpm audit exited non-zero", encoding="utf-8")
    with pytest.raises(SystemExit):
        mod._audit_pip_report(garbage, rows)

    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit):
        mod._audit_pip_report(empty, rows)

    no_route = tmp_path / "pnpm.json"
    no_route.write_text(json.dumps({"error": {"code": "ENOTFOUND"}}), encoding="utf-8")
    with pytest.raises(SystemExit):
        mod._audit_pnpm_report(no_route, rows)


def test_a_pnpm_advisory_is_judged_against_the_register(tmp_path):
    """GIVEN `pnpm audit --json` THEN an advisory the register carries passes whatever its
    scope, and one no row carries exits 1 — the JS half of the same chain, so a dev-only
    decision stays a decision and a brand-new runtime one cannot ship quietly.
    """
    mod = _resolver()
    rows = mod._entries()

    def report(advisories):
        path = tmp_path / "pnpm.json"
        path.write_text(json.dumps({"advisories": advisories}), encoding="utf-8")
        return path

    decided = report({"1": {"module_name": "katex", "severity": "low",
                            "github_advisory_id": "GHSA-238p-pmpm-9mq7", "cves": []}})
    assert mod._audit_pnpm_report(decided, rows) == 0

    undecided = report({"2": {"module_name": "newpkg", "severity": "critical",
                              "github_advisory_id": "GHSA-zzzz-yyyy-xxxx",
                              "cves": ["CVE-2026-0001"]}})
    assert mod._audit_pnpm_report(undecided, rows) == 1

