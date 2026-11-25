"""The terminal prints the thinking state in the language the installation was set to.

Three facts hold each other up, so they are checked together:

1. The saved language lives in the deep register (`appearance.language`), the
   environment overrides it for one process, and the register's default is the floor.
   `POST /api/settings` writes the register; the server process's environment, which
   used to be the only place the choice lived, stays untouched.
2. The words live in the surface catalogs the PWA reads
   (`app/src/locales/<language>.json`, the `chat.` leaves), and the terminal reads them
   from the tree it runs in — a source checkout and a wheel resolve the same way.
3. A catalog that cannot answer costs the terminal the English sentence and leaves the
   card standing.

The expected titles are read from the same catalogs, so a case asserts that the card
shows what the surface carries. `test_the_two_languages_carry_different_words` is what
keeps that reading honest: identical leaves in both catalogs would make every other
assertion here vacuous.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui.surface_words as surface_words  # noqa: E402
import ui.widgets as widgets_module  # noqa: E402
from core.language import LANGUAGE_OVERRIDE_ENV, active_language  # noqa: E402
from core.settings_schema import (  # noqa: E402
    load_deep_settings,
    save_deep_settings,
    settings_path,
)

LOCALES = ROOT / "app" / "src" / "locales"
SECTION = "appearance"
LANGUAGE_FIELD = "appearance.language"

# The English half is tree language and is written out. The German half is product copy
# with one home — `app/src/locales/de.json` — so it is pinned here by the digest of the
# leaf the card must print. A changed word in the catalog reddens the case that prints
# it; that is the drift rule, held without a second copy of the sentence.
LIVE_EN = "ephe is flying"
BRIEF_EN = "Thought briefly"
TIMED_EN = "Thought for {{duration}}"
LIVE_DE_SHA = "4538d07cd809896d"
BRIEF_DE_SHA = "3fcc28e49cbd25c9"
TIMED_DE_SHA = "cd80deb06f09b344"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _leaf(language: str, leaf: str) -> str:
    """One thinking word, read where the product keeps it."""
    body = json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))
    return body["chat"][leaf]


def _timed(language: str, duration: str) -> str:
    """The timed word with its placeholder filled, the way the card fills it."""
    return _leaf(language, "thoughtForSeconds").replace("{{duration}}", duration)


LIVE = {language: _leaf(language, "thinkingNow") for language in ("de", "en")}
BRIEF = {language: _leaf(language, "thoughtBriefly") for language in ("de", "en")}


def _save_language(language: str) -> None:
    """The choice a user left in the settings, written the way the route writes it."""
    stored = load_deep_settings()
    section = dict(stored.get(SECTION) or {})
    section[LANGUAGE_FIELD] = language
    assert save_deep_settings({**stored, SECTION: section})


class _Clock:
    """The clock one thinking turn reads: the first token, then the finished answer."""

    def __init__(self, started: float, finished: float) -> None:
        self._readings = iter([started] + [finished] * 64)

    def monotonic(self) -> float:
        return next(self._readings)


def _thinking_titles(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, started: float, finished: float
) -> tuple[str, str]:
    """The title while the thinking streams and the title after the turn finished.

    Driven through the same message chain `ui/app.py` posts, so the assertion sits on
    what the terminal prints rather than on a helper's return value.
    """
    from textual.widgets import Collapsible

    import core.session as session_module
    from ui.app import EpheApp
    from ui.widgets import ChatView

    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(session_module, "SESSION_DIR", session_dir)
    monkeypatch.setattr(session_module, "SESSION_FILE", session_dir / "default.json")
    monkeypatch.setattr(widgets_module, "time", _Clock(started, finished))

    app = EpheApp(model="gemma4:12b", reset=True)
    seen: dict[str, str] = {}

    async def run() -> None:
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            chat = app.query_one(ChatView)
            chat.post_message(ChatView.BeginAssistantMessage())
            await pilot.pause()
            chat.post_message(ChatView.AppendThinking("Plan: read the file."))
            await pilot.pause()
            seen["live"] = chat.query_one(".thinking-block", Collapsible).title
            chat.post_message(ChatView.AppendChunk("Answer."))
            await pilot.pause()
            chat.post_message(ChatView.FinalizeAssistantMessage())
            await pilot.pause()
            seen["done"] = chat.query_one(".thinking-block", Collapsible).title

    asyncio.run(run())
    return seen["live"], seen["done"]


def _titles_in(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    language: str | None,
    saved: str | None = None,
    started: float = 100.0,
    finished: float = 103.0,
) -> tuple[str, str]:
    """One turn under one language: environment above saved choice above default."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv(LANGUAGE_OVERRIDE_ENV, raising=False)
    if saved is not None:
        _save_language(saved)
    if language is not None:
        monkeypatch.setenv(LANGUAGE_OVERRIDE_ENV, language)
    return _thinking_titles(monkeypatch, tmp_path, started=started, finished=finished)


