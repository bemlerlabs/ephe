#!/usr/bin/env bash
# The static layer, run locally, before the commit exists.
#
# Wave I of docs/CI_HYBRID_CAPACITY_2026-10-11.md. Called from `.husky/pre-commit` and safe to run
# by hand. The reason it exists is that `.pre-commit-config.yaml` listed four hooks while
# `core.hooksPath` pointed at `.husky`, so nothing ever executed them and the two lint tools had
# therefore never run anywhere on this repository. The rules below are the ones that can be decided
# from the content a commit carries -- ruff's blocking subset and the prose ratchet from
# `scripts/lint_policy.sh`, the hygiene rules over the index -- and they are the same implementations
# `.github/workflows/lint.yml` and `hygiene.yml` run, read from one place so local and CI cannot
# disagree about what a finding means.
#
# Two design points, both deliberate:
#   - No stashing. `app/lint-staged.config.js` hides and restores every *unstaged* change in the
#     worktree, which on this shared tree has twice rewritten files another worker held open.
#     Nothing in here writes to the index or the worktree, so it cannot add a third instance.
#   - Every check reads content, not the disk: ruff and the prose pass read the STAGED BLOB
#     (`git show :path`), and the hygiene rules read the index. The file on disk can carry someone
#     else's unfinished edit, and a refusal naming an unstaged line would be this hook's own
#     version of that defect. Nothing here scans a whole tree: the two whole-tree ratchets stay in
#     `ci-gates.yml`, where a clean checkout of the commit is what gets judged. See the prose
#     section below for the measurement that moved them out of the hook.
#
#   - A status number is only a verdict when the check ran to the end. 128+N is a signal death: the
#     instrument is gone and decided nothing. Those two outcomes get different words and different
#     exit codes -- 1 for a gate that reached a failing verdict, 3 for a check that could not decide
#     -- and both refuse the commit, because an unchecked commit is not a clean one. The ruff section
#     below names the pipeline shape that made this rule necessary.
#
# Runs on the bash 3.2 that macOS still ships, hence the array-count guards instead of bare
# `"${arr[@]}"` expansions under `set -u`.
set -uo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root" || exit 1

skip=()
fail=()
died=()

# shellcheck source=scripts/lint_policy.sh
. "$root/scripts/lint_policy.sh"

# --- what is being committed ---
# Added, copied, modified, renamed; a deletion has no blob to lint. The scope is the whole index
# because this hook cannot see the pathspec `git commit -- <paths>` will use, so on a shared tree a
# second strand's staged path is judged here too. `EPHE_COMMIT_PATHS` (space-separated) narrows it
# to the paths one commit takes, and the first line names the scope the run decided with.
explicit=()
if [ -n "${EPHE_COMMIT_PATHS:-}" ]; then
    read -r -a explicit <<< "$EPHE_COMMIT_PATHS"
fi
staged=()
while IFS= read -r -d '' path; do
    staged+=("$path")
done < <(git diff --cached --name-only --diff-filter=ACMR -z)

scope=()
if [ "${#explicit[@]}" -gt 0 ]; then
    # The array-count guard this file's own header asks for: with a declaration and an index
    # holding nothing to lint (a commit of deletions, or a declaration that names no staged
    # path) the bare expansion is an unbound-variable error under `set -u` on bash 3.2.
    if [ "${#staged[@]}" -gt 0 ]; then
        for path in "${staged[@]}"; do
            for want in "${explicit[@]}"; do
                [ "$path" = "$want" ] && scope+=("$path")
            done
        done
    fi
    echo "ci-local: scope from EPHE_COMMIT_PATHS, ${#scope[@]} of ${#staged[@]} staged path(s)"
else
    scope=("${staged[@]:-}")
    echo "ci-local: scope is the whole index, ${#scope[@]} staged path(s); EPHE_COMMIT_PATHS narrows it"
fi

py_files=()
for path in "${scope[@]:-}"; do
    case "$path" in *.py) py_files+=("$path") ;; esac
done

echo "ci-local: ${#py_files[@]} python path(s) in scope"

# --- ruff, blocking subset, against the staged blobs ---
if [ "${#py_files[@]}" -gt 0 ]; then
    # The repository's own venv first: the numbers in scripts/lint_policy.sh were counted with the
    # pinned release, and this host's PATH ruff is 0.15.7, where PLW1514-class rules differ.
    ruff_bin="$root/.venv/bin/ruff"
    [ -x "$ruff_bin" ] || ruff_bin="$(command -v ruff || true)"
    if [ -z "$ruff_bin" ]; then
        skip+=("no ruff in .venv or on PATH, so the blocking subset was NOT checked locally. CI installs ${EPHE_RUFF_VERSION} from scripts/lint_policy.sh and gates on it.")
    else
        local_version="$("$ruff_bin" --version 2>/dev/null | awk '{print $2}')"
        echo "ci-local: ruff $local_version ($ruff_bin), CI pins $EPHE_RUFF_VERSION"
        blob_file="$(mktemp)"
        ruff_out="$(mktemp)"
        for path in "${py_files[@]}"; do
            # No pipe into ruff, and that is the whole fix. `git show | ruff` under `pipefail`
            # reports the WRITER's signal death as the pipeline's status whenever ruff exits before
            # draining stdin: measured on this tree, a consumer that closes stdin early turns a
            # clean blob into status 141 every time, and the branch that follows read that as "a
            # usage error" -- refusing commits over files ruff had never looked at. The repo-verify
            # lane was refused three commits this way on 2026-10-11 (out/lane/74-report.md), on the
            # excluded evals/repo_verify paths, which are the ones where ruff finishes fastest.
            # Redirecting stdin from a file takes the writer process out of the picture, so the only
            # status left is the one ruff reached.
            if ! git show ":$path" > "$blob_file" 2>/dev/null; then
                died+=("the staged blob for $path could not be read, so the blocking subset was NOT checked")
                continue
            fi
            "$ruff_bin" check --stdin-filename "$path" --exclude "$EPHE_LINT_EXCLUDE" \
                --force-exclude --select "$EPHE_RUFF_BLOCKING" --output-format concise - \
                < "$blob_file" > "$ruff_out" 2>&1
            status=$?
            if [ "$status" -ne 0 ]; then
                cat "$ruff_out"
            fi
            if [ "$status" -ge 128 ]; then
                died+=("ruff died with signal $((status - 128)) on $path: it reached no verdict")
            elif [ "$status" -eq 1 ]; then
                fail+=("ruff: blocking finding in the staged blob $path")
            elif [ "$status" -ne 0 ]; then
                fail+=("ruff exited $status on $path: a usage error, which means scripts/lint_policy.sh carries a code ruff does not know")
            fi
        done
        rm -f "$blob_file" "$ruff_out"
    fi
