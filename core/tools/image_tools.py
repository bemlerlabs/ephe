"""Ephe – image_tools: generate_image (free-local OR cloud, user's choice).

One contract, both worlds — the OpenAI-compatible /images/generations endpoint
is spoken by local servers (SD-WebUI / LM-Studio / ComfyUI-OpenAI-Bridge: no key,
free, no forced cloud) AND by cloud gateways (own API keys: key
set). The user decides via base_url + api_key, not the code.

Why no Diffusers/Transformers here: the model is text-only (Qwen on the
DGX). Image generation is a separate, opt-in endpoint — not pulling a heavy
ML framework onto the end device is the product promise (offline-
first, AGENTS.md). No image endpoint configured → honest error message,
no room for simulation, no invented image.

Response formats that cover both: data[0].b64_json (local, inline) OR
data[0].url (cloud, download). No blocking of the event loop: httpx async.
"""
from __future__ import annotations

import base64
import os
import re
from pathlib import Path


def _downloads() -> Path:
    from core.engine_config import artifact_output_dir

    return artifact_output_dir()


def _safe_filename(filename: str, default: str, ext: str) -> str:
    safe_name = Path(filename or default).name
    safe_name = re.sub(r"\s+", "_", safe_name.strip())
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "", safe_name)
    safe_name = re.sub(r"_+", "_", safe_name).strip("._-")
    if not safe_name:
        safe_name = default
    if not safe_name.lower().endswith(ext):
        safe_name += ext
    return safe_name


def _image_endpoint() -> tuple[str, str, str]:
    """(base_url, api_key, model) for the image endpoint — user's choice.

    Priority (R16): 1) dedicated EPHE_IMAGE_* env vars (deployment override),
    2) ~/.ephe/image.json (settings UI), 3) the active chat engine (fallback,
    so a local OpenAI-compatible server can do images without extra setup).
    """
    base = os.environ.get("EPHE_IMAGE_BASE_URL", "").strip()
    key = os.environ.get("EPHE_IMAGE_API_KEY", "").strip()
    model = os.environ.get("EPHE_IMAGE_MODEL", "").strip()
    if not base:
        try:
            from core.image_config import load_image_config

            cfg = load_image_config()
            if cfg.base_url:
                return cfg.base_url.rstrip("/"), (key or cfg.api_key), (model or cfg.model)
        except Exception:
            pass
        try:
            from core.model_provider import get_active_provider

            provider = get_active_provider()
            base = provider.base_url
            if not key:
                from core.engine_config import engine_api_key_for

                key = engine_api_key_for(provider.base_url)
        except Exception:
            base = ""
    return base.rstrip("/"), key, model


def _generations_url(base: str) -> str:
    if base.endswith("/images/generations"):
        return base
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    return f"{base}/images/generations"


async def generate_image(
    prompt: str,
    filename: str = "ephe_image.png",
    size: str = "1024x1024",
) -> str:
    """Creates a real image from a text description (text-to-image).

    Uses the configured OpenAI-compatible image endpoint — locally free
    (SD-WebUI/LM-Studio) or cloud (cloud APIs with an own key) per user setup.
    Writes a real PNG/JPEG and returns a PNG_FILE marker
    that the chat stream shows as a downloadable artifact.
    """
    payload_prompt = (prompt or "").strip()
    if not payload_prompt:
        return "[image error: empty description — pass a prompt.] No image was produced; do not claim one."

    base, key, model = _image_endpoint()
    if not base:
        return (
            "[image error: no image endpoint configured. Set EPHE_IMAGE_BASE_URL (+ optional EPHE_IMAGE_API_KEY / EPHE_IMAGE_MODEL) to an OpenAI-compatible /images/generations service — e.g. a local SD-WebUI (free) or a cloud API.] No image was produced; do not claim one."
        )

    import httpx

    body: dict = {"prompt": payload_prompt, "n": 1, "size": size}
    if model:
        body["model"] = model
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0)) as client:
            r = await client.post(_generations_url(base), json=body, headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        return f"[image error: endpoint unreachable or rejected — {exc}]. No image was produced; do not claim one."

    items = (data or {}).get("data") or []
    if not items:
        return f"[image error: endpoint returned no image — answer: {str(data)[:200]}]. No image was produced; do not claim one."

    item = items[0]
    out = _downloads() / _safe_filename(filename, "ephe_image.png", ".png")
    try:
        b64 = item.get("b64_json")
        if b64:
            out.write_bytes(base64.b64decode(b64))
        elif item.get("url"):
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0), follow_redirects=True) as dl:
                img = await dl.get(item["url"])
                img.raise_for_status()
                out.write_bytes(img.content)
        else:
            return "[image error: endpoint returned neither b64_json nor url]. No image was produced; do not claim one."
    except Exception as exc:
        return f"[image error: image could not be stored — {exc}]. No image was produced; do not claim one."

    return f"PNG_FILE:{out}"
