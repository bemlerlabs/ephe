"""A settings refusal is one sentence, and every reader gets it in one language.

`core.settings_schema.validate_sections()` is the hard gate behind POST
/api/settings: a value outside its range and a value outside its option list are
refused before anything is written. The route hands the `ValueError` text to
`HTTPException(422, detail=str(exc))` (`server/routes/settings.py:316`), the
exception handler moves a string detail to `error.message`
(`server/main.py:360`), and `useSettingsSave.ts:96` shows that message in the
toast body under a localized title (`app/src/lib/api/endpoints.ts:712` reads it
first). The sentence is therefore user-facing: it reaches the PWA exactly as the
function wrote it, in whichever language the reader chose.

Six refusals are possible and four of them are English — "section appearance:
unknown", "chat.nope: unknown", "chat.tool_result_chars: number expected",
"section chat: object expected". Two are German: the range bound and the option
list. So the reader who types a timeout of 10^9 is answered in German and the
reader next to them, who mistypes the key, is answered in English. Which
language you get depends on which line your value failed on.

The detector is the language gate's own marker list, imported rather than
restated: what this repository calls German prose is decided in
`scripts/language_inventory.py`, and a test with a vocabulary of its own drifts
from the rule it enforces. The gate itself cannot see these two strings because
it measures comments and docstrings, and a runtime message is neither.

German that *is* the product stays untouched: the locale bundles and
`core/settings_hints.py` carry the user's own language, and this file says
nothing about them.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for bootstrap_dir in (str(ROOT), str(ROOT / "scripts")):
    if bootstrap_dir not in sys.path:
        sys.path.insert(0, bootstrap_dir)

import pytest
from language_inventory import WORD

from core.settings_schema import SCHEMA, validate_sections

#: One call per refusal the function can reach, so a new sentence added here is
#: measured with the rest. The shapes are the function's own branches: an unknown
#: section, a section that is not an object, an unknown field, a field that is not
#: a number, a number past the bound, a value outside the option list.
REFUSALS: list[tuple[str, dict]] = [
    ("unknown section", {"no_such_section": {}}),
    ("section is not an object", {"chat": "expanded"}),
    ("unknown field", {"chat": {"chat.nope": 1}}),
    ("not a number", {"chat": {"chat.tool_result_chars": "five"}}),
    ("outside the range", {"chat": {"chat.tool_result_chars": 5}}),
    ("outside the options", {"chat": {"chat.details_mode": "broad"}}),
]


def _messages() -> list[tuple[str, str]]:
    """The text each refusal raises with, paired with the case that raised it."""
    out: list[tuple[str, str]] = []
    for label, payload in REFUSALS:
        with pytest.raises(ValueError) as excinfo:
            validate_sections(payload)
        out.append((label, str(excinfo.value)))
    return out


def test_every_refusal_names_its_reason_in_english() -> None:
    """The rule the six messages share, stated once over all of them."""
    for label, message in _messages():
        assert WORD.search(message) is None, f"{label} refuses in German: {message!r}"


def test_the_range_refusal_carries_the_same_words_as_its_sibling() -> None:
    """The bound is named the way the type is named: `<field>: <value> outside [min, max]`.

    `number expected` is the English shape already in this function, so the
    translated range message has to read as its neighbour instead of inventing a
    third style.
    """
    bounds = SCHEMA["chat.tool_result_chars"]
    message = dict(_messages())["outside the range"]
    assert "chat.tool_result_chars" in message
    assert "outside" in message
    assert f"[{bounds['min']}, {bounds['max']}]" in message


def test_the_option_refusal_still_names_the_legal_values() -> None:
    """Translating must not cost the reader the list they need to fix the write."""
    options = SCHEMA["chat.details_mode"]["options"]
    message = dict(_messages())["outside the options"]
    assert "chat.details_mode" in message
    for option in options:
        assert option in message


def _client():
    from fastapi.testclient import TestClient

    from server.main import app

    return TestClient(app)


@pytest.mark.parametrize(
    ("label", "payload"),
    [
        ("outside the range", {"advanced": {"advanced.api_timeout": -5}}),
        ("outside the options", {"chat": {"chat.details_mode": "broad"}}),
    ],
)
def test_the_422_body_the_pwa_shows_is_one_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: str, payload: dict
) -> None:
    """The surface proof: what the toast body actually holds after the route renders it."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    res = _client().post("/api/settings", json={"sections": payload})
    assert res.status_code == 422, label
    # `server/main.py:360` puts a string `detail` into `error.message`, and that is
    # the field `useSettingsSave.ts` reads — the envelope, not the FastAPI key.
    detail = res.json()["error"]["message"]
    assert WORD.search(detail) is None, f"{label} reaches the reader in German: {detail!r}"
