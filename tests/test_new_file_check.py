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


#: The register's German copy, and the locale bundle it joined on 2026-11-24: the two paths
#: the gate names as text a person reads, in the shape the product ships them.
ASSET = "app/src/lib/settingsCopy.de.json"
LOCALE = "app/src/locales/de.json"


def german_json(count: int) -> str:
    """`count` settings rows whose German the instrument scores, one leaf per line."""
    return json.dumps(
        {
            "settings": {
                f"row{i}": f"{MARKERS[i % len(MARKERS)]} {MARKERS[(i + 1) % len(MARKERS)]}"
                for i in range(count)
            }
        },
        ensure_ascii=False,
        indent=1,
    )


def english_json(count: int) -> str:
    """`count` settings rows in the tree's own language, for the twin that needs no naming."""
    return json.dumps(
        {"settings": {f"row{i}": f"stage {i} of the pipeline" for i in range(count)}},
        ensure_ascii=False,
        indent=1,
    )


class TestProductTextIsNamedNotSilenced:
    """A path is exempt because it is named, never because of what it holds."""

    def test_a_named_path_keeps_its_german_and_prints_the_count(self, tmp_path, capsys):
        """GIVEN the named asset with German user text, beside a locale bundle, WHEN the gate runs THEN it passes and prints the count it excused."""
        code = run({ASSET: german_json(12), LOCALE: german_json(9)}, tmp_path)
        out = capsys.readouterr().out
        assert code == 0
        assert f"product text: {ASSET} — 12 German line(s)" in out

    def test_a_path_beside_the_named_one_still_fails(self, tmp_path, capsys):
        """GIVEN German in a file the list does not name, beside one it does WHEN the gate runs THEN only the unnamed path fails."""
        tree = {ASSET: german_json(12), "app/src/lib/settingsCopy.de.copy.json": german_json(4)}
        code = run(tree, tmp_path)
        out = capsys.readouterr().out
        assert code == 1
        assert "app/src/lib/settingsCopy.de.copy.json: 0 tell(s), 4 German line(s)" in out
        assert f"{ASSET}: " not in out

    def test_removing_the_name_from_the_list_turns_the_same_file_red(self, tmp_path, capsys, monkeypatch):
        """GIVEN the asset without its name on the instrument's list WHEN the gate runs THEN its German fails, byte-identical text."""
        # The instrument owns the list and this gate reads it through the instrument, so there is
        # exactly one place a name can be added or withdrawn. A second list here would keep the
        # file passing after the name is gone, which is the failure this case exists to catch.
        assert not hasattr(check, "PRODUCT_TEXT_PATHS")
        monkeypatch.setattr(check.inventory, "PRODUCT_TEXT_PATHS", ("app/src/locales/*.json",))
        code = run({ASSET: german_json(12)}, tmp_path)
        out = capsys.readouterr().out
        assert code == 1
        assert f"{ASSET}: 0 tell(s), 12 German line(s)" in out

    def test_german_in_ordinary_code_earns_nothing_by_looking_like_user_text(self, tmp_path, capsys):
        """GIVEN a Python file full of German sentences a user could imagine reading WHEN the gate runs THEN it fails."""
        code = run({"core/order.py": german_block(6)}, tmp_path)
        out = capsys.readouterr().out
        assert code == 1
        assert "core/order.py: 0 tell(s), 6 German line(s)" in out

    def test_the_english_twin_needs_no_name_and_prints_no_count(self, tmp_path, capsys):
        """GIVEN the English half of the same asset WHEN the gate runs THEN it passes without appearing as product text."""
        code = run({"app/src/lib/settingsCopy.en.json": english_json(12)}, tmp_path)
        out = capsys.readouterr().out
        assert code == 0
        assert "product text:" not in out

    def test_a_named_path_still_carries_its_prose_tells(self):
        """GIVEN the named asset with a tell and German lines WHEN the verdict is built THEN the tell survives the exemption."""
        rows = check.violations([ASSET], set(), {ASSET: 3}, {ASSET: 56})
        assert rows == [(ASSET, 3, 0)]


#: The whole-tree entry has its own cases below because it is the one entry no injected
#: seam reaches: it asks git for the paths and reads their bytes off the disk.


def _git(root: Path, *args: str) -> str:
    """One git call against the fixture repository, output returned."""
    import subprocess

    done = subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-C",
            str(root),
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout


def _git_repo(
    root: Path,
    tracked: dict[str, str],
    *,
    untracked: dict[str, str] | None = None,
    ignored: dict[str, str] | None = None,
) -> Path:
    """A real checkout: committed files, working-tree files, and files git ignores.

    `git ls-files` is the whole gate's input on this path, so the fixture has to be a
    repository rather than a directory of text: which of these files the gate sees is
    the thing under test.
    """
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")

    def write(rel: str, text: str) -> None:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    for rel, text in (ignored or {}).items():
        write(".gitignore", f"{rel}\n")
    for rel, text in tracked.items():
        write(rel, text)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed the fixture")
    for rel, text in (untracked or {}).items():
        write(rel, text)
    return root


