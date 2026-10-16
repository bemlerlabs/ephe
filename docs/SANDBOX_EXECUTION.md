# Sandbox Execution (Opt-in) — Ephemora Cell in Ephe

The third security layer, alongside the injection guard (content) and the approval gate (intent): the
**execution** of LLM-generated / untrusted code runs isolated inside a WASI sandbox. Threat model:
`SECURITY_THREAT_MODEL.md` §7.

## Activation

```bash
pip install 'ephe[sandbox]'                 # pulls ephemora-cell (PyPI; ≤1.0.4.3 Apache-2.0)
python3 build_cpython_guest.py      # builds the pinned CPython guest into ~/./.ephe/cells
```

Without that install the runtime stays identical: `run_sandboxed_code` answers fail-closed with an
install hint, and the tool schema never appears at all (lazy import, no hard dependency). `execute_code`
without a guest runs in the kernel — and says so in every result (see E1 below).

## `run_sandboxed_code`

`core/tools/sandbox_tools.py` runs a `.wasm` module through Ephemora Cell's `run_isolated()` (OS walls:
rlimits, I/O watchdog, hard kill — never the in-process default). Vendor defaults: 128 MB memory,
1 M fuel, 30 s timeout, preopen-deny (no file access), output cap 10 KB.

The report carries `status`, `exit`, `fuel`, `elapsed`, `preopens` and
stdout/stderr — status values: `SUCCESS`, `ERROR`, `TIMEOUT`,
`FUEL_EXHAUSTED`, `MEMORY_EXCEEDED`.

Compile the code to WASM (Rust/Go/C/AssemblyScript/Zig — see the Ephemora docs) and then offer it to the
engine as a tool; the tool is classified as mutating, so it goes through the P0-1 approval gate.

## Decision (2026-10-02): cell by default for LLM code — owner chose A

`execute_code` ran model Python in-process, with full host access (`os`, `subprocess` need no registry
tool). E0 had poked the tool gate shut (`ephe_tools` only ever passes auto-approved tools); the execution
layer itself therefore stayed unprotected. The owner decided: **a pinned Python WASI cell** — not an OS
wrapper, and not "just make it visible".

That is now the build plan for wave E:

- A wasi-python component (~25 MB) is fetched into `~/.ephe/cells/` when needed and checked against a
  compiled-in SHA-256 — Ephemora's `run_isolated_dict(expected_sha256=…)` exists for exactly this. No
  silent download without a hint, no hard repo blob.
- `execute_code` routes into the cell once the component is present; the in-process kernel stays an
  explicit opt-out (`EPHE_CODE_EXEC=kernel`), not the default. No silent fallback in either direction.
- The kernel's promise that "variables survive calls" stands: the namespace is pickled into the sandbox
  directory per call and back, and the preopen stays restricted to exactly that directory.
- The report (status/fuel/elapsed/preopens) becomes both the signature receipt and the audit-log entry —
  that is the cell that dies, and the log that remains.

Order: wave D4 (Kepta bridge + Ephe memory as an MCP server) first, because it needs no new dependency;
then wave E.

## Decision (2026-10-11, W3-15): cell-by-default is the licence — the gate in front of the kernel

The 2026-10-02 decision made the cell the *default execution*. It left one coupling open, named at the
time: `execute_code` stayed unconditionally in `SAFE_TOOLS`, so the auto-run was tied to the tool **name**,
not to the cell. Two consequences followed from that single fact:

- On a machine where the guest was **never** installed, `exec_runtime()` returns `kernel` and
  `_execute_in_kernel` execs model Python in the Ephe process — `os`, `subprocess`, network, host files —
  and the static `SAFE` meant that ran **without a dialog**.
- "Flipping a single byte in `python.wasm` silently made execution unsandboxed (auto-approval included)"
  (the coupling this file names further down) *was* that coupling, seen from the other side: sandbox and
  approval were wired to the same switch, and without the guest both were off.

W3-15 closes it by making the risk class a function of the runtime, not the name:

- `core.cpython_cell.code_runs_uncontained()` is exactly `exec_runtime() == RUNTIME_KERNEL` — the one
  condition under which the runner execs on the host. It stays cheap (the env shortcut and
  `guest_installed()`, a stat) because the gate reads it on every classification; the equality against
  `exec_runtime()` is pinned in `tests/test_cell_default_approval_gate.py`.
