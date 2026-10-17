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
    __slots__ = ("code", "params")

    def __new__(cls, text: str, code: str, params: dict[str, str]):
        obj = super().__new__(cls, text)
        obj.code = code
        obj.params = params
        return obj


def reason(code: str, text: str, **params: str) -> Reason:
    return Reason(text, code, params)


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