# 1. The two languages, printed.


def test_the_catalogs_carry_the_words_the_product_is_measured_on():
    """The digests below are the words; a catalog that moved without this line moving is drift.

    English is written out because the tree is English. German is a digest because the
    sentence has exactly one home, in `app/src/locales/de.json`.
    """
    assert LIVE["en"] == LIVE_EN
    assert BRIEF["en"] == BRIEF_EN
    assert _leaf("en", "thoughtForSeconds") == TIMED_EN
    assert _sha(LIVE["de"]) == LIVE_DE_SHA
    assert _sha(BRIEF["de"]) == BRIEF_DE_SHA
    assert _sha(_leaf("de", "thoughtForSeconds")) == TIMED_DE_SHA
    assert LIVE["de"] != LIVE["en"]
    assert BRIEF["de"] != BRIEF["en"]


def test_a_german_installation_prints_the_german_word(monkeypatch, tmp_path):
    """GIVEN the saved choice is German WHEN a turn thinks THEN the block shows that catalog."""
    live, done = _titles_in(monkeypatch, tmp_path, language=None, saved="de")
    assert live == LIVE["de"]
    assert _sha(live) == LIVE_DE_SHA
    assert _sha(done.replace("3s", "{{duration}}")) == TIMED_DE_SHA


def test_an_english_installation_prints_the_english_word(monkeypatch, tmp_path):
    """GIVEN the saved choice is English WHEN a turn thinks THEN the block shows that catalog."""
    live, done = _titles_in(monkeypatch, tmp_path, language=None, saved="en")
    assert live == LIVE_EN
    assert done == TIMED_EN.replace("{{duration}}", "3s")


def test_the_word_with_a_duration_carries_the_duration_in_both_languages(monkeypatch, tmp_path):
    """The timed leaf is filled from the same clock in either language."""
    _, german = _titles_in(monkeypatch, tmp_path / "de", language=None, saved="de")
    _, english = _titles_in(monkeypatch, tmp_path / "en", language=None, saved="en")
    assert _sha(german.replace("3s", "{{duration}}")) == TIMED_DE_SHA
    assert english == TIMED_EN.replace("{{duration}}", "3s")
    assert "3s" in german and "3s" in english


def test_a_brief_think_prints_the_short_word(monkeypatch, tmp_path):
    """Under a second the block prints the short word, which carries no duration."""
    _, done = _titles_in(
        monkeypatch, tmp_path, language=None, saved="de", started=100.0, finished=100.4
    )
    assert _sha(done) == BRIEF_DE_SHA


# 2. One home for the choice, with the environment above it.


def test_the_saved_choice_lands_in_the_register_and_the_environment_stays_untouched(
    monkeypatch, tmp_path
):
    """GIVEN a client saves a language WHEN the POST answered THEN the file holds it.

    Until this patch the POST wrote `os.environ`, so the choice died with the server
    process and no other surface could read it back.
    """
    from fastapi.testclient import TestClient

    from server.main import app

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv(LANGUAGE_OVERRIDE_ENV, raising=False)
    answer = TestClient(app).post("/api/settings", json={"language": "en"})
    assert answer.status_code == 200
    assert LANGUAGE_OVERRIDE_ENV not in os.environ
    assert load_deep_settings()[SECTION][LANGUAGE_FIELD] == "en"
    assert settings_path().exists()


