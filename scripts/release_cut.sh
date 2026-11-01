#!/usr/bin/env bash
# Ephe release machine — one command from a green tree to the tag release.yml fires on.
#
# The default run makes exactly one write: the annotated tag. Every invariant the tag
# depends on is checked first and a failed check refuses the tag with the reason and the
# fix. Cheap structural checks run before the gates, so a broken invariant stops the run
# before the suite spends minutes on a tree that could not ship anyway. The desktop build
# and the updater feed are a separate, later step (scripts/release_desktop.sh); this only
# cuts the tag.
#
#   scripts/release_cut.sh --dry-run              rehearse every check, tag nothing
#   scripts/release_cut.sh                        check the tree, then cut vX.Y.Z
#   scripts/release_cut.sh --message "headline"   cut with the round's headline
#   scripts/release_cut.sh --push                 cut, then push (starts release.yml)
#   scripts/release_cut.sh --skip-gates           structure only, no gate set
#   scripts/release_cut.sh --full                 gates plus the pytest bar and tsc
#
# Environment: EPHE_RELEASE_BRANCH (default main), EPHE_RELEASE_REMOTE (default origin).
# Refusals exit 1 and each names the fix; a usage or environment error exits 2.
# The runbook is docs/RELEASE_RUNBOOK.md.
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"

BRANCH="${EPHE_RELEASE_BRANCH:-main}"
REMOTE="${EPHE_RELEASE_REMOTE:-origin}"
WANT=""
MESSAGE=""
DRY_RUN=0
DO_PUSH=0
SKIP_GATES=0
FULL_GATES=0
ALLOW_DIRTY=0
ALLOW_LOCAL=0

while [ $# -gt 0 ]; do
  case "$1" in
    --version) WANT="${2:-}"; shift 2 ;;
    --version=*) WANT="${1#*=}"; shift ;;
    --message) MESSAGE="${2:-}"; shift 2 ;;
    --message=*) MESSAGE="${1#*=}"; shift ;;
    --branch) BRANCH="${2:-}"; shift 2 ;;
    --remote) REMOTE="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --push) DO_PUSH=1; shift ;;
    --skip-gates) SKIP_GATES=1; shift ;;
    --full) FULL_GATES=1; shift ;;
    --allow-dirty) ALLOW_DIRTY=1; shift ;;
    --local) ALLOW_LOCAL=1; shift ;;
    -h|--help) awk 'NR>1 && /^#/ {sub(/^# ?/,""); print; next} NR>1 {exit}' "$0"; exit 0 ;;
    *) echo "release: unknown argument: $1" >&2; exit 2 ;;
  esac
done

# The python gates prefer the project venv, which carries the pinned interpreters CI uses.
PY="python3"
[ -x "$ROOT/.venv/bin/python" ] && PY="$ROOT/.venv/bin/python"

PROBLEMS=""
refuse() { PROBLEMS="${PROBLEMS}$1|$2
"; }
ok()   { printf '  ok       %s\n' "$1"; }
bad()  { printf '  REFUSED  %s\n' "$1"; }

semver_num() { printf '%s\n' "${1%%-*}"; }

# semver_pre X -> the prerelease part, empty when the version carries none.
semver_pre() {
  case "$1" in
    *-*) printf '%s\n' "${1#*-}" ;;
    *) printf '\n' ;;
  esac
}

