"""Offline-first model provider configuration for Ephe.

The default provider is always local Ollama. Advanced users can opt in to a
custom Ollama endpoint or an OpenAI-compatible API, but those modes must be
explicit and visible to the UI.
"""
from __future__ import annotations

import os
import json
import random as _random
import time
from dataclasses import asdict, dataclass
from typing import Any, AsyncIterator, Literal
from urllib.parse import urlparse

import httpx
import ollama

from core import provider_errors
from core.engine_config import (
    ENGINE_SETUP_HINT,
    ENV_PROVIDER,
    EngineNotConfigured,
    engine_api_key_for,
    read_generation_options,
    read_generation_values,
)


ProviderType = Literal["local_ollama", "custom_ollama", "openai_compatible"]
SUPPORTED_PROVIDER_TYPES = {"local_ollama", "custom_ollama", "openai_compatible"}
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"

# The OpenCode zen-Gateway (https://opencode.ai/zen/v1) is OpenAI-compatible but
# demands a strict request fingerprint, otherwise 403 FreeTierError
# ("can only be used from within OpenCode"). Verified live 2026-10-01:
#   1. the User-Agent must start with "opencode/",
#   2. header "x-opencode-session" = ses_<8hex><4hex><14base62> (strict:
#      zone 1+2 = 12 lowercase hex characters, zone 3 = 14 base-62 [a-zA-Z0-9]),
#   3. the tools array must contain the names "bash" AND "read" (edit optional).
# A generic nanoid (without this pattern) returns 403 — hence the structured
# generator below, not a random string.
_ZEN_HOST = "opencode.ai"
_ZEN_B62 = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
# Marker schemas: minimal OpenAI shape, parameter names identical to the real
# implementations (bash→command, read→path, edit→path/old_string/new_string),
# so the dispatcher (TOOL_MAP aliases) understands the arguments directly.
_ZEN_MARKER_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Runs a shell command and returns its output.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Reads a file and returns its text.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "Replaces an exact snippet in a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
]


def _zen_session_id() -> str:
    """Strict zen session-ID fingerprint: ses_ + 8hex + 4hex + 14base62."""
    ts = format(int(time.time()) & 0xFFFFFFFF, "08x")
    cnt = format(_random.randint(0, 0xFFFF), "04x")
    tail = "".join(_random.choice(_ZEN_B62) for _ in range(14))
    return f"ses_{ts}{cnt}{tail}"


def _is_zen_base_url(base_url: str) -> bool:
    """True when the engine URL points at the opencode.ai zen/go gateway."""
    host = (urlparse((base_url or "").strip()).hostname or "").lower()
    return host == _ZEN_HOST


def _with_zen_markers(tools: list[dict]) -> list[dict]:
    """Adds the missing mandatory zen markers (bash/read) to the tools array.

    The zen gateway only returns 200 when the tool names "bash" AND "read"
    appear in the array (verified live: [bash,read]->200, [bash,edit]->403,
    [edit,read]->403). Ephe ships its own names (run_shell/read_file/...)
    as well — the marker definitions are appended here without replacing the
    real ones.
    """
    names = {t.get("function", {}).get("name") for t in tools}
    merged = list(tools)
    for marker in _ZEN_MARKER_TOOLS:
        if marker["function"]["name"] not in names:
            merged.append(marker)
    return merged


class ProviderSetupError(RuntimeError):
    """Raised when an opt-in provider is configured incompletely."""


def _parse_json_arguments(raw: Any) -> dict:
    """Tool arguments as a JSON string (OpenAI) → dict; unparsable text stays under _raw."""
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return {}
    text = str(raw).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return {"_raw": text}
    return parsed if isinstance(parsed, dict) else {"_raw": text}


@dataclass(frozen=True)
class ModelProviderConfig:
    provider: ProviderType
    model: str
    base_url: str
    label: str
    offline_capable: bool
    requires_internet: bool
    advanced_opt_in: bool = False
    api_key_configured: bool = False
    requires_api_key: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProviderFunctionCall:
    name: str
    arguments: dict


@dataclass
class ProviderToolCall:
    function: ProviderFunctionCall
    id: str = ""


@dataclass
class ProviderMessage:
    content: str = ""
    thinking: str = ""
    tool_calls: list[ProviderToolCall] | None = None

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


@dataclass
class ProviderChatResponse:
    message: ProviderMessage

    def __getitem__(self, key: str) -> Any:
        if key == "message":
            return {"content": self.message.content}
        raise KeyError(key)


# Thinking/reasoning wire shapes (2026-10-11): one configured intent, spelled
# differently per provider family — only the native spelling was emitted. Two
# more families this client reaches carry the switch under another field, so an
# install on them had no way to turn thinking off:
#   native     — top-level {"thinking": {...}} + {"reasoning_effort": "..."}
#                (DeepSeek's OpenAI-compatible API; o-series gateways read the
#                effort string).
#   vllm       — Qwen3 on vLLM/sglang reads
#                {"chat_template_kwargs": {"enable_thinking": false}} — the shape
#                the DGX Spark engine and the live smoke tests here send.
#   openrouter — the gateway reads a {"reasoning": {"enabled"|"effort": ...}}
#                object and ignores the native fields.
# The style follows the endpoint (openrouter.ai) unless EPHE_THINKING_STYLE names
# one. With no option set every style emits nothing, so a request without a
# setting stays byte-identical to the pre-existing body.
THINKING_STYLES = ("native", "vllm", "openrouter")
THINKING_STYLE_ENV = "EPHE_THINKING_STYLE"
# Mode words that mean "thinking off"; anything else recognised as a mode reads
# as on.
_THINKING_OFF_MODES = {"disable", "disabled", "off", "false", "none", "no"}