def test_the_environment_overrides_the_saved_choice(monkeypatch, tmp_path):
    """A process that names its own language wins over the file, in both directions."""
    english, _ = _titles_in(monkeypatch, tmp_path / "env-en", language="en", saved="de")
    assert english == LIVE_EN
    german, _ = _titles_in(monkeypatch, tmp_path / "env-de", language="de", saved="en")
    assert _sha(german) == LIVE_DE_SHA


def test_the_settings_answer_names_the_language_the_terminal_prints(monkeypatch, tmp_path):
    """The PWA's GET and the terminal's title read one field, so they cannot disagree."""
    from fastapi.testclient import TestClient

    from server.main import app

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv(LANGUAGE_OVERRIDE_ENV, raising=False)
    _save_language("en")
    body = TestClient(app).get("/api/settings").json()
    assert body["language"] == active_language() == "en"
    live, _ = _titles_in(monkeypatch, tmp_path / "card", language=None, saved="en")
    assert live == LIVE_EN


def test_the_pill_and_the_register_row_show_one_value_in_the_same_moment(monkeypatch, tmp_path):
    """Two controls over one field: the PWA's pill and the panel's row may not disagree in a moment.

    The pill reads the GET answer and writes with `updateSettings({ language })`
    (`app/src/components/dashboard/settings/model/useSettingsCore.ts`); the row is built from the
    schema by `deep_view`. Both are read here after one POST, with the card the terminal prints.
    """
    from fastapi.testclient import TestClient
    from server.main import app

    from core.settings_schema import deep_view

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.delenv(LANGUAGE_OVERRIDE_ENV, raising=False)
    client = TestClient(app)
    assert client.post("/api/settings", json={"language": "en"}).status_code == 200

    body = client.get("/api/settings").json()
    row = next(f for s in deep_view() for f in s["fields"] if f["key"] == LANGUAGE_FIELD)
    card, _ = _thinking_titles(monkeypatch, tmp_path / "card", started=100.0, finished=103.0)
    assert body["language"] == row["value"] == active_language() == "en"
    assert card == LIVE_EN


def test_a_language_the_register_does_not_know_is_refused(monkeypatch, tmp_path):
    """An option the register lacks answers 422 and leaves the register as it was."""
    from fastapi.testclient import TestClient

    from server.main import app

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv(LANGUAGE_OVERRIDE_ENV, raising=False)
    answer = TestClient(app).post("/api/settings", json={"language": "fr"})
    assert answer.status_code == 422
    assert SECTION not in load_deep_settings()


def test_the_register_holds_the_language_as_a_select_with_the_shipped_default():
    """The default stands once, in the field, where the panel and the terminal both read it."""
    from core.settings_schema import SCHEMA

    meta = SCHEMA[LANGUAGE_FIELD]
    assert meta["type"] == "select"
    assert meta["options"] == ["de", "en"]
    assert meta["default"] == "de"


# 3. A catalog that cannot answer costs the English sentence, not the card.


def test_a_missing_catalog_prints_the_english_word(monkeypatch, tmp_path):
    """No file: the card still builds, and the word it prints is the one in the code."""
    monkeypatch.setattr(surface_words, "BUNDLE_DIR", tmp_path / "absent")
    live, done = _titles_in(monkeypatch, tmp_path, language="de")
    assert live == surface_words.ENGLISH["thinkingNow"]
    assert done == surface_words.ENGLISH["thoughtForSeconds"].replace("{{duration}}", "3s")


