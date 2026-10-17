# Security And Privacy

The defaults this build ships, and the exposure each one closes off. The threat model behind them is
in [`SECURITY_THREAT_MODEL.md`](SECURITY_THREAT_MODEL.md).

| Mechanism | What it does |
|---|---|
| Local default bind | The server starts on `127.0.0.1` unless LAN mode is requested |
| Conservative CORS | Browser origins are restricted |
| Tool approval | Shell, screenshot, and GUI actions require explicit approval |
| Per-segment shell whitelist | Every segment of a chained command (`;`, `&&`, pipes) must be whitelisted; command substitution, redirects, and `curl`/`wget` are blocked |
| Local memory path | Personal data is stored under local Ephe paths |
| Optional online labels | Network features are shown as opt-in |
| No telemetry in this repo | No analytics or tracking pipeline is included |

Security reports: see [SECURITY.md](../SECURITY.md).
