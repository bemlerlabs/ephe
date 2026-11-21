# Context ablation

What a repository's `AGENTS.md` is worth, measured instead of assumed. Every task runs
twice in two copies of the same fixture repository: one copy carries the rule file at the
workspace root, where `core/workspace_rules.py` reads it into the context montage, and the
other copy starts from the same tree with that one file removed. Everything else is
identical, and a real run commits its copy before the turn so `ephe run` can record a
change set from it.

Per arm, three things are recorded:

- **correctness** — the task's own verifier, its exit code. The verifier paths listed under
  `guard` are restored from the fixture immediately before it runs, so an agent that edits
  its own tests scores on the tests we shipped, not on the ones it wrote.
- **duration** — seconds for the turn in a real run, seconds for the verifier in a dry run.
- **tokens** — prompt, context and output, from the run record when the endpoint reports
  usage and from the product's own counter otherwise. The counter that priced an estimated
  side is named in the file (`counter`), because a token estimate is only comparable to
  another one taken with the same tokenizer.

## Starting it

```
# dry run: no engine, no network, no cost — the default
.venv/bin/python evals/context_ablation/harness.py

# real runs: needs the engine the user chose with `ephe configure`
.venv/bin/python evals/context_ablation/harness.py --real --model <tag> --out /tmp/ctx.json

# paired read of two result files
.venv/bin/python evals/context_ablation/harness.py --compare a.json b.json --margin 0.10
```

`--tasks` defaults to `tasks.jsonl`; `--out` and `--workdir` default to a directory under
the system temp dir, and the report ends with the result path. The arm workspaces and, in
a real run, the run records stay beside the result so a verdict can be reopened.

The dry run plays each arm with a stub that applies the fixture solution a row declares
(`stub: {"with_agents": "pass", "no_agents": "fail"}`), and then runs the verifier for
real. It exercises the arms, the verifier, the token accounting and the JSON for free,
which is what CI needs. It measures nothing about a model, and the file says so:
`"evidence": "stub"`. The shipped rows are both `pass`, so a default dry run reports equal
correctness and a context-token delta — the shape of a neutral result. Use `--real` before
quoting anything about a model.

A real run first preflights `ephe run --dry-run`, which resolves the engine and prints the
plan without spending a turn. With no engine from `ephe configure` and no explicit engine
environment, that preflight stops with the actionable hint and the ablation exits before
any arm is prepared. The turns then run through `ephe run --json --run-record`, with
`EPHE_WORKSPACE` pointing at the arm copy, so the workspace rules of that copy are the
ones in play. Like any `ephe run`, a real run keeps its turn in the user's session store
under `~/.ephe`; set `EPHE_CONFIG_DIR` to a copy of your engine config if that matters.

## Reading the numbers

One number per arm is not a result. The unit is a task, so the standard error of a pass
rate over n tasks is `sqrt(R(1-R)/n)`: at n=10 and R=0.9 that is 9.5 pp, wider than any
effect a context file is likely to have. [`evals/noise_floor.py`](../noise_floor.py)
`--power` prints the sample sizes an unpaired before/after comparison needs; this harness
uses the paired design instead, which is strictly better because the same tasks are on
both sides.

```
.venv/bin/python evals/context_ablation/harness.py --compare with.json without.json --arm with_agents
.venv/bin/python evals/context_ablation/harness.py --compare run-a.json run-b.json --margin 0.10
```

`--compare` reports, over the tasks both files share:

- the two pass rates and their mean paired difference, in percentage points;
- the discordant pairs — tasks that pass only in A, and only in B;
- the exact two-sided sign test over those discordant pairs (McNemar), which answers
  "is there a difference at all" and needs no normal approximation;
- a TOST at the chosen margin: two one-sided tests whose maximum p is the equivalence
  p-value, with the 90% interval of the paired difference. Equivalence is claimed only
  when that interval sits inside ±margin, which is the claim a null result can support;
- a verdict that separates three states: a detectable difference, equivalence within the
  margin, or inconclusive because n is too small for that margin. The last one also
  prints the number of pairs an 80%-power test would need for a binary outcome, which is
  about 620 at ±10 pp when the outcome varies at all, and about 30 when every pair agrees.

