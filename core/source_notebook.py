"""Local NotebookLM-style source notebooks for grounded answers."""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.document_text import (
    MAX_DOC_CHARS,
    OFFICE_EXTENSIONS,
    PDF_EXTENSIONS,
    TEXT_EXTENSIONS,
    extract_text,
)

MAX_SOURCE_CHARS = MAX_DOC_CHARS
MAX_NOTEBOOK_FILES = 80
DEFAULT_CHUNK_CHARS = 1_200
NOTEBOOK_SCHEMA_VERSION = 2

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__",
    "dist", "build", ".next", ".turbo", ".cache", "coverage",
}


@dataclass
class SourceRecord:
    source_id: str
    path: str
    title: str
    kind: str
    chars: int
    digest: str
    status: str = "indexed"
    warning: str = ""
    parser: str = "plain"


@dataclass
class ChunkRecord:
    chunk_id: str
    source_id: str
    path: str
    title: str
    index: int
    text: str
    tokens: list[str]
    ref: str = ""
    vector: list[float] = field(default_factory=list)


def create_source_notebook_index(
    *,
    paths: list[str] | str,
    title: str = "Ephe Source Notebook",
    notebook_id: str = "",
    extensions: list[str] | None = None,
) -> Path:
    """Create a local source-grounded notebook manifest from files/directories."""
    requested = _normalize_paths(paths)
    if not requested:
        raise ValueError("At least one file or directory path is required.")

    files = _collect_files(requested, extensions)
    if not files:
        raise FileNotFoundError("No supported source files found in the requested paths.")

    sources: list[SourceRecord] = []
    chunks: list[ChunkRecord] = []
    total_chars = 0
    for file_path in files[:MAX_NOTEBOOK_FILES]:
        source_id = f"S{len(sources) + 1:03d}"
        text, warning, parser = _read_source_text(file_path)
        if not text.strip():
            sources.append(_source_record(source_id, file_path, "", "skipped", warning or "No extractable text."))
            continue
        if total_chars + len(text) > MAX_SOURCE_CHARS:
            remaining = max(0, MAX_SOURCE_CHARS - total_chars)
            if remaining < 400:
                sources.append(_source_record(source_id, file_path, "", "skipped", "Notebook character budget reached."))
                continue
            text = text[:remaining] + "\n\n[Source truncated by notebook character budget.]"
            warning = "Source truncated by notebook character budget."

        digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]
        record = _source_record(source_id, file_path, text, "indexed", warning, parser=parser)
        record.digest = digest
        sources.append(record)
        for index, chunk_text in enumerate(_chunk_text(text), 1):
            chunk_id = f"{source_id}-C{index:03d}"
            chunks.append(ChunkRecord(
                chunk_id=chunk_id,
                source_id=source_id,
                path=str(file_path),
                title=file_path.name,
                index=index,
                text=chunk_text,
                tokens=_tokens(chunk_text),
                ref=_chunk_ref(source_id, index, chunk_text),
                vector=_text_vector(chunk_text),
            ))
        total_chars += len(text)

    if not chunks:
        raise ValueError("No source chunks could be indexed.")

    notebook_id = _safe_slug(notebook_id or title or "source-notebook")
    out = _notebook_dir() / f"{notebook_id}.json"
    suffix = 2
    while out.exists():
        out = _notebook_dir() / f"{notebook_id}_{suffix}.json"
        suffix += 1

    payload = {
        "schema_version": NOTEBOOK_SCHEMA_VERSION,
        "title": title.strip() or "Ephe Source Notebook",
        "notebook_id": out.stem,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_count": sum(1 for source in sources if source.status == "indexed"),
        "chunk_count": len(chunks),
        "total_chars": total_chars,
        "sources": [asdict(source) for source in sources],
        "chunks": [asdict(chunk) for chunk in chunks],
        "claim_ledger": _build_claim_ledger(chunks),
        "coverage": _source_coverage(sources, chunks),
        "rules": {
            "answer_policy": "Only answer source-specific claims from retrieved chunks; mark unsupported claims as not found in sources.",
            "citation_format": "[S001-C001]",
            "privacy": "Local-only source manifest; no cloud upload.",
        },
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def query_source_notebook_index(
    *,
    notebook_path: str,
    question: str,
    max_chunks: int = 6,
) -> dict[str, Any]:
    """Retrieve evidence chunks and produce a conservative grounded answer draft."""
    notebook = _load_notebook(notebook_path)
    query = (question or "").strip()
    if not query:
        raise ValueError("question is required.")
    chunks = [ChunkRecord(**chunk) for chunk in notebook.get("chunks", [])]
    ranked = _rank_chunks(query, chunks)[: max(1, min(int(max_chunks or 6), 12))]
    if not ranked:
        return {
            "status": "no_evidence",
            "answer": "I found no matching evidence in the indexed sources.",
            "evidence": [],
            "warnings": ["No relevant source chunks matched the question."],
        }

    evidence = []
    for score, chunk in ranked:
        evidence.append({
            "chunk_id": chunk.chunk_id,
            "source_id": chunk.source_id,
            "title": chunk.title,
            "path": chunk.path,
            "score": round(score, 4),
            "quote": _clean_excerpt(chunk.text, 520),
        })

    answer = _compose_grounded_answer(query, evidence)
    source_ids = {item["source_id"] for item in evidence}
    return {
        "status": "grounded",
        "question": query,
        "answer": answer,
        "evidence": evidence,
        "coverage": {
            "matched_chunks": len(evidence),
            "matched_sources": len(source_ids),
            "total_sources": int(notebook.get("source_count", 0)),
        },
        "warnings": [],
    }


def export_source_brief_file(
    *,
    notebook_path: str,
    question: str = "",
    filename: str = "",
) -> Path:
    """Export a Markdown briefing with source manifest and evidence citations."""
    notebook = _load_notebook(notebook_path)
    question = (question or f"Executive source brief for {notebook.get('title', 'notebook')}").strip()
    result = query_source_notebook_index(notebook_path=notebook_path, question=question, max_chunks=10)
    from core.engine_config import artifact_output_dir

    out = artifact_output_dir() / _safe_filename(filename or f"{Path(notebook_path).stem}_source_brief.md", ".md")
    out.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# {notebook.get('title', 'Source Notebook')} - Source Brief",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Notebook: `{Path(notebook_path).name}`",
        "",
        "## Executive Summary",
        result["answer"],
        "",
        "## Evidence Register",
    ]
    # R40c: section budget — the register lists at most 8 evidence entries; the rest is
    # folded into a pointer (full completeness still lives in the notebook JSON).
    evidence = result.get("evidence", [])
    for item in evidence[:8]:
        lines.extend([
            f"- `{item['chunk_id']}` {item['title']} (score {item['score']})",
            f"  - {item['quote']}",
        ])
    rest = len(evidence) - min(len(evidence), 8)
    if rest > 0:
        lines.append(f"- ... {rest} further evidence chunks in the notebook.")
    lines.extend(["", "## Source Manifest"])
    for source in notebook.get("sources", []):
        if source.get("status") == "indexed":
            lines.append(f"- `{source['source_id']}` {source['title']} - {source['path']}")
    warnings = [s.get("warning") for s in notebook.get("sources", []) if s.get("warning")]
    coverage = result.get("coverage") or {}
    lines.extend([
        "",
        "## Source Coverage",
        f"- Matched chunks: {coverage.get('matched_chunks', 0)}",
        f"- Matched sources: {coverage.get('matched_sources', 0)} / {coverage.get('total_sources', notebook.get('source_count', 0))}",
        "",
        "## Claim Ledger",
    ])
    for claim in notebook.get("claim_ledger", [])[:12]:
        lines.append(f"- {claim.get('claim')} {claim.get('citation')}")
    if warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in warnings)
    out.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return out