def test_an_unreadable_catalog_prints_the_english_word(monkeypatch, tmp_path):
    """A file the process may not open fails the same way no file does."""
    directory = tmp_path / "locked"
    directory.mkdir(parents=True)
    blocked = directory / "de.json"
    blocked.write_text(json.dumps({"chat": {"thinkingNow": LIVE["de"]}}), encoding="utf-8")
    blocked.chmod(0o000)
    monkeypatch.setattr(surface_words, "BUNDLE_DIR", directory)
    try:
        live, done = _titles_in(monkeypatch, tmp_path / "case", language="de")
    finally:
        blocked.chmod(0o600)
    assert live == surface_words.ENGLISH["thinkingNow"]
    assert done == surface_words.ENGLISH["thoughtForSeconds"].replace("{{duration}}", "3s")


def test_a_catalog_that_is_not_json_prints_the_english_word(monkeypatch, tmp_path):
    """Broken JSON reads as a missing catalog, and the card stays on the screen."""
    directory = tmp_path / "broken"
    directory.mkdir(parents=True)
    (directory / "de.json").write_text("{ chat: { thinkingNow: ", encoding="utf-8")
    monkeypatch.setattr(surface_words, "BUNDLE_DIR", directory)
    live, done = _titles_in(monkeypatch, tmp_path / "case", language="de")
    assert live == surface_words.ENGLISH["thinkingNow"]
    assert done == surface_words.ENGLISH["thoughtForSeconds"].replace("{{duration}}", "3s")