When every pair agrees, the interval is not a point. The difference between two paired
proportions cannot exceed the share of pairs that disagree, so the 90% window is
`±(1-0.05**(1/n))`: 26 pp at ten tasks, 4.9 pp at sixty. Fewer than about 30 tasks cannot
place a zero-discordance result inside ±10 pp, which is why a two-task stub run is never
called equivalent.

A p-value is not the goal and a large one is not equivalence. The point of the paired
design is to state the smallest effect the run could have detected and then either bound
the effect inside a margin or admit it cannot.

## What the external numbers say

The REALM 2026 ablation from Princeton ([Khatri, “Do Context Files Help Coding Agents?
A Two-Agent Ablation Study on Real Repositories”](https://aclanthology.org/2026.realm-1.5/),
pages 57–67) ran 17 real tasks from 3 repositories across Claude Code and Codex for 288
evaluated runs with gold-test scoring. Context strategy did not measurably move
correctness on either agent, bounded to ≤10–15 pp by equivalence testing; a manipulation
probe could not turn a near-miss into a pass, and borderline task difficulty was
agent-specific (Spearman ρ=0.75). That is the design this harness follows: same tasks on
both sides, a verifier instead of a judge, and an equivalence read instead of a race to
p<0.05.

The ETH study ([Gloaguen et al., arXiv:2602.11988](https://arxiv.org/abs/2602.11988))
reports the cost side that the token field is for: context files did not generally improve
task success while increasing inference cost by over 20% on average. A context file that
costs a fifth more tokens and does not move correctness is a net loss, and only a
measurement that records both axes can say so. The repo's own power arithmetic is in
[`evals/noise_floor.py`](../noise_floor.py); this harness reuses its exact sign test
rather than keeping a second copy of the binomial tail.

## Result format

```json
{
  "schema": 1,
  "mode": "dry-run",
  "evidence": "stub",
  "started_at": "2026-11-11T20:14:51Z",
  "finished_at": "2026-11-11T20:14:52Z",
  "counter": "calibrated-4.2",
  "engine": null,
  "arms": ["with_agents", "no_agents"],
  "tasks": [
    {
      "id": "slugify",
      "prompt": "...",
      "fixture": "/abs/path/evals/context_ablation/fixtures/slugify",
      "verify": ["/abs/python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
      "guard": ["tests"],
      "arms": {
        "with_agents": {
          "context": {"files": ["AGENTS.md"], "chars": 401, "tokens": 96},
          "passed": true,
          "exit_code": 0,
          "timed_out": false,
          "duration_s": 0.241,
          "duration_source": "verifier",
          "tokens": {"prompt": 27, "context": 96, "output": 8, "total": 131,
                     "source": "estimated", "tokenizer": "calibrated-4.2"},
          "record": null,
          "record_solved": null,
          "verify_tail": "",
          "notes": ["stub applied the fixture solution"]
        }
      }
    }
  ],
  "summary": {
    "n_tasks": 2,
    "arms": {"with_agents": {"passed": 2, "rate": 1.0, "duration_s": 0.437,
                             "tokens_total": 244, "tokens_context": 175}},
    "delta": {"rate_pp": 0.0, "passed": 0, "duration_s": 0.0, "tokens_total": 175}
  }
}
```

One task is shown; the `no_agents` arm carries the same fields. `mode` and `evidence`
are the honesty fields: `"real"`/`"engine"` only when a model
answered. `duration_source` names where the seconds came from (`verifier`, `record`, or
`measured`). `record_solved` is the run record's own `outcome.solved`, kept beside our
verifier's verdict; when they disagree the arm carries a note saying so, which is how a
run that edited its tests shows up.

## Adding a task

A task is a row in `tasks.jsonl` plus a fixture directory under `fixtures/`:

```
fixtures/<name>/
  repo/        the starting tree, including its AGENTS.md and its tests
  solution/    overlaid by the stub in a dry run; a real run never sees it
```

The row names the prompt, the verifier as an argv list (`{python}` becomes the running
interpreter), the paths to restore from `repo/` before verifying, and the two stub
outcomes. A fixture repository is a real repository to the agent, so a new task should
start from code that genuinely fails its tests. The tests under `fixtures/` are never
collected by the repository suite (`testpaths = ["tests"]`).
