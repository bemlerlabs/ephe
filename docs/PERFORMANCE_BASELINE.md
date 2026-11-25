# Performance baseline — start-up and window memory

This page measures start-up cost and panel/window memory instead of asserting them. Every number
names the command, the machine, the engine and the number of repetitions; medians are over the runs
named in each row. Nothing here was optimised: where a cost is named, it is the cost as shipped at
the commit below.

- **Machine:** Apple M4 (`Mac16,1`), macOS 26.6, arm64.
- **Runtime:** Python 3.13.18 (project venv), Node 22.23.5, Playwright's WebKit 26.5 (build 2336)
  where the panel store is involved.
- **Engine:** no model answers any start-up or panel number here. §1, §2 and the pinned row of §3
  run against `local_ollama` at a closed loopback port with an isolated config dir, so the health
  probe is refused and nothing is generated; the `--live` row of §3 runs against the engine this
  machine has chosen, a remote OpenAI-compatible endpoint on the owner's tailnet, named by class
  because a baseline page carries no hostname.
- **Tree:** commit `77532e569145`, 2026-11-25 — every row below was re-taken on this machine on
  that date, so a clone of this repository at that commit reproduces them with the commands printed
  under each table (§4.2's key sizes name their own source). The previous stamp, `888f1a3ce957` of
  2026-11-09, named a branch commit that never landed, which made the whole page re-takeable by no
  one ([`DEVELOPMENT.md`](DEVELOPMENT.md)); that is why this page was re-measured rather than
  annotated.
- **Repetitions:** 5 per row unless the row says otherwise. A median over 3–5 samples is a
  baseline, not a distribution: the min–max is printed beside it so a reader can see the spread.

The instruments are committed so anyone can re-take the numbers:

| instrument | measures |
|---|---|
| `scripts/bench_startup.py` | server start until `/api/health` 200, `import server.main`, `ephe doctor` |
| `scripts/bench_window_state/` | the Tauri window-state file read/write in Rust (`serde_json`, same crate as the plugin) |
| `scripts/bench_panel_state.py` | the `ephe.panel.*` localStorage reads/writes in WebKit |

## 1. Server start until the health route answers

`ready` is the first HTTP 200 from `GET /api/health`, timed from `Popen` in
`scripts/bench_startup.py`. The banner row is the moment the port is printed, i.e. before uvicorn
has imported the app. The measured start is **pinned** to a local engine
(`EPHE_MODEL_PROVIDER=local_ollama`, a closed loopback port for the probe) so the number does not
follow one machine's `engine.json`.

| state | banner (median) | ready: `/api/health` 200 (median) | min–max | runs |
|---|---|---|---|---|
| **cold** — first-party `__pycache__` removed before each start | 49.3 ms | **734.0 ms** | 704.9–957.3 ms | 5 |
| **warm** — bytecode caches present | 40.6 ms | **400.8 ms** | 392.8–413.7 ms | 5 |

Command (the `--warm-only` half is the second row; the first row is the default cold half):

```bash
.venv/bin/python scripts/bench_startup.py --runs 5
```

Reading:

- Cold start costs 333 ms more than warm. Most of that is first-party bytecode compilation: a
  cold `import server.main` (table 2) measured 609 ms median against 322 ms warm. The two rows are
  separate instruments and the gap between them is not a phase decomposition — the cold start
  also pays the first read of the sources from disk. On the first start after an install or a
  checkout that is what a person waits for; every later start is ~0.4 s.
- A warm start is 322 ms import (table 2) plus ~79 ms of uvicorn/bind/lifespan. The app's own
  import is the start-up.
- `cold` here means cold **bytecode**: macOS needs root to drop the file cache, so
  the number does not include a reboot.

### The engine probe is inside `ready`

`/api/health` probes the configured engine before it answers. With a dead loopback port the
connection is refused immediately and the row above holds. With an endpoint that accepts nothing
(blackholed `10.255.255.1:9`, `openai_compatible`, 2 s probe timeout in
`server/routes/health.py::_quick_engine_status`) readiness moves by more than the timeout:

| probe target | ready (median) | runs |
|---|---|---|
| local port 9, refused | 400.8 ms | 5 |
| blackholed endpoint | **2433.5 ms** | 3 |

```bash
.venv/bin/python scripts/bench_startup.py --runs 3 --warm-only \
  --env EPHE_MODEL_PROVIDER=openai_compatible \
  --env EPHE_OPENAI_COMPAT_BASE_URL=http://10.255.255.1:9 \
  --env EPHE_OPENAI_COMPAT_MODEL=bench
```

Measured: 2.03 s above the warm row of the same session — the excess lands on the 2 s probe timeout
rather than above it. The 2026-11-09 run measured 3.2 s above its own baseline and read that as
the probe not being the only added work on that path; that excess did not reproduce here. The table
keeps the observation and claims no decomposition either way.

## 2. Python import of the app

`python -X importtime -c "import server.main"` — the same import uvicorn performs for
`run_server.py`. Five runs; the median run is quoted whole, and the module table ranks **self**
time (cumulative time already contains the children, so ranking by cumulative would put
`server.main` and its ancestors on every row).

| state | total (median) | min–max | runs |
|---|---|---|---|
| warm | **322.2 ms** | 314.9–323.6 ms | 5 |
| cold (caches removed before each run) | **609.4 ms** | 594.7–617.4 ms | 5 |

```bash
.venv/bin/python scripts/bench_startup.py --runs 5 --imports --imports-cold
```

Ten most expensive modules by self time, warm median run (ms):

| # | module | self ms |
|---|---|---|
| 1 | `fastapi.openapi.models` | 25.66 |
| 2 | `server.routes.health` | 14.10 |
| 3 | `ollama._types` | 11.19 |
| 4 | `ollama` | 5.62 |
| 5 | `server.routes.artifacts` | 4.89 |
| 6 | `server.routes.memory` | 4.22 |
| 7 | `server.routes.skills` | 4.21 |
| 8 | `server.routes.settings` | 4.08 |
| 9 | `server.routes.plugins` | 4.08 |
| 10 | `server.routes.workspaces` | 4.04 |

The ten rows are 78 ms of the 322 ms. The rest is spread across the route modules FastAPI builds
models for; `server.routes.health` pays its own module body (including one `git rev-parse` for
`git_sha`), and `fastapi.openapi.models` is the schema layer every route imports. Seven of these ten
names are the same ones the 2026-11-09 run listed; `fastapi.routing`, `server.routes.chat` and
`pydantic_core.core_schema` left the top ten and `server.routes.memory`, `server.routes.settings`
and `server.routes.plugins` entered it. The ranking is one session's snapshot at 4–5 ms self time,
below the run-to-run movement in §6: it locates where the import cost sits.

## 3. `ephe doctor`

Whole-command wall clock. The instrument has two branches and they are not the same measurement,
so both are printed:

| branch | what it resolves | median | min–max | runs | exit |
|---|---|---|---|---|---|
| pinned (default) | an isolated config dir; `local_ollama` `bench:1b` at a closed loopback port | **1560 ms** | 1546–2409 ms | 5 | 0 |
| `--live` | the machine's own `engine.json` — a remote OpenAI-compatible endpoint on the owner's tailnet | **1575 ms** | 1546–2005 ms | 5 | 0 |

```bash
.venv/bin/python scripts/bench_startup.py --runs 5 --doctor           # pinned
.venv/bin/python scripts/bench_startup.py --runs 5 --doctor --live    # the machine's engine
```

The engine is named by class, not by host: a baseline page carries no endpoint (§
[`CONTEXT_CONTRACT.md`](CONTEXT_CONTRACT.md) and the no-hardcoded-hostname rule in
[`AGENTS.md`](AGENTS.md)).

Two defects were found while re-taking this section, and both are fixed rather than papered over.
The row that stood here — 7533 ms (6813–8218 ms, 5 runs) — came from a command block that named
`--doctor` and no `--live`, while its prose described the live branch: the row was not reproducible
from its own command. And `--live` did not do what its help text says: `_child_env` set
`EPHE_CONFIG_DIR` to a fresh temp directory in both branches, so even the live run resolved no
engine at all. Proved by the CLI itself — with the bench config dir the JSON carries no `Engine`
check, and with the config dir unset it carries `Engine openai_compatible … engine up, model served`
(10:22 +0100, rc=0). The live row above is the first doctor number this page prints that actually
probes a chosen engine.

What the two branches say today: choosing a remote engine moves the total by 15 ms, which is inside
the run-to-run spread, so the seconds the old row attributed to "the engine probe and the update
check" are not explained by the engine choice on this machine now. The old number is kept nowhere
except as the record of a superseded measurement.

Doctor prints no per-check timing, so this page does not split the 1.6 s into checks; that is still
the open number of this baseline (see §6).

## 4. Window memory

Two stores hold the window and panel state. Both are small; the measurement is here so that
"small" is a number.

### 4.1 Tauri window state (Rust)

`tauri-plugin-window-state` 2.5.0 persists each window's geometry to
`<app_config_dir>/.window-state.json`. On this machine that is
`~/Library/Application Support/com.ephe.ephe/.window-state.json`:

- **213 bytes**, one record (`main`), ten fields: `width`, `height`, `x`, `y`, `prev_x`, `prev_y`,
  `maximized`, `visible`, `decorated`, `fullscreen`.
- Read at setup: `serde_json::from_reader(BufReader<File>)` (`lib.rs:537-547`).
- Written on `RunEvent::Exit`: `serde_json::to_vec_pretty` + `std::fs::write` (`lib.rs:138-160`),
  no `fsync`.

Measured with `scripts/bench_window_state/` — same crates, the same ten fields, 200 repetitions per
run, 5 runs; the row is the median of the five run medians and the widest p95 among them:

| operation | median | p95 | runs × reps |
|---|---|---|---|
| read + parse 213 B | **0.0172 ms** (17.2 µs) | 0.0287 ms | 5 × 200 |
| pretty-print + write | **0.0386 ms** (38.6 µs) | 0.0936 ms | 5 × 200 |

```bash
cd scripts/bench_window_state && cargo run --release --offline -- \
  "$HOME/Library/Application Support/com.ephe.ephe/.window-state.json" 200
```

The store path is an argument, and the binary carries a default pointing at the same file; the run
above names it explicitly. The write number is the syscall the plugin makes; neither the plugin nor
this harness fsyncs.

### 4.2 Panel state (`ephe.panel.*`, WebKit localStorage)

Keys and payload sizes read from the installed app's WKWebView store (`tauri://localhost`,
`localstorage.sqlite3`, UTF-16LE), and replayed through the real code paths in
`usePanelGeometry.ts` and `useTabRegistry.ts` — both of which read and write through
`panelStorage.ts` today:

| key | holds | bytes in the installed store |
|---|---|---|
| `ephe.panel.dock` | dock side (`right`) | 10 (5 chars) |
| `ephe.panel.width` | last panel width in px | 24 (12 chars) |
| `ephe.panel.activeTab` | JSON string of the active tab | 18 (9 chars) |
| `ephe.panel.tabs` | JSON array of open tabs | 4 (`[]`) |
| `ephe.panel.recent` | JSON array of closed tabs (`{tab, closedAt}`) | 676 (8 entries) |

That table is the 2026-11-09 reading of an installed desktop app's store. This machine's
`~/Library/WebKit/com.ephe.ephe/…/localstorage.sqlite3` (12 288 bytes, last written 2026-10-25) now
holds two keys, neither of them `ephe.panel.*`, so the row cannot be re-taken without an installed
`.app` — it stays quoted with its date rather than refreshed from a source that is no longer there.
The timings below do not depend on it: the script seeds its own payload (dock 5, width 12, activeTab
9, tabs 32, recent 369 chars) and repeats operations on that.

Boot reads five keys and parses three JSON values; a tab change writes three keys with three
`JSON.stringify` (tabs, active tab, recent). Measured in Playwright's WebKit 26.5 (build 2336, same
engine family as the app's WKWebView; not the app process itself), 5 blocks × 100,000 calls:

| path | median | max block of the quoted run |
|---|---|---|
| boot read (5 `getItem` + 3 `JSON.parse`) | **0.00093 ms** (0.9 µs) | 0.00115 ms |
| tab write (3 `stringify` + 3 `setItem`) | **0.00059 ms** (0.6 µs) | 0.00060 ms |
| one `setItem` of the 369-byte recent list | 0.00008 ms | 0.00009 ms |
| one `getItem` of the same value | 0.00007 ms | 0.00007 ms |
| `JSON.parse` of the recent list | 0.00050 ms | 0.00051 ms |

```bash
.venv/bin/python scripts/bench_panel_state.py --json /tmp/panel.json
```

This is the JS-call cost on the renderer's main thread. WebKit commits localStorage to SQLite on
its own thread after `setItem` returns, so the disk commit is deliberately not in the number — the
app does not wait for it. Milliseconds: below 0.002 ms per boot read, below 0.001 ms per tab
change. (The five blocks of this run moved the boot-read median between 0.00091 and 0.00115 ms.)

## 5. Corrupt state

| store | corrupt value | what happens | evidence |
|---|---|---|---|
| window-state file | invalid JSON / truncated file | `load_saved_window_states` fails, the plugin's `.setup` uses `unwrap_or_default()` → empty cache → defaults; the next Exit rewrites the file | `tauri-plugin-window-state-2.5.0/src/lib.rs:423,537-547` |
| window-state file | missing | same empty cache, no error shown | same |
| window-state file | valid JSON, unknown window label | record is loaded into the cache but no window matches it on restore; stays until the next save overwrites the map | plugin `restore_state`, `lib.rs:200` |
| `ephe.panel.tabs` / `.recent` | invalid JSON | `readStored` catches the parse and delivers the default — `['preview']` (`DEFAULT_TABS`) / `[]`; boot continues | `app/src/components/dashboard/agent/panelStorage.ts:42-57,111-120`, ``app/src/components/dashboard/agent/AgentPanel.boot.shape.test.tsx`` |
| `ephe.panel.tabs` / `.recent` | **valid JSON of the wrong shape** (object, string, number) | the read shape-checks before returning — `isStringList` / `isRecentList` — and hands back the default, so nothing reaches `.map` / `.tab`; boot continues. The row used to record a thrown `TypeError` (`readJson(...).map is not a function`, a scratch vitest run); the guard moved to the read and the boot stopped being the place a stored value could crash | `app/src/components/dashboard/agent/panelStorage.ts:42-57,72-74,80-91`, ``app/src/components/dashboard/agent/AgentPanel.boot.shape.test.tsx`` |
| `ephe.panel.activeTab` | invalid JSON | a parse failure carries the legacy bare page name forward (`decodeLegacy`), the shape check still rejects objects, numbers and null, and an unknown name is filtered against the open tabs down to the first one | `app/src/components/dashboard/agent/panelStorage.ts:124-138`, `app/src/components/dashboard/agent/useTabRegistry.ts:44-48` |
| `ephe.panel.width` | non-numeric (`abc`) | `Number` yields `NaN`, `isWidth` rejects it on `Number.isFinite`, the read returns `FIT_WIDTH` = 420 px | `app/src/components/dashboard/agent/panelStorage.ts:97-104,146-147` |
| `ephe.panel.width` | negative or huge | `isWidth` bounds the stored value to `MIN_WIDTH`…`MAX_STORED_WIDTH` and a rejected one comes back as `FIT_WIDTH`; the drawn width is CSS-bounded a second time by `min(<n>px, 95vw)` + `lg:max-w-[60vw]` | `app/src/components/dashboard/agent/panelStorage.ts:97-104`, `app/src/components/dashboard/agent/panel.tsx:148,158` |
| `ephe.panel.dock` | anything but `right` / `left` | `isDock` rejects it and the read returns `DEFAULT_DOCK = 'right'`. A value that reached the render used to take the left branch while `leftOffset` was measured for the literal `left` only — that is how the pane covered the sidebar; the guard at the read closes the path and the Round-9 hotfix bounds the left dock | `app/src/components/dashboard/agent/panelStorage.ts:93-95,141-142`, `app/src/components/dashboard/agent/usePanelGeometry.ts:24-27` |

