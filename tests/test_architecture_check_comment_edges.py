"""Ephe — the architecture checker scores imports from code, not from prose.

Found on 2026-10-08 during the English sweep: `importsOf` ran its specifier regex
over raw file text, so a comment that spells `from '@/lib/api'.` at the start of a
wrapped line became a dependency edge. Tarjan then reported a three-node cycle
across api.ts, api/index.ts and api/artifacts.ts — a red gate caused by a
sentence. The comment was reworded to unblock the wave; these tests pin the
instrument, so no future comment in any language can do it again.

The fixtures run through the real `scripts/import_scan.mjs` via node, because the
checker itself executes on import and cannot be required as a module.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNER = ROOT / "scripts" / "import_scan.mjs"
CHECKER = ROOT / "scripts" / "architecture_check.mjs"

#: The regex `importsOf` used before comments were stripped — kept here so each
#: fixture proves out loud that it really did contain the phantom edge.
RAW_SPECIFIER = re.compile(r"""(?:from|import)\s*['"]([^'"]+)['"]""")


def _raw_specifiers(text: str) -> list[str]:
    return RAW_SPECIFIER.findall(text)


def _scan(cases: dict[str, dict[str, str]]) -> dict[str, list[str]]:
    """Run `importSpecifiers` over each fixture through the shipped module."""
    script = (
        "import { readFileSync } from 'node:fs';\n"
        "import { importSpecifiers } from %s;\n"
        "const cases = JSON.parse(readFileSync(0, 'utf-8'));\n"
        "const out = {};\n"
        "for (const [name, c] of Object.entries(cases)) out[name] = importSpecifiers(c.text, c.ext);\n"
        "console.log(JSON.stringify(out));\n"
    ) % json.dumps(SCANNER.as_uri())
    done = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=60,
    )
    assert done.returncode == 0, f"node failed: {done.stderr}"
    return json.loads(done.stdout)


def test_the_scanner_module_exists_and_is_importable():
    assert SCANNER.is_file(), "scripts/import_scan.mjs is missing"


class TestCommentCannotCreateAnEdge:
    #: The incident itself: a header comment whose wrap begins with the specifier.
    HEADER = """/**
 * Ephe — API client for the workbench (R4).
 * The facade (lib/api/index.ts) still re-exports everything, so the surfaces
 * keep the
 * from '@/lib/api'.
 */
import { apiUrl, request } from './http'
import type { ArtifactEntry } from './types_extra'
"""

    def test_a_ts_block_comment_naming_a_module_adds_no_edge(self):
        """GIVEN a header comment spelling from '@/lib/api' WHEN scanned THEN only real imports remain."""
        got = _scan({"ts": {"text": self.HEADER, "ext": ".ts"}})["ts"]
        assert got == ["./http", "./types_extra"]
        assert "@/lib/api" not in got
        # the fixture bites: without stripping, the comment line was an edge
        assert "@/lib/api" in _raw_specifiers(self.HEADER)

    def test_a_line_comment_naming_a_module_adds_no_edge(self):
        """GIVEN a commented-out import WHEN scanned THEN it is not a dependency."""
        text = (
            "// import { helper } from './phantom'\n"
            "/* import { blocky } from './alsophtantom' */\n"
            "import { real } from './real'\n"
        )
        got = _scan({"ts": {"text": text, "ext": ".tsx"}})["ts"]
        assert got == ["./real"]
        assert {"./phantom", "./alsophtantom"} <= set(_raw_specifiers(text))

    def test_rust_doc_comments_add_no_edge(self):
        """GIVEN a /// doc line with a specifier WHEN scanned THEN nothing is extracted."""
        text = "/// use crate::thing;\n// import { x } from './phantom'\nimport { y } from './real'\n"
        got = _scan({"rs": {"text": text, "ext": ".rs"}})["rs"]
        assert got == ["./real"]

    def test_python_hash_comment_adds_no_edge(self):
        """GIVEN a Python comment spelling from './somemodule' WHEN scanned THEN no edge."""
        text = "# from './somemodule'\nfrom . import real\nx = 1  # import os\n"
        got = _scan({"py": {"text": text, "ext": ".py"}})["py"]
        assert got == []
        assert "./somemodule" in _raw_specifiers(text)

    def test_shell_yaml_and_toml_comments_add_no_edge(self):
        """GIVEN # comment languages WHEN scanned THEN their prose stays prose."""
        cases = {
            "sh": {"text": "# import { x } from './phantom'\nsource ./real.sh\n", "ext": ".sh"},
            "yaml": {"text": "# from './phantom'\nkey: value\n", "ext": ".yaml"},
            "toml": {"text": "# from './phantom'\n[tool]\n", "ext": ".toml"},
        }
        assert all(v == [] for v in _scan(cases).values())
        assert all(_raw_specifiers(c["text"]) for c in cases.values())


