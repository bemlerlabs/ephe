"""R3: the tool catalog answers with the gate's own verdict.

The catalog exists so a reader can see, per tool, whether a call runs without a
prompt. That answer already lives in `SAFE_TOOLS`; a route that derived its own
would be a second opinion the guard never gave.
"""

from __future__ import annotations

from core.tools.approval_rules import SAFE_TOOLS
from server.routes.capabilities import capabilities


def test_every_row_carries_the_safe_sets_verdict() -> None:
    catalog = capabilities()["tools"]
    rows = catalog["tools"]
    assert rows, "the catalog lists no tool"
    for row in rows:
        assert row["safe"] is (row["name"] in SAFE_TOOLS), row["name"]


def test_the_catalog_is_complete_and_ordered() -> None:
    catalog = capabilities()["tools"]
    names = [row["name"] for row in catalog["tools"]]
    assert catalog["count"] == len(names)
    assert len(set(names)) == len(names)
    assert names == sorted(names)
    assert catalog["safe_count"] == sum(1 for row in catalog["tools"] if row["safe"])


def test_read_only_tools_are_marked_safe_and_writes_are_not() -> None:
    rows = {row["name"]: row for row in capabilities()["tools"]["tools"]}
    for known_safe in ("read_file", "list_directory", "file_search"):
        assert rows[known_safe]["safe"] is True, known_safe
    for mutating in ("write_file", "delete_file", "edit_file"):
        if mutating in rows:
            assert rows[mutating]["safe"] is False, mutating
