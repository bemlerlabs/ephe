# Eval status (internal) — creator breadth 4c/4d

State: 2026-11-12. Working note about the creator-eval baseline, deliberately **not**
linked from `docs/README.md`: the quotable numbers are bound to one engine and a paid
re-run is still owed. For the public methodology `evals/README.md` stays the one home,
and every number below obeys its rules (evidence label, denominator, quotability).

## The quotable baseline (the only citable number)

Source: the paid DeepSeek round of 2026-11-12, parallel rounds of 24 creator cases
(`/tmp/rel/eval-ds`): run-2 and run-3 fully graded; run-1's turns were paid but its
grading died on harness defect F1 (raw data kept: `receipt.json`, `staging.json`,
`transcripts.json`).

- Breadth (4c): **12/24 = 50 %**, Wilson 95 % interval [31 %, 69 %]
- Repeatability (4d): pass^3 **9/24 = 37.5 %**, Wilson 95 % interval [21 %, 57 %]
- Evidence label `engine`, engine named. Any number without that label (stub,
  unverified) is not citable — the rule lives in `evals/README.md`.

**Never cite:** `/tmp/rel/eval-runs3/report.txt` (3/24, 1/24). That run is poisoned by
HTTP 402 "Insufficient Balance": 17–19 of 24 cases per run came back `tools=0` with a
"staging folder is empty". It is an infrastructure failure, not a model result; it
stays on disk only as the evidence that the runner lacks a cheque guard.

## Instrument findings (the deepseek-flash run of 2026-11-12) — all fixed, all tested

| # | Finding | Fix |
|---|---|---|
| F1 | grading aborted on `install_refused` (RuntimeError) → the whole round without a receipt, 24 paid turns ungraded | a refusal is a case fail, never an abort (`creation_runner`) |
| F2 | `creation_checks._name_owners` popped the tool **name** where it had to filter the bundle **value** → the run's own installed bundle read as a neighbour, `capability_declared` falsely red (creation-14/19/23) | filter by values; test `test_capability_declared_does_not_call_the_installed_bundle_a_neighbour` |
| F3 | browser checks loaded the mount as a top-level page → `sdk_no_host` for every `ephe.storage` surface | the mount is framed like the app (iframe on the same origin; reload is the frame's own) |
| F4 | the harness sent `tool_budget: 16` against the product default 25 (`core.chat.MAX_TOOL_ITERATIONS`) → self-made budget stops and compaction were graded as model breadth | no `tool_budget` from the harness; the rubric pins the sentence |
| F5 | a 0-byte receipt after a crash read as "not finished" | clear-before-run plus atomic replace (`breadth_eval`) |

Product side: P1 (surface CSP without `style-src` blocked the inline styles every
generated surface writes) and P4 (creation-20/24 demanded `staging_empty` although the
task was buildable with the allowed tools) are fixed too. P2 (several bundles per turn)
gets judged after the next clean run; P3 was model behaviour, not a product defect.

## Why no paid re-run sits here

The DeepSeek key (`/tmp/deepseek.key`) has no balance (HTTP 402). A re-run is a set of
paid engine turns; without balance every repetition is worthless (evidence:
eval-runs3). The harness logic therefore stays **untouched in the tree** — harness,
rubric and cases are SSOT and tested. Once there is balance again:

    .venv/bin/python evals/breadth_eval.py --real --key-file /tmp/deepseek.key \
        --base-url <deepseek-base> --model <tag>

Before it: a fresh tree; leave `EPHE_CONTEXT_WINDOW` unset — the engine probe now takes
the selected model's own reported maximum automatically at switch time. New receipts
under `/tmp/rel/eval-runs4/`, then update this file with the new baseline.

## Why none of this is deleted

- The receipt/evidence engine (Wilson intervals, pass^3, unusable semantics) is the
  only thing forcing quotability; losing it makes every earlier rate uncheckable.
- The 402 round is the proof of the missing cheque guard: "the engine never answered"
  must never count as a model failure — that is a test to write, not a file to toss.
- The findings table above is the audit trail from the paid round to the fixed
  instrument; without it the 50 % claim cannot be re-derived.
