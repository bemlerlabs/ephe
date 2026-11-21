"""The host side of the plugin bridge: what a worker may ask for, and who says yes.

core/sandbox/bridge_host.py

A confined worker has no credential, no store, no browser and since `380bb9f0` no socket, so
every capability it needs is answered here, in the process that already holds them. That
makes this file a trust boundary in its own right, and it is written to the rule the rest of
the platform follows: a call is granted against what the manifest declared, not against what
the plugin asks for at the moment.

The order is the point. A method nobody registered is refused before anything is read; a
method the bundle's own `permissions.tool_families` did not ask for is refused next, and its
audit row carries the code beside the families the mount actually declared; only then are the
arguments checked, the call run, and the answer capped. A refusal never touches the network,
the disk or the store, and an allowed call never returns more than the pipe can carry.

`fetch` reads one URL through the host's guarded path. `search` runs one query
through the host's own search function. `fetch_url` runs the kernel page tool, the
one that already owns the cache and the coded failure lines. `memory_add`,
`memory_replace`, `memory_remove` and `memory_list` run the kernel memory tool, one
method per action. `memory_action` carries an action outside those four to the same
function and refuses a known action. `browser_go`, `browser_screenshot`,
`browser_click`, `browser_type`, `browser_press`, `browser_scroll`,
`browser_evaluate` and `browser_exec` run the kernel browser tools, one method
per action. The address check and the release gate stay in those functions.
`vision_click` and `vision_type` run the kernel desktop tools. The confirmation
stays inside those functions. The target description and the typed text stay
out of the audit row. `analyze_image` runs the kernel image tool. The path
check stays in that function. The path and the question stay out of the audit
row. `run_shell`, `read_file`, `write_file`, `edit_file`, `list_directory`,
`file_search`, `load_workspace`, `analyze_project`, `run_tests`, `run_linter`,
`format_code` and `scaffold_project` run the kernel shell and file tools, one
method per action. The command check and the path check stay in those
functions. `run_shell` asks the chat gate the model path uses before it runs.
A credential-shaped file path is refused rather than read, and a write under a
declared data root is refused because that line is a read grant. The command,
the path and the file body stay out of the audit row.
`create_pdf`, `create_docx`, `create_qrcode`, `extract_pdf_text`,
`build_document`, `export_source_brief`, `create_source_notebook`,
`query_source_notebook` and `verify_artifact` run the kernel document
tools, one method per action. The body, the path and the source text
stay out of the audit row. `create_xlsx` and `generate_chart` run the
kernel sheet and chart tools, one method per action. The rows, the
labels and the path stay out of the audit row.
`create_pptx_deck`, `create_pitch_deck`, `inspect_pptx_template`,
`edit_pptx_template`, `qa_pptx_deck`, `create_diagram` and `create_svg`
run the kernel deck tools, one method per action. The slide text, the
notes and the path stay out of the audit row. `generate_image` runs the
kernel picture tool. The prompt stays out of the audit row.
`synthesize` runs the local piper writer. `transcribe` runs the kernel
speech reader. The spoken text and the transcript stay out of the audit row.
A worker with no socket and no desktop still gets those sentences. None
of them hands the worker a credential. The table is where the next one goes.
"""
from __future__ import annotations

import contextvars
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlsplit

from core.sandbox import bridge

#: Calls one worker may make through the bridge during one tool run. Beyond it the answer is
#: a refusal with a number in it, because an unbounded loop of host calls is a second agent
#: loop the manifest never declared.
MAX_CALLS_PER_RUN = 32

#: Characters of fetched text handed back. The cap is what makes `fetch` a capability rather
#: than a way to move a whole site through a pipe that was sized for an answer. The bridge's
#: own byte ceiling bites first for a page of multi-byte text; both bounds are enforced and
#: one flag reports them, because an answer that cannot fit the pipe is a refusal the plugin
#: cannot act on.
MAX_FETCH_TEXT_CHARS = 200_000

#: The chat approval window is 300 seconds. A desktop call runs while the worker
#: waits on this reply, so the worker clock outlasts that window and still leaves
#: the click time to finish. The host wait is the shorter of the two, so a late
#: call is answered and the child can exit before the process is killed.
VISION_HOST_WAIT_SECONDS = 400.0
VISION_CALL_TIMEOUT_SECONDS = 420.0

#: How much longer the worker clock runs after the host has given up, so the
#: timeout sentence is written before the child is killed.
_IMAGE_CALL_SLACK_SECONDS = 20.0

_caller_loop: contextvars.ContextVar = contextvars.ContextVar(
    "ephe_plugin_caller_loop", default=None
)

_ABORT_SENTENCE = "Action aborted by User Intervention"


def bind_caller_loop(loop: object):
    # The loop whose task set the confirmation callback.
    return _caller_loop.set(loop)


def reset_caller_loop(token) -> None:
    _caller_loop.reset(token)


@dataclass(frozen=True)
class BridgeIdentity:
    """Who is asking, as the mount recorded it — not as the child spells it.

    The fields come from the descriptor the host built, so a plugin cannot widen its own
    grant by naming a different family in the request: the request carries a method and
    arguments, and nothing else is believed.
    """

    plugin_id: str
    tool: str
    family: str
    families: frozenset[str]
    fingerprint: str = ""

    def audit_tool(self) -> str:
        return f"{self.plugin_id}:{self.tool}"


@dataclass(frozen=True)
class Method:
    """One bridged capability: the family it requires and the function that answers."""

    name: str
    required_family: str
    handler: Callable[[dict[str, Any]], dict[str, Any]]
    #: argument name -> whether a non-empty string is required
    required_args: tuple[str, ...] = ()


@dataclass
class RunState:
    """Per-run bookkeeping: the call budget and the audit lines, kept off the envelope."""

    calls: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    confirmation: BaseException | None = None

    def take(self) -> bool:
        with self.lock:
            if self.calls >= MAX_CALLS_PER_RUN:
                return False
            self.calls += 1
            return True

    def note_confirmation(self, exc: BaseException) -> None:
        # The drain thread sees the raise. The worker thread surfaces it.
        with self.lock:
            self.confirmation = exc

    def take_confirmation(self) -> BaseException | None:
        with self.lock:
            exc = self.confirmation
            self.confirmation = None
            return exc


def fetch(args: dict[str, Any]) -> dict[str, Any]:
    """Read one URL through the host's guarded path and hand back the text.

    The guard is not reimplemented here. `core.net_guard.guarded_fetch` is the one way out of
    this process — it checks the scheme, the resolved address of every hop so a redirect onto
    loopback is refused, and the volume — and a refusal from it crosses the bridge as a code,
    not as a page.

    Runs in the drain thread, so it owns a short-lived event loop rather than reaching for one
    it does not have.
    """
    import asyncio

    from core.net_guard import guarded_fetch

    url = str(args.get("url") or "").strip()
    started = time.monotonic()

    async def _get() -> tuple[int, str, str]:
        return await guarded_fetch(url)

    status, body, note = asyncio.run(_get())
    if status == 0:
        # `guarded_fetch` answers status 0 for both halves of a failed request: a refusal it
        # decided and a transport it could not complete. Naming them apart is what lets the
        # plugin author tell "the host will not fetch this" from "the site did not answer".
        refused = str(body).startswith("[refused]")
        return {
            "ok": False,
            "code": bridge.METHOD_DENIED if refused else bridge.INTERNAL,
            "detail": str(note or body)[:200],
        }
    text = _to_text(body)
    rest = {"status": status, "note": str(note or "")[:200],
            "elapsed_ms": round((time.monotonic() - started) * 1000), "truncated": False}
    clipped, truncated = _cap_text(text, rest)
    rest["truncated"] = truncated
    return {"ok": True, "result": {**rest, "text": clipped}}


