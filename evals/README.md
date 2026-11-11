# Evals

The offline harnesses and the sets they read. An eval spends an engine turn only when
its command says `--real`; everything else runs on fixtures in this directory.

| file | what it measures | start |
| --- | --- | --- |
| [`creation_eval.py`](creation_eval.py) | the 24-case Creator set, loaded and validated | `python evals/creation_eval.py` |
| [`creation_run.py`](creation_run.py) | the engine half: 24 Creator turns, one server | `python evals/creation_run.py --help` |
| [`creation_runner.py`](creation_runner.py) | grades a run's transcripts and staged bundles | `python evals/creation_runner.py --help` |
| [`live_eval.py`](live_eval.py) | 162 skill cases through `POST /api/chat/stream` | `python evals/live_eval.py --selftest` |
| [`context_ablation/harness.py`](context_ablation/harness.py) | what a repository's `AGENTS.md` changes | [`context_ablation/README.md`](context_ablation/README.md) |
| [`pass3_release_gate.py`](pass3_release_gate.py) | a cohort whose repetitions agree, for release | `python evals/pass3_release_gate.py --runs evals/runs` |
| [`bench_trend.py`](bench_trend.py) | the recorded bench points and their engines | `python evals/bench_trend.py --help` |
| [`noise_floor.py`](noise_floor.py) | the task count a pass^3 delta needs | `python evals/noise_floor.py --power` |

## Breadth and repeatability (4c/4d)

[`breadth_eval.py`](breadth_eval.py) reads a graded creation receipt and reports a rate
per capability class, with the denominator and a Wilson 95% interval for each one. It
also runs the same set three times and reports repeatability.

The register's defect classes 4c (a request that leaves the turn) and 4d (a refusal no
authority can judge) are separate from these two measurement classes. This harness
counts the cases those defects leave unscoreable as unusable; it does not close the
defects.

```
# dry run: no engine, no network, no cost — the default
.venv/bin/python evals/breadth_eval.py

# replay one graded receipt (breadth), or three (repeatability)
.venv/bin/python evals/breadth_eval.py --receipt run-1.json
.venv/bin/python evals/breadth_eval.py --receipt r1.json --receipt r2.json --receipt r3.json \
    --evidence engine

# three paid rounds, 72 Creator turns on the engine the command names
.venv/bin/python evals/breadth_eval.py --real --key-file ~/.ephe/engine.key \
    --base-url https://... --model <tag>
```

A replayed receipt carries the evidence label in the file, or `unverified` when it has
none; pass `--evidence engine` only for receipts from a paid round, because the label is
the claim. The dry run reads [`breadth/stub-runs.json`](breadth/stub-runs.json). Its
outcomes are declared rather than measured, and the report says `evidence: stub`. Two
of its cases flip between runs so the repeatability arithmetic and the flaky list are
exercised without an engine. Those numbers test the harness; a breadth or repeatability
claim needs `--real` and an engine.

A real round runs [`creation_run.py`](creation_run.py) against its own server and grades
the result with [`creation_runner.py`](creation_runner.py) `--json`. The mount checks need
a browser engine, so a missing browser leaves those checks in `not_run`, the affected
cases count as unusable, and the report refuses to quote the rate. A run that cannot be
graded is not a low score.

### What a pass is

A creation case passes when its turn satisfied the case's `expect` block and every
end-state check that ran is green. The checks are the seven offline rows plus the three
mount rows in [`creation/rubric.md`](creation/rubric.md); the rubric names the layer that
answers each one.

A case whose turn was not graded, or whose check did not run, is **unusable**. It leaves
the denominator instead of counting as a failure. The distinction is the point: a
missing browser, a refusal no authority can judge, or a request that left the turn are
instrument defects, and a rate that counts them as fails reports the instrument's
weakness as a missing capability. An unusable case is printed by name, with the reason
the receipt carries.

### Reading the breadth number

Every line is `pass / usable` in one capability class. The aggregate is the same sum over
all classes, and its interval is a Wilson score interval at 95%: a class with four cases
at 4/4 has a lower bound near 0.51, so four green cases do not establish a 100% class.
The per-class interval is the one to quote when the claim is about a class; the aggregate
is only a summary over classes that may carry very different rates.

