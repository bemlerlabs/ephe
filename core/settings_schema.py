"""
◑ Ephe – The deep register of settings that are actually read (wave 6, I3-6)
core/settings_schema.py

A flat field register (SCHEMA) plus the section breakdown (SECTIONS) as the
single source of truth for the PWA's deep settings. Every field carries:
- type: 'bool' | 'number' | 'select' | 'text'
- default: the starting value without a user entry
- number: min/max (hard bounds), select: options (allowed values)

The PWA renders the sections generically from this register; the explanation of
a field comes from core/settings_hints.py. Both rules hold together: a field
without a consumer reached through the accessor wiring (deep_bool/deep_number/
deep_select/deep_value) does not belong here — and neither does a field with a
reader but no text. That is re-checked in
tests/test_settings_surface_is_real.py and tests/test_settings_hints.py.

Persistence: settings.json in the device folder (EPHE_CONFIG_DIR, otherwise
~/.ephe), atomic write via .tmp + replace. Fail-soft: missing/broken => {}.

Separation: the inference parameters (temperature/top_p/max_tokens/tool_budget/
context_window/memory_max_entries) stay in the `generation` block of
engine.json with their own settings section; provider, model and endpoint belong
to the engine card. Whoever moves in here needs a reader.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.settings_hints import HINTS

SCHEMA_VERSION = 1


# Field register (key: '<section>.<field>')

# Field register (key: '<section>.<field>')
#
# I3-6: the register only carries what is actually read. Before this 80 fields
# stood here while a consumer calls exactly nine of them — the rest was a false
# claim about how controllable the app is (tests/test_settings_surface_is_real.py
# pins it down: new field without a reader = red). Struck means 'not proven',
# not 'rejected': every field that gets a real reader may come
# back — with its description text in the same slice.

SCHEMA: dict[str, dict[str, Any]] = {
    # Chat / behaviour
    "chat.show_reasoning": {"type": "bool", "default": True,
                            "label": "Denkprozess anzeigen", "labelEn": "Show reasoning"},
    "chat.details_mode": {"type": "select", "default": "expanded",
                          "options": ["expanded", "collapsed"],
                          "optionLabels": {"expanded": ["Ausgeklappt", "Expanded"],
                                           "collapsed": ["Eingeklappt", "Collapsed"]},
                          "label": "Antwortprozess", "labelEn": "Response process"},
    # I6-3: the behaviour fields. The reader is the core (core/chat.py) or the
    # surface itself (app/src/lib/stream.ts, duration.ts, ChatInput,
    # MessageBubble, ThinkingBlock) — always the full key through the
    # accessor wiring, otherwise tests/test_settings_surface_is_real.py turns red.
    "chat.allow_input_while_streaming": {"type": "bool", "default": True,
                                         "label": "Eingabe während der Antwort",
                                         "labelEn": "Typing during the answer"},
    "chat.show_tool_count": {"type": "bool", "default": True,
                             "label": "Anzahl der Werkzeug-Aufrufe",
                             "labelEn": "Tool-call count"},
    "chat.expand_tool_calls": {"type": "bool", "default": False,
                               "label": "Werkzeug-Gruppen aufklappen",
                               "labelEn": "Expand tool groups"},
    "chat.show_thinking_loader": {"type": "bool", "default": True,
                                  "label": "Loader der Denkphase",
                                  "labelEn": "Thinking loader"},
    "chat.stream_idle_seconds": {"type": "number", "default": 60, "min": 10, "max": 600,
                                 "label": "Stream-Abbruch nach Stille (s)",
                                 "labelEn": "Abort stream after silence (s)"},
    "chat.duration_format": {"type": "select", "default": "compact",
                             "options": ["compact", "clock"],
                             "optionLabels": {"compact": ["Knapp (4m 12s)", "Compact (4m 12s)"],
                                              "clock": ["Uhrzeit (04:12)", "Clock (04:12)"]},
                             "label": "Dauer-Format", "labelEn": "Duration format"},
    # I6-3: the two core fields that before this only existed as a constant
    # (core/chat.py). The reader is the core itself, not the surface.
    "chat.tool_result_chars": {"type": "number", "default": 32000, "min": 2000, "max": 120000,
                               "label": "Werkzeug-Ausgabe begrenzen (Zeichen)",
                               "labelEn": "Cap tool output (characters)"},
    "chat.continue_attempts": {"type": "number", "default": 2, "min": 0, "max": 5,
                               "label": "Abgebrochene Pläne weiterführen (Versuche)",
                               "labelEn": "Continue aborted plans (attempts)"},
    # Wave 2 (B1): the user's own instruction layer. `core/chat_prompt.py` reads it as
    # a provenance-marked stage of its own; the editor stops at `max_chars`, and the
    # prompt marks a truncation if a stored value ever exceeds it.
    "chat.custom_instructions": {"type": "text", "default": "", "max_chars": 4000,
                                 "multiline": True,
                                 "label": "Eigene Anweisungen",
                                 "labelEn": "Custom instructions"},
    # Appearance
    "appearance.font_scale": {"type": "number", "default": 100, "min": 80, "max": 150,
                              "label": "Schriftgröße (%)", "labelEn": "Font scale (%)"},
    "appearance.chat_font_scale": {"type": "number", "default": 100, "min": 80, "max": 150,
                                   "label": "Schriftgröße im Gespräch (%)",
                                   "labelEn": "Chat font scale (%)"},
    "appearance.reading_width": {"type": "number", "default": 768, "min": 480, "max": 1200,
                                 "label": "Lesebreite (px)", "labelEn": "Reading width (px)"},
    "appearance.accent": {"type": "select", "default": "ember",
                          "options": ["ember", "indigo", "plum", "mono"],
                          "optionLabels": {
                              "ember": ["Ember (Rot)", "Ember (red)"],
                              "indigo": ["Indigoblau", "Indigo"],
                              "plum": ["Pflaume", "Plum"],
                              "mono": ["Monochrom", "Mono"],
                          },
                          "label": "Akzent", "labelEn": "Accent"},
    "appearance.animations_enabled": {"type": "bool", "default": True,
                                      "label": "Animationen aktiv", "labelEn": "Animations enabled"},
    # Desktop-only opt-in. The reader is the shell bridge (app/src/lib/globalShortcut.ts)
    # called from the shortcuts section; a failed registration writes the value back off.
    "shortcuts.global_enabled": {"type": "bool", "default": False,
                                 "label": "Globales Kürzel (Desktop)",
                                 "labelEn": "Global shortcut (desktop)"},
    # The companion (owner order 2026-10-17): the bee outlives the onboarding.
    # Every field is read by WorkspaceCompanion / WelcomeEmptyState / spiritAudio.
    # QD-005: default False — a fresh install stays calm until the user summons it.
    "appearance.companion_enabled": {"type": "bool", "default": False,
                                     "label": "Begleiter (Pet) im Arbeitsbereich",
                                     "labelEn": "Workspace companion (pet)"},
    "appearance.companion_species": {"type": "select", "default": "fire_bee",
                                     "options": ["fire_bee", "ember_spark", "minimal"],
                                     "optionLabels": {
                                         "fire_bee": ["Ephe Feuergeist-Biene (3D)", "Ephe Fire-Spirit Bee (3D)"],
                                         "ember_spark": ["Goldener Feuerfunke", "Golden fire spark"],
                                         "minimal": ["Dezentes Symbol", "Minimal emblem"],
                                     },
                                     "label": "Begleiter-Gestalt", "labelEn": "Companion form"},
    "appearance.companion_behavior": {"type": "select", "default": "interactive",
                                      "options": ["interactive", "perch", "header", "welcome_only"],
                                      "optionLabels": {
                                          "interactive": ["Lebendig mitfliegend & interaktiv", "Interactive & flying"],
                                          "perch": ["Ruhig am Eingabefeld sitzend", "Calm perch on composer"],
                                          "header": ["Ruhig in der Kopfzeile neben der Marke", "Calm in the header next to the mark"],
                                          "welcome_only": ["Nur auf dem Startbildschirm", "Welcome screen only"],
                                      },
                                      "label": "Begleiter-Verhalten", "labelEn": "Companion behaviour"},
    "appearance.companion_sound": {"type": "bool", "default": True,
                                   "label": "Begleiter- & Funken-Klänge",
                                   "labelEn": "Companion & spark sounds"},
    # QD-005: the co-pilot work mode. perch watches nothing, scout points,
    # copilot acts on safe targets after the visible countdown.
    "appearance.companion_mode": {"type": "select", "default": "copilot",
                                  "options": ["perch", "scout", "copilot"],
                                  "optionLabels": {
                                      "perch": ["Ruhiger Sitzplatz ohne Eingriffe", "Calm perch, no interference"],  # language-gate: ignore
                                      "scout": ["Zeigt Empfehlungen, klickt nie", "Points at targets, never clicks"],
                                      "copilot": ["Co-Pilot mit Rückfrage-Countdown", "Co-pilot with a visible countdown"],  # language-gate: ignore
                                  },
                                  "label": "Begleiter-Modus", "labelEn": "Companion mode"},
    "appearance.companion_scale": {"type": "number", "default": 100, "min": 70, "max": 140,
                                   "label": "Begleiter-Größe (%)", "labelEn": "Companion size (%)"},
    # I3-4: default True — the time always stood under the message. A
    # switch whose default invents the shipped behaviour would be a
    # regressive button (off = something disappears that nobody ever ordered).
    "appearance.show_timestamps": {"type": "bool", "default": True,
                                   "label": "Zeitstempel anzeigen", "labelEn": "Show timestamps"},
    "appearance.update_check": {"type": "bool", "default": True,
                                "label": "Nach Updates suchen (anonym)", "labelEn": "Check for updates (anonymous)"},
    # Advanced
    "advanced.api_timeout": {"type": "number", "default": 120, "min": 10, "max": 1800,
                             "label": "API-Zeitüberschreitung (s)", "labelEn": "API timeout (s)"},
    # Plugins (catalog policy)
    "plugins.plugin_autorun": {"type": "bool", "default": False,
                               "label": "Plugins automatisch starten", "labelEn": "Autorun plugins"},
    "plugins.plugin_signature_check": {"type": "bool", "default": True,
                                       "label": "Signaturprüfung erzwingen", "labelEn": "Enforce signature check"},
    # O-10 (2026-10-21): the emergency brake on the switch surface. The label
    # text lives in the app locale under this key; the register carries no German.
    "plugins.plugin_lifecycle_read_only": {
        "type": "bool",
        "default": False,
        "label": "Plugin switches read-only",
        "labelEn": "Plugin switches read-only",
        "labelKey": "settings.pluginReadOnly",
        "hintKey": "settings.pluginReadOnlyHint",
    },
    # Memory (I6-7 — own area; the readers are core/auto_memory.py and
    # core/memory.py). The size field stays in the generation block of
    # engine.json (memory_max_entries) — a second one here would be a second number
    # for the same ceiling.
    "memory.capture_enabled": {"type": "bool", "default": True,
                                "label": "Merksätze aus Gesprächen bilden",
                                "labelEn": "Learn from conversations"},
    "memory.capture_min_answer_chars": {"type": "number", "default": 120, "min": 20, "max": 2000,
                                        "label": "Antwort lang genug (Zeichen)",
                                        "labelEn": "Minimum answer length (chars)"},
    "memory.dedupe_score_threshold": {"type": "number", "default": 0.85, "min": 0.5, "max": 1.0,
                                      "label": "Duplikat ab (Ahnlichkeit)",
                                      "labelEn": "Duplicate above (similarity)"},
    "memory.inject_max_entries": {"type": "number", "default": 10, "min": 1, "max": 50,
                                  "label": "Gedächtnis im Kontext (Einträge)",
                                  "labelEn": "Memory in context (entries)"},
    "memory.inject_min_score": {"type": "number", "default": 0.3, "min": 0.0, "max": 1.0,
                                "label": "Übernommen ab (Ähnlichkeit)",
                                "labelEn": "Injected above (similarity)"},
    # The two vectorizer fields (the readers are core/memory_embed.py for the
    # choice and core/memory_embed_gemma.py for the consent). EmbeddingGemma is the
    # default; a machine that has not fetched its 540 MB keeps MiniLM, and the
    # label written into chunks.embedding_model follows whichever one loads.
    "memory.embedder": {"type": "select", "default": "embeddinggemma-2",
                        "options": ["embeddinggemma-2", "all-MiniLM-L6-v2"],
                        "optionLabels": {"embeddinggemma-2": ["EmbeddingGemma 2 (empfohlen)",
                                                             "EmbeddingGemma 2 (recommended)"],
                                         "all-MiniLM-L6-v2": ["all-MiniLM-L6-v2 (klein, lokal)",
                                                             "all-MiniLM-L6-v2 (small, local)"]},
                        "label": "Embedding-Modell", "labelEn": "Embedding model"},
    "memory.embedder_allow_download": {"type": "bool", "default": False,
                                       "label": "Embedding-Modell herunterladen erlauben",
                                       "labelEn": "Allow embedding-model download"},
    # Schedule (I7-3 — own area, the reader is core/scheduler.py)
    "cron.misfire_grace_minutes": {"type": "number", "default": 60, "min": 0, "max": 1440,
                                   "label": "Versäumten Lauf nachholen (Minuten)",
                                   "labelEn": "Catch up a missed run (minutes)"},
    "cron.history_keep": {"type": "number", "default": 50, "min": 10, "max": 500,
                          "label": "Verlauf behalten (Läufe)",
                          "labelEn": "Runs to keep"},
    "cron.history_rows": {"type": "number", "default": 20, "min": 5, "max": 100,
                          "label": "Verlauf zeigen (Zeilen)",
                          "labelEn": "Runs to show"},
    "cron.max_parallel_jobs": {"type": "number", "default": 1, "min": 1, "max": 10,
                               "label": "Gleichzeitige Läufe je Job",
                               "labelEn": "Concurrent runs per job"},
    # Ephemerality (R1 — the area where the brand's promise is regulated.
    # The readers are core/ephemeral_cell.py itself and the delete path in
    # server/routes/sessions.py; a field without this wiring does not exist here.)
    "ephemera.idle_ttl_minutes": {"type": "number", "default": 30, "min": 5, "max": 240,
                                  "label": "Ungenutzte Zelle aufgeben (Minuten)",
                                  "labelEn": "Discard an idle cell (minutes)"},
    "ephemera.evaporate_on_delete": {"type": "bool", "default": False,
                                     "label": "Sitzung sofort verdunsten",
                                     "labelEn": "Evaporate session on delete"},
    # Hooks (I6-4 — own area, the reader is core/user_hooks.py itself)
    "hooks.enabled": {"type": "bool", "default": True,
                      "label": "Hooks ausführen", "labelEn": "Run hooks"},
}

# Section breakdown (order = render order in the PWA).
SECTIONS: list[dict[str, Any]] = [
    {"key": section, "fields": [k for k in SCHEMA if k.startswith(f"{section}.")]}
    for section in ("chat", "appearance", "shortcuts", "advanced", "plugins", "memory",
                    "ephemera", "cron", "hooks")
]


# Normalisation (type-strict, with edge and centre of the bounds)

def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "1", "yes", "on", "ja"):
            return True
        if low in ("false", "0", "no", "off", "nein", ""):
            return False
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _coerce_number(value: Any, meta: dict[str, Any]) -> int | float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return meta["default"]
    num = max(meta["min"], min(meta["max"], num))
    if isinstance(meta["default"], int) and float(num).is_integer():
        return int(num)
    return num


def normalize_field(field_key: str, value: Any) -> Any:
    """Normalise a value against the register; invalid values -> the default."""
    meta = SCHEMA.get(field_key)
    if meta is None:
        return None
    kind = meta["type"]
    if kind == "bool":
        return _coerce_bool(value)
    if kind == "number":
        return _coerce_number(value, meta)
    if kind == "select":
        return value if value in meta["options"] else meta["default"]
    # Text is not clamped here: the editor stops at `max_chars`, and a value that
    # arrived another way is truncated by its reader WITH a marker. A silent cut at
    # this layer would be the one loss nobody could see.
    return str(value)


def normalize_deep(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Raw payload (section dicts) → normalised section list.

    Unknown sections and fields are dropped; a touched section becomes
    complete (default < user value) so the view after every POST
    has the same shape as after GET. Known fields are clamped type-strictly
    (number: bounds, select: options).
    """
    out: dict[str, dict[str, Any]] = {}
    section_keys = {s["key"] for s in SECTIONS}
    fields_by_section = {s["key"]: s["fields"] for s in SECTIONS}
    for sec_key, fields in (payload or {}).items():
        if sec_key not in section_keys or not isinstance(fields, dict):
            continue
        # Default fill of the touched section, then the user values on top.
        sec: dict[str, Any] = {
            k: SCHEMA[k]["default"] for k in fields_by_section.get(sec_key, [])
        }
        for field_key, value in fields.items():
            if field_key not in SCHEMA:
                continue
            norm = normalize_field(field_key, value)
            if norm is not None:
                sec[field_key] = norm
        out[sec_key] = sec
    return out


