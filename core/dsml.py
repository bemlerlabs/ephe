"""DeepSeek DSML tool calls, written into the content stream.

Some DeepSeek deployments do not use the OpenAI ``tool_calls`` channel: the
model writes the call as special tokens in the answer text,

    <｜｜DSML｜｜tool_calls>
    <｜｜DSML｜｜invoke name="read_file">
    <｜｜DSML｜｜parameter name="path" string="true">src/main.py</｜｜DSML｜｜parameter>
    </｜｜DSML｜｜invoke>
    </｜｜DSML｜｜tool_calls>

and a client that only reads ``tool_calls`` shows the reader the raw XML and
runs nothing. The bridge below splits those blocks out of the content before it
reaches the bubble and returns them as ordinary ``ProviderToolCall`` objects.
Both bar spellings (full-width ``｜`` and ASCII ``|``) and the spaced form
``<｜｜DSML｜｜ calls>`` are accepted, because the tag is a template artifact
rather than a stable protocol.
"""

from __future__ import annotations

import html
import json
import re
import uuid

from core.model_provider import ProviderFunctionCall, ProviderToolCall

_BAR = r"[｜|]{2}"
_OPEN = rf"<\s*{_BAR}\s*DSML\s*{_BAR}\s*(?:tool_calls|calls)\s*>"
_CLOSE = rf"</\s*{_BAR}\s*DSML\s*{_BAR}\s*(?:tool_calls|calls)\s*>"

_OPEN_RE = re.compile(_OPEN, re.IGNORECASE)
_CLOSE_RE = re.compile(_CLOSE, re.IGNORECASE)
_BLOCK_RE = re.compile(rf"{_OPEN}(?P<body>[\s\S]*?){_CLOSE}", re.IGNORECASE)
_INVOKE_RE = re.compile(
    rf"<\s*{_BAR}\s*DSML\s*{_BAR}\s*invoke\s+name=\"(?P<name>[^\"]*)\"\s*>"
    rf"(?P<body>[\s\S]*?)</\s*{_BAR}\s*DSML\s*{_BAR}\s*invoke\s*>",
    re.IGNORECASE,
)
_PARAM_RE = re.compile(
    rf"<\s*{_BAR}\s*DSML\s*{_BAR}\s*parameter\s+name=\"(?P<name>[^\"]*)\""
    rf"(?:\s+string=\"(?P<string>true|false)\")?\s*>"
    rf"(?P<value>[\s\S]*?)</\s*{_BAR}\s*DSML\s*{_BAR}\s*parameter\s*>",
    re.IGNORECASE,
)

# The literal heads a chunk can end inside; a suffix that is a prefix of one is
# held back until the next chunk decides whether the tag is real. The space
# between the bars and the word varies by template, so the head is matched
# loosely rather than enumerated.
_PARTIAL_HEAD = re.compile(
    r"</?\s*(?:[｜|]{1,2}\s*)?(?:D(?:S(?:M(?:L)?)?)?)?\s*(?:[｜|]{1,2}\s*)?"
    r"(?:t(?:o(?:o(?:l(?:_(?:c(?:a(?:l(?:l(?:s)?)?)?)?)?)?)?)?)?"
    r"|c(?:a(?:l(?:l(?:s)?)?)?)?)?$",
    re.IGNORECASE,
)


def _held_suffix(buffer: str) -> int:
    start = buffer.rfind("<")
    if start < 0:
        return 0
    tail = buffer[start:]
    return len(tail) if _PARTIAL_HEAD.match(tail) else 0


def _value(raw: str, is_string: bool):
    text = html.unescape(raw)
    if is_string:
        return text.strip("\n")
    trimmed = text.strip()
    try:
        return json.loads(trimmed)
    except Exception:
        return trimmed


def _calls_in(body: str) -> list[ProviderToolCall]:
    calls: list[ProviderToolCall] = []
    for invoke in _INVOKE_RE.finditer(body):
        arguments: dict = {}
        for param in _PARAM_RE.finditer(invoke.group("body") or ""):
            name = param.group("name")
            if not name:
                continue
            is_string = (param.group("string") or "true").lower() != "false"
            arguments[name] = _value(param.group("value") or "", is_string)
        calls.append(
            ProviderToolCall(
                function=ProviderFunctionCall(name=invoke.group("name"), arguments=arguments),
                id=f"dsml_{uuid.uuid4().hex[:12]}",
            )
        )
    return calls


def parse_dsml_calls(text: str) -> tuple[str, list[ProviderToolCall]]:
    """Split DSML calls out of ``text``.

    Returns the remaining visible text and the calls it carried. A block whose
    closing tag never arrived still yields its completed invokes; only then is
    the leftover dropped, because half a special token is worse than silence.
    """
    if "DSML" not in text:
        return text, []
    blocks = list(_BLOCK_RE.finditer(text))
    if blocks:
        calls: list[ProviderToolCall] = []
        for block in blocks:
            calls.extend(_calls_in(block.group("body")))
        return _BLOCK_RE.sub("", text), calls
    calls = _calls_in(text)
    if _OPEN_RE.search(text) or calls:
        return "", calls
    return text, []


class DsmlStream:
    """Content-delta sink: emits only the prose, keeps the special tokens back.

    A tag can be split across any number of chunks, so the tail of the buffer is
    held whenever it still looks like the head of an opening marker. The block
    itself is held until its closing tag arrives, then parsed in one piece.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._calls: list[ProviderToolCall] = []

    def feed(self, chunk: str) -> list[str]:
        self._buffer += chunk
        out: list[str] = []
        while self._buffer:
            opening = _OPEN_RE.search(self._buffer)
            if opening is None:
                hold = _held_suffix(self._buffer)
                cut = len(self._buffer) - hold
                if cut > 0:
                    out.append(self._buffer[:cut])
                    self._buffer = self._buffer[cut:]
                return out
            if opening.start() > 0:
                out.append(self._buffer[: opening.start()])
                self._buffer = self._buffer[opening.start():]
            closing = _CLOSE_RE.search(self._buffer)
            if closing is None:
                return out
            block = self._buffer[: closing.end()]
            self._buffer = self._buffer[closing.end():]
            rest, calls = parse_dsml_calls(block)
            self._calls.extend(calls)
            if rest.strip():
                out.append(rest)
        return out

    def finish(self) -> tuple[str, list[ProviderToolCall]]:
        tail = self._buffer
        self._buffer = ""
        calls = self._calls
        self._calls = []
        if not tail:
            return "", calls
        if _OPEN_RE.search(tail):
            rest, extra = parse_dsml_calls(tail)
            return rest, calls + extra
        # A held marker head that never completed is ordinary text ("5 < 7"
        # ending a line). Handing it back is honest; only a real block is cut.
        return tail, calls