class TestCodeIsNotMistakenForAComment:
    def test_a_url_in_code_does_not_swallow_the_rest_of_the_line(self):
        """GIVEN a URL and an import on one line WHEN scanned THEN the import survives."""
        text = "const docs = 'https://example.com/a'; import { real } from './real'\n"
        got = _scan({"ts": {"text": text, "ext": ".ts"}})["ts"]
        assert got == ["./real"]

    def test_a_block_comment_does_not_eat_the_line_after_it(self):
        """GIVEN a block comment ending mid-line WHEN scanned THEN the next import is read."""
        text = "/* note */\nimport { real } from './real'\n"
        assert _scan({"ts": {"text": text, "ext": ".ts"}})["ts"] == ["./real"]

    def test_a_hash_inside_a_string_is_not_a_comment(self):
        """GIVEN a colour literal WHEN scanned THEN the code after it is still code."""
        text = "colour = '#fff'  # from './phantom'\n"
        assert _scan({"py": {"text": text, "ext": ".py"}})["py"] == []
        # the sharp sits inside a string, so it must not blank the rest of the line
        code = "colour = '#fff'; import { real } from './real'\n"
        assert _scan({"py": {"text": code, "ext": ".py"}})["py"] == ["./real"]
        assert _raw_specifiers(code) == ["./real"], "the fixture must still hold a real import"

    def test_markdown_keeps_its_text(self):
        """GIVEN a prose file WHEN scanned THEN nothing is stripped (it is all prose)."""
        text = "Use `import { x } from './docs-example'` in your own code.\n"
        assert _scan({"md": {"text": text, "ext": ".md"}})["md"] == ["./docs-example"]


class TestCheckerOutputContract:
    def test_the_summary_line_keeps_the_words_everyone_compares_against(self):
        """GIVEN the checker WHEN it finishes THEN the line still reads findings/errors/hints."""
        done = subprocess.run(
            ["node", str(CHECKER)],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=120,
        )
        last = done.stdout.strip().splitlines()[-1]
        assert re.fullmatch(
            r"arch-check: \d+ findings \(\d+ errors, \d+ hints\), baseline=(true|false)", last
        ), last

    def test_a_changed_run_names_the_whole_tree_run_as_the_contract(self):
        """GIVEN `check --changed` WHEN it prints a verdict THEN it points at the whole-tree run.

        Severity is read per rule against the frozen count, and --changed counts only the
        changed files, so the fast run can print "info" where ci-gates.yml prints "error".
        The notice has to name that contract, and the summary stays the last line.
        """
        done = subprocess.run(
            ["node", str(CHECKER), "check", "--changed"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=120,
        )
        assert ".github/workflows/ci-gates.yml" in done.stdout, done.stdout
        assert "the changed files only" in done.stdout, done.stdout
        last = done.stdout.strip().splitlines()[-1]
        assert re.fullmatch(
            r"arch-check: \d+ findings \(\d+ errors, \d+ hints\), baseline=(true|false)", last
        ), last

    def test_the_incident_file_still_carries_no_phantom_edge(self):
        """GIVEN app/src/lib/api/artifacts.ts WHEN scanned THEN its facade sentence is not an edge.

        The file's header comment still names the `'@/lib/api'` entry point, which
        is exactly the sentence that read as a dependency before stripping. Its
        real imports must survive the same pass, or the fix would be a mute switch.
        """
        source = ROOT / "app/src/lib/api/artifacts.ts"
        text = source.read_text(encoding="utf-8")
        assert "'@/lib/api'" in text, "the fixture file no longer carries the sentence this test is about"
        got = _scan({"facade": {"text": text, "ext": ".ts"}})["facade"]
        assert "@/lib/api" not in got
        assert "./http" in got