def format_notebook_created(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    warnings = [source.get("warning") for source in payload.get("sources", []) if source.get("warning")]
    parts = [
        f"SOURCE_NOTEBOOK_FILE:{path}",
        f"Sources indexed: {payload.get('source_count', 0)}",
        f"Chunks indexed: {payload.get('chunk_count', 0)}",
    ]
    if warnings:
        parts.append("Warnings: " + "; ".join(warnings[:5]))
    return "\n".join(parts)


def format_notebook_query(result: dict[str, Any]) -> str:
    lines = [
        f"SOURCE_NOTEBOOK_QUERY_STATUS:{result.get('status', 'unknown')}",
        "",
        str(result.get("answer", "")).strip(),
    ]
    evidence = result.get("evidence") or []
    if evidence:
        lines.extend(["", "Evidence:"])
        for item in evidence:
            lines.append(f"- [{item['chunk_id']}] {item['title']}: {item['quote']}")
    warnings = result.get("warnings") or []
    if warnings:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in warnings)
    return "\n".join(lines).strip()


def _normalize_paths(paths: list[str] | str) -> list[Path]:
    if isinstance(paths, str):
        raw = [part.strip() for part in re.split(r"[\n,]", paths) if part.strip()]
    else:
        raw = [str(part).strip() for part in paths if str(part).strip()]
    resolved = [Path(part).expanduser().resolve() for part in raw]
    for path in resolved:
        if not _is_allowed(path):
            raise PermissionError(f"Path is outside the allowed user directories: {path}")
        if not path.exists():
            raise FileNotFoundError(f"Source path does not exist: {path}")
    return resolved


