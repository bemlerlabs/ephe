#!/usr/bin/env bash
# uv_lock_sync.sh — turn a changed constraint into a lock delta plus a fence verdict.
#
# Why this exists: Dependabot rewrites pyproject.toml and cannot regenerate uv.lock, so the
# supply-chain guard (`uv lock --check`, .github/workflows/tests.yml) fails a dependency PR
# before pytest runs — and with it the fence test that was supposed to decide the PR on its
# merits (PR #37, ephemora-cell >=1.0.4.3,<1.0.5 -> <1.1.1, four legs red, zero reps).
#
# Modes, none of which write the repository pair:
#   --package NAME [--bound SPEC] [--scratch DIR] [--dry-run]   print the plan
#   --package NAME [--bound SPEC] [--scratch DIR] --prepare     copy and rewrite the scratch tree, no uv
#   --package NAME --diff --repo-lock A --new-lock B            drift report, exit 1 on a second mover
#   --package NAME --verdict --pyproject P --lock L             register verdict, exit 1 on FAIL
# Run mode (no --dry-run/--diff/--verdict) executes the plan inside the scratch tree.
#
# The resolve is `uv lock --upgrade-package NAME`, never a bare `uv lock`: re-resolving 200-odd
# unrelated packages is not a consequence of one constraint change. The uv version is the one CI
# pins, read from the workflow instead of duplicated here — a lock written by an older resolver
# rewrites its own header and every block under it (measured: uv 0.12.24 writes `revision = 5`,
# the version this lock carries; uv 0.8.0 writes no revision field at all).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE="" ; BOUND="" ; SCRATCH="" ; MODE="run" ; REPO_LOCK="" ; NEW_LOCK="" ; PYPROJECT="" ; LOCK=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --package) PACKAGE="$2"; shift 2 ;;
    --bound) BOUND="$2"; shift 2 ;;
    --scratch) SCRATCH="$2"; shift 2 ;;
    --dry-run) MODE="plan"; shift ;;
    --prepare) MODE="prepare"; shift ;;
    --diff) MODE="diff"; shift ;;
    --verdict) MODE="verdict"; shift ;;
    --repo-lock) REPO_LOCK="$2"; shift 2 ;;
    --new-lock) NEW_LOCK="$2"; shift 2 ;;
    --pyproject) PYPROJECT="$2"; shift 2 ;;
    --lock) LOCK="$2"; shift 2 ;;
    *) echo "uv-lock-sync: unknown argument $1" >&2; exit 2 ;;
  esac
done

[[ -n "$PACKAGE" ]] || { echo "uv-lock-sync: --package is required" >&2; exit 2; }

