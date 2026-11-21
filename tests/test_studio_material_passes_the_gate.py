"""The gate lets a cut read the studio's own material and still refuses a key.

Two layers decide this and both are pinned here: ``core.path_guard.studio_material``
answers per path, ``core.tools.chat_gate`` consults it for the verbs listed in
``STUDIO_MATERIAL_TOOLS`` before the protected-root refusal fires. No render runs —
these are the read rules, and a real cut is exercised in ``test_film_tools.py``.
"""
import asyncio
import os
from pathlib import Path

import pytest

from core.artifact_workbench import in_workbench
from core.path_guard import (
    artifact_root,
    product_image_root,
    studio_material,
    voice_root,
)
from core.tools.chat_gate import STUDIO_MATERIAL_TOOLS, confirm_for_chat
from core.tools.film_tools import _cut_input_allowed


async def _approve(name: str, args: dict) -> bool:
    return True


async def _deny(name: str, args: dict) -> bool:
    return False


def _run(name: str, args: dict, callback=_approve):
    return asyncio.run(confirm_for_chat(name, args, on_confirm=callback))


@pytest.fixture()
def material(tmp_path: Path, monkeypatch) -> dict:
    """One file in each folder the studio writes into, plus one outside them.

    Under pytest ``EPHE_CONFIG_DIR`` is a scratch root that ``denied()`` deliberately
    ignores, so the tmp config root is added to ``DENY_ROOTS`` here: without it the
    protected-root rule never fires and every assertion below would pass vacuously.
    """
    from core import path_guard

    monkeypatch.setattr(path_guard, "DENY_ROOTS", path_guard.DENY_ROOTS + (str(tmp_path),))
    cards = artifact_root() / "turn-eins"
    cards.mkdir(parents=True)
    (cards / "card.png").write_bytes(b"png")
    voice = voice_root()
    voice.mkdir(parents=True, exist_ok=True)
    (voice / "line.wav").write_bytes(b"wav")
    images = product_image_root()
    images.mkdir(parents=True, exist_ok=True)
    (images / "shot.png").write_bytes(b"png")
    outside = tmp_path / "private.png"
    outside.write_bytes(b"png")
    return {
        "card": cards / "card.png",
        "line": voice / "line.wav",
        "image": images / "shot.png",
        "outside": outside,
    }


def test_a_file_the_studio_wrote_is_material(material):
    assert studio_material(material["card"])
    assert studio_material(material["line"])
    assert studio_material(material["image"])


def test_a_path_outside_the_studio_folders_is_not_material(material):
    assert not studio_material(material["outside"])
    assert not studio_material(os.path.expanduser("~/.ssh/id_ed25519"))


def test_a_credential_shaped_name_stays_no_material_even_inside_the_workbench():
    planted = artifact_root() / "sessions" / "id_ed25519"
    assert not studio_material(planted)
    assert not studio_material(artifact_root() / "aws_credentials.png")


def test_a_symlink_out_of_the_workbench_is_no_material(tmp_path):
    link = artifact_root() / "through.png"
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to(os.path.expanduser("~/.ssh/id_ed25519"))
    assert not studio_material(link)


def test_film_clip_is_the_verb_the_rule_was_opened_for():
    assert STUDIO_MATERIAL_TOOLS == frozenset({"film_clip"})


def test_a_cut_may_name_the_card_and_the_voice_line_it_was_made_of(material):
    args = {
        "shots": [{"image": str(material["card"]), "duration": 2.0, "caption": "proof"}],
        "audio": str(material["line"]),
        "music": str(material["card"]),
    }

    approved, denial = _run("film_clip", args)

    assert approved, denial
    assert denial == ""


def test_a_key_named_as_the_music_bed_is_still_refused_for_a_cut():
    args = {"shots": [], "music": os.path.expanduser("~/.ssh/id_ed25519")}

    approved, denial = _run("film_clip", args)

    assert not approved
    assert "protected root" in denial


def test_the_exception_is_per_verb_a_sibling_verb_keeps_the_refusal(material):
    clip_ok, _ = _run("film_clip", {"music": str(material["card"])})
    assert clip_ok

    approved, denial = _run("film_sound", {"name": "click", "out": str(material["card"])})

    assert not approved
    assert "protected root" in denial


def test_a_cut_still_needs_the_answer_it_was_asked_for(material):
    args = {"shots": [{"image": str(material["card"]), "duration": 2.0}], "audio": str(material["line"])}

    approved, denial = _run("film_clip", args, callback=_deny)

    assert not approved
    assert "did not approve" in denial


def test_a_cut_reads_material_from_a_turn_that_is_not_the_current_one(material):
    assert _cut_input_allowed(material["card"])
    assert _cut_input_allowed(material["line"])


def test_a_cut_does_not_read_from_a_folder_the_kernel_denies():
    assert not _cut_input_allowed(Path(os.path.expanduser("~/.ssh/id_ed25519.png")))


def test_the_workbench_rule_is_the_same_fact_the_workbench_answers_with(material):
    assert in_workbench(material["card"]) is True
    assert in_workbench(material["outside"]) is False


def _dispatch(name: str, args: dict) -> str:
    from core.tools.approval import ApprovalPolicy
    from core.tools.registry import execute_tool

    return asyncio.run(execute_tool(name, args, policy=ApprovalPolicy(auto_approve=True)))


def test_the_dispatch_backstop_answers_with_the_gates_rule(material):
    result = _dispatch(
        "film_clip",
        {
            "shots": [{"image": str(material["card"]), "duration": 0.04}],
            "audio": str(material["line"]),
            "music": str(material["card"]),
        },
    )

    assert "protected root" not in result, result


def test_the_dispatch_backstop_still_refuses_a_key_for_a_cut(material):
    result = _dispatch(
        "film_clip",
        {"shots": [{"image": str(material["card"]), "duration": 0.04}],
         "music": os.path.expanduser("~/.ssh/id_ed25519")},
    )

    assert "protected root" in result, result


def test_the_two_layers_do_not_keep_the_rule_each_for_themselves():
    from core.tools import chat_gate, registry

    registry_source = Path(registry.__file__).read_text(encoding="utf-8")
    assert "protected_path_hits" in registry_source
    assert "verifiable_artifact" not in registry_source
    assert chat_gate.VERIFIABLE_PATH_TOOLS == frozenset(
        {"verify_artifact", "qa_pptx_deck", "inspect_pptx_template"}
    )


def test_the_shared_rule_answers_for_every_verb_it_carries(material):
    from core.tools.chat_gate import protected_path_hits

    card = str(material["card"])
    line = str(material["line"])
    key = os.path.expanduser("~/.ssh/id_ed25519")

    assert protected_path_hits("film_clip", {"audio": line, "music": card}) == []
    assert protected_path_hits("verify_artifact", {"path": card}) == []
    assert protected_path_hits("qa_pptx_deck", {"path": card}) == []
    assert protected_path_hits("film_sound", {"out": card}) == [card]
    assert protected_path_hits("read_file", {"path": card}) == [card]
    assert protected_path_hits("film_clip", {"music": key}) == [key]