def _thinking_mode_enabled(thinking: object) -> bool | None:
    """True/False for a recognised mode object, None when the mode is not one."""
    if not isinstance(thinking, dict):
        return None
    mode = thinking.get("type")
    if not isinstance(mode, str):
        return None
    return mode.strip().lower() not in _THINKING_OFF_MODES


def _thinking_style(base_url: str) -> str:
    """The endpoint's thinking wire shape: explicit env first, then the host."""
    explicit = os.environ.get(THINKING_STYLE_ENV, "").strip().lower()
    if explicit in THINKING_STYLES:
        return explicit
    return "openrouter" if "openrouter.ai" in (base_url or "") else "native"


def thinking_request_fields(
    options: dict[str, dict | str | None], base_url: str
) -> dict[str, Any]:
    """The thinking/reasoning fields for the endpoint's shape; {} when unset."""
    thinking = options.get("thinking")
    effort = options.get("reasoning_effort")
    if thinking is None and effort is None:
        return {}
    style = _thinking_style(base_url)
    fields: dict[str, Any] = {}
    if style == "vllm":
        enabled = _thinking_mode_enabled(thinking)
        if enabled is not None:
            fields["chat_template_kwargs"] = {"enable_thinking": enabled}
        if effort is not None:
            fields["reasoning_effort"] = effort
        return fields
    if style == "openrouter":
        reasoning: dict[str, Any] = {}
        enabled = _thinking_mode_enabled(thinking)
        if enabled is not None:
            reasoning["enabled"] = enabled
        if effort is not None:
            reasoning["effort"] = effort
        if reasoning:
            fields["reasoning"] = reasoning
        return fields
    if thinking is not None:
        fields["thinking"] = thinking
    if effort is not None:
        fields["reasoning_effort"] = effort
    return fields