def deep_defaults() -> dict[str, dict[str, Any]]:
    """Only the defaults — the base for merging with the user values."""
    out: dict[str, dict[str, Any]] = {}
    for section in SECTIONS:
        sec = {k: SCHEMA[k]["default"] for k in section["fields"]}
        if sec:
            out[section["key"]] = sec
    return out


# Persistence (settings.json in the device folder)

def settings_path() -> Path:
    return Path(os.environ.get("EPHE_CONFIG_DIR") or str(Path.home() / ".ephe")) / "settings.json"


def load_deep_settings() -> dict[str, dict[str, Any]]:
    """Stored deep settings; missing/broken -> {} (fail-soft)."""
    try:
        raw = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict) or not isinstance(raw.get("sections"), dict):
        return {}
    return {k: v for k, v in raw["sections"].items() if isinstance(v, dict)}


def save_deep_settings(payload: dict[str, Any]) -> bool:
    """Write atomically (tmp + replace). True on success."""
    target = settings_path()
    body = {"version": SCHEMA_VERSION, "sections": payload}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
    except OSError:
        return False
    return True


# Wiring: the type-strict access used by consumers
#
# Before I3 every consumer read load_deep_settings() on its own and applied the
# default by hand — three copies of the same logic, the rest of the register
# without a single reader. A consumer now calls deep_bool/deep_number/
# deep_value with the full field key; an unknown
# key or a type mistake raises instead of quietly returning None. The
# call is at the same time the proof that tests/test_settings_surface_is_real.py
# demands: only a field with an accessor call is a control.
#
# Deliberately without a cache: the file is small, every access sits next to a
# model or tool call, and a cache blinds every tester who
# patches load_deep_settings — a silent read error would cost more than a read.

