# Ephe — The Ephemerides
*Tau's flight path as a constellation. Version 1 · Bad Liebenzell, Schwarzwald*

---

## The myth (prose, unchanged)

Tau, the dewdrop, lives for one day. In the evening it evaporates — but its
flight path still stands in the sky for a moment. The **ephemerides** are that
path: a star catalogue of one's own agent, recording *when* Ephe had
encounters — never *what* happened. After thirty nights the oldest path fades
quietly; whatever is meant to remain crystallises into **amber**.

The privacy contract is mechanical, not a policy: **the schema knows only four
fields (`d`, `h`, `k`, `n`) — the data model simply has no room for content.**
No path, no message, no model name can ever get in there, because the structure
does not allow it. Privacy by physics, not by promise.

## Working method: backwards from the press release

*BAD LIEBENZELL — Ephe introduces the ephemerides: the first agent that draws a
personal constellation of its own activity — locally, only for the owner, and it
fades. "Ephe tracks everything — for you, only for you, and it disappears", the
team says. The ephemeris records only paths (day, hour, kind, count) and simply
knows no content in its data model. After 30 nights a path fades quietly,
without a delete dialog; `ephe amber` crystallises a month into amber — sums and
peak hour, without a single content word.*

## The 9 pins (tests/test_ephemeris.py — the specification)

| # | Pin | Contract |
|---|-----|---------|
| 1 | record→load roundtrip | `d/h/k/n`; unknown `kind` → `ValueError` (fail-closed against garbage) |
| 2 | PRIVACY CONTRACT | the store contains **exclusively** `{"d","h","k","n"}` — value equality, never a path/content/model name |
| 3 | load fail-soft | a broken line is skipped, it never raises |
| 4 | chart shape | header + 7 day rows + hour ruler; a sown hour = `█` |
| 5 | empty chart | a dotted sky + „Der Himmel wartet" — never raises | <!-- language-gate: ignore (quoted empty-chart line the chart renders, core/ephemeris.py:134) -->
| 6 | Per-day normalisation | a quiet day still shows `█` at its own maximum |
| 7 | Faded | paths outside the visible range → „N verblasst", not in the picture | <!-- language-gate: ignore (quoted faded foot the chart renders, core/ephemeris.py:151) -->
| 8 | crystallize | monthly sums + peak hour + amber file |
| 9 | CLI | `ephe sky` / `ephe amber` from a tmp store |

## The contract in one sentence

> The ephemeris knows only paths, never content — like a star catalogue that
> records positions, never the light itself.

## Phases

| Phase | Content | Gate |
|---|---|---|
| Sky 1 | `core/ephemeris.py` (record/load/chart/crystallize) | 9/9 pins green |
| Sky 2 | CLI `ephe sky` / `ephe amber` + a start path-point in `cmd_start` | live demo |
| Sky 3 | tool path-points at `execute_tool` (fail-soft, one point per call) | pytest |
| Sky 4 | constellation chart in the PWA (app shell, `◍` motif) | Vitest + screenshot |
| Sky 5 | amber feeds memory (semantic-memory plugin) | pytest |

## Delimitation (deliberately not)

- No dashboard, no cloud sync, no "insights" AI. The sky is a blackboard, not a
  product-feature race.
- No content, ever — not even encrypted. The schema does not permit it; that is
  the whole trick.

*Ephe — Bad Liebenzell, Schwarzwald. ✧ Every day its own constellation.*
