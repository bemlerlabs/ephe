"""server/routes/models.py – the embedding model a user may choose to fetch.

The weights stay out of the install on purpose: the first start must not pull 542 MB
on a connection nobody chose to spend. `core/memory_embed_gemma` already refuses to
fetch without consent, so the missing model degrades the memory to the lexical leg and
a log line says why.

This route is the offer, not the fetch. `GET` answers whether the model is loadable
and what a fetch would cost; `POST` starts one because a person pressed a button. It
never writes the consent setting: a click here fetches once, and an automatic fetch
still needs the documented switch. A surface that polls the status sees
`downloading`, then `present` or `error`.
"""
from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, Header, HTTPException

from core import memory_embed_gemma, memory_reembed
from core.audit_log import audit_event

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Models"])

XHR_HEADER = "X-Requested-With"
XHR_VALUE = "XMLHttpRequest"

_CONFIRM_WORD = "download"

#: One fetch at a time, and the answer to "what is it doing". The route process is
#: the only writer, so a lock around the flag is enough; the thread itself is joined
#: by nobody on purpose — a slow download must not hold a request open.
_state_lock = threading.Lock()
_state: dict[str, object] = {"downloading": False, "error": "", "done": False}


def _status_payload() -> dict:
    status = memory_embed_gemma.model_status()
    with _state_lock:
        status.update(
            downloading=bool(_state["downloading"]),
            downloaded=bool(_state["done"]),
            error=str(_state["error"]),
        )
    # The fetch is only half the state: a model on disk says nothing about the
    # chunks written before it, so the same answer carries the re-embed counters.
    status["reembed"] = memory_reembed.status()
    return status


@router.get("/models/embedding")
def get_embedding_model() -> dict:
    """What the surfaces need to offer the fetch: present, missing, size, consent."""
    return _status_payload()


def _failure_text(exc: Exception) -> str:
    """The sentence the surface prints in place of the exception's class name.

    `EmbeddingGemmaNotAvailable` already carries the reason a person can act on
    (`refusal()`); any other failure keeps its class for a bug report and adds the
    message that says what broke.
    """
    if isinstance(exc, memory_embed_gemma.EmbeddingGemmaNotAvailable):
        return str(exc)
    detail = str(exc).strip()
    return f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__


def _apply_new_model() -> None:
    """Hand the running process the model that just landed on disk.

    The embedding factory caches a loaded model (or a None after a failed load) for
    the process, the memory facade caches the provider that holds the lazy embedder,
    and this app caches the facade itself. Without all three resets a finished fetch
    changes nothing until restart — worse, the cached provider keeps the fallback
    label and would stamp the new vectors with the wrong model name.
    """
    from core import memory_embed
    from core.memory import Memory

    memory_embed.reset_cache()
    Memory.reset_scoped_instances()
    from server.routes.memory import _get_memory

    _get_memory.cache_clear()


def _fetch_in_background() -> None:
    try:
        memory_embed_gemma.ensure_model(allow_fetch=True)
    except Exception as exc:  # noqa: BLE001 — the reason goes to the log and the status
        reason = _failure_text(exc)
        with _state_lock:
            _state["error"] = reason
        logger.warning("embedding model fetch failed: %s", reason)
        audit_event(
            "embedding_model_fetch_failed",
            detail=f"reason={reason}",
            status="failed",
        )
    else:
        _apply_new_model()
        with _state_lock:
            _state["done"] = True
        # New vectors for the new model: without this pass the ranking leg filters
        # on the new label and finds none of the chunks already in the store.
        memory_reembed.start(memory_factory=_memory_factory())
        audit_event("embedding_model_fetched", detail=f"label={memory_embed_gemma.MODEL_LABEL}")
    finally:
        with _state_lock:
            _state["downloading"] = False


def _memory_factory():
    """The route's own facade factory, imported at call time so server modules do
    not depend on each other's import order."""
    from server.routes.memory import _get_memory

    return _get_memory


@router.post("/models/embedding/reembed")
def post_embedding_model_reembed(
    body: dict | None = None,
    x_requested_with: str | None = Header(default=None, alias=XHR_HEADER),
) -> dict:
    """Start the pass that gives the chunks already stored the active vectors.

    The fetch starts it by itself, so this is the resume path: a process that
    restarted mid-pass, or a store written while the vector arm was off, needs a
    button rather than a second download. Nothing is fetched here.
    """
    if x_requested_with != XHR_VALUE:
        raise HTTPException(status_code=403, detail="missing X-Requested-With")
    if (body or {}).get("confirm") != "reembed":
        raise HTTPException(status_code=400, detail="missing confirm: reembed")
    from core.memory_embed import is_disabled

    if not memory_embed_gemma.model_present():
        raise HTTPException(
            status_code=409,
            detail={"code": "model_missing", "detail": "the embedding model is not on disk"},
        )
    if is_disabled():
        raise HTTPException(
            status_code=409,
            detail={"code": "vector_arm_off", "detail": "EPHE_MEMORY_EMBEDDER disables the vector arm"},
        )
    started = memory_reembed.start(memory_factory=_memory_factory())
    return {"started": started, "reembed": memory_reembed.status()}


@router.post("/models/embedding/download")
def post_embedding_model_download(
    body: dict | None = None,
    x_requested_with: str | None = Header(default=None, alias=XHR_HEADER),
) -> dict:
    """Start the fetch a user asked for. This call is the consent for one fetch.

    It passes `allow_fetch=True` so the fetch does not stop at the setting the
    click deliberately does not write. The XHR marker keeps a cross-origin form
    POST out; the confirm word keeps a stray script out. Neither replaces a
    person: this route is only ever reached by the popup's button or an explicit
    CLI flag.
    """
    if x_requested_with != XHR_VALUE:
        raise HTTPException(status_code=403, detail="missing X-Requested-With")
    if (body or {}).get("confirm") != _CONFIRM_WORD:
        raise HTTPException(status_code=400, detail="missing confirm: download")
    if memory_embed_gemma.offline():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "offline",
                "detail": "EPHE_OFFLINE=1 forbids every fetch in this process",
            },
        )
    with _state_lock:
        if _state["downloading"]:
            return {"started": False, "reason": "already downloading"}
        _state.update(downloading=True, error="", done=False)
    thread = threading.Thread(target=_fetch_in_background, name="embedding-model-fetch", daemon=True)
    thread.start()
    return {"started": True, "size_mb": memory_embed_gemma.MODEL_SIZE_MB}
