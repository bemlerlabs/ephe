"""R34 Project Factory: evidence gates for generated artifacts.

A skill playbook must not report an artifact as "done" on trust alone — it
calls ``verify_artifact`` and only a VERIFIED report may be announced as
finished. The tool is read-only, and it resolves the allowed roots on each call.
For compatibility, the runtime Python (local fork build) and the CI matrix
(3.10–3.13) rename a few path helpers, so this module sticks to string
paths plus the os.path primitives that are named identically on both
platforms (verified via the usages in the other tool modules).
"""
from __future__ import annotations

import json
import os
import re
import zipfile

from core.tools import base as tools_base

MAX_SCAN_BYTES = 40_000_000  # guard against reading huge binaries into memory

#: Checks each kind actually reads. A key no code reads is a lie waiting to happen:
#: a typo'd ``min_pages`` still answered ARTIFACT_VERIFIED. Naming the accepted keys
#: is what makes the rejection actionable.
COMMON_CHECKS: tuple[str, ...] = ("kind", "min_bytes")
KIND_CHECKS: dict[str, tuple[str, ...]] = {
    "pdf": ("min_pages",), "pptx": ("min_slides",), "docx": ("min_words",),
    "xlsx": ("min_sheets", "min_rows"), "project": ("min_files", "required_files"),
    "file": ("min_words",), "image": (),
}

_WALK = getattr(os, "walk", None) or getattr(os, "walk")


def _int_opt(opts: dict, key: str) -> tuple[int, str]:
    """(value, error) for a numeric check — never raises; ``"three"`` used to."""
    raw = opts.get(key)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return 0, ""
    if isinstance(raw, bool):
        return 0, f"{key}: true/false is not a number"
    if isinstance(raw, str):
        try:
            raw = int(raw.strip())
        except ValueError:
            return 0, f"{key}: '{raw.strip()}' is not a number"
    if isinstance(raw, float):
        if not raw.is_integer():
            return 0, f"{key}: {raw!r} is not a whole number"
        raw = int(raw)
    if not isinstance(raw, int):
        return 0, f"{key}: expected a number, got {type(raw).__name__}"
    return (0, f"{key}: must be 0 or more, got {raw}") if raw < 0 else (raw, "")


def _required_files(raw: object) -> tuple[list[str], str]:
    """``required_files`` as a list; a bare string meant one file, not its letters."""
    if raw is None:
        return [], ""
    if isinstance(raw, str):
        return ([raw.strip()] if raw.strip() else []), ""
    if isinstance(raw, (list, tuple)):
        return [str(i) for i in raw if str(i).strip()], ""
    return [], f"required_files must be a list of paths or one path, got {type(raw).__name__}"


def _near_names(sp: str) -> str:
    """A few real entries beside a missing path: recovery from a guessed
    filename, read-only inside the directory the boundary check allowed."""
    parent = os.path.dirname(sp)
    try:
        names = [n for n in sorted(os.listdir(parent)) if not n.startswith(".")]
    except OSError:
        return ""
    if not names:
        return f" — the folder {parent} is empty"
    ext = os.path.splitext(os.path.basename(sp))[1].lower()
    same_kind = [n for n in names if os.path.splitext(n)[1].lower() == ext]
    chosen = (same_kind + [n for n in names if n not in same_kind])[:6]  # 6 names is enough to recover
    return " — nothing of that name here; in this folder: " + ", ".join(chosen)


def _resolve_allowed_path(path: str) -> str:
    """Resolves a user path and enforces the ALLOWED_ROOTS boundary."""
    sp = os.path.expanduser(str(path))
    if not os.path.isabs(sp):
        # Same base as write_file/read_file (file_ops._resolve_against_workspace):
        # the agent's relative paths are workspace-relative, the server cwd is not.
        from core.engine_config import get_workspace_dir

        sp = os.path.join(get_workspace_dir(), sp)
    sp = os.path.realpath(sp)
    for root in tools_base.ALLOWED_ROOTS:
        try:
            resolved_root = os.path.realpath(str(root))
        except OSError:
            continue
        if sp == resolved_root or sp.startswith(resolved_root + os.sep):
            return sp
    allowed = ", ".join(str(r) for r in tools_base.ALLOWED_ROOTS)
    raise ValueError(f"Path outside allowed roots: {path} (allowed: {allowed})")


def _pdf_page_count(sp: str) -> int:
    """Counts PDF pages: pypdfium2 (real parser) with a byte-scan fallback.

    The byte scan counts ``/Type /Page`` objects while ignoring the
    ``/Type /Pages`` tree nodes — good enough for files Ephe itself
    generated; returns 0 for unreadable files.
    """
    try:
        import pypdfium2

        doc = pypdfium2.PdfDocument(sp)
        try:
            return len(doc)
        finally:
            doc.close()
    except Exception:
        pass
    try:
        with open(sp, "rb") as fh:
            data = fh.read(MAX_SCAN_BYTES)
    except OSError:
        return 0
    normalized = data.replace(b"\r", b" ").replace(b"\n", b" ")
    pages = 0
    for m in re.finditer(rb"/Type\s*/(Page|Pages)(?![A-Za-z])", normalized):
        if m.group(1) == b"Page":
            pages += 1
    if pages == 0:
        # Fallback: /Count on the page tree (single root) — still a heuristic.
        counts = [int(c) for c in re.findall(rb"/Count\s+(\d+)", normalized)]
        pages = max(counts) if counts else 0
    return pages


