from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = [
    ROOT / "README.md",
    ROOT / "app" / "index.html",
    ROOT / "app" / "src" / "locales" / "de.json",
    ROOT / "app" / "src" / "locales" / "en.json",
]

#: The copy work item #94 owns outright.
OWNED_PUBLIC_COPY = [ROOT / "README.md", ROOT / "app" / "index.html"]

#: The tag lines the shipped front-end surface still carried on 2026-10-11, after this
#: item emptied the files it owns. The locale bundles and the composer belong to other
#: lanes, so the sweep could not reach them here — this is the ceiling they start at.
LANE_HELD_TAG_CEILING = {
    "app/src/locales/de.json": 1,
    "app/src/locales/en.json": 1,
    "app/src/components/dashboard/chat/useComposerModelSelection.ts": 1,
}

MODEL_TAG = re.compile(
    r"\b(?:gemma|qwen|llama|mistral|minicpm|phi|deepseek)[a-z0-9._-]*:[a-z0-9._-]+",
    re.IGNORECASE,
)


def _surface_tag_counts() -> dict[str, int]:
    """Every non-test source under app/src that names a model tag.

    Test files and mocks are left out on purpose: a tag in a fixture is a made-up
    string, a tag in the surface is a model the product offers."""
    counts: dict[str, int] = {}
    for path in sorted((ROOT / "app" / "src").rglob("*")):
        if not path.is_file() or path.suffix not in {".ts", ".tsx", ".json", ".html"}:
            continue
        if ".test." in path.name or "__mocks__" in path.parts:
            continue
        rel = str(path.relative_to(ROOT))
        hits = sum(1 for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
                   if MODEL_TAG.search(line))
        if hits:
            counts[rel] = hits
    return counts


def test_given_the_other_lanes_hold_the_rest_when_scanned_then_the_debt_only_shrinks():
    """The residual tag sites outside this item's files, as a ratchet.

    A file may drop its tag (that is the point), no file may add one, and no new file
    may start naming a model. The measured state at the close of #94 is three lines:
    the two locale labels and one composer comment.
    """
    found = _surface_tag_counts()
    for rel, count in found.items():
        assert count <= LANE_HELD_TAG_CEILING.get(rel, 0), f"{rel} names {count} model tags"
    assert sum(found.values()) <= sum(LANE_HELD_TAG_CEILING.values())


def test_given_public_scope_when_scanned_then_absolutist_claims_are_absent():
    """GIVEN the public scope of the Root-PWA
    WHEN its copy is scanned
    THEN absolutist/over-broad claims are absent.
    """
    banned = [
        "Zero Human",
        "Firma",
        "CEO",
        "CTO",
        "Krisen",
        "never sends a single byte",
        "100% offline",
        "100% lokal",
        "weltweit erreichbar",
        "reachable worldwide",
        "Globaler Tunnel",
        "global tunnel",
        "2.5 GB",
        "2.5GB",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in PUBLIC_FILES)
    for term in banned:
        assert term not in text, f"absolutist claim found: {term!r}"


def test_given_owned_public_copy_when_scanned_then_it_names_no_model():
    """GIVEN the public copy this item owns (README, built HTML shell)
    WHEN it is scanned for a model tag
    THEN no tag appears, the local-path memory figure stays, and the false context
    claim stays out.

    The copy used to promise `gemma4:12b` as the model Ephe sizes from RAM; since
    2026-10-11 the tag is the user's and the product names none
    (owner decision 2026-10-11)."""
    text = "\n".join(path.read_text(encoding="utf-8") for path in OWNED_PUBLIC_COPY)
    assert re.findall(r"\b(?:gemma|qwen|llama|mistral|minicpm|phi|deepseek)[a-z0-9._-]*:[a-z0-9._-]+",
                      text, re.IGNORECASE) == []
    assert "16 GB" in text
    # Context claim: the Modelfile default is num_ctx 32768. The false "256K"
    # claim must not creep back into the public copy
    # (repo hygiene audit 2026-09-06: "256K context" was factually wrong).
    assert "256K" not in text


def test_given_root_pwa_when_components_checked_then_provider_badge_and_offline_help_exist():
    """GIVEN the Root-PWA is a React app
    WHEN its UI components are inspected
    THEN model provider state and offline help are first-class UI elements.
    """
    chat_input = (ROOT / "app" / "src" / "components" / "dashboard" / "ChatInput.tsx").read_text(encoding="utf-8")
    # R2 wave: the attachment menu lives in its own composer module (ChatInput.tsx
    # stood over the length wall). The promise is the same — a paperclip handle to
    # attach — only its place moved. The 2026-10-11 composer split moved the model
    # chip and its lastModel seed into useComposerModelSelection.ts; the promise
    # reads the whole composer family now, not one file.
    for extra in ("ComposerAttachMenu.tsx", "ComposerMenu.tsx", "useComposerModelSelection.ts"):
        f = ROOT / "app" / "src" / "components" / "dashboard" / "chat" / extra
        if f.is_file():
            chat_input += "\n" + f.read_text(encoding="utf-8")
    chat_layout = (ROOT / "app" / "src" / "components" / "dashboard" / "chat" / "index.tsx").read_text(encoding="utf-8")
    settings = (ROOT / "app" / "src" / "components" / "dashboard" / "SettingsPanel.tsx").read_text(encoding="utf-8")
    # R-J2: the connection cluster and status pills live in the status bar (image-2 parity).
    # The 2026-10-11 split moved the pill implementations into statusBar/* submodules;
    # the family reads as the surface, the shell file alone would pin a stale shape.
    status_bar = (ROOT / "app" / "src" / "components" / "dashboard" / "StatusBar.tsx").read_text(encoding="utf-8")
    status_dir = ROOT / "app" / "src" / "components" / "dashboard" / "statusBar"
    if status_dir.is_dir():
        status_bar += "\n" + "\n".join(
            p.read_text(encoding="utf-8") for p in sorted(status_dir.glob("*.tsx")) + sorted(status_dir.glob("*.ts"))
        )
    ui = chat_layout + "\n" + status_bar

    # Provider state badge: model name plus the local-engine indicator. The label is
    # product text, so the component picks an i18n key and the locales carry the words —
    # asserting on the component's German label would only prove a comment was there.
    # The composer's chip may only show a model that really was active: it seeds from
    # the last backend state, never from a constant (the retired 'gemma4:e4b' default).
    assert "ephe.lastModel" in chat_input
    assert "chat.offlineCapableLocal" in chat_input
    assert json.loads(
        (ROOT / "app" / "src" / "locales" / "de.json").read_text(encoding="utf-8")
    )["chat"]["offlineCapableLocal"] == "Lokal"
    assert json.loads(
        (ROOT / "app" / "src" / "locales" / "en.json").read_text(encoding="utf-8")
    )["chat"]["offlineCapableLocal"] == "Local"
    # Offline / connection status help
    assert "disconnected" in ui
    assert "WifiOff" in ui
    # Chat area (messages list)
    assert "messages" in chat_layout
    # Attachment actions (voice input was removed in phase 1)
    assert "Paperclip" in chat_input
    # Settings entry point opens provider panel
    assert "setSettingsOpen(true)" in chat_layout
    # Provider panel exposes OpenAI-compatible endpoint
    # (P5 hub refactor: provider selection lives in SetupPage, the settings engine tab
    #  is the model switcher — intent: an OpenAI-compatible endpoint is selectable)
    setup_page = (ROOT / "app" / "src" / "pages" / "SetupPage.tsx").read_text(encoding="utf-8")
    assert "openai_compatible" in setup_page
