# Security And Privacy

The defaults this build ships, and the exposure each one closes off. The threat model
behind them is in [`SECURITY_THREAT_MODEL.md`](SECURITY_THREAT_MODEL.md).

| Mechanism | What it does |
|---|---|
| Local default bind | The server starts on `127.0.0.1` unless LAN mode is requested |
| Conservative CORS | Browser origins are restricted |
| Tool approval | Shell and desktop-control actions (the agent clicking or typing on your screen) require explicit approval |
| Screen capture | A screen capture runs without asking. What it took is stated in the answer you see: whole screen with no window and no page crop, or page viewport, plus the frame's pixel size; the file is written under Ephe's own image folder, where you can open or delete it. Only the command line adds a voice, and only for the screen: there a screen capture needs your approval flag, while a page capture is classed read-only and asks on no path |
| Optional OS sandbox | The switch stays off until it is turned on. On macOS, `sandbox-exec` allows writes in the workspace, temp and the device nodes, closes the rest of the home directory, and denies the network. On Linux, `bwrap` does the same when it is installed. A requested sandbox with no boundary does not run the command. `EPHE_SHELL_BACKEND=docker` remains a separate boundary |
| Plugin worker boundary | A plugin tool that carries its own code runs in a separate process under the OS boundary: it sees its own plugin folder and the interpreter's runtime, writes only to its own home and the temp root, and gets an allowlisted environment with no Ephe credential in it (measured: 11 names, none of them `EPHE_*`). It has no network: `(deny network*)` on macOS, `--unshare-net` on Linux — the macOS path is the one measured here, the Linux rule is asserted on the argv the builder returns. That rule was added after measuring a worker connect to the loopback port this server listens on and read `200` from two API routes with no token — the local bind is the reason a plugin must not be able to use it, and a capability that needs the host arrives through a channel the host controls, with the plugin's identity beside it. The MCP connector rail keeps its network: a server there may legitimately be a client, and it is not this boundary's child |
| Loopback callers | The desktop app and the PWA send an Origin this server serves, and those calls stay token-free. A read-only GET with no Origin stays token-free: that is the app's own fetch and the local health check. A mutation, a WebSocket handshake, and a GET that writes state or opens another service require that Origin or the LAN token. With LAN mode off there is no token, so a local process with no Origin cannot spend that authority. A process that copies the app Origin still can, because the header is a label a program on this machine can type. The plugin worker cannot open the socket |
| Per-segment shell whitelist | Every segment of a chained command (`;`, `&&`, pipes) must be whitelisted; command substitution, redirects and `curl`/`wget` are blocked |
| Local memory path | Personal data is stored under local Ephe paths |
| Engine key | The settings page and `ephe configure` store it in the OS keychain or in `~/.ephe/engine.key` (owner-only, 0600). A shell export stays in the running process. The key is never written to `engine.json` or to the chat |
| Local engine | A local model such as Ollama keeps the prompt on this machine |
| Optional online paths | A hosted engine, web search, cloud text-to-speech and public mobile access are opt-in. What you send on one of those paths goes to the service you chose |
| LAN and public access | LAN mode is opt-in; public mobile access is a separate opt-in |
| Update check | The app asks GitHub for the newest release. There is no account and no telemetry pipeline in this repository |
| No telemetry in this repo | No analytics or tracking pipeline is included |

Security reports: see [SECURITY.md](../SECURITY.md).