- `core.tools.approval` consults it in the one place the CLI gate and the chat gate both read:
  `classify_tool` reports `SAFE`/auto-run while the cell carries the run and `MUTATING` when it does not;
  `chat_tool_requires_confirm` asks the same way. **Fail-closed**: a runtime that cannot be read counts as
  uncontained, i.e. as needing the gate.
- Effect — the cell is the licence. Contained ⇒ no dialog (the fuel/memory/file/network caps are the
  scope, the report is the receipt). Uncontained ⇒ the same gate `run_shell` passes: CLI `--yes` /
  `--dry-run` / deny, chat confirmation, and non-interactive without a flag is a deny.

Unchanged by this: `run_sandboxed_code` (prebuilt `.wasm`) stays `MUTATING`; every other tool's class is
still fixed by name; and a normal contained run keeps its auto-run ergonomics.

## Procurement status (2026-10-02, re-checked): 1.0.5 — and no CPython cell

The wave-E planning started from two things that are not true:

- **The index has no `2.x`; the upstream trunk does.** PyPI state: `1.0.4.3` →
  `1.0.5` (29 Sep 2026; the ladder comes from `pip index versions ephemora-cell`). The pin
  `ephemora-cell>=1.0.4.3,<1.0.5` (wave H1) excludes 1.0.5; 1.0.4.3 is what is installed and locked.
  `~/ephemora-cell` is a real clone of upstream (`origin` = the dependency's public repository,
  `main` at `27d8bff`, 2026-08-30) and its `pyproject.toml` says **2.2.0** — so
  upstream, but a trunk out of band: no published release belongs to that number, and the 1.0.5 metadata
  points its homepage at the same repo. Not an embarrassed snapshot, but also not a release. What counts
  for us is the **installed** wheel: what is not in it has not been shipped, the clone's documentation is
  not authoritative for 1.0.4.3, and the clone stays read-only.
- **1.0.5 is a measurement question, not an update.** Ephe pins the rung whose cell policy this
  codebase actually read: `core/cpython_cell.py` writes `max_fuel`, `max_memory_mb`,
  `timeout_seconds` and the I/O caps into the `WASIConfig`, and
  `core/cell_policy.policy_snapshot()` reports those same numbers to the settings card, `ephe doctor`
  and the status page under one rule — report == enforced. A bound that walks past the measured rung
  makes that sentence false: the panel would still quote caps that were read off 1.0.4.3 while a
  different runtime enforces them. **The licence is recorded, not fenced.** Ephemora Cell is our own
  product, so BUSL-1.1 binds nobody here; what the versions carry is stated as a fact —
  `1.0.4.3` = Apache-2.0, `1.0.5` and `1.1.0` = BUSL-1.1, read from each wheel's `*.dist-info/METADATA`
  and `licenses/LICENSE` with the sha256 checked, and cross-checked against the installed Dist-Info by
  `tests/test_dependency_license_fence.py`. `core/cpython_cell.cell_runtime_license()` still reads the
  licence where it lives, because a card that misstates the installed artifact is its own defect.
  **What the rung above really carries** (read from the wheels and from the clone's
  `v1.0.4.3..v1.1.0` history): `WASIConfig` gains `allow_fsync` and `max_wasm_bytes` in 1.1.0 and drops
  nothing, so Ephe's call site stays valid; 1.0.5 brings the `expected_alg` pinning, the preopen
  denylist fix and the JCS safe-integer guard. **What no rung carries is the wasmtime fix** — the
  guest-can-panic-host advisory (`GHSA-j2g9-4prp-pf6h` = `RUSTSEC-2026-0314`, `wasmtime-wasi`
  37.0.0 through 48.0.2, fixed in 48.0.3) is unreachable from *every* published Ephemora Cell release,
  because 1.0.4.3, 1.0.5 and 1.1.0 all require `wasmtime<48,>=43.0.1`; our lock resolves 47.0.1 and the
  bundled `_libwasmtime.dylib` carries a 47.x token. Ephe runs the guest exclusively through
  `run_isolated()` → `process_executor` → `process_worker`, i.e. the disposable worker subprocess, and
  that subprocess is the containment for the in-process panic vector — so the flaw is accepted in
  writing (`.github/engine-advisories.txt`) rather than ignored. Measured in H1 and still true:
  `WASIConfig` in 1.0.4.3 already carries `disk_quota_bytes` (256 MiB, per file), `io_cpu_seconds`
  (2.0 s) and `io_budget_bytes` (64 MiB), E1 sets all three explicitly, and the `use_subprocess=False`
  in-process path appears nowhere in Ephe. The wall is decided and locked (`72fa5de6`,
  `tests/test_dependency_license_fence.py`); `ephe doctor` runs the ladder, not this card.
