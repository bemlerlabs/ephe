#!/usr/bin/env bash
# Hermetic preflight for CI legs.
#
# Prints what the job's tools actually resolve to, and fails when they resolve outside the job's
# own install. The class it guards is ambient host state reaching a job on a self-hosted runner:
# a `pytest` left in `~/.local/bin` by an April `pip install --user` shadowed a leg's own pytest
# (PATH carries `~/.local/bin`), and a tool-cache interpreter that imports nothing from its own
# site-packages ran 3499 tests in the parent while every scrubbed child died on `No module named
# pytest`. Both read as product failures in the test report instead of as a machine problem.
#
# The loader probe reproduces the third member of that class directly: a hermetic test child
# starts from an empty environment, so if the interpreter needs `LD_LIBRARY_PATH` to load and that
# value did not reach the job, the child exits 127 while the parent is green.
set -uo pipefail

failures=()

job_roots=()
for root in "${RUNNER_TOOL_CACHE:-}" "${GITHUB_WORKSPACE:-}" "${RUNNER_TEMP:-}" "${NVM_BIN:-}"; do
    [ -n "$root" ] && job_roots+=("${root%/}")
done

inside_job_install() {
    local path="$1" root
    [ -n "$path" ] || return 1
    [ "${#job_roots[@]}" -gt 0 ] || return 1
    for root in "${job_roots[@]}"; do
        case "$path" in "$root"/*) return 0 ;; esac
    done
    return 1
}

self_hosted=0
[ "${RUNNER_ENVIRONMENT:-hosted}" = "self-hosted" ] && self_hosted=1

echo "preflight: runner environment = ${RUNNER_ENVIRONMENT:-unset}, job roots:"
if [ "${#job_roots[@]}" -gt 0 ]; then
    printf '  %s\n' "${job_roots[@]}"
fi

# --- interpreter ---
python_head="$(command -v python || true)"
echo "preflight: \`python\` head -> ${python_head:-not on PATH}"
interpreter="$python_head"
[ -n "$interpreter" ] || interpreter="$(command -v python3 || true)"
if [ -z "$interpreter" ]; then
    failures+=("no interpreter resolves on this job's PATH")
else
    sys_executable="$("$interpreter" -c 'import sys; print(sys.executable)')"
    sys_prefix="$("$interpreter" -c 'import sys; print(sys.prefix)')"
    echo "preflight: sys.executable -> $sys_executable"
    echo "preflight: sys.prefix     -> $sys_prefix"
    case "$sys_executable" in
        "$HOME"/*|/usr/bin/*|/usr/local/bin/*)
            if [ "$self_hosted" = 1 ] && ! inside_job_install "$sys_executable"; then
                failures+=("interpreter $sys_executable is host state, not this job's install")
            fi ;;
    esac
    job_roots+=("${sys_prefix%/}")

    # A pull-request leg must not install into the listener's tool-cache interpreter. `_tool`
    # survives the job: the Dependabot leg of PR run 9910615d logged 110 `Requirement already
    # satisfied` lines out of `_tool/Python/3.12.15/arm64/lib/python3.12/site-packages` on
    # `the lab runner-3`, so whatever a proposed range installs there is inherited by the next
    # main-push leg. RUNNER_TEMP is wiped between jobs, which is why the venv step in tests.yml
    # puts a pull-request install under it -- and this is the line that fails if that step is ever
    # dropped or outranked on PATH.
    if [ "$self_hosted" = 1 ] && [ "${GITHUB_EVENT_NAME:-}" = "pull_request" ] && [ -n "${RUNNER_TEMP:-}" ]; then
        # Both sides through realpath: `/tmp` is a symlink to `/private/tmp` on macOS, and a guard
        # that reds on a correctly isolated leg is a guard somebody switches off. One interpreter
        # call carries both, because the rule is a prefix comparison, not two comparisons.
        roots="$("$interpreter" -c 'import os,sys
print(os.path.realpath(sys.argv[1]))
print(os.path.realpath(sys.argv[2]))' "${RUNNER_TEMP%/}" "$sys_prefix" 2>/dev/null)"
        temp_root="${roots%%$'\n'*}"
        prefix_root="${roots##*$'\n'}"
        case "$prefix_root" in
            "$temp_root"/*)
                echo "preflight: pull-request install root = $prefix_root (wiped with the job)" ;;
            *)
                failures+=("this pull-request leg installs into $prefix_root: the listener's tool cache keeps the result for the next run") ;;
        esac
    fi

    # A user site-packages directory that CPython inserts ahead of the leg's own site-packages is
    # the leak in full: imports resolve to the machine, and pip reads the same distribution as
    # already satisfied, so the leg silently tests something it never installed.
    user_site_info="$("$interpreter" -c 'import site, sys
user_site = site.getusersitepackages()
print(user_site, "on path" if user_site in sys.path else "off path")' 2>/dev/null || true)"
    if [ -n "$user_site_info" ]; then
        echo "preflight: user site = $user_site_info (PYTHONNOUSERSITE=${PYTHONNOUSERSITE:-<unset>})"
        case "$user_site_info" in
            *"on path")
                if [ "$self_hosted" = 1 ]; then
                    failures+=("host user site-packages is on this job's import path: ${user_site_info%% *}")
                fi ;;
        esac
    fi
fi

# --- pytest: importable from the interpreter, and its head is that interpreter's own ---
if [ -n "$interpreter" ]; then
    pytest_module="$("$interpreter" -c 'import pytest; print(pytest.__file__)' 2>/dev/null || true)"
    if [ -z "$pytest_module" ]; then
        echo "preflight: pytest is not importable from $interpreter (legs that do not install it are fine)"
    else
        echo "preflight: import pytest -> $pytest_module"
        pytest_head="$(command -v pytest || true)"
        echo "preflight: \`pytest\` head -> ${pytest_head:-not on PATH}"
        if [ -n "$pytest_head" ] && [ "$self_hosted" = 1 ] && ! inside_job_install "$pytest_head"; then
            failures+=("pytest head $pytest_head resolves outside the job's install; the leg's own pytest is shadowed")
        fi
    fi
fi

# --- node and pnpm: checked only where they exist, because these legs do not install them ---
for tool in node pnpm; do
    head_path="$(command -v "$tool" || true)"
    echo "preflight: \`$tool\` head -> ${head_path:-not on PATH}"
    if [ -n "$head_path" ] && [ "$self_hosted" = 1 ] && ! inside_job_install "$head_path"; then
        failures+=("$tool head $head_path resolves outside the job's install and outside the runner's provisioned node dir")
    fi
done

# --- loader environment reaching the job ---
echo "preflight: LD_LIBRARY_PATH = ${LD_LIBRARY_PATH:-<unset>}"
if [ "$self_hosted" = 1 ] && [ -n "${interpreter:-}" ] && command -v ldd >/dev/null 2>&1; then
    probe_status=0
    env -i PATH=/usr/bin LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}" "$interpreter" -c 'pass' >/dev/null 2>&1 || probe_status=$?
    if [ "$probe_status" = 0 ]; then
        echo "preflight: a scrubbed child of this interpreter starts"
    else
        failures+=("a hermetic child (env -i, PATH=/usr/bin, LD_LIBRARY_PATH as the job has it) exits $probe_status on $interpreter: tests that build their own environment will die on the loader, not on the assertion")
    fi
fi

if [ "${#failures[@]}" -gt 0 ]; then
    echo "::error::preflight failed — ambient state is reaching this job"
    for failure in "${failures[@]}"; do
        echo "  FAIL $failure"
    done
    exit 1
fi

echo "preflight: interpreter, pytest and node/pnpm all resolve inside this job's install"