The last two rows and the wrong-shape row are behaviour the panel already has. #39 put every
`ephe.panel.*` key through one shape-checked read — `readStored` in
`app/src/components/dashboard/agent/panelStorage.ts`, which arrived whole in `2e095893`
(2026-11-10) — and `app/src/components/dashboard/agent/AgentPanel.boot.shape.test.tsx` holds it at
the pane: the corrupt values above go in, the pane comes up on the documented defaults (1 passed on
this commit). They were open findings when this section was written; the sentence that said so
outlived the fix.

## 6. What this baseline does not answer

- **Doctor's 1.6 s, split per check.** Doctor has no per-check timing. Its engine probe and its
  update check are network-bound, and the two branches of §3 differ by 15 ms while one of them
  probes a remote engine and the other a closed port — so whatever moves this number, it is not the
  engine choice on this machine. No measurement attributes the seconds yet. That is the open
  measurement.
- **Cold disk.** Dropping the OS file cache needs root on macOS; "cold" is cold bytecode.
- **Run-to-run noise.** Inside today's session the cold ready row spread 704.9–957.3 ms and the
  warm row 392.8–413.7 ms; the cold import spread 594.7–617.4 ms and the warm one 314.9–323.6 ms.
  The tables quote one session's 5-run medians. A difference under ~100 ms within a session is not a
  finding, and the cold/warm split (333 ms) survives it. Between this session and the 2026-11-09
  session the same rows moved further than that — warm ready 493.6 → 400.8 ms, cold import
  805.9 → 609.4 ms — and this page claims no cause for the gap: two sessions on one machine, nine
  dates apart, with a tree that moved in between is not a controlled comparison.
- **The app's own WebKit.** The panel numbers come from Playwright's WebKit; the Tauri process
  is unwatched here. The magnitudes (µs) are far below anything a UI decision would turn on, but the row is
  labelled so it is not read as the app's own process.
- **The `ephe start` wrapper and the desktop shell.** §1 times `run_server.py`, the process that
  binds and serves; `ephe start` adds engine resolution and the browser open, and the Tauri shell
  adds its own window creation. Neither wrapper is in the table (the shell's window-state I/O
  is, in §4.1). A person's click-to-chat path therefore costs more than §1 alone, and this page
  puts no number on the difference.
