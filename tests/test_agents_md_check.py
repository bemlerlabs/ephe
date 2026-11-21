"""`scripts/agents_md_check.py` over planted trees, so every rule of the hub is provable offline.

The instrument reads a tree of markdown files and one Makefile, so the plant is a directory of
small files: no git checkout, no network, no product import. One case runs the gate against
this repository, which is the claim CI makes on every push.

The German sample is assembled from the language instrument's own marker list, the way
`test_language_gate.py` does it: this file is scanned by `scripts/language_gate.py` too, and a
literal German sentence here would be counted as German developer prose in the tree.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GATE_PATH = REPO / "scripts" / "agents_md_check.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("agents_md_check_under_test", GATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module through this map
    spec.loader.exec_module(module)
    return module


gate = _load_gate()

AREA_OK = "# App\n\nApplies on top of the root AGENTS.md.\n\nOne constraint.\n"
MAKEFILE = "verify: test\n\n.PHONY: verify test\n\ntest:\n\t@true\n"
GITIGNORE = "node_modules\nAGENTS.override.md\n"


def hub(area_rows: list[tuple[str, str]], *, invariants: int = 4, intro: str = "") -> str:
    """A minimal valid hub whose table names `area_rows` and whose preamble is `intro`."""
    rows = "\n".join(
        f"| `{path}` | [`{area_file}`]({area_file}) | read it |"
        for path, area_file in area_rows
    )
    heads = "\n".join(f"### Invariant {number}\n\nOne line.\n" for number in range(1, invariants + 1))
    return f"""# Hub

{intro}

## What Ephe Is

Ephe is a local workbench.
A turn stays local.
No account.

## Invariants

{heads}
## Commands

```bash
make test
```

## Structure

- `core/` — text

## Areas

| Path | File | Read it when |
|---|---|---|
{rows}

## Rules that apply everywhere

- One rule.

## Boundaries

- One boundary.

## Further reading