def _pptx_slide_count(sp: str) -> tuple[int, int]:
    """Returns (slide_count, non_empty_slides) from the OOXML package."""
    try:
        with zipfile.ZipFile(sp) as zf:
            slides = [n for n in zf.namelist()
                      if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
            non_empty = 0
            for name in slides:
                xml = zf.read(name).decode("utf-8", errors="replace")
                texts = re.findall(r"<a:t[^>]*>([^<]+)</a:t>", xml)
                if sum(len(t.strip()) for t in texts) >= 5:
                    non_empty += 1
            return len(slides), non_empty
    except Exception:
        return 0, 0


def _docx_stats(sp: str) -> tuple[int, int]:
    """Returns (paragraph_count, word_count) from the document part."""
    try:
        with zipfile.ZipFile(sp) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    except Exception:
        return 0, 0
    runs = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml)
    words = sum(len(t.split()) for t in runs)
    paragraphs = len(re.findall(r"<w:p[ >/]", xml))
    return paragraphs, words


def _xlsx_stats(sp: str) -> tuple[int, int]:
    """Returns (sheet_count, max_rows) using openpyxl in read-only mode."""
    try:
        from openpyxl import load_workbook

        wb = load_workbook(sp, read_only=True, data_only=True)
        try:
            names = getattr(wb, "sheetnames", None) or getattr(wb, "sheet_names", [])
            max_rows = max(
                (int(getattr(ws, "maxrow", None) or getattr(ws, "max_row", None) or 0)
                 for ws in wb.worksheets),
                default=0,
            )
            return len(list(names)), max_rows
        finally:
            wb.close()
    except Exception:
        return 0, 0


def _text_word_count(sp: str) -> int:
    try:
        with open(sp, "r", encoding="utf-8", errors="replace") as fh:
            return len(fh.read().split())
    except OSError:
        return 0