fi

# --- repository hygiene: the index is what the commit is made of ---
python3 scripts/hygiene_check.py --all
hygiene_status=$?
if [ "$hygiene_status" -ge 128 ]; then
    died+=("hygiene_check.py died with signal $((hygiene_status - 128)): the index was not checked")
elif [ "$hygiene_status" -ne 0 ]; then
    fail+=("hygiene: a case collision or a tracked artifact is in the index")
fi

# --- tauri plugin parity: the JS plugin packages against the locked Rust crates ---
# The failure class this lane paid for on 2026-10-11: an npm PR moved `@tauri-apps/plugin-*` in
# `app/package.json`, nothing moved `tauri-plugin-*` in `Cargo.lock`, and `npm run tauri build`
# refused before compiling a single crate. The pair only matters when one side of it is in the
# commit, so this is a scoped check like the prose ratchet; the whole-tree verdict is the hygiene
# leg's, and both run the same script.
#
# The same script's second question is the 5x shell manifest: a route in `app/src/App.tsx` or a
# `isTauri` / `isDesktopShell` / `__TAURI__` read that the manifest does not name. Any frontend
# commit can create that drift, so every `app/src` path is in scope here.
parity_needed=0
for path in "${scope[@]:-}"; do
    case "$path" in
        app/package.json|app/package-lock.json|app/pnpm-lock.yaml|app/src-tauri/Cargo.lock|app/src-tauri/Cargo.toml|app/src/*|app/tests/playwright/shell-parity*)
            parity_needed=1
            ;;
    esac
done
if [ "$parity_needed" -eq 1 ]; then
    python3 scripts/tauri_parity.py
    parity_status=$?
    if [ "$parity_status" -ge 128 ]; then
        died+=("tauri_parity.py died with signal $((parity_status - 128)): the plugin pair was not checked")
    elif [ "$parity_status" -eq 2 ]; then
        died+=("tauri_parity.py could not read its inputs, so it reported no verdict instead of a pass")
    elif [ "$parity_status" -ne 0 ]; then
        fail+=("tauri plugin parity: app/package.json and Cargo.lock disagree on a plugin version")
    fi
else
    skip+=("tauri parity: no plugin package, Rust lock file or frontend path in scope")
fi

# --- the prose ratchet, over the blobs in scope ---
# The tree-wide `--strict` run stays in ci-gates.yml, where a clean checkout of one commit is what
# gets judged. Measured on this tree 2026-10-11: 5.4 s for the whole-tree pass, and its verdict
# belongs to files the committing strand does not hold -- while this hook was being written an
# unrelated strand took `tests/test_repo_verify_contract.py` from 0 to 1 tell, which would have
# blocked every commit in the tree. `scripts/prose_scope_check.py` runs the same instrument and the
# same baseline over the staged blobs in milliseconds and can only name a path in scope. It reads
# single files, so the repeated-header class stays in CI, and it prints that limit on its own line.
if [ "${#scope[@]}" -gt 0 ]; then
    EPHE_STAGED_PATHS="$(printf '%s\n' "${scope[@]}")" python3 scripts/prose_scope_check.py
    prose_status=$?
    if [ "$prose_status" -ge 128 ]; then
        died+=("prose_scope_check.py died with signal $((prose_status - 128)): the ratchet was not read")
    elif [ "$prose_status" -ne 0 ]; then
        fail+=("prose ratchet: a staged blob is over its baseline entry, or unreadable")
    fi
else
    skip+=("empty scope: the per-file checks had no input")
fi

# --- mypy, advisory here and in the CI leg ---
if [ "${#py_files[@]}" -gt 0 ] && command -v mypy >/dev/null 2>&1; then
    mypy --ignore-missing-imports --follow-imports=skip --no-error-summary "${py_files[@]}" \
        | head -20 | sed 's/^/ci-local: (advisory) /'
fi

if [ "${#skip[@]}" -gt 0 ]; then
    for line in "${skip[@]}"; do
        echo "ci-local: SKIP $line"
    done
fi

if [ "${#fail[@]}" -gt 0 ]; then
    for line in "${fail[@]}"; do
        echo "ci-local: FAIL $line"
    done
fi

# The two refusals are printed together and the code says which of them is the worse one: a check
# that died has told nobody anything, and a commit that also carries a real finding still has not
# been fully checked. 3 therefore wins over 1, and both lines appear above it.
if [ "${#died[@]}" -gt 0 ]; then
    for line in "${died[@]}"; do
        echo "ci-local: NO VERDICT $line"
    done
    echo "ci-local: FAIL — a check died without reaching a verdict, so this commit is unchecked"
    exit 3
fi

if [ "${#fail[@]}" -gt 0 ]; then
    exit 1
fi

echo "ci-local: pass"