UV_PIN="$(grep -m1 -o 'install "uv==[^"]*"' "$REPO/.github/workflows/tests.yml" \
  | sed -e 's/.*uv==//' -e 's/"//')"
[[ -n "$UV_PIN" ]] || { echo "uv-lock-sync: no pinned uv version in .github/workflows/tests.yml" >&2; exit 2; }
SCRATCH="${SCRATCH:-$(mktemp -d "${TMPDIR:-/tmp}/uv-lock-sync.XXXXXX")}"

# The bound a caller wants to ask about, in the form the register's readers parse.
SPEC_LINE=""
if [[ -n "$BOUND" ]]; then
  [[ "$BOUND" =~ ^[0-9][0-9A-Za-z.+]*(,<[0-9][0-9A-Za-z.+]*)?$ ]] \
    || { echo "uv-lock-sync: --bound takes LOWER[,<UPPER] — e.g. '1.0.4.3,<1.1.1'" >&2; exit 2; }
  if [[ "$BOUND" == *","* ]]; then
    SPEC_LINE="${PACKAGE}>=${BOUND}"
  else
    SPEC_LINE="${PACKAGE}>=${BOUND},<${BOUND}."
  fi
fi

if [[ "$MODE" == "plan" ]]; then
  cat <<PLAN
uv-lock-sync package=${PACKAGE} repo=${REPO}
scratch=${SCRATCH}
tool: ${SCRATCH}/uv-venv/bin/pip install "uv==${UV_PIN}"
tree: cp ${REPO}/pyproject.toml ${REPO}/uv.lock ${REPO}/README.md ${SCRATCH}/project/
bound: ${SPEC_LINE:-the bound already in pyproject.toml} (rewritten in the scratch copy only; the repo pyproject.toml is never touched)
resolve: cd ${SCRATCH}/project && ${SCRATCH}/uv-venv/bin/uv lock --upgrade-package ${PACKAGE}
diff: $(basename "$0") --package ${PACKAGE} --diff --repo-lock ${REPO}/uv.lock --new-lock ${SCRATCH}/project/uv.lock
fence: $(basename "$0") --package ${PACKAGE} --verdict --pyproject ${SCRATCH}/project/pyproject.toml --lock ${SCRATCH}/project/uv.lock
land: git commit -- pyproject.toml uv.lock (the constraint and its lock in one commit, after a human read the diff)
PLAN
  exit 0
fi

# A python3 that can actually run this script's heredocs, found before the first one.
# Bare `python3` is not it on a stock macOS (3.9.6 has neither tomllib nor tomli), and
# the script may be run from a Terminal, from CI or from pytest, where PATH decides which
# interpreter answers. The verdict mode loads the fence test module, which imports pytest
# on top of the TOML reader — so the preferred answer is a python that carries BOTH
# (the project .venv exists exactly for that). A machine without one still gets diff and
# prepare on a toml-only python; a missing reader anywhere fails with a named cause
# instead of mid-mode with a ModuleNotFoundError.
find_toml_python() {
  for p in python3 python3.13 python3.12 python3.11 python3.10 "$REPO/.venv/bin/python"; do
    command -v "$p" >/dev/null 2>&1 || continue
    if "$p" -c 'import tomllib, pytest' 2>/dev/null || "$p" -c 'import tomli, pytest' 2>/dev/null; then
      echo "$p"
      return 0
    fi
  done
  for p in python3 python3.13 python3.12 python3.11 python3.10 "$REPO/.venv/bin/python"; do
    command -v "$p" >/dev/null 2>&1 || continue
    if "$p" -c 'import tomllib' 2>/dev/null || "$p" -c 'import tomli' 2>/dev/null; then
      echo "$p"
      return 0
    fi
  done
  echo "uv-lock-sync: no python with a TOML reader on PATH or in $REPO/.venv — install python 3.11+ or run the suite's .venv" >&2
  return 1
}
TOML_PYTHON="$(find_toml_python)" || exit 1

rewrite_bound() {
  "$TOML_PYTHON" - "$1" "$2" <<'PY'
import re
import sys

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10, the leg this script must run on (tests/toml_compat.py)
    import tomli as tomllib  # type: ignore[no-redef]

path, line = sys.argv[1], sys.argv[2]
name = line.split(">=")[0]
text = open(path, encoding="utf-8").read()
# Both classes stop at a comma and at a quote: a set that allowed `"` ate the closing quote of the
# requirement string and handed uv a TOML parse error. The parse check catches the class here.
new, count = re.subn(name + r'\s*>=\s*[^",]+,\s*<[^",]+', line, text)
if count < 1:
    sys.exit("uv-lock-sync: no `>=A,<B` bound for " + name + " found in " + path)
tomllib.loads(new)
open(path, "w", encoding="utf-8").write(new)
print("rewrote " + str(count) + " bound(s) in the scratch copy to " + line)
PY
}

prepare_tree() {
  mkdir -p "$SCRATCH/project"
  cp "$REPO/pyproject.toml" "$REPO/uv.lock" "$REPO/README.md" "$SCRATCH/project/"
  [[ -z "$SPEC_LINE" ]] || rewrite_bound "$SCRATCH/project/pyproject.toml" "$SPEC_LINE"
  echo "prepared: $SCRATCH/project"
}

if [[ "$MODE" == "prepare" ]]; then
  prepare_tree
  exit 0
fi

if [[ "$MODE" == "diff" ]]; then
  [[ -n "$REPO_LOCK" && -n "$NEW_LOCK" ]] || { echo "uv-lock-sync: --diff needs --repo-lock and --new-lock" >&2; exit 2; }
  status=0
  REPO_LOCK="$REPO_LOCK" NEW_LOCK="$NEW_LOCK" PACKAGE="$PACKAGE" "$TOML_PYTHON" - <<'PY' || status=$?
import os, re, sys

def blocks(path):
    return open(path, encoding="utf-8").read().split("[[package]]")


def packages(path):
    """{name: {versions}} and {name: {wheel shas}} from a uv.lock.

    A forked resolution writes several `[[package]]` blocks for one name — the repo lock holds
    six such names, `numpy` among them with three — so one value per name is not a reading, it is
    whichever block happened to come last. Sets keep every fork visible to the comparison below.
    """
    versions, shas = {}, {}
    for block in blocks(path):
        name = re.search(r'^name = "([^"]+)"', block, re.M)
        if not name:
            continue
        version = re.search(r'^version = "([^"]+)"', block, re.M)
        wheel = re.search(r"sha256:([0-9a-f]{64})", block)
        versions.setdefault(name.group(1), set()).add(version.group(1) if version else "")
        shas.setdefault(name.group(1), set()).add(wheel.group(1) if wheel else "")
    return versions, shas


def graph(path):
    """name -> the names it declares, read from each block's dependency lists. The cone of a
    package is what a version change may legitimately move; anything else that moved is a
    re-resolution the request did not ask for. Forks of one name union their edges."""
    edges = {}
    for block in blocks(path):
        name = re.search(r'^name = "([^"]+)"', block, re.M)
        if not name:
            continue
        listed = []
        for section in re.findall(r"dependencies = \[(.*?)\n]", block, re.S):
            listed += re.findall(r'\{\s*name = "([^"]+)"', section)
        edges.setdefault(name.group(1), set()).update(listed)
    return {k: sorted(v) for k, v in edges.items()}


def cone(new_lock, target):
    edges, seen, queue = graph(new_lock), {target}, [target]
    while queue:
        for child in edges.get(queue.pop(), []):
            if child not in seen:
                seen.add(child)
                queue.append(child)
    return seen


old_versions, _ = packages(os.environ["REPO_LOCK"])
new_versions, _ = packages(os.environ["NEW_LOCK"])
target = os.environ["PACKAGE"]
if target not in new_versions:
    print("missing:", target, "is absent from the generated lock")
    sys.exit(1)
allowed = cone(os.environ["NEW_LOCK"], target)
moved = [n for n in new_versions if n in old_versions and old_versions[n] != new_versions[n]]
added, removed = sorted(set(new_versions) - set(old_versions)), sorted(set(old_versions) - set(new_versions))
for n in moved:
    print("moved:", n, "/".join(sorted(old_versions[n])), "->", "/".join(sorted(new_versions[n])),
          "(inside the cone)" if n in allowed else "")
for n in added:
    print("added:", n, "/".join(sorted(new_versions[n])), "(inside the cone)" if n in allowed else "")
for n in removed:
    print("removed:", n, "/".join(sorted(old_versions[n])))
intruders = [n for n in moved + added + removed if n not in allowed]
if intruders:
    print("drift:", ", ".join(intruders), "moved beside the request — a bare uv lock, not an upgrade")
    sys.exit(1)
print("clean:", target, "and its dependency cone only;", len(new_versions), "names,",
      sum(len(v) for v in new_versions.values()), "package blocks otherwise identical")
PY
  exit $status
fi

if [[ "$MODE" == "verdict" ]]; then
  [[ -n "$PYPROJECT" && -n "$LOCK" ]] || { echo "uv-lock-sync: --verdict needs --pyproject and --lock" >&2; exit 2; }
  status=0
  PYPROJECT="$PYPROJECT" LOCKF="$LOCK" PACKAGE="$PACKAGE" REPO="$REPO" "$TOML_PYTHON" - <<'PY' || status=$?
import importlib.util
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.environ["REPO"])

