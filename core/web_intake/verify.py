"""Citation checking: a sentence stands only if its source's text carries its anchor.

The anchor is the text in quotation marks when the sentence quotes something, and
the sentence itself otherwise. The second rule is what keeps an extractive answer
honest: a paraphrase that is not in the source cannot pass, so a caller that wants
one has to keep it out of the cited part.

A sentence names its source either with a page id (``[s_…]``) or with a workspace
line (``[path/to/file.py:41]``). Both resolve to stored text, so the same check
covers a hybrid answer. A sentence that names no source is reported as missing
evidence, and a sentence whose anchor is in none of its named sources is reported
as rejected. Neither is silently dropped from the count.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.web_intake.evidence import SOURCE_ID_PATTERN, EvidenceStore
from core.web_intake.workspace_scope import WorkspaceHit

CITATION = re.compile(rf"\[({SOURCE_ID_PATTERN})\]")
WORKSPACE_CITATION = re.compile(
    r"\[([A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:py|ts|tsx|js|jsx|md|json|toml|css|html|yml|yaml)):(\d+)\]"
)
QUOTED = re.compile(r"[\"“„]([^\"“”„]{8,})[\"“”]")
_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_WHITESPACE = re.compile(r"\s+")
#: One reference: a page id or a workspace line.
_REF = (
    rf"\[(?:{SOURCE_ID_PATTERN}|"
    r"[A-Za-z0-9_][A-Za-z0-9_./-]*\.(?:py|ts|tsx|js|jsx|md|json|toml|css|html|yml|yaml):\d+)"
    r"\]"
)
#: A citation written after the full stop belongs to the sentence before it. The
#: reader attaches it back before splitting, so a sentence is checked with the
#: source it names instead of leaving the id as the next sentence's opening word.
_ATTACH = re.compile(rf"([.!?])\s*((?:{_REF}\s*)+)")
#: One sentence plus the citations that trail it. A full stop followed by a digit
#: stays inside the sentence, so "3.8" is not read as its end.
_SENTENCE_SPAN = re.compile(rf"(?:[^.!?\n]|[.!?](?![ \t]|$))+\.?(?:\s*{_REF})*")

#: The marker `annotate_unverified` appends. A surface may translate it; the
#: check that produced it is code, not product copy.
UNVERIFIED_MARKER = "[unverified]"


def normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", (text or "")).strip().casefold()


@dataclass
class Verification:
    checked: int = 0
    verified: int = 0
    issues: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.checked > 0 and not self.rejected and not self.issues


def sentences(text: str) -> list[str]:
    return [part.strip() for part in _SPLIT.split(text or "") if part and part.strip()]


def _attach_citations(match: re.Match[str]) -> str:
    return f" {match.group(2).strip()}{match.group(1)} "


def claims(text: str) -> list[str]:
    """Sentences with the citations that follow their full stop kept in place."""
    return sentences(_ATTACH.sub(_attach_citations, text or ""))


def anchors_of(sentence: str) -> list[str]:
    """Quoted passages when the sentence quotes, otherwise the sentence itself."""
    quoted = [match.group(1).strip() for match in QUOTED.finditer(sentence)]
    if quoted:
        return [anchor for anchor in quoted if anchor]
    body = _WHITESPACE.sub(" ", WORKSPACE_CITATION.sub(" ", CITATION.sub(" ", sentence)))
    # A citation attached before the full stop must not leave a space before it:
    # "year [s_x]." is the sentence "year.", or the source text never matches.
    body = re.sub(r"\s+([.!?,;:])", r"\1", body).strip()
    return [body] if body else []


def workspace_refs(sentence: str) -> list[str]:
    return [
        f"{match.group(1)}:{match.group(2)}"
        for match in WORKSPACE_CITATION.finditer(sentence)
    ]


def _source_texts(
    sentence: str,
    store: EvidenceStore,
    workspace: dict[str, WorkspaceHit] | None,
    report: Verification,
) -> list[str]:
    haystacks: list[str] = []
    for source_id in dict.fromkeys(CITATION.findall(sentence)):
        source = store.get(source_id)
        if source is None:
            report.issues.append(f"unknown source id {source_id}: {sentence[:100]}")
            continue
        haystacks.append(source.extract)
    for reference in dict.fromkeys(workspace_refs(sentence)):
        hit = (workspace or {}).get(reference)
        if hit is None:
            report.issues.append(f"unknown workspace source {reference}: {sentence[:100]}")
            continue
        haystacks.append(hit.text)
    return haystacks


def verify_claims(
    items: list[str],
    store: EvidenceStore,
    workspace: dict[str, WorkspaceHit] | None = None,
) -> Verification:
    """Check one citation-bearing claim per element, without re-splitting it."""
    report = Verification()
    for sentence in items:
        if not sentence.strip():
            continue
        report.checked += 1
        if not CITATION.search(sentence) and not workspace_refs(sentence):
            report.issues.append(f"no source named: {sentence[:100]}")
            report.unverified.append(sentence)
            continue
        haystacks = [normalize(text) for text in _source_texts(
            sentence, store, workspace, report
        )]
        if not haystacks:
            report.rejected.append(sentence)
            report.unverified.append(sentence)
            continue
        anchors = anchors_of(sentence)
        if not anchors or any(
            normalize(anchor) in haystack
            for anchor in anchors
            for haystack in haystacks
        ):
            report.verified += 1
            continue
        report.rejected.append(sentence)
        report.unverified.append(sentence)
        report.issues.append(
            f"anchor not in the cited source: {sentence[:100]}"
        )
    return report


def verify_answer(
    text: str,
    store: EvidenceStore,
    workspace: dict[str, WorkspaceHit] | None = None,
) -> Verification:
    """Check every sentence of a cited answer against the store it names."""
    return verify_claims(claims(text), store, workspace)


def annotate_unverified(
    text: str,
    store: EvidenceStore,
    workspace: dict[str, WorkspaceHit] | None = None,
    marker: str = UNVERIFIED_MARKER,
) -> tuple[str, Verification]:
    """Return the text with a marker after every claim that has no stored evidence.

    The layout survives: separators are kept exactly as they arrived, so a
    Markdown answer keeps its paragraphs. Nothing is removed and no turn is
    blocked; a reader sees which sentences the sources do not carry.
    """
    body = text or ""
    report = verify_answer(body, store, workspace)
    if not body.strip():
        return body, report
    marked: list[str] = []
    cursor = 0
    for match in _SENTENCE_SPAN.finditer(body):
        sentence = match.group(0).strip()
        if not sentence:
            continue
        if verify_claims([sentence], store, workspace).verified == 0:
            end = match.end()
            while end > match.start() and body[end - 1].isspace():
                end -= 1
            marked.append(body[cursor:end])
            marked.append(f" {marker}")
            cursor = end
    marked.append(body[cursor:])
    return "".join(marked), report
