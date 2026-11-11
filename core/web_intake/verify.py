"""Citation checking: a sentence stands only if its source's text carries its anchor.

The anchor is the text in quotation marks when the sentence quotes something, and
the sentence itself otherwise. The second rule is what keeps an extractive answer
honest: a paraphrase that is not in the source cannot pass, so a caller that wants
one has to keep it out of the cited part.

A sentence that names no source is reported as missing evidence, and a sentence
whose anchor is in none of its named sources is reported as rejected. Neither is
silently dropped from the count.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.web_intake.evidence import SOURCE_ID_PATTERN, EvidenceStore

CITATION = re.compile(rf"\[({SOURCE_ID_PATTERN})\]")
QUOTED = re.compile(r"[\"“„]([^\"“”„]{8,})[\"“”]")
_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", (text or "")).strip().casefold()


@dataclass
class Verification:
    checked: int = 0
    verified: int = 0
    issues: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.checked > 0 and not self.rejected and not self.issues


def sentences(text: str) -> list[str]:
    return [part.strip() for part in _SPLIT.split(text or "") if part and part.strip()]


def anchors_of(sentence: str) -> list[str]:
    """Quoted passages when the sentence quotes, otherwise the sentence itself."""
    quoted = [match.group(1).strip() for match in QUOTED.finditer(sentence)]
    if quoted:
        return [anchor for anchor in quoted if anchor]
    body = CITATION.sub("", sentence).strip()
    return [body] if body else []


def verify_claims(claims: list[str], store: EvidenceStore) -> Verification:
    """Check one citation-bearing claim per element, without re-splitting it."""
    report = Verification()
    for sentence in claims:
        cited = CITATION.findall(sentence)
        report.checked += 1
        if not cited:
            report.issues.append(f"no source named: {sentence[:100]}")
            continue
        sources = []
        for source_id in dict.fromkeys(cited):
            source = store.get(source_id)
            if source is None:
                report.issues.append(f"unknown source id {source_id}: {sentence[:100]}")
                continue
            sources.append(source)
        if not sources:
            report.rejected.append(sentence)
            continue
        anchors = anchors_of(sentence)
        haystacks = [normalize(source.extract) for source in sources]
        if not anchors or any(
            normalize(anchor) in haystack
            for anchor in anchors
            for haystack in haystacks
        ):
            report.verified += 1
            continue
        report.rejected.append(sentence)
        report.issues.append(
            f"anchor not in {', '.join(source.source_id for source in sources)}: {sentence[:100]}"
        )
    return report


def verify_answer(text: str, store: EvidenceStore) -> Verification:
    """Check every sentence of a cited answer against the store it names."""
    return verify_claims(sentences(text), store)
