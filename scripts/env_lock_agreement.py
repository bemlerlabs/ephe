#!/usr/bin/env python3
"""Say whether the interpreter running Ephe is the interpreter the lock describes.

`uv.lock` is the version the project was measured against. An environment that quietly
drifted from it runs different code under the same test names, which is the failure mode no
test in this suite can see: a passing suite proves the installed versions pass, not the
pinned ones. This file compares the two and refuses on the product graph.

Columns, and why each behaves as it does:

* `product` — the transitive closure of `[project.dependencies]` plus every extra the product
  imports at runtime. A drift here refuses. Dev-only extras are the two named in `DEV_EXTRAS`;
  any extra not named there counts as product, because an extra nobody classified is held to
  the lock rather than excused by an omission in this file.
* `dev` — the closure of `dev` and `bench`. Those two extras are the suite's own tools
  (`pytest`, `ruff`, `httpx`); a drift there is a fact about a laptop and says nothing about
  what ships, so it is printed and never refuses. `tests/test_env_lock_agreement.py` pins that split.
* `undeclared` — installed, in no closure. A lock cannot demand the absence of something, so
  this never refuses on its own; it is the column that names `pip` in a venv nobody declared
  it in, and the reason a removal has to be argued rather than measured.

Two kinds of absence, because an optional feature that is not installed is a legitimate state
while an installed one is running:

* `missing` — an always-on dependency is not installed at all. Refuses.
* `absent` — a product extra's package is not installed. Printed only; not installing `[voice]`
  is a user's choice, installing a wrong version of it is not.

A dependency the lock admits only under a `marker` is platform-conditional, and asking the wrong
question there manufactures a missing package: `uv.lock` writes the root's own requirements as
one edge per resolution environment (`python_full_version < '3.12'` and `>= '3.12'`), so a naive
reader sees `numpy` behind two markers and calls a hard dependency conditional. Markers are
therefore evaluated against the interpreter running this file, with `packaging.markers`, which
the lock itself carries. Without `packaging` every conditional edge is held to the lock instead
of excused — a stricter verdict, never a cleaner one — and the run says so on its face.

The boundary this instrument cannot cross: it reads one environment — the interpreter that runs
it — and the one lock file it is pointed at, so a second venv, a `uv tool` environment, the
system Python or a Homebrew Python is invisible to it, and which environment is judged is
decided by how the script is invoked; the script itself carries no switch for it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

try:
    import tomllib
except ModuleNotFoundError:  # the 3.10 shape the tree's TOML readers still carry
    import tomli as tomllib  # type: ignore[no-redef]

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent

#: The extras that carry nothing but the tools the suite runs on. Everything else is held to
#: the lock, including extras this file has not heard of.
DEV_EXTRAS = frozenset({"dev", "bench"})

#: Findings that refuse. `absent`, `gated`, `gated-drift`, `dev-drift`, `dev-missing`,
#: `undeclared` and `shadow` are printed without refusing, each for the reason named at its
#: producing site.
REFUSING = frozenset({"drift", "missing"})

#: Printed in this order, hardest first.
KIND_ORDER = ("drift", "missing", "absent", "gated", "gated-drift", "dev-drift", "dev-missing",
              "undeclared", "shadow")

EXIT_OK = 0
EXIT_DIFFERS = 1
PRINTED_DEFAULT = 60


def resolution_environment(python_full_version: str) -> dict[str, str]:
    """One PEP 508 environment at a given interpreter version, for marker evaluation.

    `packaging` merges a partial context over the running interpreter instead of deriving the
    variables from the one supplied, so a caller that only sets `python_full_version` still gets
    the host's `python_version` and `implementation_version` under a marker that reads those. The
    three version variables therefore move together; the platform half stays the machine's, which
    is the half this instrument cannot know anything about anyway.
    """
    parts = python_full_version.split(".")
    major, minor = parts[0], parts[1] if len(parts) > 1 else "0"
    return {
        "python_full_version": python_full_version,
        "python_version": f"{major}.{minor}",
        "implementation_version": python_full_version,
    }


def marker_admits(
    environment: Mapping[str, str] | None = None,
) -> tuple[Callable[[str], bool], bool]:
    """A checker for lock markers, and whether real evaluation was possible.

    Without `packaging` every marker answers yes: the run then holds conditional edges to the
    lock rather than excusing them, so the failure mode of a missing library is a stricter
    verdict, never a cleaner one.

    `environment` is the PEP 508 context markers are evaluated against. Left alone it is the
    interpreter running this process, which is the right answer for the shipped gate — the one
    environment it judges is the one whose distributions it compared. A test passes one of
    `resolution_environment` instead, so a claim about a lock does not depend on the interpreter
    that happens to execute it.
    """
    try:
        from packaging.markers import Marker
    except ImportError:
        return (lambda _text: True), False
    cache: dict[str, bool] = {}

    def admits(text: str) -> bool:
        verdict = cache.get(text)
        if verdict is None:
            try:
                verdict = Marker(text).evaluate(None if environment is None else dict(environment))
            except Exception:
                verdict = True  # an unreadable marker keeps the edge held to the lock
            cache[text] = verdict
        return verdict

    return admits, True


def canonical(name: str) -> str:
    """PEP 503 name spelling, so `Python_DateUtil` and `python-dateutil` are one package."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass(frozen=True)
