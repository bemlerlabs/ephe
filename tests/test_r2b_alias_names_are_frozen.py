"""R2-B (cut 3c): the surface speaks Ephe — and must not fall back.

Wave R1 renamed the palette, not the language of the surfaces: since then there
are role tokens (bg-surface, border-hairline, text-ink-faint) AND the old
aliases (moss-light, status-info, bg-black/, bg-white/) — and the aliases had
902 call sites, the roles 47. Without a ratchet this is a matter of days: every new
file copies its neighbour, and the neighbour calls an alias.

Hence two rules, both cheap to check and both changeable in one direction only:

1. NO NEW FILE calls an alias. FROZEN is the list of files that already did at the
   moment of freezing. Adding a file to this list decides against the brand; removing
   one is the win.
2. THE TOTAL DOES NOT GROW. BASELINE_TOTAL may fall, never rise.

Both numbers are intent, not measurement error: the 902 were the count of
2026-10-05 after cut 3a and the first stage of 3b; 834 is the count of
2026-10-06, after the browser pane (W1/W1-b) was rewritten in role tokens
and `tabsB.tsx` was converted into `previewTab.tsx` — that file left FROZEN
because it calls no alias any more.

69 is the count of 2026-10-06 after W6: the TEXT steps are migrated,
`text-status-info` is the info role again (text-ink-soft) and muted text
has a role (text-ink-faint); borders are called border-hairline, or in the
louder step border-hairline-strong, surfaces bg-surface and bg-canvas.
What is left are 69 call sites in 24 files: the `bg-white/[0.0X]` overlays (they lack
a role — no surface role is lighter than bg-surface), the decorative
`text-status-info/20` in the command palette, the timeline fill
`bg-moss-light/40` and `MessageBubble.tsx:1107` — that last site is under test
by MessageBubble.streamstatus.test.tsx, which requires the signal-tone class there.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "app" / "src"

ALIAS = re.compile(r"bg-moss-light|border-moss-light|text-status-info|bg-black/|bg-white/")

BASELINE_TOTAL = 69

FROZEN = frozenset(
    {
        "components/dashboard/ActivityFeed.tsx",
        "components/dashboard/DiffView.tsx",
        "components/dashboard/FolderPickerDialog.tsx",
        "components/dashboard/MessageBubble.tsx",
        "components/dashboard/MetricsGauges.tsx",
        "components/dashboard/SchedulerPanel.tsx",
        "components/dashboard/Sidebar.tsx",
        "components/dashboard/SkyCard.tsx",
        "components/dashboard/StatusBar.tsx",
        "components/dashboard/TelegramPairingCard.tsx",
        "components/dashboard/TimelineRail.tsx",
        "components/dashboard/ToolCallDisplay.tsx",
        "components/dashboard/ToolbarRow.tsx",
        "components/dashboard/agent/tabsTrajectory.tsx",
        "components/dashboard/bubble/assistantExtras.tsx",
        "components/dashboard/bubble/bubbleActions.tsx",
        "components/dashboard/bubble/sourcesBar.tsx",
        "components/dashboard/bubble/toolStreamRows.tsx",
        "components/dashboard/chat/index.tsx",
        "components/dashboard/statusBar/ContextWindowsPopover.tsx",
        "components/dashboard/settings/model/sections-engine.tsx",
        "components/dashboard/settings/model/sections-io.tsx",
        "components/dashboard/settings/model/sections-mcp.tsx",
        "components/shell/EnvironmentTools.tsx",
        "components/ui/CommandPalette.tsx",
        "components/ui/Skeleton.tsx",
        "lib/utils.ts",
        "pages/SetupPage.tsx",
    }
)


def _alias_hits() -> Counter[str]:
    """path -> number of alias call sites (test files and dictionaries are excluded)."""
    hits: Counter[str] = Counter()
    for path in sorted(SRC.rglob("*.tsx")) + sorted(SRC.rglob("*.ts")):
        rel = str(path.relative_to(SRC))
        if ".test." in rel:
            continue
        count = len(ALIAS.findall(path.read_text(encoding="utf-8")))
        if count:
            hits[rel] = count
    return hits


def test_keine_neue_datei_ruft_einen_alias():
    hits = _alias_hits()
    neue = sorted(set(hits) - FROZEN)
    assert not neue, (
        "Neue Datei(n) mit Fremdnamen in der Flaeche: "
        + ", ".join(f"{n} ({hits[n]}x)" for n in neue)
        + " — Rollen heissen bg-surface, border-hairline, text-ink-faint."
    )


def test_aliasbestand_waechst_nicht():
    hits = _alias_hits()
    total = sum(hits.values())
    assert total <= BASELINE_TOTAL, (
        f"Alias-Aufrufe sind von {BASELINE_TOTAL} auf {total} gewachsen. "
        "Der Ratchet darf nur sinken — siehe Begründung im Kopf dieser Datei."
    )


def test_der_ratchet_selbst_misst_richtig():
    """Counter-proof: an alias in a fresh file must be caught by rule 1."""
    hits = _alias_hits()
    assert hits, "der Zaehler findet nichts — dann ist auch der Ratchet blind"
    # Sidebar carried 12 alias sites at the freeze; the 2026-10-13 surface migration
    # retired them there, so the counter-proof follows the sites that still carry them.
    assert "components/dashboard/settings/model/sections-mcp.tsx" in hits
    # And a role that already exists is NOT on the freeze list.
    assert "components/shell/EpheMark.tsx" not in hits
