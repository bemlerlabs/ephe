# Web intake: search, pages, evidence

Status 2026-11-12: the kernel tool `web_research`, the evidence list behind the
chat's source cards, and one explicit run route. Off until a provider is set.

## Pipeline

`query` → configured search provider → seed URLs → crawl → evidence store →
extractive answer with a source id per sentence → citation check; no model call.

The answer is extractive on purpose: every sentence is a passage copied from the
page it names, so the check compares text with text. A model paraphrase is written
in its own turn and cannot pass this check in this cut.

## Route surface

| Route | Answer |
|---|---|
| `GET /api/research/evidence?query=&run_id=&limit=` | `{ok, runs, sources, workspace, total}`; one source row carries `source_id`, `url`, `title`, `fetched_at`, `sha256`, `excerpt`, `query`, `run_id`; one workspace row carries `path`, `line`, `reference`, `text`, `query`, `run_id` |
| `POST /api/research/run` (XHR marker, explicit call) | `{ok, status, reason_code, reason, next, text, run, verification}`; `run` is null on a refusal or a failed provider |

`GET` is read-only over the run ledger and spends no local authority. `POST`
runs the same code path as the tool and is not an auto-run licence: `web_research`
keeps its `NETWORK` approval class and its `network` creator privilege, so a
model call still asks before it leaves the machine. The route exists for a user
who asked for the research, and every hop still goes through `core/net_guard`.

The ledger holds the last 32 runs and 400 sources of this process, newest first;
a restart forgets them. Evidence that should outlive a turn is a later cut.

## Hybrid evidence

`workspace_scope` adds local lines to the same answer. A path prefix keeps files
below it; a bare word keeps lines carrying it, which is how a symbol reaches its
definition site. The scan visits what the index would visit (the same ignore
files and skip directories) plus the text formats a workspace keeps its rules in,
capped at 600 files, 512 KB per file and 2 s. Each local claim cites
`path:line`; each page claim keeps `s_<12 hex>`. `verify.py` resolves both, so one
citation check covers the mixed answer, and the excerpt is the line itself.

## Why this shape

- HybridDeepResearch (arXiv:2609.09410) combines web retrieval with structured
  data and still reports roughly 50–54 % Pass@8 on its hard subset; it names
  constraint preservation between sources as the bottleneck, not finding pages.
  The evidence store keeps a constraint with the text that stated it.
- LiveResearchBench (arXiv:2510.14240) measures user-centred live research; it is
  why `site`, `max_pages`, `depth` and `freshness` are inputs of the call.
- Reference-Hallucination (arXiv:2604.03173) makes a check against the source
  mandatory; `verify.py` requires a quoted passage, or the sentence itself, in a
  cited source.

## Provider

One JSON endpoint, in the environment or `~/.ephe/web-search.json` (owner-only);
the environment wins per field.
| Variable | Meaning |
|---|---|
| `EPHE_SEARCH_API_URL` / `EPHE_SEARCH_API_KEY` | endpoint, and the key sent in a header |
| `EPHE_SEARCH_KEY_HEADER`, `EPHE_SEARCH_KEY_PREFIX` | default `Authorization`, `Bearer ` |
| `EPHE_SEARCH_QUERY_PARAM`, `EPHE_SEARCH_COUNT_PARAM` | default `q`, `count` |
| `EPHE_SEARCH_PROVIDER`, `EPHE_SEARCH_TIMEOUT` | result label, seconds (1–60) |
| `EPHE_SEARCH_CONFIG` | alternative path to the JSON file |

The endpoint answers `{"results": [{"url", "title", "snippet"}]}`; `items`,
`data`, `web`, `hits`, `link`, `href`, `name`, `description` are accepted as
aliases, so another provider is a JSON file. Without URL and key the tool refuses
with `web_search_not_configured` and `Next:`.

## Crawl policy
| Bound | Value |
|---|---|
| pages per call | 8 (default 4), depth 2 (default 1; 1 reads hits only) |
| bytes per page | 1 MB; a larger page becomes a gap |
| extract | 12,000 chars |
| content types | html, xhtml, text/plain, markdown |
| delay | 1 s per host, robots.txt may raise it to 5 s |
| robots.txt | cached one hour; 401/403/5xx keeps the crawler out |

Links are followed only inside the `site` restriction, or the seed's own host.
Reach is `core/net_guard`, as for `fetch_url`: public addresses, every redirect
hop checked, the connection pinned. `EPHE_FETCH_ALLOW_PRIVATE=1` stays the only
path to a private network.

## Cache, evidence, check

Pages are cached as JSON under `~/.ephe/web-cache/pages/`, keyed by URL and
revalidated with `If-None-Match`/`If-Modified-Since`; a `304`, or a page younger
than the `freshness` window, reuses the stored text. The cache is not evidence:
the store lives for one run, `source_id` is `s_<12 hex>` over URL and text hash.

`verify_claims` reports three cases instead of dropping them: a sentence with no
source, an unknown id, and a sentence whose anchor is in none of its sources.
Citation-shaped text inside a page is removed before the real marker is appended,
so page content cannot mint a source. A citation written after the full stop is
attached back to its sentence before splitting, because an id that opens the next
sentence would leave the source unread.

`verify_answer` runs over the model's own answer after a turn that recorded a run.
The `citation_check` frame carries `checked`, `verified` and up to five unverified
sentences; the surface shows them under the answer and the turn is not blocked.
`annotate_unverified` is the same check with an `[unverified]` marker per claim,
available to an API consumer that wants the text, layout unchanged.

## Verification
`tests/web_intake_fixture.py` is a loopback server on a kernel port; no test opens
a real host. Cases: robots allow/deny/5xx, ETag 304, redirects, a private address
refused before any request, byte cap, content-type whitelist, depth, `max_pages`,
freshness cache, provider 500, empty results, site restriction, unreachable hit,
injected marker. Run: `.venv/bin/python -m pytest tests/test_web_intake.py tests/test_web_intake_crawl.py tests/test_web_research.py -q -p no:cacheprovider`.

## Open

- `NETWORK` class: chat and CLI ask before it runs, Architect mode refuses it; an
  auto-run licence is an owner decision.
- One provider shape; adapters belong behind `hits_from_payload`. No sitemap, no
  provider pagination, and a flat cache entry cap.
- The ledger is per process. Evidence that survives a restart, a size budget per
  device and an enable switch for the local half are later cuts.
- The five `web_*` reason codes fall back to the server's English sentence in the
  tool card. `reader.*` entries would need a case each in
  `tests/test_reader_reason_codes.py`, including the `next` parameter, so that
  gate stays the contract for both bundles.
- `guarded_get` is public in `core/net_guard`; the first-hop-only header rule and
  the `url` field of `GuardedResponse` still want a security review.
