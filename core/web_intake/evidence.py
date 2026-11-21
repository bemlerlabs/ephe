"""Evidence from one research run, each source under a stable id.

The id is derived from the URL and the text hash, so the same page read twice
keeps the same id and a changed page gets a new one. A sentence that names an id
can be checked against exactly the text that id stood for.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

SOURCE_ID_PATTERN = r"s_[0-9a-f]{12}"
SOURCE_ID = re.compile(rf"^{SOURCE_ID_PATTERN}$")


def _digest(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", "replace")).hexdigest()


def canonical_url(url: str) -> str:
    """The URL without its fragment, which never changes the document."""
    return (url or "").strip().split("#", 1)[0]


@dataclass(frozen=True)
class EvidenceSource:
    source_id: str
    url: str
    title: str
    fetched_at: str
    content_type: str
    sha256: str
    extract: str

    @property
    def short_sha(self) -> str:
        return self.sha256[:12]


class EvidenceStore:
    """The sources one run collected, keyed by id and by URL."""

    def __init__(self) -> None:
        self._by_id: dict[str, EvidenceSource] = {}
        self._by_url: dict[str, EvidenceSource] = {}

    def add(
        self,
        *,
        url: str,
        title: str,
        fetched_at: str,
        content_type: str,
        extract: str,
    ) -> EvidenceSource:
        url = canonical_url(url)
        text = extract or ""
        sha = _digest(text)
        seed = f"{url}\n{sha}"
        source_id = f"s_{_digest(seed)[:12]}"
        source = EvidenceSource(
            source_id=source_id,
            url=url,
            title=(title or url).strip()[:200],
            fetched_at=fetched_at,
            content_type=content_type,
            sha256=sha,
            extract=text,
        )
        self._by_id[source_id] = source
        self._by_url[url] = source
        return source

    def get(self, source_id: str) -> EvidenceSource | None:
        return self._by_id.get(source_id)

    def sources(self) -> list[EvidenceSource]:
        # One entry per URL: a re-read page replaces its own earlier evidence.
        return list(self._by_url.values())

    def __len__(self) -> int:
        return len(self._by_url)

    def __contains__(self, source_id: object) -> bool:
        return str(source_id) in self._by_id