def _listed(root: Path) -> list[str]:
    """What the gate's own two git calls return for this checkout."""
    tracked = _git(root, "ls-files").splitlines()
    untracked = _git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(tracked) | set(untracked))


def _walk(root: Path, tmp_path: Path, *flags: str) -> int:
    """The whole-tree entry: no path list, no reader, git and the disk only."""
    return check.main(
        [
            "--root", str(root),
            "--prose-baseline", str(prose_baseline(tmp_path, {})),
            "--language-baseline", str(german_baseline(tmp_path, {})),
            *flags,
        ]
    )


class TestTheWholeTreeWalkAsksGit:
    """The entry a commit hook never calls and a wave never runs: no `--paths-from`."""

    def test_the_walk_judges_every_path_git_lists_and_passes(self, tmp_path, capsys):
        """GIVEN a clean fixture checkout WHEN the whole-tree entry runs THEN its own count is the verdict."""
        repo = _git_repo(
            tmp_path / "checkout",
            {"core/order.py": clean_block(3), "scripts/tool_main.py": clean_block(2)},
            untracked={"scripts/tool_extra.py": clean_block(2)},
            ignored={"build/dropped.py": tell_block(3)},
        )
        code = _walk(repo, tmp_path)
        out = capsys.readouterr().out
        assert code == 0, out
        assert f"{len(_listed(repo))} path(s) neither baseline covers are clean" in out, out
        assert len(_listed(repo)) == 4
        assert "build/dropped.py" not in out

    def test_the_walk_judges_a_file_that_was_never_committed(self, tmp_path, capsys):
        """GIVEN one untracked file carrying tells WHEN the whole-tree entry runs THEN it is named.

        This is the wave-3 shape over real git: the file is absent from
        `git ls-files`, so only the `--others --exclude-standard` call can reach it.
        """
        repo = _git_repo(
            tmp_path / "checkout",
            {"core/order.py": clean_block(2)},
            untracked={"scripts/brand_new.py": clean_block(1) + "\n" + tell_block(3)},
        )
        code = _walk(repo, tmp_path)
        out = capsys.readouterr().out
        assert code == 1, out
        assert "scripts/brand_new.py: 3 tell(s)" in out, out

    def test_both_entries_report_the_same_verdict_for_the_same_paths(self, tmp_path, capsys):
        """GIVEN one checkout WHEN both entries judge it THEN the two verdicts are the same text."""
        repo = _git_repo(
            tmp_path / "checkout",
            {"core/order.py": clean_block(2), "scripts/tool_main.py": clean_block(3)},
            untracked={"scripts/tool_extra.py": clean_block(2)},
        )
        listing = tmp_path / "paths.txt"
        listing.write_text("\n".join(_listed(repo)) + "\n", encoding="utf-8")

        walked = _walk(repo, tmp_path)
        walked_out = capsys.readouterr().out

        listed = check.main(
            [
                "--root", str(repo),
                "--prose-baseline", str(prose_baseline(tmp_path, {})),
                "--language-baseline", str(german_baseline(tmp_path, {})),
                "--paths-from", str(listing),
            ]
        )
        listed_out = capsys.readouterr().out

        assert walked == listed == 0
        assert walked_out == listed_out

    def test_a_directory_that_is_no_checkout_is_an_error_naming_the_call(self, tmp_path, capsys):
        """GIVEN a directory with no repository WHEN the whole-tree entry runs THEN it errors."""
        code = _walk(tmp_path / "not-a-checkout", tmp_path)
        err = capsys.readouterr().err
        assert code == 2
        assert "ERROR" in err
        assert "git failed" in err

    def test_a_walk_without_its_git_call_never_reports_a_clean_tree(self, tmp_path, capsys, monkeypatch):
        """GIVEN the walk's git helper missing from the module WHEN the entry runs THEN nothing passes.

        The accident this case exists for: a wave's edit removed the helper that the
        whole-tree entry calls, every injected-path case stayed green, and the gate
        would have gone silent on a tree carrying findings.
        """
        repo = _git_repo(
            tmp_path / "checkout",
            {"core/order.py": clean_block(2)},
            untracked={"scripts/brand_new.py": clean_block(1) + "\n" + tell_block(3)},
        )
        monkeypatch.delattr(check, "run_git", raising=False)
        try:
            code = _walk(repo, tmp_path)
        except NameError:
            code = 1
        out = capsys.readouterr().out
        assert code != 0
        assert "PASS" not in out