def test_a_catalog_without_the_leaf_prints_the_english_word(monkeypatch, tmp_path):
    """A leaf the catalog lacks falls back on its own; the card never prints a key."""
    directory = tmp_path / "partial"
    directory.mkdir(parents=True)
    (directory / "de.json").write_text(
        json.dumps({"chat": {"thinkingNow": "   ", "thoughtForSeconds": 42}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(surface_words, "BUNDLE_DIR", directory)
    live, done = _titles_in(monkeypatch, tmp_path / "case", language="de")
    assert live == surface_words.ENGLISH["thinkingNow"]
    assert done == surface_words.ENGLISH["thoughtForSeconds"].replace("{{duration}}", "3s")


# 4. The reads a card owes the disk, and the drift the product path proves.


def test_the_card_reads_the_catalog_once_per_card(monkeypatch, tmp_path):
    """A thinking state repaints through a turn while the words are read once."""
    calls: list[str] = []
    real = surface_words._bundle

    def counting(language: str) -> dict:
        calls.append(language)
        return real(language)

    monkeypatch.setattr(surface_words, "_bundle", counting)
    _titles_in(monkeypatch, tmp_path, language="de")
    assert calls == ["de"]


def test_a_card_built_after_the_language_moved_prints_the_new_language(monkeypatch, tmp_path):
    """Two cards, one language move between them: each prints the language it was built in.

    A read per frame and a cache that never falls look identical under one card. The second
    card separates them, and the read log says what each card cost the disk.
    """
    import core.session as session_module
    from ui.app import EpheApp
    from ui.widgets import ChatView

    calls: list[str] = []
    real = surface_words._bundle

    def counting(language: str) -> dict:
        calls.append(language)
        return real(language)

    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(session_module, "SESSION_DIR", session_dir)
    monkeypatch.setattr(session_module, "SESSION_FILE", session_dir / "default.json")
    monkeypatch.setattr(widgets_module, "time", _Clock(100.0, 103.0))
    monkeypatch.setattr(surface_words, "_bundle", counting)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv(LANGUAGE_OVERRIDE_ENV, "de")

    app = EpheApp(model="gemma4:12b", reset=True)
    seen: dict[str, str] = {}

    async def run() -> None:
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            chat = app.query_one(ChatView)
            chat.post_message(ChatView.BeginAssistantMessage())
            await pilot.pause()
            chat.post_message(ChatView.AppendThinking("Plan: read the file."))
            await pilot.pause()
            seen["first"] = list(chat.query("AgentMessageCard .thinking-block"))[-1].title
            chat.post_message(ChatView.AppendChunk("Answer."))
            await pilot.pause()
            chat.post_message(ChatView.FinalizeAssistantMessage())
            await pilot.pause()
            os.environ[LANGUAGE_OVERRIDE_ENV] = "en"
            chat.post_message(ChatView.BeginAssistantMessage())
            await pilot.pause()
            chat.post_message(ChatView.AppendThinking("Plan again."))
            await pilot.pause()
            blocks = list(chat.query("AgentMessageCard .thinking-block"))
            seen["first_done"] = blocks[0].title
            seen["second"] = blocks[-1].title
            seen["cards"] = f"{len(blocks)}:{len(set(id(b) for b in blocks))}"

    asyncio.run(run())
    assert seen["cards"] == "2:2", "two cards, each with its own thinking block"
    assert _sha(seen["first"]) == LIVE_DE_SHA
    # The finished card carries the German done-word after the move too: it keeps the words it
    # was built with, while the card built after the move reads the new ones.
    assert _sha(seen["first_done"].replace("3s", "{{duration}}")) == TIMED_DE_SHA
    assert seen["second"] == LIVE_EN
    assert calls == ["de", "en"]


def test_a_word_changed_in_the_catalog_moves_the_printed_title(monkeypatch, tmp_path):
    """Change the word where it lives and the terminal prints the change.

    This is the drift case: the terminal reads the same file the PWA ships, so a copy
    that would go stale cannot exist here.
    """
    directory = tmp_path / "bundle"
    directory.mkdir(parents=True)
    shutil.copy(LOCALES / "de.json", directory / "de.json")
    monkeypatch.setattr(surface_words, "BUNDLE_DIR", directory)
    before, _ = _titles_in(monkeypatch, tmp_path, language="de")
    assert _sha(before) == LIVE_DE_SHA

    body = json.loads((directory / "de.json").read_text(encoding="utf-8"))
    body["chat"]["thinkingNow"] = "ephe ponders"
    body["chat"]["thoughtForSeconds"] = "Pondered for {{duration}}"
    (directory / "de.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")

    live, done = _titles_in(monkeypatch, tmp_path / "after", language="de")
    assert live == "ephe ponders"
    assert done == "Pondered for 3s"


def test_the_fallback_words_are_the_sentences_the_english_catalog_carries():
    """The code's English is the English the reader would have gotten from the catalog."""
    english = json.loads((LOCALES / "en.json").read_text(encoding="utf-8"))
    for leaf in surface_words.THINKING_LEAVES:
        assert surface_words.ENGLISH[leaf] == english["chat"][leaf], leaf


def test_an_installed_wheel_reads_the_catalog_from_its_own_tree(tmp_path):
    """A packaged install has no source tree, so the path follows the installed files.

    The layout is the wheel's: `ui/` and `app/src/locales/` side by side under one root,
    which is what `[tool.hatch.build.targets.wheel] include` produces (pyproject.toml).
    """
    tree = tmp_path / "site-packages"
    (tree / "ui").mkdir(parents=True)
    (tree / "app" / "src" / "locales").mkdir(parents=True)
    shutil.copy(ROOT / "ui" / "surface_words.py", tree / "ui" / "surface_words.py")
    for name in ("de.json", "en.json"):
        shutil.copy(LOCALES / name, tree / "app" / "src" / "locales" / name)

    spec = importlib.util.spec_from_file_location(
        "installed_surface_words", tree / "ui" / "surface_words.py"
    )
    installed = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(installed)

    assert installed.BUNDLE_DIR == tree / "app" / "src" / "locales"
    assert _sha(installed.thinking_words("de")["thinkingNow"]) == LIVE_DE_SHA

    packaged = tree / "app" / "src" / "locales" / "de.json"
    body = json.loads(packaged.read_text(encoding="utf-8"))
    body["chat"]["thinkingNow"] = "ephe ponders"
    packaged.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    assert installed.thinking_words("de")["thinkingNow"] == "ephe ponders"
