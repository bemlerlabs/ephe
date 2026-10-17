# Benchmark manifests

The 150 JSON files in this directory are one cohort: 50 tasks, three repetitions each,
the set `evals/pass3_release_gate.py --runs evals/runs` reads. The gate reports
`release-ok: pass^3 50/50, 0 flaky` for it, which is why this is the cohort the tree
carries — a newer cohort with a flip between repetitions cannot be quoted as a number.

Later trials stay in the lab under `~/.ephe/bench/`, including the cohorts that produced
a flip (T14 on 2026-10-10, K5 and T9 on 2026-10-12) and the runs aborted before a
complete matrix. They are working state, not release evidence.

When a newer cohort is clean, replace these files in one commit: the gate reads a flat
set, so a second cohort beside this one would mix two code addresses into one ratio.
`evals/bench-trend.json` keeps the historical points; their receipts name the run
directories that produced them.