def search(args: dict[str, Any]) -> dict[str, Any]:
    """Run one query on the host and hand back the kernel tool's own text.

    The worker that asked has no socket, and this function opens none of its own. It calls
    `web_search`, which already owns the deadline, the backend order and the reach line on
    a result the fetch guard would refuse. The query stays an argument: the audit row names
    the method and records no target, because a query can be the thing a later reader of
    the trail was never meant to see.

    The package binds the name `core.tools.web_search` to the function, over the submodule.
    `import_module` is what still returns the module, which is also what a test has to patch.
    """
    import asyncio
    from importlib import import_module

    from core.tools.base import WebSearchError

    query = str(args.get("query") or "")
    started = time.monotonic()
    call = import_module("core.tools.web_search").web_search
    kwargs: dict[str, Any] = {}
    if args.get("max_results") is not None:
        kwargs["max_results"] = args.get("max_results")
    try:
        text = asyncio.run(call(query, **kwargs))
    except WebSearchError as exc:
        return {"ok": False, "code": bridge.INTERNAL, "detail": str(exc)[:200]}
    rest = {"elapsed_ms": round((time.monotonic() - started) * 1000), "truncated": False}
    clipped, truncated = _cap_text(str(text), rest)
    rest["truncated"] = truncated
    return {"ok": True, "result": {**rest, "text": clipped}}


def fetch_url_text(args: dict[str, Any]) -> dict[str, Any]:
    """Run the kernel page tool and hand back its sentence.

    `fetch` stays the guarded reader with a status and a note. This method is the
    page tool: `fetch_url` already owns the cache, the HTML reduction and the
    coded failure lines, and a worker calls that function through here. A blank
    URL is that function's own sentence, so this method does not refuse it first.
    `prompt` is accepted and ignored, which is the signature the kernel tool documents.
    """
    import asyncio

    from core.tools.fetch_tools import fetch_url as kernel_fetch_url

    url = str(args.get("url") or "")
    prompt = str(args.get("prompt") or "")
    started = time.monotonic()
    try:
        text = asyncio.run(kernel_fetch_url(url, prompt))
    except Exception as exc:  # noqa: BLE001 — the child gets the class, never a path
        return {"ok": False, "code": bridge.INTERNAL, "detail": type(exc).__name__}
    rest = {"elapsed_ms": round((time.monotonic() - started) * 1000), "truncated": False}
    clipped, truncated = _cap_text(str(text), rest)
    rest["truncated"] = truncated
    result: dict[str, Any] = {**rest, "text": clipped}
    # The sentence is what the model reads. The code rides beside it so the
    # host can put it back on that sentence after the worker returns.
    code = str(getattr(text, "code", "") or "")
    if code:
        result["code"] = code
    params = getattr(text, "params", None)
    if isinstance(params, dict) and params:
        result["params"] = {str(key): str(value) for key, value in params.items()}
    return {"ok": True, "result": result}


_KNOWN_MEMORY_ACTIONS = frozenset({"add", "replace", "remove", "list"})


def _memory_call(action: str, args: dict[str, Any]) -> dict[str, Any]:
    """Run one memory action on the host and hand back the kernel sentence.

    The body, the old text and the column names stay arguments. The audit row
    names the method. It records no entry, because a memory body is the thing a
    later reader of the trail was never meant to see. A blank field reaches the
    kernel, which already owns the sentence for it.
    """
    import asyncio

    from core.tools.state_tools import memory as kernel_memory

    started = time.monotonic()
    try:
        text = asyncio.run(kernel_memory(
            action,
            str(args.get("target") or ""),
            content=str(args.get("content") or ""),
            old_text=str(args.get("old_text") or ""),
            memory_type=str(args.get("memory_type") or ""),
            supersedes=str(args.get("supersedes") or ""),
        ))
    except Exception as exc:  # noqa: BLE001 — the child gets the class, never a path
        return {"ok": False, "code": bridge.INTERNAL, "detail": type(exc).__name__}
    return {"ok": True, "result": _coded_page(text, started)}


def _coded_page(text: Any, started: float) -> dict[str, Any]:
    """The sentence, and the code beside it when the kernel tool put one on."""
    rest = {"elapsed_ms": round((time.monotonic() - started) * 1000), "truncated": False}
    clipped, truncated = _cap_text(str(text), rest)
    rest["truncated"] = truncated
    result: dict[str, Any] = {**rest, "text": clipped}
    code = str(getattr(text, "code", "") or "")
    if not code:
        return result
    result["code"] = code
    result["happened"] = bool(getattr(text, "happened", False))
    params = getattr(text, "params", None)
    if isinstance(params, dict) and params:
        result["params"] = {str(key): str(value) for key, value in params.items()}
    return result


def memory_add(args: dict[str, Any]) -> dict[str, Any]:
    return _memory_call("add", args)


def memory_replace(args: dict[str, Any]) -> dict[str, Any]:
    return _memory_call("replace", args)


def memory_remove(args: dict[str, Any]) -> dict[str, Any]:
    return _memory_call("remove", args)


def memory_list(args: dict[str, Any]) -> dict[str, Any]:
    return _memory_call("list", args)


def memory_action(args: dict[str, Any]) -> dict[str, Any]:
    """Hand an action outside the four to the kernel.

    A known action has its own method. Running it here would let the audit row
    name one door while the kernel performed another, so this method refuses
    that shape before the store is touched.
    """
    action = str(args.get("action") or "").strip().lower()
    if action in _KNOWN_MEMORY_ACTIONS:
        return {
            "ok": False,
            "code": bridge.METHOD_DENIED,
            "detail": "a known memory action has its own method",
        }
    return _memory_call(action, args)


def _browser_page(call: Callable[[], Any]) -> dict[str, Any]:
    """Run one browser kernel function and hand back its sentence.

    The address check, the release gate and the session namespace stay in the
    kernel function. This method opens no browser of its own. Typed text, a
    script and a code block stay arguments. The audit row names the method.
    A navigation URL is the one argument the row keeps, and it keeps the host.
    """
    import asyncio

    started = time.monotonic()
    try:
        text = asyncio.run(call())
    except Exception as exc:  # noqa: BLE001 — the child gets the class, never a path
        return {"ok": False, "code": bridge.INTERNAL, "detail": type(exc).__name__}
    rest = {"elapsed_ms": round((time.monotonic() - started) * 1000), "truncated": False}
    clipped, truncated = _cap_text(str(text), rest)
    rest["truncated"] = truncated
    return {"ok": True, "result": {**rest, "text": clipped}}


