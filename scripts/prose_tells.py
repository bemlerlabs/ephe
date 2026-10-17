#!/usr/bin/env python3
"""Prose tells: the generated-code tells of `AGENTS.md` "Writing quality", counted and held.

`scripts/prose_inventory.py` finds the forbidden shapes in one file. This script runs
them over tracked source under the shipped roots, prints the census, and compares the
result with `scripts/prose-tells-baseline.json`. Owner rule 2026-10-09: the repository
has to read as hand-written to a reader with no context, and a rule nobody measures
stays a wish.

The ratchet is per file, like the language gate. A total can fall while one file gets
worse, and only the per-file comparison names the file that regressed. `--update`
therefore only ever lowers: a tree that grew cannot be made to pass by re-measuring it.

Three classes are decided across files: the header wording, the banner wording in
`scripts/prose_wide.py`, and the long prose run counted as comment voice. `--wide` adds the
wide tier to the number and `--update --wide` scopes a baseline for it; a baseline written
in one scope refuses to be compared in the other, since the two totals differ.

Exit codes: 0 at or below the baseline, 1 with `--strict` when a file grew, 2 when the
baseline or the instrument cannot be trusted.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import language_inventory as inventory  # noqa: E402  (path bootstrap above)
import prose_inventory as rules  # noqa: E402
import prose_wide as wide  # noqa: E402
import language_gate as gate  # noqa: E402

REPO_ROOT = SCRIPTS_DIR.parent
BASELINE_DEFAULT = SCRIPTS_DIR / "prose-tells-baseline.json"
POLICY = "prose-tells-ratchet"
VERSION = 1
BASELINE_KEYS = {"policy", "version", "instrument", "total", "files", "scope"}
UPDATE_HINT = f"python3 {BASELINE_DEFAULT.parent.name}/{Path(__file__).name} --update"
PROSE_ROOTS = ("core", "server", "app/src", "scripts", "ephe_cli.py", "tests", ".github")
RATCHET_SCOPE = "ratchet"
MEASURED_SCOPE = "measured"

HEADER_MIN_WORDS = 3
HEADER_MIN_CHARS = 20
HEADER_MIN_ROW = 8
# A prose run this long is a voice, and this tree has 176 files carrying one
# (2026-10-09). It is measured for the census document and kept out of the ratchet,
# because the law says what a comment must carry, never how long it may run.
ESSAY_LINES = 6


def header_of(rel: str, text: str) -> str | None:
    """The first wording of a file, normalized, for the repetition detector."""
    for row, _kind, chunk in rules.chunks_of(rel, text):
        if row > HEADER_MIN_ROW:
            break
        for line in chunk.splitlines():
            body = rules.strip_rule_runs(rules.marker_body(line)).strip("\"'` ")
            if not body or rules.HEADER_SKIP.match(body):
                continue
            if len(body) < HEADER_MIN_CHARS or len(rules.words(body)) < HEADER_MIN_WORDS:
                continue
            return body[:160].casefold()
    return None


def header_duplicates(texts: dict[str, str]) -> set[str]:
    """Files whose header wording already appeared in an earlier file.

    Repetition only, no judgement of content. A banner carried by N files yields N-1 of
    these, and the survivor is the first path in sort order.
    """
    seen: set[str] = set()
    dupes: set[str] = set()
    for rel in sorted(texts):
        key = header_of(rel, texts[rel])
        if key is None:
            continue
        if key in seen:
            dupes.add(rel)
        else:
            seen.add(key)
    return dupes


def essay_blocks(rel: str, text: str) -> int:
    """Contiguous runs of `ESSAY_LINES` or more comment lines in this file.

    A docstring is documentation and stays out of this count; the voice the census asks
    about is the paragraph a reader finds between statements. Python gives one chunk per
    `#` line, so a run has to be merged across chunk edges, and it counts once however
    long it runs.
    """
    prose: set[int] = set()
    for row, kind, chunk in rules.chunks_of(rel, text):
        if kind == "docstring":
            continue
        prose.update(row + offset for offset in range(len(chunk.splitlines())))
    runs, previous, length = 0, 0, 0
    for row in sorted(prose):
        length = length + 1 if row == previous + 1 else 1
        runs += length == ESSAY_LINES
        previous = row
    return runs


def texts_of(files: Iterable[str], read_text: Callable[[str], str]) -> dict[str, str]:
    """The contents of exactly the paths `is_scannable` accepts.

    A tracked path missing from the worktree is skipped, the way `language_gate.measure`
    skips it: a shared checkout is not always clean.
    """
    out: dict[str, str] = {}
    for rel in files:
        if not inventory.is_scannable(rel):
            continue
        try:
            out[rel] = read_text(rel)
        except (OSError, UnicodeDecodeError):
            continue
    return out


def score(texts: dict[str, str]) -> tuple[dict[str, int], Counter[str], dict[str, int]]:
    """Findings per path, per class, and the prose-run count, from contents read once."""
    counts: dict[str, int] = {}
    by_class: Counter[str] = Counter()
    essays: dict[str, int] = {}
    for rel, text in texts.items():
        found = rules.findings_for(rel, text)
        if found:
            counts[rel] = len(found)
            by_class.update(f.cls for f in found)
        runs = essay_blocks(rel, text)
        if runs:
            essays[rel] = runs
    for rel in header_duplicates(texts):
        counts[rel] = counts.get(rel, 0) + 1
        by_class[rules.REPEATED_HEADER] += 1
    return counts, by_class, essays


def counts_for(files: Iterable[str], read_text: Callable[[str], str]) -> dict[str, int]:
    """Tell findings per tracked path.

    `read_text` is injected so a test scores a fixture tree without a checkout, the way
    `language_inventory.counts_for` does. A path with no finding is left out, so an
    empty result means nothing was found; it is no evidence that nothing was read.
    """
    return score(texts_of(files, read_text))[0]


def tracked(root: Path) -> list[str]:
    done = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--", *PROSE_ROOTS],
        capture_output=True, text=True, check=True,
    )
    return done.stdout.splitlines()


def refuse_orphan_entries(baseline: dict[str, int], tracked_paths: list[str]) -> None:
    """A baseline entry has to name a path the tree holds.

    `evaluate` compares the union of the baseline and the measured keys, so an entry whose file was
    deleted scores `old = N, new = 0` and lands in `lowered` rather than in `regressions`. Left in
    place it is a budget with a name: the path can come back carrying N tells and the per-file
    ratchet calls the tree clean, because the number it is judged against was earned by a file
    nobody measured since. The verdict is `GateError`, so the caller exits 2 — the instrument
    cannot be trusted, which is a different answer from "the tree is over budget" and from "clean".

    Mode split, stated because the two language instruments differ here: this gate has no staged
    mode at all, it always measures the tracked tree under `PROSE_ROOTS`, so every entry it reads
    should name a path that exists. `scripts/language_gate.py` carries the same rule and must not
    apply it under `--staged`, where the scope is the few paths one commit happens to carry.
    `--update` is the way out, and the only way it lowers: prune the entry while the tree really is
    cleaner, and the recreated path starts from zero.
    """
    present = set(tracked_paths)
    orphans = sorted(rel for rel in baseline if rel not in present)
    if orphans:
        raise gate.GateError(
            f"baseline names {len(orphans)} path(s) the tree does not hold: "
            + ", ".join(orphans[:5])
            + (", …" if len(orphans) > 5 else "")
            + " — prune them with --update; an entry for a deleted file is a budget for whoever "
            "recreates it"
        )


def group_by_dir(counts: dict[str, int]) -> dict[str, list[tuple[str, int]]]:
    per_dir: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for rel, hits in counts.items():
        parts = Path(rel).parts
        top = "/".join(parts[:2]) if len(parts) > 2 else parts[0]
        per_dir[top].append((rel, hits))
    return per_dir


def load_baseline(path: Path, *, wide: bool = False) -> dict[str, int]:
    """Read the tell baseline; an unknown key or a protected path makes it unreadable."""
    if not path.exists():
        raise gate.GateError(f"no baseline at {path.name} (looked in {path.parent}); create it with {UPDATE_HINT}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise gate.GateError(f"baseline {path} cannot be read: {exc}") from exc
    if not isinstance(raw, dict):
        raise gate.GateError(f"baseline {path} must be a JSON object")
    unknown = sorted(set(raw) - BASELINE_KEYS)
    if unknown:
        raise gate.GateError(
            f"baseline {path} carries unknown key(s) {', '.join(unknown)}. This gate has no exemption "
            f"list; remove the key, or lower the baseline with {UPDATE_HINT}."
        )
    if raw.get("policy") != POLICY or raw.get("version") != VERSION:
        raise gate.GateError(
            f"baseline {path} is policy {raw.get('policy')!r} version {raw.get('version')!r}; this gate "
            f"speaks {POLICY!r} version {VERSION}"
        )
    # A wide baseline holds numbers the eight-class run cannot produce, and reading it the
    # other way round would report growth as silence.
    scope = raw.get("scope", RATCHET_SCOPE)
    if scope != (MEASURED_SCOPE if wide else RATCHET_SCOPE):
        raise gate.GateError(
            f"baseline {path} is scoped {scope!r}; a {'--wide' if wide else 'ratchet'} run reads "
            f"{MEASURED_SCOPE if wide else RATCHET_SCOPE!r}. Pass the matching flag, or write the "
            f"baseline again with it."
        )
    files = raw.get("files")
    if not isinstance(files, dict):
        raise gate.GateError(f"baseline {path} has no `files` mapping")
    clean: dict[str, int] = {}
    for rel, hits in files.items():
        if not isinstance(rel, str) or isinstance(hits, bool) or not isinstance(hits, int) or hits < 0:
            raise gate.GateError(f"baseline {path} entry {rel!r} is not a non-negative finding count")
        if rel.startswith(inventory.PROTECTED_PREFIXES):
            raise gate.GateError(
                f"baseline {path} records the protected path {rel!r}; the census never measures it "
                "and must never be told it did"
            )
        clean[rel] = hits
    return clean


def evaluate(baseline: dict[str, int], measured: dict[str, int]) -> "gate.Verdict":
    """The same verdict shape as the language gate — one instrument's `report` reads the other's."""
    regressions: list[tuple[str, int, int]] = []
    lowered: list[tuple[str, int, int]] = []
    for rel in sorted(set(baseline) | set(measured)):
        old, new = baseline.get(rel, 0), measured.get(rel, 0)
        if new > old:
            regressions.append((rel, old, new))
        elif new < old:
            lowered.append((rel, old, new))
    return {
        "regressions": regressions,
        "lowered": lowered,
        "baseline_total": sum(baseline.values()),
        "measured_total": sum(measured.values()),
        "measured_files": len(measured),
    }


def report(result: 'gate.Verdict') -> tuple[int, list[str]]:
    regressions, lowered = result["regressions"], result["lowered"]
    total, baseline_total = result["measured_total"], result["baseline_total"]
    lines: list[str] = []
    if regressions:
        grew = sum(new - old for _, old, new in regressions)
        lines.append(f"prose-tells gate: FAIL — generated-code tells grew in {len(regressions)} file(s) (+{grew})")
        for rel, old, new in regressions:
            lines.append(f"  {rel}: {old} -> {new} (+{new - old})")
        lines.append(f"  total {baseline_total} -> {total} tells")
        lines.append(
            f"Rewrite those lines by hand. Do not run `{UPDATE_HINT}` to cover them; --update only "
            "ever lowers this baseline."
        )
        return 1, lines
    if lowered:
        lines.append("prose-tells gate: PASS — no file grew past the baseline")
        lines.append(f"  total {baseline_total} -> {total} tells ({result['measured_files']} files still carry one)")
        lines.append(f"  {len(lowered)} file(s) sit below their baseline entry: the baseline can be lowered")
        lines.append(f"  {UPDATE_HINT}")
        return 0, lines
    lines.append("prose-tells gate: PASS — the tree matches the baseline")
    lines.append(f"  total {total} tells over {result['measured_files']} files")
    return 0, lines


def write_baseline(path: Path, measured: dict[str, int], *, wide: bool = False) -> None:
    """Freeze a measurement. Sorted keys, no timestamp, so the file diffs cleanly."""
    payload = {
        "policy": POLICY,
        "version": VERSION,
        "instrument": "scripts/prose_tells.py",
        "scope": MEASURED_SCOPE if wide else RATCHET_SCOPE,
        "total": sum(measured.values()),
        "files": measured,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def update_baseline(path: Path, measured: dict[str, int], *, wide: bool = False) -> int:
    """Tighten the baseline to the current tree, never loosen it."""
    if not path.exists():
        write_baseline(path, measured, wide=wide)
        label = "measured" if wide else "ratchet"
        print(f"prose-tells: baseline created — {sum(measured.values())} tells over {len(measured)} files, {label} scope ({path.name})")
        return 0
    before = load_baseline(path, wide=wide)
    higher = [(rel, before.get(rel, 0), hits) for rel, hits in measured.items() if hits > before.get(rel, 0)]
    if higher:
        print(
            f"prose-tells: FAIL — baseline was not written; --update only lowers it "
            f"({len(higher)} file(s) would rise)",
            file=sys.stderr,
        )
        for rel, old, new in sorted(higher):
            print(f"  {rel}: {old} -> {new} (+{new - old})", file=sys.stderr)
        print("  rewrite the prose in plain English first, then run the command above again", file=sys.stderr)
        return 1
    write_baseline(path, measured, wide=wide)
    dropped = sum(before.values()) - sum(measured.values())
    print(
        f"prose-tells: baseline lowered — {sum(before.values())} -> {sum(measured.values())} tells "
        f"({dropped} fewer, {len(set(before) - set(measured))} file(s) now clean)"
    )
    return 0


def measure(
    root: Path,
    *,
    list_files: Callable[[], list[str]] | None = None,
    read_text: Callable[[str], str] | None = None,
) -> tuple[dict[str, int], Counter[str], dict[str, int]]:
    return score(texts_of(
        list_files() if list_files else tracked(root),
        read_text if read_text else (lambda rel: (root / rel).read_text(encoding="utf-8")),
    ))


def main(
    argv: list[str] | None = None,
    *,
    list_files: Callable[[], list[str]] | None = None,
    read_text: Callable[[str], str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--top", type=int, default=0, help="show only the N busiest directories")
    parser.add_argument("--files", action="store_true", help="list every file, not just the leaders")
    parser.add_argument("--porcelain", action="store_true", help="only the totals, for gates")
    parser.add_argument("--strict", action="store_true", help="exit 1 when a file grew past the baseline")
    parser.add_argument("--update", action="store_true", help="lower the baseline to the tree (refuses to raise it)")
    parser.add_argument("--wide", action="store_true", help="count and gate the wide tier too")
    parser.add_argument("--banners", action="store_true", help="list the repeated banner wordings")
    parser.add_argument("--baseline", type=Path, default=BASELINE_DEFAULT, help="committed baseline")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="tree to measure")
    args = parser.parse_args(argv)

    try:
        # The census shares the language instrument's protected paths, so it shares the
        # proof that they stay product-only and never reach a guarded root.
        gate.checked_protected_prefixes()
        paths = list_files() if list_files else tracked(args.root)
        texts = texts_of(
            paths,
            read_text if read_text else (lambda rel: (args.root / rel).read_text(encoding="utf-8")),
        )
        counts, by_class, essays = score(texts)
        groups: dict[str, list[str]] = {}
        wide_by_class: Counter[str] = Counter()
        if args.wide or args.banners:
            wide_counts, wide_by_class, groups = wide.wide_score(texts)
            if args.wide:
                counts = wide.merge(counts, wide_counts)
        if args.update:
            return update_baseline(args.baseline, counts, wide=args.wide)
        # A census run asks the baseline no question, so --wide can measure before anyone gates.
        baseline = load_baseline(args.baseline, wide=args.wide) if args.strict else {}
        if args.strict:
            refuse_orphan_entries(baseline, paths)
    except gate.GateError as exc:
        print(f"prose-tells gate: ERROR — {exc}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() if isinstance(exc.stderr, str) else exc
        print(f"prose-tells gate: ERROR — git ls-files failed: {detail}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"prose-tells gate: ERROR — {exc}", file=sys.stderr)
        return 2

    if args.strict:
        code, lines = report(evaluate(baseline, counts))
        print("\n".join(lines))
        return code
    if not args.porcelain:
        ranked = sorted(group_by_dir(counts).items(), key=lambda kv: -sum(h for _, h in kv[1]))
        if args.top:
            ranked = ranked[: args.top]
        for directory, rows in ranked:
            print(f"{sum(h for _, h in rows):6d} tells  {len(rows):4d} files  {directory}")
            shown = rows if args.files else sorted(rows, key=lambda r: -r[1])[:4]
            for rel, hits in sorted(shown, key=lambda r: -r[1]):
                print(f"           {hits:4d}  {rel}")
        print()
        for cls in rules.CLASSES:
            print(f"{by_class.get(cls, 0):6d}  {cls}")
        print(f"{sum(essays.values()):6d}  prose runs of {ESSAY_LINES}+ lines (voice, counted, not ratcheted)")
        wide.describe(groups, wide_by_class, classes=args.wide, banners=args.banners)
        print()
    print(f"TOTAL\t{len(counts)} files\t{sum(counts.values())} tells")
    return 0


if __name__ == "__main__":
    sys.exit(main())