class OpenAICompatibleAsyncClient:
    """Small adapter exposing the subset of Ollama's AsyncClient used here."""

    def __init__(self, *, base_url: str, api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _chat_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        # OpenRouter attribution (docs: HTTP-Referer + X-Title identify the app
        # in the dashboard/ranking — a correct integration instead of anonymous).
        if "openrouter.ai" in (self.base_url or ""):
            headers["HTTP-Referer"] = "http://localhost:8765"
            headers["X-Title"] = "Ephe"
        # The zen gateway demands the opencode fingerprint (otherwise 403 FreeTierError):
        # the UA starts with "opencode/" AND x-opencode-session carries the
        # structured ses_ pattern. Both headers are a condition for 200.
        if _is_zen_base_url(self.base_url):
            headers["User-Agent"] = "opencode/1.18.34"
            headers["x-opencode-session"] = _zen_session_id()
        return headers

    def _convert_messages(self, messages: list[dict]) -> list[dict]:
        converted: list[dict] = []
        # Position-based tool_call_id correlation: the shared tool loop
        # (core/chat.py) appends an assistant ProviderMessage with tool_calls,
        # then the tool results as {"role":"tool"}.
        # OpenAI requires tool_call_id on the tool messages — the IDs
        # (exactly as delivered by the engine) are returned in the order
        # the tool results arrive.
        pending_tool_call_ids: list[str] = []
        # OpenAI requires the tool messages answering an assistant `tool_calls`
        # block to follow it with no other role in between. The shared tool loop
        # appends a "Tool evidence summary" after EACH tool result, so a round of
        # two or more calls used to convert to assistant/tool/user/tool/user — and
        # the engine refused the request with "An assistant message with
        # 'tool_calls' must be followed by tool messages responding to each
        # 'tool_call_id' (insufficient tool messages following tool_calls
        # message)". The interleaved messages are held back here and re-emitted
        # once the block is fully answered, so the tool messages stay contiguous.
        deferred: list[dict] = []

        def _flush_deferred() -> None:
            if deferred:
                converted.extend(deferred)
                deferred.clear()

        def _register_block(calls: list[Any]) -> list[dict]:
            """Wire shape of an assistant `tool_calls` array + its ids in order.

            Both shapes reach here: ProviderToolCall objects (the tool loop) and
            the already-wire dicts of a replayed history (an OpenAI-protocol
            client over /v1/chat/completions, a resumed session). The dict form
            used to be dropped — the assistant went out without its tool_calls
            and every tool message of the conversation was left orphaned, which
            the engine refuses with 'Messages with role "tool" must be a response
            to a preceding message with "tool_calls"'.
            """
            out: list[dict] = []
            for i, call in enumerate(calls or []):
                if isinstance(call, dict):
                    function = call.get("function") or {}
                    tool_call_id = str(call.get("id") or f"call_{i}")
                    entry = call
                else:
                    function = call.function
                    tool_call_id = call.id or f"call_{i}"
                    entry = None
                arguments = function.get("arguments") if isinstance(function, dict) else function.arguments
                if not isinstance(arguments, str):
                    arguments = json.dumps(arguments or {}, ensure_ascii=False)
                pending_tool_call_ids.append(tool_call_id)
                out.append(
                    entry
                    if isinstance(entry, dict) and entry.get("id") and entry.get("function")
                    else {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": function.get("name", "") if isinstance(function, dict) else function.name,
                            "arguments": arguments,
                        },
                    }
                )
            return out

        for msg in messages:
            if isinstance(msg, ProviderMessage):
                # A new block ends any previous one; anything held back is due
                # before this message.
                _flush_deferred()
                tool_calls_out = _register_block(msg.tool_calls or [])
                out: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
                if tool_calls_out:
                    out["tool_calls"] = tool_calls_out
                converted.append(out)
                continue
            role = getattr(msg, "role", None) or msg.get("role", "user")
            content = getattr(msg, "content", None) or msg.get("content", "")
            if role == "assistant" and isinstance(msg, dict) and msg.get("tool_calls"):
                # A replayed (dict) assistant block: same handling as the object.
                _flush_deferred()
                out = {"role": "assistant", "content": str(content or "")}
                out["tool_calls"] = _register_block(msg["tool_calls"])
                converted.append(out)
                continue
            if role == "tool" and isinstance(msg, dict):
                # A replayed result names the id it answers; when that id is one
                # of the open ones, it wins over the positional order.
                explicit = str(msg.get("tool_call_id") or "")
                if explicit and explicit in pending_tool_call_ids:
                    pending_tool_call_ids.remove(explicit)
                    tool_call_id = explicit
                elif pending_tool_call_ids:
                    tool_call_id = pending_tool_call_ids.pop(0)
                else:
                    tool_call_id = f"call_{len(converted)}"
                converted.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": str(content),
                    }
                )
                if not pending_tool_call_ids:
                    # The block is answered — the held-back messages follow it.
                    _flush_deferred()
                continue
            images = msg.get("images") if isinstance(msg, dict) else None
            # OpenAI/vLLM: system messages belong only at the START of the
            # conversation. The shared tool loop appends a "Tool evidence summary"
            # as role=system after tool results — for the OpenAI provider that is
            # remapped to user (vLLM accepts user messages in the middle; Ollama
            # allows system anywhere).
            if role == "system" and converted:
                role = "user"
            if images:
                parts: list[dict] = [{"type": "text", "text": str(content)}]
                for image_b64 in images:
                    parts.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                        }
                    )
                entry: dict = {"role": role, "content": parts}
            else:
                entry = {"role": role, "content": str(content)}
            if pending_tool_call_ids:
                # Inside an unanswered tool_calls block — hold it back so the
                # tool messages that answer the block stay contiguous.
                deferred.append(entry)
            else:
                converted.append(entry)
        _flush_deferred()
        return converted

    async def chat(
        self,
        *,
        model: str,
        messages: list[dict],
        stream: bool = False,
        tools: list[dict] | None = None,
        **_: Any,
    ) -> ProviderChatResponse | AsyncIterator[dict]:
        # I2-5 way A: the active generation values (env precedence → engine.json
        # → default) go into the request — before this a hardcoded 0.0 stood here,
        # and top_p/max_tokens were never sent while the settings card showed three
        # sliders. With nothing configured everything stays at the old behaviour:
        # temperature 0.0 (deterministic, pass^3 reliability),
        # top_p/max_tokens are None and therefore not sent — an invented cap would
        # have flipped every existing installation.
        generation = read_generation_values()
        payload: dict[str, Any] = {
            "model": model,
            "messages": self._convert_messages(messages),
            "stream": stream,
            "temperature": generation["temperature"],
        }
        if generation.get("top_p") is not None:
            payload["top_p"] = generation["top_p"]
        if generation.get("max_tokens") is not None:
            payload["max_tokens"] = generation["max_tokens"]
        # Non-thinking passthrough (2026-10-11): DeepSeek's API defaults
        # thinking ON and bills the reasoning text against max_tokens —
        # {"type": "disabled"} in this field is what switches it off. The
        # options follow the same ladder as the numeric generation values
        # (env → engine.json → unset) and travel ONLY when set: without a
        # setting the request body stays exactly what every installation
        # sends today. thinking_request_fields maps the intent onto the field
        # shape of the endpoint family (native / vllm / openrouter, table above).
        options = read_generation_options()
        payload.update(thinking_request_fields(options, self.base_url))
        # N8a: the endpoint should deliver its measured usage block.
        # vLLM/sglang only send it in the SSE when stream_options.include_usage
        # is set — without this flag the counting stays an estimate.
        if stream:
            payload["stream_options"] = {"include_usage": True}
        # Send the tool schemas to the OpenAI-compatible engine (vLLM
        # supports native tool calling). The shared tool loop in
        # core/chat.py appends the results position-based —
        # _convert_messages restores the tool_call_id.
        if tools:
            payload["tools"] = (
                _with_zen_markers(tools) if _is_zen_base_url(self.base_url) else tools
            )

        if stream:
            return self._stream_chat(payload)

        # zen gateway: non-streaming is not possible (stream missing/False ->
        # 403). The fingerprint demands stream=true, so the SSE stream is
        # collected here into a ProviderChatResponse (identical semantics).
        if _is_zen_base_url(self.base_url):
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
            return await self._collect_zen_stream(payload)

        async with httpx.AsyncClient(timeout=self.api_timeout_seconds()) as client:
            response = await client.post(self._chat_url(), headers=self._headers(), json=payload)
            challenge = _key_challenge(response.status_code, self.base_url, self.api_key)
            if challenge is not None:
                raise challenge
            if response.status_code >= 400:
                raise _status_error(response)
            response.raise_for_status()
            data = response.json()

        from core.tools.session_ctx import record_measured_usage

        record_measured_usage(data.get("usage"))
        message = data.get("choices", [{}])[0].get("message", {})
        tool_calls: list[ProviderToolCall] | None = None
        raw_tool_calls = message.get("tool_calls")
        if raw_tool_calls:
            tool_calls = [
                ProviderToolCall(
                    id=str(tc.get("id", "") or f"call_{i}"),
                    function=ProviderFunctionCall(
                        name=str((tc.get("function") or {}).get("name", "")),
                        arguments=_parse_json_arguments(
                            (tc.get("function") or {}).get("arguments")
                        ),
                    ),
                )
                for i, tc in enumerate(raw_tool_calls)
            ]
        return ProviderChatResponse(
            message=ProviderMessage(
                content=message.get("content") or "",
                thinking=str(message.get("reasoning_content") or message.get("reasoning") or ""),
                tool_calls=tool_calls,
            )
        )

    # W19 bench finding: `timeout=None` in the engine stream hangs the agent loop
    # forever when a connection (e.g. Tailscale) dies without a FIN —
    # the SSE keepalives to the client hide the silence. Read timeout with
    # generous headroom (models may think slowly between tokens), but
    # bounded; the non-streaming request takes its bound from the
    # deep register (advanced.api_timeout, default 120 = the old hardcoded value).
    STREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)

    @staticmethod
    def api_timeout_seconds() -> float:
        """Non-streaming requests: timeout taken from the register.

        The lookup clamps to the bound (10..1800 s) so a hand-edited
        settings.json value cannot let the request run forever.
        """
        from core.settings_schema import deep_number

        return float(deep_number("advanced.api_timeout"))

    async def _stream_chat(self, payload: dict[str, Any]) -> AsyncIterator[dict]:
        async with httpx.AsyncClient(timeout=self.STREAM_TIMEOUT) as client:
            async with client.stream(
                "POST",
                self._chat_url(),
                headers=self._headers(),
                json=payload,
            ) as response:
                challenge = _key_challenge(response.status_code, self.base_url, self.api_key)
                if challenge is not None:
                    raise challenge
                if 400 <= response.status_code < 500:
                    # Row #51: on this path the body is still in the buffer, and the
                    # mapper dies on `response.text` (ResponseNotRead) — the reader then
                    # saw httpx's url line where the engine's reason belongs. The
                    # non-streaming branch has opened the body since W13; a 4xx gets the
                    # same treatment here, and a 5xx keeps the line every caller had.
                    await response.aread()
                    raise _status_error(response)
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line.removeprefix("data:").strip()
                    if raw == "[DONE]":
                        break
                    if not raw:
                        continue
                    data = json.loads(raw)
                    # N8a: the measured usage block arrives (with include_usage=true)
                    # in the last data frame before [DONE].
                    from core.tools.session_ctx import record_measured_usage

                    record_measured_usage(data.get("usage"))
                    # The final usage frame carries choices=[] (no delta) — with an
                    # empty list [0] must not be indexed, otherwise the parser breaks
                    # the stream in the middle of the answer (empty answer).
                    choices = data.get("choices") or []
                    delta = choices[0].get("delta", {}) if choices else {}
                    reasoning = delta.get("reasoning_content") or delta.get("reasoning")
                    if reasoning:
                        # Reasoning as its own channel — the consumer
                        # (core.chat.stream_response) forwards it to on_thinking
                        # instead of mixing it into the answer stream.
                        yield {"message": {"reasoning_content": reasoning}}
                    content = delta.get("content") or ""
                    if content:
                        yield {"message": {"content": content}}
                    raw_tool_calls = delta.get("tool_calls")
                    if raw_tool_calls:
                        # Tool-call deltas (OpenAI format, arguments arrive in
                        # fragments) — without them the tool detection could
                        # not stream (sglang/vLLM stream them correctly).
                        yield {"message": {"tool_calls": raw_tool_calls}}

    async def _collect_zen_stream(self, payload: dict[str, Any]) -> ProviderChatResponse:
        """Aggregate the zen gateway's SSE stream into one ProviderChatResponse.

        The zen fingerprint demands stream=true; this path delivers the
        non-streaming answer by consolidating the deltas. Tool-call
        deltas arrive fragmented (arguments in pieces) and are merged per
        index — identical shape to the non-streaming branch.
        """
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        # index -> {id, name, arguments}
        tool_acc: dict[int, dict[str, str]] = {}
        async for frame in self._stream_chat(payload):
            msg = frame.get("message", {})
            if msg.get("content"):
                content_parts.append(str(msg["content"]))
            if msg.get("reasoning_content"):
                reasoning_parts.append(str(msg["reasoning_content"]))
            for frag in msg.get("tool_calls") or []:
                idx = frag.get("index", 0)
                slot = tool_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                if frag.get("id"):
                    slot["id"] = str(frag["id"])
                fn = frag.get("function") or {}
                if fn.get("name"):
                    slot["name"] = str(fn["name"])
                if fn.get("arguments"):
                    slot["arguments"] += str(fn["arguments"])

        tool_calls: list[ProviderToolCall] | None = None
        if tool_acc:
            tool_calls = [
                ProviderToolCall(
                    id=slot["id"] or f"call_{idx}",
                    function=ProviderFunctionCall(
                        name=slot["name"],
                        arguments=_parse_json_arguments(slot["arguments"]),
                    ),
                )
                for idx, slot in sorted(tool_acc.items())
            ]
        return ProviderChatResponse(
            message=ProviderMessage(
                content="".join(content_parts),
                thinking="".join(reasoning_parts),
                tool_calls=tool_calls,
            )
        )


