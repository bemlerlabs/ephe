"""Every action pin in `.github/workflows/` has to agree with itself.

Pinned here because CI proved what a divergent one costs: `release.yml` carried
`actions/setup-node@49933ea5288caeca8642dfe031c25787c58f31ff` from 5ead3c23 onward, a
commit that does not exist in that repository. GitHub reports it as
`Unable to resolve action` twelve seconds into the job, and because the release
workflow only runs on a tag, nothing exercised it — the desktop bundles it is supposed
to build could never have been built. The same action was pinned correctly in two
other workflows, which is the whole reason a rule like this one is cheap to check.

Offline on purpose: resolving a SHA to a release tag needs the API and a token, so a
test that did that would be a network dependency inside the hygiene suite. What can be
proven from the files alone is that a repository does not pin one action to two
commits, and never to a moving ref.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

USES = re.compile(r"uses:\s*([^\s@]+)@(\S+)")
SHA = re.compile(r"^[0-9a-f]{40}$")
#: Local step references and container actions are not repository pins.
SKIP_PREFIXES = ("./", "docker://")


def _pins() -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            m = USES.search(line)
            if m and not m.group(1).startswith(SKIP_PREFIXES):
                out.append((m.group(1), m.group(2), path.name))
    return out


def test_every_action_is_pinned_to_a_commit():
    """GIVEN every `uses:` line in the workflows THEN none of them trusts a moving
    ref. A tag or branch can be repointed by whoever owns the repo, and a workflow
    that publishes a signed desktop build must not follow it there.
    """
    floating = [(a, ref, f) for a, ref, f in _pins() if not SHA.match(ref)]
    assert not floating, f"actions pinned to a moving ref: {floating}"


def test_one_action_never_has_two_commits():
    """GIVEN the same action used by several workflows THEN they all name the same
    commit. Two pins of one action mean one of them is stale, and the stale one is
    usually in the workflow nobody runs on a schedule — which is how an unresolvable
    SHA sat in `release.yml` unnoticed.
    """
    by_action: dict[str, set[str]] = defaultdict(set)
    for action, ref, _ in _pins():
        by_action[action].add(ref)
    split = {a: sorted(refs) for a, refs in by_action.items() if len(refs) > 1}
    assert not split, f"actions pinned to more than one commit: {split}"


def test_a_commit_is_never_labelled_two_versions():
    """GIVEN the `# vX.Y.Z` comment beside a pin THEN one commit always carries the
    same label. The comment is the only human-readable statement of what the hash
    means; two different labels for one hash means at least one of them lies.
    """
    labels: dict[tuple[str, str], set[str]] = defaultdict(set)
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.search(r"uses:\s*([^\s@]+)@(\S+)\s*(?:#\s*(.+))?$", line.strip())
            if not m or m.group(1).startswith(SKIP_PREFIXES):
                continue
            comment = (m.group(3) or "").strip()
            if comment:
                labels[(m.group(1), m.group(2))].add(comment)
    ambiguous = {f"{a}@{r[:12]}": sorted(s) for (a, r), s in labels.items() if len(s) > 1}
    assert not ambiguous, f"the same pin is labelled differently: {ambiguous}"


def test_the_workflow_directory_is_not_empty():
    """A guard against the test passing because the path moved: no workflows would
    make every rule above vacuously true.
    """
    assert list(WORKFLOWS.glob("*.yml")), f"no workflows found under {WORKFLOWS}"
