"""Every page under `docs/` is named by the index, or says why it stays out.

`docs/README.md` opens with "The documentation that ships with this repository", and measured on
`main` on 2026-11-16 eight pages were named by nothing in it. Three of them sat together in
`docs/decisions/`, including the ledger every `(owner decision 2026-10-08)` line in the agent files
and the comments points at: the record existed and no path reached it.

A page below `docs/` has to be named by its path, because a bare `README.md` in an index holding two
of them names nothing. Whether a named path still exists is the gate's question and `scripts/
readme_check.py` answers it; this file only asks the one the gate cannot: what is missing from the
list.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
INDEX = DOCS / "README.md"

#: A page earns an entry by stating in its own first lines that it stays out of the index, so the
#: exception is visible here instead of hidden in a document this check cannot read. The set is
#: empty since 2026-11-19, when the last working note that used it left the public tree.
OPTED_OUT: set[str] = set()


def _named(index: str, page: Path) -> bool:
    """Whether the index carries this page in backticks: the path below docs/, the name on it."""
    if page.parent != DOCS:
        return f"`{page.relative_to(DOCS).as_posix()}`" in index
    return f"`{page.name}`" in index


def _pages() -> list[Path]:
    return [
        page
        for page in sorted(DOCS.rglob("*.md"))
        if page != INDEX and page.name not in OPTED_OUT
    ]


def test_the_index_names_every_page_under_docs() -> None:
    index = INDEX.read_text(encoding="utf-8")
    missing = [page.relative_to(DOCS).as_posix() for page in _pages() if not _named(index, page)]
    assert not missing, (
        f"{len(missing)} page(s) under docs/ are named by nothing in docs/README.md: "
        f"{', '.join(missing)}"
    )


def test_the_opt_out_stays_a_named_decision_and_not_a_hole() -> None:
    """The exception is only earned by the page that states it.

    Renaming or rewriting that first line is the moment the entry has to go, and a set nobody can
    justify is how an index quietly stops covering half the tree.
    """
    for name in OPTED_OUT:
        page = DOCS / name
        assert page.is_file(), f"{name} was deleted; drop it from OPTED_OUT"
        head = page.read_text(encoding="utf-8").splitlines()[:6]
        joined = " ".join(head).lower()
        assert "docs/readme.md" in joined and "linked" in joined and "deliberately" in joined, (
            f"{name} no longer says in its first lines that it is deliberately left out of the index"
        )