class Edge:
    """One lock edge: a required package, the extras of it that were asked for, its marker."""

    name: str
    extras: tuple[str, ...] = ()
    marker: str | None = None


@dataclass(frozen=True)
class Lock:
    """The pins and the graph of one `uv.lock`."""

    path: str
    root: str
    versions: Mapping[str, str]
    requires: Mapping[str, tuple[Edge, ...]]
    optional: Mapping[str, Mapping[str, tuple[Edge, ...]]]

    def version_of(self, name: str) -> str | None:
        return self.versions.get(name)


def _edges(rows: Iterable[Mapping]) -> tuple[Edge, ...]:
    out: list[Edge] = []
    for row in rows:
        extras = row.get("extra") or row.get("extras") or ()
        if isinstance(extras, str):
            extras = (extras,)
        out.append(Edge(canonical(str(row["name"])), tuple(extras), row.get("marker")))
    return tuple(out)


def read_lock_text(text: str, path: str = "<lock>") -> Lock:
    """Parse a `uv.lock` body. Only names, versions and edges are read — no hash is required."""
    body = tomllib.loads(text)
    versions: dict[str, str] = {}
    requires: dict[str, tuple[Edge, ...]] = {}
    optional: dict[str, Mapping[str, tuple[Edge, ...]]] = {}
    root = ""
    for package in body.get("package", []):
        name = canonical(str(package["name"]))
        versions[name] = str(package["version"])
        requires[name] = _edges(package.get("dependencies", []))
        optional[name] = {
            str(extra): _edges(rows) for extra, rows in (package.get("optional-dependencies") or {}).items()
        }
        source = package.get("source") or {}
        if "editable" in source or "virtual" in source:
            root = name
    if not root:
        raise ValueError(f"{path}: no editable or virtual root package — this is not the project's lock")
    return Lock(path, root, versions, requires, optional)


def read_lock(path: Path) -> Lock:
    return read_lock_text(path.read_text(encoding="utf-8"), str(path))


def closure(lock: Lock, roots: Iterable[Edge], admits: Callable[[str], bool] | None = None) -> tuple[set[str], set[str]]:
    """Walk the graph from `roots`: names required outright, and names only a marker admits.

    A name reached by one plain edge is required even when another edge into it carries a
    marker, so the plain set wins: `gated` is what only conditional edges brought in. `admits`
    answers whether a marker holds here; with none given, every edge is treated as required.
    """

    check = admits if admits is not None else (lambda _text: True)
    plain: set[str] = set()
    gated: set[str] = set()
    queue: list[Edge] = list(roots)
    asked: set[tuple[str, tuple[str, ...], str | None]] = set()
    while queue:
        edge = queue.pop()
        # The marker belongs in the walk key. uv writes one requirement once per resolution
        # environment, so `numpy` arrives as two edges with the same name and extras and
        # different markers; keyed without the marker, the second edge is dismissed as already
        # asked and the one edge that happens to pop first decides whether the package counts
        # as product or as conditional.
        key = (edge.name, edge.extras, edge.marker)
        if key in asked:
            continue
        asked.add(key)
        (plain if edge.marker is None or check(edge.marker) else gated).add(edge.name)
        for child in lock.requires.get(edge.name, ()):
            queue.append(child)
        for extra in edge.extras:
            for child in lock.optional.get(edge.name, {}).get(extra, ()):
                queue.append(child)
    return plain, gated - plain