- [`docs/README.md`](docs/README.md)
"""


ROOT_OK = hub([("app/", "app/AGENTS.md")])


def base_tree(**overrides: str) -> dict[str, str]:
    files = {
        "AGENTS.md": ROOT_OK,
        "app/AGENTS.md": AREA_OK,
        "Makefile": MAKEFILE,
        ".gitignore": GITIGNORE,
    }
    files.update(overrides)
    return files


def plant(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def run(root: Path, files: dict[str, str], *flags: str) -> int:
    plant(root, files)
    return gate.main(["--root", str(root), *flags])


class TestTheCheckedInTree:
    def test_the_hub_and_its_areas_pass(self, capsys):
        assert gate.main(["--root", str(REPO)]) == 0
        assert "OK agents-md" in capsys.readouterr().out


class TestCaps:
    def test_a_hub_over_its_ceiling_fails(self, tmp_path, capsys):
        assert run(tmp_path, base_tree(**{"AGENTS.md": ROOT_OK + "x" * 12_000})) == 1
        assert "root-cap" in capsys.readouterr().out

    def test_an_area_file_over_its_ceiling_fails(self, tmp_path, capsys):
        assert run(tmp_path, base_tree(**{"app/AGENTS.md": AREA_OK + "x" * 8_000})) == 1
        assert "area-cap" in capsys.readouterr().out

    def test_the_whole_chain_over_its_ceiling_fails(self, tmp_path, capsys):
        """Each file under its own cap, the set over the budget: the failure names the set."""
        rows = [("app/", "app/AGENTS.md"), ("core/", "core/AGENTS.md"), ("ui/", "ui/AGENTS.md")]
        files = {
            "AGENTS.md": hub(rows, intro="x" * 11_000),
            "app/AGENTS.md": AREA_OK + "\n" + "a" * 7_000,
            "core/AGENTS.md": AREA_OK + "\n" + "b" * 7_000,
            "ui/AGENTS.md": AREA_OK + "\n" + "c" * 7_000,
            "Makefile": MAKEFILE,
            ".gitignore": GITIGNORE,
        }
        assert run(tmp_path, files) == 1
        out = capsys.readouterr().out
        assert "chain-cap" in out
        assert "cap 30000" in out


class TestSections:
    def test_a_missing_section_is_named(self, tmp_path, capsys):
        files = base_tree(**{"AGENTS.md": ROOT_OK.replace("## Boundaries", "## Limits")})
        assert run(tmp_path, files) == 1
        assert "missing section '## Boundaries'" in capsys.readouterr().out

    def test_sections_out_of_order_fail(self, tmp_path, capsys):
        structure = "## Structure\n\n- `core/` — text\n\n"
        reordered = ROOT_OK.replace(structure, "") + structure
        assert run(tmp_path, base_tree(**{"AGENTS.md": reordered})) == 1
        assert "section-order" in capsys.readouterr().out

    def test_the_invariant_count_is_four(self, tmp_path, capsys):
        assert run(tmp_path, base_tree(**{"AGENTS.md": hub([("app/", "app/AGENTS.md")], invariants=3)})) == 1
        assert "3 invariant headings" in capsys.readouterr().out


class TestRouting:
    def test_a_row_naming_a_missing_directory_fails(self, tmp_path, capsys):
        files = base_tree(**{"AGENTS.md": hub([("missing/", "app/AGENTS.md")])})
        assert run(tmp_path, files) == 1
        assert "area-path" in capsys.readouterr().out

    def test_a_row_naming_a_missing_area_file_fails(self, tmp_path, capsys):
        files = base_tree(**{"AGENTS.md": hub([("app/", "app/ABSENT.md")])})
        assert run(tmp_path, files) == 1
        assert "area-file" in capsys.readouterr().out

    def test_an_area_file_without_the_header_line_fails(self, tmp_path, capsys):
        files = base_tree(**{"app/AGENTS.md": "# App\n\nOne constraint.\n"})
        assert run(tmp_path, files) == 1
        assert "area-header" in capsys.readouterr().out


class TestCommands:
    def test_a_make_target_the_makefile_lacks_fails(self, tmp_path, capsys):
        root = ROOT_OK.replace("make test", "make deploy")
        assert run(tmp_path, base_tree(**{"AGENTS.md": root})) == 1
        assert "make deploy" in capsys.readouterr().out

    def test_the_word_make_in_prose_is_not_a_command(self, tmp_path, capsys):
        root = ROOT_OK.replace("- One rule.", "- One rule; we make sure the tree stays small.")
        assert run(tmp_path, base_tree(**{"AGENTS.md": root})) == 0

    def test_a_script_path_that_does_not_exist_fails(self, tmp_path, capsys):
        root = ROOT_OK.replace(
            "- [`docs/README.md`](docs/README.md)",
            "- [`docs/README.md`](docs/README.md)\n- `scripts/absent.py`",
        )
        assert run(tmp_path, base_tree(**{"AGENTS.md": root})) == 1
        assert "scripts/absent.py" in capsys.readouterr().out

    def test_a_script_under_app_resolves(self, tmp_path, capsys):
        """`scripts/bundle_budget.py` is a real command inside `app/`, so the gate looks there."""
        root = ROOT_OK.replace("make test", "make test\ncd app && python scripts/bundle_budget.py dist")
        files = base_tree(**{"AGENTS.md": root, "app/scripts/bundle_budget.py": "print()\n"})
        assert run(tmp_path, files) == 0

    def test_the_override_file_has_to_be_gitignored(self, tmp_path, capsys):
        files = base_tree(**{".gitignore": "node_modules\n"})
        assert run(tmp_path, files) == 1
        assert "AGENTS.override.md" in capsys.readouterr().out


class TestDuplicates:
    def test_a_shared_block_over_the_threshold_is_reported(self, tmp_path, capsys):
        block = "x" * 201
        files = base_tree(**{
            "AGENTS.md": hub([("app/", "app/AGENTS.md")], intro=block),
            "app/AGENTS.md": AREA_OK + "\n" + block + "\n",
        })
        assert run(tmp_path, files) == 1
        assert "duplicate" in capsys.readouterr().out

    def test_a_block_at_the_threshold_is_allowed(self, tmp_path, capsys):
        block = "x" * 200
        files = base_tree(**{
            "AGENTS.md": hub([("app/", "app/AGENTS.md")], intro=block),
            "app/AGENTS.md": AREA_OK + "\n" + block + "\n",
        })
        assert run(tmp_path, files) == 0


class TestLanguage:
    def test_a_german_line_in_an_area_fails(self, tmp_path, capsys):
        german = " ".join(gate.inventory.MARKERS[:4])
        files = base_tree(**{"app/AGENTS.md": AREA_OK + "\n" + german + "\n"})
        assert run(tmp_path, files) == 1
        assert "language" in capsys.readouterr().out

    def test_a_german_line_in_the_hub_fails(self, tmp_path, capsys):
        german = " ".join(gate.inventory.MARKERS[:4])
        files = base_tree(**{"AGENTS.md": ROOT_OK + "\n" + german + "\n"})
        assert run(tmp_path, files) == 1
        assert "language" in capsys.readouterr().out


class TestJson:
    def test_a_clean_tree_reports_ok_and_the_caps(self, tmp_path, capsys):
        assert run(tmp_path, base_tree(), "--json") == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["caps"] == {"root": 12_000, "area": 8_000, "chain": 30_000}
        assert payload["findings"] == []

    def test_a_finding_carries_check_path_and_detail(self, tmp_path, capsys):
        files = base_tree(**{"AGENTS.md": hub([("missing/", "app/AGENTS.md")])})
        assert run(tmp_path, files, "--json") == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is False
        assert {"check", "path", "detail"} == set(payload["findings"][0])

