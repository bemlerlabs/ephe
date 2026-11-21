"""A tool result or a guard note that names its own reason.

`str` subclassing is the additive half — every reader that formats or `str()`s the note keeps the
sentence it got before. `code` and `params` travel beside it into `tool_done` and `GET /api/reader`,
so a client that translates resolves `reader.<code>` in `app/src/locales/{de,en.json}` instead of
showing the engine's wording. The wording the engine reads lives here: a code a surface has to
recognise is not product copy, same rule as `core/tool_markers.py`. A code describes the whole result —
the card replaces the text with the locale entry, so only a result that IS this one sentence may carry
one.
"""
from __future__ import annotations


class Reason(str):
    __slots__ = ("code", "params", "happened")

    def __new__(cls, text: str, code: str, params: dict[str, str], happened: bool = False):
        obj = super().__new__(cls, text)
        obj.code = code
        obj.params = params
        obj.happened = happened
        return obj


def reason(code: str, text: str, **params: str) -> Reason:
    """A result that says the call did not do what was asked.

    A code alone is not an outcome: `reason()` marks a blockade, `outcome()` marks something
    that happened. The chat surface paints one as failed and the other as completed, and the
    two used to be told apart by "does this carry a code at all" — which is the rule that made
    `[memory] stored (35 entries)` read as a failure to the person who had just stored it.
    """
    return Reason(text, code, params)


def outcome(code: str, text: str, **params: str) -> Reason:
    """A result that names what it achieved — coded for the reader, and not a failure."""
    return Reason(text, code, params, happened=True)


def coded(code: str, exception: BaseException, **params: str) -> BaseException:
    """Puts a reason code on an exception without changing its type.

    A tool that raises goes through `core/tools/registry.py`, which turns the exception into
    `[tool-error '<name>': <exc>]` and reads these two attributes off whatever object arrives.
    Subclassing instead would rename the class in the audit line and change what an existing
    `except ValueError` catches.
    """
    exception.code = code  # type: ignore[attr-defined]
    exception.params = params  # type: ignore[attr-defined]
    return exception