- **No release contains a CPython/WASI component** (the 1.0.5 wheel is 170 KB), and
  there is no fetch helper. Option A ("pinned Python WASI cell") therefore needs its own procurement
  decision before E1 can be built.

Open with the owner: (1) stay on the measured rung 1.0.4.3, or re-measure the cell policy against
1.0.5/1.1.0 (egress grants, SSRF filter, the `expected_alg` pinning) and move the pin with it — a
measurement task, not a licence problem, because Ephemora Cell is our own product?
**Provisionally decided and sealed (wave H1, reason corrected 2026-10-09):** the pin
holds the rung this codebase measured, `ephe doctor` names a release above it as a re-measurement
decision instead of an upgrade command, and `tests/test_dependency_license_fence.py` keeps pyproject,
lockfile, documentation and `.github/cell-runtime-fence.json` from drifting apart. Moving the pin is
not forbidden by this — it needs the four caps re-read against the new runtime and a register entry
with that date on it. (2) Where does the wasi-python component come from and who verifies its SHA-256? —
**answered by wave E1:** from the signed python.org source, built and verified by
`build_cpython_guest.py`; the hash lives in the manifest, not with a supplier.

## Built (wave E1, 2026-10-02): seam A — the CPython cell is the default

**Seam decision (A):** `core/cpython_cell.py` binds `ephemora_cell.run_isolated()` natively instead of
dressing the guest up as an MCP tool inside `ephemora-cell-mcp`. Evidence:

- `run_isolated()` already starts the guest in its own worker subprocess — a guest crash kills the
  worker, not Ephe. On the MCP path Ephe would have had to manage that process itself (start, timeout,
  zombies, stdout piping): the same wall, more expensive. The worker is not a side product of this
  choice, it is the place where the hard file caps are enforced (`ephemora_cell/process_worker.py`:
  `disk_quota_bytes` as a per-file write limit, the `io_cpu_seconds` watchdog). The worker does not cap
  the sum across several files inside one preopen — Ephemora
  counts its own sandbox folder (`io_budget_bytes`) and names the
  preopen variant as a v2 option. That cap is therefore Ephe's own promise
  (`DEFAULT_WORK_QUOTA_BYTES`, enforced in `core/cpython_guest.sweep_work_dir`).
- The MCP stdio path cuts stdin off at `STDIN_MAX_BYTES = 9.216` bytes; every model program would have
  landed inside that. Here the program sits as a file in `/work`, and a 20 KB program runs
  (demonstrated in `tests/test_cpython_cell_e1.py`).
- The report needs fields the MCP tool does not return — `fuel_consumed`,
  `effective_preopens`, exit code. Exactly the lines that settings, the audit log and the panel show
  ("report == enforced").
- `io_bytes_written` is **not** in the headline for any of this: measured, the
  engine counter reports `0` while the guest writes 32 MiB into `/work`. The counting does not see the
  guest's write paths, and the cap still works — so Ephe measures the floor itself (`work_bytes`) and
  does not ground the claim in the counter.
- Path B stays tested only as a cheap guard: `core/tools/code_kernel.py` imports no MCP client, and
  `mcp_client` has no `run_python`.