def _merged_values() -> dict[str, dict[str, Any]]:
    return normalize_deep(load_deep_settings())


def _require(key: str, kind: str) -> None:
    meta = SCHEMA.get(key)
    if meta is None:
        raise KeyError(f"unbekanntes Deep-Feld: {key}")
    if meta["type"] != kind:
        raise TypeError(f"{key} ist {meta['type']}, nicht {kind}")


def deep_value(key: str, default: Any = None) -> Any:
    """Set, clamped value; otherwise the register default (`default`
    overrides that one for the empty case)."""
    if key not in SCHEMA:
        raise KeyError(f"unbekanntes Deep-Feld: {key}")
    section = key.split(".", 1)[0]
    value = _merged_values().get(section, {}).get(key)
    if value is None:
        return SCHEMA[key]["default"] if default is None else default
    return value


def deep_bool(key: str) -> bool:
    _require(key, "bool")
    return bool(deep_value(key))


def deep_number(key: str) -> int | float:
    _require(key, "number")
    return deep_value(key)


def deep_select(key: str) -> str:
    _require(key, "select")
    return deep_value(key)


# View for the API (GET /api/settings -> 'deep')

def deep_view() -> list[dict[str, Any]]:
    """Section list with field entries (key/type/default/value + bounds).

    Merge: default < stored value. The values come from
    load_deep_settings(); missing entries stay at the default.
    `hint`/`hintEn` come from core/settings_hints.py and appear only
    where a consumer actually reads the value — text without a reader is decoration.
    """
    saved = load_deep_settings()
    merged = normalize_deep(saved)
    out: list[dict[str, Any]] = []
    for section in SECTIONS:
        sec_key = section["key"]
        fields: list[dict[str, Any]] = []
        for field_key in section["fields"]:
            meta = SCHEMA[field_key]
            entry: dict[str, Any] = {
                "key": field_key,
                "type": meta["type"],
                "label": meta.get("label", field_key),
                "labelEn": meta.get("labelEn", field_key),
                "default": meta["default"],
                "value": merged.get(sec_key, {}).get(field_key, meta["default"]),
            }
            if "labelKey" in meta:
                entry["labelKey"] = meta["labelKey"]
            if "hintKey" in meta:
                entry["hintKey"] = meta["hintKey"]
            pair = HINTS.get(field_key)
            if pair is not None:
                entry["hint"], entry["hintEn"] = pair
            if meta["type"] == "number":
                entry["min"] = meta["min"]
                entry["max"] = meta["max"]
                # I3-3: step derived from the field type, not typed per field —
                # whole numbers jump by 1, decimals with a fine hand. A fourth
                # bound in the schema would be another source to keep in sync.
                entry["step"] = 1 if isinstance(meta["default"], int) else 0.01
            if meta["type"] == "text" and "max_chars" in meta:
                entry["maxChars"] = meta["max_chars"]
                entry["multiline"] = bool(meta.get("multiline"))
            if meta["type"] == "select":
                entry["options"] = list(meta["options"])
                # I6-3: how the selection values are displayed. The value itself stays
                # the identifier (validation, persistence); the text comes from the
                # register so the German interface shows no English word
                # (and vice versa).
                labels = meta.get("optionLabels")
                if labels:
                    entry["optionLabels"] = [
                        {"value": v, "label": labels[v][0], "labelEn": labels[v][1]}
                        for v in meta["options"]
                    ]
            fields.append(entry)
        out.append({"key": sec_key, "fields": fields})
    return out


