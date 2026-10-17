#!/usr/bin/env bash
# Clean-room install: prove that this repository installs from a fresh clone into a scratch
# root, with nothing carried over from the machine that runs it.
#
# Why it exists: every shipped leg installs into an interpreter on a host that already has the
# product, so `0 MISSING` there has never meant the lock can be installed cold. The receipt for
# that hazard is in tests.yml's own venv step: PR run `9910615d` logged 110 `Requirement already
# satisfied` lines out of the listener's `_tool` cache, and `_tool` survives the job, so the next
# leg read those packages as satisfied. A clone into a directory the runner wipes is the only
# shape where an unsatisfiable lock has to say so.
#
# Two rules are plants rather than preferences:
#   * the install root must sit under a directory this job loses. An install that lands in
#     `RUNNER_TOOL_CACHE` or in the source tree outlives the run and poisons whoever lands next.
#   * a failed step prints a verdict and exits non-zero. A crash is not a red check, it is an
#     unreadable one.
#
# The Python set is compared against `uv.lock` itself: `uv export` writes a universal file with
# environment markers (measured: the leg's 121 exported lines load as 103 on one platform), so
# the expected set is that file filtered by the target interpreter's own marker environment.
# Markers are evaluated through the seeded venv's own pip, which vendors `packaging`, because
# installing a resolver into the venv would add a package to the set under test.
set -uo pipefail

readonly UV_VERSION="${EPHE_UV_VERSION:-0.12.24}"
readonly EXTRAS=(--extra dev --extra tui)
readonly TARGETS="${EPHE_CLEAN_ROOM_TARGETS:-py,js}"
readonly WANT_REF="${EPHE_CLEAN_ROOM_REF:-HEAD}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SOURCE="${EPHE_CLEAN_ROOM_SOURCE:-${GITHUB_WORKSPACE:-$(dirname "$script_dir")}}"

IFS=',' read -ra shapes <<< "${EPHE_CLEAN_ROOM_PYTHONS:-3.12}"

failures=0
wall=()
say() { printf 'clean-room: %s\n' "$*"; }
fail() { failures=$((failures + 1)); say "FAIL $*"; }
# Every refusal leaves the same shape on stdout: a FAIL line naming the rule and a VERDICT line.
# A guard that exits without them is indistinguishable from a crash in a job log.
bail() { fail "$*"; say "VERDICT fail ($failures check(s) did not hold)"; exit 1; }
timed() { wall+=("$1 ${2}s"); }
want_target() { [[ ",$TARGETS," == *",$1,"* ]]; }

# --- the install root: the one printed line, and the guard a dropped venv step hits ---
scratch_root_raw="${EPHE_CLEAN_ROOM_ROOT:-}"
if [ -z "$scratch_root_raw" ]; then
    bail "EPHE_CLEAN_ROOM_ROOT is unset; refusing to install where this job cannot be wiped"
fi
# The parent is resolved rather than the root itself, so nothing is created before the guards below
# have passed. Measured: a run that refused a tool-cache root still left that empty directory behind,
# which is a write into the location the refusal exists to keep clean.
root_parent="$(dirname "$scratch_root_raw")"
root_parent_real="$(cd "$root_parent" 2>/dev/null && pwd -P)" \
    || bail "the install root's parent $root_parent does not exist"
scratch_root="$root_parent_real/$(basename "$scratch_root_raw")"

job_temp_raw="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
job_temp="$(cd "$job_temp_raw" 2>/dev/null && pwd -P)" \
    || bail "the directory this job is supposed to lose, $job_temp_raw, does not exist"
