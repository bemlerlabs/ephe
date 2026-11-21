"""server/routes/vision.py — the HTTP face of the vision pipeline, instrumented.

The endpoint census (docs/ENDPOINT_SURFACE_AND_GUARD_CENSUS_2026-10-09.md §4.2a)
found both vision endpoints with 0 tests and the base64 twin uncapped; these
tests are the missing instrumentation. Three contracts are pinned, each with
the written rule it enforces:

a) No shipped default model. A request naming no model runs on the ACTIVE
   provider's tag; an active tag that is empty is refused with the setup hint
   instead of putting an empty tag on the wire (owner decision 2026-10-11,
   implemented by `chosen_model`; tests/test_no_default_local_model.py:237 pins
   the core rule, these tests carry it through the HTTP surface).
b) Readable refusals at the pipeline's limits. The MIME allowlist and the
   20 MB cap answer as a JSON refusal on BOTH endpoints, without a provider
   round-trip for the rejected payload; a provider-side rejection arrives as
   the coded `vision_failed` refusal, never a traceback
   (docs/SECURITY_THREAT_MODEL.md I1: cause + fix, no raw stack trace).
c) No EXIF rewriting — and no invented one. "exif" has zero matches in this
   repo, and no doc promises stripping; the documented privacy stance is
   locality + explicit engine choice (README "Private by architecture",
   SECURITY.md "Local-First Default"), so an EXIF-bearing photo travels
   byte-identical to exactly two places: the active engine call and the
   device image dir.
"""
from __future__ import annotations

import asyncio
import base64
import io
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

_ACTIVE_TAG = "fixture-vl:9b"


def _png_bytes(size: int = 256) -> bytes:
    """A small PNG-ish payload (the routes never sniff bytes — MIME decides)."""
    return b"\x89PNG\r\n\x1a\n" + b"\x00" * size


def _exif_jpeg() -> bytes:
    """A real JPEG carrying an EXIF GPS IFD (latitude/longitude, reference N/E)."""
    from PIL import Image
    from PIL.TiffImagePlugin import IFDRational

    image = Image.new("RGB", (4, 4), "red")
    exif = image.getexif()
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"  # GPSLatitudeRef
    gps[2] = (IFDRational(48, 1), IFDRational(51, 1), IFDRational(0, 1))
    gps[3] = "E"  # GPSLongitudeRef
    gps[4] = (IFDRational(8, 1), IFDRational(14, 1), IFDRational(0, 1))
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif)
    data = out.getvalue()
    assert b"Exif\x00\x00" in data
    return data


def _provider(model: str):
    from core.model_provider import ModelProviderConfig

    return ModelProviderConfig(
        provider="local_ollama",
        model=model,
        base_url="http://localhost:11434",
        label="Local Ollama",
        offline_capable=True,
        requires_internet=False,
    )