def browser_go(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.browser_tools import browser_go as kernel_go

    return _browser_page(lambda: kernel_go(str(args.get("url") or "")))


def browser_screenshot(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.browser_tools import browser_screenshot as kernel_shot

    return _browser_page(lambda: kernel_shot())


def browser_click(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.browser_tools import browser_click as kernel_click

    return _browser_page(lambda: kernel_click(str(args.get("target_description") or "")))


def browser_type(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.browser_tools import browser_type as kernel_type

    return _browser_page(lambda: kernel_type(str(args.get("text") or "")))


def browser_press(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.browser_tools import browser_press as kernel_press

    return _browser_page(lambda: kernel_press(str(args.get("key") or "")))


def browser_scroll(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.browser_tools import browser_scroll as kernel_scroll

    kwargs: dict[str, Any] = {}
    if args.get("direction") is not None:
        kwargs["direction"] = args.get("direction")
    if args.get("amount") is not None:
        kwargs["amount"] = args.get("amount")
    return _browser_page(lambda: kernel_scroll(**kwargs))


def browser_evaluate(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.browser_tools import browser_evaluate as kernel_eval

    return _browser_page(lambda: kernel_eval(str(args.get("js") or "")))


def browser_exec(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.browser_tools import browser_exec as kernel_exec

    kwargs: dict[str, Any] = {"code": str(args.get("code") or "")}
    if args.get("session") is not None:
        kwargs["session"] = str(args.get("session"))
    if args.get("timeout_s") is not None:
        kwargs["timeout_s"] = args.get("timeout_s")
    return _browser_page(lambda: kernel_exec(**kwargs))


def _cancel_task(task_box: dict[str, Any]) -> None:
    task = task_box.get("task")
    if task is not None:
        task.cancel()


def image_host_wait_seconds() -> float:
    # advanced.api_timeout, because the kernel client itself has no clock.
    from core.settings_schema import deep_number

    return float(deep_number("advanced.api_timeout"))


def image_call_timeout_seconds() -> float:
    return image_host_wait_seconds() + _IMAGE_CALL_SLACK_SECONDS


_PICTURE_HOST_WAIT_SECONDS = 200.0


def picture_host_wait_seconds() -> float:
    # The generation client waits 120 seconds and a download waits 60.
    return _PICTURE_HOST_WAIT_SECONDS


def picture_call_timeout_seconds() -> float:
    return picture_host_wait_seconds() + _IMAGE_CALL_SLACK_SECONDS


_VOICE_HOST_WAIT_SECONDS = 90.0


def voice_host_wait_seconds() -> float:
    # Piper's own wait is 80 seconds. This clock lets that wait finish.
    return _VOICE_HOST_WAIT_SECONDS


def voice_call_timeout_seconds() -> float:
    return voice_host_wait_seconds() + _IMAGE_CALL_SLACK_SECONDS


def _run_kernel(
    factory: Callable[[], Any],
    *,
    wait_seconds: float = VISION_HOST_WAIT_SECONDS,
    timeout_message: str = "the desktop call ran out of time",
) -> Any:
    # The drain thread is the caller. The chat task published its loop, and the
    # confirmation callback waits on that loop. The coroutine runs there, in the
    # context this thread already holds. With no published loop it runs here.
    import asyncio
    import concurrent.futures

    loop = _caller_loop.get()
    if loop is None or not loop.is_running():
        return asyncio.run(factory())

    ctx = contextvars.copy_context()
    done: concurrent.futures.Future = concurrent.futures.Future()
    task_box: dict[str, Any] = {}

    def _start() -> None:
        async def _body() -> None:
            try:
                done.set_result(await factory())
            except Exception as exc:
                if not done.done():
                    done.set_exception(exc)

        task_box["task"] = loop.create_task(_body(), context=ctx)

    loop.call_soon_threadsafe(_start)
    try:
        return done.result(timeout=wait_seconds)
    except concurrent.futures.TimeoutError as exc:
        loop.call_soon_threadsafe(_cancel_task, task_box)
        raise TimeoutError(timeout_message) from exc


def _vision_sentence(factory: Callable[[], Any]) -> dict[str, Any]:
    # The confirmation stays in the kernel function. A missing callback raises,
    # and that raise is carried back to the turn. The abort sentence is the one
    # the kernel already writes when the person says no. The description and
    # the typed text stay arguments. The audit row names the method.
    started = time.monotonic()
    try:
        text = _run_kernel(factory)
    except Exception as exc:  # noqa: BLE001 — the child gets a code, never the target
        if exc.__class__.__name__ == "SandboxConfirmationRequired":
            return {
                "ok": False,
                "code": bridge.INTERNAL,
                "detail": "SandboxConfirmationRequired",
                "confirm": exc,
            }
        if str(exc) == _ABORT_SENTENCE:
            detail = _ABORT_SENTENCE
        elif isinstance(exc, TimeoutError):
            detail = "the desktop call ran out of time"
        else:
            return {"ok": False, "code": bridge.INTERNAL, "detail": type(exc).__name__}
        return {"ok": False, "code": bridge.INTERNAL, "detail": detail}
    rest = {"elapsed_ms": round((time.monotonic() - started) * 1000), "truncated": False}
    clipped, truncated = _cap_text(str(text), rest)
    rest["truncated"] = truncated
    return {"ok": True, "result": {**rest, "text": clipped}}


def vision_click(args: dict[str, Any]) -> dict[str, Any]:
    from core.vision import vision_click as kernel_click

    return _vision_sentence(
        lambda: kernel_click(str(args.get("target_description") or ""))
    )


def vision_type(args: dict[str, Any]) -> dict[str, Any]:
    from core.vision import vision_type as kernel_type

    text = str(args.get("text") or "")
    if "press_enter" in args and args.get("press_enter") is not None:
        return _vision_sentence(
            lambda: kernel_type(text, press_enter=bool(args.get("press_enter")))
        )
    return _vision_sentence(lambda: kernel_type(text))


def _image_sentence(factory: Callable[[], Any]) -> dict[str, Any]:
    # The path check stays in the kernel function. A missing file and a path
    # outside the allowed roots come back as the sentence that function already
    # raises. The path and the question stay arguments. The audit row names
    # the method.
    started = time.monotonic()
    try:
        text = _run_kernel(
            factory,
            wait_seconds=image_host_wait_seconds(),
            timeout_message="the image call ran out of time",
        )
    except Exception as exc:  # noqa: BLE001 — the child gets a sentence, never a traceback
        if exc.__class__.__name__ in {"FileNotFoundError", "FileNotAllowedError"}:
            text = f"[tool-error 'analyze_image': {exc}]"
        elif isinstance(exc, TimeoutError):
            text = "[tool-error 'analyze_image': the image call ran out of time]"
        else:
            return {"ok": False, "code": bridge.INTERNAL, "detail": type(exc).__name__}
    rest = {"elapsed_ms": round((time.monotonic() - started) * 1000), "truncated": False}
    clipped, truncated = _cap_text(str(text), rest)
    rest["truncated"] = truncated
    return {"ok": True, "result": {**rest, "text": clipped}}


def analyze_image(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.system_tools import analyze_image as kernel_image

    path = str(args.get("path") or "")
    question = args.get("question")
    region = args.get("region")
    has_question = "question" in args and question is not None
    has_region = "region" in args and region is not None

    def _call():
        if has_question and has_region:
            return kernel_image(path, question=str(question), region=region)
        if has_question:
            return kernel_image(path, question=str(question))
        if has_region:
            return kernel_image(path, region=region)
        return kernel_image(path)

    return _image_sentence(_call)


def _cap_text(text: str, rest: dict) -> tuple[str, bool]:
    """Trim fetched text to what the reader was promised and to what the pipe carries.

    Two bounds, in that order: the character ceiling is the reading cap the plugin author can
    quote, and the byte ceiling is the envelope this reply travels in. Slicing bytes cannot cut
    a character in half, so the cut is decoded with the incomplete tail dropped.
    """
    clipped = text[:MAX_FETCH_TEXT_CHARS]
    truncated = len(clipped) < len(text)
    envelope = len(json.dumps(rest, ensure_ascii=False).encode("utf-8"))
    room = max(0, bridge.MAX_BRIDGE_BYTES - envelope - 64)
    if len(clipped.encode("utf-8")) > room:
        clipped = clipped.encode("utf-8")[:room].decode("utf-8", "ignore")
        truncated = True
    return clipped, truncated


def _to_text(body: str) -> str:
    """HTML becomes its text; anything else arrives as it came.

    The body decides, because `guarded_fetch` hands back text and a note and no content type.
    A URL heuristic would turn `…/html5/spec` into a parse of plain text.
    """
    if body.lstrip().startswith(("<!doctype", "<html", "<HTML")):
        from core.tools.fetch_tools import _html_to_text

        return _html_to_text(body)
    return body


_SHELL_HOST_MARGIN_SECONDS = 10.0
_SHELL_WORKER_SLACK_SECONDS = 20.0
FILE_HOST_WAIT_SECONDS = 15.0

_SENTENCE_ERRORS = {
    "FileNotFoundError",
    "FileNotAllowedError",
    "DirectoryNotFoundError",
    "IsADirectoryError",
    "ShellTimeoutError",
    "ValueError",
}


def shell_host_wait_seconds() -> float:
    # SHELL_TIMEOUT_SECONDS plus the margin, so the kernel sentence wins the race.
    from core.tools.base import SHELL_TIMEOUT_SECONDS

    return float(SHELL_TIMEOUT_SECONDS) + _SHELL_HOST_MARGIN_SECONDS


def shell_call_timeout_seconds() -> float:
    return shell_host_wait_seconds() + _SHELL_WORKER_SLACK_SECONDS


def test_host_wait_seconds() -> float:
    # TEST_TIMEOUT_SECONDS plus the same margin. The runner outlives this wait.
    from core.tools.test_tools import TEST_TIMEOUT_SECONDS

    return float(TEST_TIMEOUT_SECONDS) + _SHELL_HOST_MARGIN_SECONDS


def test_call_timeout_seconds() -> float:
    return test_host_wait_seconds() + _SHELL_WORKER_SLACK_SECONDS


_DOC_HOST_WAIT_SECONDS = 90.0
_BRIEF_HOST_WAIT_SECONDS = 180.0
_DOC_TOOLS = {
    "create_pdf", "create_docx", "create_qrcode", "extract_pdf_text",
    "export_source_brief", "create_source_notebook", "query_source_notebook",
    "verify_artifact",
    "create_pptx_deck", "create_pitch_deck", "inspect_pptx_template",
    "edit_pptx_template", "qa_pptx_deck", "create_diagram", "create_svg",
}


def doc_host_wait_seconds() -> float:
    # A PDF with a cover still finishes inside a minute on this machine.
    return _DOC_HOST_WAIT_SECONDS


def doc_call_timeout_seconds() -> float:
    return doc_host_wait_seconds() + _SHELL_WORKER_SLACK_SECONDS


def brief_host_wait_seconds() -> float:
    # The brief reads local sources and may ask the host search before it renders.
    return _BRIEF_HOST_WAIT_SECONDS


def brief_call_timeout_seconds() -> float:
    return brief_host_wait_seconds() + _SHELL_WORKER_SLACK_SECONDS


def _clock(name: str) -> tuple[float, str]:
    if name == "run_tests":
        return test_host_wait_seconds(), "the test call ran out of time"
    if name == "build_document":
        return brief_host_wait_seconds(), "the document call ran out of time"
    if name in _DOC_TOOLS:
        return doc_host_wait_seconds(), "the document call ran out of time"
    if name in {"run_shell", "format_code", "run_linter", "file_search", "analyze_project", "load_workspace"}:
        return shell_host_wait_seconds(), "the shell call ran out of time"
    return FILE_HOST_WAIT_SECONDS, "the file call ran out of time"


def _text_arg(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    return "" if value is None else str(value)


def _kept(args: dict[str, Any], key: str) -> Any:
    if key in args and args.get(key) is not None:
        return args.get(key)
    return None


def _credential_refusal(name: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """Refuse a file method whose path is credential-shaped, or None when it is not.

    The model path forces a dialog for such a name even when the tool is read-only
    (`core/tools/chat_gate.py`). A bridged call has no dialog of its own and its worker
    clock can outlast a person's answer, so the bridge takes the other branch of the
    same rule and refuses. The code names the rule and the text names the next step.

    A path outside the granted roots is left to the kernel: its own refusal names the
    boundary that answered, and a credential rule on top would hide that.
    """
    from core.path_guard import secret_paths

    if not secret_paths(args):
        return None
    from core.tools.base import _is_path_allowed
    from core.tools.file_ops import _resolve_against_workspace

    path = _text_arg(args, "path")
    if path and not _is_path_allowed(_resolve_against_workspace(path)):
        return None
    return {
        "ok": False,
        "code": bridge.PATH_DENIED,
        "detail": (
            f"{name} names a credential-shaped path, and a bridged call carries no dialog "
            "of its own. Ask the user to handle the file in the chat, or choose a path "
            "that is not credential-shaped."
        ),
    }


def _write_scope_refusal(args: dict[str, Any], key: str = "path") -> dict[str, Any] | None:
    """The read-only-root refusal, taken before a credential dialog could ask about it."""
    from core.tools.base import _plugin_write_refusal
    from core.tools.file_ops import _resolve_against_workspace

    denial = _plugin_write_refusal(_resolve_against_workspace(_text_arg(args, key)))
    if not denial:
        return None
    return {"ok": False, "code": bridge.PATH_DENIED, "detail": denial}


def _consent_refusal(name: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """Ask the active approval gate before a bridged call that changes the host.

    Two gates exist, and the bridge carries whichever one the outer call already used.
    A registry call with an `ApprovalPolicy` asks that policy, so a `--yes` run keeps
    its standing answer and an interactive run sees the command that would run. A chat
    turn has no policy: the request-scoped dialog answers, because the worker runs while
    that turn is open. With nobody to ask, the call is refused instead of run
    unconfirmed, and the refusal keeps the gate's code beside the reason.

    A helper's call arrives here a second time: the delegated gate already asked for the
    tool whose worker now bridges `run_shell`. The delegated answer covers this channel
    once, and the line says so, so one decision is not two dialogs.
    """
    from core.tools.chat_gate import claim_delegated_consent

    consented = claim_delegated_consent()
    if consented:
        try:
            from core.audit_log import audit_event

            audit_event(
                "approval",
                tool=name,
                decision="approved",
                status="delegated-consent",
                detail=f"the delegated gate confirmed {consented}; the bridge did not ask again",
            )
        except Exception:  # noqa: BLE001 — the log never blocks the call it records
            pass
        return None

    from core.tools.session_ctx import get_current_policy

    policy = get_current_policy()
    if policy is not None:
        from core.tools.approval import request_approval

        async def _decide() -> Any:
            return await request_approval(name, args, policy)

        try:
            decision = _run_kernel(_decide)
        except TimeoutError:
            return {
                "ok": False,
                "code": bridge.CONSENT_REQUIRED,
                "detail": "the approval gate did not answer; ask the user, or choose a call that needs no approval",
            }
        if decision.approved:
            return None
        return {
            "ok": False,
            "code": bridge.CONSENT_REQUIRED,
            "detail": f"not_approved: {decision.report}",
        }

    from core.tools.chat_gate import confirm_for_chat

    async def _ask() -> tuple[bool, Any]:
        return await confirm_for_chat(name, args)

    try:
        approved, denial = _run_kernel(_ask)
    except TimeoutError:
        return {
            "ok": False,
            "code": bridge.CONSENT_REQUIRED,
            "detail": "the approval dialog did not answer; ask the user, or choose a call that needs no approval",
        }
    if approved:
        return None
    code = str(getattr(denial, "code", "") or "not_approved")
    return {
        "ok": False,
        "code": bridge.CONSENT_REQUIRED,
        "detail": f"{code}: {denial}",
    }


def _tool_sentence(name: str, factory: Callable[[], Any]) -> dict[str, Any]:
    # Path and command checks stay in the kernel function. The audit row names the method.
    wait_seconds, timeout_message = _clock(name)
    started = time.monotonic()
    try:
        text = _run_kernel(
            factory,
            wait_seconds=wait_seconds,
            timeout_message=timeout_message,
        )
    except Exception as exc:  # noqa: BLE001 — the child gets a sentence, never a traceback
        kind = exc.__class__.__name__
        if kind in {"ShellConfirmationRequired", "SandboxConfirmationRequired"}:
            return {
                "ok": False,
                "code": bridge.INTERNAL,
                "detail": kind,
                "confirm": exc,
            }
        if kind == "ReadOnlyRootError":
            # A declared data root is a read grant, so the child gets a code.
            return {"ok": False, "code": bridge.PATH_DENIED, "detail": str(exc)}
        if kind in _SENTENCE_ERRORS:
            text = f"[tool-error '{name}': {exc}]"
        elif isinstance(exc, TimeoutError):
            text = f"[tool-error '{name}': {timeout_message}]"
        else:
            return {"ok": False, "code": bridge.INTERNAL, "detail": kind}
    if isinstance(text, list):
        text = "\n".join(str(item) for item in text)
    rest = {"elapsed_ms": round((time.monotonic() - started) * 1000), "truncated": False}
    clipped, truncated = _cap_text(str(text), rest)
    rest["truncated"] = truncated
    return {"ok": True, "result": {**rest, "text": clipped}}


def run_shell(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools._shell_exec import run_shell as kernel_shell

    command = _text_arg(args, "command")
    cwd = _kept(args, "cwd")
    background = _kept(args, "run_in_background")
    gate_args: dict[str, Any] = {"command": command}
    if cwd is not None:
        gate_args["cwd"] = str(cwd)
    refusal = _consent_refusal("run_shell", gate_args)
    if refusal is not None:
        return refusal

    def _call():
        extra: dict[str, Any] = {}
        if cwd is not None:
            extra["cwd"] = str(cwd)
        if background is not None:
            extra["run_in_background"] = bool(background)
        return kernel_shell(command, **extra)

    return _tool_sentence("run_shell", _call)


def read_file(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.file_ops import read_file as kernel_read

    path = _text_arg(args, "path")
    offset = _kept(args, "offset")
    limit = _kept(args, "limit")
    refusal = _credential_refusal("read_file", args)
    if refusal is not None:
        return refusal

    def _call():
        extra: dict[str, Any] = {}
        if offset is not None:
            extra["offset"] = int(offset)
        if limit is not None:
            extra["limit"] = int(limit)
        return kernel_read(path, **extra)

    return _tool_sentence("read_file", _call)


def write_file(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.file_ops import write_file as kernel_write

    path = _text_arg(args, "path")
    content = _text_arg(args, "content")
    refusal = _write_scope_refusal(args) or _credential_refusal("write_file", args)
    if refusal is not None:
        return refusal
    return _tool_sentence("write_file", lambda: kernel_write(path, content))


def edit_file(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.file_ops import edit_file as kernel_edit

    path = _text_arg(args, "path")
    old_string = _text_arg(args, "old_string")
    new_string = _text_arg(args, "new_string")
    replace_all = _kept(args, "replace_all")
    refusal = _write_scope_refusal(args) or _credential_refusal("edit_file", args)
    if refusal is not None:
        return refusal

    def _call():
        if replace_all is None:
            return kernel_edit(path, old_string, new_string)
        return kernel_edit(path, old_string, new_string, replace_all=bool(replace_all))

    return _tool_sentence("edit_file", _call)


def list_directory(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.file_ops import list_directory as kernel_list

    path = _text_arg(args, "path")
    refusal = _credential_refusal("list_directory", args)
    if refusal is not None:
        return refusal
    return _tool_sentence("list_directory", lambda: kernel_list(path))


def file_search(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.file_ops import file_search as kernel_search

    query = _text_arg(args, "query")
    root = _kept(args, "path")
    refusal = _credential_refusal("file_search", args)
    if refusal is not None:
        return refusal

    def _call():
        if root is None:
            return kernel_search(query)
        return kernel_search(query, path=str(root))

    return _tool_sentence("file_search", _call)


def load_workspace(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.system_tools import load_workspace as kernel_load

    path = _text_arg(args, "path")
    extensions = _kept(args, "extensions")
    max_depth = _kept(args, "max_depth")

    def _call():
        extra: dict[str, Any] = {}
        if extensions is not None:
            extra["extensions"] = list(extensions)
        if max_depth is not None:
            extra["max_depth"] = int(max_depth)
        return kernel_load(path, **extra)

    return _tool_sentence("load_workspace", _call)


def analyze_project(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.system_tools import analyze_project as kernel_analyze

    path = _text_arg(args, "path")
    return _tool_sentence("analyze_project", lambda: kernel_analyze(path))


def run_tests(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.test_tools import run_tests as kernel_tests

    command = _text_arg(args, "command")
    cwd = _kept(args, "cwd")

    def _call():
        if cwd is None:
            return kernel_tests(command)
        return kernel_tests(command, cwd=str(cwd))

    return _tool_sentence("run_tests", _call)


def run_linter(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.utility_tools import run_linter as kernel_lint

    path = _text_arg(args, "path")
    fix = _kept(args, "fix")
    max_issues = _kept(args, "max_issues")

    def _call():
        extra: dict[str, Any] = {}
        if fix is not None:
            extra["fix"] = bool(fix)
        if max_issues is not None:
            extra["max_issues"] = int(max_issues)
        return kernel_lint(path, **extra)

    return _tool_sentence("run_linter", _call)


def format_code(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.utility_tools import format_code as kernel_format

    path = _text_arg(args, "path")
    check_only = _kept(args, "check_only")

    def _call():
        if check_only is None:
            return kernel_format(path)
        return kernel_format(path, check_only=bool(check_only))

    return _tool_sentence("format_code", _call)


def scaffold_project(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools._factory_templates import scaffold_project as kernel_scaffold

    target_dir = _text_arg(args, "target_dir")
    template = _kept(args, "template")
    project_name = _kept(args, "project_name")
    description = _kept(args, "description")
    author = _kept(args, "author")
    refusal = _write_scope_refusal(args, "target_dir")
    if refusal is not None:
        return refusal

    def _call():
        extra: dict[str, Any] = {}
        if template is not None:
            extra["template"] = str(template)
        if project_name is not None:
            extra["project_name"] = str(project_name)
        if description is not None:
            extra["description"] = str(description)
        if author is not None:
            extra["author"] = str(author)
        return kernel_scaffold(target_dir, **extra)

    return _tool_sentence("scaffold_project", _call)


def create_pdf(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.pdf_tools import create_pdf as kernel

    title = _text_arg(args, "title")
    content = _text_arg(args, "content")

    def _call():
        extra: dict[str, Any] = {}
        filename = _kept(args, "filename")
        template = _kept(args, "template")
        document = _kept(args, "document")
        if filename is not None:
            extra["filename"] = str(filename)
        if template is not None:
            extra["template"] = str(template)
        if document is not None:
            extra["document"] = bool(document)
        return kernel(title, content, **extra)

    return _tool_sentence("create_pdf", _call)


def create_docx(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.office_tools import create_docx as kernel

    title = _text_arg(args, "title")
    content = _text_arg(args, "content")

    def _call():
        extra: dict[str, Any] = {}
        filename = _kept(args, "filename")
        if filename is not None:
            extra["filename"] = str(filename)
        return kernel(title, content, **extra)

    return _tool_sentence("create_docx", _call)


def create_qrcode(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.office_tools import create_qrcode as kernel

    data = _text_arg(args, "data")

    def _call():
        extra: dict[str, Any] = {}
        for key in ("filename", "fill_color", "back_color"):
            value = _kept(args, key)
            if value is not None:
                extra[key] = str(value)
        return kernel(data, **extra)

    return _tool_sentence("create_qrcode", _call)


def extract_pdf_text(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.utility_tools import extract_pdf_text as kernel

    path = _text_arg(args, "path")
    max_chars = _kept(args, "max_chars")

    def _call():
        if max_chars is None:
            return kernel(path)
        return kernel(path, max_chars=int(max_chars))

    return _tool_sentence("extract_pdf_text", _call)


def build_document(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.factory_tools import build_document as kernel

    topic = _text_arg(args, "topic")

    def _call():
        extra: dict[str, Any] = {}
        source_paths = _kept(args, "source_paths")
        include_web = _kept(args, "include_web_research")
        filename = _kept(args, "filename")
        if source_paths is not None:
            extra["source_paths"] = str(source_paths)
        if include_web is not None:
            extra["include_web_research"] = bool(include_web)
        if filename is not None:
            extra["filename"] = str(filename)
        return kernel(topic, **extra)

    return _tool_sentence("build_document", _call)


def export_source_brief(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.source_tools import export_source_brief as kernel

    notebook_path = _text_arg(args, "notebook_path")

    def _call():
        extra: dict[str, Any] = {}
        question = _kept(args, "question")
        filename = _kept(args, "filename")
        if question is not None:
            extra["question"] = str(question)
        if filename is not None:
            extra["filename"] = str(filename)
        return kernel(notebook_path, **extra)

    return _tool_sentence("export_source_brief", _call)


def create_source_notebook(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.source_tools import create_source_notebook as kernel

    paths = args.get("paths")
    if paths is None:
        paths = []

    def _call():
        extra: dict[str, Any] = {}
        title = _kept(args, "title")
        notebook_id = _kept(args, "notebook_id")
        extensions = _kept(args, "extensions")
        if title is not None:
            extra["title"] = str(title)
        if notebook_id is not None:
            extra["notebook_id"] = str(notebook_id)
        if extensions is not None:
            extra["extensions"] = extensions
        return kernel(paths, **extra)

    return _tool_sentence("create_source_notebook", _call)


def query_source_notebook(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.source_tools import query_source_notebook as kernel

    notebook_path = _text_arg(args, "notebook_path")
    question = _text_arg(args, "question")
    max_chunks = _kept(args, "max_chunks")

    def _call():
        if max_chunks is None:
            return kernel(notebook_path, question)
        return kernel(notebook_path, question, max_chunks=int(max_chunks))

    return _tool_sentence("query_source_notebook", _call)


def verify_artifact(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.verify_tools import verify_artifact as kernel

    path = _text_arg(args, "path")
    checks = _kept(args, "checks")

    def _call():
        if checks is None:
            return kernel(path)
        return kernel(path, checks=str(checks))

    return _tool_sentence("verify_artifact", _call)


def create_xlsx(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.office_tools import create_xlsx as kernel

    title = _text_arg(args, "title")
    data = args.get("data")
    if data is None:
        data = ""

    def _call():
        extra: dict[str, Any] = {}
        filename = _kept(args, "filename")
        path = _kept(args, "path")
        formats = _kept(args, "formats")
        if filename is not None:
            extra["filename"] = str(filename)
        if path is not None:
            extra["path"] = str(path)
        if formats is not None:
            extra["formats"] = formats
        return kernel(title, data, **extra)

    return _tool_sentence("create_xlsx", _call)


def generate_chart(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.chart_tools import generate_chart as kernel

    chart_type = _text_arg(args, "chart_type")
    title = _text_arg(args, "title")
    labels = args.get("labels")
    if labels is None:
        labels = []
    values = args.get("values")
    if values is None:
        values = []

    def _call():
        extra: dict[str, Any] = {}
        for key in ("xlabel", "ylabel", "color", "theme"):
            value = _kept(args, key)
            if value is not None:
                extra[key] = str(value)
        series = _kept(args, "series")
        if series is not None:
            extra["series"] = series
        return kernel(chart_type, title, labels, values, **extra)

    return _tool_sentence("generate_chart", _call)


def _deck_extra(args: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    for key in keys:
        value = _kept(args, key)
        if value is not None:
            extra[key] = str(value)
    return extra


def create_pptx_deck(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.deck_tools import create_pptx_deck as kernel

    topic = _text_arg(args, "topic")

    def _call():
        extra = _deck_extra(
            args,
            (
                "audience", "thesis", "filename", "deck_profile", "design_theme",
                "source_notes", "evidence_level", "template_path", "brand_name",
                "brand_primary", "brand_secondary", "deck_quality_profile",
                "source_notebook_path",
            ),
        )
        slides = _kept(args, "slides")
        if slides is not None:
            extra["slides"] = slides
        for key in ("enterprise_grade", "asset_paths"):
            value = _kept(args, key)
            if value is not None:
                extra[key] = value
        return kernel(topic, **extra)

    return _tool_sentence("create_pptx_deck", _call)


def create_pitch_deck(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.deck_tools import create_pitch_deck as kernel

    topic = _text_arg(args, "topic")

    def _call():
        extra = _deck_extra(
            args,
            (
                "audience", "thesis", "filename", "deck_profile", "design_theme",
                "source_notes", "evidence_level", "deck_quality_profile",
                "source_notebook_path",
            ),
        )
        slides = _kept(args, "slides")
        if slides is not None:
            extra["slides"] = slides
        for key in ("include_animation_preview", "enterprise_grade", "brand_kit", "asset_paths"):
            value = _kept(args, key)
            if value is not None:
                extra[key] = value
        return kernel(topic, **extra)

    return _tool_sentence("create_pitch_deck", _call)


def inspect_pptx_template(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.deck_tools import inspect_pptx_template as kernel

    path = _text_arg(args, "path")

    def _call():
        extra = _deck_extra(args, ("filename",))
        return kernel(path, **extra)

    return _tool_sentence("inspect_pptx_template", _call)


def edit_pptx_template(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.deck_tools import edit_pptx_template as kernel

    template_path = _text_arg(args, "template_path")
    replacements = args.get("replacements")
    if replacements is None:
        replacements = {}

    def _call():
        extra = _deck_extra(args, ("filename",))
        return kernel(template_path, replacements, **extra)

    return _tool_sentence("edit_pptx_template", _call)


def qa_pptx_deck(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.deck_tools import qa_pptx_deck as kernel

    pptx_path = _text_arg(args, "pptx_path")

    def _call():
        return kernel(pptx_path)

    return _tool_sentence("qa_pptx_deck", _call)


def create_diagram(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.diagram_tools import create_diagram as kernel

    kind = _text_arg(args, "kind")
    title = _text_arg(args, "title")
    items = args.get("items")
    if items is None:
        items = ""

    def _call():
        extra = _deck_extra(args, ("filename", "theme"))
        return kernel(kind, title, items, **extra)

    return _tool_sentence("create_diagram", _call)


def create_svg(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.system_tools import create_svg as kernel

    svg_code = _text_arg(args, "svg_code")

    def _call():
        extra = _deck_extra(args, ("filename",))
        return kernel(svg_code, **extra)

    return _tool_sentence("create_svg", _call)


def _picture_sentence(factory: Callable[[], Any]) -> dict[str, Any]:
    # The endpoint check stays in the kernel function. The prompt stays an
    # argument. The audit row names the method.
    started = time.monotonic()
    try:
        text = _run_kernel(
            factory,
            wait_seconds=picture_host_wait_seconds(),
            timeout_message="the picture call ran out of time",
        )
    except Exception as exc:  # noqa: BLE001 — the child gets a sentence, never a traceback
        if isinstance(exc, TimeoutError):
            text = "[tool-error 'generate_image': the picture call ran out of time]"
        else:
            return {"ok": False, "code": bridge.INTERNAL, "detail": type(exc).__name__}
    rest = {"elapsed_ms": round((time.monotonic() - started) * 1000), "truncated": False}
    clipped, truncated = _cap_text(str(text), rest)
    rest["truncated"] = truncated
    return {"ok": True, "result": {**rest, "text": clipped}}


def _voice_sentence(name: str, factory: Callable[[], Any]) -> dict[str, Any]:
    # The speech stays an argument. The audit row names the method.
    started = time.monotonic()
    try:
        text = _run_kernel(
            factory,
            wait_seconds=voice_host_wait_seconds(),
            timeout_message="the voice call ran out of time",
        )
    except Exception as exc:  # noqa: BLE001 — the child gets a sentence, never a traceback
        if isinstance(exc, TimeoutError):
            text = f"[tool-error '{name}': the voice call ran out of time]"
        else:
            return {"ok": False, "code": bridge.INTERNAL, "detail": type(exc).__name__}
    rest = {"elapsed_ms": round((time.monotonic() - started) * 1000), "truncated": False}
    clipped, truncated = _cap_text(str(text), rest)
    rest["truncated"] = truncated
    return {"ok": True, "result": {**rest, "text": clipped}}


def synthesize(args: dict[str, Any]) -> dict[str, Any]:
    from core.voice_synth import synthesize_local

    text = _text_arg(args, "text")

    async def _call() -> str:
        return synthesize_local(text)

    return _voice_sentence("synthesize", _call)


def transcribe(args: dict[str, Any]) -> dict[str, Any]:
    from core.voice_synth import transcribe_file

    name = _text_arg(args, "name")

    async def _call() -> str:
        return transcribe_file(name)

    return _voice_sentence("transcribe", _call)


def generate_image(args: dict[str, Any]) -> dict[str, Any]:
    from core.tools.image_tools import generate_image as kernel

    prompt = _text_arg(args, "prompt")

    def _call():
        extra: dict[str, Any] = {}
        filename = _kept(args, "filename")
        size = _kept(args, "size")
        if filename is not None:
            extra["filename"] = str(filename)
        if size is not None:
            extra["size"] = str(size)
        return kernel(prompt, **extra)

    return _picture_sentence(_call)


METHODS: dict[str, Method] = {
    "fetch": Method(
        name="fetch",
        required_family="network",
        handler=fetch,
        required_args=("url",),
    ),
    "search": Method(
        name="search",
        required_family="network",
        handler=search,
        required_args=("query",),
    ),
    "fetch_url": Method(
        name="fetch_url",
        required_family="network",
        handler=fetch_url_text,
        required_args=(),
    ),
    "memory_add": Method(
        name="memory_add",
        required_family="memory",
        handler=memory_add,
        required_args=(),
    ),
    "memory_replace": Method(
        name="memory_replace",
        required_family="memory",
        handler=memory_replace,
        required_args=(),
    ),
    "memory_remove": Method(
        name="memory_remove",
        required_family="memory",
        handler=memory_remove,
        required_args=(),
    ),
    "memory_list": Method(
        name="memory_list",
        required_family="memory",
        handler=memory_list,
        required_args=(),
    ),
    "memory_action": Method(
        name="memory_action",
        required_family="memory",
        handler=memory_action,
        required_args=(),
    ),
    "browser_go": Method(
        name="browser_go",
        required_family="browser",
        handler=browser_go,
        required_args=(),
    ),
    "browser_screenshot": Method(
        name="browser_screenshot",
        required_family="browser",
        handler=browser_screenshot,
        required_args=(),
    ),
    "browser_click": Method(
        name="browser_click",
        required_family="browser",
        handler=browser_click,
        required_args=(),
    ),
    "browser_type": Method(
        name="browser_type",
        required_family="browser",
        handler=browser_type,
        required_args=(),
    ),
    "browser_press": Method(
        name="browser_press",
        required_family="browser",
        handler=browser_press,
        required_args=(),
    ),
    "browser_scroll": Method(
        name="browser_scroll",
        required_family="browser",
        handler=browser_scroll,
        required_args=(),
    ),
    "browser_evaluate": Method(
        name="browser_evaluate",
        required_family="browser",
        handler=browser_evaluate,
        required_args=(),
    ),
    "browser_exec": Method(
        name="browser_exec",
        required_family="browser",
        handler=browser_exec,
        required_args=(),
    ),
    "vision_click": Method(
        name="vision_click",
        required_family="vision",
        handler=vision_click,
        required_args=(),
    ),
    "vision_type": Method(
        name="vision_type",
        required_family="vision",
        handler=vision_type,
        required_args=(),
    ),
    "analyze_image": Method(
        name="analyze_image",
        required_family="vision",
        handler=analyze_image,
        required_args=(),
    ),
    "run_shell": Method(
        name="run_shell",
        required_family="shell",
        handler=run_shell,
        required_args=(),
    ),
    "read_file": Method(
        name="read_file",
        required_family="read",
        handler=read_file,
        required_args=(),
    ),
    "write_file": Method(
        name="write_file",
        required_family="write",
        handler=write_file,
        required_args=(),
    ),
    "edit_file": Method(
        name="edit_file",
        required_family="write",
        handler=edit_file,
        required_args=(),
    ),
    "list_directory": Method(
        name="list_directory",
        required_family="read",
        handler=list_directory,
        required_args=(),
    ),
    "file_search": Method(
        name="file_search",
        required_family="read",
        handler=file_search,
        required_args=(),
    ),
    "load_workspace": Method(
        name="load_workspace",
        required_family="read",
        handler=load_workspace,
        required_args=(),
    ),
    "analyze_project": Method(
        name="analyze_project",
        required_family="read",
        handler=analyze_project,
        required_args=(),
    ),
    "run_tests": Method(
        name="run_tests",
        required_family="shell",
        handler=run_tests,
        required_args=(),
    ),
    "run_linter": Method(
        name="run_linter",
        required_family="shell",
        handler=run_linter,
        required_args=(),
    ),
    "format_code": Method(
        name="format_code",
        required_family="shell",
        handler=format_code,
        required_args=(),
    ),
    "scaffold_project": Method(
        name="scaffold_project",
        required_family="write",
        handler=scaffold_project,
        required_args=(),
    ),
    "create_pdf": Method(
        name="create_pdf",
        required_family="docs",
        handler=create_pdf,
        required_args=(),
    ),
    "create_docx": Method(
        name="create_docx",
        required_family="docs",
        handler=create_docx,
        required_args=(),
    ),
    "create_qrcode": Method(
        name="create_qrcode",
        required_family="docs",
        handler=create_qrcode,
        required_args=(),
    ),
    "extract_pdf_text": Method(
        name="extract_pdf_text",
        required_family="docs",
        handler=extract_pdf_text,
        required_args=(),
    ),
    "build_document": Method(
        name="build_document",
        required_family="docs",
        handler=build_document,
        required_args=(),
    ),
    "export_source_brief": Method(
        name="export_source_brief",
        required_family="docs",
        handler=export_source_brief,
        required_args=(),
    ),
    "create_source_notebook": Method(
        name="create_source_notebook",
        required_family="docs",
        handler=create_source_notebook,
        required_args=(),
    ),
    "query_source_notebook": Method(
        name="query_source_notebook",
        required_family="docs",
        handler=query_source_notebook,
        required_args=(),
    ),
    "verify_artifact": Method(
        name="verify_artifact",
        required_family="docs",
        handler=verify_artifact,
        required_args=(),
    ),
    "create_xlsx": Method(
        name="create_xlsx",
        required_family="docs",
        handler=create_xlsx,
        required_args=(),
    ),
    "generate_chart": Method(
        name="generate_chart",
        required_family="docs",
        handler=generate_chart,
        required_args=(),
    ),
    "create_pptx_deck": Method(
        name="create_pptx_deck",
        required_family="docs",
        handler=create_pptx_deck,
        required_args=(),
    ),
    "create_pitch_deck": Method(
        name="create_pitch_deck",
        required_family="docs",
        handler=create_pitch_deck,
        required_args=(),
    ),
    "inspect_pptx_template": Method(
        name="inspect_pptx_template",
        required_family="docs",
        handler=inspect_pptx_template,
        required_args=(),
    ),
    "edit_pptx_template": Method(
        name="edit_pptx_template",
        required_family="docs",
        handler=edit_pptx_template,
        required_args=(),
    ),
    "qa_pptx_deck": Method(
        name="qa_pptx_deck",
        required_family="docs",
        handler=qa_pptx_deck,
        required_args=(),
    ),
    "create_diagram": Method(
        name="create_diagram",
        required_family="docs",
        handler=create_diagram,
        required_args=(),
    ),
    "create_svg": Method(
        name="create_svg",
        required_family="docs",
        handler=create_svg,
        required_args=(),
    ),
    "generate_image": Method(
        name="generate_image",
        required_family="network",
        handler=generate_image,
        required_args=(),
    ),
    "synthesize": Method(
        name="synthesize",
        required_family="voice",
        handler=synthesize,
        required_args=(),
    ),
    "transcribe": Method(
        name="transcribe",
        required_family="voice",
        handler=transcribe,
        required_args=(),
    ),
}


def dispatch(
    payload: dict[str, Any], identity: BridgeIdentity, state: RunState
) -> dict[str, Any]:
    """Answer one bridge request. Always returns an envelope; never raises to the drain."""
    method_name = str(payload.get("method") or "")
    args = payload.get("args") or {}
    # Read for the audit line only. Nothing here decides access from a URL: the guard the
    # handler calls does, and it re-reads the same string.
    target = host_target(str(args.get("url") or ""))
    method = METHODS.get(method_name)
    if method is None:
        # The name is the child's. The list is ours, and a cut through the
        # middle of it would hide a method this build does answer.
        shown = method_name[:80]
        offered = ", ".join(sorted(METHODS))
        sentence = f"no bridged method {shown!r}; this build offers {offered}"
        return _denied(
            bridge.METHOD_UNKNOWN,
            sentence,
            identity,
            method_name,
            target,
            "unregistered",
            limit=len(sentence),
        )
    if method.required_family not in identity.families:
        return _denied(
            bridge.METHOD_DENIED,
            f"{method.name} works in the {method.required_family!r} family, which plugin "
            f"{identity.plugin_id!r} does not declare",
            identity,
            method.name,
            target,
            "undeclared-family",
        )
    for name in method.required_args:
        if not str(args.get(name) or "").strip():
            return _denied(
                bridge.ARGS_INVALID,
                f"{method.name} needs a non-empty {name!r}",
                identity,
                method.name,
                target,
                "arguments",
            )
    if not state.take():
        return _denied(
            bridge.RATE_LIMITED,
            f"a tool run may make {MAX_CALLS_PER_RUN} bridged calls; this one asked for more",
            identity,
            method.name,
            target,
            "budget",
        )
    try:
        answer = method.handler(dict(args))
    except Exception as exc:  # noqa: BLE001 — the child gets a code, the log gets the class
        return _denied(
            bridge.INTERNAL,
            f"{type(exc).__name__}",
            identity,
            method.name,
            target,
            "internal",
        )
    if isinstance(answer, dict):
        confirm = answer.pop("confirm", None)
        if confirm is not None:
            state.note_confirmation(confirm)
    if not answer.get("ok"):
        return _denied(
            str(answer.get("code") or bridge.INTERNAL),
            str(answer.get("detail") or ""),
            identity,
            method.name,
            target,
            "handler",
        )
    result = answer.get("result")
    if _too_large(result):
        return _denied(
            bridge.PAYLOAD_TOO_LARGE,
            f"the answer exceeds {bridge.MAX_BRIDGE_BYTES} bytes",
            identity,
            method.name,
            target,
            "oversize",
        )
    _audit_allowed(identity, method.name, target)
    return {"ok": True, "result": result}


def _too_large(result: Any) -> bool:
    try:
        return len(json.dumps(result, ensure_ascii=False)) > bridge.MAX_BRIDGE_BYTES
    except (TypeError, ValueError):
        return True


def _denied(
    code: str,
    detail: str,
    identity: BridgeIdentity,
    method: str,
    target: str = "",
    cause: str = "",
    limit: int = 200,
) -> dict[str, Any]:
    _audit_denied(identity, method, code, target, cause)
    return {"ok": False, "code": code, "detail": detail[:limit]}


def _audit_allowed(identity: BridgeIdentity, method: str, target: str) -> None:
    from core.audit_log import audit_event

    audit_event(
        "bridge_call",
        tool=identity.audit_tool(),
        decision="allowed",
        status="ok",
        detail=_target_detail(
            method,
            target,
            granted=True,
            family=identity.family,
            fingerprint=identity.fingerprint,
        ),
    )


def _audit_denied(
    identity: BridgeIdentity, method: str, code: str, target: str = "", cause: str = ""
) -> None:
    from core.audit_log import audit_event

    audit_event(
        "bridge_call",
        tool=identity.audit_tool(),
        decision="denied",
        status=code,
        detail=_target_detail(
            method,
            target,
            granted=False,
            note=code,
            cause=cause,
            declared=tuple(sorted(identity.families)),
            family=identity.family,
            fingerprint=identity.fingerprint,
        ),
    )


def _target_detail(
    method: str,
    target: str,
    *,
    granted: bool,
    note: str = "",
    cause: str = "",
    declared: tuple[str, ...] = (),
    family: str = "",
    fingerprint: str = "",
) -> str:
    """One audit line, and never a full address.

    A guarded URL can carry a token in its query the way any URL can, and the audit trail is
    read by people and shipped in exports. The method and the host are what answer "who was
    allowed out"; the path and the query are dropped for that reason.

    Two denials share one code — the bundle was never granted the family, and the guard
    refused the address inside a method it was granted — so the row names the gate that
    answered (`cause`) beside the families the mount declared. A reader of the trail sees
    which rule stopped the call.
    """
    parts = [
        f"method={method}",
        f"target={target or 'n/a'}",
        f"granted={'yes' if granted else 'no'}",
    ]
    if cause:
        parts.append(f"cause={cause}")
    if note:
        parts.append(f"code={note}")
    if family:
        parts.append(f"family={family}")
    short = fingerprint[:12]
    if short:
        parts.append(f"fingerprint={short}")
    if declared:
        parts.append(f"declared={','.join(declared) or 'none'}")
    return " ".join(parts)[:300]


def host_target(url: str) -> str:
    """The host part of a URL, for the audit line. Exposed so a test can name what is kept."""
    try:
        return urlsplit(url).netloc
    except ValueError:
        return ""
