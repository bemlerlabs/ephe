# Ephe — Security Threat Model (STRIDE)

> **As of:** 2026-08-19 (Sprint3-G2 channel delta §6) · 2026-10-10 (§1a engine token paths, measured on the installed desktop build) · 2026-10-11 (E2 web/MCP quarantine done — channel fence reused in the tool loop) · **Role:** AppSec (application security engineer) · **Scope:** CLI (`ephe_cli.py`) + engine (`core/`) + the `serve` API + the channel layer (`core/channels/`, Gateway-Alpha)
> **Principle:** server binding, CORS, mobile pairing and tool approval stay conservative. Offline-first default.

## 1. Trust boundary

```
User ── TTY ──▶ ephe_cli.py ── core/ (chat, model_router, tools) ──▶ Engine
                      │  ▲                        │
                      ▼  │                        ▼
              ~/.ephe/*.json          local (Ollama) / remote (ds4, OpenAI-compatible)
              session env (EPHE_*_KEY)    serve API (phase 3, localhost-only)
```

- **Persisted:** only the engine choice (`~/.ephe/engine.json`), never secrets.
- **Session env:** the API keys (`EPHE_OPENAI_COMPAT_API_KEY`) — for the process lifetime only.
- **Trust:** local = trustworthy; a remote engine + web/MCP content = untrusted (prompt injection).

### 1a. Where an engine access token comes from

Measured 2026-10-10 against the installed desktop build. Three surfaces, three lifetimes:

| Surface | How the token gets there | How long it lives |
|---|---|---|
| `ephe start`, `ephe desktop` from a terminal | `export EPHE_OPENAI_COMPAT_API_KEY=…` — `ephe_cli.py` copies the shell env into the backend it spawns | that shell session |
| Onboarding / settings engine form | `POST /api/settings` writes the typed value into the env of the **running server process** (`server/routes/settings.py`, the `provider.api_key` branch) | that process — a backend restart drops it, `engine.json` never holds it |
| The app opened from Finder or the Dock | `app/src-tauri/src/backend.rs` reads `~/.ephe/engine.key` and passes it to the backend as the same env variable | until the file is removed |

The third line exists because the first one cannot reach an icon-launched app: a `.app`
inherits no shell environment (measured: the backend on :8765 carried 36 environment
variables, none of them `EPHE_`). `~/.ephe/engine.key` is the declared equivalent of the
export — the user writes it, Ephe never creates or suggests it, and it is one line read by
the desktop spawn and, since the same date as its fallback removal, by the resolver below.
A file that is not owner-only (mode looser than `0600`), empty, holding
more than one line, or a symlink is refused rather than used, and an inherited variable
always wins over the file: nothing is overridden quietly. The token goes into the child's
environment and into no argv, log line, `engine.json` or `desktop.json` (a command line is
visible in `ps` to every user on the machine; a process environment is visible to its own
user only).

The resolver `core/engine_config.py::engine_api_key_for()` reads exactly the two sources above: the
env variable, and — when the env is empty — `~/.ephe/engine.key`. It is the same file the desktop
spawn reads, and it now works on every start rather than only the spawned one, because
`core/model_provider.py` had been sending users to that path in error text on surfaces that could not
see it. An inherited variable always wins over the file.

Until 2026-10-10 an empty env fell back instead to another tool's credential store
(`~/.local/share/opencode/auth.json`, matched by the models.dev API URL, read-only). That store was
never one of the declared sources, and on a machine with an opencode login it silently authenticated the endpoints
its catalog names — measured with `EPHE_OPENAI_COMPAT_API_KEY` unset, a 73-character token resolved
for `https://openrouter.ai/api/v1`. It survived only on the argument that removing it would break a
working engine, and that argument measured false: the issuer answered `401 {"message":"API key
expired."}` for the token it resolved, and the `http://` spelling of the same host resolved nothing,
so the "working engine" was one scheme wide and already dead. Owner decision 2026-10-10 removed it.
The positive and negative halves are both pinned in `tests/test_desktop_engine_key.py`,
and that test fails if the resolver gains a further source this
section does not name.

One foreign-store read remains, deliberately: the onboarding "test connection" probe
(`server/routes/model_provider.py::_mirror_api_key`) still resolves a key from the opencode configs so
a user can try an endpoint before configuring Ephe. It authenticates a metadata request and nothing
else — no chat turn, no tool call, no engine traffic ever reads that store.

## 2. STRIDE matrix

