# Web intake: search, pages, evidence

Status 2026-11-12: first cut, one kernel tool `web_research` with
`core/web_intake/` behind it. No route, no surface; off until a provider is set.

## Pipeline

`query` → configured search provider → seed URLs → crawl → evidence store →
extractive answer with a source id per sentence → citation check; no model call.

The answer is extractive on purpose: every sentence is a passage copied from the
page it names, so the check compares text with text. A model paraphrase is written
in its own turn and cannot pass this check in this cut.

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
so page content cannot mint a source.

## Verification
`tests/web_intake_fixture.py` is a loopback server on a kernel port; no test opens
a real host. Cases: robots allow/deny/5xx, ETag 304, redirects, a private address
refused before any request, byte cap, content-type whitelist, depth, `max_pages`,
freshness cache, provider 500, empty results, site restriction, unreachable hit,
injected marker. Run: `.venv/bin/python -m pytest tests/test_web_intake.py tests/test_web_intake_crawl.py tests/test_web_research.py -q -p no:cacheprovider`.

## Open for the second cut

- `NETWORK` class: chat and CLI ask before it runs, Architect mode refuses it; an
  auto-run licence is an owner decision.
- No route or UI. A surface needs the evidence list as data, and the five new
  reason codes (`web_search_not_configured`, `web_search_failed`,
  `web_query_empty`, `web_freshness_unknown`, `web_site_outside_reach`) need
  `reader.*` entries in `app/src/locales/{de,en}.json`.
- One provider shape; adapters belong behind `hits_from_payload`. No sitemap, no
  provider pagination, no evidence across turns, and a flat cache entry cap.
- `verify_claims` can check a model-written answer against the same store; the
  tool only checks its own answer today.
