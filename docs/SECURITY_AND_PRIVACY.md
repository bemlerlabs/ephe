# Security And Privacy

The defaults this build ships, and the exposure each one closes off. The threat model
behind them is in [`SECURITY_THREAT_MODEL.md`](SECURITY_THREAT_MODEL.md).

| Mechanism | What it does |
|---|---|
| Local default bind | The server starts on `127.0.0.1` unless LAN mode is requested |
| Conservative CORS | Browser origins are restricted |
| Tool approval | Shell, screenshot and GUI actions require explicit approval |
| Optional OS sandbox | On macOS the opt-in Seatbelt sandbox wraps approved commands (workspace, temp and `$HOME` writes; no network). Linux has no OS wrapper |
| Per-segment shell whitelist | Every segment of a chained command (`;`, `&&`, pipes) must be whitelisted; command substitution, redirects and `curl`/`wget` are blocked |
| Local memory path | Personal data is stored under local Ephe paths |
| Engine key | The settings page and `ephe configure` store it in the OS keychain or in `~/.ephe/engine.key` (owner-only, 0600). A shell export stays in the running process. The key is never written to `engine.json` or to the chat |
| Local engine | A local model such as Ollama keeps the prompt on this machine |
| Optional online paths | A hosted engine, web search, cloud text-to-speech and public mobile access are opt-in. What you send on one of those paths goes to the service you chose |
| LAN and public access | LAN mode is opt-in; public mobile access is a separate opt-in |
| Update check | The app asks GitHub for the newest release. There is no account and no telemetry pipeline in this repository |
| No telemetry in this repo | No analytics or tracking pipeline is included |

Security reports: see [SECURITY.md](../SECURITY.md).
