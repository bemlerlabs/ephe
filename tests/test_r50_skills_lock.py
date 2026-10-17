"""
◑ Ephe – W4 S2: skills-lock.json + the doctor integrity check.
tests/test_r50_skills_lock.py

RULE: these tests were written BEFORE the implementation.

Pins:
1. The generator is idempotent: a second run == a byte-identical lock.
2. Fresh lock: --check/verify → 0, 51 packs, each {name, source, computedHash}.
3. A byte-edit in one SKILL.md → verify != 0 and the pack name shows up in
   the structured deviation lines.
4. The ErrorCode enum carries skills_lock_mismatch (append-only).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _gen():
    spec = importlib.util.spec_from_file_location(
        "generate_skills_lock", str(REPO / "scripts" / "generate_skills_lock.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_lock_file_matches_disk():
    gen = _gen()
    ok, diffs = gen.verify(REPO)
    assert ok, diffs


def test_lock_shape_and_pack_count():
    lock = json.loads((REPO / "skills-lock.json").read_text(encoding="utf-8"))
    assert lock["version"] == 1
    assert len(lock["skills"]) == 51
    for entry in lock["skills"]:
        assert set(entry) == {"name", "source", "computedHash"}
        assert len(entry["computedHash"]) == 64


def test_generator_is_idempotent():
    gen = _gen()
    first = json.dumps(gen.build_lock(REPO), sort_keys=True)
    second = json.dumps(gen.build_lock(REPO), sort_keys=True)
    assert first == second


def test_byte_edit_breaks_check_with_pack_name(capsys):
    gen = _gen()
    target = REPO / "skills" / "api-designer" / "SKILL.md"
    original = target.read_bytes()
    try:
        target.write_bytes(original + b"\n")
        assert gen.main(["--check"]) == 1
        out = capsys.readouterr().err
        assert "api-designer" in out
    finally:
        target.write_bytes(original)
    assert gen.main(["--check"]) == 0


def test_error_code_appended():
    from core.observability import ErrorCode

    assert ErrorCode.SKILLS_LOCK_MISMATCH.value == "skills_lock_mismatch"