def product_and_dev_roots(lock: Lock) -> tuple[list[Edge], list[Edge], dict[str, list[Edge]]]:
    """Split the root's extras into the dev tools and everything the product runs."""
    extras = lock.optional.get(lock.root, {})
    dev: list[Edge] = []
    product: list[Edge] = []
    unknown: dict[str, list[Edge]] = {}
    for extra, rows in sorted(extras.items()):
        if extra in DEV_EXTRAS:
            dev.extend(rows)
        else:
            product.extend(rows)
            unknown[extra] = list(rows)
    return list(lock.requires.get(lock.root, ())), dev, unknown


@dataclass(frozen=True)
class Finding:
    """One disagreement: what is installed, what the lock pins, and which column it belongs to."""

    name: str
    kind: str
    installed: str | None
    pinned: str | None

    def line(self) -> str:
        return f"  {self.kind:<11} {self.name:<28} installed {self.installed or '—':<12} lock {self.pinned or '—'}"


def compare(
    lock: Lock,
    installed: Mapping[str, str],
    shadows: Iterable[str] = (),
    admits: Callable[[str], bool] | None = None,
) -> list[Finding]:
    """Every disagreement between one lock and one set of installed distributions."""
    always_on_roots, dev_roots, product_extras = product_and_dev_roots(lock)
    always_on, always_gated = closure(lock, always_on_roots, admits)
    extra_edges = [edge for rows in product_extras.values() for edge in rows]
    extra_names, extra_gated = closure(lock, extra_edges, admits)
    product = always_on | extra_names
    gated = (always_gated | extra_gated) - product
    dev, _dev_gated = closure(lock, dev_roots, admits)
    dev -= product

    findings: list[Finding] = []
    for name in sorted(product):
        pinned = lock.version_of(name)
        have = installed.get(name)
        if have is None:
            # Not installing an opt-in feature is a choice; not installing something the product
            # imports unconditionally is a broken environment.
            findings.append(Finding(name, "missing" if name in always_on else "absent", None, pinned))
        elif have != pinned:
            findings.append(Finding(name, "drift", have, pinned))
    for name in sorted(dev):
        pinned = lock.version_of(name)
        have = installed.get(name)
        if have is None:
            findings.append(Finding(name, "dev-missing", None, pinned))
        elif have != pinned:
            findings.append(Finding(name, "dev-drift", have, pinned))
    for name in sorted(gated - dev):
        pinned = lock.version_of(name)
        have = installed.get(name)
        if have is None:
            findings.append(Finding(name, "gated", None, pinned))
        elif have != pinned:
            # The marker excludes it here, so the product cannot reach this copy; a wrong version
            # is named rather than refused.
            findings.append(Finding(name, "gated-drift", have, pinned))
    for name in sorted(set(installed) - product - dev - gated - {lock.root}):
        findings.append(Finding(name, "undeclared", installed[name], lock.version_of(name)))
    for name in sorted(shadows):
        findings.append(Finding(name, "shadow", installed.get(name), lock.version_of(name)))
    return findings


def installed_distributions(reader: Callable[[], Iterable] | None = None) -> tuple[dict[str, str], list[str]]:
    """The environment running this process: one version per name, plus the names holding two.

    `reader` is the injection point a test uses to hand in its own distributions; by default it
    is `importlib.metadata.distributions`, so no installer is ever shelled out to.
    """
    rows = (reader or metadata.distributions)()
    versions: dict[str, str] = {}
    seen: dict[str, set[str]] = {}
    for row in rows:
        try:
            name = row.metadata["Name"]
            version = row.version
        except Exception:  # a broken dist-info still must not make the run look clean
            continue
        if not name or not version:
            continue
        key = canonical(name)
        seen.setdefault(key, set()).add(version)
        versions.setdefault(key, version)
    shadows = sorted(name for name, found in seen.items() if len(found) > 1)
    return versions, shadows


