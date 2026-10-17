"""The load bar this repository measures against: 2.0 runnable tasks per CPU.

Two callers need the same number and neither may guess it:

* `tests/timing_segment.py` stands a wall-clock assertion down at the bar, because past it
  the reading describes the run queue and not the code.
* `core/agent_limits.py` refuses to admit another agent there, because past it the box is
  already oversubscribed.

A second literal for one threshold is how the two drift apart, so the constant lives here
and both import it. Measured 2026-10-13 on a 10-core box: thirteen parallel agents reached
load 246 (24.6 runnable tasks per CPU), forty vitest processes deep, and one full run was
killed before it finished. The same bar held CI green on 2026-10-11: the Spark peaked at
27.9 on 20 cores (1.4 per CPU) and its serial segment kept measuring there.
"""
from __future__ import annotations

#: runnable tasks per CPU beyond which a wall-clock number describes the queue
LOAD_BAR_PER_CPU = 2.0