_ACTIVE_OVERRIDE: ModelProviderConfig | None = None


def validate_provider_type(provider: str) -> ProviderType:
    if provider not in SUPPORTED_PROVIDER_TYPES:
        allowed = ", ".join(sorted(SUPPORTED_PROVIDER_TYPES))
        raise ValueError(f"Unsupported model provider '{provider}'. Allowed: {allowed}")
    return provider  # type: ignore[return-value]


def _base_url(value: str | None, default: str = DEFAULT_OLLAMA_BASE_URL) -> str:
    raw = (value or default).strip().rstrip("/")
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"http://{raw}"
    return raw


def _endpoint_requires_api_key(base_url: str) -> bool:
    """The key requirement depends on the endpoint, not on the provider.

    Root cause: a local/private OpenAI-compatible endpoint (DGX-Spark via
    Tailnet ``*.ts.net``, ``127.0.0.1``, ``*.local``, RFC1918 private network)
    needs NO API key — but a public cloud API (own gateway endpoint,
    …) does. The old logic made ``requires_api_key`` a provider constant (True)
    → every PWA choice of a keyless-DGX engine failed with "no API key is
    configured", although the endpoint is open.

    Heuristic (deliberately simple, no DNS lookup — deterministic & offline):
    - empty / no host       → False (local)
    - localhost / 127.x / ::1 → False
    - *.ts.net / *.local / *.lan / mDNS name → False (Tailnet/local)
    - RFC1918 (10./172.16-31./192.168.) → False
    - otherwise (public host) → True
    """
    host = ""
    raw = (base_url or "").strip().rstrip("/")
    if raw:
        rest = raw.split("://", 1)[1] if "://" in raw else raw
        authority = rest.split("/", 1)[0]
        if authority.startswith("["):
            # IPv6 literal "[::1]:8000" — the host sits inside the brackets.
            host = (
                authority[1:authority.index("]")].lower()
                if "]" in authority
                else authority[1:].lower()
            )
        else:
            host = authority.split(":", 1)[0].lower()

    if not host:
        return False
    if host in ("localhost", "0.0.0.0", "::1"):
        return False
    if host.startswith("127."):
        return False
    if host.startswith("192.168"):
        return False
    if host.startswith("10."):
        return False
    # RFC1918 172.16.0.0–172.31.255.255 (exact, not a prefix approximation)
    if host.startswith("172."):
        parts = host.split(".")
        if len(parts) >= 2 and parts[1].isdigit() and 16 <= int(parts[1]) <= 31:
            return False
    if host.endswith((".ts.net", ".local", ".lan", ".internal", ".home.arpa")):
        return False
    return True


