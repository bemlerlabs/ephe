"""Area SSOT: bounds and texts travel inside the payload (I3-3, I3-9).

`sections-engine.tsx` wrote '0–2', '0–1', '1–40' as hard-coded labels, although
core/engine_config.py::GENERATION_BOUNDS has long held them. Two sources,
one truth: when the bound changed, the label went on lying. The same
pattern in the expert tab — the client sent raw numbers without bracketing and
the user saw a 422 toast only on saving.

This test holds the three links of the chain: the bound in the payload, value and
bound under the same keys, the step in the tab.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.engine_config import GENERATION_BOUNDS  # noqa: E402
from core.settings_schema import SCHEMA, deep_view  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch: pytest.MonkeyPatch):
    isolated = tmp_path / "config"
    isolated.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(isolated))
    import core.engine_config as ec

    monkeypatch.setattr(ec, "CONFIG_DIR", isolated)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("EPHE_HEALTH_DEEP", raising=False)
    from server.routes import settings as settings_route

    app = FastAPI()
    app.include_router(settings_route.router, prefix="/api")
    return TestClient(app)


# generation block: bounds from ENGINE, not from the TSX

def test_generation_grenzen_und_texte_im_payload(client: TestClient) -> None:
    meta = client.get("/api/settings").json()["generation_meta"]
    assert set(meta) == set(GENERATION_BOUNDS), "andere Schluessel als der Verbraucher"
    for key, (default, low, high) in GENERATION_BOUNDS.items():
        assert meta[key]["default"] == default, key
        assert meta[key]["min"] == low, key
        assert meta[key]["max"] == high, key
        # I3-9: each slider explains itself — in both languages, and differently.
        de, en = meta[key]["hint"], meta[key]["hintEn"]
        assert 24 <= len(de) <= 240 and 24 <= len(en) <= 240, (key, len(de), len(en))
        assert de != en, key


def test_werte_und_grenzen_decken_sich(client: TestClient) -> None:
    """A value without a bound would reach the client as a blind field."""
    body = client.get("/api/settings").json()
    assert set(body["generation"]) == set(body["generation_meta"])


def test_optionale_grenze_bleibt_null(client: TestClient) -> None:
    """max=None means 'no upper bound' — a substituted default would be a lie."""
    meta = client.get("/api/settings").json()["generation_meta"]
    assert meta["max_tokens"]["max"] is None
    assert meta["temperature"]["max"] == 2.0


# Expert tab: step and bounds out of the schema

def test_numberfelder_im_register_traegen_einen_step() -> None:
    entries = {f["key"]: f for s in deep_view() for f in s["fields"]}
    for key, meta in SCHEMA.items():
        if meta["type"] != "number":
            assert "step" not in entries[key], key
            continue
        step = entries[key]["step"]
        assert step > 0, key
        # Integer fields step by 1, decimals with a light touch.
        assert step == 1 if isinstance(meta["default"], int) else step < 1, key
        assert entries[key]["min"] == meta["min"] and entries[key]["max"] == meta["max"], key


def test_der_step_passt_in_den_bereich() -> None:
    entries = {f["key"]: f for s in deep_view() for f in s["fields"]}
    for key, entry in entries.items():
        if entry["type"] != "number":
            continue
        assert entry["step"] <= entry["max"] - entry["min"], f"{key}: Step groesser als Bereich"
