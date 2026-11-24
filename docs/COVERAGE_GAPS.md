# Where the suite is thin, and what tracing it costs

The coverage floor gate (`scripts/coverage_floor.py`, run by `ci-gates.yml`) compares a coverage
report against `scripts/coverage-floor-baseline.json`. This page records what that measurement shows
today, which modules are thin, and one place where the trace cannot reach the code at all.

## How to take the measurement again

```bash
# traced — the leg CI runs, in the order ci-gates.yml runs it
export COVERAGE_PROCESS_START=$PWD/.coverage.rc COVERAGE_FILE=/tmp/cov/.covdata
export PYTHONPATH=$HOOKDIR:$PWD           # $HOOKDIR holds the sitecustomize.py the leg installs
python -m coverage run -p -m pytest tests/ -q -n auto -p no:cacheprovider
python -m coverage combine --rcfile=$PWD/.coverage.rc
python -m coverage json -o .coverage.json --rcfile=$PWD/.coverage.rc
python3 scripts/coverage_floor.py --report .coverage.json
```

The rc file sets `[run] source = core, server, ephe_cli, ephe` and `parallel = True`
(`ci-gates.yml`, step "Produce the coverage report", is the authoritative copy). The tracer is pinned
to `coverage==7.16.2` in the step "Install the package and the tracer"; it is not a declared
dependency of the product, and `rg -n coverage pyproject.toml` returns nothing.

| | |
|---|---|
| Machine | Apple Silicon, macOS 26.6 arm64, 10 CPU |
| Runtime | Python 3.13.18, the repository's own `.venv` |
| Tree | `0405b51`, with only documentation pages and workflow comments differing |
| Engine | none — the suite runs against mock Ollama fixtures (owner decision 2026-10-11) |
| Result | `11542 passed, 177 skipped`, exit 0, traced wall clock 200.32 s |
| Taken | 2026-11-24 01:12:40–01:16:01 +01:00, no other suite on the box |

## The floor, as the gate computes it

`scripts/coverage_floor.py:63-72` groups a file by its first two path components: `core/chat.py`
joins `core`, `core/tools/registry.py` joins `core/tools`, `server/routes/search.py` joins
`server/routes`. Twelve modules are counted; eight carry a floor. Measured against the committed
baseline on 2026-11-24:

| module | floor | measured | statements |
|---|---:|---:|---:|
| `core` | 88 | 89.66 | 30783 |
| `core/channels` | 76 | 77.46 | 852 |
| `core/semindex` | 90 | 91.52 | 554 |
| `core/tools` | 83 | 86.53 | 8212 |
| `ephe.py` | 80 | 80.00 | 25 |
| `ephe_cli.py` | 100 | 100.00 | 2040 |
| `server` | 94 | 95.94 | 1256 |
| `server/routes` | 88 | 89.77 | 7724 |
| **total** | 87 | 88.86 | 55137 |

`core/run`, `core/sandbox`, `core/sol` and `core/web_intake` are counted and unfloored, which is the
state a new package starts in before its first ratchet. The gate's own words:

```
coverage floor: PASS — no module fell below the baseline floor
  total 87% -> 88% over 12 module(s)
  6 module(s) sit above their floor: the baseline can be raised
```

## The module the trace cannot reach

`core/sandbox/worker_launcher.py` reports **0.0 %** — 50 statements, none executed — while the tests
that exercise it pass. The cause is structural: the launcher is not imported, it is handed to
`subprocess.Popen` as a file to run (`core/sandbox/runner.py:32`, `core/sandbox/supervisor.py:366-379`),
and that child gets `env = child_env(home=home)` — an allow-listed copy of the environment
(`core/secret_broker.py:68-90`: `PATH`, `HOME`, `USER`, `LOGNAME`, `SHELL`, `PWD`, `TMPDIR`, `TEMP`,
`TMP`, `LANG`, `LANGUAGE` and `LC_*`). `PYTHONPATH` and `COVERAGE_PROCESS_START` are not in it, so the
`sitecustomize` hook never loads in the worker and no data file can appear for those 50 statements.
No amount of testing raises this module inside the current recipe; the number is a property of how the
child is started.

The invariant behind it has a holder: `tests/test_child_env_carries_no_trace.py` starts `child_env()`
with `PYTHONPATH`, `COVERAGE_PROCESS_START` and `COVERAGE_FILE` set in the parent and asserts the child
receives none of them, including no route to a `.pth` hook, and it fails the moment one of those keys
reaches the allow-list by name or by prefix. So the 0.0 % is a statement about what a plugin or sandbox
child may inherit, recorded here as a measurement and defended there as a rule. Reaching the module
with coverage would mean widening that list, which is a product-code decision about the child
environment; no test asks for it.

## The thinnest modules the trace does reach

