"""Every browser spec has exactly one home, and Playwright replaces a project's ignores.

The product cannot import a Playwright config, so the only way to hold these two rules is to read the
file — the same reason `tests/test_playwright_port_hygiene.py` parses it. The rules exist because
Playwright REPLACES a project's `testIgnore` with its own instead of merging the two: a glob added at
the top of the config silently stops applying to the `chromium` project, which is what happened on
2026-11-09 and is recorded in `app/tests/playwright/playwright.config.ts:89-99`. The release runbook
used a collected-test count as the check for exactly this; a count drifts with every new spec and says
nothing about which leg a file landed in, so the count stays in the runbook as a reading and the
invariant lives here.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PW_DIR = REPO / "app" / "tests" / "playwright"
CONFIG = PW_DIR / "playwright.config.ts"

#: The one file the gated `visual` project may own alone. A second file hiding behind the gate would
#: run in no default leg, which is how a spec becomes decoration.
VISUAL_ONLY = {"visual.spec.ts"}


def _code(text: str) -> str:
    return "\n".join(
        line
        for line in text.splitlines()
        if not line.lstrip().startswith(("//", "*", "/*"))
    )


def _ignore_blocks(text: str) -> list[list[str]]:
    return [re.findall(r"'([^']+)'", body) for body in
            re.findall(r"testIgnore:\s*\[([^\]]*)\]", text)]


def _match_blocks(text: str) -> list[list[str]]:
    """Each `testMatch:` as the regex sources it names, literal or array."""
    rows: list[list[str]] = []
    for body in re.findall(r"testMatch:\s*(\[[^\]]*\]|/(?:[^/\\]|\\.)*/)", text):
        rows.append(re.findall(r"/((?:[^/\\]|\\.)*)/", body))
    return rows


def _projects(text: str) -> list[dict[str, object]]:
    tail = text[text.index("projects:"):]
    projects: list[dict[str, object]] = []
    for chunk in re.split(r"name:\s*'", tail)[1:]:
        ignores = _ignore_blocks(chunk)
        matches = [source for block in _match_blocks(chunk) for source in block]
        projects.append(
            {
                "name": chunk.split("'", 1)[0],
                "ignore": ignores[0] if ignores else [],
                "match": matches,
            }
        )
    return projects


def _is_ignored(relative: str, globs: list[str]) -> bool:
    for glob in globs:
        stem = glob.removeprefix("**/")
        if stem.endswith("/**"):
            directory = stem[:-3]
            if relative == directory or relative.startswith(directory + "/"):
                return True
        elif relative == stem or Path(relative).name == stem:
            return True
    return False


CONFIG_TEXT = _code(CONFIG.read_text(encoding="utf-8"))
PROJECTS = _projects(CONFIG_TEXT)
TOP_IGNORE = _ignore_blocks(CONFIG_TEXT[: CONFIG_TEXT.index("projects:")])[0]
SPECS = sorted(
    path.relative_to(PW_DIR).as_posix() for path in PW_DIR.rglob("*.spec.ts") if path.is_file()
)


def _named(name: str) -> dict[str, object]:
    return next(project for project in PROJECTS if project["name"] == name)


def _compiled(project: dict[str, object]) -> list[re.Pattern[str]]:
    return [re.compile(str(source)) for source in project["match"]]


def test_the_config_parses_into_the_pieces_the_rules_need() -> None:
    """The scan has to see the file it claims to read, or the rules below are theatre."""
    names = [project["name"] for project in PROJECTS]
    assert {"chromium", "load-sensitive", "visual"} <= set(names), names
    assert TOP_IGNORE, "no top-level testIgnore parsed"
    assert len(SPECS) >= 30, f"only {len(SPECS)} specs found under {PW_DIR}"
    assert _named("chromium")["ignore"], "chromium carries no ignore list of its own"
    assert _named("load-sensitive")["match"], "load-sensitive carries no testMatch"


def test_every_top_level_ignore_applies_to_the_chromium_project_too() -> None:
    # The four top-level globs name the specs another config owns: playwright.real.config.ts,
    # dogfood.config.ts, latency.config.ts. Replacing rather than merging means each has to appear
    # in the project list as well, or it runs against the static dist server that cannot serve it.
    chromium = _named("chromium")
    missing = sorted(glob for glob in TOP_IGNORE if glob not in chromium["ignore"])
    assert not missing, (
        f"{missing} are ignored at the top of {CONFIG.relative_to(REPO)} but not in the chromium "
        "project, and Playwright replaces the project list instead of merging it"
    )


def _owners(relative: str) -> list[str]:
    """Which of the three projects this spec file lands in. Playwright decides by the same three
    rules this function models: the project ignore list, then the two `testMatch` lists."""
    owners: list[str] = []
    if not _is_ignored(relative, _named("chromium")["ignore"]):
        owners.append("chromium")
    for name in ("load-sensitive", "visual"):
        if any(pattern.search(relative) for pattern in _compiled(_named(name))):
            owners.append(name)
    return owners


def _default_lane_specs() -> list[str]:
    return [relative for relative in SPECS if not _is_ignored(relative, TOP_IGNORE)]


def test_each_spec_is_collected_by_exactly_one_project() -> None:
    strays: list[str] = []
    for relative in _default_lane_specs():
        owners = _owners(relative)
        if len(owners) != 1:
            strays.append(f"{relative} → {owners or 'no project'}")
    assert not strays, (
        f"a browser spec must run in exactly one project: {strays} — collected twice runs the same "
        "budget twice, collected never runs nowhere"
    )


def test_the_gated_visual_project_is_the_only_lane_a_spec_can_hide_in() -> None:
    hidden = sorted(relative for relative in _default_lane_specs() if _owners(relative) == ["visual"])
    assert hidden == sorted(VISUAL_ONLY), (
        f"{hidden} is reachable only through the EPHE_VISUAL project, so no default leg runs it — "
        f"{sorted(VISUAL_ONLY)} is the single file allowed to live there"
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
