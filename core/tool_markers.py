"""core/tool_markers.py — what the reach-layer tools say about themselves.

A refusal line is a machine-readable fact before it is a sentence: the audit
trail reads the marker at the head of the line to decide `decision="blocked"`
(I1-9, `core.quality.result_decision`), while the text behind it is the
explanation a human or a model reads. Producer and detector therefore share one
contract across two files, and that contract broke silently once: the German
wording lived in the tool *and* in the matcher table, so translating either side
alone leaves the audit calling a blockade an ordinary successful run — with every
test still green, because the test read the table, not the tool.

So the wording lives here, once. Producers format from these constants and the
detector unpacks them; a one-sided edit now fails a test instead of shipping.

English on purpose: `⚠️ Security:` and `[TOOL-DENIED]`, the two markers the same
table already matches, carry no other language, and a marker a detector has to
recognise is not product copy — there is nothing to localise in it.

`LEGACY_*` below are the retired wordings. No producer writes them any more; the
matcher still lists them so historical audit rows and stale on-disk records keep
classifying. See the comment at `core.quality.BLOCKED_RESULT_PREFIXES`.
"""
from __future__ import annotations

#: `PlaywrightBrowserManager.go()` — `core.browser_url.url_policy` said no.
BROWSER_DENIED_MARKER = "[browser denied]"

#: `fetch_tools.fetch_url()` — `core.net_guard` refused the target (`FetchRefused`).
FETCH_REFUSED_MARKER = "[fetch refused]"

#: `fetch_tools.fetch_url()` — the fetch itself failed (HTTP status, timeout,
#: unreachable host). A transport failure is not a blockade, so this marker is an
#: error prefix in `core.quality` and deliberately not a refusal marker.
FETCH_FAILED_MARKER = "[fetch failed]"

#: What a refusal starts with today. The detector unpacks this tuple.
CURRENT_REFUSAL_MARKERS: tuple[str, ...] = (
    BROWSER_DENIED_MARKER,
    FETCH_REFUSED_MARKER,
)

#: Retired German wordings, kept for the matcher only.
LEGACY_BROWSER_DENIED_MARKER = "[browser abgelehnt]"
LEGACY_FETCH_REFUSED_MARKER = "[fetch verweigert]"

#: Everything a tool used to pronounce and still must be recognised as blocked.
LEGACY_REFUSAL_MARKERS: tuple[str, ...] = (
    LEGACY_BROWSER_DENIED_MARKER,
    LEGACY_FETCH_REFUSED_MARKER,
)
