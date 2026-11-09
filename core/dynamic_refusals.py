"""The codes the dynamic-tool rail answers with — born once, named everywhere.

A refusal on this rail has three readers at once: the model (the sentence), the audit
line (the `decision` string), and a surface that translates (the `reason_code` a card
or an HTTP envelope carries). All three must spell the refusal identically, or the
audit says one thing and the reader's bundle another. Before this module the same
string was written out at four sites — the transport wiring, the confined runner, the
restart budget, and the HTTP registry that reads them — and a rename had to find all
of them by search.

These are identifiers, not copy: the sentence a reader sees lives in the locale
bundles and, for the HTTP half, in `server.refusals.REASONS`, which imports these
constants as its keys. A code added here without that registration is caught by
`tests/test_server_refusal_codes.py`, whose tables compare the whole set by equality.
"""
from __future__ import annotations

#: Registered under a name, but nothing runs behind it: an MCP remote that is not being
#: served, or a plugin descriptor whose directory the registry cannot resolve yet.
TOOL_NOT_AVAILABLE = "tool_not_available"

#: No OS boundary on this machine, so no confined worker may start (fail-closed).
#: The supervisor's own status word, kept identical so a status and a code cannot drift.
SANDBOX_UNAVAILABLE = "sandbox_unavailable"

#: The worker for one plugin died often enough that its restart budget is spent.
PLUGIN_WORKER_RESTART_EXHAUSTED = "plugin_worker_restart_exhausted"

#: The descriptor's `module:callable` entry leaves the plugin directory, so the run is
#: refused before any process exists.
PLUGIN_ENTRY_REFUSED = "plugin_entry_refused"

#: The bundle's own state folder is at or past the ceiling it lives under, so the run is
#: refused before a worker starts. The next call is refused the same way until the reader
#: prunes the folder; nothing is deleted on their behalf.
PLUGIN_STATE_FULL = "plugin_state_full"

#: Every code this rail may emit. `tests/test_dynamic_refusal_codes.py` walks it and
#: fails if one of them is not registered end to end, because an uncoded refusal is the
#: 500 a reader gets instead of a sentence in their own language.
CODES: tuple[str, ...] = (
    TOOL_NOT_AVAILABLE,
    SANDBOX_UNAVAILABLE,
    PLUGIN_WORKER_RESTART_EXHAUSTED,
    PLUGIN_ENTRY_REFUSED,
    PLUGIN_STATE_FULL,
)

#: The code for a supervisor status that refused the spawn instead of running it. The
#: status word and the code are the same string on purpose: `core.sandbox.supervisor`
#: classifies into a fixed vocabulary, and a second spelling of it would be a drift a
#: reader cannot tell from a bug.
STATUS_CODES = {SANDBOX_UNAVAILABLE: SANDBOX_UNAVAILABLE}

#: How much of a descriptor fingerprint the audit trail carries: the leading characters
#: of the sha256 over the canonical schema bytes (#6's pin). Long enough to compare
#: against a lockfile line, short enough to sit in one log record.
FINGERPRINT_CHARS = 12


def rail_fields(descriptor) -> str:
    """The one audit detail shape for the dynamic rail: identity, never content.

    Plugin id, declared family, transport and the short fingerprint — what a reader
    needs to say which pinned contract ran. A descriptor's schema text, its entry and
    any host directory stay out: the trail is readable by every surface, and a plugin's
    source is not a fact about a call.
    """
    if descriptor is None:
        return ""
    return " ".join(
        (
            f"plugin={descriptor.plugin_id}",
            f"family={descriptor.tool_family}",
            f"transport={descriptor.transport}",
            f"fingerprint={descriptor.fingerprint[:FINGERPRINT_CHARS]}",
        )
    )
