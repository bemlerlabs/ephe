"""S17: the interactive search budget of one turn."""
from __future__ import annotations

from core.search_budget import DEDUPED, EXHAUSTED, SearchBudget


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def test_four_searches_are_allowed_and_the_fifth_is_refused():
    budget = SearchBudget()
    for index in range(4):
        assert budget.check("web_search", {"query": f"q{index}"}) is None
    assert budget.check("web_search", {"query": "q5"}) == EXHAUSTED
    assert budget.calls == 4


def test_a_repeated_query_is_deduplicated_without_spending_budget():
    budget = SearchBudget()
    assert budget.check("web_search", {"query": "DGX Spark price"}) is None
    assert budget.check("web_search", {"query": "  dgx spark PRICE "}) == DEDUPED
    assert budget.calls == 1


def test_the_window_closes_the_budget_after_sixty_seconds():
    clock = _Clock()
    budget = SearchBudget(clock=clock)
    assert budget.check("web_search", {"query": "a"}) is None
    clock.t += 61.0
    assert budget.check("web_search", {"query": "b"}) == EXHAUSTED


def test_other_tools_never_touch_the_budget():
    budget = SearchBudget()
    assert budget.check("read_file", {"path": "/tmp/x"}) is None
    assert budget.calls == 0
    assert budget.started is None
