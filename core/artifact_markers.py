"""The artifact-marker table exists once, here.

Every tool in ``core/tools`` and the deck pipeline announces a produced file with a
``*_FILE:`` marker line. Three modules read that set and each used to keep its own
copy: the evidence gate in ``core/tools/registry.py`` stamps ``ARTIFACT_VERIFIED``,
``core/quality.py`` turns the markers into typed artifacts, and
``server/routes/chat.py`` registers the library row. Two copies fell behind, so a
produced file reached neither the library nor the evidence stamp. The set now lives
only here; the callers import it and filter it, never restate it.
``tests/test_artifact_marker_single_source.py`` fails the moment one grows a copy
again.

Row shape: ``(marker, kind, label, activity_word, with_name)``. ``kind`` is the
library kind the workbench stores; ``with_name`` appends the file name to the
activity-rail label. The marker strings sit in string literals on purpose — a label
reaches the UI, so localising it is a locale-file job, not a rename here.

One marker carries more than one thing: ``WAV_FILE:`` comes off three verbs and only
one of them speaks. The ``AUDIO_ROLES`` table below decides what a WAV card says about
itself; the emitter states the role it knows on the line above its marker and
``artifact_label`` turns that into the card text. A WAV that arrives with no role line
reads as the row's own label — a voice, on a machine that has a voice rung.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Three verbs write a WAV. ``synthesize`` speaks a line, ``film_music`` renders a
#: bed and ``film_sound`` renders one named effect.
AUDIO_ROLE_VOICE = "voice"
AUDIO_ROLE_MUSIC_BED = "music_bed"
AUDIO_ROLE_SOUND_EFFECT = "sound_effect"

#: The role a WAV keeps when its emitter stated none. The voice rung is the one this
#: machine always has, so an unlabelled WAV is a spoken line and never a mystery file.
DEFAULT_AUDIO_ROLE = AUDIO_ROLE_VOICE

#: The marker the three verbs above share. Kept as one marker on purpose: a consumer
#: that parses ``WAV_FILE:`` today still finds every WAV there.
AUDIO_MARKER = "WAV_FILE:"

#: The line an emitter writes above the ``WAV_FILE:`` line whose role it states. Not a
#: ``*_FILE:`` marker: it names no file, so the evidence gate, the library and the
#: frontend's marker strip pass it by. Its copy in ``app/src/lib/fileMarkers.ts`` is
#: pinned to this string by ``tests/test_artifact_markers.py``.
AUDIO_ROLE_LINE_PREFIX = "AUDIO_ROLE:"

#: role → (card label, activity-rail word, locale leaf). The leaf names the entry in
#: ``app/src/locales/{en,de}.json`` under ``artifactLabel.`` that carries the card text
#: in the reader's own language, with ``{{name}}`` for the file name; ``label`` is the
#: English sentence a surface that does not translate still reads. German is product
#: surface, so it is not written here.
AUDIO_ROLES: dict[str, tuple[str, str, str]] = {
    AUDIO_ROLE_VOICE: ("🔊 Voice", "Voice", "audioVoice"),
    AUDIO_ROLE_MUSIC_BED: ("🎵 Music bed", "Music bed", "audioMusicBed"),
    AUDIO_ROLE_SOUND_EFFECT: ("🎼 Sound effect", "Sound effect", "audioSoundEffect"),
}


def audio_role(stated: str) -> str:
    """The role a word names, or the default when it names none.

    A reader never invents a fourth kind of audio and never shows a mystery file, so
    an unknown word lands on the role the machine most likely produced.
    """
    word = (stated or "").strip().lower()
    return word if word in AUDIO_ROLES else DEFAULT_AUDIO_ROLE


def _audio_card(role: str) -> tuple[str, str, str]:
    """Label, activity-rail word and locale leaf for one audio role."""
    return AUDIO_ROLES[audio_role(role)]


# Copied verbatim from the emitters (rg "'_FILE:'" across core/). The three trailing
# rows name markers no tool emits in this revision; they stay so a declared kind and
# a silent library cannot drift apart again.
ARTIFACT_MARKERS: tuple[tuple[str, str, str, str, bool], ...] = (
    ("CHART_FILE:", "chart", "📊 Chart created", "Chart", False),
    ("PDF_FILE:", "pdf", "📄 PDF", "PDF", True),
    ("SVG_FILE:", "svg", "🎨 SVG", "SVG", True),
    ("XLSX_FILE:", "xlsx", "📊 Excel", "Excel", True),
    ("DOCX_FILE:", "docx", "📝 Word", "Word", True),
    ("PNG_FILE:", "png", "🖼️ Bild", "Image", True),
    (AUDIO_MARKER, "audio", *_audio_card(DEFAULT_AUDIO_ROLE)[:2], True),
    ("PITCH_DECK_FILE:", "deck", "📊 Deck", "Deck", True),
    ("PPTX_DECK_FILE:", "pptx", "📊 Folien", "Folien", True),
    ("SCREENSHOT_FILE:", "screenshot", "📷 Screenshot", "Screenshot", True),
    ("WRITE_FILE:", "file", "📝 File saved", "File", True),
    ("PREVIEW_FILE:", "html", "🎞️ Deck preview", "Preview", True),
    ("SCORECARD_FILE:", "scorecard", "🧮 Scorecard", "Scorecard", True),
    ("MANIFEST_FILE:", "manifest", "📋 Manifest", "Manifest", True),
    ("RENDER_QA_FILE:", "render_qa", "🔎 Render QA", "Render QA", True),
    ("VISUAL_QA_FILE:", "visual_qa", "👁️ Visual QA", "Visual QA", True),
    ("DECK_SPEC_FILE:", "deck_spec", "📐 Deck spec", "Deck spec", True),
    ("EVIDENCE_LEDGER_FILE:", "evidence_ledger", "📑 Evidence ledger", "Evidence ledger", True),
    ("QA_FILE:", "qa", "✅ Deck QA", "QA", True),
    ("PPTX_QA_FILE:", "pptx_qa", "✅ PPTX QA", "PPTX QA", True),
    ("CONTACT_SHEET_FILE:", "html", "🗂️ Contact sheet", "Contact sheet", True),
    ("PPTX_TEMPLATE_ANALYSIS_FILE:", "pptx_template_analysis", "🧩 Template analysis", "Template analysis", True),
    ("SOURCE_NOTEBOOK_FILE:", "source_notebook", "📓 Source notebook", "Source notebook", True),
    ("SOURCE_BRIEF_FILE:", "source_brief", "📄 Source brief", "Source brief", True),
    ("DECK_STUDIO_FILE:", "deck_studio", "🎛️ Deck Studio", "Deck Studio", True),
    ("DIAGRAM_FILE:", "diagram", "🧭 Diagram", "Diagram", True),
    ("VIDEO_FILE:", "video", "🎬 Video", "Video", True),
    ("SOURCES_FILE:", "sources", "🔖 Sources", "Sources", True),
)

#: The marker column, in table order — what the evidence gate scans for.
ARTIFACT_MARKER_PREFIXES: tuple[str, ...] = tuple(row[0] for row in ARTIFACT_MARKERS)

#: Marker by library kind. A kind repeats only where two markers share one ("html"
#: is preview and contact sheet), so a caller resolving a kind unique here — the
#: twelve ``core/quality.py`` validates — is exact.
MARKER_BY_KIND: dict[str, str] = {kind: marker for marker, kind, *_ in ARTIFACT_MARKERS}


@dataclass(frozen=True)
class ArtifactLabel:
    """What the card and the activity rail say about one produced file."""

    label: str
    label_code: str
    activity_word: str


def stated_audio_role(line: str) -> str | None:
    """The role a role line names, or None when the line names none.

    The reader calls this per line and carries the answer to the ``WAV_FILE:`` line
    below it; a word the table does not name is the default role.
    """
    if not line.startswith(AUDIO_ROLE_LINE_PREFIX):
        return None
    return audio_role(line[len(AUDIO_ROLE_LINE_PREFIX) :])


def artifact_label(marker: str, name: str, *, role: str = "") -> ArtifactLabel:
    """The card text for one marker line, given the role its emitter stated.

    Audio is the only kind with roles; every other marker answers from its own row and
    carries no code, so its label reaches a reader of either language as written here.
    """
    if marker == AUDIO_MARKER:
        label, activity_word, leaf = _audio_card(role)
        return ArtifactLabel(f"{label}: {name}", leaf, activity_word)
    for row_marker, _kind, base_label, activity_word, with_name in ARTIFACT_MARKERS:
        if row_marker == marker:
            card = f"{base_label}: {name}" if with_name else base_label
            return ArtifactLabel(card, "", activity_word)
    raise KeyError(f"no artifact row for marker {marker!r}")
