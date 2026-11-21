#!/usr/bin/env python3
"""E4 generator: the golden case matrix for all 14 production plugins.

Writes plugins/<name>/prompts/golden.jsonl. It does NOT own
rubric.md: that text is authored and translated in the tree, so a missing
rubric is seeded and an existing one is left alone. Rewriting all 14 rubrics
from German literals here used to undo the English translation wave on every
run — and the language gate could not see it, because the restored text
matched the committed per-file baseline exactly (scripts/language_gate.py).

Every tool_use list uses ONLY real registry tool names (66 verified).

Usage:
    python scripts/gen_golden.py            # write golden.jsonl, seed missing rubrics
    python scripts/gen_golden.py --check    # report drift, write nothing, exit 1
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # scripts/gen_golden.py -> repository root
ANTI_SLOP = ["Platzhalter", "TODO", "Lorem ipsum", "[...]"]

#: {plugin: [cases]} — the case matrix, and nothing but the case matrix.
PLUGINS: dict[str, list[dict]] = {}

def cases(*cs: dict) -> list[dict]:
    return list(cs)

def c(pid: str, cmd: str | None, inp: str, expect: dict, note: str = "") -> dict:
    d = {"id": pid, "command": cmd, "input": inp, "expect": expect}
    if note:
        d["note"] = note
    return d

def art(suffix: str) -> dict:
    return {"kind": "artifact", "suffix": suffix}

def use(*tools: str) -> dict:
    return {"kind": "tool_use", "any": list(tools)}

def has(*subs: str) -> dict:
    return {"kind": "contains", "any": list(subs)}

def lacks(*subs: str) -> dict:
    return {"kind": "not_contains", "any": list(subs)}

#: Scaffold for a plugin that has no rubric yet. Written only when the file is
#: absent — an existing rubric is owned by the tree, never regenerated here.
RUBRIC_SEED = """# Rubric — Plugin `{name}`

Quality criteria for the golden matrix. The pass^3 rate of this suite is
measured, not claimed: a case counts only when all 3 runs pass (TAU
reliability, as in evals/bench_option_b.py). Gate: **pass^3 >= 90 % per
plugin** (`ephe bench --run {name}`).