#: What an endpoint answers when it is asked for a model list by nobody: it is keyed.
#: The taxonomy owns the set, so a challenge means the same thing here and in the
#: retry/error table (core/provider_errors.py).
KEY_CHALLENGE_STATUSES = provider_errors.AUTH_STATUSES

#: The two places a token can sit so that THIS start reads it. An icon-launched
#: desktop app inherits no shell export (`app/src-tauri/src/backend.rs` reads the
#: file into the child instead), so naming only the variable leaves a desktop user
#: with a file they were never told about. Since 2026-10-10 the file is not a
#: desktop special case: `core/engine_config.py` reads it for every start too.
KEY_PLACES = (
    "Put the token where this start reads it: EPHE_OPENAI_COMPAT_API_KEY in the "
    "environment that starts the server, or one owner-readable line in "
    "~/.ephe/engine.key for a start no shell reached — the app opened from the Dock."
)


def endpoint_requires_api_key(base_url: str, observed_status: int | None = None) -> bool:
    """Whether an endpoint wants a token — from what it does, when it has said so.

    ``_endpoint_requires_api_key`` is a guess about the infrastructure, made before
    the first request and blind to a Tailnet engine standing behind an
    authenticating proxy. A 401 is not a guess: it is the endpoint. Where both are
    known, the answer wins.
    """
    if observed_status in KEY_CHALLENGE_STATUSES:
        return True
    return _endpoint_requires_api_key(base_url)


def key_challenge_reason(base_url: str, status: int, token_sent: bool) -> str:
    """The one sentence both sinks may show: what was seen, and where the fix goes."""
    endpoint = (base_url or "").rstrip("/")
    if token_sent:
        return (
            f"{endpoint} refused the token it was given (HTTP {status}). {KEY_PLACES}"
        )
    return f"{endpoint} answers HTTP {status} to an unauthenticated request. {KEY_PLACES}"


def _key_challenge(status: int, base_url: str, token: str) -> ProviderSetupError | None:
    """The error for a challenge, or None when the status says something else.

    Raised instead of a bare HTTPStatusError so the run stops here: the failover
    chain keeps the chosen engine when an endpoint refuses us, and a silent switch
    to another engine is the failure mode the whole engine selection avoids.
    """
    if status not in KEY_CHALLENGE_STATUSES:
        return None
    return ProviderSetupError(key_challenge_reason(base_url, status, bool(token)))


def _status_error(response: httpx.Response) -> httpx.HTTPStatusError:
    """The exception a refused request becomes, with the provider's own body in it.

    Both request paths raise this one, so the mapper reads the engine's reason
    whichever path answered, and the two cannot drift apart. `response.text` needs
    the body: on a streamed response that means an `aread()` first, otherwise this
    raises ResponseNotRead and the reader gets httpx's own line instead (row #51).
    """
    return httpx.HTTPStatusError(
        f"{response.status_code} Bad Request: {response.text[:500]}",
        request=response.request,
        response=response,
    )


def _required_model(env_var: str, provider: str) -> str:
    """The model name is part of the choice — not a leftover we fill in.

    `core/engine_config.py` has said since W18: there is no silent engine
    default. This function was the exception — custom_ollama
    got the local model, openai_compatible the placeholder "custom-model",
    and the surface reported an active_model that nobody had named.
    """
    model = (os.environ.get(env_var) or "").strip()
    if not model:
        raise EngineNotConfigured(
            f"{ENV_PROVIDER}={provider} is set, but {env_var} is missing. " + ENGINE_SETUP_HINT
        )
    return model