def _project_stats(root: str, required: list[str]) -> dict:
    """Structural checks for a generated project directory."""
    skip = {".git", "__pycache__", ".venv", "node_modules", ".pytest_cache", ".mypy_cache"}
    rel: list[str] = []
    for dirpath, dirnames, filenames in _WALK(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        prefix = "" if dirpath == root else dirpath[len(root) + 1:] + "/"
        rel.extend(prefix + fn for fn in filenames)
    rel.sort()
    relset = set(rel)
    missing = [r for r in required if r not in relset
               and not any(o.startswith(r.rstrip("/") + "/") for o in relset)]
    empty = []
    for r in rel:
        try:
            if os.path.getsize(os.path.join(root, r)) == 0:
                empty.append(r)
        except OSError:
            pass
    has_readme = any(os.path.basename(r).upper().startswith("README") for r in rel)
    return {
        "files": len(rel),
        "missing_required": missing,
        "empty_files": empty,
        "has_readme": has_readme,
    }


def _is_image(sp: str) -> bool:
    if os.path.splitext(sp)[1].lower() in tools_base.SUPPORTED_IMAGE_EXTENSIONS:
        return True
    try:
        with open(sp, "rb") as fh:
            head = fh.read(8)
        return (head.startswith(b"\x89PNG") or head.startswith(b"\xFF\xD8\xFF")
                or head[:4] == b"RIFF" or head.startswith(b"GIF8"))
    except OSError:
        return False


def _verify(path: str, checks: str = "{}") -> dict:
    """Pure verification logic; returns the report dict (never raises)."""
    try:
        opts = json.loads(checks) if checks and checks.strip() else {}
        if not isinstance(opts, dict):
            raise ValueError("checks must be a JSON object")
    except (ValueError, TypeError) as exc:
        return {"verified": False, "kind": "invalid", "failures": [f"checks: {exc}"], "metrics": {}}

    if not str(path or "").strip():
        return {"verified": False, "kind": "path",
                "failures": ["no path given — pass the artifact or project folder to check"],
                "metrics": {}}

    try:
        sp = _resolve_allowed_path(path)
    except ValueError as exc:
        return {"verified": False, "kind": "path", "failures": [str(exc)], "metrics": {}}

    if not os.path.exists(sp):
        return {
            "verified": False,
            "kind": "missing",
            "failures": [f"Path does not exist: {path}{_near_names(sp)}"],
            "metrics": {},
        }

    kind = (opts.get("kind") or "auto").lower()
    failures: list[str] = []
    metrics: dict = {}

    def limit(key: str) -> int:
        """Numeric check for this kind; a bad value fails the gate loudly."""
        value, error = _int_opt(opts, key)
        if error:
            failures.append(f"checks: {error}")
        return value

    min_bytes = limit("min_bytes")

    if os.path.isfile(sp):
        size = os.path.getsize(sp)
        metrics["bytes"] = size
        if size == 0:
            failures.append("file is empty (0 bytes)")
        elif min_bytes and size < min_bytes:
            failures.append(f"file is {size} bytes, below min_bytes {min_bytes}")
        elif min_bytes == 0 and kind == "auto" and size < 50:
            failures.append("file is suspiciously small (<50 bytes)")

        ext = os.path.splitext(sp)[1].lstrip(".").lower()
        if kind == "auto":
            if ext == "pdf":
                kind = "pdf"
            elif ext in ("pptx", "docx", "xlsx"):
                kind = ext
            elif _is_image(sp):
                kind = "image"
            else:
                kind = "file"
    if os.path.isdir(sp):
        kind = "project"
        if "min_bytes" in opts:
            failures.append("checks: min_bytes does not apply to a directory — use min_files")

    if kind not in KIND_CHECKS:
        kinds = ", ".join(["auto"] + sorted(KIND_CHECKS))
        return {"verified": False, "kind": kind, "path": sp, "metrics": metrics,
                "failures": [f"checks: kind '{kind}' is not known. Use one of: {kinds}."]}

    # A key the resolved kind never reads would drop the requirement silently.
    allowed = set(COMMON_CHECKS) | set(KIND_CHECKS[kind])
    for unknown in sorted(set(opts) - allowed):
        failures.append(f"checks: '{unknown}' is not read for kind '{kind}'. "
                        f"Accepted here: {', '.join(sorted(allowed))}.")

    if kind == "pdf":
        pages = _pdf_page_count(sp)
        metrics["pages"] = pages
        if pages < 1:
            failures.append("not a readable PDF (0 pages found)")
        min_pages = limit("min_pages")
        if min_pages and pages < min_pages:
            failures.append(f"PDF has {pages} pages, below min_pages {min_pages}")
    elif kind == "pptx":
        slides, non_empty = _pptx_slide_count(sp)
        metrics["slides"] = slides
        metrics["non_empty_slides"] = non_empty
        if slides < 1:
            failures.append("not a readable PPTX (0 slides)")
        min_slides = limit("min_slides")
        if min_slides and slides < min_slides:
            failures.append(f"deck has {slides} slides, below min_slides {min_slides}")
        if slides and non_empty < slides:
            failures.append(f"{slides - non_empty} slide(s) are empty (no text)")
    elif kind == "docx":
        paragraphs, words = _docx_stats(sp)
        metrics["paragraphs"] = paragraphs
        metrics["words"] = words
        if words < 1:
            failures.append("not a readable DOCX (no text runs)")
        min_words = limit("min_words")
        if min_words and words < min_words:
            failures.append(f"document has {words} words, below min_words {min_words}")
    elif kind == "xlsx":
        sheets, max_rows = _xlsx_stats(sp)
        metrics["sheets"] = sheets
        metrics["max_rows"] = max_rows
        if sheets < 1:
            failures.append("not a readable XLSX (0 sheets)")
        min_sheets = limit("min_sheets")
        if min_sheets and sheets < min_sheets:
            failures.append(f"workbook has {sheets} sheets, below min_sheets {min_sheets}")
        min_rows = limit("min_rows")
        if min_rows and max_rows < min_rows:
            failures.append(f"largest sheet has {max_rows} rows, below min_rows {min_rows}")
    elif kind == "project":
        required, required_error = _required_files(opts.get("required_files"))
        if required_error:
            failures.append(f"checks: {required_error}")
        stats = _project_stats(sp, required)
        metrics.update(stats)
        if stats["files"] == 0:
            failures.append("folder holds no files — nothing was generated here")
        if stats["missing_required"]:
            failures.append(f"missing required files: {', '.join(stats['missing_required'])}")
        if stats["empty_files"]:
            failures.append(f"empty files: {', '.join(stats['empty_files'][:5])}")
        min_files = limit("min_files")
        if min_files and stats["files"] < min_files:
            failures.append(f"project has {stats['files']} files, below min_files {min_files}")
    elif kind == "image":
        if not _is_image(sp):
            failures.append("file is not a valid image (bad magic bytes)")
    else:  # kind == "file": plain text/other deliverable
        min_words = limit("min_words")
        if min_words:
            words = _text_word_count(sp)
            metrics["words"] = words
            if words < min_words:
                failures.append(f"file has {words} words, below min_words {min_words}")

    return {
        "verified": not failures,
        "kind": kind,
        "path": sp,
        "failures": failures,
        "metrics": metrics,
    }


async def verify_artifact(path: str, checks: str = "{}") -> str:
    """Verifies that a generated artifact really exists and is complete.

    Evidence gate for skill playbooks: report an artifact as finished only
    when this tool returns ARTIFACT_VERIFIED. ``checks`` is a JSON object,
    e.g. {"kind":"pdf","min_pages":3} or
    {"kind":"project","min_files":8,"required_files":["README.md","tests"]}.
    """
    report = _verify(path, checks)
    payload = json.dumps(report, ensure_ascii=False)
    if report["verified"]:
        return f"ARTIFACT_VERIFIED: {payload}"
    return f"ARTIFACT_FAILED: {payload}"
