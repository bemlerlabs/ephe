"""Confined plugin-worker supervision (task #47) — descriptors in, classified outcomes out.

`worker_spec` carries the descriptor shape, `supervisor` runs one confined child and
classifies it, `restart_budget` bounds respawning a worker that keeps dying, and
`policy_truth` states per platform which ceilings are enforced, bounded, or not
enforced at all. The confined runner of task #9 composes these; nothing here imports
plugin code into this process — the rule from the A1 ruling and the wave-2 contract.

Task #23 added the three halves of the bridge: `bridge` is the envelope grammar,
`bridge_host` decides and answers a worker's request in this process, and
`bridge_client` is the handle the confined child is handed.
"""
from __future__ import annotations

from core.sandbox.policy_truth import policy_snapshot
from core.sandbox.restart_budget import Refusal, RestartBudget
from core.sandbox.supervisor import WorkerOutcome, confined_argv, run_worker
from core.sandbox.worker_spec import STATUSES, WorkerSpec, build_spec

__all__ = [
    "Refusal",
    "RestartBudget",
    "STATUSES",
    "WorkerOutcome",
    "WorkerSpec",
    "build_spec",
    "confined_argv",
    "policy_snapshot",
    "run_worker",
]
