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

import threading

from fastapi import APIRouter, Header, HTTPException

from core import memory_embed_gemma
from core.audit_log import audit_event

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
    return status


@router.get("/models/embedding")
def get_embedding_model() -> dict:
    """What the surfaces need to offer the fetch: present, missing, size, consent."""
    return _status_payload()


def _fetch_in_background() -> None:
    try:
        memory_embed_gemma.ensure_model()
    except Exception as exc:  # noqa: BLE001 — the reason goes to the log and the status
        with _state_lock:
            _state["error"] = type(exc).__name__
        audit_event(
            "embedding_model_fetch_failed",
            detail={"reason": type(exc).__name__},
            status="failed",
        )
    else:
        with _state_lock:
            _state["done"] = True
        audit_event("embedding_model_fetched", detail={"label": memory_embed_gemma.MODEL_LABEL})
    finally:
        with _state_lock:
            _state["downloading"] = False


@router.post("/models/embedding/download")
def post_embedding_model_download(
    body: dict | None = None,
    x_requested_with: str | None = Header(default=None, alias=XHR_HEADER),
) -> dict:
    """Start the fetch a user asked for. Consent for this one fetch is the call.

    The XHR marker keeps a cross-origin form POST out; the confirm word keeps a stray
    script out. Neither replaces a person: this route is only ever reached by the
    popup's button or an explicit CLI flag.
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