**Procurement:** the guest is not a download but a build from signed source —
Python 3.13.16 (python.org archive, SHA-256 in the manifest) with wasi-sdk 24.0 (SHA-256 pin),
cross-built via `Tools/wasm/wasi.py`, one patch `ac_cv_func_fdatasync=no` (without it
Ephemora P1 #12 refuses every module that imports `fd_datasync`, and no CPython runs in the cell).
Recipe, toolchain and licenses are in `core/cpython_guest.manifest.json`; building happens exclusively
through `build_cpython_guest.py` (fetch → build → stage → install → record → smoke).
~29 MB of interpreter and 1.256 stdlib files sit under `~/.ephe/cells/` and therefore
**never** in Git; the repo holds only hashes and the recipe.

**Integrity:** entry hash on every load, stdlib tree digest once per process
(`guest_state(deep=True)` for doctor and for build). Any deviation is `GUEST_UNVERIFIED` with a build
hint — never a fall-back into the kernel. The kernel remains only the case "the guest was never
installed" and then names itself: since the live test of 2026-10-02, `guest_installed()` separates it
from "installed but unverifiable" — before that both collapsed to `False` through `cell_ready()`, and
flipping a single byte in `python.wasm` silently made execution unsandboxed (auto-approval included). The installation is read-only (directories
0555, files 0444), because a write test inside the guest showed exactly the case this replaces: a model
set `json/__init__.py = "x"` and the pinned guest kept running with a corrupted stdlib until the digest
caught it. Permissions plus manifest digest are the answer, not trust in the guest.

**Reproducibility:** the recipe is complete and re-runnable (archive and SDK
by SHA-256, commands and patch in the manifest); the output is not path-independent. The pinned entry is
byte-identical to the artifact of the tree that produced it, and to the installation; a freshly unpacked
second tree from the same archive produced a different hash (29.309.917 instead of 29.309.906 bytes), a
third scratch path gave 29.345.624, and the stdlib digest moves along, because `.pyc` headers contain the
staging path and the build timestamp. The hashes in the manifest therefore describe the installation
state that every load is checked against — not an expectation for every rebuild environment. Anyone
rebuilding runs `record`, and `--stage-only` compares built against pinned before anything is installed.
A bit-for-bit reproducible build would be the next step and is not claimed here.

**Measured caps** (ephemora-cell 1.0.4.3 / wasmtime 47.0.1 / Darwin arm64):

| Cap | Value | Evidence |
|---|---|---|
| Fuel per run | 20.000.000.000 (`EPHE_CELL_MAX_FUEL`) | `while True` → `FUEL_EXHAUSTED`, `fuel_consumed == fuel_budget`, Ephe survives and the next run proceeds |
| Boot fixed cost | 1.418.393.708 fuel / 995 ms wall | `print(1+1)` — before any model code |
| Conversion | ~9,0 G fuel per guest CPU second | a 2,0 s counting loop = 18,04 G fuel → the default cap is ~2,2 s of compute time |
| Memory | 256 MB | a 512 MB allocation → `MemoryError` **inside the guest**, no host OOM |
| Wall timeout | 30 s | Ephemora watchdog, independent of fuel |
| `/work` per **file** | 32 MiB (`disk_quota_bytes`) | The engine sets RLIMIT_FSIZE in the worker: 64 × 1 MiB in *one* file → `OSError [Errno 22] File too large` at exactly 33.554.432 bytes, the file sits on the cap (measured) |
| `/work` per **session** | 64 MiB (`DEFAULT_WORK_QUOTA_BYTES`) | Measured 2026-10-02: eight files of 4 MiB each stayed under the per-file cap and together occupied 34.238.818 bytes on disk — the engine does not see the sum. So ephe sweeps (`core.cpython_guest.sweep_work_dir`, before and after every run): 20 × 4 MiB ends at ≤ 64 MiB, oldest first, output journals and session state are protected, and the report names what had to make room |
| the engine's `io_budget_bytes` / `io_cpu_seconds` | 64 MiB / 20 s | The byte guard scans **the engine's sandbox folder**, not Ephe's `/work` preopen — `io_bytes_written` always reports 0 for `/work` (measured, and nailed down in `tests/test_cpython_cell_e1.py`). `io_cpu_seconds` caps write load in the preopen only in time (worker rusage). The total cap on `/work` is therefore Ephe's own enforcement, not the engine's |
| stdout / stderr | ~10.000 bytes each into the Ephemora sink; **not a cap, a wall** | from ~11.000 bytes the guest raises `OSError [Errno 29] I/O error` out of its own `sys.stdout.write` |
| Output policy (ephe) | `core.cell_boot` tees the full stream to `/work/stdout.log` (512 KiB/run), 2.048 bytes per stream are passed through | The report delivers head **and** body, counts the losses, names the byte range — and the next run in the same session can read it |
| Network | none | `socket` → Errno 58 (notsupported), Preview1 has no sockets |
| Host files | only `/work` writable, guest root read | `open('/etc/passwd')` → Errno 44 |

**Why the tee sits inside the cell and not in the host:** the wall stands *inside* the guest.
A host that limits the channel after the fact cannot prevent the `OSError` raised while writing —
it can only let it land on the model as the model's own error. So `core/cell_boot.py` trims the
pass-through before the sink is ever provoked, and meanwhile parks every byte in `/work`. The host cuts
with head and body afterwards (errors sit at the end, and so does "last line = result") and names the
byte range in the journal. Demonstrated in
`tests/test_cpython_cell_e1.py` — including the second run that fetches the rest.

**Deliberately unresolved:**

- Code that writes straight to the file descriptor with `os.write(1, …)` bypasses the tee and still runs
  into the wall. The test records that this is *not* a success — the edge is named, not hidden.

- The **peak during** a run is not hard-capped: ephe sweeps before and after the
  run, the engine caps per file (RLIMIT_FSIZE) and caps write load in time
  (`io_cpu_seconds`). A run that writes many files within ~2,2 s of compute time can
  briefly exceed the session quota before the report brings it back in line —
  `run_isolated` offers no abort handling for the worker on this path.

- The guest sees no host files and no `ephe_tools`. Everything a skill previously walked through the
  user's machine with `pathlib` now needs a tool call (`read_file`, `file_search`) or the named opt-out
  `EPHE_CODE_EXEC=kernel`. That is a consequence of the cell, not a bug in it.
- The guest has no OpenSSL, no compression (`zlib`/`bz2`/`lzma`), no `sqlite3`,
  no `readline`, no `fork`/`subprocess` — wasi-sysroot 24 does not ship them.
- The precompiled `.pyc` files are tied to the minor version of the build host; another host
  builds a different tree (legal, but hashed differently). That is why the recipe is in the manifest and
  not just the output.
- `run_shell` stays what it was: native binaries are not WASM modules.

## Built-in browser: scope instead of a dialog (wave G)

The browser cluster (`browser_go/click/type/press/screenshot`) does not ask in chat — here `SELF_GATED`
does **not** mean `check_sandbox` (that call only sits in the vision cluster),
it means the scope is the gate:

- `core/browser_url.py::url_policy` allows http/https, data: and `file:` **only
  inside Ephe's own storage locations** (`~/.ephe`, `EPHE_IMAGE_DIR`, the output path, the workspace,
  /tmp; symlinks resolved, no `../` escape). `javascript:`, `gopher:`, `chrome:`, `ws:`,
  `ftp:`, `about:` are refused. Before this, `file:` was explicitly whitelisted —
  "open file:///Users/x/.ssh/id_rsa" was a file reader that never asked.