case "$scratch_root/" in
    "$job_temp"/*) : ;;
    *) bail "install root $scratch_root is not under the directory this job loses ($job_temp)" ;;
esac
# Each forbidden root is resolved the same way the install root is. Measured on this machine: a
# `RUNNER_TOOL_CACHE` spelled `/var/folders/...` never prefix-matches an install root the script
# resolved to `/private/var/folders/...`, so the raw comparison let an install into the shared tool
# cache pass the guard and run to completion. A guard that depends on how the caller spells a path
# is not a guard.
for forbidden_raw in "${RUNNER_TOOL_CACHE:-}" "${GITHUB_WORKSPACE:-}" "$SOURCE"; do
    [ -n "$forbidden_raw" ] || continue
    forbidden="$(cd "$forbidden_raw" 2>/dev/null && pwd -P)" || forbidden="${forbidden_raw%/}"
    case "$scratch_root/" in
        "$forbidden"/*) bail "install root $scratch_root sits inside $forbidden, which outlives the job" ;;
    esac
done
readonly WORK="$scratch_root"
mkdir -p "$WORK" || bail "cannot create the install root $WORK"
readonly CLONE="$WORK/clone"
readonly BOOT="$WORK/uv-boot"
readonly PYTHONS="$WORK/pythons"
# `UV_PYTHON_INSTALL_DIR` in the scratch root so an interpreter fetch cannot land in
# `~/.local/share/uv`, and one `UV_CACHE_DIR` per interpreter shape so every sync figure below is a
# cold one. Measured on this host: a single cache shared by four shapes reads 4s, 5s, 3s, 2s, one
# shape against a fresh cache reads 11s, and with `UV_CACHE_DIR` unset the run never wrote the scratch
# directory at all and moved the machine's 3.9 GB cache mtime instead.
export UV_PYTHON_INSTALL_DIR="$PYTHONS"
say "install root = $WORK (wiped with the job)"

# Named here because a missing tool should read as a verdict, not as `git: command not found` two
# steps later: python:3.12-slim on aarch64 carries bash and python3 but neither git nor xz (measured).
for tool in git python3; do
    command -v "$tool" >/dev/null 2>&1 || bail "$tool is not on PATH: this image cannot run a clean-room clone"
done

# --- fresh clone: the tree that ships, no untracked file and no local state ---
t0=$SECONDS
if [ ! -d "$SOURCE/.git" ] && [ ! -f "$SOURCE/HEAD" ]; then
    bail "source $SOURCE is not a git repository"
fi
rm -rf "$CLONE"
# The tool's own words go to the log and onto stdout: measured in a container, a clone refused for a
# repository-ownership reason printed only "exited non-zero", which is the unreadable check again.
if ! git clone --no-hardlinks --quiet "$SOURCE" "$CLONE" >"$WORK/clone.log" 2>&1; then
    tail -3 "$WORK/clone.log" | sed 's/^/clean-room:   /'
    bail "git clone from $SOURCE exited non-zero (its message above)"
fi
case "$WANT_REF" in
    refs/*)
        # A `refs/...` name resolves on the SOURCE, never inside the clone. Measured 2026-10-11:
        # asking the clone for `refs/remotes/origin/main` answered with the clone's own
        # remote-tracking ref, which points at the source's `main` branch, so the run printed a
        # clean-room receipt for a lock that a merged npm group had already changed on origin.
        # An explicit fetch into a branch of its own is the reading that means what the name says.
        if ! git -C "$CLONE" fetch --quiet "$SOURCE" "$WANT_REF:refs/heads/clean-room" \
                >"$WORK/fetch.log" 2>&1; then
            tail -3 "$WORK/fetch.log" | sed 's/^/clean-room:   /'
            bail "$WANT_REF does not exist in $SOURCE (its message above)"
        fi
        git -C "$CLONE" checkout --quiet clean-room || bail "checkout of $WANT_REF failed" ;;
    *)
        git -C "$CLONE" checkout --quiet "$WANT_REF" >/dev/null 2>&1 \
            || bail "$WANT_REF does not resolve in the clone" ;;
esac
timed clone $((SECONDS - t0))
say "clone: $(git -C "$CLONE" rev-parse --short HEAD) $(git -C "$CLONE" log -1 --format=%s)"
say "clone: locks $(git -C "$CLONE" hash-object uv.lock | cut -c1-12)/$(git -C "$CLONE" hash-object app/pnpm-lock.yaml | cut -c1-12) (uv.lock/pnpm-lock.yaml)"

# --- the pinned resolver, bootstrapped inside the scratch root ---
t0=$SECONDS
rm -rf "$BOOT"
/usr/bin/env python3 -m venv "$BOOT" >/dev/null 2>&1 \
    || bail "no python3 to bootstrap uv with"
"$BOOT/bin/pip" install --quiet "uv==$UV_VERSION" >/dev/null 2>&1 \
    || bail "the pinned resolver uv==$UV_VERSION could not be installed into $BOOT"
readonly UVBIN="$BOOT/bin/uv"
timed uv-bootstrap $((SECONDS - t0))
say "resolver: $("$UVBIN" --version)"

# --- lock-exactness of the installed set, measured by the target interpreter ---
verify_python() {
    local venv="$1" shape="$2"
    local reqs="$WORK/requirements-$shape.txt"
    if ! ( cd "$CLONE" && "$UVBIN" export --frozen --no-emit-project --no-hashes -q \
            "${EXTRAS[@]}" -o "$reqs" ) >/dev/null 2>&1; then
        fail "uv export could not read the lock for the $shape check"
        return
    fi
    "$venv/bin/python" - "$reqs" "$shape" <<'PY'
import re
import sys
from pathlib import Path

try:
    from pip._vendor.packaging.requirements import Requirement
except Exception as exc:
    print(f"clean-room: FAIL no marker evaluator in the target venv ({exc})")
    sys.exit(2)


def canonical(name):
    # PEP 503: runs of -_. all fold to a single dash, so `pdfminer.six` and `pdfminer-six` are
    # the same project. Comparing on the raw spelling invents a MISSING and an UNEXPECTED pair.
    return re.sub(r"[-_.]+", "-", name).lower()

reqs_path, shape = Path(sys.argv[1]), sys.argv[2]
raw = reqs_path.read_text(encoding="utf-8").replace("\\\n", " ")

expected = {}
for line in raw.splitlines():
    line = line.split("#", 1)[0].strip()
    if not line or line.startswith("-"):
        continue
    req = Requirement(line)
    if req.marker is None or req.marker.evaluate():
        version = next((s.version for s in req.specifier), "")
        expected[canonical(req.name)] = version

from importlib.metadata import distributions

names = {}
for dist in distributions():
    name = dist.metadata["Name"]
    if name:
        names[canonical(name)] = dist.version
# The product itself is the one package `--no-emit-project` keeps out of the expected set, so it
# needs its own verdict: an install that resolves every dependency and never builds ephe is a
# green count over an environment that cannot run the software.
project_installed = "ephe" in names
names.pop("ephe", None)

missing = sorted(set(expected) - set(names))
# `uv venv --seed` puts pip in the environment so the receipt can name it; the lock did not
# install it, so it is counted as seed rather than as a package nobody decided on. A seed name
# that the lock does require still shows up as MISSING, because that side is a plain difference.
seed_names = {"pip", "setuptools", "wheel"}
extra = sorted(set(names) - set(expected))
seed = [name for name in extra if name in seed_names]
unexpected = [name for name in extra if name not in seed_names]
print(f"clean-room: py {shape} against the lock: {len(missing)} MISSING, {len(unexpected)} UNEXPECTED "
      f"({len(expected)} expected, {len(names)} installed, {len(seed)} seed: {', '.join(seed) or 'none'})")
for name in missing[:20]:
    print(f"clean-room:   MISSING {name} {expected[name]}")
for name in unexpected[:20]:
    print(f"clean-room:   UNEXPECTED {name} {names[name]}")
if not project_installed:
    print("clean-room:   MISSING ephe (the product itself is not installed in this environment)")
sys.exit(1 if missing or unexpected or not project_installed else 0)
PY
    if [ $? -ne 0 ]; then
        fail "the $shape environment is not lock-exact (see the MISSING/UNEXPECTED lines above)"
    fi
}

# --- one cold install per interpreter shape ---
first_venv=""
if want_target py; then
    for shape in "${shapes[@]}"; do
        [ -n "$shape" ] || continue
        venv="$WORK/venv-$shape"
        cache="$WORK/uv-cache-$shape"
        rm -rf "$venv" "$PYTHONS" "$cache"
        export UV_CACHE_DIR="$cache"

        t0=$SECONDS
        if ! "$UVBIN" python install "$shape" >/dev/null 2>&1; then
            fail "uv could not provide CPython $shape into $PYTHONS"
            continue
        fi
        fetch_time=$((SECONDS - t0))
        timed "interpreter-$shape" "$fetch_time"

        t0=$SECONDS
        if ! "$UVBIN" venv --seed --python "$shape" "$venv" >/dev/null 2>&1; then
            fail "uv venv --seed failed for $shape"
            continue
        fi
        # Two flags decide what the receipt means. `--active` is where the install lands: without
        # it uv writes `$CLONE/.venv` and the measured venv stays empty (measured here: 244
        # entries in the clone, 5 in the target, so `0 MISSING` would have been a fiction).
        # `--python` is what it lands on: unpinned, uv recreated this venv on the host's 3.13 and
        # dropped the seed pip with it -- the same silent substitution the CI lane hit on PATH.
        if ! ( cd "$CLONE" && VIRTUAL_ENV="$venv" "$UVBIN" sync --frozen --active \
                --python "$shape" "${EXTRAS[@]}" ) >/dev/null 2>&1; then
            sync_time=$((SECONDS - t0))
            timed "uv-sync-$shape" "$sync_time"
            fail "uv sync --frozen exited non-zero for $shape (cold ${sync_time}s): the lock cannot be installed as written"
            continue
        fi
        sync_time=$((SECONDS - t0))
        timed "uv-sync-$shape" "$sync_time"
        first_venv="${first_venv:-$venv}"

        got="$("$venv/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
        if [ "$got" != "$shape" ]; then
            fail "shape $shape resolved to CPython $got: the leg does not run the interpreter it names"
        fi
        say "shape $shape: interpreter ${fetch_time}s, uv sync --frozen ${sync_time}s cold, exit 0"
        say "shape $shape: cold cache $cache holds $(find "$cache" -type f 2>/dev/null | wc -l | tr -d ' ') files, $(du -sh "$cache" 2>/dev/null | cut -f1)"
        say "shape $shape: CPython $got at $("$venv/bin/python" -c 'import sys; print(sys.prefix)')"
        say "shape $shape: $("$venv/bin/pip" -V 2>/dev/null || echo 'no pip in this environment')"
        verify_python "$venv" "$shape"
    done
    [ -n "$first_venv" ] || fail "no interpreter shape installed"
else
    say "py: not requested (EPHE_CLEAN_ROOM_TARGETS=$TARGETS)"
fi

# --- the JS half, against the same fresh clone and a store inside the scratch root ---
if want_target js; then
    pinned="$(sed -n 's/.*"packageManager": *"pnpm@\([^"]*\)".*/\1/p' "$CLONE/app/package.json" | head -1)"
    if [ -z "$pinned" ]; then
        bail "app/package.json declares no packageManager pin to install against"
    fi
    # Resolved inside app/: corepack's shim picks the version from the nearest package.json, so a
    # `pnpm --version` from anywhere else reports a different number than the install will use.
    got="$(cd "$CLONE/app" && pnpm --version 2>/dev/null || echo none)"
    if [ "$got" != "$pinned" ] && command -v corepack >/dev/null 2>&1; then
        export COREPACK_HOME="$WORK/corepack"
        corepack enable --install-directory "$WORK/bin" >/dev/null 2>&1
        PATH="$WORK/bin:$PATH"
        got="$(cd "$CLONE/app" && pnpm --version 2>/dev/null || echo none)"
        [ "$got" = "$pinned" ] && say "js: corepack brought pnpm $got into $WORK/bin"
    fi
    if [ "$got" != "$pinned" ]; then
        fail "pnpm $got does not match the packageManager pin $pinned: a different pnpm resolves a different graph"
    else
        say "js: pnpm $got matches packageManager"
    fi
    if [ "$got" = "$pinned" ]; then
        t0=$SECONDS
        ( cd "$CLONE/app" && pnpm install --frozen-lockfile --store-dir "$WORK/pnpm-store" ) \
            > "$WORK/pnpm-install.log" 2>&1
        js_status=$?
        timed pnpm-install $((SECONDS - t0))
        if [ "$js_status" -ne 0 ]; then
            fail "pnpm install --frozen-lockfile exited $js_status; tail of its output:"
            tail -8 "$WORK/pnpm-install.log" | sed 's/^/clean-room:   /'
        else
            say "js: pnpm install --frozen-lockfile exit 0, store $WORK/pnpm-store"
            ( cd "$CLONE/app" && pnpm install --frozen-lockfile --offline --store-dir "$WORK/pnpm-store" ) \
                > "$WORK/pnpm-verify.log" 2>&1
            if grep -qiE "Already up to date|Already found" "$WORK/pnpm-verify.log"; then
                say "js: an offline re-install against the same lockfile changes nothing (lock-exact)"
            else
                fail "an offline re-install did not report the tree already satisfied: $(tail -3 "$WORK/pnpm-verify.log" | tr '\n' ' ')"
            fi
        fi
    fi
else
    say "js: not requested (EPHE_CLEAN_ROOM_TARGETS=$TARGETS)"
fi

# --- the CI strand's own guard, over the tree this run installed ---
judge_venv="${first_venv:-$BOOT}"
t0=$SECONDS
if ( cd "$CLONE" && PATH="$judge_venv/bin:$PATH" bash scripts/ci_preflight.sh ) > "$WORK/preflight.log" 2>&1; then
    say "preflight: $(tail -1 "$WORK/preflight.log")"
else
    pf=$?
    fail "scripts/ci_preflight.sh exited $pf over this install"
    grep -E "^  FAIL|::error::" "$WORK/preflight.log" | sed 's/^/clean-room:   /'
fi
timed preflight $((SECONDS - t0))

say "wall: ${wall[*]}"
if [ "$failures" -gt 0 ]; then
    say "VERDICT fail ($failures check(s) did not hold)"
    exit 1
fi
say "VERDICT pass"