Criteria:
1. **Real artifact**: the promised file or behaviour exists and is checked.
2. **Structure**: organised output, not a wall of prose.
3. **Sources**: figures name where they came from; nothing invented.
4. **Usable**: the user can forward the result without editing it.
5. **Anti-slop**: no placeholders, no TODOs, no filler.
"""

PLUGINS["documents"] = cases(
    c("documents-1", "pdf", "Erstelle ein einseitiges PDF 'Quartalsbericht Q3' mit Kennzahlen-Tabelle und einer Quellenangabe.", art(".pdf"), "deck-Kommando muss echte PDF-Datei liefern"),
    c("documents-2", "docx", "Erstelle ein DOCX-Protokoll der Team-Besprechung mit Tagesordnung und Ergebnissen.", art(".docx")),
    c("documents-3", "report", "Erstelle einen Report im Briefing-Stil zur Marktlage von E-Bikes in Deutschland.", has("Quellen", "Kennzahlen")),
    c("documents-4", None, "Erzeuge einen QR-Code zur URL https://example.org/ephe als PNG-Datei.", use("create_qrcode")),
    c("documents-5", None, "Erstelle ein Quellen-Notizbuch zum Thema 'Heizungspumpen-Vergleich' mit 3 echten Quellen.", use("create_source_notebook", "export_source_brief")),
    c("documents-6", "pdf", "Baue ein PDF mit einer Tabelle über 4 Mitarbeiter und ihren Urlaubstagen.", has("Tabelle", "Mitarbeiter")),
    c("documents-7", None, "Erzeuge eine Markdown-Briefing-Datei über den Stand des Onboardings.", art(".md")),
    c("documents-8", None, "Schreibe den Einleitungstext für den Quartalsbericht — fertig formuliert, nichts offenes.", lacks(*ANTI_SLOP)),
)

PLUGINS["spreadsheets"] = cases(
    c("spreadsheets-1", "xlsx", "Erstelle eine Ausgaben-Tabelle (Miete, Essen, Transport) mit Summenformel als XLSX.", art(".xlsx")),
    c("spreadsheets-2", "xlsx", "Baue eine Mitarbeiterliste mit Gehältern und einer SUMME über 12 Monaten.", use("create_xlsx")),
    c("spreadsheets-3", "xlsx", "Wandle diese CSV in eine formatierte Arbeitsmappe: name,rolle,stunde\\nada,dev,80\\ngrace,ops,70", art(".xlsx")),
    c("spreadsheets-4", "xlsx", "Erstelle ein Budget-Sheet mit Durchschnittsformel pro Kategorie.", has("Durchschnitt", "Formel")),
    c("spreadsheets-5", None, "Erzeuge ein Diagramm zum Umsatzverlauf Jan–Mär (120k, 135k, 150k).", use("generate_chart")),
    c("spreadsheets-6", None, "Beantworte ohne Tabellenblatt: Was ist der Unterschied zwischen SUMME und SUMMEWENN?", has("SUMMEWENN")),
    c("spreadsheets-7", "xlsx", "Erstelle die Vorstands-Tabelle mit echten Werten — keine unbestimmten Zellen.", lacks(*ANTI_SLOP)),
)

PLUGINS["presentations"] = cases(
    c("presentations-1", "deck", "Baue ein 5-Folien-Deck über unser Q3: Umsatz 150k, NPS 62, 3 neue Kunden.", art(".pptx")),
    c("presentations-2", "deck", "Erstelle ein Pitch-Deck (Problem, Lösung, Markt) für eine lokale Fahrradwerkstatt.", use("create_pptx_deck", "create_pitch_deck")),
    c("presentations-3", None, "Prüfe das Deck /tmp/deck.pptx auf Folienzahl und Sprechernotizen.", use("qa_pptx_deck", "inspect_pptx_template")),
    c("presentations-4", None, "Gib mir die Agenda als Text für einen 10-Minuten-Vortrag über lokale Stromspeicher.", has("Agenda", "Vortrag")),
    c("presentations-5", "deck", "Erstelle ein Deck mit Sprechernotizen zu jedem Slide über den Schwarzwald-Tourismus.", has("Notiz", "Sprecher")),
    c("presentations-6", None, "Wie viele Folien braucht ein 15-Minuten-Vortrag laut Faustregel? Begründe kurz.", has("Faustregel", "Folie")),
    c("presentations-7", "deck", "Vervollständige die Folientitel für das Q3-Deck — jeder Titel fertig formuliert.", lacks(*ANTI_SLOP)),
)

PLUGINS["code-shell"] = cases(
    c("code-shell-1", "fix", "python app/tests_smoke.py wirft IndexError Zeile 42. Finde die Ursache und fixe sie.", has("Ursache", "IndexError")),
    c("code-shell-2", None, "Zähle die Zeilen aller Python-Dateien unter core/ zusammen.", use("run_shell")),
    c("code-shell-3", "fix", "Der Linter meckert über ungenutzte Imports in ephe_cli.py. Räume auf und zeige den diff.", use("run_linter", "edit_file", "format_code")),
    c("code-shell-4", None, "Führe die Test-Suite tests/test_cli_desktop.py aus und fasse das Ergebnis in einem Satz zusammen.", use("run_tests", "run_shell")),
    c("code-shell-5", None, "Lies die Datei core/ephemeris.py und erkläre die Funktion chart() in 3 Sätzen.", use("read_file")),
    c("code-shell-6", None, "Erkläre, warum man shell-Befehle in Ephe freigeben muss, bevor sie laufen.", lacks("weiß ich nicht")),
)

PLUGINS["web-research"] = cases(
    c("web-research-1", "research", "Recherchiere die aktuellen Preise für 12kWh-Heimspeicher in Deutschland.", has("Quellen", "€", "EUR")),
    c("web-research-2", None, "Suche 3 aktuelle Nachrichten zur Schwarzwaldbahn-Sanierung mit URLs.", use("web_search", "fetch_url")),
    c("web-research-3", "research", "Vergleiche Ollama und vLLM für lokale Inferenz und nenne je Quelle.", art(".md")),
    c("web-research-4", None, "Hole die Inhaltsangabe der Seite https://example.org und fasse sie in 2 Sätzen zusammen.", use("fetch_url")),
    c("web-research-5", None, "Erstelle ein Quellen-Notizbuch zum Thema 'DGX Spark lokale LLMs'.", use("create_source_notebook")),
    c("web-research-6", None, "Nenne die Release-Notes von Ephe v1.1.0 aus dem lokalen CHANGELOG.md.", lacks("man sagt", "vermutlich")),
)

PLUGINS["browser-use"] = cases(
    c("browser-use-1", "browse", "Öffne https://example.org und nenne den H1-Titel der Seite.", use("browser_go", "browser_click")),
    c("browser-use-2", "browse", "Gehe zu example.org und mache einen Screenshot des Viewports.", use("browser_screenshot", "take_screenshot")),
    c("browser-use-3", None, "Fülle auf einer Testseite das Suchfeld mit 'ephe' aus — ohne abzuschicken.", use("browser_type")),
    c("browser-use-4", None, "Lies den ersten Absatz von https://example.org und fasse ihn zusammen.", has("Beispiel", "Domain", "Illustration")),
    c("browser-use-5", None, "Prüfe, ob https://example.org erreichbar ist, und nenne den HTTP-Status.", use("browser_go", "browser_exec")),
    c("browser-use-6", None, "Scrolle auf der aktuellen Seite ans Ende und zähle die Abschnitte.", use("browser_scroll")),
    c("browser-use-7", None, "Öffne eine Seite und zitiere wörtlich, was dort steht — nichts erfinden.", lacks(*ANTI_SLOP)),
)

PLUGINS["memory"] = cases(
    c("memory-1", "memorize", "Merke dir: Der Router steht im Arbeitszimmer, IP 192.168.1.1.", use("memory")),
    c("memory-2", None, "Was habe ich dir über den Router gesagt?", has("Arbeitszimmer", "192.168")),
    c("memory-3", "memorize", "Speichere, dass meine Lieblingsbibliothek für Diagramme Mermaid ist.", use("memory")),
    c("memory-4", None, "Liste alle gespeicherten Fakten über meine Werkstatt auf.", use("memory")),
    c("memory-5", None, "Vergiss den Eintrag über den Router wieder.", has("gelöscht", "entfernt", "vergessen")),
    c("memory-6", None, "Erkläre in 2 Sätzen, wo Ephe sein Gedächtnis lokal ablegt.", lacks("Cloud")),
)

PLUGINS["vision"] = cases(
    c("vision-1", None, "Beschreibe, was auf dem Bild /tmp/screenshot.png zu sehen ist.", use("analyze_image")),
    c("vision-2", None, "Wo sitzt der 'Senden'-Button in /tmp/ui.png? Nenne ungefähre Koordinaten.", use("analyze_image", "vision_click")),
    c("vision-3", None, "Klicke auf das Menü-Symbol oben rechts in der geöffneten App.", use("vision_click")),
    c("vision-4", None, "Tippe 'Ephe' in das fokussierte Textfeld des Bildschirms.", use("vision_type")),
    c("vision-5", None, "Die Datei /tmp/gibtsnicht.png — prüfe, ob sie existiert, bevor du sie analysierst.", lacks("auf dem Bild ist", "ich sehe")),
    c("vision-6", None, "Vergleiche die zwei Diagramme in /tmp/a.png und /tmp/b.png in 3 Sätzen.", use("analyze_image")),
)

PLUGINS["voice"] = cases(
    c("voice-1", None, "Sprich den Satz 'Willkommen bei Ephe' als Audiodatei.", art(".wav")),
    c("voice-2", None, "Transkribiere die Datei /tmp/notiz.wav und gib den Text aus.", has("Transkript", "Text")),
    c("voice-3", None, "Erzeuge eine Audio-Version der Kurzanleitung 'Erster Start' als MP3.", art(".mp3")),
    c("voice-4", None, "Welche Stimmen sind lokal installiert und welche müssten nachinstalliert werden?", has("piper", "Stimme", "installiert")),
    c("voice-5", None, "Lies den Satz 'Test' vor, ohne eine Datei anzulegen — nur zur Kontrolle.", has("Audio", "Stimme")),
    c("voice-6", None, "Die Stimme en_US-amy-medium fehlt — was sagt Ephe genau?", lacks("habe einfach eine andere benutzt")),
)

PLUGINS["image-studio"] = cases(
    c("image-studio-1", None, "Erzeuge ein SVG-Logo: Kreis mit aufgehendem Pfeil, flat, 512x512.", art(".svg")),
    c("image-studio-2", None, "Baue ein isometrisches Icon einer Werkstatt als SVG.", use("create_svg")),
    c("image-studio-3", None, "Erstelle einen 5-Sekunden-Loop: Tautropfen fällt in einen See, als MP4.", art(".mp4")),
    c("image-studio-4", None, "Zeichne ein Diagramm-Thumbnail (Balken, 3 Balken, blau) als SVG.", use("create_svg", "create_diagram")),
    c("image-studio-5", None, "Erzeuge ein 1024x1024 Rasterbild eines Orbs — sag ehrlich, ob die lokale Bild-Engine das kann.", has("Engine", "Vektor", "SVG")),
    c("image-studio-6", None, "Erkläre den Unterschied zwischen SVG- und PNG-Ausgabe in deinem Werkzeugkasten.", has("Vektor", "Raster")),
    c("image-studio-7", None, "Beschreibe das fertige Logo-Design in 3 Sätzen — das konkrete Ergebnis.", lacks(*ANTI_SLOP)),
)

PLUGINS["mcp-connector"] = cases(
    c("mcp-connector-1", None, "Welche MCP-Server sind konfiguriert und wie viele Tools lief jeder?", use("tool_describe", "tool_search")),
    c("mcp-connector-2", None, "Rufe über MCP das Tool 'get_current_time' des time-Servers auf.", use("tool_call")),
    c("mcp-connector-3", None, "Suche in den konfigurierten MCP-Servern ein Tool, das Dateien lesen kann.", use("tool_search")),
    c("mcp-connector-4", None, "Der Server unter http://127.0.0.1:9/mcp antwortet nicht — diagnose, was los ist.", has("erreicht", "Status", "Health")),
    c("mcp-connector-5", None, "Beschreibe das Tool-Set des filesystem-Servers, ohne es auszuführen.", use("tool_describe")),
    c("mcp-connector-6", None, "Wie füge ich einen neuen MCP-Server in Ephe hinzu? Nenne die Datei.", has("mcp.json")),
    c("mcp-connector-7", None, "Fasse den Status aller konfigurierten Server in einem Satz zusammen.", lacks(*ANTI_SLOP)),
)

PLUGINS["guide"] = cases(
    c("guide-1", "howto", "Wie starte ich Ephe zum ersten Mal? Schritte bis zum ersten Chat.", has("Schritt", "ephe start")),
    c("guide-2", "diagnose", "Die PWA lädt, aber der Chat antwortet nicht. Diagnose-Anleitung.", has("Engine", "health")),
    c("guide-3", "howto", "Wie binde ich einen OpenAI-kompatiblen Endpunkt als Engine ein?", has("engine.json", "openai")),
    c("guide-4", "diagnose", "Ollama läuft, aber das Modell lädt nicht. Schritt-für-Schritt.", has("ollama", "pull")),
    c("guide-5", None, "Erzeuge eine Markdown-Checkliste 'Desktop-Build prüfen' mit 6 Punkten.", art(".md")),
    c("guide-6", "howto", "Wie exportiere ich einen Monat als Bernstein? Nenne den Befehl.", has("ephe amber")),
    c("guide-7", None, "Schreibe die Kurzfassung 'Ephe in 5 Sätzen' — ausformuliert.", lacks(*ANTI_SLOP)),
)

PLUGINS["plugin-creator"] = cases(
    c("plugin-creator-1", "newplugin", "Lege das Plugin 'tafelplan' an: 1 Command 'plan', permission read.", use("write_file", "scaffold_project")),
    c("plugin-creator-2", "validateplugin", "Prüfe das Manifest plugins/documents/ephe-plugin.json gegen das Schema.", use("validate_json", "read_file")),
    c("plugin-creator-3", "newplugin", "Erzeuge ein Plugin-Gerüst mit genau 2 Slash-Commands.", art(".json")),
    c("plugin-creator-4", None, "Was gehört in permissions.tool_families und was bedeutet 'origin': 'first-party'?", has("first-party", "families")),
    c("plugin-creator-5", None, "Liste die Dateien, die ein minimales Ephe-Plugin braucht.", has("ephe-plugin.json", "icon.svg")),
    c("plugin-creator-6", None, "Warum lehnt Ephe ein Manifest mit Stub-Tools beim Laden ab?", lacks("weiß nicht")),
)

PLUGINS["skill-creator"] = cases(
    c("skill-creator-1", "newskill", "Lege das Skill-Pack 'botecho' an: SKILL.md mit 2 Few-Shot-Beispielen.", use("write_file", "skill_manage")),
    c("skill-creator-2", "grade", "Bewerte das Skill-Pack 'regex-helper' gegen seine Rubric.", has("Rubric", "Punkte", "pass")),
    c("skill-creator-3", "newskill", "Erzeuge die Dateien references/rubric.md und examples/golden.md für ein neues Pack.", art(".md")),
    c("skill-creator-4", None, "Was prüft scripts/audit_skills.py an einem Skill-Pack?", has("rubric", "golden")),
    c("skill-creator-5", None, "Nenne die 3 Pflichtdateien eines Skill-Packs und ihren Zweck.", has("SKILL.md", "rubric", "golden")),
    c("skill-creator-6", None, "Warum braucht jedes Skill-Pack ein Golden-Beispiel?", lacks("weiß nicht")),
)


def _matrix_text(cs: list[dict]) -> str:
    """The exact bytes golden.jsonl must hold for this case list."""
    return "".join(json.dumps(case, ensure_ascii=False) + "\n" for case in cs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare the tree against the matrix; write nothing, exit 1 on drift",
    )
    args = parser.parse_args(argv)

    drift: list[str] = []
    total = 0
    for name, cs in PLUGINS.items():
        pdir = ROOT / "plugins" / name / "prompts"
        golden = pdir / "golden.jsonl"
        rubric = pdir / "rubric.md"
        wanted = _matrix_text(cs)
        total += len(cs)

        if args.check:
            if not golden.is_file() or golden.read_text(encoding="utf-8") != wanted:
                drift.append(f"{name}: prompts/golden.jsonl is not what the matrix says")
            if not rubric.is_file():
                drift.append(f"{name}: prompts/rubric.md is missing")
            continue

        pdir.mkdir(parents=True, exist_ok=True)
        if not golden.is_file() or golden.read_text(encoding="utf-8") != wanted:
            golden.write_text(wanted, encoding="utf-8")
        # rubric.md is authored content: seeded when absent, never overwritten.
        if not rubric.is_file():
            rubric.write_text(RUBRIC_SEED.replace("{name}", name), encoding="utf-8")
            print(f"{name}: seeded prompts/rubric.md")
        print(f"{name}: {len(cs)} cases")

    if args.check:
        for line in drift:
            print(line, file=sys.stderr)
        state = "OK" if not drift else "DRIFT"
        print(f"gen_golden --check: {state} — {len(PLUGINS)} plugins, {total} cases")
        return 1 if drift else 0

    print(f"TOTAL: {total} cases over {len(PLUGINS)} plugins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