def environment_label(python: str) -> str:
    """Where this interpreter came from, read from its own `pyvenv.cfg` when it has one.

    Printed because the most expensive finding this instrument produced was not a version but a
    ownership question: an environment that belongs to a different project than the code it runs
    can satisfy its own lock and still be the wrong runtime.
    """
    facts: dict[str, str] = {}
    try:
        for line in (Path(sys.prefix) / "pyvenv.cfg").read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            facts[key.strip()] = value.strip()
    except OSError:
        return f"python {python} (no pyvenv.cfg — not a virtualenv)"
    return (
        f"python {python} | prefix {sys.prefix} | created by {facts.get('command', '?')} "
        f"| home {facts.get('home', '?')}"
    )


def report(
    lock: Lock,
    findings: list[Finding],
    *,
    python: str,
    installed_count: int,
    limit: int = PRINTED_DEFAULT,
    markers_evaluated: bool = True,
) -> tuple[int, list[str]]:
    """The printed verdict and its exit code. Refusal comes from `REFUSING` alone."""
    hard = [f for f in findings if f.kind in REFUSING]
    columns: dict[str, list[Finding]] = {}
    for finding in findings:
        columns.setdefault(finding.kind, []).append(finding)
    marker_note = "evaluated here" if markers_evaluated else "NOT evaluated — every conditional edge held to the lock"
    lines = [
        f"env/lock agreement: {'FAIL' if hard else 'PASS'} — "
        f"{len(hard)} product-graph deviation(s) against {lock.path}",
        f"  {environment_label(python)} | {installed_count} distribution(s) installed | "
        f"{len(lock.versions)} package(s) in the lock | markers: {marker_note}",
    ]
    for kind in KIND_ORDER:
        rows = columns.get(kind, [])
        if not rows:
            continue
        note = "" if kind in REFUSING else "  (printed, does not refuse)"
        lines.append(f"  {kind}: {len(rows)}{note}")
        for row in rows[: max(0, limit)]:
            lines.append(row.line())
        if len(rows) > limit:
            lines.append(f"  ... {len(rows) - limit} more {kind}")
    if not hard:
        lines.append("  no product dependency differs from the lock")
    return (EXIT_DIFFERS if hard else EXIT_OK), lines


def as_json(
    lock: Lock, findings: list[Finding], *, python: str, installed_count: int, markers_evaluated: bool = True
) -> str:
    return json.dumps(
        {
            "lock": lock.path,
            "python": python,
            "environment": environment_label(python),
            "installed": installed_count,
            "locked_packages": len(lock.versions),
            "markers_evaluated": markers_evaluated,
            "refusing": sorted(REFUSING),
            "findings": [
                {"name": f.name, "kind": f.kind, "installed": f.installed, "pinned": f.pinned} for f in findings
            ],
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="project whose lock is the contract")
    parser.add_argument("--lock", type=Path, default=None, help="lock file to read (default <root>/uv.lock)")
    parser.add_argument("--limit", type=int, default=PRINTED_DEFAULT, help="findings printed per kind")
    parser.add_argument("--json", action="store_true", help="machine-readable output for later use")
    args = parser.parse_args(argv)

    lock_path = args.lock or (args.root / "uv.lock")
    try:
        lock = read_lock(lock_path)
    except (OSError, tomllib.TOMLDecodeError, ValueError) as error:
        print(f"env/lock agreement: cannot read the lock — {error}", file=sys.stderr)
        return EXIT_DIFFERS
    installed, shadows = installed_distributions()
    admits, markers_evaluated = marker_admits()
    findings = compare(lock, installed, shadows, admits)
    if args.json:
        print(
            as_json(
                lock,
                findings,
                python=sys.executable,
                installed_count=len(installed),
                markers_evaluated=markers_evaluated,
            )
        )
        return EXIT_DIFFERS if any(f.kind in REFUSING for f in findings) else EXIT_OK
    code, lines = report(
        lock,
        findings,
        python=sys.executable,
        installed_count=len(installed),
        limit=args.limit,
        markers_evaluated=markers_evaluated,
    )
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
