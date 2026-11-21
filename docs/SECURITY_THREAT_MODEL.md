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
(`core/model_probe.py::mirror_api_key`) still resolves a key from the opencode configs so
a user can try an endpoint before configuring Ephe. It authenticates a metadata request and nothing
else — no chat turn, no tool call, no engine traffic ever reads that store. Owner decision 2026-10-18
kept it for that reason and added the condition: the source is named. `resolve_probe_key()` is the
single order the probe and the surface share (`given` → `own` → `foreign` → `none`), both discovery
routes return it as `key_source`, and a setup screen that answered with `foreign` says so — because
"your key worked" and "a key we found beside Ephe worked" are different answers, and only the second
one is a token the user must supply before their first message. The token itself goes to the endpoint
it was read for and to no other sink: not a response body, not a log line, not a file under the
config root. `tests/test_r71_environment_mirror.py::TestProbeKeySource` pins the order, both route
answers, the absence of the token from every sink, and that exactly one production call site reads
that store at all.

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
> **Note (as of 2026-11-16):** the channel runtime ships again and is opt-in per
> user. `server/routes/channels.py` mounts `/api/channels`; the poller from
> `core/channels/` starts only on `POST /api/channels/telegram/start` or
> `POST /api/channels/discord/start`, and both refuse without a bot token the user
> stored (`409` with the Settings path to it). Each start writes an audit event.
> Both transports are outbound httpx REST — `HttpxTelegramTransport`,
> `HttpxDiscordTransport` — so the C4 boundary above still holds: no inbound port,
> no webhook listener, no relay process. `core/channels/` remains the security
> layer those routes drive (pairing allowlist, injection guard, approval policy +
> regression tests). `docs/FEATURE_STATUS.md` and `docs/TELEGRAM.md` carry the
> feature-facing wording.

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

## Wave 2 (B3) — per-category approval overrides, review delta

The wave asked for per-category overrides and gated them on a review before any code.
This is the delta; it covers **one direction only**: a category can be made to *ask
more often*, never to run without asking when it asks today.

| Bound the wave requires | What the override does | Evidence |
|---|---|---|
| Defaults unchanged | The stored list is empty by default; `chat_tool_requires_confirm` returns exactly the value it returned before for every tool while the list is empty | `tests/test_wave2_approval_overrides.py::test_defaults_are_unchanged_for_every_category` |
| Workspace boundary for writes | Untouched: write confinement lives in the file tools (`workspace_dir`) and the deny-root backstop in `core/tools/registry.py`, neither reads this setting | matrix below; `tests/test_path_guard.py` unchanged |
| Shell restrictions | Untouched: `run_shell` never enters the chat auto-run set, is never in `ASKABLE_CATEGORIES`, and its command whitelist, blocked patterns and per-command confirmation are not gated by this list | matrix below (`run_shell` asks in every profile and every override) |
| Denial semantics | Unchanged: a refused prompt still returns the existing `not_approved` denial; the override adds prompts, it does not add refusal reasons | `tests/test_wave2_approval_overrides.py::test_a_declined_forced_prompt_keeps_the_denial_code` |

Only `SAFE` and `NETWORK` are accepted, because they are the two classes that auto-run
on the chat path. `MUTATING` and `DANGEROUS` already prompt in every profile, so there
is nothing to raise, and `save_security_config` drops them from the list rather than
storing a value that would do nothing. `--yes` on the CLI does not override a forced
category, the same way the confidence floor does not.

What would unblock the other direction (a category running *without* its prompt): a
capability-scoped exception list (per tool, per workspace, with an expiry) and its own
review — a per-category switch is too coarse to bound what `DANGEROUS` covers.

## 8. Accepted scanner findings

A dismissal made in GitHub's interface is invisible to someone reading the tree, so every finding
this repository has accepted is answered here: what the analyser pointed at, and the fact in the
code that answers it. The numbers are the alert ids under
`github.com/bemlerlabs/ephe/security/code-scanning/<n>`; the Dependabot row names its package.

Counted on `main` on 2026-11-19: **0 open** code-scanning alerts, **0 open** Dependabot alerts,
**0 open** secret-scanning alerts, against 16 code-scanning dismissals and 1 Dependabot dismissal.
The count belongs to the day it was taken, so it is re-taken rather than trusted:

```bash
gh api "repos/bemlerlabs/ephe/code-scanning/alerts?state=open" --jq 'length'
gh api "repos/bemlerlabs/ephe/dependabot/alerts?state=open" --jq 'length'
gh api "repos/bemlerlabs/ephe/secret-scanning/alerts?state=open" --jq 'length'
```

