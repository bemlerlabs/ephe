# One authority for the workspace root

Status: accepted, implemented (working tree on e65be13b; no commit by ticket #153). The
location is the owner's decision; the single-authority shape is the security review's
recommendation.

| Field | Value |
|---|---|
| Date | 2026-11-09 |
| Ticket | #153 |
| Scope of this change | this record, the workspace authority, its resolver delegation and the guard tests |
| Decides | where an unconfigured install puts the user's workspace |
| Changes with the fix | `core/engine_config.py` (`get_workspace_dir`, `neutral_workspace_dir`, legacy migration), `core/workspace_rules.py` (`resolve_workspace_dir`), `tests/test_workspace_authority.py`, the flipped pin `tests/test_path_authority_pin.py`, `tests/test_run_shell_executes.py`, `tests/test_r59_workspace_state.py`, the `HOME` pins in the chat-turn modules the gate selects (`tests/test_tool_approval_gate.py`, `tests/test_performance_fast_paths.py`, `tests/test_ephe_cli_run.py`), this record |

## Context

Two code paths answer "where are this user's files", and the answers disagree:

| Question | Answer before the fix | Where |
|---|---|---|
| May any tool read under `~/.ephe`? | no, at every approval level | `core/path_guard.py:30` (`DENY_ROOTS`), refused in `core/tools/registry.py:976` |
| Where does an unconfigured install put the workspace? | `~/.ephe/workspace`, created on demand | `core/engine_config.get_workspace_dir` |

The fallback has a real job: a server started from a source checkout must not expose that
checkout as the user's project folder, so `get_workspace_dir()` leaves the cwd and creates a
neutral directory. It created that directory inside the one root the product refuses.

The chain, end to end:

1. no `EPHE_WORKSPACE`, no `engine.json` workspace, cwd inside the checkout →
   `get_workspace_dir()` returns `config_root()/workspace`.
2. `core/tools/base.py:249` appends that folder to the allowed roots;
   `core/tools/base.py:279` refuses it again, because `path_guard.denied()` resolves it
   under a deny root.
3. `core/tools/registry.py:976` refuses before a human can be asked:
   `[Tool 'read_file' refused: … is inside a protected root …; no approval can open it.]`
4. `core/workspace_rules.py:160` reports the same files as `denied / protected-root`, so the
   prompt layer receives no project rules either.

On a machine nobody configured, every file and shell tool points at a folder the same
product refuses. `read_file` failed in the pilot this way.

Note that `denied()` also appends a *configured* `EPHE_CONFIG_DIR` to the deny roots when the
process is not under pytest (`core/path_guard.py:173`). The conflict therefore follows the
config root wherever it is pointed, so the defect is structural.

## Pinned state

`tests/test_workspace_authority.py` states the contract first: the folder
`get_workspace_dir()` returns lies outside every `DENY_ROOTS` entry, `denied()` answers
`False`, `_is_path_allowed()` answers `True` and `deny_paths()` answers `[]`; a configured
workspace still wins and is never migrated; a legacy neutral folder reaches the new default
without overwriting a file the user already has there. Written before the product change,
five of the seven tests then in the file failed on this tree:

```
>       assert handed_out == unconfigured_install.home / "Ephe"
E       AssertionError: assert PosixPath('<config root>/workspace') == PosixPath('<home>/Ephe')
```

`tests/test_path_authority_pin.py` now holds the settled state, asking the real functions:
`get_workspace_dir()` for the folder, then `denied()`, `_is_path_allowed()` and
`deny_paths()` on that folder and on a file below it. It also asserts that
`<config root>/workspace` is still `denied()`, so the change carved no exception. The suite
pins `EPHE_CONFIG_DIR` to a scratch folder, and `denied()` adds a configured root to the deny
list only outside pytest (`core/path_guard.py:173`), so the test drops `PYTEST_CURRENT_TEST`
inside the test body, after fixture setup, to run the shipped rule while keeping the write in
`tmp_path`. `HOME` is pinned as well, so the neutral folder is created under `tmp_path` and
never in the developer's home. The contradiction this record was written against stays in
the pin's module docstring.

## Options

Effort counts the product change behind each option, measured from the common part (one
constant, the pin flip, the guard tests) and the extra work the row adds.

| Option | Why it fits | Effort | Cost | Migration | Rollback |
|---|---|---|---|---|---|
| `~/Ephe` | One obvious folder in the home directory; no privacy prompt; `$HOME` is already an allowed root (`core/tools/base.py:226`), so nothing widens; the code already names `~/ephe` as the example workspace (`core/tools/base.py:242`), which is the same folder on a case-insensitive filesystem | about two hours | On a case-insensitive volume where `~/ephe` already exists (the example workspace, possibly a source checkout), `~/Ephe` is that same inode: no folder is created and the reused folder is not neutral. On a case-sensitive volume, and for a user without that folder, a new folder directly under the home folder appears the first time an unconfigured install resolves a workspace; some users do not want that | Rename `<config root>/workspace` into the default when it is free; otherwise copy the entries the default does not hold and leave the old folder in place | Revert the constant; the migrated files stay at `~/Ephe`, so set `EPHE_WORKSPACE=~/Ephe` or move the folder back once |
| `~/Documents/Ephe` | Visible in the file manager sidebar and in every backup and cloud-sync default, so the user finds their files | about half a day | A TCC prompt on first read: `NSDocumentsFolderUsageDescription` is declared already (see `docs/TCC.md`), and the grant binds to the code requirement, so an ad-hoc-signed build asks again after each rebuild; a refused prompt leaves the workspace unreachable, which is this ticket again | As above, plus a first-run grant step and a support answer for the denied-prompt case | Same constant revert, plus the now-unused grant |
| Another neutral place, e.g. the platform application-data directory (`~/Library/Application Support/Ephe/workspace`) | Never prompts and never litters the home directory; the platform convention for per-app data | about three hours | Invisible to the user, so a workspace they are meant to read and edit looks like a hidden cache; needs a per-platform path helper, because the location differs on Linux (`XDG_DATA_HOME`) and Windows (`LOCALAPPDATA`) | Move the old neutral directory once, as above | Same constant revert; the moved copy is the rollback |

Rejected: carve `<config root>/workspace` out of `DENY_ROOTS`. The state directory holds the
engine key, the session store and the audit log beside that folder, and a path-shaped
exception is what a symlink climbs through; the refusal is also the answer the security tab
and the model-facing refusal text quote verbatim.

## Recommendation

One authority: `core/engine_config.get_workspace_dir()` decides the location, and
`core/workspace_rules.resolve_workspace_dir()` is a pure delegation to it. Before the fix
that resolver read `EPHE_WORKSPACE` a second time and fell back to `os.getcwd()`
(`core/workspace_rules.py:83`), so the prompt layer and the tools could answer differently.
The implementation is one `return get_workspace_dir()`, and the rules reader keeps using it.

The guard keeps no exception, and the resolver's default must satisfy it. The fix therefore
carries one product-level assertion: the resolved workspace is not `denied()`. The pin is
exactly that assertion, so a future fallback cannot land in a refused root without failing a
test.

For the location itself: `~/Ephe`, for the absence of a privacy prompt, one predictable
folder, and the already-allowed home root. `~/Documents/Ephe` is the better answer only if
the owner values sidebar visibility above the TCC grant and the support load that comes with
a rebuild-sensitive prompt.

## Migration

A configured `engine.json` workspace or `EPHE_WORKSPACE` wins and never moves. Only the
neutral folder is migrated, and only when it holds files
(`core/engine_config._migrate_legacy_workspace`):

1. resolve the old neutral directory (`config_root()/workspace`) and the new default;
2. when the default is free, rename the old folder into it, one atomic step on the same
   volume;
3. when a rename cannot happen (another volume, or the default already exists), copy every
   entry whose name the default does not hold; an existing file is the user's current copy and
   is skipped, and the old folder is left in place;
4. never delete user files, and never move sessions, artifacts or the engine key, which stay
   under the config root by design.

Risks of this migration:

- After a rename the old path is gone, so reverting the constant alone points an old build at
  an empty `~/.ephe/workspace`; the recovery is `EPHE_WORKSPACE=~/Ephe` (see Rollback).
- The migration runs on the first neutral resolution. A same-volume rename touches the old
  folder once; a cross-volume copy leaves it in place and re-checks it on later resolutions,
  where every entry that already exists is skipped and no file is rewritten.
- On a case-insensitive volume where `~/ephe` already exists, `~/Ephe` is that folder, so
  the default workspace can be a folder that was not neutral; on the development machine it
  is the source checkout. The migration refuses to write into the checkout the process runs
  from and leaves the legacy folder in place. `EPHE_WORKSPACE` names a different folder for
  anyone who wants one.
- When the home folder is read-only, `get_workspace_dir()` answers `$HOME` itself, an allowed
  root, instead of failing; the workspace is then the whole home folder until the user picks
  one.

## Rollback

Revert the constant. The pin fails on the reverted tree, so the revert is visible. A fresh
profile leaves an empty `~/Ephe` folder the user can delete. An upgraded profile has its
files at `~/Ephe`, so the reverted build needs `EPHE_WORKSPACE=~/Ephe` or one move of the
folder back to `~/.ephe/workspace`; after a cross-volume copy the old folder is still there
and the reverted build reads it again.

## Verification

`tests/test_workspace_authority.py` was written first and failed on this tree; it is green
after the change. The pin, `tests/test_workspace*.py` and the `-k "path or workspace"`
selection of `tests/` are green. The two tests outside the new file that pinned the old
default (`tests/test_run_shell_executes.py`, `tests/test_r59_workspace_state.py`) assert the
new one and pin `HOME`, so the neutral folder is created in `tmp_path`. The chat-turn modules
the gate selects pin `HOME` too: an unconfigured install resolves the neutral `~/Ephe`, and a
turn records its episode under the workspace, so without the pin those tests would write into
the developer's home. A suite-wide `HOME` pin is a follow-up; the sandbox tests in particular
need a target outside the temporary-directory allowance, which a pinned home cannot be. Ruff's
blocking set (`scripts/lint_policy.sh`) runs over the changed files, and the prose ratchet is
unchanged.

## Not in this change

`DENY_ROOTS`, the model-facing refusal text and the refusal order stay as they are; the
guard keeps no exception for any workspace path. Moving the location again is a new owner
decision, and the pin plus this record carry the current one.

A suite-wide `HOME` pin is a follow-up. The chat-turn modules in this ticket's gate pin
`HOME` locally (`tests/test_tool_approval_gate.py`,
`tests/test_performance_fast_paths.py`, `tests/test_ephe_cli_run.py`), and a full `-k`
run leaves `~/Ephe` untouched. A broader pin needs the tests that read this machine's
device folder (`tests/test_memory_embed_onnx.py`, `tests/test_port_squatter_guard.py`,
`tests/test_docker_binding.py`, `tests/test_dynamic_runner.py`) to opt back into the real
home; until then a chat-turn test outside that set can record an episode under `~/Ephe`.
