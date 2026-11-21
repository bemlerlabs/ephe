# Gold-Standard SKILL.md Template (Deep-Audit 2026-09-13)

Kopiere diesen Block und fuelle ihn aus. Die Regeln darunter sind verbindlich.

---
name: <slug>
version: "1.0.0"
trigger: /<cmd>
description: "<ein Satz, <=120 Zeichen, enthaelt die distinktiven Suchwoerter>"
when_to_use: [<>=2-Wort-Phrasen; keine Einzelwort-Fuellwoerter>]
when_not_to_use: [<distinkt; ueberlappt nicht mit when_to_use>]
tools: [<minimale geschlossene Menge; bei Datei-Artefakt immer verify_artifact>]
quality_profile: standard|artifact|source_grounded
allowed_tools: [<identisch zu tools — ein Feld, kein Dualismus>]
artifact_types: [<pdf|pptx|xlsx|docx|svg|image|video|notebook oder []>]
---

# <name>

**Trigger**: /<cmd>
**Description**: <exakt der Frontmatter-description-Wert>
**Tools**: <exakt die Frontmatter-tools, kommagetrennt>

## System Prompt

<Rollensatz. Dann die Loop in 3–5 nummerierten Schritten:
1. PLAN — in einem Satz, was getan wird.
2. ACT — welches Tool, welche Aenderung.
3. VERIFY — das konkrete Verify-Kommando (run_tests / verify_artifact).
4. REPORT — ehrliche Uebergabe mit echtem Tool-Output.>

Regeln:
- Read before edit. Never guess file content.
- Kein Claim ohne echten Tool-Output (kein Simulieren).
- Immer in der Sprache des Nutzers antworten.

Output Contract:
- <Liste der gelieferten Artefakte/Dateien mit je einer Zeile Begruendung.>
- <Ausgefuehrte Verify-Kommandos und ihre echten Ergebnisse.>

Quality Gate:
- <Harte Bedingung, z.B. 'run_tests >=1x nach dem letzten Edit' oder
  'verify_artifact lieferte ARTIFACT_VERIFIED'.>

## Test

**Input**: <reale Nutzer-Phrase>
**Expect Tool**: <exakter Toolname>
**Expect Contains**: <distinktives Token, z.B. ARTIFACT_VERIFIED / DOCUMENT_BUILT_VERIFIED>

## Reference

<Kurz-Checkliste. NICHT wortgleich mit den System-Prompt-Bullets (Dedup).>

## Example

Input: <frage>
Tool-Call: {"name":"<tool>","arguments":{...}}
Answer: <erwarteter Final-Text inkl. Evidenz-Zeile>

---

## Verbindliche Regeln

1. **Frontmatter ist die einzige Wahrheit.** Die `**Description**:`/`**Tools**:`-Zeilen
   im Body sind nur Fallback und muessen wortgleich mit dem Frontmatter sein — sonst
   wirft der Loader eine Mismatch-Warnung.
2. **`allowed_tools` == `tools`.** Kein eigener Wert; ein Feld steuert die Whitelist.
3. **`## Example` ist ein echtes Few-Shot-Paar**, kein Bullett-Block:
   `Input → Tool-Call (JSON) → Answer (mit Evidenz-Zeile)`. Kleine Modelle
   (gemma4:12b, qwen3:4b) treffen den Call nur bei gemustertem Output.
4. **Jeder `## Test` braucht `Expect Tool` UND `Expect Contains`** mit einem
   distinktiven Token, den nur ein korrekter Lauf produziert.
5. **Artefakt-Skills listen `verify_artifact`** in `tools`/`allowed_tools`; der
   Fast-Path haengt die `ARTIFACT_VERIFIED/FAILED`-Evidenz an.
6. **Sidecars sind gekappt** (`references/` ≤1200, `examples/` ≤1600 Zeichen,
   doppelte Zeilen werden im Loader deduplt) — kein Gold-Example ueber 20 Zeilen.