class _RecordingClient:
    """Stands in for the provider client; records every chat() the route makes."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.answer = "Ein rotes Pixel."
        self.error: Exception | None = None

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(message=SimpleNamespace(content=self.answer))


@pytest.fixture
def vision(tmp_path, monkeypatch):
    """App under test + handles to steer the provider layer per test."""
    monkeypatch.setenv("EPHE_IMAGE_DIR", str(tmp_path / "images"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "user_profile.json"))
    monkeypatch.setenv("EPHE_CORRECTIONS_PATH", str(tmp_path / "corrections.md"))
    monkeypatch.setenv("EPHE_FEEDBACK_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_SKILLS_DIR", str(tmp_path / "skills"))

    import server.routes.vision as route

    fake = _RecordingClient()
    state = {"provider": _provider(_ACTIVE_TAG)}
    monkeypatch.setattr(route, "get_active_provider", lambda: state["provider"])
    monkeypatch.setattr(route, "build_provider_client", lambda config=None: fake)

    from server.main import create_app

    return SimpleNamespace(
        app=TestClient(create_app()),
        route=route,
        fake=fake,
        state=state,
        image_dir=tmp_path / "images",
    )


# (a) No model named → the active provider's tag, never the shipped default


def test_analyze_without_a_model_falls_to_the_active_provider(vision):
    """G: the active provider carries the user's tag; the request names no model
    W: POST /api/vision/analyze
    T: the engine is asked with the active tag — not the shipped default — and
       the response reports the same model"""
    assert vision.route.DEFAULT_MODEL != _ACTIVE_TAG, (
        "premise: the shipped default has to differ from the active tag, else "
        "this test cannot tell fall-through from pass-through"
    )

    response = vision.app.post(
        "/api/vision/analyze",
        files={"file": ("pixel.png", _png_bytes(), "image/png")},
        data={"question": "Was ist das?"},
    )

    assert response.status_code == 200
    assert vision.fake.calls, "the engine was never asked"
    assert vision.fake.calls[0]["model"] == _ACTIVE_TAG
    assert response.json()["model"] == _ACTIVE_TAG


def test_base64_without_a_model_falls_to_the_active_provider(vision):
    """G: same active provider, base64 endpoint
    W: POST /api/vision/base64 without a model field
    T: the engine is asked with the active tag, not the shipped default"""
    assert vision.route.DEFAULT_MODEL != _ACTIVE_TAG  # premise, see above

    response = vision.app.post(
        "/api/vision/base64",
        json={"image_b64": base64.b64encode(_png_bytes()).decode()},
    )

    assert response.status_code == 200
    assert vision.fake.calls, "the engine was never asked"
    assert vision.fake.calls[0]["model"] == _ACTIVE_TAG
    assert response.json()["model"] == _ACTIVE_TAG


def test_an_explicit_model_name_passes_through_untouched(vision):
    """G: the client names its own model
    W: POST /api/vision/base64 with model="caller-pick:2b"
    T: exactly that tag reaches the engine"""
    response = vision.app.post(
        "/api/vision/base64",
        json={"image_b64": base64.b64encode(_png_bytes()).decode(), "model": "caller-pick:2b"},
    )

    assert response.status_code == 200
    assert vision.fake.calls[0]["model"] == "caller-pick:2b"
    assert response.json()["model"] == "caller-pick:2b"


def test_no_model_anywhere_is_refused_with_the_setup_hint(vision, monkeypatch):
    """G: the active provider carries no tag and no model is named
    W: POST /api/vision/base64 (and the same through the form endpoint)
    T: a readable setup refusal — nothing travels to an engine as an empty tag
       (chosen_model's rule: an empty tag must not be put on the wire)"""
    monkeypatch.delenv("EPHE_MODEL", raising=False)
    vision.state["provider"] = _provider("")

    response = vision.app.post(
        "/api/vision/base64",
        json={"image_b64": base64.b64encode(_png_bytes()).decode()},
    )

    assert response.status_code == 409
    message = response.json()["error"]["message"]
    assert "No model chosen for the vision call" in message
    assert "ephe configure" in message  # the actionable hint, a bare 500 would not name one
    assert vision.fake.calls == [], "an empty model tag was put on the wire"

    form_response = vision.app.post(
        "/api/vision/analyze",
        files={"file": ("pixel.png", _png_bytes(), "image/png")},
    )
    assert form_response.status_code == 409
    assert vision.fake.calls == []


def test_an_explicitly_empty_model_field_is_treated_as_named_none(vision):
    """G: the caller sends model="" (names nothing)
    W: POST /api/vision/base64
    T: the same setup refusal as naming no model at all"""
    vision.state["provider"] = _provider("")

    response = vision.app.post(
        "/api/vision/base64",
        json={"image_b64": base64.b64encode(_png_bytes()).decode(), "model": ""},
    )

    assert response.status_code == 409
    assert vision.fake.calls == []


# (b) Limits answer as readable refusals; provider rejections stay coded


def test_unsupported_mime_is_refused_readably_without_an_engine_call(vision):
    response = vision.app.post(
        "/api/vision/analyze",
        files={"file": ("scan.tiff", _png_bytes(), "image/tiff")},
    )

    assert response.status_code == 415
    message = response.json()["error"]["message"]
    assert "unsupported format" in message  # a sentence a reader can act on
    assert vision.fake.calls == [], "a rejected payload reached the engine"


def test_upload_over_the_size_cap_is_refused_readably(vision):
    oversize = _png_bytes(vision.route.MAX_FILE_SIZE)
    assert len(oversize) > vision.route.MAX_FILE_SIZE

    response = vision.app.post(
        "/api/vision/analyze",
        files={"file": ("huge.png", oversize, "image/png")},
    )

    assert response.status_code == 413
    assert "file too large" in response.json()["error"]["message"]
    assert vision.fake.calls == [], "an over-size payload reached the engine"


def test_base64_over_the_size_cap_is_refused_readably(vision):
    """The uncapped twin (census §4.2a item 10) carries the same 20 MB cap."""
    oversize = base64.b64encode(_png_bytes(vision.route.MAX_FILE_SIZE)).decode()

    response = vision.app.post("/api/vision/base64", json={"image_b64": oversize})

    assert response.status_code == 413
    assert "file too large" in response.json()["error"]["message"]
    assert vision.fake.calls == [], "an over-size payload reached the engine"


def test_a_provider_rejection_is_the_coded_refusal_not_a_traceback(vision):
    """G: the engine rejects the image (its own size/format limits)
    W: POST /api/vision/base64 with a payload the fake provider refuses
    T: the refusal channel's envelope — `vision_failed` with the reason beside
       the transport code, no Python traceback in the reader's hands"""
    vision.fake.error = RuntimeError("HTTP 413: image exceeds provider payload limit")

    response = vision.app.post(
        "/api/vision/base64",
        json={"image_b64": base64.b64encode(_png_bytes()).decode()},
    )

    assert response.status_code == 500
    body = response.json()["error"]
    assert body["reason_code"] == "vision_failed"
    assert body["message"].startswith("Image analysis failed:")
    assert "exceeds provider payload limit" in body["message"]
    assert body["reason_params"]["error"]  # the cause travels for the bundle


# (c) EXIF: original bytes to the chosen engine + device dir, nothing else


def test_exif_bearing_photo_arrives_byte_identical_at_engine_and_disk(vision):
    """G: a JPEG with an EXIF GPS IFD (the case a privacy reviewer asks about)
    W: POST /api/vision/analyze and then /api/vision/base64
    T: the engine receives exactly the uploaded bytes — EXIF intact, nothing
       stripped or rewritten — and the copy kept for /images serving is the
       same original; locality/explicit-engine-choice is the documented stance,
       and the code neither leaks further nor invents a strip it never promised"""
    from PIL import Image

    photo = _exif_jpeg()

    response = vision.app.post(
        "/api/vision/analyze",
        files={"file": ("foto.jpg", photo, "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    sent = base64.b64decode(vision.fake.calls[0]["messages"][0]["images"][0])
    assert sent == photo

    # The EXIF survived the transit: GPS latitude ref still reads "N" at the
    # engine — the pipeline did not strip what no doc promised to strip.
    assert Image.open(io.BytesIO(sent)).getexif().get_ifd(0x8825).get(1) == "N"

    # The kept copy under the device image dir is the same original, and it is
    # what /images serves — the only two places the bytes go.
    stored = vision.image_dir / body["filename"]
    assert stored.read_bytes() == photo
    assert body["image_url"] == f"/images/{body['filename']}"

    # The base64 endpoint is the same pipeline — same guarantee.
    vision.fake.calls.clear()
    b64_response = vision.app.post(
        "/api/vision/base64",
        json={"image_b64": base64.b64encode(photo).decode()},
    )
    assert b64_response.status_code == 200
    sent_b64 = base64.b64decode(vision.fake.calls[0]["messages"][0]["images"][0])
    assert sent_b64 == photo


def test_agent_client_path_uses_the_users_tag_and_refuses_readably_without_one(
    monkeypatch,
):
    """The other half of the pipeline: core.tools.analyze_image (the agent path,
    census §4.2a "the agent path uses core.tools") runs on `chosen_model` — the
    user's tag when there is one, a readable refusal string when there is not."""
    import core.tools.system_tools as system_tools
    from PIL import Image

    image_file = Path.home() / "tmp" / "vision_route_agent_path.png"
    image_file.parent.mkdir(exist_ok=True)
    Image.new("RGB", (4, 4), "red").save(image_file)

    calls: list[dict] = []

    class _Client:
        async def chat(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(message=SimpleNamespace(content="ok"))

    monkeypatch.setattr(system_tools, "_get_shared_client", lambda: _Client())

    try:
        # Nothing chosen anywhere (conftest's isolation removed EPHE_MODEL):
        # the tool answers with the readable line so named by `chosen_model` —
        # no traceback, nothing on the wire.
        result = asyncio.run(system_tools.analyze_image(path=str(image_file)))
        assert isinstance(result, str)
        assert "No model chosen for the screen-vision tool" in result
        assert "Traceback" not in result
        assert calls == [], "an empty tag reached the engine"

        # The user's own tag travels unchanged.
        monkeypatch.setenv("EPHE_MODEL", "agent-pick:1b")
        result = asyncio.run(system_tools.analyze_image(path=str(image_file)))
        assert result == "ok"
        assert calls[0]["model"] == "agent-pick:1b"
    finally:
        image_file.unlink(missing_ok=True)
