"""WA-10 — the remaining vision-route branches (server/routes/vision.py).

The existing route suite (tests/test_vision_route.py) pins the model-selection,
size-cap and EXIF contracts. This file closes the branches it left open: the
upload floor, the provider-setup refusal on both endpoints, the base64 twin's
own floor and invalid-input paths, and the upload path's coded failure.
"""
from __future__ import annotations

import base64

import pytest

from core.model_provider import ProviderSetupError
from tests.test_vision_route import _png_bytes, vision  # noqa: F401  (fixture reused)


def _message(response) -> str:
    return response.json()["error"]["message"]


# upload endpoint: the floor and the provider refusals


def test_upload_below_the_size_floor_is_refused(vision):
    tiny = _png_bytes(10)  # 8-byte header + 10 payload bytes, under 100
    assert len(tiny) < 100

    response = vision.app.post(
        "/api/vision/analyze",
        files={"file": ("small.png", tiny, "image/png")},
    )

    assert response.status_code == 400
    assert "too small" in _message(response)
    assert vision.fake.calls == [], "a rejected payload reached the engine"


def test_upload_provider_setup_error_is_a_503(vision):
    vision.fake.error = ProviderSetupError("the chosen vision provider is not configured")

    response = vision.app.post(
        "/api/vision/analyze",
        files={"file": ("pixel.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 503
    assert "not configured" in _message(response)


def test_upload_generic_provider_error_is_the_coded_refusal(vision):
    vision.fake.error = RuntimeError("engine blew up mid-stream")

    response = vision.app.post(
        "/api/vision/analyze",
        files={"file": ("pixel.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 500
    body = response.json()["error"]
    assert body["reason_code"] == "vision_failed"
    assert body["message"].startswith("Image analysis failed:")
    assert "blew up mid-stream" in body["message"]


# base64 endpoint: empty, malformed and undersized input


def test_base64_missing_payload_is_refused(vision):
    response = vision.app.post("/api/vision/base64", json={"image_b64": ""})

    assert response.status_code == 400
    assert "must not be empty" in _message(response)
    assert vision.fake.calls == []


def test_base64_invalid_string_is_refused(vision):
    response = vision.app.post("/api/vision/base64", json={"image_b64": "abcde"})

    assert response.status_code == 400
    assert "invalid Base64" in _message(response)
    assert vision.fake.calls == []


def test_base64_below_the_size_floor_is_refused(vision):
    small = base64.b64encode(b"x" * 50).decode()

    response = vision.app.post("/api/vision/base64", json={"image_b64": small})

    assert response.status_code == 400
    assert "too small" in _message(response)
    assert vision.fake.calls == []


def test_base64_provider_setup_error_is_a_503(vision):
    vision.fake.error = ProviderSetupError("no key for the vision provider")

    response = vision.app.post(
        "/api/vision/base64",
        json={"image_b64": base64.b64encode(_png_bytes()).decode()},
    )

    assert response.status_code == 503
    assert "no key" in _message(response)


def test_a_missing_base64_body_field_is_a_validation_error(vision):
    response = vision.app.post("/api/vision/base64", json={"question": "hi"})

    assert response.status_code == 422
    assert vision.fake.calls == []
