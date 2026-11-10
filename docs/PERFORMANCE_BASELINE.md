# Performance baseline — start-up and window memory

This page measures start-up cost and panel/window memory instead of asserting them. Every number names the command, the machine and the number of
repetitions; medians are over the runs named in each row. Nothing here was optimised: where a
cost is named, it is the cost as shipped at the commit below.

- **Machine:** Apple M4 (`Mac16,1`), macOS 26.6, arm64.
- **Runtime:** Python 3.13.18 (project venv), Node 22.23.4 where the frontend is involved.
- **Tree:** commit `888f1a3ce957`, 2026-11-09.
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
| **cold** — first-party `__pycache__` removed before each start | 45.8 ms | **1345.5 ms** | 1068.4–1685.0 ms | 5 |
| **warm** — bytecode caches present | 33.3 ms | **493.6 ms** | 482.2–514.3 ms | 5 |

Command (the `--warm-only` half is the second row; the first row is the default cold half):

```bash
.venv/bin/python scripts/bench_startup.py --runs 5
```

Reading:

- Cold start costs 852 ms more than warm. Most of that is first-party bytecode compilation: a
  cold `import server.main` (table 2) measured 806 ms median against 444 ms warm. The two rows are
  separate instruments and the gap between them is not a phase decomposition — the cold start
  also pays the first read of the sources from disk. On the first start after an install or a
  checkout that is what a person waits for; every later start is ~0.5 s.
- A warm start is 444 ms import (table 2) plus ~50 ms of uvicorn/bind/lifespan. The app's own
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
| local port 9, refused | 493.6 ms | 5 |
| blackholed endpoint | **3704.3 ms** | 3 |

```bash
.venv/bin/python scripts/bench_startup.py --runs 3 --warm-only \
  --env EPHE_MODEL_PROVIDER=openai_compatible \
  --env EPHE_OPENAI_COMPAT_BASE_URL=http://10.255.255.1:9 \
  --env EPHE_OPENAI_COMPAT_MODEL=bench
```

Measured: 3.2 s above the local baseline is more than the 2 s probe timeout, so the
probe is not the only added work on that path. The table keeps the observation and does not claim
a decomposition.

## 2. Python import of the app

`python -X importtime -c "import server.main"` — the same import uvicorn performs for
`run_server.py`. Five runs; the median run is quoted whole, and the module table ranks **self**
time (cumulative time already contains the children, so ranking by cumulative would put
`server.main` and its ancestors on every row).

| state | total (median) | min–max | runs |
|---|---|---|---|
| warm | **443.9 ms** | 414.8–526.7 ms | 5 |
| cold (caches removed before each run) | **805.9 ms** | 763.0–858.9 ms | 5 |

```bash
.venv/bin/python scripts/bench_startup.py --runs 5 --imports --imports-cold
```

Ten most expensive modules by self time, warm median run (ms):

| # | module | self ms |
|---|---|---|
| 1 | `fastapi.openapi.models` | 24.91 |
| 2 | `server.routes.health` | 21.25 |
| 3 | `ollama._types` | 13.26 |
| 4 | `server.routes.artifacts` | 9.60 |
| 5 | `ollama` | 7.82 |
| 6 | `fastapi.routing` | 7.66 |
| 7 | `server.routes.chat` | 5.54 |
| 8 | `pydantic_core.core_schema` | 4.93 |
| 9 | `server.routes.workspaces` | 4.91 |
| 10 | `server.routes.skills` | 4.89 |

The ten rows are 105 ms of the 444 ms. The rest is spread across the route modules FastAPI builds
models for; `server.routes.health` pays its own module body (including one `git rev-parse` for
`git_sha`), and `fastapi.openapi.models` is the schema layer every route imports.

## 3. `ephe doctor`

Whole-command wall clock, this machine's own `engine.json` and network (the run's checks include
the engine probe and the update check):

| command | median | min–max | runs | exit |
|---|---|---|---|---|
| `ephe doctor --json` | **7533 ms** | 6813–8218 ms | 5 | 0 |

```bash
.venv/bin/python scripts/bench_startup.py --runs 5 --doctor
```

Doctor prints no per-check timing, so this page does not split the 7.5 s into checks; that is the
open number of this baseline (see §6). An earlier quiet-machine run of the same command measured
6.6 s median, so the network-dependent part moves by ~1 s run to run.

## 4. Window memory

Two stores hold the window and panel state. Both are small; the measurement is here so that
"small" is a number.

### 4.1 Tauri window state (Rust)

`tauri-plugin-window-state` 2.5.0 persists each window's geometry to
`<app_config_dir>/.window-state.json`. On this machine that is
`~/Library/Application Support/com.ephe.ephe/.window-state.json`:

- **209 bytes**, one record (`main`), ten fields: `width`, `height`, `x`, `y`, `prev_x`, `prev_y`,
  `maximized`, `visible`, `decorated`, `fullscreen`.
- Read at setup: `serde_json::from_reader(BufReader<File>)` (`lib.rs:537-547`).
- Written on `RunEvent::Exit`: `serde_json::to_vec_pretty` + `std::fs::write` (`lib.rs:138-160`),
  no `fsync`.

Measured with `scripts/bench_window_state/` — same crates, same payload, 200 repetitions per run,
5 runs:

| operation | median | p95 | runs × reps |
|---|---|---|---|
| read + parse 209 B | **0.0184 ms** (18.4 µs) | 0.0380 ms | 5 × 200 |
| pretty-print + write | **0.0455 ms** (45.5 µs) | 0.1516 ms | 5 × 200 |

```bash
cd scripts/bench_window_state && cargo run --release --offline
```

