# CLI inventory — 2026-10-25 (S20)

Scope: every subcommand `ephe --help` lists at this commit, its machine-readable
surface, the exit codes the handlers return, and the non-interactive seams a
script depends on. Everything below comes from a command run in a throwaway
`EPHE_CONFIG_DIR` or from the line named in the `evidence` column.

## Command table

| command | machine-readable | exit codes | evidence / note |
|---|---|---|---|
| `start` | no | 0/1/2 | long-running server; JSON would be a stream, not a document |
| `web` | no | 0/1/2 | alias of `start` |
| `desktop` | no | 0/1/2 | build + install to `/Applications`; build output on stdout |
| `sky` | no | 0/1/2 | ephemeris text table (`ephe_cli.py:1153`) |
| `amber` | no | 0/1/2 | writes the monthly crystal (`ephe_cli.py:1162`) |
| `bench` | no | 0/1/2 | gate/measurement per plugin (`ephe_cli.py:1183`) |
| `doctor` | `--json` | 0/1 | health report; `--fix` repairs (`ephe_cli.py:639`) |
| `code` | `--json` | 0/1/2 | agent loop in the workspace (`ephe_cli.py:259`) |
| `run` | `--json` | 0/1/2 | streaming agent run, resumable (`ephe_cli.py:340`) |
| `goal` | `--json` | 0/1/2 | goal loop with a check command (`ephe_cli.py:465`) |
| `voice` | no | 0/1/2 | `list` is the scriptable half and has no JSON (gap, see below) |
| `update` | `--json` (S20) | 0/1 | one document on stdout; children on stderr |
| `configure` | no | 0/1/2 | interactive by design; `--force` re-selects |
| `tui` | no | 0/1/2 | Textual UI; not a machine surface |
| `completion` | no | 0 | prints a completion script |
| `session` | `--json` | 0/1/2 | `new` takes `--title`, never a positional |
| `serve` | no | 0/1/2 | OpenAI-compatible server; JSON would be SSE |
| `memory-mcp` | no | 0/1/2 | JSON-RPC on stdio; the protocol is the surface |
| `tool` | `--json` | 0/1/2 | `--dry-run`/`--yes`/`--no` gates (`ephe_cli.py:1543`) |
| `plugin` | `list --json` (S20) | 0/1/2 | enable/disable/install print prose |
| `import` | no | 0/1/2 | one-shot migration (`ephe_cli.py:1513`) |
| `agents` | `--json` | 0/1/2 | live workspaces (`ephe_cli.py:1678`) |
| `changes` | `--json` | 0/1/2 | change sets, newest first |
| `show` | `--json` | 0/1/2 | one change set's diff |
| `review` | `--json` | 0/1/2 | reviewer verdict |
| `publish` | `--json` | 0/1/2 | one approved change set to a branch |
| `reap` | `--json` | 0/1/2 | removes workspaces whose owner is gone |
| `prune` | `--json` | 0/1/2 | dry run unless `--apply` |

Observed exit codes (`EPHE_CONFIG_DIR` in a temp dir):
`--version` 0 · unknown command 2 · `session new` without a title 2 ·
`tool __no_such_tool__` 1 · `completion bash` 0 · `session list` 0.
The contract is `0` success, `1` runtime/repair error, `2` usage error
(`docs/CLI.md` §Exit codes); argparse usage failures also exit 2.

## Non-interactive behaviour

- `ephe doctor --json`, `ephe tool --json` and the change-set verbs work with
  no TTY. `ephe configure` requires one; headless setups use the engine env.
- `ephe update --json` used to print its result document before doing the work
  and let `git pull`/`install.sh` write to the same stdout, so a consumer read
  two documents. Both are fixed: children now land on stderr.
- `ephe session list` on an empty store printed a hint the parser rejects
  (`ephe session new <title>`; the flag is `--title`). Fixed, and a test parses
  the printed hint and runs it.

## TUI focus entry points

The Textual UI sets focus in `ui/composer.py:257` (chat input),
`ui/session_switcher.py:84` (session filter), `ui/overlays.py:54` (overlay
filter) and `ui/widgets.py:741`. Focus behaviour is covered by
`tests/test_tui_viewport.py` and `tests/test_steering.py`; this inventory did
not add a new focus test.

## The three improvements landed

1. `ephe update --json` — one JSON document, real `exit_code`, children's prose
   on stderr. Before: early `{"ok": true, "message": "update gestartet"}` plus
   child stdout on the same stream (`ephe_cli.py:1228` at the base commit).
2. `ephe plugin list --json` — `{"plugins": [{name, enabled, version}]}`.
   Before: table only, no machine-readable listing.
3. `ephe session new` hint — the printed way out now names `--title 'My
   project'`, the form the parser accepts. Before: a positional that exits 2.

Each change has a test in `tests/test_s20_cli.py`; all four tests fail on the
base commit and pass with the change.

## Remaining gaps (not changed here)

- `ephe voice list` has no `--json`; a script that needs the installed voices
  must parse the table.
- `ephe import` reports no machine-readable result.
- `ephe start`, `ephe desktop`, `ephe serve` and `ephe memory-mcp` are
  long-running or protocol surfaces; JSON mode does not apply to them.
