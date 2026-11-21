"""tests/test_persona_cli.py — `ephe persona` is the pack library's only caller.

`core/persona_pack.py` is a finished, tested library that nothing in the tree called: a persona
had an editor behind `/api/settings/persona` and no door for the one thing that makes it travel —
a file carrying its own name and the hash that says its text arrived whole. Moving one between two
Ephe installs meant copying `~/.ephe/persona.md` by hand, which carries neither. These cases pin
what the four actions promise:

* an export is re-importable: the bytes it writes load, and their hash is the stored text's;
* an import writes through the editor's own atomic, owner-only writer and refuses the two things
  it has to refuse — a persona already in place, and a signature no trusted key answers;
* verify answers in exit codes, because someone checking a file before importing it reads the
  status more often than the prose.

Every case runs against a temporary persona directory and a temporary working folder.
"""
from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

import ephe_cli
from core import persona_pack as pp
from core.engine_config import config_root
from core.persona import persona_path
from core.plugin_signing import generate_keypair

BODY = "## Voice\n- Warm, brief, honest."


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A persona dir and a working folder of our own; the owner's `~/.ephe` stays out of it."""
    monkeypatch.setenv("EPHE_PERSONA_DIR", str(tmp_path / "cfg"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(capsys, *argv: str):
    """Build the real parser, run the action, hand back (code, stdout, stderr)."""
    args = ephe_cli.build_parser().parse_args(["persona", *argv])
    code = args.func(args)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _pack_file(tmp_path: Path, **kw) -> Path:
    """A pack on disk, the way a person would receive one."""
    text = kw.pop("text", BODY)
    pack = pp.build_pack(text, **kw)
    path = tmp_path / pp.filename(pack)
    path.write_text(pp.dumps(pack), encoding="utf-8")
    return path


def _sign_and_trust(pack: dict, kid: str = "unit-test") -> dict:
    """Sign with a fresh key and hand the public half to the anchor folder the CLI reads."""
    private_pem, public_pem = generate_keypair()
    anchors = config_root() / "trusted-keys"
    anchors.mkdir(parents=True, exist_ok=True)
    (anchors / "unit.pub.pem").write_bytes(public_pem)
    return pp.sign_pack(pack, private_pem, kid=kid)


class TestShow:
    def test_it_names_the_source_the_characters_and_the_cap(self, home, capsys):
        code, out, _ = _run(capsys, "show")

        assert code == 0
        assert "source: default" in out
        assert "of 8000" in out
        assert "sha256: " in out

    def test_the_json_carries_the_same_four_facts(self, home, capsys):
        code, out, _ = _run(capsys, "show", "--json")

        assert code == 0
        assert set(json.loads(out)) == {"source", "chars", "cap", "sha256"}


class TestExport:
    def test_the_file_is_named_after_the_persona_it_carries(self, home, capsys):
        code, out, _ = _run(capsys, "export")

        assert code == 0
        written = home / "default.ephe-persona.json"
        assert written.is_file(), "the default persona exports under its own source's name"
        assert "next:" in out
        pack = pp.load(json.loads(written.read_text(encoding="utf-8")))
        assert pack["persona_sha256"] == pp.persona_sha256(pack["persona"])

    def test_every_field_a_person_types_arrives_in_the_file(self, home, capsys):
        code, out, _ = _run(
            capsys,
            "export",
            "--out",
            "nested/mine.json",
            "--name",
            "marvin",
            "--title",
            "Marvin",
            "--description",
            "runs errands",
            "--author",
            "Ada",
        )

        assert code == 0
        path = home / "nested/mine.json"
        assert path.is_file(), "--out creates the folder it writes into"
        assert "bytes" in out
        pack = pp.load(json.loads(path.read_text(encoding="utf-8")))
        assert (pack["name"], pack["title"], pack["description"], pack["author"]) == (
            "marvin",
            "Marvin",
            "runs errands",
            "Ada",
        )

    def test_the_persona_this_ephe_serves_is_the_one_that_travels(self, home, capsys):
        persona_path().parent.mkdir(parents=True, exist_ok=True)
        persona_path().write_text(BODY, encoding="utf-8")

        code, _, _ = _run(capsys, "export", "--name", "carrier")

        assert code == 0
        pack = pp.load(json.loads((home / "carrier.ephe-persona.json").read_text(encoding="utf-8")))
        assert pack["persona"] == BODY
        assert pack["persona_sha256"] == pp.persona_sha256(BODY)

    def test_a_slug_nothing_could_read_is_refused(self, home, capsys):
        code, _, err = _run(capsys, "export", "--name", "___")

        assert code == 1
        assert "name required" in err


class TestImport:
    def test_an_unsigned_pack_is_refused_and_the_persona_untouched(self, home, capsys):
        pack = _pack_file(home, title="Marvin")

        code, _, err = _run(capsys, "import", str(pack))

        assert code == 1
        assert "no signature record" in err
        assert "--trust-local" in err, "the refusal says what the way in would be"
        assert not persona_path().exists()

    def test_the_word_trust_local_writes_through_the_editors_own_writer(self, home, capsys):
        pack = _pack_file(home, title="Marvin")

        code, out, _ = _run(capsys, "import", str(pack), "--trust-local")

        assert code == 0
        assert persona_path().read_text(encoding="utf-8") == BODY
        assert "imported on --trust-local" in out
        mode = stat.S_IMODE(persona_path().stat().st_mode)
        assert mode == 0o600, "the persona arrives with the editor's owner-only mode"

    def test_an_existing_persona_survives_until_the_person_names_otherwise(self, home, capsys):
        persona_path().parent.mkdir(parents=True, exist_ok=True)
        persona_path().write_text("keep me", encoding="utf-8")
        pack = _pack_file(home, title="Marvin")

        code, _, err = _run(capsys, "import", str(pack), "--trust-local")
        assert code == 1
        assert "already exists" in err
        assert persona_path().read_text(encoding="utf-8") == "keep me"

        code, out, _ = _run(capsys, "import", str(pack), "--trust-local", "--overwrite")
        assert code == 0
        assert persona_path().read_text(encoding="utf-8") == BODY
        assert "marvin" in out

    def test_a_pack_a_trusted_key_answers_needs_no_trust_local(self, home, capsys):
        pack = _sign_and_trust(pp.build_pack(BODY, title="Marvin"))
        path = home / "signed.ephe-persona.json"
        path.write_text(pp.dumps(pack), encoding="utf-8")

        code, out, _ = _run(capsys, "import", str(path))

        assert code == 0
        assert "verified (kid unit-test)" in out
        assert persona_path().read_text(encoding="utf-8") == BODY

    def test_a_file_it_cannot_read_says_so_with_the_path(self, home, capsys):
        code, _, err = _run(capsys, "import", str(home / "nowhere.json"))

        assert code == 1
        assert "no pack to read at" in err
        assert "nowhere.json" in err

    def test_a_file_that_is_not_json_says_where_it_stopped(self, home, capsys):
        broken = home / "broken.json"
        broken.write_text("{oops", encoding="utf-8")

        code, _, err = _run(capsys, "import", str(broken))

        assert code == 1
        assert "is not json" in err

    def test_a_json_object_that_is_not_a_pack_is_refused(self, home, capsys):
        not_a_pack = home / "not-a-pack.json"
        not_a_pack.write_text('{"hello": "world"}', encoding="utf-8")

        code, _, err = _run(capsys, "import", str(not_a_pack))

        assert code == 1
        assert "persona" in err.lower()


class TestVerify:
    def test_a_signed_pack_verifies_and_the_anchors_it_read_are_counted(self, home, capsys):
        from core.plugin_signing import load_trusted_public_keys

        pack = _sign_and_trust(pp.build_pack(BODY, title="Marvin"))
        path = home / "signed.ephe-persona.json"
        path.write_text(pp.dumps(pack), encoding="utf-8")

        code, out, _ = _run(capsys, "verify", str(path))

        assert code == 0
        assert "marvin: verified" in out
        assert f"anchors: {len(load_trusted_public_keys())} trusted key(s) read" in out

    def test_an_unsigned_pack_exits_nonzero_with_the_reason(self, home, capsys):
        pack = _pack_file(home, title="Marvin")

        code, out, _ = _run(capsys, "verify", str(pack))

        assert code == 1
        assert "refused: no signature record" in out

    def test_a_file_that_is_not_there_says_so_before_any_verdict(self, home, capsys):
        code, _, err = _run(capsys, "verify", str(home / "gone.ephe-persona.json"))

        assert code == 1
        assert "no pack to read at" in err
        assert "anchors" not in _, "no verdict is printed for a file that was never read"

    def test_what_is_not_an_object_is_named_as_unnamed(self, home, capsys):
        array = home / "array.json"
        array.write_text("[1, 2]", encoding="utf-8")

        code, out, _ = _run(capsys, "verify", str(array))

        assert code == 1
        assert "unnamed pack" in out
        assert "not a json object" in out

    def test_the_json_holds_the_verdict_for_a_script_to_read(self, home, capsys):
        pack = _pack_file(home, title="Marvin")

        code, out, _ = _run(capsys, "verify", str(pack), "--json")

        assert code == 1
        body = json.loads(out)
        assert body["ok"] is False
        assert body["reason"] == "no signature record"
        assert body["name"] == "marvin"