| # | Category | Threat | Affected | Mitigation | Status |
|---|---|---|---|---|---|
| S1 | Spoofing | a remote engine (ds4/OpenAI) poses as trustworthy | CLI→engine | the engine URL is chosen explicitly (onboarding), never silently remote | ✅ |
| S2 | Spoofing | an API key persisted in cleartext | `engine.json` | keys stay in the session env; `engine.json` never has secret fields (test) | ✅ |
| S2b | Spoofing | another local process reads a stored desktop token | `~/.ephe/engine.key` | written by the user only, mode verified at read (owner-only or refused), never in argv, log, `engine.json` or `desktop.json` | ✅ |
| S3 | Spoofing | serve reachable without auth | serve (P3) | auth token required for remote access; localhost bind is the default | 📌 P3 |
| T1 | Tampering | other local processes read or change the engine config | `~/.ephe` | dir 0700, file 0600 (least privilege) | ✅ |
| T2 | Tampering | a damaged config crashes the CLI | `engine.json` | atomic write (`tmp.replace`) | ✅ |
| I1 | Information Disclosure | error messages leak stack traces/secrets to the outside | CLI/serve | actionable errors: cause + fix, no raw stack trace; serve redacts | 📌 |
| I2 | Information Disclosure | a side channel reads the config | `~/.ephe` | 0700/0600 (T1) | ✅ |
| D1 | DoS | an unreachable remote engine blocks the CLI | CLI | timeout/retry/backoff, a clear offline error message (connectivity probe) | ✅ |
| D2 | DoS | serve overloaded by remote consumers | serve (P3) | request ID, idempotency, rate limit for remote access | 📌 P3 |
| E1 | Elevation | agentic tools (shell/browser/file) without approval | CLI/TUI (P2) | approval gates for destructive/network tools; `--dry-run` default | 📌 P2 |
| E2 | Elevation | prompt injection over MCP/web content steers the tools | CLI/TUI | injection policy: web/MCP content never as an instruction — the channel fence (C2) reused by the tool loop (`core/chat_tools.py::fence_tool_output`) on `web_search`/`fetch_url`/MCP output before it reaches the engine; tool approval conservative. Pinned by `tests/test_security_e2.py` + `tests/test_injection_loop.py` | ✅ |

## 3. Concrete mitigations (implemented)

1. **`~/.ephe` 0700, `engine.json` 0600** — `core/engine_config.py::save_engine_config` sets `chmod` after the atomic write (least privilege, T1/I2).
2. **No secret in the engine config** — `engine.json` holds provider, model, endpoint and the
   folder/parameter blocks, and the regression test proves it carries no key field (S2). A token
   reaches the engine through `EPHE_OPENAI_COMPAT_API_KEY` and through nothing else on the Ephe
   side: exported in a shell, typed into the onboarding/settings field, or read from
   `~/.ephe/engine.key` by the desktop spawn (§1a). The file is the user's own act; the app never
   writes it, and a mode that lets group or other read it is refused instead of used.
3. **Atomic config write** — `tmp.replace` prevents a half-written file (T2).
4. **Offline-first** — local Ollama auto-detect; remote only on an explicit choice; a connectivity probe with a clear error message (D1).

## 4. Open requirements (roadmap)

| Phase | Requirement |
|---|---|
| P0 ✅ | least-privilege config dir/file; no secret in the engine config (§1a names the one place a user may store a token) |
| P0 ✅ | rule on the opencode `auth.json` fallback: the documented rule named one key source, `engine_api_key_for()` read two (§1a) — owner decided 2026-10-10, the fallback is gone and both files name it |
| P2 📌 | approval gates for destructive/network tools; `--dry-run`; a status bar with a context meter |
| P3 📌 | `serve`: localhost bind by default, CORS off, auth token required for remote; request ID + idempotency; redacted errors |
| P4 📌 | structured logs (no secrets); stable error codes |

## 5. Regression gates (tests)

