"""Ephe — the new-file gate holds the paths the ratchets cannot list.

Both ratchets assemble their corpus from `git ls-files` (`scripts/prose_tells.py` puts
`PROSE_ROOTS` on that call, `scripts/language_gate.py` takes the whole checkout), so a file
a wave writes and leaves unstaged is absent from every whole-tree pass: no measured count,
no baseline entry, nothing for the union walk to compare. Wave 3 landed 87 prose tells and
27 German developer lines across 28 such files and both passes stayed green until the files
were staged.

These tests drive `scripts/new_file_check.py` through an injected path list and reader, so
they need no git checkout, no network and no fixture repository.

Given / When / Then, strictly.

No German of its own lives here: the sample prose is assembled from the instrument's own
marker list, the way `tests/test_language_gate.py` does it, so this file is read by the
language ratchet at zero.
"""
from __future__ import annotations

import importlib.util
import json
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECK_PATH = REPO / "scripts" / "new_file_check.py"


def _load_check():
    spec = importlib.util.spec_from_file_location("new_file_check_under_test", CHECK_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: Loaded once for the whole file: the builders below need the instruments' own
#: vocabulary, and a pytest fixture cannot reach it.
check = _load_check()
inventory = check.inventory
MARKERS = inventory.MARKERS

#: A committed path, and a fresh one no baseline has ever scored.
SOURCE = "core/order.py"
FRESH = "scripts/brand_new.py"


def clean_block(count: int, tag: str = "step") -> str:
    """`count` comment lines the prose instrument leaves unjudged."""
    return "\n".join(f"# {tag} {i} of the pipeline" for i in range(count))


def tell_block(count: int) -> str:
    """`count` filler lines the prose instrument scores."""
    return "\n".join(f"# Note: stage {i} belongs to the pipeline" for i in range(count))


def german_block(count: int) -> str:
    """`count` comment lines the German instrument scores, built from its own list."""
    return "\n".join(
        f"# {MARKERS[i % len(MARKERS)]} {MARKERS[(i + 1) % len(MARKERS)]}"
        for i in range(count)
    )


def planted(tree: dict[str, str]) -> tuple[Callable[[], list[str]], Callable[[str], str]]:
    """The two seams the gate measures through: the paths to judge, and their text."""
    return (lambda: sorted(tree), lambda rel: tree[rel])


def prose_baseline(tmp_path: Path, files: dict[str, int]) -> Path:
    """Write a committed tell baseline holding `files`."""
    path = tmp_path / "prose-tells-baseline.json"
    payload: dict = {
        "policy": check.tells.POLICY,
        "version": check.tells.VERSION,
        "scope": check.tells.RATCHET_SCOPE,
        "files": files,
    }
    payload["total"] = sum(files.values())
    path.write_text(json.dumps(payload, sort_keys=True, indent=1), encoding="utf-8")
    return path


def german_baseline(tmp_path: Path, files: dict[str, int]) -> Path:
    """Write a committed German baseline holding `files`."""
    path = tmp_path / "language-baseline.json"
    payload: dict = {
        "policy": check.language_gate.POLICY,
        "version": check.language_gate.VERSION,
        "files": files,
    }
    payload["total"] = sum(files.values())
    path.write_text(json.dumps(payload, sort_keys=True, indent=1), encoding="utf-8")
    return path


def run(
    tree: dict[str, str],
    tmp_path: Path,
    *flags: str,
    prose: dict[str, int] | None = None,
    german: dict[str, int] | None = None,
    paths_injected: bool = True,
) -> int:
    """Drive the gate over one fixture tree, with both baselines written first.

    `paths_injected=False` leaves the path list to the gate itself, so a test can exercise
    `--paths-from` and `EPHE_STAGED_PATHS`; the reader stays injected either way.
    """
    list_files, read_text = planted(tree)
    seam = {"list_files": list_files} if paths_injected else {}
    return check.main(
        [
            "--root", str(tmp_path),
            "--prose-baseline", str(prose_baseline(tmp_path, prose or {})),
            "--language-baseline", str(german_baseline(tmp_path, german or {})),
            *flags,
        ],
        read_text=read_text,
        **seam,
    )


class TestTheGapIsClosed:
    """The wave-3 shape: a path the tree measures for the first time, with a finding on it."""

    def test_a_fresh_path_with_a_tell_fails_and_is_named(self, tmp_path, capsys):
        """GIVEN a file no baseline covers WHEN it carries a tell THEN the gate names it."""
        code = run({FRESH: clean_block(2) + "\n" + tell_block(3)}, tmp_path)
        out = capsys.readouterr().out
        assert code == 1
        assert "FAIL" in out
        assert FRESH in out
        assert "3 tell(s)" in out

    def test_a_fresh_path_with_german_fails_and_is_named(self, tmp_path, capsys):
        """GIVEN a file no baseline covers WHEN it carries German THEN the gate names it."""
        code = run({FRESH: clean_block(2) + "\n" + german_block(4)}, tmp_path)
        out = capsys.readouterr().out
        assert code == 1
        assert FRESH in out
        assert "4 German line(s)" in out

    def test_a_fresh_clean_path_passes(self, tmp_path, capsys):
        """GIVEN a new file written in plain English WHEN the gate runs THEN it passes."""
        code = run({FRESH: clean_block(6)}, tmp_path)
        out = capsys.readouterr().out
        assert code == 0
        assert "PASS" in out

    def test_the_ratchet_comparison_cannot_see_a_path_it_never_listed(self):
        """GIVEN a tell-bearing file git never lists WHEN the ratchet compares THEN silence.

        `evaluate` walks the union of the baseline keys and the measured keys. A path that
        reached neither side contributes no key, so its count lands in `regressions`
        however large it is. This is the wave-3 landmine stated as the comparison itself,
        and the assertion below is the deliverable of this task.
        """
        tree = {SOURCE: clean_block(2), FRESH: tell_block(3)}
        list_files, read_text = planted(tree)
        measured = check.tells.counts_for([SOURCE], read_text)
        assert check.tells.evaluate({}, measured)["regressions"] == []
        tells_by_path, german_by_path = check.measure(list_files(), read_text)
        rows = check.violations([SOURCE, FRESH], set(), tells_by_path, german_by_path)
        assert [row[0] for row in rows] == [FRESH]


class TestAllowancesAreLeftAlone:
    """A path a baseline already scores belongs to that ratchet, findings and all."""

    def test_a_baselined_tell_allowance_is_not_reopened(self, tmp_path, capsys):
        """GIVEN a file at its recorded tell count WHEN the gate runs THEN it stays quiet."""
        tree = {SOURCE: clean_block(2) + "\n" + tell_block(2)}
        code = run(tree, tmp_path, prose={SOURCE: 2})
        out = capsys.readouterr().out
        assert code == 0
        assert "PASS" in out
        assert SOURCE not in out

    def test_a_baselined_german_allowance_is_not_reopened(self, tmp_path, capsys):
        """GIVEN a file at its recorded German count WHEN the gate runs THEN it stays quiet."""
        tree = {SOURCE: clean_block(2) + "\n" + german_block(3)}
        code = run(tree, tmp_path, german={SOURCE: 3})
        assert code == 0

    def test_a_path_in_either_baseline_is_left_to_its_ratchet(self, tmp_path, capsys):
        """GIVEN a path the German baseline alone holds WHEN it is judged THEN it is skipped."""
        tree = {SOURCE: clean_block(1) + "\n" + german_block(5)}
        code = run(tree, tmp_path, german={SOURCE: 5})
        out = capsys.readouterr().out
        assert code == 0
        assert "stay with it" in out


class TestScopeMirrorsTheRatchets:
    """The gate judges what the two instruments judge, so it cannot invent a new rule."""

    def test_a_protected_product_path_is_never_judged(self, tmp_path, capsys):
        """GIVEN German product text in a fresh locale file WHEN the gate runs THEN silence.

        `app/src/locales/de.json` is German by design, and `is_scannable` is the line the
        language ratchet draws around it. Judging the file here would forbid a product.
        """
        tree = {"app/src/locales/de.json": german_block(9)}
        code = run(tree, tmp_path)
        out = capsys.readouterr().out
        assert code == 0
        assert "locales" not in out

    def test_a_path_outside_the_prose_roots_is_not_judged_for_tells(self, tmp_path, capsys):
        """GIVEN a filler line under docs/ WHEN the gate runs THEN the prose ratchet's silence holds.

        `prose_tells.tracked` puts `PROSE_ROOTS` on the `git ls-files` call, and `docs/` is
        not among them, so a filler line there is a finding no ratchet asked about.
        """
        code = run({"docs/notes.md": tell_block(3)}, tmp_path)
        assert code == 0

    def test_a_path_outside_the_prose_roots_is_still_judged_for_german(self, tmp_path, capsys):
        """GIVEN German under docs/ WHEN the gate runs THEN the language ratchet's scope applies."""
        code = run({"docs/notes.md": clean_block(1) + "\n" + german_block(2)}, tmp_path)
        out = capsys.readouterr().out
        assert code == 1
        assert "docs/notes.md" in out


class TestTheInstrumentsAreTheRatchetsOwn:
    """A number printed here has to be the number the ratchet would print for that path."""

    def test_prose_counts_match_the_corpus_pass(self):
        """GIVEN one tree WHEN both callers score it THEN the per-path tell numbers agree."""
        tree = {SOURCE: clean_block(1) + "\n" + tell_block(2), FRESH: clean_block(3, tag="stage")}
        read_text = lambda rel: tree[rel]
        tells_by_path, _ = check.measure(sorted(tree), read_text)
        assert tells_by_path == check.tells.counts_for(sorted(tree), read_text) == {SOURCE: 2}

    def test_german_counts_match_the_whole_line_instrument(self):
        """GIVEN one tree WHEN both callers score it THEN the per-path German numbers agree."""
        tree = {SOURCE: clean_block(1) + "\n" + german_block(3)}
        read_text = lambda rel: tree[rel]
        _, german_by_path = check.measure(sorted(tree), read_text)
        scored = inventory.counts_for(sorted(tree), read_text)
        assert german_by_path == scored == {SOURCE: inventory.hits_in(tree[SOURCE])} == {SOURCE: 3}

    def test_the_repeated_banner_class_compares_the_same_wordings(self):
        """GIVEN two fresh files sharing a banner WHEN the gate runs THEN it reports the repeat.

        `prose_tells.score` adds the corpus-wide class, so a copy-paste banner is a finding
        for whichever path comes second in sort order. Running the same `score` keeps the
        gate consistent with the ratchet over the class that needs every file.
        """
        banner = "Configuration the wave shares across both tools"
        tree = {
            "scripts/alpha_tool.py": f"# {banner}\n" + clean_block(2),
            "scripts/beta_tool.py": f"# {banner}\n" + clean_block(2),
        }
        read_text = lambda rel: tree[rel]
        tells_by_path, _ = check.measure(sorted(tree), read_text)
        assert tells_by_path == {"scripts/beta_tool.py": 1}


class TestInputsAreCheckedNotAssumed:
    """A missing baseline is an unmeasurable tree, which is exit 2 and never a pass."""

    def test_a_missing_prose_baseline_is_an_error(self, tmp_path, capsys):
        """GIVEN no tell baseline WHEN the gate runs THEN it refuses to judge."""
        list_files, read_text = planted({FRESH: clean_block(1)})
        code = check.main(
            [
                "--root", str(tmp_path),
                "--prose-baseline", str(tmp_path / "absent.json"),
                "--language-baseline", str(german_baseline(tmp_path, {})),
            ],
            list_files=list_files,
            read_text=read_text,
        )
        err = capsys.readouterr().err
        assert code == 2
        assert "ERROR" in err
        assert "absent.json" in err

    def test_a_missing_language_baseline_is_an_error(self, tmp_path, capsys):
        """GIVEN no German baseline WHEN the gate runs THEN it refuses to judge."""
        list_files, read_text = planted({FRESH: clean_block(1)})
        code = check.main(
            [
                "--root", str(tmp_path),
                "--prose-baseline", str(prose_baseline(tmp_path, {})),
                "--language-baseline", str(tmp_path / "absent.json"),
            ],
            list_files=list_files,
            read_text=read_text,
        )
        assert code == 2
        assert "ERROR" in capsys.readouterr().err


class TestDiffMode:
    """The same judgment over the paths of one diff, for a worker checking a short list."""

    def test_only_the_listed_paths_are_judged(self, tmp_path, capsys):
        """GIVEN a tree with one bad file and a list naming a clean one WHEN it runs THEN pass."""
        tree = {FRESH: tell_block(3), SOURCE: clean_block(2)}
        listing = tmp_path / "paths.txt"
        listing.write_text(SOURCE + "\n", encoding="utf-8")
        code = run(tree, tmp_path, "--paths-from", str(listing), paths_injected=False)
        out = capsys.readouterr().out
        assert code == 0
        assert FRESH not in out

    def test_the_listed_bad_path_is_judged(self, tmp_path, capsys):
        """GIVEN the same tree and a list naming the bad path WHEN it runs THEN it fails."""
        tree = {FRESH: tell_block(3), SOURCE: clean_block(2)}
        listing = tmp_path / "paths.txt"
        listing.write_text(FRESH + "\n", encoding="utf-8")
        code = run(tree, tmp_path, "--paths-from", str(listing), paths_injected=False)
        out = capsys.readouterr().out
        assert code == 1
        assert FRESH in out

    def test_the_environment_variable_carries_the_diff_too(self, tmp_path, capsys, monkeypatch):
        """GIVEN `EPHE_STAGED_PATHS` naming the bad path WHEN no flag is passed THEN it fails."""
        monkeypatch.setenv("EPHE_STAGED_PATHS", FRESH)
        code = run({FRESH: german_block(2)}, tmp_path, paths_injected=False)
        assert code == 1
        assert FRESH in capsys.readouterr().out