The write number is the syscall the plugin makes; neither the plugin nor
this harness fsyncs.

### 4.2 Panel state (`ephe.panel.*`, WebKit localStorage)

Keys and payload sizes read from the installed app's WKWebView store (`tauri://localhost`,
`localstorage.sqlite3`, UTF-16LE), and replayed through the real code paths in
`usePanelGeometry.ts` and `useTabRegistry.ts`:

| key | holds | bytes in the installed store |
|---|---|---|
| `ephe.panel.dock` | dock side (`right`) | 10 (5 chars) |
| `ephe.panel.width` | last panel width in px | 24 (12 chars) |
| `ephe.panel.activeTab` | JSON string of the active tab | 18 (9 chars) |
| `ephe.panel.tabs` | JSON array of open tabs | 4 (`[]`) |
| `ephe.panel.recent` | JSON array of closed tabs (`{tab, closedAt}`) | 676 (8 entries) |

Boot reads five keys and parses three JSON values; a tab change writes three keys with three
`JSON.stringify` (tabs, active tab, recent). Measured in Playwright's WebKit 27.2 (same engine family as the app's WKWebView;
not the app process itself), 5 blocks × 100,000 calls:

| path | median | max block of the quoted run |
|---|---|---|
| boot read (5 `getItem` + 3 `JSON.parse`) | **0.00108 ms** (1.1 µs) | 0.00121 ms |
| tab write (3 `stringify` + 3 `setItem`) | **0.00069 ms** (0.7 µs) | 0.00070 ms |
| one `setItem` of the 369-byte recent list | 0.00009 ms | 0.00009 ms |
| one `getItem` of the same value | 0.00007 ms | 0.00008 ms |
| `JSON.parse` of the recent list | 0.00057 ms | 0.00059 ms |

```bash
.venv/bin/python scripts/bench_panel_state.py --json /tmp/panel.json
```

This is the JS-call cost on the renderer's main thread. WebKit commits localStorage to SQLite on
its own thread after `setItem` returns, so the disk commit is deliberately not in the number — the
app does not wait for it. Milliseconds: below 0.002 ms per boot read, below 0.001 ms per tab
change. (Five consecutive runs of the script moved these medians by less than 0.0002 ms.)

## 5. Corrupt state

| store | corrupt value | what happens | evidence |
|---|---|---|---|
| window-state file | invalid JSON / truncated file | `load_saved_window_states` fails, the plugin's `.setup` uses `unwrap_or_default()` → empty cache → defaults; the next Exit rewrites the file | `tauri-plugin-window-state-2.5.0/src/lib.rs:423,537-547` |
| window-state file | missing | same empty cache, no error shown | same |
| window-state file | valid JSON, unknown window label | record is loaded into the cache but no window matches it on restore; stays until the next save overwrites the map | plugin `restore_state`, `lib.rs:200` |
| `ephe.panel.tabs` / `.recent` | invalid JSON | `readJson` catches and returns the fallback (`['preview']` / `[]`); boot continues | `primitives.ts:74-81` |
| `ephe.panel.tabs` / `.recent` | **valid JSON of the wrong shape** (object, string, number) | `.map` / `.filter` on the parsed value throws `TypeError` inside the state initialiser; the panel fails to boot | measured in a scratch vitest run: `readJson(...).map is not a function` |
| `ephe.panel.activeTab` | invalid JSON | parse fails, the raw string is used, then filtered against the open tabs; an unknown value falls back to the first tab | `useTabRegistry.ts:40-48` |
| `ephe.panel.width` | non-numeric (`abc`) | `Number(...) || 420` → 420 px | `usePanelGeometry.ts:26-28` |
| `ephe.panel.width` | negative or huge | passes the read unchanged; CSS `min(<n>px, 95vw)` + `lg:max-w-[60vw]` bounds the drawn width, a negative value makes the declaration invalid and the pane falls back to content width | `panel.tsx:137-146` |
| `ephe.panel.dock` | anything but `right` / `left` | read as a `Dock` without validation; every value other than `right` renders the left branch, while `leftOffset` is only measured for the literal `left` → the pane can cover the sidebar | `usePanelGeometry.ts:18-20,33-52` |

The last two rows and the wrong-shape row are behaviour: they are the "broken state"
half of #39 and are recorded here as findings. No code was changed for them in this task.

## 6. What this baseline does not answer

- **Doctor's 7.5 s, split per check.** Doctor has no per-check timing. The engine probe and the
  update check are network-bound and visibly move the total (6.6 s vs 7.5 s on two runs of the
  same command), but no number attributes the seconds today. That is the open measurement.
- **Cold disk.** Dropping the OS file cache needs root on macOS; "cold" is cold bytecode.
- **Run-to-run noise.** Repeating a session on this machine moved the cold import median between
  701 and 806 ms and the warm start between 494 and 516 ms (±15 % and ±4 %). The tables quote one
  session's 5-run medians; a difference under ~100 ms between two sessions is not a finding, and
  the cold/warm split (852 ms) is large enough to survive it.
- **The app's own WebKit.** The panel numbers come from Playwright's WebKit; the Tauri process
  is unwatched here. The magnitudes (µs) are far below anything a UI decision would turn on, but the row is
  labelled so it is not read as the app's own process.
- **The `ephe start` wrapper and the desktop shell.** §1 times `run_server.py`, the process that
  binds and serves; `ephe start` adds engine resolution and the browser open, and the Tauri shell
  adds its own window creation. Neither wrapper is in the table (the shell's window-state I/O
  is, in §4.1). A person's click-to-chat path therefore costs more than §1 alone, and this page
  puts no number on the difference.
