"""Ephe — the language gate holds the English-only rule.

Owner rule 2026-10-08: repository artifacts are English, German stays where it is
the product. `scripts/language_inventory.py` measures that; `scripts/language_gate.py`
turns the measurement into a gate over a committed baseline. These tests drive the
gate with an injected file list and reader, so they need no git checkout, no
network, and no fixture repository — and they run in milliseconds, which is what
a gate that belongs on every commit costs.

Given / When / Then, strictly.

No German of its own lives here: the sample prose is assembled from the
instrument's own marker list. That keeps the gate honest about this repository —
the instrument reads every tracked file, these tests included — and stops the
fixture from drifting away from the detector it exercises.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent
GATE_PATH = REPO / "scripts" / "language_gate.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("language_gate_under_test", GATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: Loaded once for the whole file: the helpers below need the instrument's marker
#: list, and a pytest fixture cannot reach them.
gate = _load_gate()


#: A tracked path with German developer prose, far from any protected prefix.
SOURCE = "core/order.py"
#: Paths where German is the product, so the number must never see them.
PRODUCT = ("skills/survival/SKILL.md", "app/src/locales/de.json", "knowledge/survival/de.md")


def german_lines(count: int, markers: list[str]) -> str:
    """`count` lines that the instrument counts as German developer prose."""
    return "\n".join(
        f"# {markers[i % len(markers)]} {markers[(i + 1) % len(markers)]}"
        for i in range(count)
    )


def clean_lines(count: int) -> str:
    """`count` lines the instrument leaves alone."""
    return "\n".join(f"# step {i} of the pipeline" for i in range(count))


def tree(*, german: int = 0, product_german: int = 0) -> dict[str, str]:
    """A synthetic tracked tree: one developer file plus the product paths."""
    markers = gate.inventory.MARKERS
    return {
        SOURCE: clean_lines(3) + "\n" + german_lines(german, markers),
        **{rel: german_lines(product_german, markers) for rel in PRODUCT},
    }


def injected(files: dict[str, str]) -> tuple[Callable[[], list[str]], Callable[[str], str]]:
    """The two seams the gate measures through: which paths are tracked, and their text."""
    return (lambda: sorted(files), lambda rel: files[rel])


def baseline(tmp_path: Path, files: dict[str, int], **extra) -> Path:
    path = tmp_path / "language-baseline.json"
    payload: dict = {"policy": gate.POLICY, "version": gate.VERSION, "files": files}
    payload.update(extra)
    payload["total"] = sum(files.values())
    path.write_text(json.dumps(payload, sort_keys=True, indent=1), encoding="utf-8")
    return path


def run(tmp_path: Path, path: Path, files: dict[str, str], *flags: str) -> int:
    list_files, read_text = injected(files)
    return gate.main(
        ["--baseline", str(path), "--root", str(tmp_path), *flags],
        list_files=list_files,
        read_text=read_text,
    )


class TestGrowthFails:
    def test_a_file_that_gained_german_lines_fails_and_is_named(self, tmp_path, capsys):
        """GIVEN a baseline at one line WHEN that file carries two THEN the gate fails by name."""
        path = baseline(tmp_path, {SOURCE: 1})
        code = run(tmp_path, path, tree(german=2))
        out = capsys.readouterr().out
        assert code == 1
        assert "FAIL" in out
        assert SOURCE in out
        assert "1 -> 2" in out

    def test_a_new_german_file_fails_even_when_the_total_shrinks(self, tmp_path, capsys):
        """GIVEN a translated file and a new German one WHEN both are measured THEN growth wins."""
        newcomer = "core/newcomer.py"
        path = baseline(tmp_path, {SOURCE: 9, newcomer: 0})
        files = {SOURCE: clean_lines(1), newcomer: german_lines(4, gate.inventory.MARKERS)}
        code = run(tmp_path, path, files)
        out = capsys.readouterr().out
        assert code == 1
        assert newcomer in out
        # the total fell from nine lines to four, and the gate still failed: the
        # ratchet is per file, so one clean-up cannot pay for a new German comment.
        assert "total 9 -> 4" in out

    def test_an_unchanged_tree_passes_quietly(self, tmp_path, capsys):
        """GIVEN a baseline that matches the tree WHEN the gate runs THEN it passes."""
        path = baseline(tmp_path, {SOURCE: 2})
        code = run(tmp_path, path, tree(german=2))
        out = capsys.readouterr().out
        assert code == 0
        assert "PASS" in out
        assert "lowered" not in out


class TestShrinkagePasses:
    def test_a_cleaner_tree_passes_and_offers_to_lower_the_baseline(self, tmp_path, capsys):
        """GIVEN three lines baselined WHEN only one is left THEN the gate says: lower it."""
        path = baseline(tmp_path, {SOURCE: 3})
        code = run(tmp_path, path, tree(german=1))
        out = capsys.readouterr().out
        assert code == 0
        assert "PASS" in out
        assert "the baseline can be lowered" in out
        assert "language_gate.py --update" in out

    def test_update_lowers_the_baseline(self, tmp_path, capsys):
        """GIVEN a cleaner tree WHEN --update runs THEN the committed number follows it down."""
        path = baseline(tmp_path, {SOURCE: 3})
        assert run(tmp_path, path, tree(german=1), "--update") == 0
        assert "baseline lowered" in capsys.readouterr().out
        assert json.loads(path.read_text())["files"] == {SOURCE: 1}

    def test_update_refuses_to_raise_the_baseline(self, tmp_path, capsys):
        """GIVEN a tree that grew WHEN --update runs THEN the baseline stays put and it fails."""
        path = baseline(tmp_path, {SOURCE: 1})
        before = path.read_text()
        assert run(tmp_path, path, tree(german=5), "--update") == 1
        assert "only lowers" in capsys.readouterr().err
        assert path.read_text() == before


class TestProtectedPathsNeverMoveTheNumber:
    def test_product_german_is_invisible_to_the_measurement(self):
        """GIVEN the same developer files WHEN product German is added THEN the counts are equal."""
        list_files, read_text = injected(tree(german=2))
        with_list, with_read = injected(tree(german=2, product_german=40))
        plain = gate.measure(Path("."), list_files=list_files, read_text=read_text)
        guarded = gate.measure(Path("."), list_files=with_list, read_text=with_read)
        assert plain == guarded == {SOURCE: 2}

    def test_product_german_does_not_change_the_gate_verdict(self, tmp_path, capsys):
        """GIVEN a passing baseline WHEN the skill packs grow forty lines THEN it still passes."""
        path = baseline(tmp_path, {SOURCE: 2})
        assert run(tmp_path, path, tree(german=2, product_german=40)) == 0
        assert "PASS" in capsys.readouterr().out

    def test_the_shipped_protected_prefixes_pass_the_gate_guard(self):
        """GIVEN the instrument's own list WHEN the gate checks it THEN nothing is refused."""
        assert gate.checked_protected_prefixes() == tuple(gate.inventory.PROTECTED_PREFIXES)


