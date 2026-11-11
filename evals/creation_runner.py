"""Ephe · Creator — the runner that grades a case's turn and its end state (task #51d).
evals/creation_runner.py

A case in `evals/creation/cases.jsonl` has two halves. The turn half — `input`, `expect`,
`mode`, `privileges`, `tools` — is graded by `core.plugin_golden.grade` against a
transcript the engine produced. The end-state half is what the harness reads back from
the bundle the turn left behind, graded by `evals.creation_checks` (offline) and
`evals.creation_checks_browser` (engine).

It prints a receipt.
category. A category whose cases cannot pass is work in the plan with its transcript
attached, not copy in a marketing page — which is the claim the set exists to keep
honest.

The runner does not spend an engine itself. A transcript is handed in, and a staging
root is handed in, and the browser half is handed a session that already booted. What
spends the engine is task #51e; what this module owns is the grading and the receipt.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evals.creation_checks import (
    Verdict,
    run_offline_checks,
    verdict_rows,
)
from evals.creation_checks_browser import SurfaceSession, browser_verdicts
from evals.creation_eval import CATEGORIES, load_cases
from evals.creation_transcript import adopt_declaration

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CaseResult:
    """One case graded: its turn half, its end-state half, and the checks that did not run."""

    case_id: str
    category: str
    turn_ok: bool | None
    turn_detail: str
    verdicts: list[Verdict]
    not_run: list[str]

    @property
    def end_state_ok(self) -> bool:
        return all(v.ok for v in self.verdicts)

    @property
    def ok(self) -> bool:
        """A case passes when its turn passed (if graded) and every check that ran passed."""
        if self.turn_ok is not None and not self.turn_ok:
            return False
        return self.end_state_ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "turn_ok": self.turn_ok,
            "turn_detail": self.turn_detail,
            "checks": verdict_rows(self.verdicts),
            "not_run": list(self.not_run),
        }


@dataclass(frozen=True)
class Receipt:
    """The per-category rates the receipt prints, and the cases that carry them."""

    results: list[CaseResult]
    engine_skipped: str = ""

    @property
    def categories(self) -> dict[str, dict[str, int]]:
        """Pass and total per category, so the rate is `pass / total`."""
        out: dict[str, dict[str, int]] = {}
        for category in CATEGORIES:
            out[category] = {"pass": 0, "total": 0}
        for result in self.results:
            bucket = out.setdefault(result.category, {"pass": 0, "total": 0})
            bucket["total"] += 1
            if result.ok:
                bucket["pass"] += 1
        return out

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.ok)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "categories": self.categories,
            "engine_skipped": self.engine_skipped,
            "cases": [r.to_dict() for r in self.results],
        }

    def format(self) -> str:
        """The human-readable receipt: one line per category, then the cases that failed."""
        lines: list[str] = []
        lines.append(f"{self.passed}/{self.total} creation cases passed")
        if self.engine_skipped:
            lines.append(f"  engine: {self.engine_skipped}")
        for category, bucket in self.categories.items():
            if bucket["total"] == 0:
                continue
            rate = bucket["pass"] / bucket["total"]
            lines.append(f"  {category:<12} {bucket['pass']}/{bucket['total']}  ({rate:.0%})")
        failures = [r for r in self.results if not r.ok]
        if failures:
            lines.append("")
            lines.append(f"{len(failures)} case(s) failed:")
            for result in failures:
                lines.append(f"  - {result.case_id} ({result.category})")
                if result.turn_ok is not None and not result.turn_ok:
                    lines.append(f"      turn: {result.turn_detail}")
                for verdict in result.verdicts:
                    if not verdict.ok:
                        lines.append(f"      {verdict.check}: {verdict.detail}")
                if result.not_run:
                    lines.append(f"      not run: {', '.join(result.not_run)}")
        return "\n".join(lines)


def grade_turn(case: dict, transcript: str) -> tuple[bool, str]:
    """The turn half, graded by the golden contract's own reader.

    A case whose transcript says the tool was used and the tool did not refuse is a pass;
    a case whose transcript says the tool refused with the reason the case expected is a
    pass for a refusal case. A reasonless refusal case asks only that the named call did
    not run, because the Creator guard withholds a call the turn holds no grant for
    (`core.tools.creator_guard.filter_offer`) and the turn names the missing step in
    prose instead. Everything else is a fail with the transcript's own words.
    """
    from core.plugin_golden import grade

    ok = grade(case, transcript)
    if ok:
        return True, "the transcript satisfies the expect block"
    kind = case.get("expect", {}).get("kind", "unknown")
    return False, f"the transcript does not satisfy expect.kind={kind!r}"


def install_and_enable(staging_root: Path, name: str) -> str:
    """Install one staged bundle into the run's home and hold the enable switch.

    `install_plugin_bundle` lands a local bundle switched off on purpose — the switch is
    the person's — and a switched-off bundle is a coded 404 at the mount route. A harness
    that measures a mount therefore has to hold the switch itself, and it says who did:
    `actor="eval"` is the same seam the browser test uses.
    """
    import shutil

    from core import plugin_runtime
    from core.tools import creator_tools

    # `take_staged_bundles` copies a turn's bundle out of the run home into the case's
    # own folder, and `install_plugin_bundle(name)` reads `<config>/creator/plugins/<name>`.
    # The bytes therefore go back into the home the product reads before the install.
    source = Path(staging_root) / str(name)
    target = creator_tools.bundle_dir(str(name))
    if source.is_dir() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)

    answer = json.loads(creator_tools.install_plugin_bundle(str(name)))
    status = answer.get("status") if isinstance(answer, dict) else None
    if status != "installed":
        raise RuntimeError(f"could not install the staged bundle {name!r}: {answer}")
    plugin_runtime.lifecycle().set_enabled(str(name), True, actor="eval")
    plugin_runtime.invalidate_ownership_cache()
    return str(name)


def _staged_bundle(staging_root: Path) -> tuple[str, str]:
    """The one staged bundle's name, and why there is no single name when there is not.

    Zero and two bundles are different facts: `run5` staged two and the old helper answered
    `""` for both, so the receipt said "no staged bundle to mount" about a turn that staged
    two. An instrument must not assert what it did not read.
    """
    from evals.creation_checks import staged_bundles

    bundles = staged_bundles(staging_root)
    if len(bundles) == 1:
        return bundles[0].name, ""
    if not bundles:
        return "", "no staged bundle to mount"
    names = ", ".join(bundle.name for bundle in bundles)
    return "", f"the turn staged {len(bundles)} bundles, not one: {names}"


def grade_end_state(
    case: dict,
    staging_root: Path,
    session: SurfaceSession | None = None,
    installed: str = "",
) -> tuple[list[Verdict], list[str]]:
    """The end-state half: offline checks first, then the browser checks if a session was given.

    A session that cannot boot is reported by name as skipped, and the browser rows
    arrive as `not_run` — a rate that counted a green row nobody measured would be the
    same defect this set exists to prevent.
    """
    offline, not_run = run_offline_checks(case, staging_root)
    if not session or not not_run:
        return offline, not_run
    plugin, why = _staged_bundle(staging_root)
    if not installed:
        detail = (
            why
            if not plugin
            else f"the turn staged a bundle and never installed it: {plugin}"
        )
        browser = [Verdict(name, False, detail) for name in not_run]
        return offline + browser, []
    if not plugin:
        browser = [Verdict(name, False, why) for name in not_run]
        return offline + browser, []
    try:
        load, reload = session.evidence(installed)
    except Exception as exc:
        browser = [Verdict(name, False, f"engine unavailable: {exc}") for name in not_run]
        return offline + browser, []
    return offline + browser_verdicts(case, plugin, load, reload), []


def run_case(
    case: dict,
    staging_root: Path,
    transcript: str | None = None,
    session: SurfaceSession | None = None,
    installed: str = "",
) -> CaseResult:
    """Grade one case: its turn (if a transcript was given) and its end state."""
    case_id = case["id"]
    category = case.get("category", "unknown")
    turn_ok: bool | None = None
    turn_detail = "no transcript graded"
    if transcript is not None:
        turn_ok, turn_detail = grade_turn(case, transcript)
    verdicts, not_run = grade_end_state(case, staging_root, session, installed)
    return CaseResult(
        case_id=case_id,
        category=category,
        turn_ok=turn_ok,
        turn_detail=turn_detail,
        verdicts=verdicts,
        not_run=not_run,
    )


def run_set(
    cases: list[dict],
    staging_roots: dict[str, Path],
    transcripts: dict[str, str] | None = None,
    session: SurfaceSession | None = None,
    engine_skipped: str = "",
    config: Path | None = None,
) -> Receipt:
    """Grade every case and fold the results into one receipt.

    `staging_roots` is keyed by case id: the directory the turn left behind for that
    case. A case whose id is missing from the map is graded with an empty staging root,
    which is the same end state as a turn that wrote nothing — the offline checks will
    report it as such.
    """
    transcripts = transcripts or {}
    results: list[CaseResult] = []
    installing = session is not None and config is not None
    for case in cases:
        cid = case["id"]
        root = staging_roots.get(cid, Path("/nonexistent-creation-eval-staging"))
        transcript = transcripts.get(cid)
        installed = ""
        if installing:
            name, _why = _staged_bundle(root)
            if name:
                installed = install_and_enable(root, name)
        results.append(run_case(case, root, transcript, session, installed))
    return Receipt(results=results, engine_skipped=engine_skipped)


def main(argv: list[str] | None = None) -> int:
    """The set's own runner: read the cases, print the receipt.

    Without `--staging` the runner grades the turn half only (no end state to read),
    which is what `--json` prints for a receipt the engine half will later fill in.
    With `--staging` it reads one directory per case id from a JSON map and grades the
    offline end state; the browser half needs `--browser` to boot an engine.
    """
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", type=Path, help="the JSONL set to read")
    parser.add_argument(
        "--staging", type=Path,
        help="a JSON file mapping case ids to staging directories",
    )
    parser.add_argument(
        "--transcripts", type=Path,
        help="a JSON file mapping case ids to engine transcripts",
    )
    parser.add_argument(
        "--browser", action="store_true",
        help="boot a browser session for the three engine rows",
    )
    parser.add_argument(
        "--config", type=Path,
        help="the run-scoped config home the browser half boots against (required with --browser)",
    )
    parser.add_argument(
        "--engine", default="chromium",
        help="the engine to boot when --browser is set (default: chromium)",
    )
    parser.add_argument("--json", action="store_true", help="print the receipt as JSON")
    args = parser.parse_args(argv)

    # The offer a case's grant produced was built in the run home, so the check that
    # compares it with the guard has to read that home's declaration - not the operator's
    # portfolio, which is what the process would otherwise scan (class 4d, 2026-11-11).
    if args.config is not None:
        adopted = adopt_declaration(args.config)
        if adopted:
            print(f"declaration: {adopted}", file=sys.stderr)
    cases = load_cases(args.cases) if args.cases else load_cases()
    staging_roots: dict[str, Path] = {}
    if args.staging:
        raw = json.loads(args.staging.read_text(encoding="utf-8"))
        staging_roots = {cid: Path(path) for cid, path in raw.items()}
    transcripts: dict[str, str] = {}
    if args.transcripts:
        transcripts = json.loads(args.transcripts.read_text(encoding="utf-8"))

    session: SurfaceSession | None = None
    engine_skipped = ""
    if args.browser and args.config is None:
        print(
            "--browser needs --config <dir>: without a run-scoped home the mount would "
            "read the operator's own ~/.ephe and grade a state this run does not own",
            file=sys.stderr,
        )
        return 2
    if args.browser:
        args.config.mkdir(parents=True, exist_ok=True)
        session = SurfaceSession(engine=args.engine, config=args.config)
        try:
            session.start()
        except Exception as exc:
            engine_skipped = f"{args.engine} unavailable: {exc}"
            session = None

    try:
        receipt = run_set(
            cases, staging_roots, transcripts, session, engine_skipped, args.config
        )
    finally:
        if session is not None:
            session.stop()

    if args.json:
        print(json.dumps(receipt.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(receipt.format())
    return 0 if receipt.passed == receipt.total else 1


if __name__ == "__main__":
    raise SystemExit(main())
