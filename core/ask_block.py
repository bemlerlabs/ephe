"""The AskUserQuestion block, read by the surfaces that never had a parser.

`core/persona.py` offers the model two ways to ask: the `ask_user` tool, and the older
JSON block convention. `app/src/lib/askUserQuestion.ts` reads the block for the browser, and
`AskUserQuestionCard` renders it. The terminal read neither — it printed the JSON, so a
question arrived as a transcript of its own wire format.

This is the same reading in Python, deliberately tolerant in the same places: fenced or bare
block, trailing commas, options as strings or as objects with a `label`, at least two of
them. Anything that fails those checks is left exactly where it is — a guess about somebody
else's JSON is how a real answer goes missing, and a block this module does not understand
is still text the reader can read.
"""
from __future__ import annotations

import json
import re
from typing import Any

#: A fenced block whose body starts with an object.
_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```")
#: The bare form: from the opening of `{ "question": …` to the last `}` in the answer.
_BARE_START = re.compile(r'\{\s*"question"\s*:')


def _try_parse(raw: str) -> Any:
    try:
        return json.loads(raw)
    except ValueError:
        pass
    # Tolerance pass, same as the browser's: a trailing comma before `}` or `]`.
    try:
        return json.loads(re.sub(r",(\s*[}\]])", r"\1", raw))
    except ValueError:
        return None


def _coerce_options(value: Any) -> list[dict[str, str]] | None:
    if not isinstance(value, list) or len(value) < 2:
        return None
    options: list[dict[str, str]] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            options.append({"label": item.strip()})
        elif isinstance(item, dict) and isinstance(item.get("label"), str):
            option = {"label": str(item["label"])}
            description = item.get("description")
            if isinstance(description, str) and description:
                option["description"] = description
            options.append(option)
        else:
            return None
    return options


def _spec(record: Any) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        return None
    question = record.get("question")
    if not isinstance(question, str) or not question.strip():
        return None
    options = _coerce_options(record.get("options"))
    if options is None:
        return None
    spec: dict[str, Any] = {"question": question.strip(), "options": options}
    recommendation = record.get("recommendation")
    if isinstance(recommendation, str) and recommendation.strip():
        spec["recommendation"] = recommendation.strip()
    if record.get("multiSelect") is True:
        spec["multi_select"] = True
    return spec


def _candidates(text: str) -> list[tuple[str, int, int]]:
    """(body, start, end) for every block-shaped span, fenced first, then bare."""
    found: list[tuple[str, int, int]] = []
    for match in _FENCE.finditer(text):
        body = (match.group(1) or "").strip()
        if body.startswith("{"):
            found.append((body, match.start(), match.end()))
    bare = _BARE_START.search(text)
    if bare:
        rest = text[bare.start():]
        end = rest.rfind("}")
        if end > 0:
            found.append((rest[: end + 1], bare.start(), bare.start() + end + 1))
    return found


def parse_spec(text: str) -> dict[str, Any] | None:
    """The question a block carries, or None when the text holds no readable one."""
    for body, _start, _end in _candidates(text or ""):
        spec = _spec(_try_parse(body))
        if spec:
            return spec
    return None


def split_block(text: str) -> tuple[str, dict[str, Any] | None]:
    """The answer without its question block, and the question the block held.

    Only the span that parsed is removed. A fenced block that is not a question stays in the
    text, because the model may have been showing the reader real JSON as content.
    """
    body = text or ""
    for candidate_body, start, end in _candidates(body):
        spec = _spec(_try_parse(candidate_body))
        if spec is None:
            continue
        cleaned = (body[:start] + body[end:]).strip()
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned, spec
    return body, None
