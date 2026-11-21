"""What a person means, in the words of both product languages.

A search box that only matches package names answers the person who already
knows the package. Someone typing "Rechnung als PDF auslesen" is describing a
task; the entry that does that says "extract line items from invoices" and
shares not one word with the query. This vocabulary maps an intent key to the
words that express it, and the key becomes a searchable tag on every entry the
catalog generator put in the shelf.

The vocabulary is a word list, which is exactly what the gate pragma is for:
the German column below is the product's own language, not developer prose.
Every word is written in folded form, the same way a query is folded, so an
umlaut in the query and its ASCII spelling meet on one entry.
"""
from __future__ import annotations

import re
import unicodedata

#: (intent key, German words, English words). Matching is prefix-shaped, so a
#: plural or an inflection still lands on the same key.
INTENTS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("invoices", ("rechnung", "rechnungen", "beleg", "belege", "buchhaltung", "abrechnung"), ("invoice", "receipt", "billing", "accounting", "ledger")),  # language-gate: ignore
    ("calendar", ("termin", "termine", "kalender", "besprechung"), ("calendar", "schedule", "event", "meeting", "appointment")),
    ("mail", ("mail", "mails", "nachricht", "nachrichten", "postfach", "email"), ("mail", "email", "inbox", "message", "newsletter")),  # language-gate: ignore
    ("files", ("datei", "dateien", "dokument", "dokumente", "ordner", "ablage"), ("file", "folder", "document", "drive", "storage")),  # language-gate: ignore
    ("database", ("datenbank", "datenbanken", "abfrage", "tabelle"), ("database", "sql", "query", "postgres", "sqlite", "mysql")),  # language-gate: ignore
    ("web", ("webseite", "webseiten", "internet", "suche", "recherche"), ("web", "website", "search", "crawl", "scrape", "fetch")),  # language-gate: ignore
    ("code", ("code", "quelle", "quellcode", "programmieren", "repository"), ("code", "repository", "git", "github", "source", "programming")),  # language-gate: ignore
    ("browser", ("browser", "seite", "klicken", "formular"), ("browser", "click", "page", "form", "automation")),  # language-gate: ignore
    ("memory", ("gedachtnis", "wissen", "wissensbasis", "notiz", "notizen"), ("memory", "knowledge", "note", "notes", "graph")),  # language-gate: ignore
    ("finance", ("finanzen", "zahlung", "zahlungen", "konto", "preis", "preise"), ("finance", "payment", "bank", "price", "trading", "stock")),  # language-gate: ignore
    ("maps", ("karte", "karten", "route", "ort", "adresse", "reise"), ("map", "maps", "route", "location", "address", "travel", "geo")),  # language-gate: ignore
    ("weather", ("wetter", "vorhersage", "temperatur"), ("weather", "forecast", "temperature", "climate")),  # language-gate: ignore
    ("media", ("bild", "bilder", "video", "musik", "audio", "foto"), ("image", "video", "music", "audio", "photo", "media")),  # language-gate: ignore
    ("translation", ("ubersetzung", "ubersetzen", "sprache", "sprachen"), ("translation", "translate", "language", "locale")),  # language-gate: ignore
    ("tables", ("tabelle", "tabellen", "excel", "kalkulation"), ("spreadsheet", "excel", "csv", "sheet", "table")),  # language-gate: ignore
    ("team", ("team", "chat", "kanal", "kanalnachricht", "besprechung"), ("team", "chat", "channel", "slack", "discord", "meeting")),  # language-gate: ignore
    ("devops", ("betrieb", "bereitstellung", "server", "container", "wolke"), ("devops", "deploy", "deployment", "server", "container", "docker", "kubernetes", "cloud")),  # language-gate: ignore
    ("testing", ("test", "tests", "prufen", "prufung", "qualitat"), ("test", "testing", "qa", "check", "verify", "lint")),  # language-gate: ignore
    ("analytics", ("auswertung", "analyse", "statistik", "bericht", "kennzahl"), ("analytics", "analysis", "statistics", "report", "metric", "dashboard")),  # language-gate: ignore
    ("office", ("buro", "prasentation", "folie", "folien", "textverarbeitung"), ("office", "presentation", "slide", "slides", "word", "powerpoint")),  # language-gate: ignore
    ("security", ("sicherheit", "passwort", "passworter", "schlussel", "verschlusselung"), ("security", "password", "secret", "key", "encryption", "audit", "vulnerability")),  # language-gate: ignore
    ("home", ("zuhause", "haus", "licht", "heizung", "gerat"), ("home", "iot", "light", "thermostat", "device", "smart")),  # language-gate: ignore
    ("time", ("zeit", "uhr", "zeitzone", "datum"), ("time", "clock", "timezone", "date")),  # language-gate: ignore
)

_KEYS = tuple(intent[0] for intent in INTENTS)

#: A word may take an inflection and still mean the intent, and nothing more: "invoices"
#: and "Termine" land, "terminal" does not become a calendar entry through "Termin".
_INFLECTION = r"(?:s|es|ed|ing|e|en|er|n)?"


def fold(text: str) -> str:
    """Lowercase ASCII: "Prüfen" and "prufen" both become "prufen"."""
    normal = unicodedata.normalize("NFKD", str(text or ""))
    return normal.encode("ascii", "ignore").decode("ascii").lower()


def _words() -> dict[str, str]:
    table: dict[str, str] = {}
    for key, *columns in INTENTS:
        for column in columns:
            for word in column:
                table.setdefault(fold(word), key)
    return table


_WORDS = _words()


def tags_for(*parts: str) -> list[str]:
    """Every intent whose word appears in one of the parts, in a stable order."""
    haystack = fold(" ".join(str(part or "") for part in parts))
    found = set()
    for word, key in _WORDS.items():
        if re.search(rf"\b{re.escape(word)}{_INFLECTION}\b", haystack):
            found.add(key)
    return sorted(found)


def intents_in(query: str) -> list[str]:
    """The keys a typed query expresses, so its synonyms can ride along."""
    return tags_for(query)


def keys() -> tuple[str, ...]:
    return _KEYS