- `tests/test_engine_config.py::test_saved_engine_config_file_permissions_0600`
- `tests/test_engine_config.py::test_saved_engine_config_dir_permissions_0700`
- `tests/test_engine_config.py::test_saved_engine_config_never_persists_api_key`
- `tests/test_desktop_engine_key.py` (the spawn injects one declared variable, §1a names every source the resolver reads, the key-file rules are the same in Python and Rust, no key file is tracked)
- `tests/conftest.py::_hermetic_engine_key_file` (autouse: no test can resolve the developer's own stored token, which would authenticate a stub endpoint with a live secret)
- `app/src-tauri/src/backend.rs` unit tests (key file: owner-only mode enforced, inherited variable wins, `desktop.json` has no place for a token)
- `tests/test_security_offline_defaults.py` (the offline-first positioning)
- `tests/test_channel_injection_guard.py` (channel guard: pairing, injection, token, outbound-only)
- `tests/test_channel_injection_guard_live.py` (LIVE DoD: an injected channel message → no tool call, against the DGX harness Qwen)
- `tests/test_security_e2.py` (E2: `web_search`/`fetch_url`/MCP output quarantined by the tool-loop fence `core/chat_tools.fence_tool_output` before it reaches the engine)
- `tests/test_injection_loop.py` (E2 loop integration: the engine-facing tool message is a single untrusted-data block; a local result passes through untouched; the evidence summary never quotes external content)

## 6. Sprint 3 — channel threat model (Gateway-Alpha: the Telegram channel)

> **Delta reference:** the matrix extended by the new channel surface
> (the Telegram channel as an on-device gateway, no cloud relay). Sprint3-G2,
> implemented in `core/channels/` (pairing + token vault + injection guard).
> **Trust-boundary extension (C4):** the channel transport is
> **outbound-only** — the gateway opens NO inbound port (no
> webhook listener, no relay process, no second runtime). The only
> outbound = the channel transport itself (bot API polling, `getUpdates`).
>
> **Note (as of 2026-09):** the Telegram runtime was removed from `main`
> (fb8ddf7). `core/channels/` stays as a reusable
> security layer (pairing allowlist, injection guard,
> approval policy + regression tests) for future channels — currently
> wired to no running runtime.

### 6.1 New trust boundary (channel level)

```
Channel message (e.g. Telegram, untrusted) ── outbound-only transport ──▶ core/channels/pairing.py
                                                               │ pairing gate (allowlist, C1)
                                                               ▼
                                                  core/channels/injection_guard.py
                                                  (wrap + flagging, C2)
                                                               │ approval policy (C3, P0-1 gate)
                                                               ▼
                                                        engine/chat pipeline (as in the PWA)
```

- **Persisted:** `pairing.json` (user IDs only, 0600, C1/C3) and the bot token (keyring, fallback 0600 file, C3).
- **Session:** the bot token never in logs or a config commit; only in the keyring/0600 file.
- **Trust:** channel content = untrusted (prompt injection), analogously to web/MCP (E2).

### 6.2 STRIDE delta matrix (the channel surface)

| # | Category | Threat | Affected | Mitigation | Status |
|---|---|---|---|---|---|
| C1 | Spoofing (S3) | an unpaired Telegram user steers the gateway | the channel entrance | pairing = a static allowlist of Telegram user IDs, **default-empty** (it answers nobody); fail-closed on a missing or corrupt config | ✅ |
| C2 | Elevation (E2) | prompt injection over the channel text steers the tools | channel→engine | injection guard: (1) quarantine wrap (untrusted-data block) + a guard system prompt, (2) heuristic flagging (observability), (3) **the approval policy as a safety net** (reusing the P0-1 gate, non-interactive, conservative) | ✅ |
| C3 | Information Disclosure (I2) + Tampering (T1) | the bot token persisted/leaked in cleartext | the token vault | keyring first, fallback a 0600 file; never in a log or config commit; `mask_token` for all outputs | ✅ |
| C4 | Tampering (T1) / Spoofing (S3) | an inbound port/webhook relay opens new attack surface | the channel transport | **outbound-only transport**: no inbound port, no webhook, no relay process, no second runtime (test `test_channel_layer_opens_no_inbound_port`) | ✅ |

### 6.3 DoD verification (Sprint3-G2)

- **Offline (deterministic):** `tests/test_channel_injection_guard.py` —
  the pairing allowlist (default-empty), the injection guard (wrap + flagging +
  free of false positives), the token vault (0600/keyring, no cleartext),
  the outbound-only gate. E2E scenario: an injected instruction → a MUTATING
  tool call → the approval gate **DENIES** (no side effects).
- **LIVE (DGX harness Qwen):** `tests/test_channel_injection_guard_live.py` —
  an injected channel message (guard-wrapped) triggers **no**
  tool call on the Qwen engine; the answer is a refusal.
  The endpoint comes from the env (`EPHE_DGX_BASE`; no hostname in the repo),
  model `qwen38-27b-unsloth-nvfp4`, `enable_thinking=false`.

### 6.4 QR deep-link pairing (R24) — STRIDE delta

Pairing is no longer only manual allowlist maintenance: the desktop generates
a QR carrying `https://t.me/<bot>?start=<token>` (a device-coupling principle like the leading AI clients).
New surface + mitigations:

| # | Category | Threat | Mitigation | Status |
|---|---|---|---|---|
| C5 | Spoofing (S3) / QR phishing | an adversary talks the victim into scanning a stranger's QR code (pairing an attacker's account) | **two-sided confirmation:** the confirmation message in the bot chat shows the coupled account (name + user ID) — the victim sees the foreign account immediately; revoke withdraws it at once (devices UI, one click). Additionally: the QR is generated ONLY on request in the desktop (no poster/static QR) | ✅ |
| C6 | Replay / Tampering (T1) | an intercepted or re-scanned token is replayed later | the token is **single-use** (idempotent: a re-delivery → a `used` answer, no new pairing) + **TTL 10 min** + offset persistence; persisted only as a SHA-256 hash | ✅ |
| C7 | Information Disclosure (I1/I2) | the pairing token leaked in cleartext (log/screenshot of old QRs) | the cleartext exists exactly once: in the desktop user's QR; the audit log + the HTTP response of the token endpoint never contain the bot token; the pairing token only in the `deep_link` field of the desktop response | ✅ |
| C8 | DoS (flood) | flooding the token endpoint exhausts memory/Telegram | `MAX_OPEN_TOKENS = 6` (rate limit → HTTP 429) + brute-force lockout (`MAX_FAILED_CONSUMES = 10` per 5-minute window, fail-closed even for the correct token) | ✅ |

