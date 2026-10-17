"""Which interface language a user gets, and the three rules that decide it.

`app/src/i18n.ts` is the only place the UI language is resolved. The browser language
must never decide it without a stored choice, the fallback is English, and the switch in
the settings pane persists the choice per user. The config is read from the shipped
source and then executed against the real i18next pair in `app/node_modules`, so a config
that reads right but resolves wrong still fails.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
I18N_TS = APP_DIR / "src" / "i18n.ts"
DATE_LOCALE_TS = APP_DIR / "src" / "lib" / "dateLocale.ts"
SETTINGS_CONSTANTS_TS = (
    APP_DIR / "src" / "components" / "dashboard" / "settings" / "model" / "constants.ts"
)
SETTINGS_CORE_TS = (
    APP_DIR / "src" / "components" / "dashboard" / "settings" / "model" / "useSettingsCore.ts"
)

NODE = shutil.which("node")
I18NEXT_PACKAGE = APP_DIR / "node_modules" / "i18next" / "package.json"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# WD-33 splits the catalogs per language, and the language has to be decided *before*
# `init` — the preloaded chunk has to be the one the detected language needs. That is why
# `fallbackLng` and `supportedLngs` name module-level constants instead of carrying the
# literal inside the init object. The shipped *values* are what these rules are about, so
# the read follows the name: a constant that changes fails here exactly as a changed
# literal did, and an inline literal is still read as before.
_NAMED = re.compile(r"[A-Za-z_$][\w$]*")
_LITERAL = re.compile(r"'([^']*)'")
_ENTRY = re.compile(r"'([^']*)'|\.\.\.([A-Za-z_$][\w$]*)")


def _first(pattern: str, text: str) -> str:
    found = re.search(pattern, text, re.S)
    assert found is not None, f"i18n source no longer matches {pattern!r}"
    return found.group(1).strip()


def _constant(name: str, text: str) -> str:
    """What a module-level `const NAME[: Type] = <value>` holds."""
    found = re.search(rf"^const {name}\s*(?::[^=]+)?=\s*(.+)$", text, re.M)
    assert found is not None, f"i18n.ts declares no const {name}"
    return found.group(1).strip()


def _value(raw: str, text: str) -> str:
    """A config value: its own string literal, or the constant it is named by."""
    if _NAMED.fullmatch(raw):
        literals = _LITERAL.findall(_constant(raw, text))
        assert literals, f"i18n.ts: const {raw} carries no string literal"
        return literals[0]
    literal = _LITERAL.fullmatch(raw)
    assert literal is not None, f"i18n.ts: {raw!r} is neither a literal nor a constant"
    return literal.group(1)


def _list(body: str, text: str) -> list[str]:
    """The entries of an array literal, with a `...NAME` splice expanded where it stands."""
    out: list[str] = []
    for entry in _ENTRY.finditer(body):
        if entry.group(1) is not None:
            out.append(entry.group(1))
        else:
            out.extend(_LITERAL.findall(_constant(entry.group(2), text)))
    return out


def resolution_config() -> dict:
    """The resolution the shipped i18n source declares, as plain values."""
    text = _text(I18N_TS)
    return {
        "fallbackLng": _value(_first(r"fallbackLng:\s*([^,\n}]+)", text), text),
        "supportedLngs": _list(_first(r"supportedLngs:\s*\[([^\]]*)\]", text), text),
        "load": _value(_first(r"load:\s*([^,\n}]+)", text), text),
        "detectionOrder": _list(
            _first(r"detection:\s*\{[^}]*order:\s*\[([^\]]*)\]", text), text
        ),
        "detectionCaches": _list(
            _first(r"detection:\s*\{[^}]*caches:\s*\[([^\]]*)\]", text), text
        ),
    }


class TestDetectionConfig:
    def test_only_english_and_german_are_supported(self):
        assert resolution_config()["supportedLngs"] == ["en", "de"]

    def test_the_browser_language_is_never_the_detector(self):
        # Only 'localStorage' in the lookup order. A navigator or htmlTag entry would let
        # the machine's locale decide the first impression for a user who never chose one.
        assert resolution_config()["detectionOrder"] == ["localStorage"]

    def test_a_region_code_narrows_to_its_language(self):
        assert resolution_config()["load"] == "languageOnly"


class TestFallback:
    def test_the_fallback_language_is_english(self):
        assert resolution_config()["fallbackLng"] == "en"

    def test_dates_and_numbers_default_to_english(self):
        text = _text(DATE_LOCALE_TS)
        assert "?? 'en'" in text
        assert "? de : enUS" in text
        assert "? 'de-DE' : 'en-US'" in text


class TestPerUserSwitch:
    def test_the_stored_choice_is_cached_per_user(self):
        assert "localStorage" in resolution_config()["detectionCaches"]

    def test_the_settings_pane_switches_and_persists_the_choice(self):
        core = _text(SETTINGS_CORE_TS)
        assert "i18n?.changeLanguage(code)" in core
        assert "updateSettings({ language: code })" in core

    def test_the_switch_offers_exactly_the_supported_languages(self):
        codes = re.findall(r"code:\s*'([^']+)'", _text(SETTINGS_CONSTANTS_TS))
        assert set(codes) == set(resolution_config()["supportedLngs"])


NODE_PROGRAM = r"""
import i18next from 'i18next'
import LanguageDetector from 'i18next-browser-languagedetector'