# One source of truth for what "measured" means: the fence test's own readers, pointed at the
# files the caller named. Restating the rule here would let mechanism and guard drift apart.
spec = importlib.util.spec_from_file_location(
    "fence_rules", Path(os.environ["REPO"]) / "tests" / "test_dependency_license_fence.py")
fence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fence)
fence.PYPROJECT = Path(os.environ["PYPROJECT"])
fence.LOCK = Path(os.environ["LOCKF"])

name = os.environ["PACKAGE"]
pkg = fence._register()[name]
reasons = []

for where, lower, upper in fence._requirement_bounds(name):
    admitted = [v for v in (pkg.get("releases") or {})
                if fence._version_tuple(lower) <= fence._version_tuple(v) < fence._version_tuple(upper)]
    print(f"bound[{where}] {name}>={lower},<{upper} admits: {', '.join(sorted(admitted)) or 'nothing registered'}")
    if not admitted:
        reasons.append(f"{where} admits no release the register knows")
    for v in sorted(admitted):
        try:
            fence._measurable(pkg, name, v)
        except AssertionError as exc:
            reasons.append(str(exc))

resolved = fence._lock_resolution(name)
if resolved is None:
    reasons.append("the lock resolves no version for this package")
else:
    # `_lock_resolution` answers the first block it finds for a name. A forked resolution writes
    # one block per version — six names in this lock do, `numpy` with three — so a fence reading
    # one of them is not a fence. Collect every block of the target and judge each one.
    target_blocks = []
    for block in Path(os.environ["LOCKF"]).read_text(encoding="utf-8").split("[[package]]"):
        if not re.search(rf'^name = "{re.escape(name)}"\s*$', block, re.M):
            continue
        version = re.search(r'^version = "([^"]+)"', block, re.M)
        wheel = re.search(r"wheels\s*=\s*\[.*?sha256:([0-9a-f]{64})", block, re.S)
        target_blocks.append((version.group(1), (wheel.group(1) if wheel else "")))
    if len({v for v, _ in target_blocks}) > 1:
        print("lock forks: " + ", ".join(sorted({v for v, _ in target_blocks})))
    for version, wheel_sha in sorted(target_blocks):
        print(f"lock resolves: {name} {version} sha256:{wheel_sha or '<missing>'}")
        entry = {}
        try:
            entry = fence._release(pkg, name, version, "resolved by the lock")
            fence._measurable(pkg, name, version)
        except AssertionError as exc:
            reasons.append(str(exc))
            entry = (pkg.get("releases") or {}).get(version) or {}
        if entry.get("wheel_sha256") and entry["wheel_sha256"] != wheel_sha:
            reasons.append(
                f"the lock installs {name} {version} from sha256:{wheel_sha or '<missing>'} while the register "
                f"read its licence and policy off sha256:{entry['wheel_sha256']}")

for reason in dict.fromkeys(reasons):
    print(f"reason: {reason}")
print(f"verdict: {'FAIL' if reasons else 'PASS'}")
sys.exit(1 if reasons else 0)
PY
  exit $status
fi

prepare_tree
PROJ="$SCRATCH/project"
VENV="$SCRATCH/uv-venv"
if [[ ! -x "$VENV/bin/uv" ]]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" --quiet install "uv==${UV_PIN}"
fi
( cd "$PROJ" && "$VENV/bin/uv" lock --upgrade-package "$PACKAGE" )
"$0" --package "$PACKAGE" --diff --repo-lock "$REPO/uv.lock" --new-lock "$PROJ/uv.lock"
"$0" --package "$PACKAGE" --verdict --pyproject "$PROJ/pyproject.toml" --lock "$PROJ/uv.lock"
echo "scratch: $PROJ"
