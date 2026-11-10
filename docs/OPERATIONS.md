# Operations — starting, stopping and owning the backend

The product makes one promise about this machine:

> **When nothing was started, nothing is reachable.** No listener on the product
> port, no orphan from an earlier run, and no second backend sharing the port
> quietly.

The port is `8765` by default (`--port` moves it). The promise is enforced by the
lifecycle in `core/backend_lifecycle.py`, the `ephe stop` / `ephe status`
commands, and the pidfile a running server writes about itself.

## Start

```sh
ephe start            # start the PWA backend (default 127.0.0.1:8765)
ephe start --open     # also open the browser
ephe start --takeover # replace an Ephe backend this installation did not start
```

Before anything is spawned, `ephe start` inspects the port:

| What the port answers | What `ephe start` does |
| --- | --- |
| nothing | starts and writes the pidfile |
| this installation's backend, same contract and version | reports it as already running; starts no second server |
| an Ephe backend from another checkout, another version, or without a matching pidfile | names pid, version and root, then exits 1 without spawning |
| the same, with `--takeover` | stops that backend (SIGTERM, then SIGKILL), verifies the port, then starts |
| a listener that is not Ephe | names the pid, exits 1, and does not kill it — not even with `--takeover` |
| a stale pidfile (pid gone) | removes the record and starts |

`ephe serve` (the OpenAI-compatible engine, default port `8766`) runs the same
inspection before it binds. It speaks no `/api/health`, so an occupied port is
reported as unidentified rather than reused.

## Stop

```sh
ephe stop             # stop the backend this installation started
ephe stop --json      # machine-readable result
ephe stop --timeout 2 # shorter SIGTERM grace before SIGKILL
```

`ephe stop` ends only the backend that the pidfile and the health answer both
name:

1. read `~/.ephe/run/backend-<port>.json`;
2. ask `GET /api/health` for `pid`, `owner`, `root`, `version`;
3. require the pidfile pid, owner, root and process start time to match the
   process the health answer describes (a recycled pid fails the start-time
   comparison);
4. `SIGTERM`, wait up to `--timeout` seconds, then `SIGKILL` if the process is
   still there;
5. verify that the port has no listener, then remove the pidfile.

Exit codes:

* `0` — stopped, or nothing was running (idempotent; a stale pidfile is cleaned).
* `1` — the port is held by a process this installation cannot prove it started.
  The process is named and left alive; `ephe stop` never kills a stranger.

An Ephe backend started before the pidfile existed, or from another checkout, is
therefore *named* rather than killed. Replace it deliberately with
`ephe start --takeover`, or stop it by its pid after checking `ephe status`.

## Status

```sh
ephe status
ephe status --json
```

`ephe status` exits `0` when an Ephe backend answers on the port, `1` when
nothing does or when the listener is not Ephe. It prints pid, version, root,
owner and whether the pidfile proves ownership.

## The pidfile

Path: `~/.ephe/run/backend-<port>.json` (the device folder follows
`EPHE_CONFIG_DIR` when set). Mode `0600`, written atomically by the server
before it starts serving.

```json
{
  "pid": 63104,
  "port": 8765,
  "owner": "18f4c0d2e1a3b4-63104",
  "root": "/Users/you/ephe",
  "version": "0.6.2",
  "api_contract": 1,
  "started_at": 1762793286.12,
  "start_time": "Mon Nov 10 18:28:06 2026"
}
```

* `pid` + `start_time` identify one process, not a recycled pid.
* `owner` is the token `/api/health` reports; the desktop shell passes its own
  token, a CLI start generates one.
* `root` and `version` make a record from another checkout or release visible.

A clean shutdown (SIGTERM, Ctrl+C) removes the file. A SIGKILL leaves it behind;
the next start reads it, recognises the orphan, and removes the record (and the
process, if it is still alive and provably this installation's leftover).

## Desktop app

The Tauri shell starts the backend recorded in `~/.ephe/desktop.json` and keeps
the child handle:

* on `RunEvent::Exit` (quit from the tray, the menu bar, or AppKit) it stops the
  child and removes that child's pidfile;
* on the next start, when the port is occupied, an Ephe backend is replaced
  only if it is this project's orphan — proven by a dead shell owner of the
  owner token, or by the pidfile's pid, start time and root. A backend owned by
  a live shell is left alone;
* with no listener, a pidfile from a dead pid is removed before the start.

## Finding leftovers by hand

```sh
lsof -nP -iTCP:8765 -sTCP:LISTEN      # who holds the port, if anyone
ps -p <pid> -o pid=,lstart=,command=  # pid, start time, command line
ephe status                           # is it an Ephe backend, and is it ours?
```

Kill a process only when `ephe status` (or the pidfile) shows it is this
installation's backend. A listener that does not answer `/api/health` is not
Ephe and is not the product's to end.

## Direct server starts

`python run_server.py --port 8765` still picks the next free port when 8765 is
taken, so a developer can run two checkouts side by side. That is a developer
path, not the product path: it never takes over, never kills, and the pidfile it
writes makes the process stoppable through `ephe stop`. `--reload` starts a
uvicorn reloader whose serving child has a different pid; `ephe stop` declines
such a backend rather than guessing. Stop a reload run with Ctrl+C.

## Tests that keep the promise

`tests/test_backend_lifecycle.py` covers:

* start → stop → `/api/health` unreachable, port has no listener, pidfile gone;
* `ephe stop` twice exits `0` both times;
* a backend that ignores SIGTERM is ended with SIGKILL, and the port is verified
  afterwards;
* a foreign listener on the port survives `ephe stop` and `--takeover`;
* an Ephe backend without our pidfile is named, not killed;
* a stale pidfile is recognised and removed;
* a backend from another installation is named with pid and version, replaced
  only with `--takeover`;
* `ephe start` refuses before spawning a second backend;
* the pidfile is owner-only and records the process start time.

All tests use an ephemeral port; `8765` is left to whatever the developer runs
by hand.
