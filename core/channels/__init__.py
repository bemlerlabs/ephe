"""Ephe – channel layer (Sprint 3 Gateway-Alpha).

Security-first components for the Telegram channel as an on-device gateway
(Sprint3-G2 channel threat model, docs/SECURITY_THREAT_MODEL.md §6):

- ``pairing``           — static pairing allowlist (default-empty) +
                          bot-token vault (keyring/0600) + channel approval policy.
- ``injection_guard``   — prompt-injection policy: channel content = data,
                          NEVER an instruction (E2 extension).

Rule (release bar): conservative. Channel messages run through
the same engine/chat pipeline as the PWA — no second runtime, no relay.
"""
