#!/usr/bin/env python3
"""Catalog freshness: the committed catalogs are what their sources imply.

Wave II of `docs/CI_HYBRID_CAPACITY_2026-10-11.md`, rows 40 and 41 (hermes' `skills-index-freshness.yml`
and `skills-index.yml`, the regenerate-and-diff half). Surfaces, decided differently because the
acceptance for a gate is that it is green on the tree it was written against:

* `skills-lock.json` through `scripts/generate_skills_lock.py --check`, which already answers with
  `skills_lock_mismatch pack=<slug> lock=<hash> disk=<hash>`. Proven red on 2026-10-11 by appending one
  space to `skills/api-designer/SKILL.md` and restoring it.
* `plugin-catalog.json` through `scripts/generate_plugin_catalog.py --check`, the check mode added by
  this wave. Proven red by adding a file to `plugins/browser-use/`, which moves that pack's `dir_sha256`
  and prints `sha256 af307177d0be... != ff6389797bd7...`.
* `marketplace/index.json` through `scripts/build_marketplace.py --check`, which repacks every bundle
  in a temporary directory and compares the index and the ZIP bytes against the committed shelf.
  Proven red on 2026-11-22: the committed index carried `countdown` under `meta` while the builder
  generates `widgets`, and the `widgets` category was missing from `metadata.categories`.
* `core/mcp_catalog.py` (the MCP starter catalog) is **gated** on its shape contract, not a
  regenerate-and-diff: it is hand-curated data with no generator. The check is what the MCP page
  renders and what the register depends on (required keys, unique ids, a bilingual `description_en`
  that is not a copy of the German, https-only docs, a registerable `spec` or an `install_hint`, and the
  first-party license fence kept at its pin). Whether a named server actually answers is deliberately
  *not* asked here — the catalog must stay pure data, and liveness belongs to the runtime probe
  `POST /api/mcp/health`.
* `marketplace/` (the discover shelf) is **gated on its own claims and never on its age**: the three
  committed files each say when they were generated, and what is refused is the files contradicting
  that — one regenerated while two waited, a timestamp ahead of today, a claim postdating the commit
  that carries it. Added 2026-11-17 after `catalog-sync.yml` was measured to have opened no pull
  request in its entire history while the shelf aged 18 days behind green nightlies.
* `knowledge/index.json` against the tree, **reported and not gated**. Measured 2026-10-11: the index
  declares the domain `system`, for which no directory exists, `knowledge/navigation/` is on disk and
  undeclared, and `stats.totalFiles` says 6 where the tree carries 9 `.md` files. A check that is red on
  the day it lands teaches the reader to file the nightly as noise, so it prints its findings and the
  owner flips it into `GATED` when the knowledge lane has fixed the index.
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATORS = (
    ("skills-lock.json", ("scripts/generate_skills_lock.py", "--check")),
    ("plugin-catalog.json", ("scripts/generate_plugin_catalog.py", "--check")),
    ("marketplace/index.json", ("scripts/build_marketplace.py", "--check")),
)
#: The knowledge index is report-only until the drift above is closed; see the module docstring.
#: `core/mcp_catalog.py` is gated — its contract is green on the tree this landed against.
#: `marketplace/` is gated on the files' own claims, never on their age; see `shelf_drift`.
GATED: tuple[str, ...] = ("skills-lock.json", "plugin-catalog.json", "core/mcp_catalog.py",
                          "marketplace/")
#: The license fence the first-party catalog entry advertises for the project's own cell. A binary
#: distribution may not silently cross it, so the entry keeps its version pin in the description and
#: the install hint; the check reads both.
_MCP_LICENSE_FENCE: tuple[str, ...] = ("ephemora-cell-mcp", "1.0.4.3", "1.0.5")

#: The discover shelf's three committed data files. The weekly job that is supposed to refresh them
#: opened no pull request in three weeks and no nightly noticed, so this leg looks at them now.
_SHELF_FILES: tuple[str, ...] = ("marketplace/registry-snapshot.json",
                                 "marketplace/registry-curated.json",
                                 "marketplace/search-intents.json")
#: One sync run regenerates all three in the same minute; measured 2026-11-17 they sit two days
#: apart (a timezone's worth of writing plus a commit landing the next morning). Twice that means one
#: file came along on a sync the other two missed.
_SHELF_SPREAD_DAYS = 8
#: The sync generates and commits inside the same UTC hour, so a day of tolerance covers the
#: timezone and nothing more.
_SHELF_LAG_DAYS = 1


def shelf_history_available(root: Path) -> bool:
    """Whether `git log` here can date the commit that last touched a file."""
    done = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=root, text=True,
                          capture_output=True, check=False)
    return done.returncode == 0 and done.stdout.strip() == "false"


def _shelf_commit_date(root: Path, rel: str) -> datetime.date | None:
    """The date of the commit that last carried `rel`, or None when history cannot answer."""
    done = subprocess.run(["git", "log", "-1", "--format=%cI", "--", rel], cwd=root, text=True,
                          capture_output=True, check=False)
    stamp = done.stdout.strip()
    if done.returncode != 0 or not stamp:
        return None
    try:
        return datetime.datetime.fromisoformat(stamp).date()
    except ValueError:
        return None


def shelf_drift(root: Path) -> list[str]:
    """Every way the committed discover shelf contradicts its own `generated` claim.

    The three files under `marketplace/` are generated by `scripts/catalog_discover.py` and shipped
    as committed data, and each carries the moment of its own making under `generated`. Age alone is
    deliberately **not** gated: a registry that did not change legitimately leaves a file ageing, and
    a nightly that cries at a quiet upstream is the red leg this module's header already refuses. What
    can rot silently is the files disagreeing with themselves — one regenerated without the others, a
    timestamp no run could have written, a claim that postdates the commit carrying it, which is the
    shape of an artifact edited by hand after generation.

    The commit half needs real history. A `fetch-depth: 1` checkout dates every file at the boundary
    commit, so there the half is announced as skipped rather than answered wrongly: it can miss a lie
    in a shallow tree, never invent one.
    """
    problems: list[str] = []
    claims: dict[str, datetime.date] = {}
    today = datetime.date.today()
    for rel in _SHELF_FILES:
        path = root / rel
        if not path.is_file():
            problems.append(f"{rel} is missing")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{rel} does not parse: {exc.__class__.__name__}")
            continue
        raw = data.get("generated") if isinstance(data, dict) else None
        if not raw:
            problems.append(f"{rel} carries no `generated` claim")
            continue
        try:
            claim = datetime.datetime.fromisoformat(str(raw)).date()
        except ValueError:
            problems.append(f"{rel} carries a `generated` value that is no ISO timestamp: {raw!r}")
            continue
        claims[rel] = claim
        ahead = (claim - today).days
        if ahead > _SHELF_LAG_DAYS:
            problems.append(f"{rel} claims it was generated {claim.isoformat()}, {ahead} days ahead of today")
    if len(claims) == len(_SHELF_FILES):
        oldest = min(claims.values())
        newest = max(claims.values())
        spread = (newest - oldest).days
        if spread > _SHELF_SPREAD_DAYS:
            laggards = sorted(rel for rel, day in claims.items() if day == oldest)
            problems.append(f"the shelf files disagree about when they were generated: {spread} days "
                            f"apart, oldest {oldest.isoformat()} in {', '.join(laggards)}")
    if claims and shelf_history_available(root):
        for rel, claim in claims.items():
            commit = _shelf_commit_date(root, rel)
            if commit is None:
                continue
            behind = (claim - commit).days
            if behind > _SHELF_LAG_DAYS:
                problems.append(f"{rel} claims it was generated {claim.isoformat()}, {behind} days "
                                f"after the commit that carries it ({commit.isoformat()})")
    return problems


def knowledge_drift(root: Path) -> list[str]:
    """Every way `knowledge/index.json` and `knowledge/` on disk disagree."""
    index_path = root / "knowledge" / "index.json"
    if not index_path.is_file():
        return [f"{index_path.relative_to(root)} is missing"]
    data = json.loads(index_path.read_text(encoding="utf-8"))
    declared = [str(domain.get("id")) for domain in data.get("domains", []) if domain.get("id")]
    base = root / "knowledge"
    on_disk = sorted(p.name for p in base.iterdir() if p.is_dir())
    problems = [f"index declares domain {name}, no knowledge/{name}/ directory exists"
                for name in declared if name not in on_disk]
    problems += [f"knowledge/{name}/ exists on disk and no domain in the index declares it"
                 for name in on_disk if name not in declared]
    files = sum(len(list((base / name).rglob("*.md"))) for name in on_disk)
    claimed = (data.get("stats") or {}).get("totalFiles")
    if isinstance(claimed, int) and claimed != files:
        problems.append(f"stats.totalFiles says {claimed}, the tree carries {files} .md files")
    return problems


def _load_mcp_catalog(root: Path) -> tuple[object | None, list[str]]:
    """Load ``core/mcp_catalog.py`` by path — pure data, no package import needed.

    The module carries no imports, so loading it by path avoids pulling
    ``core/__init__`` (which imports a version module that needs ``tomllib``/``tomli``).
    Path-bound on purpose: a plant is a directory passed as ``--root``, the same
    shape the knowledge half is tested with.
    """
    path = root / "core" / "mcp_catalog.py"
    if not path.is_file():
        return None, [f"{path.relative_to(root)} is missing"]
    spec = importlib.util.spec_from_file_location("_ephe_mcp_catalog", path)
    if spec is None or spec.loader is None:
        return None, ["core/mcp_catalog.py is not importable"]
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # noqa: BLE001 — a broken catalog stays a finding
        return None, [f"core/mcp_catalog.py does not import: {exc!r}"]
    return module, []


def mcp_catalog_drift(root: Path) -> list[str]:
    """Every way the curated MCP catalog (``core/mcp_catalog.py``) breaks its contract.

    The catalog is hand-curated data with no generator, so there is nothing to
    regenerate and diff. What can rot is its *shape*: the MCP page renders
    ``name``/``category``/``description``/``install_hint``/``docs``, the bilingual
    rule (I7-4) needs ``description_en`` to carry the English text and not a copy
    of the German, a ``spec`` — when present — must be a registerable engine spec,
    and the first-party cell entry keeps its license fence. There is deliberately
    **no** network liveness check: the catalog must stay pure data, and whether a
    named server answers belongs to the runtime probe ``POST /api/mcp/health``.
    """
    module, problems = _load_mcp_catalog(root)
    if module is None:
        return problems
    entries = getattr(module, "CATALOG", None)
    if not isinstance(entries, list) or not entries:
        return problems + ["core/mcp_catalog.py declares no CATALOG entries"]

    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            problems.append(f"catalog entry is not a dict: {entry!r}")
            continue
        entry_id = str(entry.get("id") or "")
        label = entry_id or "?"
        if not entry_id:
            problems.append(f"catalog entry without an id: {entry.get('name')!r}")
        elif entry_id in seen_ids:
            problems.append(f"catalog id {entry_id} is declared twice")
        else:
            seen_ids.add(entry_id)
        for key in ("name", "description", "description_en", "category"):
            if not str(entry.get(key) or "").strip():
                problems.append(f"{label}: no {key}")
        de = str(entry.get("description") or "").strip()
        en = str(entry.get("description_en") or "").strip()
        if de and en and de == en:
            problems.append(f"{label}: description_en is a copy of description")
        docs = str(entry.get("docs") or "")
        if docs and not docs.startswith("https://"):
            problems.append(f"{label}: docs link is not https ({docs!r})")
        spec = entry.get("spec")
        if spec is not None:
            text = str(spec)
            if not text.startswith(("http://", "https://", "stdio:")):
                problems.append(f"{label}: spec {text!r} is not the http/https/stdio PUT contract")
        elif not str(entry.get("install_hint") or "").strip():
            problems.append(f"{label}: neither a registerable spec nor an install_hint")

    fence = next((e for e in entries if isinstance(e, dict) and e.get("id") == "mcp-ephemora-cell"), None)
    if fence is None:
        problems.append("mcp-ephemora-cell is missing from the catalog (the first-party license fence)")
    else:
        blob = json.dumps(fence, ensure_ascii=False)
        for token in _MCP_LICENSE_FENCE:
            if token not in blob:
                problems.append(f"mcp-ephemora-cell no longer names its license fence token {token!r}")
    return problems


def run_generators(root: Path) -> list[str]:
    problems = []
    for label, argv in GENERATORS:
        done = subprocess.run([sys.executable, *argv], cwd=root, text=True, capture_output=True,
                              check=False)
        lines = (done.stdout + done.stderr).strip().splitlines()
        if done.returncode == 0 and not lines:
            # `generate_skills_lock.py --check` is silent when the lock is fresh, and a CI step that
            # prints nothing reads as a step that never ran.
            print(f"  {label}: fresh (the generator prints nothing on success)")
        for line in lines:
            print(f"  {label}: {line}")
        if done.returncode != 0:
            problems.append(f"{label} is not what its sources generate (exit {done.returncode})")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    problems = run_generators(args.root)
    drift = knowledge_drift(args.root)
    for line in drift:
        print(f"  knowledge/index.json: {line}")
    if drift and "knowledge/index.json" in GATED:
        problems.append(f"knowledge/index.json disagrees with the tree in {len(drift)} way(s)")

    mcp = mcp_catalog_drift(args.root)
    if mcp:
        for line in mcp:
            print(f"  core/mcp_catalog.py: {line}")
    else:
        # A silent-but-ran surface reads as a surface that never ran; mirror the skills-lock line.
        print("  core/mcp_catalog.py: fresh")
    if mcp and "core/mcp_catalog.py" in GATED:
        problems.append(f"core/mcp_catalog.py breaks its contract in {len(mcp)} way(s)")

    shelf = shelf_drift(args.root)
    for line in shelf:
        print(f"  marketplace/: {line}")
    if not shelf:
        print("  marketplace/: fresh")
    if not shelf_history_available(args.root):
        # A shallow checkout dates every file at its boundary commit; the claim half still ran.
        print(f"  marketplace/: {len(_SHELF_FILES)} file(s) dated from their own claims only, "
              f"no history to compare against")
    if shelf and "marketplace/" in GATED:
        problems.append(f"marketplace/ contradicts its own claims in {len(shelf)} way(s)")

    print(f"catalog-freshness: {len(GENERATORS)} generator(s) checked, "
          f"{len(drift)} knowledge-index finding(s), {len(mcp)} mcp-catalog finding(s), "
          f"{len(shelf)} shelf finding(s), {len(problems)} problem(s)")
    for problem in problems:
        print(f"catalog-freshness: FAIL {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
