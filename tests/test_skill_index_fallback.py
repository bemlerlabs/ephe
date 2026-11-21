"""P1-1: model index fallback on a 0-hit from the deterministic layer.

The compact skill index is injected only when no active skill
resolves and no ask_mode applies — otherwise the
progressive-disclosure chain stays unchanged.
"""
from __future__ import annotations

from core.skills import SkillLoader
from server.routes.chat import _compose_extra_system


def test_index_shape_and_cap():
    idx = SkillLoader().build_skill_index()
    assert idx.startswith("Verfuegbare Skills")
    # 47 skills, 1 line each + header → compact (< 6k characters at cap 70).
    assert len(idx) < 6000, f"Index zu gross: {len(idx)}"
    assert "…" in idx, "Beschreibungen werden nicht am Cap gekappt"


def test_index_injected_only_on_zero_hit():
    loader = SkillLoader()
    # 0-hit cases: no skill active → the index lands in the extra system.
    out = _compose_extra_system(None, ask_mode=False)
    assert out is not None and "## Skill-Index" in out
    # ask_mode: the guard has precedence, no index fallback needed.
    out_ask = _compose_extra_system(None, ask_mode=True)
    assert "## Skill-Index" not in (out_ask or "")
    # An active skill: its own prompt, no index.
    skill = loader.resolve_trigger("/pdf")
    assert skill is not None
    out_skill = _compose_extra_system(skill, ask_mode=False)
    assert "## Skill-Index" not in (out_skill or "")


def test_deterministic_layer_still_wins():
    """A clear intent resolves without the index fallback (the score layer)."""
    loader = SkillLoader()
    hit = loader.resolve_for_message("Erstelle ein PDF mit Zahlen")
    assert hit is not None and hit.name == "pdf-creator"
