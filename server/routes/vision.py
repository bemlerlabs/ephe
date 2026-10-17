"""server/routes/vision.py – POST /api/vision/analyze

Takes an image as multipart/form-data, stores it under the device image dir
(served at /images/<name>) and analyses it with the ACTIVE provider's model —
no shipped default travels to the engine.

Endpoints:
  POST /api/vision/analyze   – upload an image + ask a question
  POST /api/vision/base64    – Base64 string + question (for a frontend without file upload)
"""
from __future__ import annotations

import base64
import os
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from core.engine_config import EngineNotConfigured
from core.model_provider import (
    ProviderSetupError,
    build_provider_client,
    chosen_model,
    get_active_provider,
)
from server.refusals import Refused

router = APIRouter(tags=["Vision"])

# Sentinel, not a model: equality with it means "nothing was chosen — the active
# provider decides". Empty while EPHE_MODEL is unset; the product ships no tag
# (owner decision 2026-10-11).
DEFAULT_MODEL = os.environ.get("EPHE_MODEL", "")

# Allowed image formats
ALLOWED_MIME = {
    "image/png", "image/jpeg", "image/jpg",
    "image/webp", "image/gif", "image/bmp",
    "image/heic", "image/heif",  # iPhone camera format
}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


class VisionBase64Request(BaseModel):
    image_b64: str
    question: str = "Describe this image in detail."
    model: str = DEFAULT_MODEL


@router.post("/vision/analyze")
async def analyze_uploaded_image(
    file: UploadFile = File(..., description="Image file (PNG, JPG, WEBP, GIF, BMP)"),
    question: str = Form(
        default="Describe this image in detail.",
        description="Question about the image",
    ),
    model: str = Form(default=DEFAULT_MODEL),
):
    """
    Upload an image and analyse it via the engine you chose.

    - Accepts: PNG, JPG, WEBP, GIF, BMP (max 20 MB)
    - Returns: { analysis: str, filename: str, model: str }
    """
    # Validation
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=f"unsupported format: {content_type}. "
                   f"allowed: {', '.join(sorted(ALLOWED_MIME))}",
        )

    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"file too large: {len(raw) // 1024}KB. max: {MAX_FILE_SIZE // 1024}KB",
        )
    if len(raw) < 100:
        raise HTTPException(status_code=400, detail="file too small or empty.")

    # Store the temporary file (for analyze_image tool compatibility)
    tmp_dir = Path(os.environ.get(
        "EPHE_IMAGE_DIR",
        str(Path.home() / ".ephe" / "sessions" / "images")
    ))
    tmp_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename or "upload.png").suffix.lower() or ".png"
    filename = f"upload_{int(time.time())}_{uuid.uuid4().hex[:6]}{ext}"
    tmp_path = tmp_dir / filename
    tmp_path.write_bytes(raw)

    image_b64 = base64.b64encode(raw).decode("utf-8")

    try:
        provider = get_active_provider()
        client = build_provider_client(provider)
        model = (provider.model if model == DEFAULT_MODEL else model).strip()
        if not model:
            # An empty tag must not travel to the engine as though it were a
            # model — the same fail-closed refusal the start paths give
            # (chosen_model, owner decision 2026-10-11).
            model = chosen_model("the vision call")
        response = await client.chat(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": question,
                    "images": [image_b64],
                }
            ],
            stream=False,
        )
        analysis = str(response.message.content or "No description generated.")
    except ProviderSetupError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except EngineNotConfigured as exc:
        raise HTTPException(status_code=409, detail=f"{exc} {exc.hint}")
    except Exception as exc:
        raise Refused("vision_failed", error=str(exc))
    finally:
        # Nothing is removed here: the upload stays under EPHE_IMAGE_DIR so
        # /images/<filename> can serve it, like the screenshots in the same
        # folder — no cleanup job runs after the route returns.
        pass

    return {
        "analysis": analysis,
        "filename": filename,
        "image_url": f"/images/{filename}",
        "model": model,
        "question": question,
    }


@router.post("/vision/base64")
async def analyze_base64_image(req: VisionBase64Request):
    """
    Analyse an image passed as a Base64 string (for a frontend that cannot use FormData).

    Body: { image_b64: "...", question: "...", model: "<tag>" } — `model` is optional;
    omitted means the active provider decides.
    """
    if not req.image_b64:
        raise HTTPException(status_code=400, detail="image_b64 must not be empty.")

    # Basic validation of the Base64 string
    try:
        raw = base64.b64decode(req.image_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid Base64 string.")

    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"file too large: {len(raw) // 1024}KB. max: {MAX_FILE_SIZE // 1024}KB",
        )
    if len(raw) < 100:
        raise HTTPException(status_code=400, detail="image too small or empty.")

    try:
        provider = get_active_provider()
        client = build_provider_client(provider)
        model = (provider.model if req.model == DEFAULT_MODEL else req.model).strip()
        if not model:
            # Same rule as /analyze: never put an empty tag on the wire.
            model = chosen_model("the vision call")
        response = await client.chat(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": req.question,
                    "images": [req.image_b64],
                }
            ],
            stream=False,
        )
        analysis = str(response.message.content or "No description generated.")
    except ProviderSetupError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except EngineNotConfigured as exc:
        raise HTTPException(status_code=409, detail=f"{exc} {exc.hint}")
    except Exception as exc:
        raise Refused("vision_failed", error=str(exc))

    return {
        "analysis": analysis,
        "model": model,
        "question": req.question,
    }
