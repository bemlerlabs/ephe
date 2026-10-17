# shellcheck shell=bash
# The two ruff rule sets and the one path list they skip, in one place, so the local hook and the
# CI leg cannot drift into disagreement about what a finding means. Both consumers source this file:
# `scripts/ci_local.sh` with `. scripts/lint_policy.sh`, and the run blocks in
# `.github/workflows/lint.yml` the same way.
#
# Every number below is a measurement against this tree (2046 tracked files) with the pinned ruff
# 0.16.10, counted with `ruff check . --select <set> --output-format concise | grep -c` and checked
# against a rule known to be non-zero (I001 = 425), because `--statistics` prints nothing at all for
# a clean run and a clean run is what a broken counter looks like.
EPHE_RUFF_VERSION="0.16.10"
EPHE_MYPY_VERSION="1.19.1"

# EPHE_RUFF_BLOCKING is the set that gates a push. Membership requires proving the tree is already
# clean of the rule in the same commit that adds it; this set is 0 findings today. Four codes came
# out of the first draft for not existing in ruff at all -- F831, PIE700, PIE701, PIE702 are
# pyflakes and flake8-pie numbers ruff never implemented, and one unknown code makes `--select` exit
# 2 on the whole invocation, which reaches the report as a red leg with no finding inside it.
#   E9            syntax errors (category: the parse-failure family)
#   F821 F822 F823 undefined name, undefined __all__ export, undefined local
#   B006 RUF008    mutable default argument, mutable default in a dataclass: shared state
#   B012            jump statement in finally, which swallows what it jumps past
#   PLW1509         preexec_fn with arguments, a fork-safety footgun
#   PIE794 PIE800   duplicate class field, dict union shadowed by unpacking
EPHE_RUFF_BLOCKING="E9,F821,F822,F823,B006,B012,PLW1509,PIE794,PIE800,RUF008"

# EPHE_RUFF_ADVISORY prints a number in the log and never a red X: 1326 findings tree-wide on
# 2026-10-11, the bulk I001 (425), BLE001 (413), F401 (263), S110 (112), PLW1510 (65). A 1300-line
# cleanup in front of the owner before one product defect surfaced is a refusal, so it is reported.
EPHE_RUFF_ADVISORY="F,I001,BLE001,PLW1510,S110,B008,B015,B018,SIM201,SIM212,RUF006"

# PLW1514 (`open()` without an explicit encoding) is in neither set, and the reason is the line ruff
# itself prints for it: "Selection `PLW1514` has no effect because preview is not enabled." Left in
# the blocking set it would be a rule that cannot fire, which is the shape of coverage. Turned on
# with `--preview` it reports 15 findings here, all `Path(...).read_text`/`write_text` calls in
# tests/. The Windows-encoding row of docs/CI_EXPANSION_2026-10-10.md therefore stays open until the
# 15 are fixed or the owner accepts `--preview` for the leg.

# evals/repo_verify holds the held-out verification tasks: synthetic broken repositories whose whole
# purpose is to fail (`tasks/rv02-missing-import/fixture/notifier/send.py` imports nothing and is
# meant not to). That fixture is the only F821 finding in the tree, so the alternative to excluding
# it would be dropping undefined-name from the blocking set -- losing a real class to keep a fixture
# quiet. Neither leg reads it.
EPHE_LINT_EXCLUDE="evals/repo_verify"
