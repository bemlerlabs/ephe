# Competitive delta board

Date: 2026-10-26. Order: S25 §8. Product: `bemlerlabs/ephe`. This board names
where Ephe stands beside Cursor, Qoder, Hermes and pi, and what it must close
before a comparison earns a sentence.

## Reading rule

A cell carries what was observed and where. `unmeasured` means nobody ran the
check on this host; a vendor's documentation is named as such and is no
measurement. No cell claims "better": that word needs a number, a command and a
log line beside it (S25 §1, §10). The Ephe cells cite the code, the release or
the receipt that carries the evidence.

## The board

| Surface | Cursor | Qoder | Hermes (CLI / Desktop) | pi | Ephe |
|---|---|---|---|---|---|
| First run | vendor documentation: account and picker inside the IDE; unmeasured here | installed on this host; first-run path unmeasured | not installed here; unmeasured | not installed here; unmeasured | fails closed without `~/.ephe/engine.json`; no guided first run yet (S25 §9 is the target). Evidence: `core/engine_config.py`, S25 §9 |
| Task runtime | cloud agent, vendor documentation; runtime unmeasured | agent inside the IDE; runtime unmeasured | unmeasured | unmeasured | one SSE turn, tool loop, abort at 1,152 chars with no terminal frame (S21 receipt); 0.1.8 keeps the tool result and reason on a frame without a call id (`c2f49ab`) |
| Coding loop | editor-native; unmeasured | editor-native; unmeasured | CLI agent; unmeasured | CLI agent; not installed here | no measured coding loop; repo-verify harness exists with 23 held-out tasks and is the 0.2.5 slice (C6) |
| Update trust | vendor-managed; unmeasured | vendor-managed; unmeasured | unmeasured | unmeasured | shell replaces only the `.app`; 0.1.8 compares shell and backend versions, but the check loses the race against the cold backend start (S25-3a). Tag `v0.1.8` = `64f87633` = main; feed 0.1.8; package hashes measured |
| Marketplace | vendor extensions; unmeasured | skills and MCP connectors, counts unread | unmeasured | unmeasured | plugin marketplace with a six-field contract, 22 catalogue entries; marketplace core is 0.2.3 (E5) |
| Native desktop | Electron-class shell; unmeasured | desktop app; unmeasured | unmeasured | terminal only | tray, window effects (`set_effects`, `UnderWindowBackground`), updater, dialog, notification, global shortcut; no full menu, pasteboard, Quick Look, Share, Finder icons, Dock badge, Vision OCR (N2–N8). Ad-hoc signature: `codesign` reports `Identifier=app-145d…`, `TeamIdentifier=not set` |
| Security | vendor-hosted; unmeasured | vendor-hosted; unmeasured | unmeasured | unmeasured | fail-closed engine, key from env or `~/.ephe/engine.key` only, loopback fetch guard, command line free of the backend path (`6dce8df`); signing and TCC diagnostics are N1 |
| Measured evidence | none on this host | none on this host | none on this host | none on this host | S19/S21/S24 receipts: suite counts, artifact bytes, hashes, live turns. No competitor run exists |

## Must

| Must row | Why it is a must | Ephe version | Owner |
|---|---|---|---|
| Guided first-run threshold | a fail-closed start without a guide is a wall; Hermes' lesson (S25 §9) | 0.2.0-alpha.2 | Interaction Designer + Frontend |
| Stable update and rollback | an update that splits shell and backend breaks trust in one click | 0.2.0-beta.2 | SRE/Release Engineer |
| Ledger, cancel, resume | a run that cannot be replayed or stopped is not an agent workspace | 0.2.0-alpha.1 (ledger, cancel), 0.2.1 (resume) | Agent-Runtime Engineer |
| Coding loop baseline | without a measured loop there is no coding claim | 0.2.4 (C1) | DevEx/CLI + Agent-Runtime |
| Typed clipboard, Finder, Quick Look | the shell must do what a macOS app does with files and images | 0.2.0-alpha.2 (N3/N4), 0.2.0-beta.2 (N5) | macOS/Native Engineer |
| Vision OCR split | reading text out of an image must not need a vision model | 0.2.0-beta.1 (N7) | macOS/Native + Backend/Engine |

## Should

| Should row | Ephe version |
|---|---|
| Beta channel beside the stable feed | 0.2.0-rc.1 |
| Public changelog with each beta | 0.2.0-rc.1 |
| Marketplace P2 (registry, install/rollback) | 0.2.3 (E5), registry slice after |
| MCP and connectors | 0.3.x (E8) |
| 25 visual baselines | 0.2.2 (D6) |
| Benchmark axes web, coding, design | 0.2.5 (C7), 1.0 (K8) |

## Defer

Cloud agents, enterprise IM, voice, an editor fork, hosted models and
proprietary model claims. Each one would pull the product away from the
local-first, no-account core that the release gate protects (S25 §15).

## What would falsify this board

1. A competitor run on this host with the same task, engine budget and time
   limit, whose raw log contradicts a cell.
2. An Ephe update that leaves shell and backend unequal after the restart the
   surface asks for.
3. A native capability that exists only in the acceptance test and not in the
   installed app.

## Red team

1. **"Only Ephe is measured."** True. The board is a to-do list with evidence on
   one side; its value is that it stops us from writing the other side.
2. **"A delta board without competitor runs is marketing in waiting."** True
   until C7 installs pi and runs the same tasks; every cell above that carries a
   vendor claim says so.
3. **"Native islands can become a second product."** They can. N0 keeps them
   behind capabilities and a JSON contract, and each island ships with a web
   fallback.