- `browser_exec` now keeps its declared time budget (1–300 s, default 120): on expiry it returns the
  stdout captured up to that point and discards the session, instead of leaving the turn stuck on an
  endless loop.
- The decisive difference from the rest: the headless context holds none of the user's cookies. A portal
  login through the browser is therefore not theft — and equally not an action taken in the user's name.

`browser_exec` itself stays in-process Python with full host access and needs the dialog; that is exactly
the layer wave E moves into the cell.

## fetch_url: the same scope rule, second tool (wave G4)

`fetch_url` is the only tool that receives a URL directly from the model, and up to here it followed
redirects blindly (`follow_redirects=True`, no address check, no size limit). `core/net_guard.py` is the
counterpart to `browser_url.py` — the same formula: **scope, not guesswork**, decided as a pure function
of (URL, resolution).

- Scheme: http/https only. `file:`/`data:`/`gopher:`/`ftp:` do not pass.
- Target address: public by default. Loopback/RFC1918/IPv6-local are **opt-in** through
  `EPHE_FETCH_ALLOW_PRIVATE=1` (the legitimate case: documentation on your own dev server).
- Link-local, `0.0.0.0/8`, IPv6-unspecified and the metadata endpoints
  (`169.254.169.254`, `fd00:ec2::254`, `metadata.google.internal`) stay **always**
  blocked — the opt-in applies to the dev server, not to the environment's instance credentials.