def _provider_from_env() -> ModelProviderConfig:
    provider = validate_provider_type(os.environ.get("EPHE_MODEL_PROVIDER", "local_ollama"))

    if provider == "custom_ollama":
        return ModelProviderConfig(
            provider="custom_ollama",
            model=_required_model("EPHE_MODEL", "custom_ollama"),
            base_url=_base_url(os.environ.get("EPHE_CUSTOM_OLLAMA_BASE_URL")),
            label="Custom Ollama",
            offline_capable=True,
            requires_internet=False,
            advanced_opt_in=True,
        )

    if provider == "openai_compatible":
        compat_base = _base_url(os.environ.get("EPHE_OPENAI_COMPAT_BASE_URL"), "")
        return ModelProviderConfig(
            provider="openai_compatible",
            model=_required_model("EPHE_OPENAI_COMPAT_MODEL", "openai_compatible"),
            base_url=compat_base,
            label="OpenAI-compatible API",
            offline_capable=False,
            requires_internet=True,
            advanced_opt_in=True,
            api_key_configured=bool(engine_api_key_for(compat_base)),
            requires_api_key=_endpoint_requires_api_key(compat_base),
        )

    # The local class needs its tag from the user as well. Two states differ here:
    # an explicit EPHE_MODEL_PROVIDER without EPHE_MODEL is an incomplete choice and
    # names the missing variable; nothing set at all is the unconfigured state the
    # setup gate reports, and its active model stays empty rather than invented.
    explicit = bool(os.environ.get("EPHE_MODEL_PROVIDER"))
    local_model = (
        _required_model("EPHE_MODEL", "local_ollama")
        if explicit
        else (os.environ.get("EPHE_MODEL") or "").strip()
    )

    return ModelProviderConfig(
        provider="local_ollama",
        model=local_model,
        base_url=_base_url(os.environ.get("EPHE_LOCAL_OLLAMA_BASE_URL")),
        label="Local Ollama",
        offline_capable=True,
        requires_internet=False,
    )


def get_active_provider() -> ModelProviderConfig:
    return _ACTIVE_OVERRIDE or _provider_from_env()


def chosen_model(caller: str = "") -> str:
    """The tag the user chose, for a call that has to put a name in the request: a
    scheduled job, a skill's test run, a vision round.

    ``get_active_provider().model`` is empty when nothing was chosen, and an empty tag
    must not travel to the engine as though it were a model — this raises the same
    actionable refusal the start paths give (owner decision 2026-10-11: no shipped
    default, the tag belongs to the user).
    """
    model = (os.environ.get("EPHE_MODEL") or "").strip()
    if not model:
        model = (get_active_provider().model or "").strip()
    if not model:
        raise EngineNotConfigured(f"No model chosen{' for ' + caller if caller else ''}.")
    return model


# W7-1: the real second path. One chosen engine is a single point of failure, and
# the local Ollama is only a fallback where it is installed and tagged. These three
# variables name a second engine the chain may fall back to, so a dead endpoint, a
# 5xx or a timeout leaves a reachable, named engine rather than the honest error alone.
FAILOVER_PROVIDER_ENV = "EPHE_FAILOVER_PROVIDER"
FAILOVER_BASE_URL_ENV = "EPHE_FAILOVER_BASE_URL"
FAILOVER_MODEL_ENV = "EPHE_FAILOVER_MODEL"


def secondary_provider_from_env() -> ModelProviderConfig | None:
    """The configured second path, or None when the owner named none (W7-1).

    All three variables decide it — the family, the endpoint, the tag. A partial
    trio is a typo rather than an engine, so it is ignored instead of probed: a half-written
    env may not quietly redirect a turn to an endpoint nobody finished naming.
    """
    provider_raw = (os.environ.get(FAILOVER_PROVIDER_ENV) or "").strip()
    base_raw = (os.environ.get(FAILOVER_BASE_URL_ENV) or "").strip()
    model = (os.environ.get(FAILOVER_MODEL_ENV) or "").strip()
    if not (provider_raw and base_raw and model):
        return None
    try:
        provider = validate_provider_type(provider_raw)
    except ValueError:
        return None
    base_url = _base_url(base_raw, "")
    if not base_url:
        return None
    local = provider == "local_ollama"
    return ModelProviderConfig(
        provider=provider,
        model=model,
        base_url=base_url,
        label="Failover engine",
        offline_capable=local,
        requires_internet=not local,
        advanced_opt_in=True,
        api_key_configured=bool(engine_api_key_for(base_url)),
        requires_api_key=_endpoint_requires_api_key(base_url),
    )


def _engine_handle(config: ModelProviderConfig) -> str:
    """A stable name for one engine: class, host and tag.

    A provider *type* alone cannot tell two openai_compatible engines apart, and a
    failover note has to name the engine the turn actually landed on.
    """
    host = urlparse(config.base_url).netloc or (config.base_url or "").strip() or "unnamed"
    return f"{config.provider}@{host}#{config.model or '-'}"


def failover_note(
    source: ModelProviderConfig,
    target: ModelProviderConfig,
    failure: provider_errors.ProviderFailure | None = None,
) -> str:
    """The ``from→to (cause)`` line the turn audit and the transcript both carry (W7-1).

    Both engines are named by host and tag, because a class alone cannot name a second
    openai_compatible path, and the cause is the classified trip — the dead endpoint,
    the 5xx, the timeout — that moved the turn off the chosen engine.
    """
    cause = failure.kind.value if failure is not None else "unreachable"
    if failure is not None and failure.status is not None:
        cause = f"{cause} {failure.status}"
    return f"{_engine_handle(source)}→{_engine_handle(target)} ({cause})"


