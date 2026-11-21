"""QD-015 X: DeepSeek writes its tool call into the content as DSML tokens.

A client that reads only ``tool_calls`` showed the reader the special-token XML
and ran nothing. These tests pin the parse, the chunked stream bridge and the
end-to-end turn: prose stays, the block becomes a real call.
"""

from __future__ import annotations

import pytest

from core.chat_detect import _stream_detect_openai
from core.dsml import DsmlStream, parse_dsml_calls

BLOCK = (
    "<｜｜DSML｜｜tool_calls>\n"
    '<｜｜DSML｜｜invoke name="read_file">\n'
    '<｜｜DSML｜｜parameter name="path" string="true">src/main.py</｜｜DSML｜｜parameter>\n'
    '<｜｜DSML｜｜parameter name="limit" string="false">40</｜｜DSML｜｜parameter>\n'
    "</｜｜DSML｜｜invoke>\n"
    "</｜｜DSML｜｜tool_calls>"
)


def _frame(content: str) -> dict:
    return {"message": {"content": content}}


class FakeStream:
    def __init__(self, frames: list[dict]):
        self._frames = list(frames)
        self._i = 0

    def __aiter__(self):
        return self

    async def __anext__(self) -> dict:
        if self._i >= len(self._frames):
            raise StopAsyncIteration
        frame = self._frames[self._i]
        self._i += 1
        return frame


class FakeClient:
    def __init__(self, stream: FakeStream):
        self._stream = stream

    async def chat(self, **kwargs):
        return self._stream


class TestParse:
    def test_a_full_block_becomes_one_call_with_typed_arguments(self):
        rest, calls = parse_dsml_calls(f"Reading now.\n{BLOCK}")
        assert rest.strip() == "Reading now."
        assert len(calls) == 1
        call = calls[0]
        assert call.function.name == "read_file"
        assert call.function.arguments == {"path": "src/main.py", "limit": 40}
        assert call.id

    def test_the_spaced_template_form_is_accepted(self):
        text = (
            "<｜｜DSML｜｜ calls>\n"
            '<｜｜DSML｜｜ invoke name="ping">\n'
            '<｜｜DSML｜｜ parameter name="host" string="true">example.test</｜｜DSML｜｜ parameter>\n'
            "</｜｜DSML｜｜ invoke>\n"
            "</｜｜DSML｜｜ calls>"
        )
        _, calls = parse_dsml_calls(text)
        assert calls[0].function.name == "ping"
        assert calls[0].function.arguments == {"host": "example.test"}

    def test_ascii_bars_are_accepted(self):
        text = (
            "<||DSML||tool_calls>"
            '<||DSML||invoke name="now">'
            "</||DSML||invoke>"
            "</||DSML||tool_calls>"
        )
        _, calls = parse_dsml_calls(text)
        assert calls[0].function.name == "now"

    def test_a_block_whose_outer_close_never_arrived_still_yields_its_call(self):
        text = BLOCK.rsplit("</｜｜DSML｜｜tool_calls>", 1)[0]
        rest, calls = parse_dsml_calls(text)
        assert rest == ""
        assert calls[0].function.name == "read_file"

    def test_text_without_dsml_is_untouched(self):
        rest, calls = parse_dsml_calls("plain <b>answer</b>")
        assert rest == "plain <b>answer</b>"
        assert calls == []


class TestStream:
    def test_a_block_split_across_chunks_never_leaks_a_token(self):
        stream = DsmlStream()
        text = f"Before.\n{BLOCK}\nAfter."
        emitted: list[str] = []
        for i in range(0, len(text), 3):
            emitted.extend(stream.feed(text[i : i + 3]))
        tail, calls = stream.finish()
        visible = "".join(emitted) + tail
        assert visible == "Before.\n\nAfter."
        assert "DSML" not in visible
        assert calls[0].function.arguments == {"path": "src/main.py", "limit": 40}

    def test_a_trailing_smaller_than_sign_is_not_swallowed(self):
        stream = DsmlStream()
        assert stream.feed("5 <") == ["5 "]
        tail, calls = stream.finish()
        assert tail == "<"
        assert calls == []

    def test_prose_passes_through_unchanged(self):
        stream = DsmlStream()
        assert stream.feed("hello ") == ["hello "]
        assert stream.feed("world") == ["world"]
        assert stream.finish() == ("", [])


class TestEndToEnd:
    @pytest.mark.asyncio
    async def test_the_turn_answers_with_prose_and_a_real_call(self):
        chunks: list[str] = []
        frames = [_frame("Checking the file. "), _frame(BLOCK[:60]), _frame(BLOCK[60:] + "\nDone.")]
        resp = await _stream_detect_openai(
            FakeClient(FakeStream(frames)),
            model="deepseek-v3.2",
            messages=[{"role": "user", "content": "read it"}],
            tools=[{"type": "function", "function": {"name": "read_file"}}],
            on_chunk=chunks.append,
            on_thinking=None,
            idle_timeout=5.0,
        )
        assert "DSML" not in "".join(chunks)
        assert "DSML" not in resp.message.content
        assert "Checking the file." in resp.message.content
        assert "Done." in resp.message.content
        assert resp.message.tool_calls is not None
        call = resp.message.tool_calls[0]
        assert call.function.name == "read_file"
        assert call.function.arguments["path"] == "src/main.py"