class TestNoAccidentalWhitelist:
    def test_a_baseline_naming_a_protected_path_is_refused(self, tmp_path, capsys):
        """GIVEN the locale file recorded in the baseline WHEN the gate reads it THEN error."""
        path = baseline(tmp_path, {SOURCE: 1, PRODUCT[1]: 400})
        code = run(tmp_path, path, tree(german=1))
        err = capsys.readouterr().err
        assert code == 2
        assert "protected path" in err
        assert PRODUCT[1] in err

    def test_an_exemption_key_in_the_baseline_is_refused(self, tmp_path, capsys):
        """GIVEN a whitelist-shaped key WHEN the gate reads the baseline THEN it refuses the shape."""
        path = baseline(tmp_path, {SOURCE: 1}, exempt=[SOURCE])
        code = run(tmp_path, path, tree(german=1))
        err = capsys.readouterr().err
        assert code == 2
        assert "no exemption list" in err
        assert "exempt" in err

    def test_a_protected_prefix_over_developer_code_is_refused(self, tmp_path, capsys, monkeypatch):
        """GIVEN the protected list widened over core/ WHEN the gate starts THEN the run stops."""
        monkeypatch.setattr(gate.inventory, "PROTECTED_PREFIXES", ("core/",))
        path = baseline(tmp_path, {SOURCE: 1})
        code = run(tmp_path, path, tree(german=1))
        err = capsys.readouterr().err
        assert code == 2
        assert "covers developer code" in err

    def test_a_missing_baseline_is_an_error_not_a_pass(self, tmp_path, capsys):
        """GIVEN no baseline WHEN the gate runs THEN it says so instead of measuring nothing."""
        missing = tmp_path / "language-baseline.json"
        list_files, read_text = injected(tree(german=0))
        code = gate.main(
            ["--baseline", str(missing), "--root", str(tmp_path)],
            list_files=list_files,
            read_text=read_text,
        )
        err = capsys.readouterr().err
        assert code == 2
        assert "--update" in err


