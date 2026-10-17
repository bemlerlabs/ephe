#!/usr/bin/env python3
"""Ephe - scripts/custody_demo: the two refusals and the one landing.

`core/change_set.py`, `core/review_gate.py` and `core/atomic_publish.py` each ship a rule a
diff cannot express: an author may not sign their own work, a reviewer's signature is bound
to the digests it was given, and a landing is every file or none. What this script does is
*run* those three rules against a real repository with real git under it and write down what
each one answered, so the claim can be read as a receipt instead of believed.

The demo needs a repository of its own to move a branch in, and it takes one:

  * default: a scratch repository under the store's own directory, so a run nobody asked for
    cannot touch the operator's ``~/.ephe``;
  * ``--store ~/.ephe``: the same beats against the product's real stores, which is what the
    Workspaces page then reads (used to record the page's evidence).

The publish beats mirror the guard ``POST /api/change-sets/{id}/publish`` applies — the gate
first, then ``verify_current`` — because that pair is what makes the signature mean anything.
``ephe publish`` applies the first half only; see the findings inbox.

Run:  python3 scripts/custody_demo.py [--store DIR] [--repo DIR] [--out receipt.json]
Exit: 0 when every beat is proven, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parent.parent

#: Bump when the receipt shape changes; a reader refuses a version it does not know.
RECEIPT_SCHEMA = 1
DEMO = "change-set-custody"

WORKER = "demo-worker"
REVIEWER = "demo-reviewer"
WORKER_EDIT = "VALUE = 2\n"
STALE_EDIT = "VALUE = 3\n"
SEEDED = "VALUE = 1\n"


def git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "user.name=ephe-demo", "-c", "user.email=demo@ephe.invalid", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def must(args: list[str], cwd: Path) -> str:
    done = git(args, cwd)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {done.stderr.strip()}")
    return done.stdout.strip()


def seed_repo(target: Path) -> None:
    """A small real repository: one module, one commit, nothing else."""
    target.mkdir(parents=True)
    must(["init", "-q", "-b", "main"], target)
    (target / "values.py").write_text(SEEDED, encoding="utf-8")
    (target / "README.md").write_text("# the demo target\n", encoding="utf-8")
    must(["add", "-A"], target)
    must(["commit", "-qm", "chore: seed the target"], target)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ephe - the custody demo")
    parser.add_argument("--store", default="", help="Where the three stores live (default: scratch)")
    parser.add_argument("--repo", default="", help="The repository to move a branch in (default: scratch)")
    parser.add_argument("--out", default="", help="Write the receipt here as well as to stdout")
    parser.add_argument("--keep", action="store_true", help="Leave a scratch store and repo behind")
    args = parser.parse_args()

    scratch = Path(tempfile.mkdtemp(prefix="ephe-custody-"))
    store = Path(args.store).expanduser() if args.store else scratch / "store"
    repo = Path(args.repo).expanduser() if args.repo else scratch / "target"
    # The three modules read their locations at import; point them before the import.
    os.environ["EPHE_CHANGESETS_DIR"] = str(store / "changesets")
    os.environ["EPHE_REVIEW_LEDGER"] = str(store / "reviews.jsonl")
    os.environ["EPHE_WORKSPACES_DIR"] = str(store / "workspaces")
    os.environ["EPHE_REPO_ROOT"] = str(repo)
    sys.path.insert(0, str(REPO_ROOT))

    from core import change_set as store_mod
    from core import review_gate as gate
    from core import workspace_lifecycle as life
    from core._cli_isolation import gate_change_set, run_publish, run_review
    from core.atomic_publish import publish
    from core.change_set_read import verify_current

    beats: list[dict] = []

    def beat(name: str, **fields) -> None:
        beats.append({"beat": name, **fields})
        print(f"\n== {name} ==")
        for key, value in fields.items():
            print(f"  {key}: {value}")

    def view(change) -> gate.ChangeSet:
        return gate_change_set(change)

    def latest(change_set_id: str) -> gate.ReviewVerdict:
        recorded = gate.decide(change_set_id)
        if recorded is None:
            raise RuntimeError(f"no verdict was recorded for {change_set_id}")
        return recorded

    def state_of(change_set_id: str) -> str:
        stored = store_mod.load(change_set_id)
        if stored is None:
            raise RuntimeError(f"change set {change_set_id} is not in the store")
        return stored.state

    def refusals(calls: list[tuple[str, dict]]) -> list[dict]:
        """Every rule as it answers when it is broken — the sentences, never a traceback."""
        out = []
        for label, kwargs in calls:
            try:
                gate.submit(**kwargs)
                out.append({"rule": label, "refused": False})
            except gate.ReviewGateError as exc:
                out.append({"rule": label, "refused": True, "sentence": str(exc)})
        return out

    def route_publish(change, target: str) -> dict:
        """The guard POST …/publish applies, in the order that route applies it."""
        if not gate.may_publish(view(change)):
            return {"landed": False, "check": "may_publish", "sentence": "no approval from a reviewer other than the author"}
        drifted = verify_current(change)
        if drifted:
            return {"landed": False, "check": "verify_current", "drifted": drifted}
        result = publish(change, target=target, dry_run=False)
        return {"landed": bool(result.ok), "check": "publish", "applied": result.applied, "reason": result.reason}

    try:
        if not repo.exists():
            seed_repo(repo)
        print(f"target repository: {repo}")
        print(f"stores:            {store}")

        # 1. Two agents, two checkouts, one repository.
        worker = life.create(WORKER)
        reviewer = life.create(REVIEWER)
        beat("two-agents-two-checkouts", worker=worker.id, reviewer=reviewer.id,
             **{"worker_branch": worker.branch, "reviewer_branch": reviewer.branch})

        # 2. The worker changes a real file and says why.
        (Path(worker.path) / "values.py").write_text(WORKER_EDIT, encoding="utf-8")
        first = store_mod.build(
            worker.path,
            "raise VALUE to 2",
            {"session_id": "s-demo", "agent_id": WORKER, "why": "the demo needs a changed byte"},
        )
        beat("recorded", change_set=first.id, state=first.state,
             why=first.provenance.why,
             **{"files": [{"path": f.path, "op": f.op, "diff_sha": f.diff_sha} for f in first.files]})

        # 3. Every way the gate says no to one submission.
        refused = refusals([
            ("the author signing their own work", dict(
                change_set=view(first), verdict=gate.APPROVE, reviewer=WORKER,
                reasons=[{"path": "values.py", "line": 1, "why": "looks right to me"}])),
            ("a verdict with no reason at all", dict(
                change_set=view(first), verdict=gate.APPROVE, reviewer=REVIEWER, reasons=[])),
            ("a reason naming a line outside the set", dict(
                change_set=view(first), verdict=gate.APPROVE, reviewer=REVIEWER,
                reasons=[{"path": "values.py", "line": 0, "why": "nowhere"}])),
            ("a reason naming a file the set never touches", dict(
                change_set=view(first), verdict=gate.APPROVE, reviewer=REVIEWER,
                reasons=[{"path": "other.py", "line": 1, "why": "not in the set"}])),
        ])
        beat("the-gate-says-no", **{"refusals": refused})

        # 4. The other agent signs it, through the product's own verb, and the signature is
        #    bound to these digests.
        run_review(first.id, "approve", REVIEWER,
                   [f"{first.files[0].path}:1:the value is the one the demo asks for"],
                   as_json=False)
        verdict = latest(first.id)
        beat("signed-by-the-other-agent", reviewer=verdict.reviewer, verdict=verdict.verdict,
             state=state_of(first.id),
             may_publish=gate.may_publish(view(first)),
             ledger_lines=len((store / "reviews.jsonl").read_text(encoding="utf-8").strip().splitlines()))

        # 5. The signed bytes move. The signature does not move with them.
        (Path(worker.path) / "values.py").write_text(STALE_EDIT, encoding="utf-8")
        stale = route_publish(first, target="custody/demo")
        beat("the-bytes-moved", **{"refused": not stale["landed"], **stale})

        # 6. Record it again, sign the new digests, land — every file or none.
        second = store_mod.build(
            worker.path,
            "raise VALUE to 3",
            {"session_id": "s-demo", "agent_id": WORKER,
             "why": "the reviewed bytes are the ones that land"},
        )
        run_review(second.id, "approve", REVIEWER,
                   [f"{second.files[0].path}:1:three is the reviewed value"], as_json=False)
        # Landed through the product's own verb, which applies the gate and moves the state.
        run_publish(second.id, target="custody/demo", dry_run=False, as_json=False)
        head = must(["rev-parse", "custody/demo"], repo)
        runs = must(["rev-list", "--count", "main..custody/demo"], repo)
        landed = {"landed": True, "applied": [f.path for f in second.files]}
        beat("landed-atomically", change_set=second.id, state=state_of(second.id),
             **{"landed": True, "applied": landed["applied"],
                "branch": "custody/demo", "commit": head, "commits_ahead_of_main": runs,
                "file_on_the_branch": must(["show", "custody/demo:values.py"], repo)})

        receipt = {
            "schema": RECEIPT_SCHEMA,
            "demo": DEMO,
            "target_repository": str(repo),
            "stores": {
                "changesets": str(store / "changesets"),
                "ledger": str(store / "reviews.jsonl"),
                "workspaces": str(store / "workspaces"),
            },
            "beats": beats,
            "proven": all([
                all(r.get("refused") for r in refused),
                verdict.reviewer == REVIEWER,
                not stale["landed"] and stale["check"] == "verify_current",
                landed["landed"] and runs == "1",
            ]),
        }
        payload = json.dumps(receipt, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(payload + "\n", encoding="utf-8")
        print("\n" + payload)
        return 0 if receipt["proven"] else 1
    finally:
        if not args.keep and not args.store:
            shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
