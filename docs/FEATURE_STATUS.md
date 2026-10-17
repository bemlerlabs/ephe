# Feature Status

What is active today, what is experimental, and the limits this table does not capture.

**How to read the status column.** `Active` means it ships, is covered by the tracked test
suite, and this repository's CI runs it. `Experimental` means it ships behind an explicit
switch, has no stability promise, and may change shape between releases. `Planned` means it
is written down as intent and is not in the tree yet — the row names what would have to
exist first, and nothing in the product claims it until it does.

| Feature | Status | Notes |
|---|---|---|
| Desktop PWA chat | Active | Root PWA is the main product |
| Tauri desktop shell | Active | Native window around the PWA plus what a browser cannot do: it starts and stops the Python backend, keeps the engine key in the OS keychain, holds the machine awake during a run, and ships a tray icon, native notifications, a native file dialog, an embedded browser, a single-instance lock and the auto-updater |
| Mobile PWA via QR | Active | LAN by default; public mode requires explicit opt-in |
| Telegram channel (gateway) | Active | Outbound httpx long-polling adapter (`core/channels/telegram_bot.py`); pairing allowlist + injection guard; QR pairing in Settings → Mobile |
| Discord channel (gateway) | Active | Second outbound-only REST adapter (`core/channels/discord.py`); token + runner toggle in Settings → Mobile; honest "not configured" without a token |
| Provider settings | Active | `local_ollama`, `custom_ollama`, `openai_compatible` |
| Model choice | Active | `EPHE_MODEL`, `--model`, or the UI name the tag; nothing sizes or picks a model (the RAM-based auto-picker was retired 2026-10-11) |
| Missing model recovery | Active | UI and CLI show `ephe doctor` / `ephe start` guidance |
| Vision upload | Active | Sends images to the configured Ollama-compatible vision path |
| File/PDF/Office workflows | Active | Local file access is restricted by tool policy; artifacts get inline previews |
| Shell/desktop actions | Active | Approval-gated, per-segment command whitelist |
| **Plugins (Extensions 1.0)** | **Active** | Manifest-based bundles (skills, commands, agents, hooks, MCP) — versioned, sha256-hashed, ES256-signed, switchable per plugin with a master kill-switch; marketplace + `ephe plugin` CLI |
| v2 experiments | Experimental | Not the main product surface |

Known limits that this table does not capture:

- Per-task model routing is partial: one active model at a time (G7 in [Feature Parity](AT_A_GLANCE.md#feature-parity)), not a shipped router.
- CI runs the tracked offline test subset; the full `pytest tests/ -q` suite is maintainer-side.
- The benchmark figures are a product benchmark and trend points, not an academic SOTA claim — the methodology and its deliberate limits live in [`benchmark-mapping.md`](benchmark-mapping.md).