const payload = JSON.parse(process.argv[1])
const { config, cases } = payload

function installStorage(entries) {
  const map = new Map(Object.entries(entries))
  globalThis.localStorage = {
    getItem: (key) => (map.has(key) ? map.get(key) : null),
    setItem: (key, value) => map.set(key, String(value)),
    removeItem: (key) => map.delete(key),
  }
  return map
}

async function resolve(entries, navigatorLanguage) {
  const cache = installStorage(entries)
  globalThis.window = globalThis
  globalThis.document = { cookie: '' }
  Object.defineProperty(globalThis, 'navigator', {
    value: { language: navigatorLanguage, languages: [navigatorLanguage] },
    configurable: true,
  })
  const instance = i18next.createInstance()
  instance.use(LanguageDetector)
  await instance.init({
    resources: { en: { translation: {} }, de: { translation: {} } },
    fallbackLng: config.fallbackLng,
    supportedLngs: config.supportedLngs,
    load: config.load,
    interpolation: { escapeValue: false },
    detection: { order: config.detectionOrder, caches: config.detectionCaches },
  })
  return { language: instance.language, cache: [...cache.entries()] }
}

const results = []
for (const item of cases) {
  const resolved = await resolve(item.store, item.navigator)
  results.push({ id: item.id, language: resolved.language, cache: resolved.cache })
}
process.stdout.write(JSON.stringify(results))
"""


def _run_node(cases: list[dict]) -> list[dict]:
    assert NODE is not None
    payload = {"config": resolution_config(), "cases": cases}
    done = subprocess.run(
        [NODE, "--input-type=module", "-e", NODE_PROGRAM, json.dumps(payload)],
        cwd=str(APP_DIR),
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.mark.skipif(
    NODE is None or not I18NEXT_PACKAGE.exists(),
    reason="node or app/node_modules is absent, so the detector cannot be executed",
)
class TestResolvedByTheRealDetector:
    def test_a_stored_choice_wins_and_the_browser_language_never_does(self):
        cases = [
            {"id": "fresh, browser German", "store": {}, "navigator": "de-DE", "expect": "en"},
            {
                "id": "stored German",
                "store": {"i18nextLng": "de"},
                "navigator": "en-US",
                "expect": "de",
            },
            {
                "id": "stored unsupported code",
                "store": {"i18nextLng": "fr"},
                "navigator": "de-DE",
                "expect": "en",
            },
        ]
        resolved = {row["id"]: row for row in _run_node(cases)}
        for case in cases:
            assert resolved[case["id"]]["language"] == case["expect"]

    def test_the_resolved_language_is_written_back_to_storage(self):
        resolved = _run_node([{"id": "fresh", "store": {}, "navigator": "de-DE"}])
        assert dict(resolved[0]["cache"]).get("i18nextLng") == "en"
