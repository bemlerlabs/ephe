"""Template library tests: a curated pack names what it ships and why."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "ephe-template-library"
MANIFEST = PLUGIN / "ephe-plugin.json"
PROVENANCE = PLUGIN / "templates" / "PROVENANCE.json"
TEMPLATES = PLUGIN / "templates"


def _provenance() -> dict:
    return json.loads(PROVENANCE.read_text(encoding="utf-8"))


def test_manifest_matches_the_plugin_directory() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["name"] == "ephe-template-library"
    assert data["version"] == "1.0.0"
    assert data["manifest_version"] == 2
    assert str(data.get("origin")) == "first-party"


def test_every_shipped_template_has_a_provenance_entry_and_a_licence() -> None:
    """A template without a licence is not a template we may ship."""
    prov = _provenance()
    entries = {e["id"]: e for e in prov["templates"]}
    assert entries, "the curated pack must name at least one template"
    for folder in sorted(p for p in TEMPLATES.iterdir() if p.is_dir()):
        if folder.name in {"websites", "worlds", "motion"}:
            continue
        entry = entries.get(folder.name)
        assert entry, f"{folder.name} is shipped without provenance"
        assert (folder / entry["licence_file"]).is_file(), folder
        assert entry["source_url"].startswith("https://"), entry


def test_sha256_matches_the_file_that_is_shipped() -> None:
    """A hash that does not cover the shipped bytes is theatre."""
    for entry in _provenance()["templates"]:
        target = TEMPLATES / entry["id"] / entry["file"]
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        assert digest == entry["sha256"], entry["id"]


def test_no_template_fetches_from_a_cdn_at_runtime() -> None:
    """Local-first means the shipped file is the whole file."""
    for path in TEMPLATES.glob("*/*.html"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in ("cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com",
                       "fonts.googleapis.com", "static.heygen.ai"):
            assert marker not in text, (path, marker)


def test_golden_cases_cover_the_truthful_refusals() -> None:
    cases = [json.loads(line) for line in
             (PLUGIN / "prompts" / "golden.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    assert len(cases) >= 6
    ids = {c["id"] for c in cases}
    assert any("unknown" in i for i in ids)
    assert any("licence" in i or "license" in i for i in ids)


def test_unknown_template_is_refused_without_copying(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ephe_template_handlers", PLUGIN / "tools" / "handlers.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.ephe_template_apply("does-not-exist", str(tmp_path / "out"))
    assert "unknown template" in result
    assert not (tmp_path / "out").exists()


def test_apply_copies_the_licence_alongside_the_file(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ephe_template_handlers_apply", PLUGIN / "tools" / "handlers.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    target = tmp_path / "out"
    result = mod.ephe_template_apply("cut-short", str(target))
    assert "cut-short" in result
    assert (target / "index.html").is_file()
    assert (target / "LICENSE").is_file()
