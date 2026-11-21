"""`HTTPException(detail="a sentence")` is the shape `server/AGENTS.md` names as the defect.

A refusal that arrives as a bare sentence carries no `reason_code`, so the page has nothing to look
up in the reader's bundle: `app/src/lib/api/http.ts` prefers `reason_code` over `detail`, and when
only a sentence is present, one language stands in front of a reader who set the other. The route's
own code is the fix, `Refused(code)` with a `serverError.<code>` leaf in both bundles, and the tree
is not there yet. Measured on 2026-11-17 under `server/`: 181 `detail=` arguments that are a string
literal or an f-string, across 32 files. 101 further `detail=` values are structured or computed,
and this census leaves them alone; `detail={"code": "…"}` is how a coded answer looks.

Migrating 181 sites is product copy, because each one needs a sentence in each bundle. Until that
happens this file holds the measured state instead of pretending the tree is clean. The census is
an equality, not a ceiling: a file above its entry gained a sentence, and a file below one removed a
sentence and owes the entry a matching line in the same patch.

One site is already pinned by behaviour rather than by counting.
`tests/test_settings_refusal_is_one_language.py` drives the settings validator and reads the
messages it raises. This file makes no claim about those sentences.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOT = ROOT / "server"

#: The state of the tree on 2026-11-17, one entry per file that answers with a written sentence.
BASELINE: dict[str, int] = {
    "server/middleware.py": 1,
    "server/openai.py": 5,
    "server/routes/artifacts.py": 19,
    "server/routes/audio.py": 5,
    "server/routes/capabilities.py": 2,
    "server/routes/channels.py": 7,
    "server/routes/chat.py": 2,
    "server/routes/discover.py": 2,
    "server/routes/events.py": 1,
    "server/routes/fs.py": 15,
    "server/routes/git_info.py": 17,
    "server/routes/importer.py": 5,
    "server/routes/learning.py": 2,
    "server/routes/marketplace.py": 5,
    "server/routes/memory.py": 6,
    "server/routes/memory_trash.py": 1,
    "server/routes/model_provider.py": 4,
    "server/routes/models.py": 4,
    "server/routes/plugins.py": 8,
    "server/routes/profile.py": 2,
    "server/routes/project.py": 1,
    "server/routes/proxy.py": 3,
    "server/routes/schedule.py": 3,
    "server/routes/session_mirror.py": 3,
    "server/routes/sessions.py": 13,
    "server/routes/settings.py": 2,
    "server/routes/shell.py": 4,
    "server/routes/skills.py": 17,
    "server/routes/sol.py": 4,
    "server/routes/subagents.py": 1,
    "server/routes/update.py": 8,
    "server/routes/vision.py": 9,
}


def _detail_sites(path: Path) -> list[int]:
    """The lines where an `HTTPException` is raised with a sentence rather than a code."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    found: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", "")
        if name != "HTTPException":
            continue
        for keyword in node.keywords:
            if keyword.arg != "detail":
                continue
            value = keyword.value
            written = isinstance(value, ast.JoinedStr) or (
                isinstance(value, ast.Constant) and isinstance(value.value, str)
            )
            if written:
                found.append(node.lineno)
    return found


def _python_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _census() -> dict[str, list[int]]:
    """Every scanned file, mapped to the lines where it answers with a sentence."""
    return {str(p.relative_to(ROOT)): _detail_sites(p) for p in _python_files(SCAN_ROOT)}


def test_no_route_gains_a_refusal_without_a_code():
    """Each file stands exactly where the census recorded it.

    Above the entry means a new sentence reached a reader who cannot translate it. Below the entry
    means a sentence was migrated and the census has to be told, in the same patch.
    """
    counts = _census()
    grew = {rel: len(lines) for rel, lines in counts.items() if len(lines) > BASELINE.get(rel, 0)}
    if grew:
        where = "; ".join(
            f"{rel}: {len(_detail_sites(ROOT / rel))} sites, census {BASELINE.get(rel, 0)}, lines "
            + ",".join(str(line) for line in _detail_sites(ROOT / rel))
            for rel in sorted(grew)
        )
        raise AssertionError(f"refusal sentences that carry no reason code — {where}")
    shrank = {
        rel: (BASELINE[rel], len(counts.get(rel, [])))
        for rel in BASELINE
        if len(counts.get(rel, [])) < BASELINE[rel]
    }
    assert not shrank, "these files migrated refusals and their entries must follow: " + "; ".join(
        f"{rel} {was}->{now}" for rel, (was, now) in sorted(shrank.items())
    )


def test_the_census_names_only_files_that_still_stand():
    """A renamed or deleted module leaves an entry behind that nothing reads."""
    missing = sorted(rel for rel in BASELINE if not (ROOT / rel).is_file())
    assert not missing, f"census entries for files that are gone: {missing}"


def test_the_scan_reads_a_sentence_and_lets_a_code_pass(tmp_path):
    """The counting itself, pinned on two planted files so the census is not decoration."""
    sentence = tmp_path / "sentence.py"
    sentence.write_text(
        "from fastapi import HTTPException\n"
        "\n"
        "def refuse():\n"
        '    raise HTTPException(status_code=400, detail="a sentence here")\n'
        "\n"
        "def refuse_again():\n"
        '    name = "x"\n'
        '    raise HTTPException(status_code=400, detail=f"no {name} here")\n',
        encoding="utf-8",
    )
    coded = tmp_path / "coded.py"
    coded.write_text(
        "from fastapi import HTTPException\n"
        "\n"
        "def refuse():\n"
        '    raise HTTPException(status_code=400, detail={"code": "bundle_id_invalid"})\n'
        "\n"
        "def refuse_with_a_variable(message):\n"
        "    raise HTTPException(status_code=400, detail=message)\n",
        encoding="utf-8",
    )
    assert _detail_sites(sentence) == [4, 8]
    assert _detail_sites(coded) == []