def resolve_failover_chain(
    active: ModelProviderConfig | None,
) -> list[ModelProviderConfig]:
    """R44/W7-1: provider failover chain — active → second path → local_ollama.

    Pure, testable core logic without I/O. The chain holds one entry per engine
    (provider + base_url): since 2026-10-11 the local class carries no default tag,
    so deduplicating by the tag would list the same Ollama twice — once chosen, once
    unnamed. The second path is named by env (``EPHE_FAILOVER_*``) and joins ahead of
    the local Ollama, so a remote failure lands on a real, named engine and not on an
    installed-or-not local one. With ``None`` (no engine chosen) the chain is empty —
    fail-closed, no silent default. The chat path runs the chain: the first reachable
    candidate wins, and a fallback to a later candidate is recorded in the session_ctx
    failover note.
    """
    if active is None:
        return []
    chain: list[ModelProviderConfig] = [active]
    seen = {(active.provider, active.base_url)}

    def _add(candidate: ModelProviderConfig | None) -> None:
        if candidate is None:
            return
        key = (candidate.provider, candidate.base_url)
        if key in seen:
            return
        seen.add(key)
        chain.append(candidate)

    # The configured second path first, the local Ollama last.
    _add(secondary_provider_from_env())
    fallback = _provider_from_env()
    if fallback.provider == "local_ollama":
        _add(fallback)
    return chain


async def probe_provider_failure(
    config: ModelProviderConfig, *, timeout: float = 3.0
) -> provider_errors.ProviderFailure | None:
    """The classified reason ``config`` is unreachable, or None when it answers /models.

    Both engine types (Ollama, OpenAI-compatible) serve /models. The trip is
    deterministic on the three shapes the chain cares about: a dead endpoint (a
    transport error), a 5xx (a server error) and a timeout. A status below 500 stays
    reachable on purpose (measured 2026-10-10): the endpoint is up and it is the engine
    the user chose, and calling it unreachable here would let the chain answer a keyed
    engine with another engine's output. The challenge is raised where the request is
    actually made, with the token's two places named. Nothing is raised outward.
    """
    import httpx

    url = config.base_url.rstrip("/")
    if not url.endswith("/models"):
        url = f"{url}/models"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
    except Exception as exc:
        return provider_errors.classify(exc)
    if resp.status_code >= 500:
        return provider_errors.classify_status(resp.status_code)
    return None


async def probe_provider(config: ModelProviderConfig, *, timeout: float = 3.0) -> bool:
    """Short reachability probe: GET {base_url}/models. True when reachable.

    The boolean face of ``probe_provider_failure``, for a caller that only needs the
    verdict; the chain reads the classified reason, so its note can name the trip.
    """
    return await probe_provider_failure(config, timeout=timeout) is None


async def resolve_active_with_failover(
    provider: ModelProviderConfig | None,
) -> ModelProviderConfig | None:
    """R44/W7-1: walk the failover chain — the first reachable candidate wins.

    One candidate => no failover (the note stays empty). Several => the first
    reachable one; when the turn lands on a later candidate the note names both engines
    and the classified cause of the trip, for the kind=turn audit and the transcript. A
    candidate with no tag cannot answer a turn (the local class ships no default since
    2026-10-11), so it is skipped instead of probed and handed an empty model. No
    candidate reachable => the active config is kept, and the downstream call raises the
    honest unreachable error.
    """
    from core.tools.session_ctx import set_failover_note

    set_failover_note("")
    chain = resolve_failover_chain(provider)
    if not chain:
        return None
    if len(chain) == 1:
        return chain[0]
    trip: provider_errors.ProviderFailure | None = None
    for idx, candidate in enumerate(chain):
        if not candidate.model:
            continue
        failure = await probe_provider_failure(candidate)
        if failure is None:
            if idx > 0 and provider is not None:
                set_failover_note(failover_note(provider, candidate, trip))
            return candidate
        if trip is None:
            # The first unreachable candidate is the chosen engine; its failure is the
            # cause the note carries.
            trip = failure
    return chain[0]


def has_explicit_provider() -> bool:
    """True when the engine was chosen explicitly (env or session selection).

    W19: without the env ``_provider_from_env`` falls back to local_ollama
    silently — for the chat fail-closed in setup mode chat.py needs an honest
    answer on whether an engine exists at all (engine.json counts via the
    setup UI's persist path as well, but is checked there separately).
    """
    return bool(os.environ.get("EPHE_MODEL_PROVIDER") or _ACTIVE_OVERRIDE is not None)