def _collect_files(paths: list[Path], extensions: list[str] | None) -> list[Path]:
    allowed_exts = {ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in (extensions or [])}
    if not allowed_exts:
        allowed_exts = TEXT_EXTENSIONS | PDF_EXTENSIONS | OFFICE_EXTENSIONS
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix.lower() in allowed_exts:
            files.append(path)
        elif path.is_dir():
            for root, dirs, filenames in os.walk(path):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
                for filename in sorted(filenames):
                    file_path = Path(root) / filename
                    if file_path.suffix.lower() in allowed_exts:
                        files.append(file_path)
                    if len(files) >= MAX_NOTEBOOK_FILES:
                        return files
    return sorted(dict.fromkeys(files))


def _read_source_text(path: Path) -> tuple[str, str, str]:
    """The notebook reads through the one extractor the library shares (`core/document_text.py`)."""
    return extract_text(path)


def _source_record(source_id: str, path: Path, text: str, status: str, warning: str = "", parser: str = "plain") -> SourceRecord:
    digest = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16] if text else ""
    return SourceRecord(
        source_id=source_id,
        path=str(path),
        title=path.name,
        kind=path.suffix.lower().lstrip(".") or "file",
        chars=len(text),
        digest=digest,
        status=status,
        warning=warning,
        parser=parser,
    )


def _chunk_text(text: str, chunk_chars: int = DEFAULT_CHUNK_CHARS) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= chunk_chars:
            current = f"{current}\n\n{paragraph}".strip()
        else:
            if current:
                chunks.append(current)
            if len(paragraph) > chunk_chars:
                for start in range(0, len(paragraph), chunk_chars):
                    chunks.append(paragraph[start:start + chunk_chars].strip())
                current = ""
            else:
                current = paragraph
    if current:
        chunks.append(current)
    return chunks or [text[:chunk_chars]]


def _tokens(text: str) -> list[str]:
    stop = {
        "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
        "der", "die", "das", "und", "ist", "mit", "von", "ein", "eine", "auf",
    }
    return [tok for tok in re.findall(r"[a-zA-Z0-9äöüÄÖÜß_-]{3,}", text.lower()) if tok not in stop]


def _text_vector(text: str, dims: int = 48) -> list[float]:
    vector = [0.0] * dims
    for token in _tokens(text):
        bucket = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16) % dims
        vector[bucket] += 1.0
    norm = sum(value * value for value in vector) ** 0.5
    if not norm:
        return vector
    return [round(value / norm, 6) for value in vector]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def _chunk_ref(source_id: str, index: int, text: str) -> str:
    page = re.search(r"---\s*(Page|Slide)\s+(\d+)", text)
    if page:
        return f"{source_id}:{page.group(1).lower()}:{page.group(2)}"
    return f"{source_id}:chunk:{index}"