class UnknownKey(ValueError):
    """A section or field key the register does not know (POST answers 400)."""


def validate_sections(
    payload: dict[str, Any], *, stored: dict[str, dict[str, Any]] | None = None
) -> dict[str, dict[str, Any]]:
    """Hard validation for POST: range violation/option → ValueError.

    Unlike normalize_deep (which clamps) this aborts: a value
    outside the bounds is a 422 value, not a clamping candidate.
    A write is a merge over `stored`: a field the caller did not send keeps
    its value, and a key the register does not know is refused instead of
    ignored — silently dropping either one lost stored settings.
    """
    section_keys = {s["key"] for s in SECTIONS}
    result: dict[str, dict[str, Any]] = {}
    for sec_key, fields in (payload or {}).items():
        if sec_key not in section_keys:
            raise UnknownKey(f"section {sec_key}: unknown")
        if not isinstance(fields, dict):
            raise ValueError(f"section {sec_key}: object expected")
        sec: dict[str, Any] = dict((stored or {}).get(sec_key) or {})
        for field_key, value in fields.items():
            meta = SCHEMA.get(field_key)
            if meta is None:
                raise UnknownKey(f"{field_key}: unknown")
            if meta["type"] == "number":
                try:
                    num = float(value)
                except (TypeError, ValueError):
                    raise ValueError(f"{field_key}: number expected") from None
                if not (meta["min"] <= num <= meta["max"]):
                    raise ValueError(
                        f"{field_key}: {num} ausserhalb [{meta['min']}, {meta['max']}]"
                    )
                sec[field_key] = int(num) if float(num).is_integer() else num
            elif meta["type"] == "select":
                if value not in meta["options"]:
                    raise ValueError(f"{field_key}: {value!r} nicht in {meta['options']}")
                sec[field_key] = value
            elif meta["type"] == "bool":
                sec[field_key] = _coerce_bool(value)
            else:
                sec[field_key] = str(value)
        result[sec_key] = sec
    return result
