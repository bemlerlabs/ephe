"""R44 (P4) / R4-A1: what the output_dir field means today.

Before A1: 1) a path in the prompt, 2) output_dir, 3) ~/Downloads. Since A1 there
is a birthplace: the workbench (~/.ephe/artifacts/<session>). output_dir is the
**marked adopt target** — read by POST /api/artifacts/{id}/adopt, no longer by the
writing tools. The path named in the prompt still wins, because the user names it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import core.engine_config as ec


@pytest.fixture
def cfg_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "CONFIG_DIR", tmp_path)
    monkeypatch.delenv("EPHE_OUTPUT_DIR", raising=False)
    return tmp_path


def test_get_output_dir_none_ohne_alles(cfg_dir):
    assert ec.get_output_dir() is None
    assert ec.get_output_dir() == None  # noqa: no 0/"" trap


def test_get_output_dir_persistiert_gewinnt_vor_env(cfg_dir, monkeypatch):
    out = str(cfg_dir / "o1")
    ok = ec.save_engine_config(
        ec.EngineChoice(provider="local_ollama", model="gemma4:12b",
                        output_dir=out),
        path=cfg_dir / "engine.json",
    )
    assert ok
    monkeypatch.setenv("EPHE_OUTPUT_DIR", str(cfg_dir / "o2"))
    assert ec.get_output_dir() == out


def test_get_output_dir_env_fallback_ohne_persistenz(cfg_dir, monkeypatch):
    monkeypatch.setenv("EPHE_OUTPUT_DIR", str(cfg_dir / "o2"))
    assert ec.get_output_dir() == str(cfg_dir / "o2")


def test_validate_output_dir_regeln(cfg_dir):
    assert ec.validate_output_dir("") is None
    assert ec.validate_output_dir(None) is None
    # absolute, and it gets created
    p = ec.validate_output_dir(str(cfg_dir / "deep/nested"))
    assert Path(p).is_dir()
    with pytest.raises(ValueError):
        ec.validate_output_dir("relativ/ordner")


async def test_prompt_pfad_gewinnt_ueber_output_dir(cfg_dir, monkeypatch):
    ec.save_engine_config(
        ec.EngineChoice(provider="local_ollama", model="gemma4:12b",
                        output_dir=str(cfg_dir / "o1")),
        path=cfg_dir / "engine.json",
    )
    from core.tools.office_tools import create_xlsx

    res = await create_xlsx(
        title="Kette",
        data=[["a", "b"], ["1", "2"]],
        filename="kette.xlsx",
        path=str(cfg_dir / "prompt"),
    )
    assert (cfg_dir / "prompt" / "kette.xlsx").is_file()
    assert not (cfg_dir / "o1" / "kette.xlsx").exists()
    assert res  # the FILE marker came back


async def test_geburtsort_ist_die_werkbank_und_nicht_mehr_output_dir(cfg_dir, werkbank):
    """R4-A1: the settings field moved from birthplace to adopt target.

    This test is the other half of the decision: a tool no longer asks output_dir
    when it writes. Otherwise there would be two birthplaces — and the workbench
    would just be a third place in the chaos.
    """
    from core.tools.office_tools import _downloads

    ec.save_engine_config(
        ec.EngineChoice(provider="local_ollama", model="gemma4:12b",
                        output_dir=str(cfg_dir / "o1")),
        path=cfg_dir / "engine.json",
    )
    assert _downloads() == werkbank
    assert not (cfg_dir / "o1").exists(), "output_dir wird beim Schreiben nicht mehr angefasst"


async def test_persist_engine_choice_erhaelt_ordner_einstellungen(cfg_dir):
    ec.save_engine_config(
        ec.EngineChoice(provider="local_ollama", model="gemma4:12b",
                        output_dir=str(cfg_dir / "o1"),
                        workspace_dir=str(cfg_dir)),
        path=cfg_dir / "engine.json",
    )
    assert ec.persist_engine_choice("openai_compatible", "qwen3.8-flash-next",
                                    "http://127.0.0.1:8080/v1")
    again = ec.load_engine_config(cfg_dir / "engine.json")
    assert again.output_dir == str(cfg_dir / "o1")
    assert again.workspace_dir == str(cfg_dir)
    assert again.api_url == "http://127.0.0.1:8080/v1"


#: The surface line about the adopt target promises that the birthplace is the
#: workbench and that an order does not change it. That is checked on the tool
#: schemas themselves — not on a text.
OUTPUT_TOOLS = (
    "create_pdf", "create_svg", "create_diagram", "generate_chart",
    "create_pitch_deck", "create_pptx_deck", "create_xlsx", "create_docx", "create_qrcode",
)


def test_ausgabewerkzeuge_kennen_keinen_pfad():
    """R4 (W2 register, point 10): no output tool accepts a path.

    Before A1 the surface said „ein im Auftrag genannter Pfad gewinnt immer" —  # language-gate: ignore (quote of the retired surface sentence this guard forbids from coming back)
    re-measured: at most one of these tools had a `path`, and the sanitizers cut it
    back to the bare name. The sentence is corrected now; this guard forbids it from
    coming back should a path parameter ever show up again.
    """
    from core.tools import get_tool_schemas

    by_name = {t["function"]["name"]: t for t in get_tool_schemas()}
    missing = [name for name in OUTPUT_TOOLS if name not in by_name]
    assert not missing, f"Werkzeuge aus der Prüfung verschwunden: {missing}"
    with_path = [
        name
        for name in OUTPUT_TOOLS
        if "path" in (by_name[name]["function"].get("parameters") or {}).get("properties", {})
    ]
    assert with_path == [], f"Diese Ausgabe-Werkzeuge nehmen einen Pfad: {with_path}"
