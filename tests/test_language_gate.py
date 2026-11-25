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
import os
import re
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent
#: The gate under test. The seam exists for one thing: a wave that changes the gate proves its new
#: case red against the previous copy and green against the new one, in one command, with the old
#: copy kept outside the tree.
GATE_PATH = Path(os.environ.get("EPHE_LANGUAGE_GATE_PATH", REPO / "scripts" / "language_gate.py"))


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
    def test_a_cleaner_tree_passes_and_reports_the_smaller_total(self, tmp_path, capsys):
        """GIVEN three lines baselined WHEN only one is left THEN the pass carries the current total."""
        path = baseline(tmp_path, {SOURCE: 3})
        code = run(tmp_path, path, tree(german=1))
        out = capsys.readouterr().out
        assert code == 0
        assert "PASS" in out
        assert "total 3 -> 1 lines" in out

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


class TestTheOfferIsPrintedWhenActionable:
    """The offer belongs to the passing run, once, in the family's two lines.

    `prose_tells.py` and `home_isolation_gate.py` close a pass with the offer to lower the
    baseline, and this gate reads the same way. The offer is tied to the action, not to a
    flag: at least one file sits below its entry, so re-measuring would lower the number.
    A tree that matches the baseline has nothing to offer and stays quiet.
    """

    def test_a_cleaner_tree_offers_the_update_without_a_flag(self, tmp_path, capsys):
        """GIVEN three baselined lines WHEN one is left THEN the pass carries the offer."""
        path = baseline(tmp_path, {SOURCE: 3})
        assert run(tmp_path, path, tree(german=1)) == 0
        out = capsys.readouterr().out
        assert "PASS" in out
        assert "1 file(s) sit below their baseline entry: the baseline can be lowered" in out
        assert "language_gate.py --update" in out

    def test_the_offer_prints_once_for_every_lowered_file(self, tmp_path, capsys):
        """GIVEN two files below their entries WHEN the gate passes THEN one hint counts both."""
        other = "core/other.py"
        path = baseline(tmp_path, {SOURCE: 3, other: 5})
        files = tree(german=1)
        files[other] = clean_lines(2)
        assert run(tmp_path, path, files) == 0
        out = capsys.readouterr().out
        assert "2 file(s) sit below their baseline entry" in out
        assert out.count("the baseline can be lowered") == 1
        assert out.count("language_gate.py --update") == 1

    def test_a_matching_tree_has_nothing_to_offer(self, tmp_path, capsys):
        """GIVEN a baseline that matches WHEN the gate runs THEN no lowering hint appears."""
        path = baseline(tmp_path, {SOURCE: 2})
        assert run(tmp_path, path, tree(german=2)) == 0
        out = capsys.readouterr().out
        assert "PASS" in out
        assert "can be lowered" not in out

    def test_a_failing_run_prints_no_offer(self, tmp_path, capsys):
        """GIVEN one file above and one below WHEN the gate runs THEN growth decides the text."""
        lower = "core/lower.py"
        path = baseline(tmp_path, {SOURCE: 1, lower: 5})
        files = {SOURCE: german_lines(3, gate.inventory.MARKERS), lower: clean_lines(2)}
        assert run(tmp_path, path, files) == 1
        out = capsys.readouterr().out
        assert "FAIL" in out
        assert "can be lowered" not in out

    def test_a_staged_run_leaves_the_whole_tree_offer_out(self, tmp_path, capsys):
        """GIVEN two staged paths WHEN the rest is below its baseline THEN the pass is silent.

        `--staged` measures the few blobs one commit carries, so a baseline entry it never
        read is out of scope rather than lower. The offer names a whole-tree `--update`,
        which a pre-commit hook must not invite while lint-staged has unstaged work hidden.
        """
        other = "core/other.py"
        path = baseline(tmp_path, {SOURCE: 3, other: 5})
        list_files, read_text = injected({SOURCE: clean_lines(1)})
        code = gate.main(
            ["--baseline", str(path), "--root", str(tmp_path), "--staged"],
            list_files=list_files,
            read_text=read_text,
        )
        out = capsys.readouterr().out
        assert code == 0
        assert "PASS" in out
        assert "can be lowered" not in out


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
        word_may, word_as, word_count = (
            inv.HINTS[inv.HINTS.index("darf")],
            inv.HINTS[inv.HINTS.index("als")],
            inv.HINTS[inv.HINTS.index("zahl")],
        )
        word_the, word_contain = inv.HINTS[inv.HINTS.index("der")], inv.HINTS[inv.HINTS.index("enthalten")]
        samples = [
            f"# PWA-Build {word_may} den Start nie blockieren",
            f"# lockfile-Probleme: npm install {word_as} Fallback",
            f"# {word_count} {word_the} Prosa-Zeilen, die Marker {word_contain}",
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
        """The net reads vocabulary: a noun the list does not carry stays invisible.

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
        wave = next(w for w in inv.WIDE_EXTRA if w == "welle")
        assert inv.wide_prose_hits(f"# {wave.capitalize()} 3: utility tools T1-T4") == 1

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


#: The sentence the probes below ask about, assembled from the instrument's own list so this file
#: holds no German of its own — the same rule `german_lines` above follows.
SPOKEN = " ".join(gate.inventory.MARKERS[:4])
#: How many lines the line ratchet scores in one of the sources below: the marker comment and the
#: message line, each holding one of the assembled marker words, counted by the instrument itself.
SPOKEN_LINES = 1


def suite_source(*, sentence: str, marker: str = "") -> str:
    """A test module whose second assert answers in `sentence`, optionally marked on its line."""
    pragma = f"  # {marker}" if marker else ""
    return (
        "import pytest\n\n\n"
        "def test_one():\n    assert 1 == 1, \"the counter advanced\"\n\n\n"
        f"def test_two():\n    assert 2 == 2, \"{sentence}\"{pragma}\n"
    )


class TestMessageLeg:
    """The second leg, and the disagreement it exists for.

    `counts_for` scores every line of a file, string literals included — its own docstring says the
    number "tracks growth alone". So the ratchet did see these sentences, measured them into the
    baseline, and stopped asking: a German message in a file the baseline already tolerates is free.
    This leg refuses at zero, by node, with no baseline to age into.
    """

    SUITE_FILE = "tests/test_a_capability.py"

    def test_a_german_assert_message_fails_the_gate_and_is_named(self, tmp_path, capsys):
        """GIVEN a baseline that already tolerates the German line WHEN the gate runs THEN this leg fails by file and line."""
        path = baseline(tmp_path, {self.SUITE_FILE: SPOKEN_LINES})
        code = run(tmp_path, path, {self.SUITE_FILE: suite_source(sentence=SPOKEN)})
        out = capsys.readouterr().out
        assert code == 1
        assert "language gate: PASS" in out, "the ratchet is clean here; only the new leg refuses"
        assert "message language: FAIL" in out
        assert f"{self.SUITE_FILE}:9" in out
        assert "assert message" in out

    def test_an_english_suite_passes_both_legs(self, tmp_path, capsys):
        """GIVEN the same file with English messages WHEN the gate runs THEN both legs pass."""
        path = baseline(tmp_path, {})
        code = run(tmp_path, path, {self.SUITE_FILE: suite_source(sentence="the counter did not advance")})
        out = capsys.readouterr().out
        assert code == 0
        assert "message language: PASS" in out

    def test_a_marked_product_message_is_not_a_finding(self, tmp_path, capsys):
        """German the product itself says is the subject of the test, so the marker carries it."""
        path = baseline(tmp_path, {self.SUITE_FILE: SPOKEN_LINES})
        files = {
            self.SUITE_FILE: suite_source(
                sentence=SPOKEN,
                marker=f"{gate.messages.MESSAGE_PRAGMA} (the refusal the product shows)",
            )
        }
        assert run(tmp_path, path, files) == 0
        assert "message language: PASS" in capsys.readouterr().out

    def test_a_marker_without_a_reason_does_not_clear_it(self, tmp_path, capsys):
        """An exemption nobody can read is overlooked the next quarter, so the reason is required."""
        path = baseline(tmp_path, {self.SUITE_FILE: SPOKEN_LINES})
        files = {self.SUITE_FILE: suite_source(sentence=SPOKEN, marker=gate.messages.MESSAGE_PRAGMA)}
        code = run(tmp_path, path, files)
        out = capsys.readouterr().out
        assert code == 1
        assert "unexplained exemption" in out

    def test_the_rule_reads_the_suite_and_nothing_else(self, tmp_path, capsys):
        """The claim is about the suite's voice, so the leg stays out of product code.

        The same sentence in `core/` is not this leg's business: the third leg, `surface_leg`,
        owns a sentence product code addresses a person with, and it is the one that refuses here.
        Asked directly, this leg passes the product file — which is the scope claim, kept honest by
        asserting both halves.
        """
        path = baseline(tmp_path, {self.SUITE_FILE: 0, SOURCE: SPOKEN_LINES})
        files = {
            self.SUITE_FILE: suite_source(sentence="the counter did not advance"),
            SOURCE: suite_source(sentence=SPOKEN),
        }
        list_files, read_text = injected(files)
        code, _ = gate.message_leg([self.SUITE_FILE, SOURCE], read_text, tmp_path)
        assert code == 0, "the message leg reads the suite and leaves product code alone"
        assert run(tmp_path, path, files) == 1
        out = capsys.readouterr().out
        assert "message language: PASS" in out
        assert "surface language: FAIL" in out, "the refusal here belongs to the leg that owns product sentences"

    def test_a_file_the_leg_cannot_parse_is_reported_not_skipped(self, tmp_path, capsys):
        """A leg that passes because it read nothing would be the failure this rule exists to stop."""
        path = baseline(tmp_path, {self.SUITE_FILE: 0})
        code = run(tmp_path, path, {self.SUITE_FILE: "def test(:\n"})
        out = capsys.readouterr().out
        assert code == 1
        assert "unparsable" in out


#: A German message assembled from the leg's own word lists: this file carries no German of its
#: own, and the fixture cannot drift away from the detector it exercises.
SURFACE_GERMAN = sorted(gate.SURFACE_HIGH)[0] + ": " + "{value!r}" + " (" + sorted(gate.SURFACE_HIGH)[1] + ")"
#: The same shape in the language the rule asks for there.
SURFACE_ENGLISH = "unknown field: " + "{value!r}" + " (allowed: 1, 2)"

#: The sky chart's lines as they shipped before this wave, quoted verbatim from
#: `core/ephemeris.py`. A human read seven German lines there; the instrument measured one, and the
#: leg as first written measured the four sentences that merely printed. The case exists so that a
#: vocabulary hole shows up as a red test, and so the file keeps the sentences it used to ship.
PRE_WAVE_SKY = (
    "◍ Ephe Ephemeris — die letzten {days} Tage",  # language-gate: ignore (quoted chart heading as it shipped, core/ephemeris.py:130)
    "Bahnen, keine Inhalte — WANN Ephe lebendig war, nie WAS geschah.",  # language-gate: ignore (quoted chart line as it shipped, core/ephemeris.py:131)
    "Der Himmel wartet.",  # language-gate: ignore (quoted chart line as it shipped, core/ephemeris.py:134)
    "Sichtweite {days} Tage · {total_n} Bahnen",  # language-gate: ignore (quoted chart footer as it shipped, core/ephemeris.py:149)
)


def product_source(*, message: str, kind: str = "raise", marker: str = "") -> str:
    """A product module that says `message` to a person on line 2 of one function."""
    pragma = f"  # {marker}" if marker else ""
    statement = f'raise ValueError(f"{message}")' if kind == "raise" else f'print(f"{message}")'
    return f"def run(value):\n    {statement}{pragma}\n    return value\n"


def sky_source() -> str:
    """The four pre-wave chart lines in the shape they shipped in: a list, an append, a footer."""
    heading, subtitle, waiting, footer = PRE_WAVE_SKY
    return (
        "def chart(events, days, total_n):\n"
        "    lines = [\n"
        '        f"' + heading + '",\n'
        '        "' + subtitle + '",\n'
        "    ]\n"
        "    if not events:\n"
        '        lines.append("' + waiting + '")\n'
        '    foot = f"' + footer + '"\n'
        '    lines.append(f"({foot})")\n'
        '    return "\\n".join(lines)\n'
    )


class TestSurfaceLeg:
    """The third leg, and the hole it exists for.

    The ratchet scores lines and compares a count, so a German `ValueError` in a file the baseline
    already tolerates is free — and `core/voice_config.py` scored zero lines with three of them in
    it, because the words it uses (`Unbekannte`, `erlaubt`) are in neither of the instrument's two
    lists. The message leg stops at `tests/`. This leg reads the sentences product code addresses a
    person with, carries its own word lists, and keeps no baseline.
    """

    def test_a_german_raise_message_fails_the_gate_and_is_named(self, tmp_path, capsys):
        """GIVEN a file the baseline never mentions WHEN its one message is German THEN the gate is red by file and line."""
        path = baseline(tmp_path, {})
        code = run(tmp_path, path, {SOURCE: product_source(message=SURFACE_GERMAN)})
        out = capsys.readouterr().out
        assert code == 1
        assert "language gate: PASS" in out, "the ratchet is clean here; only the new leg refuses"
        assert "surface language: FAIL" in out
        assert f"{SOURCE}:2" in out
        assert "raise" in out

    def test_planted_german_in_a_plain_product_file_is_red_with_file_and_delta(self, tmp_path, capsys):
        """GIVEN untouched product code WHEN German prose and a German message arrive THEN the report names file, delta and line."""
        path = baseline(tmp_path, {})
        files = {SOURCE: german_lines(3, gate.inventory.MARKERS) + "\n" + product_source(message=SURFACE_GERMAN)}
        code = run(tmp_path, path, files)
        out = capsys.readouterr().out
        assert code == 1
        assert f"{SOURCE}: 0 -> 3 (+3)" in out
        assert "surface language: FAIL" in out
        assert f"{SOURCE}:5" in out

    def test_the_line_ratchet_scores_that_same_message_as_clean(self):
        """The disagreement in one assertion: the number sees nothing, the node sees the sentence."""
        list_files, read_text = injected({SOURCE: product_source(message=SURFACE_GERMAN)})
        assert gate.measure(Path("."), list_files=list_files, read_text=read_text) == {}
        findings = gate.surface_findings(SOURCE, product_source(message=SURFACE_GERMAN))
        assert [f.kind for f in findings] == ["raise"]

    def test_an_english_message_passes_all_three_legs(self, tmp_path, capsys):
        """The English twin of the planted sentence passes all three legs."""
        path = baseline(tmp_path, {})
        code = run(tmp_path, path, {SOURCE: product_source(message=SURFACE_ENGLISH)})
        out = capsys.readouterr().out
        assert code == 0
        assert "surface language: PASS" in out

    def test_a_printed_line_is_read_the_way_a_raised_one_is(self, tmp_path, capsys):
        """`print` is as user-facing as `raise`, so the leg cannot stop at exceptions."""
        path = baseline(tmp_path, {})
        code = run(tmp_path, path, {SOURCE: product_source(message=SURFACE_GERMAN, kind="print")})
        out = capsys.readouterr().out
        assert code == 1
        assert "output" in out

    def test_the_sky_chart_lines_are_all_findings(self):
        """The seven lines a human read in the chart, including the four that only ever printed."""
        findings = gate.surface_findings(SOURCE, sky_source())
        assert len(findings) == len(PRE_WAVE_SKY), [f.quote for f in findings]
        assert {f.kind for f in findings} == {"assembled text"}
        assert len({f.line for f in findings}) == len(PRE_WAVE_SKY), "one finding per shipped line, not one per file"

    def test_a_defused_marker_list_leaves_this_leg_red(self, tmp_path, capsys, monkeypatch):
        """The leg exists because of a hole in the instrument's list, so widening that hole cannot silence it."""
        monkeypatch.setattr(gate.inventory, "MARKERS", [])
        monkeypatch.setattr(gate.inventory, "WORD", re.compile("(?!a)a"))
        path = baseline(tmp_path, {})
        code = run(tmp_path, path, {SOURCE: product_source(message=SURFACE_GERMAN)})
        out = capsys.readouterr().out
        assert code == 1
        assert "language gate: PASS" in out
        assert "surface language: FAIL" in out
        assert f"{SOURCE}:2" in out

    def test_a_marked_product_message_with_a_reason_is_not_a_finding(self, tmp_path, capsys):
        """German a program shows its user is the product's own surface, and the marker carries it."""
        path = baseline(tmp_path, {})
        files = {
            SOURCE: product_source(
                message=SURFACE_GERMAN,
                marker=f"{gate.messages.MESSAGE_PRAGMA} (the refusal the settings panel shows)",
            )
        }
        assert run(tmp_path, path, files) == 0
        assert "surface language: PASS" in capsys.readouterr().out

    def test_a_marker_without_a_reason_is_reported(self, tmp_path, capsys):
        """An exemption nobody can read is overlooked next quarter, so the reason is required."""
        path = baseline(tmp_path, {})
        files = {SOURCE: product_source(message=SURFACE_GERMAN, marker=gate.messages.MESSAGE_PRAGMA)}
        code = run(tmp_path, path, files)
        assert code == 1
        assert "unexplained exemption" in capsys.readouterr().out

    def test_the_suites_own_voice_stays_the_other_legs_business(self, tmp_path):
        """Same sentence, other directory: this leg reads product code and leaves `tests/` alone."""
        code, lines = gate.surface_leg(
            [TestMessageLeg.SUITE_FILE], lambda rel: product_source(message=SURFACE_GERMAN), tmp_path
        )
        assert code == 0
        assert "surface language: PASS" in lines[0]

    def test_a_product_path_is_never_read_by_this_leg(self):
        """The bundles are the German surface; the scope function is what keeps them out."""
        assert gate.in_surface_scope("app/src/locales/de.json") is False
        assert gate.in_surface_scope("skills/survival/tool.py") is False
        assert gate.in_surface_scope("core/voice_config.py") is True

    def test_an_unparsable_product_file_is_reported_not_skipped(self, tmp_path, capsys):
        """A leg that reads nothing would report the quiet pass this rule was written against."""
        path = baseline(tmp_path, {})
        code = run(tmp_path, path, {SOURCE: "def run(:\n"})
        out = capsys.readouterr().out
        assert code == 1
        assert "unparsable" in out


#: Written from code points on purpose: a test that plants these characters would
#: otherwise trip the leg it tests, and the suite is one of the files the leg reads.
HAN = chr(0x4E2D) + chr(0x6587)
HIRAGANA = chr(0x306B) + chr(0x308C)
HANGUL = chr(0xD55C) + chr(0xAD55)
FULLWIDTH_BAR = chr(0xFF5C)

JSON_SOURCE = "marketplace/example.json"


def run_cjk(files: dict[str, str], exceptions: dict[str, str] | None = None):
    """The fourth leg over an injected tree, with the named exceptions swapped for the test's."""
    keep = gate.CJK_EXCEPTIONS
    if exceptions is not None:
        gate.CJK_EXCEPTIONS = exceptions
    try:
        return gate.cjk_leg(list(files), lambda rel: files[rel], REPO)
    finally:
        gate.CJK_EXCEPTIONS = keep


class TestCjkLeg:
    """The tree is written in Han-free English: one character outside a named file is the finding."""

    def test_a_han_character_in_a_product_module_is_a_finding(self):
        """Given a Python module with one planted character, When the leg reads it, Then the file and line are named."""
        files = {SOURCE: f"def run():\n    return 1  # {HAN}\n"}
        code, lines = run_cjk(files, {})
        assert code == 1
        assert any(f"{SOURCE}:2" in line for line in lines)
        assert any("Han" in line for line in lines)

    def test_a_han_character_in_a_json_file_is_a_finding(self):
        """Given a registry-shaped JSON file, When the leg reads it, Then it is reported like any other file."""
        files = {JSON_SOURCE: '{{"name": "{0}"}}\n'.format(HAN)}
        code, lines = run_cjk(files, {})
        assert code == 1
        assert any(JSON_SOURCE in line and "Han" in line for line in lines)

    def test_each_script_is_named_by_its_own_class(self):
        """Given three scripts in three files, When the leg reads them, Then each names the class it belongs to."""
        files = {
            "core/a.py": f"# {HAN}\n",
            "core/b.py": f"# {HIRAGANA}\n",
            "core/c.py": f"# {HANGUL}\n",
        }
        code, lines = run_cjk(files, {})
        assert code == 1
        joined = "\n".join(lines)
        for script in ("Han", "Hiragana", "Hangul"):
            assert script in joined

    def test_fullwidth_punctuation_counts_as_script(self):
        """Given a fullwidth bar from a model token, When the leg reads it, Then the file is reported."""
        files = {"core/token.py": f'LABEL = "{FULLWIDTH_BAR}tool"\n'}
        code, lines = run_cjk(files, {})
        assert code == 1
        assert any("CJK punctuation" in line for line in lines)

    def test_a_named_file_may_carry_its_own_script(self):
        """Given a file named with its reason, When the leg reads it, Then it passes and says how many are named."""
        files = {"README.zh-CN.md": f"# {HAN}\n"}
        code, lines = run_cjk(files, {"README.zh-CN.md": "the Chinese README, product copy"})
        assert code == 0
        assert "PASS" in lines[0]

    def test_a_sibling_of_a_named_file_stays_read(self):
        """Given one named file in a directory, When the leg reads its neighbour, Then the neighbour is still reported."""
        files = {"docs/zh/README.md": f"# {HAN}\n", "docs/zh/notes.md": f"# {HAN}\n"}
        code, lines = run_cjk(files, {"docs/zh/README.md": "a translated page"})
        assert code == 1
        assert any("docs/zh/notes.md" in line for line in lines)
        assert not any("docs/zh/README.md" in line for line in lines)

    def test_an_exception_naming_a_clean_file_is_a_finding(self):
        """Given an exception whose file no longer carries the script, When the leg runs, Then the stale entry is reported."""
        files = {"docs/zh/README.md": "# English only\n"}
        code, lines = run_cjk(files, {"docs/zh/README.md": "a translated page"})
        assert code == 1
        assert any("carries no such character" in line for line in lines)

    def test_an_exception_without_a_reason_is_a_finding(self):
        """Given an exception with an empty reason, When the leg runs, Then the missing reason is reported."""
        files = {"docs/zh/README.md": f"# {HAN}\n"}
        code, lines = run_cjk(files, {"docs/zh/README.md": "   "})
        assert code == 1
        assert any("without a reason" in line for line in lines)

    def test_a_line_pragma_does_not_exempt_a_character(self):
        """Given the pragma that exempts a German line, When the leg reads the same line, Then the character still reports."""
        files = {SOURCE: f"# language-gate: ignore (a German line) {HAN}\n"}
        code, lines = run_cjk(files, {})
        assert code == 1
        assert "Han" in "\n".join(lines)

    def test_the_committed_exceptions_cover_the_tree(self):
        """Given this checkout as it stands, When the leg reads every tracked file, Then nothing is reported."""
        tracked = gate.tracked_files(REPO)()
        code, lines = gate.cjk_leg(tracked, None, REPO)
        assert code == 0, lines
        assert f"{len(gate.CJK_EXCEPTIONS)} named file(s)" in lines[0]


#: The register's lazy copy asset and its English twin, as they sit in the tree.
COPY_ASSET = "app/src/lib/settingsCopy.de.json"
COPY_TWIN = "app/src/lib/settingsCopy.en.json"


def copy_json(leaves: int, *, plant: dict[str, str] | None = None) -> str:
    """The asset's shape: one `settings` object of leaf sentences, plus any field a test plants."""
    markers = gate.inventory.MARKERS
    settings = {
        f"row{index}Hint": " ".join(markers[(index + offset) % len(markers)] for offset in range(3))
        for index in range(leaves)
    }
    return json.dumps({"settings": {**settings, **(plant or {})}}, ensure_ascii=False, indent=1)


def english_copy_json(leaves: int) -> str:
    """The same shape in the tree's own language."""
    settings = {f"row{index}Hint": f"Sets how the {index} row behaves." for index in range(leaves)}
    return json.dumps({"settings": settings}, ensure_ascii=False, indent=1)


def developer_german() -> str:
    """A German sentence the surface leg's own word lists recognise."""
    high = sorted(gate.SURFACE_HIGH)
    return f"{high[0]} {high[1]} {high[2]}"


class TestNamedProductCopy:
    """The one named class of paths whose German a reader is shown, and what that costs.

    `language_inventory.PRODUCT_TEXT_PATHS` is the tree's only list of them, and the two legs treat
    it differently on purpose: the ratchet leaves those paths out, because it measures developer
    prose and a translation of the product is not a regression — and the surface leg reads them all
    the harder, because a string in a copy file that nobody is ever shown is developer prose in
    copy's clothes. Every case below pins one direction of that bargain.
    """

    def test_the_named_asset_never_moves_the_ratchet_and_is_printed_by_the_surface_leg(
        self, tmp_path, capsys
    ):
        """GIVEN fifty-six German lines in the named asset WHEN the gate runs THEN the ratchet stays at zero and the surface leg reports the file with its count."""
        path = baseline(tmp_path, {})
        code = run(tmp_path, path, {COPY_ASSET: copy_json(56)})
        out = capsys.readouterr().out
        assert code == 0
        assert "language gate: PASS" in out
        assert "total 0 lines over 0 files" in out, "the copy is not developer prose, so the ratchet must not see it"
        assert f"product copy: {COPY_ASSET} — 56 German line(s) read, 0 outside what a reader is shown" in out

    def test_the_english_twin_stays_quiet(self, tmp_path, capsys):
        """GIVEN the English half of the same asset WHEN the gate runs THEN no leg prints it."""
        path = baseline(tmp_path, {})
        code = run(tmp_path, path, {COPY_TWIN: english_copy_json(56)})
        out = capsys.readouterr().out
        assert code == 0
        assert COPY_TWIN not in out, "English is the tree's own language; it needs no name and no line"

    def test_the_same_file_without_its_name_is_red_with_its_line_count(self, tmp_path, capsys, monkeypatch):
        """GIVEN byte-identical copy text whose path is no longer named WHEN the gate runs THEN the ratchet reports all of it."""
        monkeypatch.setattr(gate.inventory, "PRODUCT_TEXT_PATHS", ("app/src/locales/*.json",))
        path = baseline(tmp_path, {})
        code = run(tmp_path, path, {COPY_ASSET: copy_json(56)})
        out = capsys.readouterr().out
        assert code == 1
        assert f"{COPY_ASSET}: 0 -> 56 (+56)" in out
        assert "product copy:" not in out, "an un-named path is an ordinary file, and the ratchet counts it"

    def test_a_file_beside_the_named_one_is_red(self, tmp_path, capsys):
        """GIVEN the same German under a path one character away from a named one WHEN the gate runs THEN it fails."""
        path = baseline(tmp_path, {})
        code = run(tmp_path, path, {COPY_ASSET: copy_json(56), f"{COPY_ASSET}.copy.json": copy_json(7)})
        out = capsys.readouterr().out
        assert code == 1
        assert f"{COPY_ASSET}.copy.json: 0 -> 7 (+7)" in out, "the list does not leak to its neighbours"

    def test_german_developer_prose_in_code_is_still_red(self, tmp_path, capsys):
        """GIVEN the named copy exists in the tree WHEN a module gains German prose THEN the ratchet still fails by name."""
        path = baseline(tmp_path, {})
        code = run(tmp_path, path, {COPY_ASSET: copy_json(56), SOURCE: german_lines(3, gate.inventory.MARKERS)})
        out = capsys.readouterr().out
        assert code == 1
        assert f"{SOURCE}: 0 -> 3 (+3)" in out

    def test_german_nobody_is_shown_fails_through_the_surface_leg(self, tmp_path, capsys):
        """GIVEN a German note inside the named asset that no reader is ever shown WHEN the gate runs THEN the surface leg reports it, though the ratchet exempts the file."""
        path = baseline(tmp_path, {})
        code = run(tmp_path, path, {COPY_ASSET: copy_json(20, plant={"_devNote": developer_german()})})
        out = capsys.readouterr().out
        assert code == 1
        assert "language gate: PASS" in out, "the ratchet is exempt here; only this leg can catch it"
        assert "surface language: FAIL" in out
        assert "not user copy" in out
        assert "_devNote" in out

    def test_a_copy_file_that_stops_being_a_copy_file_is_measured_again(self, tmp_path, capsys):
        """GIVEN the named path holding text that is no one JSON object WHEN the gate runs THEN its German is counted like any other file's."""
        path = baseline(tmp_path, {})
        code = run(tmp_path, path, {COPY_ASSET: german_lines(9, gate.inventory.MARKERS)})
        out = capsys.readouterr().out
        assert code == 1
        assert f"{COPY_ASSET}: 0 -> 9 (+9)" in out
        assert "not a JSON object, measured as an ordinary file" in out

    def test_neither_gate_keeps_a_second_list(self):
        """GIVEN both gates read the instrument WHEN their modules are loaded THEN neither holds its own tuple of paths."""
        assert not hasattr(gate, "PRODUCT_TEXT_PATHS")
        assert gate.inventory.PRODUCT_TEXT_PATHS == __import__("language_inventory").PRODUCT_TEXT_PATHS


class TestStagedPassHonoursTheName:
    """The hook's own path, where the tree arrives as index blobs.

    The commit that introduced the copy asset was refused here and nowhere else — the whole-tree run
    passed, `--staged` measured the same bytes through a second code path that had never heard of the
    named class. Both paths now go through `measure`, and these two cases keep them together.
    """

    def test_the_hook_measures_a_staged_copy_file_and_passes(self, tmp_path, capsys):
        """GIVEN the named asset staged with its German WHEN the hook runs the gate THEN it passes."""
        path = baseline(tmp_path, {})
        code = run(
            tmp_path, path, {COPY_ASSET: copy_json(56), SOURCE: clean_lines(3)}, "--staged"
        )
        out = capsys.readouterr().out
        assert code == 0
        assert f"product copy: {COPY_ASSET} — 56 German line(s) read, 0 outside what a reader is shown" in out

    def test_a_staged_file_without_its_name_is_refused_by_the_hook(self, tmp_path, capsys, monkeypatch):
        """GIVEN the same staged bytes and no name on the list WHEN the hook runs the gate THEN the commit is refused with its line count."""
        monkeypatch.setattr(gate.inventory, "PRODUCT_TEXT_PATHS", ("app/src/locales/*.json",))
        path = baseline(tmp_path, {})
        code = run(tmp_path, path, {COPY_ASSET: copy_json(56)}, "--staged")
        out = capsys.readouterr().out
        assert code == 1
        assert f"{COPY_ASSET}: 0 -> 56 (+56)" in out