Regression gates: `tests/test_r24_pairing_tokens.py` (C6/C7/C8),
`tests/test_r24_channel_runner.py` (C5 two-sidedness, the immediate effect of revoke),
`tests/test_r24_channels_routes.py` (C7: the token never leaves the server).

## 7. Execution Boundary (Ephemora Cell, opt-in)

> **Three security layers:** the injection guard (§6/C2) protects the **content**,
> the approval gate (§3/P0-1) the **intention**, Ephemora Cell bounds the
> **execution**. None of them replaces another. The gate and the cell are not two
> switches but one decision: the gate treats model code as auto-run **only while
> the cell carries it** — where no cell can (no guest, or `EPHE_CODE_EXEC=kernel`)
> the code runs on the host and passes the gate (§7/X1, W3-15).

**Context:** `run_shell` checks the whitelist + blocked patterns, but then runs
`subprocess.run(shell=True)` with the user's rights — a circumvented pattern
or a manipulated command has full access to the user's filesystem.
Competing harnesses enforce the execution boundary with an OS sandbox
(macOS Seatbelt / Linux Landlock/bwrap — e.g. external agent harnesses,
`packages/sandbox/sandbox-local`). Ephe adds to that **opt-in** a
WASI sandbox (Ephemora Cell, Apache-2.0):

| # | Category | Threat | Affected | Mitigation | Status |
|---|---|---|---|---|---|
| X1 | Elevation (E2) | LLM-generated code exfiltrates/destroys host data | code execution | model Python (`execute_code`) runs in the pinned CPython guest by default (WASI: no host files/network, fuel/memory/file caps, no fork); auto-run **only while the cell carries the run** — without a guest it executes on the host and needs the approval gate (W3-15). Prebuilt `.wasm` via `run_sandboxed_code` (10-KB output cap), executed through `run_isolated()` (OS walls + hard kill) | ✅ (opt-in) |
| X2 | Tampering (T1) | the sandbox as a false sense of security (the in-process default) | Ephemora API usage | deliberately `run_isolated()` is never the in-process default; no `allow_dirs` parameter (the preopen deny is untouchable) | ✅ |
| X3 | Denial of Service (T-DoS) | an infinite loop/RAM eater from generated code | the execution runtime | fuel metering + memory cap + epoch timeout + I/O budgets; the status `FUEL_EXHAUSTED`/`MEMORY_EXCEEDED` is visible in the report | ✅ (opt-in) |
| X4 | Supply Chain | the opt-in package as an attack vector | `ephe[sandbox]` | lazy import + fail-closed without the package (the runtime without the sandbox is identical); the schema only when the environment is installed; a Git URL pin, a tag pin from the first Ephemora release | ✅ |

**Limits (honestly):** `run_shell` stays outside the WASI sandbox
(native binaries are not WASM modules) — a Seatbelt/Landlock wrapper is
planned as the next step. Ephemora does not guarantee that code is
*correct*, only isolation + resource limits (the upstream's SECURITY.md).

**Regression:** `tests/test_sandboxed_code_tool.py` (fail-closed without the
package, mutating classification → approval gate, hello=SUCCESS,
exploit=BLOCKED, fuel exhaustion, observability fields).