| alerts | rule | where it pointed | what answers it |
|---|---|---|---|
| 174, 175, 176, 177 | `py/path-injection` | the four folder helpers of `core/marketplace_service.py` | Each path is `config_root()` or the state root joined with `os.path.basename(_safe_name(name))`, and `_safe_name` refuses anything outside `^[a-z0-9][a-z0-9-]*$`, an alphabet with no separator and no dot in it. The removal that deletes folders can therefore only delete one folder directly under a root this product made. The refusal is tested in `tests/test_marketplace_routes.py`. |
| 142 | `py/path-injection` | the descriptor walk in `server/plugin_surface.py` | The walk opens one segment at a time with `openat` against a directory fd, and a segment that is empty, `.`, `..` or carries a separator is refused before any descriptor is opened — no path string reaches a syscall. The hostile shapes stand in `tests/test_plugin_surface_walk_contract.py`. |
| 11, 13 | `py/path-injection` | the two `resolve()` calls in `core/path_guard.py` | The resolve *is* the check: the resolved text is compared against the deny roots and never opened, so the query's sink is the thing that proves the confinement. Both lines carry their suppression, and `tests/test_path_guard.py` holds the cases. |
| 4, 5, 110, 111 | `py/path-injection` | `Path(...).expanduser()` in `core/engine_config.py` | The value is the owner's own folder choice, posted by the person who owns the machine, and `validate_workspace_dir` / `validate_output_dir` refuse a relative path, so nothing is resolved inside a root it could leave. The two surviving sites carry the suppression and say so; the region the 2026-10-16 pair named has been rewritten since, and today's scan of the rule on `main` reports nothing. |
| 134 | `py/stack-trace-exposure` | the failed-tool answer in `server/routes/plugins.py` | A tool that raised answers with a refusal code, the plugin id and the request id. The exception is logged with its traceback in its own handler and never reaches the response, which is what the function's docstring names as CWE-209 and CWE-497. |
| 115, 15 | `py/clear-text-storage-sensitive-data` | the two append sinks in `core/audit_log.py` | The audit file is `chmod 0600`, and every text field passes the masker on write and again on read, so the file holds no credential in the clear. The suppression sits on the `open("a")` the analyser named. |
| 116 | `py/weak-sensitive-data-hashing` | the keyed fingerprint in `core/engine_config.py` | The digest is HMAC-SHA-256 over a fixed context string, which answers "is this the key already stored" and decides nothing on its own; the shape a password hash would need — an unsalted digest of a secret compared for admission — is not what this line builds. |
| 117 | `py/weak-sensitive-data-hashing` | the legacy fingerprint in `core/engine_config.py` | A plain SHA-256 of a key, kept only so a fingerprint written before the keyed form still matches: `hmac.compare_digest` reads it, and dropping the function would report an older `engine.key` as absent. Accepted rather than fixed; the file stores the digest, never the key. |
| Dependabot | `glib` 0.18.5, medium, no patched release | `app/src-tauri/Cargo.lock` | The advisory is an unsound `unsafe` implementation of `glib::VariantStrIter`, an API no code in this tree calls. The crate is not in the host graph at all — `cargo tree -i glib` prints nothing on macOS — it arrives through the Linux WebKitGTK stack of the desktop shell (`webkit2gtk-sys` in the same lock). Accepted for as long as that graph holds. |

A row that stops matching the code is worse than no row, so the rule for this table is that a
dismissal enters it with the fact that answers it, and a reader can find that fact in the named
file without opening GitHub.


## 9. The finding this tree closed by moving the work in process

The table above lists findings the code answers as it stands. This one is the other kind: a finding
whose answer was to delete the shape the analyser pointed at. It is written down because a critical
alert that disappears without a word is indistinguishable from one that was quietly dismissed.

**What it pointed at.** `core/voice_synth.py`, rule `py/command-line-injection`, reported on the
branch that added the second local voice rung: one alert, critical severity. The sentence a user
asked Ephe to speak travelled as an argument to the vendor CLI through `subprocess.run`, and the
taint from the request reached the argument list.

**What was tried before it was moved.** The command line was hardened the way a command line is
hardened: the sentence fenced behind `--` so the option parser cannot read it as a flag, a NUL byte
refused, the length bounded, and the two configurable names checked against a token alphabet at the
call. The alert stayed on the new head. The remaining readings — a local daemon holding the model, a
suppression, or loading the package in process — were put to the owner rather than resolved
unilaterally, and the answer was the third.

**What answers it now.** There is no command line. The synthesis package is imported and called the
way the STT side loads `faster-whisper`, and the sentence is a Python argument
(`write_supertonic_wav` in `core/voice_synth.py`). `tests/test_voice_supertonic.py` keeps it that way
with a case that patches `subprocess.run` to fail: the second rung starting a process is a test
failure. Nothing was dismissed in the interface and no suppression comment was added. This
repository's analyses run through the default setup, which ignores `# codeql[...]` comments, so a
comment in that file would have promised a suppression that never happens.

**Where the risk sits after the move.** Two places, both checked at the call rather than at the
settings screen, because `voice.json` is a file the owner edits by hand. The voice name becomes a
file name inside the asset folder, so it is refused unless it matches
`[A-Za-z0-9][A-Za-z0-9._-]{0,31}`. And a synthesis must never fetch its own 385 MB of weights as a
side effect of a chat turn, so the graphs load with `auto_download=False` and the install verb asks
before it downloads anything.

**What the move cost, measured.** On the reference machine on 2026-11-19, through the product path
with the real weights installed: 1,2 s for a sentence with the graphs loaded, 3,0 s for the first
sentence of a process, 39,8 s at the 3000-character bound, 65,5 s at 5000. The last pair is why the
bound is 3000. A pass in this process cannot be interrupted from outside, so the route holds a thread
and a wall clock around it (`SUPERTONIC_SYNTHESIS_SECONDS`) and answers a rung that overruns with a
refusal.

**How to check it without trusting this page.**

```bash
pytest tests/test_voice_supertonic.py -q
gh pr checks 364 --repo bemlerlabs/ephe --json name,state --jq '.[] | select(.name == "CodeQL")'
```

The first is the suite that holds the contract. The second is the analysis of the head that removed
the command line, read from the check run: a PR-scoped alert does not appear in the open-alerts query
whose numbers §8 counts, so the check run is where that answer lives.