`headline` and `scored` are printed separately when they differ. `headline` divides
passes by every row, which is what a naive receipt count does. `scored` divides by the
rows the instrument actually measured. The old `10/24` headline is reproduced in
[`breadth/legacy-10-of-24.json`](breadth/legacy-10-of-24.json) as exactly this case: ten
passes over 24 rows, four of which no turn verdict can support (4a `creation-04`, 4c
`creation-15` and `creation-24`, 4d `creation-20`). The report prints both
`10/24 = 0.4167 [0.2447, 0.6117]` and `10/20 = 0.5000 [0.2993, 0.7007]` and marks the set
not quotable. The original receipt is not in the tree, so the fixture reconstructs the
arithmetic from the defect classes the register documents; it is a regression fixture for
the reporting rule rather than a replayed run.

A number is **quotable** only under all of these:

- the evidence is `engine`, meaning the rows came from a paid round rather than the stub;
- every case in the set was scored, so no unusable row moved the denominator;
- the set holds at least 20 scored cases and every class at least three, the floors
  [`creation_eval.py`](creation_eval.py) sets for a rate;
- the receipt's own declared headline agrees with its rows. A disagreement is named in
  the report, because a declared count that no row supports is how the old number
  travelled.

Otherwise the report prints `NOT QUOTABLE` and the reasons. The reasons are the result.

### Reading the repeatability number

The same set runs three times. Each case is classified with the pass^3 rule the release
gate already uses ([`pass3_release_gate.py`](pass3_release_gate.py)):

- **pass** — green in all three runs;
- **fail** — red in all three;
- **flaky** — green in some and red in others, printed by name;
- **incomplete** — at least one run left the case unscored.

`pass^3` counts only the first group, over the whole set. `agreement` is the share of
completely measured cases that reached the same verdict three times. The per-class table
prints the three run rates, the spread in percentage points, and that class's pass^3
count. A class whose rate moves between runs is what repeatability is measured for; one
flaky case does not by itself make a run unquotable, because "this case is flaky" is a
result and the set still measured it. The harness accepts exactly three runs: two cannot
distinguish a consistent verdict from a coincidence.

### Method

The design follows the REALM ablation from Princeton
([Khatri, "Do Context Files Help Coding Agents? A Two-Agent Ablation Study on Real
Repositories"](https://aclanthology.org/2026.realm-1.5/), pages 57–67): a fixed task set,
multiple task classes, repeated runs, and a rate reported with its denominator rather
than a single headline. That study bounded its effects with equivalence tests on the same
tasks; this harness borrows the fixed-set, per-class and repeated-run parts and adds a
Wilson interval on each rate. The sample size needed before an interval is narrow enough
to support a claim is in [`noise_floor.py`](noise_floor.py).

The 24-case set is deliberately split four per class. Four is enough to show that a class
can pass at all, and not enough to place its rate tighter than the interval printed. A
future run with more cases per class will narrow the interval; a second paid run after
the 4a/4c/4d repairs is what the register asks for before any rate leaves the building.

### Result format

```json
{
  "schema": 1,
  "generated_at": "2026-11-11T23:59:00Z",
  "source": "fixture:evals/breadth/stub-runs.json",
  "method": {"interval": "wilson", "level": 0.95,
             "denominator": "scored cases; unusable rows leave the denominator",
             "repeatability": "pass^3 over three runs"},
  "set": {"cases": 24, "classes": 6, "case_floor": 20, "class_floor": 3, "runs": 3},
  "breadth": {
    "evidence": "stub",
    "engine": null,
    "declared": null,
    "headline": {"pass": 21, "total": 24, "rate": 0.875, "ci95": [0.69, 0.9566]},
    "scored": {"pass": 21, "total": 24, "rate": 0.875, "ci95": [0.69, 0.9566]},
    "per_class": {"widget": {"pass": 4, "usable": 4, "unusable": 0,
                            "rate": 1.0, "ci95": [0.5101, 1.0], "rateable": true}},
    "unusable": [],
    "defects": ["the run carries 'stub' evidence; a quotable rate needs 'engine'"],
    "quotable": false
  },
  "repeatability": {
    "runs": [{"run": 1, "evidence": "stub", "scored": {}}],
    "pass^3": {"pass": 20, "total": 24, "rate": 0.8333, "ci95": [0.6415, 0.9332]},
    "flaky": ["creation-15", "creation-23"],
    "incomplete": [],
    "defects": ["the run carries 'stub' evidence; a quotable rate needs 'engine'"],
    "quotable": false
  }
}
```

The example is abbreviated. A breadth per-class entry carries its usable count, its
rate and interval; a repeatability per-class entry carries the three run rates, the
spread and the pass^3 count. Each run carries its own per-class table.
