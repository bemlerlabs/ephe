"""The CLI-and-documents check, exercised against a planted CLI and the real one.

`scripts/cli_docs_check.py` reads the live parser out of `<root>/ephe_cli.py` and the documents under
`<root>/docs/**/*.md` and `<root>/README*.md`, so every case here is a directory in `tmp_path`: a
two-command argparse module and a page that names some of it. The repository's own tree is only ever
read, which is where the claim that the shipped CLI is fully documented comes from.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cli_docs_check.py"

PLANT_CLI = '''
import argparse

import planted_dep


def build_parser():
    parser = argparse.ArgumentParser(prog="ephe", description=planted_dep.VALUE)
    sub = parser.add_subparsers(dest="command")
    keep = sub.add_parser("prune", help="bound the store")
    keep.add_argument("--keep-rest", type=int, help="files to keep")
    keep.add_argument("--keep-hidden", type=int, help="a flag no document names")
    keep.set_defaults(func=lambda a: 0)
    shown = sub.add_parser("shown", help="a command the page names")
    shown.add_argument("--plain", action="store_true", help="nothing notable")
    shown.add_argument("--rep", type=int, help="repetition index the harness reads")
    shown.set_defaults(func=lambda a: 0)
    group = sub.add_parser("group", help="a bare group with subcommands")
    gsub = group.add_subparsers(dest="action")
    inner = gsub.add_parser("run", help="the invocable half")
    inner.set_defaults(func=lambda a: 0)
    return parser
'''

PLANT_DOC = """# Reference

## `ephe prune [--keep-rest <n>]`

Bound the store. `ephe shown [--plain]` is the other one.
"""


def load_check_module():
    spec = importlib.util.spec_from_file_location("cli_docs_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def plant(root: Path, doc: str = PLANT_DOC) -> Path:
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "ephe_cli.py").write_text(PLANT_CLI, encoding="utf-8")
    (root / "docs" / "CLI.md").write_text(doc, encoding="utf-8")
    (root / "planted_dep").mkdir(exist_ok=True)
    (root / "planted_dep" / "__init__.py").write_text('VALUE = "the tree under check"\n',
                                                      encoding="utf-8")
    return root


class TestThePlantedTree:
    def test_a_flag_no_document_names_is_a_problem(self, tmp_path):
        module = load_check_module()
        problems, _notes, commands, flags = module.check(plant(tmp_path))
        assert commands == 3, commands
        assert flags == 4, flags  # --plain, --rep, --keep-rest, --keep-hidden
        assert any("--keep-hidden" in line and "ephe prune" in line for line in problems), problems
        assert not any("--keep-rest" in line for line in problems), problems

    def test_a_command_no_document_names_is_a_problem(self, tmp_path):
        module = load_check_module()
        problems, _notes, _commands, _flags = module.check(plant(tmp_path))
        assert any("ephe group run" in line for line in problems), problems

    def test_the_tree_under_check_is_importable_while_it_loads(self, tmp_path):
        """The CLI imports from the tree, not from a package someone happens to have installed.

        Run on a machine with ephe installed, an unprepared load answered from that installation
        and measured the wrong tree; on a runner with nothing installed it raised
        `No module named 'core'` (ci-gates.yml, 2026-11-17).
        """
        module = load_check_module()
        tree = plant(tmp_path)
        try:
            cli = module.load_cli(tree)
            assert cli.build_parser().description == "the tree under check"
        finally:
            sys.modules.pop("planted_dep", None)
        assert str(tree) not in sys.path, "the load left the tree on the import path"
        assert "_ephe_cli_for_docs_check" not in sys.modules, "the load leaked the module globally"

    def test_a_bare_group_is_not_held_to_a_naming(self, tmp_path):
        """`ephe group` only prints help; the requirement sits on the invocable leaf."""
        module = load_check_module()
        problems, _notes, _commands, _flags = module.check(plant(tmp_path))
        assert not any("ephe group " not in line and "ephe group" in line for line in problems), problems

    def test_the_family_idiom_names_every_branch(self, tmp_path):
        module = load_check_module()
        doc = "## `ephe prune [--keep-rest <n>]`, `ephe group run | stop`\n"
        problems, _notes, _commands, _flags = module.check(plant(tmp_path, doc))
        assert not any("ephe group run" in line for line in problems), problems

    def test_prose_about_a_command_is_not_a_naming(self, tmp_path):
        """Only a code span or a fenced block counts, so the sentence has to show what to type."""
        module = load_check_module()
        doc = "The prune verb bounds the store, and shown is the other one.\n"
        problems, _notes, _commands, _flags = module.check(plant(tmp_path, doc))
        assert any("ephe prune is invocable" in line for line in problems), problems
        assert any("ephe shown is invocable" in line for line in problems), problems

    def test_an_allowlist_entry_the_parser_no_longer_needs_is_a_problem(self, tmp_path, monkeypatch):
        module = load_check_module()
        monkeypatch.setattr(module, "INTERNAL_FLAGS", {"--never-existed": "a reason nobody checks"})
        problems, _notes, _commands, _flags = module.check(plant(tmp_path))
        assert any("--never-existed" in line for line in problems), problems

    def test_an_allowlisted_flag_is_a_naming_the_parser_still_has_to_answer_for(self, tmp_path,
                                                                                  monkeypatch):
        module = load_check_module()
        monkeypatch.setattr(module, "INTERNAL_FLAGS", {"--keep-hidden": "internal, says so"})
        problems, _notes, _commands, _flags = module.check(plant(tmp_path))
        assert not any("--keep-hidden" in line for line in problems), problems

    def test_a_path_the_page_invents_is_a_note_and_stays_ungated(self, tmp_path):
        """Printed so a reader sees it, kept out of the exit code so prose in a code span cannot
        turn the check into the red leg nobody reads."""
        module = load_check_module()
        doc = PLANT_DOC + "\n`ephe group invented` is not a command.\n"
        problems, notes, _commands, _flags = module.check(plant(tmp_path, doc))
        assert any("ephe group invented" in line for line in notes), notes
        assert not any("ephe group invented" in line for line in problems), problems


class TestTheRepositoryTree:
    def test_the_shipped_cli_is_documented(self, tmp_path):
        """Run from outside the tree with the root named, so neither the working directory nor
        an installed copy of the package can answer for the tree under check."""
        done = subprocess.run([sys.executable, str(SCRIPT), "--root", str(ROOT)],
                              text=True, capture_output=True, check=False, cwd=tmp_path)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "0 problem(s)" in done.stdout, done.stdout

    def test_the_check_reads_the_real_parser_not_a_copy(self):
        """The counts are the parser's own: if they drift from argparse the gate is measuring nothing."""
        module = load_check_module()
        cli = module.load_cli(ROOT)
        parser = cli.build_parser()
        commands = module.command_parsers(parser)
        flags = module.option_flags(parser)
        assert "prune" in commands and "reap" in commands, sorted(commands)
        assert "--keep-rest" in flags and "--older-than" in flags, sorted(flags)[:5]
        assert all(path and not path.startswith("ephe ") for path in commands), sorted(commands)