Percentages from the same run. A cause is stated only where it was verified in this session.

| file | covered | uncovered / total | cause |
|---|---:|---:|---|
| `core/tools/_deck_pdf.py` | 8.7 % | 126 / 138 | no test in the suite calls `_write_pitch_deck_pdf`, which `core/tools/deck_tools.py:40` exports as a product tool |
| `core/sandbox/bridge_client.py` | 33.5 % | 234 / 352 | not established in this session |
| `core/guarded_fetch.py` | 37.8 % | 23 / 37 | not established in this session |
| `core/_cli_ollama.py` | 48.8 % | 127 / 248 | not established in this session |
| `core/tools/utility_tools.py` | 49.6 % | 58 / 115 | not established in this session |
| `core/memory_embed_onnx.py` | 56.6 % | 36 / 83 | the ONNX model is absent on this machine: the tests skip with "`~/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx` does not hold config.json, model.onnx, …" |
| `core/tools/_deck_pptx.py` | 59.4 % | 43 / 106 | not established in this session |
| `core/secret_store.py` | 68.8 % | 39 / 125 | not established in this session |
| `server/routes/proxy.py` | 69.6 % | 31 / 102 | not established in this session |

Two gaps belong to the machine. The Windows installer path skips with "no PowerShell interpreter on
this host (pwsh/powershell): install.ps1 cannot be parsed or executed here" (`tests/test_installer_cli.py`),
and the live sandbox proofs are owned by a capability probe (`tests/support/capabilities.py:54-55`
requires `sandbox-exec` on macOS, `has_bwrap()` on Linux) so a host without a boundary skips rather
than passing under a different one.

## What two tests still cite from a page that no longer exists

`tests/test_wa10_vision_paths.py:3` cites "Item 9" of the page then named
`COVERAGE_GAPS_2026-10-11.md` — both tests carry the reference with a `docs/` prefix — and says it
left `core/vision.py` at 55 %. `tests/test_wa10_browser_paths.py:3` cites the same item for
`core/browser.py`. Measured in this run: `core/vision.py` **91.2 %** (18 of 204 statements uncovered)
and `core/browser.py` **87.8 %** (56 of 460). The 55 % figure belongs to the list that page was, and
the numbers above supersede it.

## The cost of tracing, measured

Two legs, same tree, same box, two minutes apart, no other suite running:

| leg | command | wall clock |
|---|---|---:|
| traced | `coverage run -p` + `combine` + `json`, then the floor gate | 200.32 s |
| untraced | `pytest tests/ -q -n auto -p no:cacheprovider` | 136.01 s |

Tracing costs 1.47× here. The workflow comment that pointed at this page previously stated "308 s
where the same suite untraced takes 61.7 s, about five times", measured on the owner's idle box on
2026-10-11; that pair belongs to a run this machine cannot re-take, so the comment no longer carries
it and this page carries the pair above instead.

The hosted lane costs something else again, and one data point was checked here against the Actions
API on 2026-11-24: run `45170149051` (push `1f77d1c`, 2026-11-23) started its
`Coverage floor (per-module ratchet)` job at 12:04:01Z and ended it cancelled at 12:24:18Z — 20 min
17 s that produced no verdict. That is the reading recorded in the note above the job's
`timeout-minutes: 45`, which is why a traced leg needs three quarters of an hour there.

## The claim about `pytest-cov` that did not reproduce

The same comment explains the recipe by saying `pytest-cov`'s `--cov` form drops xdist worker data and
"reads a false low". Tested on this machine (pytest-cov 7.1.0 and coverage 7.16.2, both installed
into a scratch directory — neither is a declared dependency of the tree, and the CI leg installs only
`coverage==7.16.2`), two subsets under `-n 4`:

| subset | process-start hook + combine | `pytest-cov --cov` |
|---|---:|---:|
| 4 timing/session files | 19.57 % (10388/53072) | 19.58 % (10389/53072) |
| 4 subprocess-heavy sandbox/CLI files | 20.35 % (11216/55112) | 20.35 % (11215/55112) |

The two forms agreed to within one statement, including for the subset that spawns children, so the
false-low claim did not reproduce here. The recipe is left exactly as CI runs it: this page changes no
gate, and the comment now points at the measurement instead of asserting the mechanism.

## Related pages

[`PERFORMANCE_BASELINE.md`](PERFORMANCE_BASELINE.md) for the start-up and window-memory numbers,
[`LATENCY_BUDGETS.md`](LATENCY_BUDGETS.md) for the wall-clock budgets and the load they were taken at,
[`CI_HYBRID_CAPACITY.md`](CI_HYBRID_CAPACITY.md) for which legs run where, and
[`decisions/ci-capacity-and-runners.md`](decisions/ci-capacity-and-runners.md) for the runner decision.
