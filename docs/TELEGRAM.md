# Telegram Channel

Ephe runs as one local service: one FastAPI app, one runtime. The Telegram channel is an adapter
inside that service (`core/channels/`), routed into the same engine and chat pipeline as the desktop
PWA (`core/engine_config.py` plus `core/tools/registry.execute_tool`). It adds no second runtime and
no relay process, and no Ephe server stores or proxies your conversations. The repo's documented,
opt-in `ephe serve` OpenAI adapter is a separate, user-invoked surface, not part of the channel.

Where each piece runs:

- **Messages** leave your device over the Telegram API as an outbound connection. Ephe opens no
  inbound port and operates no relay of its own — the carrier's network carries the message the same
  way it carries an email. Conversation content, tool approvals, local files, and model execution
  never pass through an Ephe or third-party cloud.
- **Approvals** reuse the local policy. Channel sessions run under the P0-1 ApprovalPolicy
  (`core/tools/approval.py`): mutating and network tools are denied by default and require your
  explicit approval. There is no auto-approve path.
- **Pairing** is an allowlist on your own device. You add your Telegram user ID to a static allowlist
  stored locally; it is empty by default, so the channel answers nobody until you add someone. No
  Ephe account, no sign-up, no telemetry in this repo.
- **Setup** runs as local configuration on your own device; there is no registration step with us.
  The one-command installer starts the local service; enabling the channel is a local step, and the
  bot token is stored owner-only — a `0700` directory holding a `0600` file, the same hardening as
  `~/.ephe/engine.json` (`core/engine_config.py`).

**Status: active.** The security foundation ships: the pairing allowlist and the prompt-injection
guard live in `core/channels/`, and outbound transport adapters exist for Telegram (`telegram_bot.py`)
and Discord (`discord.py`), verified end-to-end live against the configured engine
(`qwen3.8-flash-next`, OpenAI-compatible vLLM, `tests/test_channel_injection_guard_live.py`).
Everything above the channel adapters is the already-shipping local core, which runs fully offline as
soon as you have picked a local engine.
