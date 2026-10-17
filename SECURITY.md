# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| `0.1.x` | Active |
| < `0.1.0` | Best-effort only |

## Reporting a Vulnerability

**Do NOT open a public GitHub issue for security vulnerabilities.**

Report through GitHub — the private channel is built into the repository and reaches every
maintainer:

**[Report a vulnerability](https://github.com/bemlerlabs/ephe/security/advisories/new)**

A private security advisory keeps the details out of public issues until a fix ships. There is
no security mailbox behind this project; anything that looks like one is out of date.

Include:

- A description of the vulnerability
- Steps to reproduce
- Your assessment of the severity (Critical / High / Medium / Low)
- Any suggested fix (optional)

The licence and the rights in this project sit with Bemler Labs; the trademark filing
follows the public release. <!-- owner decision 2026-10-16 -->

## Safe Harbor

We consider security research and vulnerability disclosure under this policy to be authorized,
beneficial to the project, and conducted in good faith. We will not pursue or support legal
action against a researcher who, while researching or reporting under this policy:

- finds and reports an issue through the private channel above,
- gives us a reasonable time to respond and to ship a fix before any public disclosure,
- keeps the report limited to what is needed to demonstrate the issue, and
- does not access, modify, or exfiltrate data that is not their own.

Under the [Business Source License 1.1](LICENSE) this product ships with, that research is
already permitted: the grant covers copying, modifying and non-production use, which is what reading
the source, building a local copy and demonstrating a flaw in your own environment amount to. What
this policy adds is the part a licence cannot give: our commitment not to pursue legal action for
research conducted under it.

If legal action is brought by a third party against you for research that followed this policy,
we will make this position public.

## What Not To Do

- Do not run denial-of-service, load, or volume testing against any shared instance.
- Do not access, modify, or delete data you do not own; demonstrate the issue with your own data.
- Do not disclose the issue publicly before a fix is released.
- Do not use social engineering, or attempt to reach a system through physical access.

## Response Timeline

| Phase | Timeframe |
|-------|-----------|
| Acknowledgment | Within **48 hours** |
| Initial assessment | Within **5 business days** |
| Fix release | Within **30 days** (critical: 7 days) |
| Public disclosure | After fix is released |

## Security Measures

Ephe is designed with **privacy and security as core principles**:

- **Zero Telemetry in this repository** — No analytics or tracking pipeline is included
- **No Engine Default** — the engine is the user's declared choice (a local Ollama or an
  OpenAI-compatible endpoint); nothing picks one in code, and the online providers are opt-in
- **Shell Sandbox** — Commands always require explicit user approval
- **Per-Segment Shell Whitelist** — Every segment of a chained shell command (`;`, `&&`, `||`, `|`) must start with a whitelisted binary. Command substitution (`$(…)`, backticks, process substitution), shell redirects, and network binaries (`curl`/`wget`) are rejected outright. Mutating tools are never auto-approved (`ApprovalPolicy.auto_approve` defaults to `false`).
- **File Whitelist** — Access restricted to safe directories only
- **Hardened Response Headers** — `Content-Security-Policy: frame-ancestors 'self'` (own artifact previews render, foreign framing blocked), `X-Content-Type-Options: nosniff`, strict `Referrer-Policy`
- **XSS Protection** — All output sanitized via DOMPurify
- **SVG Sanitizer** — Blocks script injection in generated graphics
- **No API Keys Required for Core Use** — External providers are optional
- **Supply-Chain Integrity** — `install.sh` verifies every vendor download (uv) against a pinned SHA256 and hard-fails on mismatch; `install.ps1` performs no vendor downloads at all (git clone + system Python only)
- **Virtual Environment Isolation** — Python dependencies run from the project environment

## Accepted advisories and pins

Where a finding is accepted rather than fixed, it is recorded here and in the register files:

- **Dependency Advisory Register** — `.github/advisories-ignore.txt` is the only place an advisory is accepted, and every entry names the package, its ecosystem and scope, the affected range, why no fix version exists and a re-check date. `.github/workflows/supply-chain.yml` audits every locked manifest in the tree on every lockfile change and weekly: `uv.lock` with pip-audit, `app/pnpm-lock.yaml` with `pnpm audit`, and `app/src-tauri/Cargo.lock` against the crates.io advisory database (one batched lookup for all 512 pinned crates). Each audit step is soft so its findings always reach the job summary and the annotations; what fails is the verdict step after it, on any finding no register row decides — before 2026-10-14 that chain ended at a warning for Python, and did not exist at all for Cargo, so a finding waited for a re-check date instead of failing where it appeared. An entry that passes its re-check date fails the run until it is upgraded away or renewed in writing. An advisory that has a release is not accepted but fixed: `[tool.uv] constraint-dependencies` in pyproject.toml holds urllib3, multidict and oauthlib at their fixed versions, the register keeps a `state=fixed` row naming each `fixed_in`, and `tests/test_supply_chain_gate.py` asserts the floor against pyproject.toml, asserts the committed `uv.lock` still resolves at or above it, and reads the floors out of the register rather than from a list of its own. An entry whose fix exists but has not been applied carries `state=pending-fix` and a `blocked_by=`, so it reads as open work rather than as a carried risk, and only PyPI entries in `state=accepted` ever reach `pip-audit --ignore-vuln`. **The Python audit reads PyPI only:** the npm and crates.io rows in the same register are judged by the JS and Cargo verdict steps, and `scripts/lockfile_check.py` additionally pins every crate `app/src-tauri/Cargo.toml` declares against the committed lock. The register and the dependency bot count different things - an entry is counted once per advisory, an alert once per advisory per locked version and per manifest - and the two sets only partly overlap — the wasmtime-wasi entries produce no Dependabot alert at all, because a crates.io advisory inside a pip wheel is not a manifest Dependabot reads. Neither number is the other's check.
- **Engine Advisory Register** — `.github/engine-advisories.txt` covers the class the Python audit cannot see: flaws in the Rust execution engine compiled into the `wasmtime` wheel, whose advisories live in the crates.io database. Measured 2026-10-09, the locked engine version answers zero records as `wasmtime` (PyPI) and five as `wasmtime-wasi` (crates.io) — so without this file the audit reports clean about the component that runs model-authored code.
- **Advisory ID resolution (blocking)** — `scripts/advisory_id_check.py` resolves every accepted ID against the advisory databases, by the ID itself and, when that misses, as a package/version query matched on `id` **and** `aliases`. A well-formed ID that names no advisory fails the run instead of being ignored quietly: `pip-audit --ignore-vuln` exits 0 on an ID that matches nothing, which is how an accepted risk could refer to an advisory that never existed.
- **Cell Runtime Pin Register** — `.github/cell-runtime-fence.json` records, per published Ephemora Cell release, the licence and wheel hash read from that artifact and whether this codebase measured its policy caps; the pin admits only measured, unexpired rungs, so the settings surface cannot report caps nobody read off the runtime that enforces them.
- **Path expressions in the owner's own folder settings** — CodeQL's `py/path-injection`
  query cannot model the confinement this tree uses: `core/path_guard.py` resolves a value
  once and then compares it on a path-separator boundary, and the two folder settings refuse
  the filesystem root, credential directories, system roots and this product's own state
  directory (`REFUSED_DIRS`). The three findings of that query stand dismissed on the
  security tab with this paragraph as their rationale; `tests/test_path_guard.py` and
  `tests/test_user_folder_choice.py` are what a reviewer reads instead of the alert.
- **Virtual Environment Isolation** — Python dependencies run from the project environment

## Scope

The following are **in scope** for security reports:

- Remote code execution
- Cross-site scripting (XSS)
- Authentication bypass
- Information disclosure
- Privilege escalation
- Denial of service

The following are **out of scope**:

- Issues in dependencies (report to upstream)
- Attacks requiring physical access to the device
- Social engineering attacks

*Ephe — Bad Liebenzell, Black Forest, Germany*