# semver_gt A B -> true when A sorts strictly above B.
#
# The prerelease suffix decides when the numbers are equal, because this product's whole
# update story lives there: 0.1.0-beta.10 is ahead of 0.1.0-beta.9, and the release 0.1.0
# is ahead of every prerelease of it. Identifiers compare numerically when both are digits
# and as ASCII otherwise; a shorter prerelease that matches point for point is the lower
# one (semver §11).
semver_gt() {
  local a b i x y pa pb n
  a="$(semver_num "$1")"; b="$(semver_num "$2")"
  local IFS=.
  local -a A B
  read -r -a A <<< "$a"; read -r -a B <<< "$b"
  for i in 0 1 2; do
    x="${A[$i]:-0}"; y="${B[$i]:-0}"
    [ "$x" -gt "$y" ] && return 0
    [ "$x" -lt "$y" ] && return 1
  done
  pa="$(semver_pre "$1")"; pb="$(semver_pre "$2")"
  [ -z "$pa" ] && [ -z "$pb" ] && return 1
  [ -z "$pa" ] && return 0
  [ -z "$pb" ] && return 1
  local -a P Q
  read -r -a P <<< "$pa"; read -r -a Q <<< "$pb"
  n=${#P[@]}
  [ ${#Q[@]} -gt "$n" ] && n=${#Q[@]}
  for ((i = 0; i < n; i++)); do
    x="${P[i]:-}"; y="${Q[i]:-}"
    [ -z "$y" ] && return 0
    [ -z "$x" ] && return 1
    if [[ "$x" =~ ^[0-9]+$ ]] && [[ "$y" =~ ^[0-9]+$ ]]; then
      [ "$((10#$x))" -gt "$((10#$y))" ] && return 0
      [ "$((10#$x))" -lt "$((10#$y))" ] && return 1
    elif [[ "$x" =~ ^[0-9]+$ ]]; then
      return 1
    elif [[ "$y" =~ ^[0-9]+$ ]]; then
      return 0
    else
      [[ "$x" > "$y" ]] && return 0
      [[ "$x" < "$y" ]] && return 1
    fi
  done
  return 1
}

read_pyproject_version() {
  sed -n 's/^version *= *"\([^"]*\)".*/\1/p' "$ROOT/pyproject.toml" | head -1
}

read_json_field() {
  "$PY" - "$1" "$2" <<'PYEOF'
import json, sys
try:
    print(json.load(open(sys.argv[1])).get(sys.argv[2], ""))
except Exception:
    print("")
PYEOF
}

# last released version = the topmost `## [...]` header that starts with a digit, kept whole
# including its prerelease, so a beta line compares against the beta that is actually on top.
last_released_version() {
  sed -n 's/^## \[\([0-9][^]]*\)\].*/\1/p' "$ROOT/CHANGELOG.md" | head -1
}

run_gate() {
  local label="$1"; shift
  local log rc=0
  log="$(mktemp "${TMPDIR:-/tmp}/ephe-release-gate.XXXXXX")"
  ( "$@" ) >"$log" 2>&1 || rc=$?
  if [ "$rc" -ne 0 ]; then
    bad "gate failed: $label (exit $rc)"
    sed 's/^/             /' "$log" | tail -12
    refuse "the '$label' gate failed on this commit" "run $label by hand, fix it, commit, re-run"
  else
    ok "gate $label"
  fi
  rm -f "$log"
}

gate_pytest() { "$ROOT/scripts/run-tests.sh" -q; }
gate_tsc()    { ( cd "$ROOT/app" && npx tsc --noEmit ); }

printf 'ephe release — branch %s @ %s\n' "$BRANCH" "$(git rev-parse --short HEAD 2>/dev/null || echo '?')"

# 1. version carriers agree, and the candidate is valid
PYV="$(read_pyproject_version)"
PKGV="$(read_json_field "$ROOT/app/package.json" version)"
TAURIV="$(read_json_field "$ROOT/app/src-tauri/tauri.conf.json" version)"

if [ -z "$PYV" ]; then
  refuse "cannot read [project].version from pyproject.toml" "fix the manifest"
else
  if [ "$PYV" = "$PKGV" ] && [ "$PYV" = "$TAURIV" ]; then
    ok "version carriers agree: $PYV"
  else
    bad "version carriers disagree"
    printf '             pyproject.toml %s | app/package.json %s | tauri.conf.json %s\n' "$PYV" "${PKGV:-?}" "${TAURIV:-?}"
    refuse "the three version carriers do not name the same X.Y.Z" "bump all three to one version, commit, re-run"
  fi
fi

V="$PYV"
if [ -n "$WANT" ]; then
  if [ -n "$PYV" ] && [ "$WANT" != "$PYV" ]; then
    refuse "--version $WANT does not match the carriers ($PYV)" "bump the carriers to $WANT, commit, re-run"
  fi
  V="$WANT"
fi

if [ -z "$V" ]; then
  refuse "no version could be resolved" "pass --version X.Y.Z or set [project].version"
elif ! printf '%s' "$V" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?$'; then
  refuse "'$V' is not a semver X.Y.Z" "use X.Y.Z (an optional -suffix is allowed)"
fi
TAG="v$V"

# 2. the branch the tag is cut from
CUR_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')"
if [ "$CUR_BRANCH" = "$BRANCH" ]; then
  ok "on the release branch ($BRANCH)"
else
  bad "on '$CUR_BRANCH', release tags come from '$BRANCH'"
  refuse "HEAD is on '$CUR_BRANCH', not the release branch '$BRANCH'" "git switch $BRANCH (or set EPHE_RELEASE_BRANCH)"
fi

# 3. a clean tree
DIRTY_N="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
if [ "${DIRTY_N:-0}" -eq 0 ]; then
  ok "worktree is clean"
elif [ "$ALLOW_DIRTY" = 1 ]; then
  printf '  warn     worktree has %s path(s) that differ from HEAD (--allow-dirty)\n' "$DIRTY_N"
else
  bad "worktree is not clean: $DIRTY_N path(s) differ from HEAD"
  git status --porcelain | sed 's/^/             /' | head -8
  refuse "the worktree has uncommitted or untracked changes" "commit or stash them; a tag names a committed tree"
fi

# 4. the tag does not exist yet
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null 2>&1; then
  bad "tag $TAG already exists"
  refuse "tag $TAG already exists at $(git rev-parse --short "$TAG")" "delete it to re-cut, or bump to a new version"
else
  ok "tag $TAG is free"
fi

# 5. the changelog is folded for this cut and nothing newer sits above it.
#
# A `## [V]` section for the version being tagged is the normal state before the tag: the
# checklist's `changelog-section` item, `release_notes.py` and every beta tag since beta.4 all
# require the curated section to exist first, so the machine requires it too and refuses only
# when the section is missing or a *newer* one sits on top. "Already released" is the tag, and
# check 4 owns that refusal.
if [ -n "$V" ]; then
  LASTV="$(last_released_version)"
  FOLDED=0
  grep -qF "## [$V]" "$ROOT/CHANGELOG.md" 2>/dev/null && FOLDED=1
  if [ -z "$LASTV" ] && [ "$FOLDED" = 1 ]; then
    ok "CHANGELOG.md carries ## [$V] as its topmost release"
  elif [ -z "$LASTV" ]; then
    bad "CHANGELOG.md has no released section at all"
    refuse "CHANGELOG.md has no \`## [$V]\` section" "write the entry for $V, commit, re-run"
  elif [ "$LASTV" = "$V" ]; then
    ok "the topmost CHANGELOG section is [$V], folded for this cut"
  elif semver_gt "$LASTV" "$V" 2>/dev/null; then
    bad "a newer release ($LASTV) is already logged above [$V]"
    refuse "$V is behind the last release [$LASTV]" "bump the carriers above $LASTV and write the new CHANGELOG entry"
  elif [ "$FOLDED" = 1 ]; then
    ok "version $V is ahead of the last release ($LASTV) and folded for the cut"
  else
    bad "the last release is $LASTV and no \`## [$V]\` section exists"
    refuse "CHANGELOG.md has no \`## [$V]\` section" "write the entry for $V, commit, re-run"
  fi
fi

# 6. HEAD is the commit origin can fetch
if [ "$ALLOW_LOCAL" = 1 ]; then
  printf '  warn     remote sync check skipped (--local)\n'
elif git fetch --quiet "$REMOTE" "$BRANCH" >/dev/null 2>&1; then
  HEAD_SHA="$(git rev-parse HEAD)"
  UP_SHA="$(git rev-parse "refs/remotes/$REMOTE/$BRANCH" 2>/dev/null || true)"
  if [ -z "$UP_SHA" ]; then
    refuse "no refs/remotes/$REMOTE/$BRANCH to compare against" "git push -u $REMOTE $BRANCH, or pass --local"
  elif [ "$HEAD_SHA" = "$UP_SHA" ]; then
    ok "HEAD matches $REMOTE/$BRANCH"
  else
    AHEAD="$(git rev-list --count "$REMOTE/$BRANCH..HEAD" 2>/dev/null || echo '?')"
    BEHIND="$(git rev-list --count "HEAD..$REMOTE/$BRANCH" 2>/dev/null || echo '?')"
    bad "HEAD is $AHEAD ahead / $BEHIND behind $REMOTE/$BRANCH"
    refuse "the commit to tag is not on $REMOTE/$BRANCH" "push (or pull) first, or pass --local to tag an unpushed commit"
  fi
else
  printf '  warn     could not fetch %s — sync check skipped (offline?)\n' "$REMOTE"
fi

# 7. gates
if [ "$SKIP_GATES" = 1 ]; then
  printf '  skip     gate set (--skip-gates)\n'
else
  run_gate "changelog [Unreleased]" "$PY" "$ROOT/scripts/changelog_unreleased.py" --check
  run_gate "language ratchet"       "$PY" "$ROOT/scripts/language_gate.py"
  run_gate "architecture ratchet"   node  "$ROOT/scripts/architecture_check.mjs" check
  if [ "$ALLOW_LOCAL" = 1 ]; then
    printf '  warn     provenance gate skipped (--local: no trunk ref to compare)\n'
  else
    # The trunk ref is the release remote's, not the literal `origin`, and the tag list comes
    # from that remote's own refs. A working clone can hold another lineage's objects under the
    # same tag names, and judging those files a divergence in a release line that never carried
    # it: measured 2026-11-01, the published v0.1.0, v0.1.1 and v0.1.0-beta.9 sit on
    # public/main while this machine's refs/tags held the private lineage's commits.
    if git fetch --quiet --prune "$REMOTE" "+refs/tags/*:refs/remotes/$REMOTE/tags/*" >/dev/null 2>&1; then
      TAG_NS="refs/remotes/$REMOTE/tags"
    else
      TAG_NS="refs/tags"
      printf '  warn     %s carries no tag refs here — judging this checkout\n' "$REMOTE"
    fi
    run_gate "provenance" "$PY" "$ROOT/scripts/provenance_check.py" \
      --base "$REMOTE/$BRANCH" --baseline-at "$REMOTE/$BRANCH" --tag-namespace "$TAG_NS"
  fi
  if [ "$FULL_GATES" = 1 ]; then
    run_gate "pytest release bar"   gate_pytest
    run_gate "typescript"           gate_tsc
  fi
fi

# verdict
if [ -n "$PROBLEMS" ]; then
  printf '\nrelease refused — %s check(s) failed:\n' "$(printf '%s' "$PROBLEMS" | grep -c .)"
  i=1
  printf '%s' "$PROBLEMS" | while IFS='|' read -r why fix; do
    [ -z "$why" ] && continue
    printf '  %d. %s\n       fix: %s\n' "$i" "$why" "$fix"
    i=$((i+1))
  done
  exit 1
fi

[ -n "$MESSAGE" ] || MESSAGE="Ephe $V"

if [ "$DRY_RUN" = 1 ]; then
  printf '\nall checks passed — dry run, nothing written.\n'
  printf '  git tag -a %s -m "%s"\n' "$TAG" "$MESSAGE"
  [ "$DO_PUSH" = 1 ] && printf '  git push %s %s\n' "$REMOTE" "$TAG"
  exit 0
fi

git tag -a "$TAG" -m "$MESSAGE" || { echo "release: git tag failed" >&2; exit 2; }
printf '\nrelease %s created at %s\n' "$TAG" "$(git rev-parse --short "$TAG")"

if [ "$DO_PUSH" = 1 ]; then
  git push "$REMOTE" "$TAG" && printf 'pushed %s — release.yml starts on the tag\n' "$TAG"
else
  printf 'push with:  git push %s %s\n' "$REMOTE" "$TAG"
fi
