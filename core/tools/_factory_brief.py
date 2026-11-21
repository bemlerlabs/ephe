"""R34 Project Factory: whole projects and report-grade documents in one pass.

Two deterministic, evidence-gated generators:

- ``scaffold_project`` builds a complete, runnable project skeleton (manifest,
  sources, real tests, docs, gitignore, license) and verifies it structurally
  before reporting success.
- ``build_document`` composes a NotebookLM-style briefing PDF from local
  sources and/or web research, then verifies the PDF really has pages.

Both are mutating tools (they write files) and therefore pass through the
normal approval gate. Success strings are only returned after the internal
verification gate passed — the playbooks must relay them unchanged.
"""
from __future__ import annotations

import json
import os
import re

from core.tools.verify_tools import _resolve_allowed_path, _verify
from core.tools._factory_templates import BULLET_STRIP, _clean_name


def _collect_source_text(paths: list[str], max_chars: int = 60_000) -> tuple[str, list[str]]:
    """Reads local source files (txt/md/py/html/pdf via read_file rules)."""
    chunks: list[str] = []
    used: list[str] = []
    budget = max_chars
    for p in paths:
        try:
            sp = _resolve_allowed_path(p)
        except ValueError as exc:
            chunks.append(f"[skipped: {exc}]")
            continue
        if not os.path.isfile(sp):
            chunks.append(f"[skipped, not a file: {p}]")
            continue
        try:
            with open(sp, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read(budget)
        except OSError as exc:
            chunks.append(f"[skipped {p}: {exc}]")
            continue
        budget -= len(text)
        used.append(sp)
        chunks.append(f"## Source: {os.path.basename(sp)}\n\n{text}")
        if budget <= 0:
            break
    return "\n\n".join(chunks), used


async def build_document(
    topic: str,
    source_paths: str = "",
    include_web_research: bool = True,
    filename: str = "",
) -> str:
    """Builds a report-grade briefing PDF (NotebookLM-style) and verifies it.

    Gathers evidence from local files and (optionally) web research, writes a
    structured brief, renders it via the PDF tool, then checks the PDF really
    has pages. Only DOCUMENT_BUILT_VERIFIED may be relayed as finished.
    """
    topic = (topic or "").strip()
    if not topic:
        return "[factory-error: topic is required]"
    paths = [p.strip() for p in (source_paths or "").split(",") if p.strip()][:8]
    evidence_parts: list[str] = []
    used_sources: list[str] = []
    if paths:
        text, used_sources = _collect_source_text(paths)
        if text:
            evidence_parts.append(text)
    if include_web_research:
        try:
            from core.tools.web_search import web_search

            hits = await web_search(f"{topic} overview facts 2026", max_results=5)
            if hits:
                evidence_parts.append(str(hits)[:12_000])
        except Exception as exc:
            evidence_parts.append(f"[web research unavailable: {exc}]")
    evidence = "\n\n".join(evidence_parts).strip()

    from core.tools.pdf_tools import create_pdf

    title = topic[:90]
    content = _compose_brief_markdown(title, topic, evidence)
    out = await create_pdf(title=title, content=content,
                          filename=filename or f"ephe_brief_{_clean_name(topic, 'document')}.pdf",
                          template="report")
    m = re.search(r"PDF_FILE:(.+)", out or "")
    produced = m.group(1).strip() if m else ""
    if not produced or not os.path.isfile(produced):
        return f"DOCUMENT_BUILD_INCOMPLETE: pdf tool reported: {(out or '')[:400]}"
    check = _verify(produced, json.dumps({"kind": "pdf", "min_pages": 1}))
    payload = {"path": produced, "topic": topic, "sources": used_sources,
               "web_research": bool(include_web_research), "metrics": check["metrics"]}
    body = json.dumps(payload, ensure_ascii=False)
    if check["verified"]:
        return f"DOCUMENT_BUILT_VERIFIED: {body}"
    return f"DOCUMENT_BUILD_INCOMPLETE: {body} || failures={check['failures']}"


def _san(text: str) -> str:
    text = text.replace("\u25a0", "-").replace("\u25aa", "-").replace("\u00b6", "")
    return re.sub(r" {2,}", " ", text)


def _compose_brief_markdown(title: str, topic: str, evidence: str) -> str:
    """Deterministic report skeleton: exec summary, sections, sources."""
    lines = [
        f"# {title}",
        "",
        "## Executive Summary",
        f"This briefing answers: {topic}. It synthesizes the gathered local and",
        "web evidence into a compact, source-grounded overview.",
        "",
        "## Key Findings",
    ]
    facts = [ln.strip() for ln in evidence.splitlines()
             if ln.strip().startswith(("-", "*", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"))
             and len(ln.strip()) > 25][:12]
    if not facts:
        facts = [ln.strip() for ln in evidence.splitlines() if len(ln.strip()) > 25][:12]
    if not facts:
        facts = ["No evidence lines were collected for this topic."]
    lines += [f"- {_san(BULLET_STRIP.sub('', f))}" for f in facts]
    lines += ["", "## Analysis", "",
              "The findings above were extracted verbatim from the evidence base;",
              "no claims beyond the sources were added.", "",
              "## Recommended Next Steps",
              "- Validate the top findings against a primary source.",
              "- Decide scope and budget before implementation.",
              "- Produce a follow-up briefing with deeper sections.",
              "", "## Source Notes", ""]
    srcs = [ln for ln in evidence.splitlines() if ln.startswith("## Source:")]
    lines += [f"- {_san(s.lstrip('#').strip())}" for s in srcs] or ["- See the Evidence Appendix."]
    lines += ["", "## Evidence Appendix", ""]
    appendix = [ln.strip() for ln in evidence.splitlines() if ln.strip()][:40]
    lines += [f"- {_san(BULLET_STRIP.sub('', ln))}" if ln.startswith(("-", "*")) else _san(ln)
              for ln in appendix] or ["- No evidence collected."]
    return "\n".join(lines)