def _rank_chunks(question: str, chunks: list[ChunkRecord]) -> list[tuple[float, ChunkRecord]]:
    query_tokens = _tokens(question)
    if not query_tokens:
        return []
    query_set = set(query_tokens)
    query_vector = _text_vector(question)
    ranked: list[tuple[float, ChunkRecord]] = []
    for chunk in chunks:
        chunk_tokens = set(chunk.tokens)
        if not chunk_tokens:
            continue
        overlap = query_set & chunk_tokens
        phrase_bonus = 0.25 if question.lower()[:60] in chunk.text.lower() else 0.0
        title_bonus = 0.15 if any(token in chunk.title.lower() for token in query_set) else 0.0
        lexical = (len(overlap) / max(1, len(query_set))) + (len(overlap) / max(8, len(chunk_tokens)))
        semantic = _cosine(query_vector, chunk.vector)
        score = (lexical * 0.72) + (semantic * 0.28) + phrase_bonus + title_bonus
        if score > 0:
            ranked.append((score, chunk))
    return sorted(ranked, key=lambda item: item[0], reverse=True)


def _source_coverage(sources: list[SourceRecord], chunks: list[ChunkRecord]) -> dict[str, Any]:
    indexed_sources = [source for source in sources if source.status == "indexed"]
    chunked_sources = {chunk.source_id for chunk in chunks}
    return {
        "indexed_sources": len(indexed_sources),
        "chunked_sources": len(chunked_sources),
        "chunks": len(chunks),
        "parsers": sorted({source.parser for source in indexed_sources}),
    }


def _build_claim_ledger(chunks: list[ChunkRecord], limit: int = 24) -> list[dict[str, str]]:
    ledger: list[dict[str, str]] = []
    for chunk in chunks:
        for sentence in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", chunk.text).strip()):
            clean = sentence.strip()
            if 70 <= len(clean) <= 260:
                ledger.append({
                    "claim": clean,
                    "citation": f"[{chunk.chunk_id}]",
                    "source_id": chunk.source_id,
                    "ref": chunk.ref,
                })
                break
        if len(ledger) >= limit:
            break
    return ledger


def _compose_grounded_answer(question: str, evidence: list[dict[str, Any]]) -> str:
    top = evidence[:4]
    citations = ", ".join(f"[{item['chunk_id']}]" for item in top)
    lines = [
        f"Based on the indexed sources, the strongest evidence for '{question}' is in {citations}.",
        "Key grounded points:",
    ]
    for item in top:
        sentence = _first_sentence(item["quote"])
        lines.append(f"- {sentence} [{item['chunk_id']}]")
    lines.append("Unsupported claims should be treated as unknown until additional sources are indexed.")
    return "\n".join(lines)


def _first_sentence(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    match = re.search(r"(.{80,260}?[.!?])\s", compact + " ")
    return (match.group(1) if match else compact[:220]).strip()


def _clean_excerpt(text: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) > max_chars:
        return compact[: max_chars - 1].rstrip() + "…"
    return compact


def _load_notebook(notebook_path: str) -> dict[str, Any]:
    path = Path(notebook_path).expanduser().resolve()
    if not _is_allowed(path):
        raise PermissionError(f"Notebook path is outside the allowed user directories: {path}")
    if not path.exists():
        raise FileNotFoundError(f"Notebook not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if int(payload.get("schema_version", 0)) > NOTEBOOK_SCHEMA_VERSION:
        raise ValueError("Unsupported notebook schema version.")
    return payload


def _notebook_dir() -> Path:
    path = Path.home() / "Documents" / "Ephe" / "notebooks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip().lower())
    return slug.strip("._-")[:80] or "source_notebook"


def _safe_filename(value: str, suffix: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]+", "_", Path(value).name.strip())
    name = name.strip("._-") or "source_brief"
    if not name.lower().endswith(suffix):
        name += suffix
    return name


def _allowed_roots() -> list[Path]:
    home = Path.home()
    return [
        home / "Desktop",
        home / "Documents",
        home / "Dokumente",
        home / "Downloads",
        home / "Developer",
        home / "Code",
        home / "Projects",
        home / "Projekte",
        home / "tmp",
        Path("/tmp"),
        Path(os.environ.get("TMPDIR", "/tmp")),
    ]


def _is_allowed(path: Path) -> bool:
    resolved = path.resolve()
    for root in _allowed_roots():
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False