class TestInstrumentStillMeansWhatItMeant:
    """The gate leans on the instrument's filtering; these pin it down."""

    def test_only_prose_paths_are_scannable(self):
        cases = {
            "core/order.py": True,
            "app/src/pages/Shelf.tsx": True,
            "README.md": True,
            "assets/logo.png": False,
            "app/dist/app.js": False,
            "node_modules/pkg/index.js": False,
            "app/src/locales/de.json": False,
            "skills/german/SKILL.md": False,
            "knowledge/survival/de.md": False,
        }
        for rel, expected in cases.items():
            assert gate.inventory.is_scannable(rel) is expected, rel

    def test_a_line_counts_once_however_many_markers_it_holds(self):
        markers = gate.inventory.MARKERS
        text = f"# {markers[0]} {markers[1]} {markers[2]}\n# plain english line"
        assert gate.inventory.hits_in(text) == 1

    def test_the_escape_valve_is_a_line_pragma_not_a_weaker_instrument(self):
        """GIVEN German that is the point WHEN the line says so THEN only that line is exempt.

        Two kinds of exemption exist: a whole path (a rubric quoting the filler it warns
        against) and a single line (the marker vocabulary the detector itself searches
        for). The narrow one is a pragma, and the line below it is still measured.
        """
        markers = gate.inventory.MARKERS
        pragma = gate.inventory.PRAGMA
        text = f"# {markers[0]} {markers[1]} {pragma}\n# {markers[2]} {markers[3]}"
        assert gate.inventory.hits_in(text) == 1

    def test_a_plugin_rubric_path_is_not_developer_prose(self):
        """Its German is the product's own filler, quoted as the thing to avoid."""
        assert not gate.inventory.is_scannable("plugins/vision/prompts/rubric.md")

    def test_a_committed_baseline_records_evidence_it_must_not_score(self):
        """A baseline quotes the paths and test ids that still carry the debt.

        Recorded evidence is not developer prose: `tests/home-isolation-baseline.json`
        names a test whose function name is German, and scoring that line would make the
        instrument punish a worker for writing the ratchet down.
        """
        for rel in (
            "tests/home-isolation-baseline.json",
            "scripts/language-baseline.json",
            ".architecture-baseline.json",
        ):
            assert not gate.inventory.is_scannable(rel), rel

    def test_the_wide_net_catches_german_the_marker_list_is_blind_to(self):
        """A sentence with no marker word is still German, and two workers proved it.

        Wave 4 reported the same hole twice: the planning vocabulary is small on
        purpose, so a comment like "PWA-Build darf den Start nie blockieren" scored [language-gate: ignore]
        zero and a finished-looking file shipped German. The wide net is the
        completion pass: broad vocabulary, umlauts, German abbreviations.

        The samples are assembled from the instrument's own lists, so this file keeps
        carrying no German of its own and the whole-line ratchet is not fooled by a
        fixture written to defeat it.
        """
        inv = gate.inventory
        darf, als, zahl = (
            inv.HINTS[inv.HINTS.index("darf")],
            inv.HINTS[inv.HINTS.index("als")],
            inv.HINTS[inv.HINTS.index("zahl")],
        )
        der, enthalten = inv.HINTS[inv.HINTS.index("der")], inv.HINTS[inv.HINTS.index("enthalten")]
        samples = [
            f"# PWA-Build {darf} den Start nie blockieren",
            f"# lockfile-Probleme: npm install {als} Fallback",
            f"# {zahl} {der} Prosa-Zeilen, die Marker {enthalten}",
            "# voice naming schema: piper_de, z. B. for the offline engine",
        ]
        assert all(inv.wide_prose_hits(line) == 1 for line in samples), samples
        assert inv.hits_in_prose(samples[0]) == 0, (
            "the first sample must stay invisible to the narrow metric, or the test proves nothing"
        )

    def test_a_wide_word_is_caught_whatever_its_case(self):
        """A German noun at the head of a comment is the commonest shape, and it was missed.

        The umlaut class used to require a lowercase umlaut inside the word, so the
        capitalised forms — the way German nouns open a sentence — scored nothing, and a
        worker found the gap by counting the difference between the number and the file.
        Built from the instrument's own vocabulary so this file keeps carrying no German
        literal of its own.
        """
        inv = gate.inventory
        umlaut_words = [w for w in inv.HINTS if any(c in w for c in "äöüß")]
        assert umlaut_words, "the vocabulary must contain umlauted words to test this"
        for word in umlaut_words:
            assert inv.wide_prose_hits(f"# {word}") == 1, word
            assert inv.wide_prose_hits(f"# {word.capitalize()}") == 1, word
        assert inv.wide_prose_hits("# Xbernehmen Ynderungen") == 0

    def test_a_german_noun_without_an_umlaut_still_needs_the_list(self):
        """The net sees vocabulary, not grammar: an unlisted noun stays invisible.

        `Ansicht`, `Vorlagen` and `bestand` scored nothing in the literal census, where  # language-gate: ignore (the instrument's own vocabulary words, named verbatim — asserted below via inv.HINTS)
        the wide pass flagged 110 lines and a reader counted about 230. Three of those
        nouns are now in the list, and the limitation is asserted rather than trusted.
        """
        inv = gate.inventory
        nouns = ["ansicht", "vorlagen", "bestand", "datei", "ordner"]
        for noun in nouns:
            assert noun in inv.HINTS, noun
        # assembled from the list itself, so the file still carries no German literal
        first, second, third = (inv.HINTS[inv.HINTS.index(n)] for n in nouns[:3])
        assert inv.wide_prose_hits(f"# {first} {second} {third}") == 1
        assert "prioritiser" in inv.wide_prose_hits.__doc__, (
            "the function producing the completion number has to state its own limit"
        )

    def test_the_wide_list_carries_the_nouns_the_sweep_reported(self):
        """Wave 11 (2026-10-09): the workers' eye-reports are how the net gets wider.

        Five packages named German words they had translated that `--wide` scored as zero
        — among them `Welle`, `Zeitplan`, `Datenschutz`, `Volltextsuche`, `Ziehkante` and  # language-gate: ignore (words the wave 11 workers reported, named verbatim — asserted below via inv.WIDE_EXTRA)
        `Generierung`. They are in the list now.  # language-gate: ignore (continuation of the same reported word list)

        `fake` was reported in the same breath and deliberately left OUT: it is an English
        word, and with it the completion measure jumped from 36 files / 44 lines to 90 /
        125 by flagging ordinary English comments ("no fake green", `def fake_call`). A
        recall fix that manufactures false positives is not a recall fix.
        """
        inv = gate.inventory
        for word in ("welle", "zeitplan", "datenschutz", "volltextsuche", "ziehkante", "generierung"):
            assert word in inv.WIDE_EXTRA, word
        assert "fake" not in inv.WIDE_EXTRA
        # assembled from the list, so this file keeps no German literal of its own
        welle = next(w for w in inv.WIDE_EXTRA if w == "welle")
        assert inv.wide_prose_hits(f"# {welle.capitalize()} 3: utility tools T1-T4") == 1

    def test_the_net_does_not_call_an_english_word_german(self):
        """Round 2 (2026-10-09): `listen` was in the vocabulary and it is not German.

        It scored the TCP socket state `LISTEN` as developer German — in
        `scripts/stress_1000_messages.py:479,501` and in a half-translated docstring —
        so a worker had to spend an escape valve on an English word. The plural of the
        wave name was the opposite failure: the plural was invisible while its singular was
        listed, because the word-boundary lookahead does not match inflection.
        """
        inv = gate.inventory
        assert "listen" not in inv.MARKERS
        assert "listen" not in inv.HINTS
        for word in ("wellen", "waehrend", "gekuerzt", "aehnlich", "installieren"):
            assert word in inv.WIDE_EXTRA, word

    def test_the_wide_net_leaves_plain_english_alone(self):
        """Higher recall may be noisy, but it must not flag an ordinary English comment."""
        samples = [
            "# the number of prose lines holding a marker word",
            "# npm install as a fallback when the lockfile is missing",
            "# loading a voice model for the offline engine",
            "# it is used only when the user asks for it",
        ]
        assert [gate.inventory.wide_prose_hits(line) for line in samples] == [0, 0, 0, 0], samples

    def test_the_wide_net_reuses_the_same_escape_valve(self):
        """A quoted product label stays exempt in the second pass too."""
        markers = gate.inventory.MARKERS
        line = f"# the badge reads {markers[0]} {markers[1]} verbatim {gate.inventory.PRAGMA}"
        assert gate.inventory.wide_prose_hits(line) == 0

    def test_a_url_inside_a_fixture_is_not_developer_prose(self):
        """A bare `//` scan read a URL's slashes as a comment, so the file could never reach zero.

        Both translation workers of wave 4 reported it independently: an asserted markdown fixture
        holds a `https://` link with a marker word behind it, and prose mode scored that string
        literal as developer prose forever — clearing it would have meant editing test data.
        """
        markers = gate.inventory.MARKERS
        text = f"const MSG = {{ content: '[a](https://example.com/{markers[0]}) {markers[1]} [b](x)' }}\n"
        assert gate.inventory.clike_prose(text) == ""
        assert gate.inventory.hits_in_prose(gate.inventory.clike_prose(text)) == 0

    def test_an_apostrophe_in_jsx_does_not_swallow_the_comment_after_it(self):
        """Closing a quote on the same line is what keeps prose mode from going blind."""
        markers = gate.inventory.MARKERS
        text = f"<p>don't panic</p>\n// {markers[0]} {markers[1]}\n"
        prose = gate.inventory.clike_prose(text)
        assert f"{markers[0]} {markers[1]}" in prose

    def test_a_template_literal_and_a_block_comment_are_told_apart(self):
        markers = gate.inventory.MARKERS
        text = f"const u = `https://example.com/{markers[0]}`\n/* {markers[1]} {markers[2]} */\n"
        prose = gate.inventory.clike_prose(text)
        assert "https" not in prose
        assert f"{markers[1]} {markers[2]}" in prose