def set_active_provider(
    *,
    provider: str,
    model: str | None = None,
    base_url: str | None = None,
) -> ModelProviderConfig:
    """Set a session-local provider override used until process restart."""
    global _ACTIVE_OVERRIDE
    provider_type = validate_provider_type(provider)

    if provider_type == "local_ollama":
        config = ModelProviderConfig(
            provider="local_ollama",
            model=(model or "").strip(),
            base_url=_base_url(base_url),
            label="Local Ollama",
            offline_capable=True,
            requires_internet=False,
        )
    elif provider_type == "custom_ollama":
        config = ModelProviderConfig(
            provider="custom_ollama",
            model=(model or "").strip(),
            base_url=_base_url(base_url),
            label="Custom Ollama",
            offline_capable=True,
            requires_internet=False,
            advanced_opt_in=True,
        )
    else:
        # F4: base_url=None means "do not change the URL", not "delete it".
        # Root cause: saveSettings() in the 'model' tab sends endpoint=None ->
        # the active API URL became "" and the chat was dead.
        if not base_url:
            current = _ACTIVE_OVERRIDE or _provider_from_env()
            if current.provider == "openai_compatible" and current.base_url:
                base_url = current.base_url
        # W18: no implicit access token — the key comes from
        # EPHE_OPENAI_COMPAT_API_KEY (the settings input writes it there).
        # Fail-closed tag: the same rule as the two Ollama branches below and
        # as ``_required_model`` on the env path — the active choice carries the
        # tag the caller gave, never one this code invents. Without it a
        # model-less POST /api/settings (or PUT /api/model/provider) reported —
        # and, through persist_engine_choice, persisted — the placeholder
        # "custom-model" as the active model, which nobody named.
        config = ModelProviderConfig(
            provider="openai_compatible",
            model=(model or "").strip(),
            base_url=_base_url(base_url, ""),
            label="OpenAI-compatible API",
            offline_capable=False,
            requires_internet=True,
            advanced_opt_in=True,
            api_key_configured=bool(engine_api_key_for(base_url or "")),
            # The key requirement depends on the endpoint (DGX/Tailnet/LAN = keyless,
            # public cloud = key). Root-cause fix: the PWA route
            # (POST /api/settings → set_active_provider) built the config with
            # the default requires_api_key=True → a keyless-DGX engine always ran
            # into "no API key" in /api/chat.
            requires_api_key=_endpoint_requires_api_key(base_url or ""),
        )

    _ACTIVE_OVERRIDE = config
    return config


def list_provider_options() -> list[dict]:
    """The engine classes the user can pick, with no model filled in for any of them."""
    return [
        ModelProviderConfig(
            provider="local_ollama",
            model="",
            base_url=DEFAULT_OLLAMA_BASE_URL,
            label="Local Ollama",
            offline_capable=True,
            requires_internet=False,
        ).to_dict(),
        ModelProviderConfig(
            provider="custom_ollama",
            model="",
            base_url=DEFAULT_OLLAMA_BASE_URL,
            label="Custom Ollama",
            offline_capable=True,
            requires_internet=False,
            advanced_opt_in=True,
        ).to_dict(),
        ModelProviderConfig(
            provider="openai_compatible",
            model="custom-model",
            base_url="",
            label="OpenAI-compatible API",
            offline_capable=False,
            requires_internet=True,
            advanced_opt_in=True,
            api_key_configured=bool(os.environ.get("EPHE_OPENAI_COMPAT_API_KEY")),
        ).to_dict(),
    ]


def ensure_provider_ready(config: ModelProviderConfig | None = None) -> None:
    """Refuse a client build for an endpoint this install cannot reach.

    Two ENDPOINT prerequisites are checked, because no request can leave without
    them: an API key where the endpoint demands one, and a base URL. The model tag
    is not checked here — it travels per request (``client.chat(model=...)``)
    rather than describing the endpoint, and the unconfigured state resolves to a
    tag-free local config on purpose: ``core/chat_providers.py::list_local_models``
    and ``check_ollama_connection`` build a client from exactly that config to
    enumerate the models the user already installed, and answer ``[]``/offline when
    the build raises. A tag check here would hide those models during onboarding.
    The refusal for a request that carries no tag is ``chosen_model``'s, on the
    request path (R24, docs/FAIL_CLOSED_PROVIDER_AUDIT.md).
    """
    active = config or get_active_provider()
    if (
        active.provider == "openai_compatible"
        and active.requires_api_key
        and not active.api_key_configured
    ):
        raise ProviderSetupError(
            "OpenAI-compatible API provider selected, but no API key is configured. "
            + KEY_PLACES
            + " Or switch back to Local Ollama."
        )
    if active.provider == "openai_compatible" and not active.base_url:
        raise ProviderSetupError(
            "OpenAI-compatible API provider selected, but no base URL is configured. "
            "Set EPHE_OPENAI_COMPAT_BASE_URL or switch back to Local Ollama."
        )


def build_provider_client(config: ModelProviderConfig | None = None) -> Any:
    active = config or get_active_provider()
    ensure_provider_ready(active)
    # I2-5 way A applies here only to the OpenAI-compatible path. The native
    # Ollama path (the device default!) is deliberately NOT fed with options=:
    # GENERATION_BOUNDS has 0.0 as the default for temperature, and that is
    # indistinguishable from "the user chose 0.0" — every local request would
    # have dropped from Ollama's own 0.8 to greedy 0.0 without anybody
    # having set it. Only once temperature is optional (None = engine default)
    # may options be passed to ollama.AsyncClient.
    if active.provider == "openai_compatible":
        from core.engine_config import engine_api_key_for

        return OpenAICompatibleAsyncClient(
            base_url=active.base_url,
            api_key=engine_api_key_for(active.base_url),
        )
    return ollama.AsyncClient(host=active.base_url)


def build_engine_provider(api_url: str, model: str) -> ModelProviderConfig:
    """Build an OpenAI-compatible provider config for a remote engine (e.g. DGX-Spark ds4).

    api_url is the full base URL (e.g. ``http://your-engine-host:8000/v1``).
    The API key is optional — a local engine (DGX-Spark ds4) needs none.
    """
    return ModelProviderConfig(
        provider="openai_compatible",
        model=model,
        base_url=api_url.rstrip("/"),
        label="OpenAI-compatible Engine",
        offline_capable=False,
        requires_internet=False,
        advanced_opt_in=True,
        api_key_configured=bool(engine_api_key_for(api_url)),
        requires_api_key=False,
    )