- **Every redirect hop is checked individually** (max 5). A 302 onto `127.0.0.1` is exactly
  the attack that checking only the entry point does nothing against.
- Data volume: at most `MAX_DOWNLOAD_BYTES` (2 MB) per request; beyond that the text is
  truncated and the note says so. Before, a large document was a memory DoS inside the process running
  on the user's machine.

Deliberately unresolved and therefore noted here: DNS binding (TOCTOU). Resolution happens before the
request, and httpx then reconnects to the same hostname again; an attacker controlling the nameserver can
move between the check and the connection. IP pinning in the transport would close it — for a local tool
with no tenant boundary, documented rather than hidden.

## MCP rail

Ephemora Cell ships a dependency-free MCP stdio server whose tools are themselves WASM modules running
inside the cell. Ephe already consumes stdio MCP servers through `EPHE_MCP_SERVERS`:

```bash
export EPHE_MCP_SERVERS="stdio:ephemora-cell-mcp --tools-dir ./tools"
ephe chat
```

Every registered WASM tool then runs with fuel metering, an output cap and
without network; namespace `mcp_…`, dispatch through `core/tools/mcp_client.py`.

## Limits (honestly)

- `run_shell` stays outside the WASI sandbox (native binaries are not WASM modules);
  an OS Seatbelt/Landlock wrapper for it is a separate sprint (`SECURITY_THREAT_MODEL.md` §7, X1 boundary).
- Ephemora guarantees isolation plus resource limits, not that the code is correct.
- Model Python needs no AOT step anymore: since wave E1 it runs in the pinned wasi-CPython guest
  (see above). `run_sandboxed_code` remains the tool for prebuilt `.wasm` modules — the two paths are not
  interchangeable.
- The cell is not an antivirus: a guest that builds nonsense within 2,2 s of compute time still
  does that. What it promises is scope (no host files, no network, no process spawning) and a cap that
  the report makes readable.

## Regression

`tests/test_sandboxed_code_tool.py` — fail-closed without the package,
mutating classification, hello=SUCCESS, exploit=BLOCKED,
fuel exhaustion, observability fields. Tested against the public
PyPI release `ephemora-cell>=1.0.0`.

`tests/test_cpython_cell_e1.py` — wave E1: manifest and recipe, hash comparison,
guest-not-installed vs. mismatching (fail closed, no kernel fall-back), kernel
opt-out with a named consequence, the gate following the runtime (contained ⇒
auto-run, uncontained ⇒ gated; W3-15), `ephe doctor` fail-soft,
policy parity settings ↔ `WASIConfig` `/get-policy`, and live (skip marker without the
guest): fuel bomb, memory cap, host-file and socket refusal,
self-tampering of the interpreter, `/work` quota, a program above the 9.216-byte cap
of the MCP rail, no host tools from inside the guest.

`tests/test_cell_default_approval_gate.py` — W3-15: `code_runs_uncontained()` equals
`exec_runtime() == RUNTIME_KERNEL` across every choice, contained ⇒ `SAFE`/auto-run vs.
uncontained ⇒ `MUTATING`, the runtime probe does not leak into other tools' classes,
an unreadable runtime fails closed, and both gates (CLI `request_approval`, chat
`confirm_for_chat`) deny an uncontained run while auto-running a contained one.

The rule **report == enforced** is also gated on every CI leg, without the package and
without a guest: `test_reported_caps_equal_the_config_the_runner_writes_without_the_guest`
stands a fake `ephemora_cell` in front of the real path
(`run_python` → `_run_sync` → `WASIConfig`) and pins the config the runner builds to
`policy_snapshot()` — fuel, memory, timeout, `io_budget_bytes`, `io_cpu_seconds`,
`disk_quota_bytes`, and an egress-free `allow_dirs` (only the read-only guest root and
the writable `/work`). The `@live` sibling `test_cell_config_carries_every_ceiling_it_claims`
is the same identity against the installed release; this one keeps it in CI.