class TestOrphanBaselineEntry:
    """A baseline promises about files the tree holds; deleting the file has to end the promise.

    `evaluate` compares the union of baseline and measured keys, so an entry for a path that is
    gone reads as `old = N, new = 0` and lands in `lowered`. That is the shape of a hole: delete a
    file with N German lines, leave its entry in the JSON, and the path can come back carrying N
    lines again — the per-file ratchet has nothing to compare against, because the number it holds
    was earned by a file that no longer existed when it was last measured.
    """

    GONE = "core/deleted.py"

    def test_an_entry_for_a_path_the_tree_does_not_hold_refuses_to_judge(self, tmp_path, capsys):
        """GIVEN a baseline naming a deleted path WHEN the whole tree is measured THEN exit 2."""
        path = baseline(tmp_path, {SOURCE: 1, self.GONE: 3})
        code = run(tmp_path, path, tree(german=1))
        out = capsys.readouterr()
        assert code == 2, "a stale entry must not read as a clean tree"
        assert self.GONE in out.err, out.err

    def test_the_hole_lives_in_the_comparison_itself(self):
        """Measured inside the instrument: `evaluate` scores a deleted file's German as progress.

        An entry with nothing measured against it is `old = N, new = 0`, which is `lowered` and
        never a regression. That is why the orphan rule sits in front of the comparison and not
        inside it — and why a path that returns *before* anyone ran the whole-tree pass is the
        case the refusal in the test above exists to make impossible.
        """
        result = gate.evaluate({self.GONE: 3}, {})
        assert result["regressions"] == []
        assert [row[0] for row in result["lowered"]] == [self.GONE]

    def test_pruning_the_entry_leaves_the_recreated_file_without_an_allowance(self, tmp_path, capsys):
        """GIVEN the stale entry pruned by --update WHEN the path returns with German THEN it fails."""
        path = baseline(tmp_path, {SOURCE: 1, self.GONE: 3})
        assert run(tmp_path, path, tree(german=1), "--update") == 0
        capsys.readouterr()
        grown = tree(german=1)
        grown[self.GONE] = german_lines(2, gate.inventory.MARKERS)
        assert run(tmp_path, path, grown) == 1
        assert self.GONE in capsys.readouterr().out

    def test_a_file_that_went_clean_is_lowered_and_not_refused(self, tmp_path, capsys):
        """An existing path at zero German is progress; the orphan rule is about missing paths."""
        path = baseline(tmp_path, {SOURCE: 3})
        assert run(tmp_path, path, {SOURCE: clean_lines(4)}) == 0
        assert "PASS" in capsys.readouterr().out

    def test_the_staged_pass_does_not_judge_orphans(self, tmp_path, capsys):
        """Two modes, two scopes: a commit carries few paths, so an absent entry is normal there.

        The orphan rule belongs to the whole-tree pass — the one `ci-gates.yml` runs on a clean
        checkout, where every tracked path is present by definition.
        """
        path = baseline(tmp_path, {SOURCE: 1, self.GONE: 3})
        assert run(tmp_path, path, tree(german=1), "--staged") == 0
        assert "ERROR" not in capsys.readouterr().err
