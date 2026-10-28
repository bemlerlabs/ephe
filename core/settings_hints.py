"""
◑ Ephe – Descriptions for the deep settings (wave I3)
core/settings_hints.py

A field in the register cannot be explained without text, and text for a field
without a reader states a false depth: the user sees an explained control that
does nothing. That is why the same bar applies here as in
tests/test_settings_surface_is_real.py — only what the wiring actually feeds is
written down. A field is wired (an accessor call) and its text is added in the
same slice; a field without a reader stays without text.

Form: HINTS[key] = (german, english). The client picks by language, the way
`label`/`labelEn` already does; a locale key is not needed.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

from typing import Final

#: (de, en) per field key. The prerequisites are checked by
#: tests/test_settings_hints.py: field wired, both languages different,
#: no echo of the label, 24-240 characters, no claim without code.
HINTS: Final[dict[str, tuple[str, str]]] = {
    "shortcuts.global_enabled": (
        "Der einzige Schalter, der eine Taste außerhalb des Fensters belegt: "  # language-gate: ignore
        "Cmd+Shift+E auf macOS, sonst Ctrl+Shift+E, holt Ephe nach vorn. Aus ist "  # language-gate: ignore
        "die Vorgabe; belegt eine andere App die Kombination, schreibt Ephe den "  # language-gate: ignore
        "Wert zurück auf aus.",  # language-gate: ignore
        "The one switch that claims a key outside the window: Cmd+Shift+E on "
        "macOS, Ctrl+Shift+E elsewhere, brings Ephe to the front. Off is the "
        "default; if another app owns the chord, Ephe writes the value back to off.",
    ),
    "advanced.api_timeout": (
        "Zeitlimit für eine einzelne Nicht-Stream-Anfrage an die Engine "
        "(10-1800 Sekunden). Der Stream-Pfad hält eigene Schranken (read 300 s) "
        "und bleibt von diesem Feld unberührt.",
        "Time limit for one non-streaming request to the engine (10-1800 seconds). "
        "The streaming path keeps its own bounds (300 s read) and is untouched by "
        "this field.",
    ),
    "chat.details_mode": (
        "Vorgabe für einen fertigen Durchlauf: ausgefahren zeigt die ganze "
        "Zeitleiste mit Denkphase, Werkzeugen und Antwort, eingeklappt nur die "
        "Antwort. Ein Klick am Kopf überschreibt es für diesen einen Durchlauf.",
        "Starting state of a finished turn: expanded shows the whole timeline — "
        "reasoning, tools and answer; collapsed shows the answer. Clicking the head "
        "overrides it for that one turn.",
    ),
    "chat.allow_input_while_streaming": (
        "An: Enter stellt eine weitere Aufgabe in die Queue, solange Ephe "
        "antwortet. Aus: Das Eingabefeld ist während der Antwort nur lesbar und "
        "Enter tut nichts.",
        "On: Enter queues another task while Ephe answers. Off: the composer is "
        "read-only during a turn and Enter does nothing.",
    ),
    "chat.show_tool_count": (
        "Zeigt hinter einer Werkzeug-Gruppe, wie oft sie aufgerufen wurde — live "
        "als erledigt/total, fertig als Zahl. Aus blendet nur diesen Zähler aus, "
        "die Zeile selbst bleibt stehen.",
        "Shows after a tool group how often it was called — live as done/total, "
        "finished as a number. Off hides only that counter; the line stays.",
    ),
    "chat.expand_tool_calls": (
        "Die oberste Werkzeug-Gruppe eines Durchlaufs startet ausgeklappt statt "
        "eingeklappt. Ein eigener Klick gewinnt immer — die Vorgabe gilt bis zum "
        "ersten Klick auf eine Zeile.",
        "The top tool group of a turn starts open instead of closed. Your own click "
        "always wins — the default holds until the first click on a line.",
    ),
    "chat.show_thinking_loader": (
        "Der pulsierende „Denkt nach…“-Strich mit der tickenden Sekundenzahl, "
        "solange die Phase läuft. Aus lässt nur diese Zeile weg; der Reasoning-Text "
        "folgt aus „Denkprozess anzeigen“.",
        "The pulsing “thinking…” line with its ticking seconds while the phase runs. "
        "Off drops only that line; the reasoning text follows “Show reasoning”.",
    ),
    "chat.stream_idle_seconds": (
        "Bricht einen laufenden Stream ab, wenn der Server so lange kein Byte "
        "sendet (10-600 Sekunden). Gezählt wird echte Stille, nicht die "
        "Gesamtdauer — eine lange Antwort bleibt in Ruhe.",
        "Aborts a running stream when the server sends no byte for this long "
        "(10-600 seconds). Only silence counts, not total duration — a long answer "
        "is left alone.",
    ),
    "chat.duration_format": (
        "Wie lang etwas dauerte: knapp nach Ephe-Norm (4m 12s, maximal zwei "
        "Einheiten) oder als Uhrzeit (04:12, ab einer Stunde 1:04:12). Wirkt auf "
        "Dauer-Angaben in Agent-Panels, Speicher und Einstellungen.",
        "How long something took: compact per Ephe norm (4m 12s, at most two units) "
        "or as a clock (04:12, 1:04:12 past an hour). Applies to durations in the "
        "agent panels, memory and settings.",
    ),
    "chat.show_reasoning": (
        "Zeigt die Denkphase des Modells als eigene Zeile — im Chronologie-Plan an "
        "ihrer Position, in der Legacy-Antwort zuerst. Aus blendet nur die "
        "Reasoning-Texte aus, Werkzeuge und Antwort bleiben stehen.",
        "Shows the model's reasoning as its own line — at its position in the "
        "timeline, first in the legacy layout. Off hides only the reasoning text; "
        "tools and the answer stay.",
    ),
    "chat.tool_result_chars": (
        "Wie viele Zeichen ein Werkzeugergebnis höchstens haben darf, bevor es "
        "gekürzt in den Gesprächskontext geht (2.000-120.000). Niedrig spart Platz "
        "in langen Tool-Ketten, hoch lässt mehr von Datei- oder Shell-Ausgabe stehen.",
        "How many characters a tool result may carry before it is shortened into the "
        "conversation context (2,000-120,000). Low saves room in long tool chains, "
        "high keeps more of the file or shell output.",
    ),
    "chat.continue_attempts": (
        "So oft stößt Ephe eine Antwort nach, die einen Schritt ankündigt, aber nicht "
        "ausführt (0-5). Bei 0 bleibt der Abbruch stehen und es läuft keine "
        "zusätzliche Modell-Runde.",
        "How often Ephe nudges an answer that announces a step but never runs it "
        "(0-5). At 0 the stop stands and no extra model round is started.",
    ),
    "appearance.font_scale": (
        "Setzt die Schriftgröße der Oberfläche: alle sieben Stufen hängen an "
        "einer Variablen (14 px bei 100 Prozent), die Abstände in rem bleiben. "
        "Wirkt direkt nach dem Speichern.",
        "Sets the interface text size: all seven steps hang off one variable "
        "(14 px at 100 percent) while rem spacing stays. Applies right after saving.",
    ),
    "appearance.base_font_px": (
        "Legt die Grundstufe der Oberfläche fest (13, 14 oder 15 px). Die "  # language-gate: ignore
        "Prozent-Regler darüber skalieren diesen Wert; 15 px ist der Standard.",  # language-gate: ignore
        "Sets the interface's base step (13, 14 or 15 px). The percentage dials "
        "scale this value; 15 px is the default.",
    ),
    "appearance.chat_font_scale": (
        "Skaliert nur den Fließtext im Gespräch zwischen 80 und 150 Prozent; "  # language-gate: ignore
        "die übrige Oberfläche folgt weiterhin der allgemeinen Schriftgröße.",  # language-gate: ignore
        "Scales only the conversation text between 80 and 150 percent; the rest "
        "of the interface keeps following the general font scale.",
    ),
    "appearance.reading_width": (
        "Begrenzt die Breite des Gesprächs zwischen 480 und 1200 Pixeln; auf "  # language-gate: ignore
        "schmalen Fenstern bleibt die verfügbare Breite die Grenze.",  # language-gate: ignore
        "Caps the conversation width between 480 and 1200 pixels; on narrow "
        "windows the available width stays the limit.",
    ),
    "appearance.accent": (
        "Wählt den kuratierten Akzent für Marke und Live-Aktionen; Grund, "  # language-gate: ignore
        "Statusfarben und Auswahl bleiben unverändert.",  # language-gate: ignore
        "Chooses the curated accent for the mark and live actions; grounds, status "
        "tones and selection stay unchanged.",
    ),
    "appearance.companion_enabled": (
        "Zeigt den gewählten Begleiter im Startbildschirm und im aktiven Chat. "  # language-gate: ignore
        "Aus blendet ihn überall aus; Gestalt, Größe und Klangwahl bleiben "  # language-gate: ignore
        "gespeichert und wirken wieder beim nächsten Einschalten.",  # language-gate: ignore
        "Shows the chosen companion on the welcome screen and in the active chat. "
        "Off hides it everywhere while form, size and sound choices stay stored "
        "and return the next time it is switched on.",
    ),
    "appearance.companion_species": (
        "Wählt die Gestalt im Arbeitsbereich: die volle Feuergeist-Biene, den "  # language-gate: ignore
        "goldenen Funken mit Geist-Augen aus dem Film oder ein ruhiges Symbol. "  # language-gate: ignore
        "Die Biene trägt Flügel, Stirnflamme und Blick; der Funke bleibt eine Kugel.",  # language-gate: ignore
        "Chooses the form in the workspace: the full fire-spirit bee, the golden "
        "spark with ghost eyes from the film, or a calm emblem. The bee carries "
        "wings, the forehead flame and the gaze; the spark stays a single glow.",
    ),
    "appearance.companion_behavior": (
        "Bestimmt Ort und Bewegung: mitfliegend und klickbar am Composer, ruhig "  # language-gate: ignore
        "oben am Eingabefeld sitzend, oben in der Kopfzeile neben der Marke oder "  # language-gate: ignore
        "nur auf dem Startbildschirm sichtbar, sobald der erste Chat begonnen hat.",  # language-gate: ignore
        "Sets place and motion: flying and clickable at the composer, sitting "
        "calmly above the input, resting in the header next to the mark, or "
        "visible only on the welcome screen once the first chat has begun.",
    ),
    "appearance.companion_sound": (
        "Schaltet Flügelschwirren und den Kristallton der Funken an oder aus. "  # language-gate: ignore
        "Bewegungsreduktion des Systems und die Animations-Einstellung halten "  # language-gate: ignore
        "den Synthesizer zusätzlich still, unabhängig von diesem Schalter.",  # language-gate: ignore
        "Turns the wing flutter and the spark's crystal note on or off. The "
        "system's reduced-motion setting and the animations switch keep the "
        "synthesizer silent as well, whatever this switch says.",
    ),
    "appearance.companion_mode": (
        "Wählt die Arbeit des Begleiters: ruhig am Rand sitzen, Ziele auf der "  # language-gate: ignore
        "Oberfläche zeigen, oder als Co-Pilot sichere Aktionen nach einem "  # language-gate: ignore
        "sichtbaren Countdown selbst auslösen. Riskantere Aktionen bleiben "  # language-gate: ignore
        "immer beim Nutzer.",  # language-gate: ignore
        "Chooses the companion's work: sit quietly at the edge, point at targets "
        "on the surface, or act as a co-pilot that runs safe actions itself after "
        "a visible countdown. Riskier actions always stay with the user.",
    ),
    "appearance.companion_scale": (
        "Skaliert nur den Begleiter zwischen 70 und 140 Prozent; Typografie, "  # language-gate: ignore
        "Abstände und die Touch-Flächen der übrigen Bedienelemente bleiben "  # language-gate: ignore
        "unverändert.",  # language-gate: ignore
        "Scales the companion alone between 70 and 140 percent; type, spacing "
        "and the touch targets of every other control stay unchanged.",
    ),
    "appearance.companion_countdown_seconds": (
        "Wie lange der Begleiter seinen Vorschlag zeigt, bevor er ihn selbst "  # language-gate: ignore
        "ausführt (0 bis 10 Sekunden). Bei 0 führt er sofort aus.",  # language-gate: ignore
        "How long the companion shows its proposal before acting on it "
        "(0 to 10 seconds). At 0 it acts at once.",
    ),
    "appearance.animations_enabled": (
        "Übergänge und CSS-Animationen ein oder aus; aus legt auch den "
        "Feder-Einstieg der Nachrichten still. Die reduced-motion-Einstellung des "
        "Betriebssystems wirkt weiterhin zusätzlich.",
        "Turns transitions and CSS animations on or off; off also stills the spring "
        "entrance of messages. The operating system's reduced-motion keeps applying "
        "on top.",
    ),
    "appearance.show_timestamps": (
        "Zeigt die Uhrzeit unter jeder Nachricht. Aus blendet nur diese Zeile aus — "
        "Inhalt, Werkzeugspuren und Buttons bleiben stehen.",
        "Shows the time under each message. Off hides only that line; content, tool "
        "trail and buttons stay put.",
    ),
    "appearance.update_check": (
        "Fragt alle 30 Minuten anonym die GitHub-Releases ab und zeigt dann das "
        "Update-Banner. Aus: keine ausgehende Anfrage, kein Banner.",
        "Polls the GitHub releases anonymously every 30 minutes and then shows the "
        "update banner. Off: no outbound request, no banner.",
    ),
    "memory.capture_enabled": (
        "Nach jeder Antwort prüfen, ob sich das Paar aus Frage und Antwort lohnt, "
        "und es sonst ins Gedächtnis schreiben. Aus: es kommen keine neuen Merksätze "
        "dazu — Suchen, Injection und das memory-Werkzeug bleiben in Kraft.",
        "After each answer, decide whether the pair is worth keeping and store it. "
        "Off: no new facts are added — search, injection and the memory tool keep working.",
    ),
    "memory.capture_min_answer_chars": (
        "Unter dieser Länge gilt eine Antwort als zu dünn für einen Merksatz "
        "(20-2000 Zeichen). Höher filtert mehr weg, niedriger lässt mehr stehen; die "
        "Frage selbst braucht mindestens 8 Zeichen.",
        "Below this length an answer is too thin to become a memory (20-2000 "
        "characters). Higher filters more, lower keeps more; the question itself "
        "needs at least 8 characters.",
    ),
    "memory.dedupe_score_threshold": (
        "Ab welchem Aehnlichkeitswert (0,5 bis 1) ein gefundener Eintrag als Duplikat "
        "zählt und das neue Paar nicht eingetragen wird. Chroma liefert für "
        "identischen Text etwa 0,89, nie 1,0.",
        "From which similarity (0.5 to 1) a found entry counts as a duplicate and "
        "the new pair is not stored. Chroma returns about 0.89 for identical text, "
        "never 1.0.",
    ),
    "memory.inject_max_entries": (
        "Wie viele Einträge höchstens in den System-Prompt gehoben werden (1-50) — "
        "dieselbe Zahl begrenzt den Suchlauf der Injection. Mehr Wissen, mehr Tokens.",
        "At most how many entries are lifted into the system prompt (1-50) — the same "
        "number bounds injection's own search. More knowledge, more tokens.",
    ),
    "memory.inject_min_score": (
        "Unterhalb dieses Werts (0 bis 1) wird ein gefundener Eintrag nicht "
        "übernommen, weil er nur Tokens kosten würde. Höher hält die Injection "
        "knapper, niedriger lässt sie mehr durch.",
        "Below this value (0 to 1) a found entry is not injected, because it would "
        "only cost tokens. Higher keeps the block leaner, lower lets more through.",
    ),
    "memory.embedder": (
        "Bestimmt das Modell der Vektorsuche: EmbeddingGemma 2 liefert 768 Werte, "  # language-gate: ignore (shipped product string, as the sibling Memory hints)
        "von denen Ephe die ersten 256 speichert; all-MiniLM-L6-v2 bleibt bei 384. "  # language-gate: ignore (shipped product string)
        "Ein Wechsel gilt ab dem nächsten Eintrag.",  # language-gate: ignore (shipped product string)
        "Chooses the vector-search model: EmbeddingGemma 2 emits 768 values, of which "
        "Ephe stores the leading 256, while all-MiniLM-L6-v2 stays at 384. A switch "
        "applies from the next stored entry on.",
    ),
    "memory.embedder_allow_download": (
        "Erlaubt einen einmaligen Bezug der EmbeddingGemma-Gewichte (540 MB) von "  # language-gate: ignore (shipped product string)
        "huggingface.co ins Geräteverzeichnis; ohne diese Erlaubnis bleibt die "  # language-gate: ignore (shipped product string)
        "Vektorsuche bei all-MiniLM-L6-v2.",  # language-gate: ignore (shipped product string)
        "Allows a one-time fetch of the EmbeddingGemma weights (540 MB) from "
        "huggingface.co into the device folder; without that permission vector "
        "search stays on all-MiniLM-L6-v2.",
    ),
    "ephemera.idle_ttl_minutes": (
        "Wie lange eine Zelle ohne jeden Lauf überlebt; der nächste Zugriff räumt "
        "sie dann weg, und ihr Namespace ist Geschichte. Eine Zelle, die gebraucht "
        "wird, bleibt so lange, wie sie gebraucht wird.",
        "How long a cell survives without a run; the next access then discards it "
        "and its namespace is gone. A cell that is used stays as long as it is used.",
    ),
    "ephemera.evaporate_on_delete": (
        "Löscht eine Sitzung auch sofort ihre Arbeitsmappe, statt auf die "
        "Idle-Grenze oben zu warten. Dateien, die ein Lauf in den Ausgabepfad "
        "geschrieben hat, bleiben in beiden Fällen liegen — kein Schalter löscht sie.",
        "Whether deleting a session also frees its work directory at once instead of "
        "waiting for the idle limit above. Files a run wrote to the output folder stay "
        "either way — no switch deletes those.",
    ),
    "cron.misfire_grace_minutes": (
        "Wie lange ein Termin nach seiner Zeit noch angetreten wird, wenn Ephe "
        "gerade nicht lief (0-1440 Minuten). 0 holt nichts nach; darüber hinaus "
        "verfällt der Lauf ersatzlos.",
        "How long a slot may still start after its time when Ephe was not running "
        "(0-1440 minutes). 0 never catches up; past it the run lapses without "
        "replacement.",
    ),
    "cron.history_keep": (
        "Wie viele Läufe gespeichert bleiben — im Arbeitsspeicher und in "
        "schedule_results.json (10-500). Ältere fallen zuerst weg; Verläufe, die "
        "du brauchst, vorher exportieren.",
        "How many runs are kept — in memory and in schedule_results.json "
        "(10-500). Oldest go first; export anything you need before it drops.",
    ),
    "cron.history_rows": (
        "Wie viele Läufe die Liste unter einem Zeitplan zeigt (5-100). Geändert "
        "nichts an dem, was gespeichert ist — nur an dem, was zu sehen ist.",
        "How many runs the list under a schedule shows (5-100). Changes nothing "
        "about what is stored — only what is visible.",
    ),
    "cron.max_parallel_jobs": (
        "Wie viele Läufe desselben Jobs gleichzeitig laufen dürfen (1-10). 1, der "
        "Default: ein Lauf wartet, bis der vorherige geendet hat — schnell "
        "aufeinanderfolgende Termine fallen dann nicht weg, sie stauen sich.",
        "How many runs of the same job may overlap (1-10). At 1, the default, a "
        "run waits for the previous one to end — closely spaced slots queue "
        "instead of being dropped.",
    ),
    "hooks.enabled": (
        "Aus führt keinen der Befehle aus hooks.json mehr aus — kein "
        "Kindprozess vor oder nach einem Werkzeugaufruf. Die Datei bleibt "
        "unverändert, Werkzeuge und Antworten laufen unverdrossen durch.",
        "Off runs none of the commands in hooks.json — no subprocess before or "
        "after a tool call. The file stays as it is; tools and answers keep "
        "running unchanged.",
    ),
    "plugins.plugin_autorun": (
        "Gilt nur beim Installieren: ein frisches Marketplace-Plugin landet "
        "aktiviert statt deaktiviert in der Registry. Bestehende Einträge "
        "bleiben unverändert.",
        "Applies at install time only: a new marketplace plugin lands enabled "
        "instead of disabled in the registry. Existing entries stay as they are.",
    ),
    "plugins.plugin_signature_check": (
        "Prüft beim Aktivieren, ob der Plugin-Inhalt noch zur gespeicherten "
        "Signatur passt; bei Abweichung blockiert die Aktivierung mit 409 und "
        "Audit-Eintrag. Die Installation prüft unabhängig davon.",
        "Checks on enable whether the plugin content still matches its stored "
        "signature; on drift the activation fails with 409 and an audit entry. "
        "Installation is checked independently.",
    ),
}


def hints_for(key: str) -> tuple[str, str] | None:
    """(de, en) for a wired field, otherwise None."""
    return HINTS.get(key)

#: (de, en) per key of the generation block (engine.json). Not in the
#: register — the inference parameters have their own map in the settings
#: surface. The text says what the value does inside the request: all values
#: are read (I2-5 for temperatur/top_p/max_tokens, I3-8 for the others).
GENERATION_HINTS: Final[dict[str, tuple[str, str]]] = {
    "temperature": (
        "Wie zufällig die Wortwahl wird: 0 hält die Engine am wahrscheinlichsten "
        "Token fest, höhere Werte variieren mehr. Der Wert geht in jede Anfrage; "
        "0.0 ist hier bewusste Vorgabe, weil Messläufe Wiederholbarkeit brauchen.",
        "How random the wording gets: 0 pins the engine to the most likely token, "
        "higher values vary more. Sent with every request; 0.0 is the deliberate "
        "default here because eval runs need repeatability.",
    ),
    "top_p": (
        "Kernsampling: lässt nur die wahrscheinlichste Textmasse bis zu diesem Wert "
        "zu. Leer entscheidet die Engine selbst, gesetzt geht der Wert in jede "
        "Anfrage.",
        "Nucleus sampling: admits only the most probable mass up to this value. "
        "Empty lets the engine decide; set, it ships with every request.",
    ),
    "max_tokens": (
        "Höchstzahl Tokens pro Antwort. Leer entscheidet die Engine; ein gesetzter "
        "Wert kappt die Antwortlänge in jeder Anfrage.",
        "Upper bound of tokens per answer. Empty lets the engine decide; a set "
        "value caps every response.",
    ),
    "tool_budget": (
        "Wie viele Werkzeug-Aufrufe ein Durchlauf höchstens tun darf (1–40). Er "
        "stoppt die Agent-Schleife, nicht das Modell. Ohne Einstellung gilt der "
        "Klassen-Default: 25 Runden, /ephe bis an den Cap von 40.",
        "How many tool calls one turn may make at most (1-40). It stops the agent "
        "loop, not the model. Unset keeps the class default: 25 rounds, /ephe up to "
        "the cap of 40.",
    ),
    "context_window": (
        "Größe des Kontextfensters, das Ephe für dieses Modell annimmt: begrenzt, "
        "wie viel Verlauf und Werkzeugschrift in die Anfrage passen. Ohne "
        "Einstellung löst die Modelltabelle auf.",
        "Context window Ephe assumes for this model: caps how much history and tool "
        "text fit into the request. Unset falls back to the model table.",
    ),
    "memory_max_entries": (
        "Obergrenze für gespeicherte Gedächtniseinträge. Darüber räumt das "
        "Auto-Memory die am wenigsten wertvollen selbstgelernten ein, höchstens 50 "
        "pro Lauf.",
        "Ceiling for stored memory entries. Above it, auto-memory evicts the least "
        "valuable self-learned ones, at most 50 per pass.",
    ),
    "swarm_max_parallel": (
        "Wie viele Swarm-Agenten einer Welle gleichzeitig laufen dürfen (1 = "  # language-gate: ignore (German UI hint — the product's German settings surface)
        "jeder nacheinander). Der Rest wartet in der Warteschlange, bis ein "  # language-gate: ignore (German UI hint — the product's German settings surface)
        "Platz frei wird.",  # language-gate: ignore (German UI hint — the product's German settings surface)
        "How many swarm agents of one wave may run at the same time (1 = one "
        "after another). The rest queue up until a slot frees.",
    ),
}


def generation_hint(key: str) -> tuple[str, str] | None:
    """(de, en) for a generation key, otherwise None."""
    return GENERATION_HINTS.get(key)
