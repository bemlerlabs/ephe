"""Ephe – Utility tools (Wave 3: T1-T4).

T1: extract_pdf_text  — PDF text extraction (pdfplumber)
T2: format_code       — Python source code formatting (ruff format)
T3: run_linter        — Ruff code analysis
T4: validate_json     — JSON schema validation (Draft 2020-12)
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


# T1: extract_pdf_text
async def extract_pdf_text(path: str, max_chars: int = 8000) -> str:
    """Extracts the text from a PDF file and returns it as a string.

    Args:
        path: absolute or relative path to the PDF file.
        max_chars: maximum number of characters to return (default 8000).

    Returns:
        The extracted text of the PDF, page-wise separated by --- Page N/M ---.
        [PDF-ERROR] prefix on failure.
    """
    p = Path(path).resolve()
    if not p.exists():
        return f"[PDF-ERROR] File not found: {path}"
    if p.suffix.lower() not in (".pdf",):
        return f"[PDF-ERROR] Not a PDF file: {path}"
    try:
        import pdfplumber
    except ImportError:
        return "[PDF-ERROR] pdfplumber not installed. pip install pdfplumber."
    try:
        pages: list[str] = []
        with pdfplumber.open(str(p)) as pdf:
            total = len(pdf.pages)
            for i, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(f"--- Page {i}/{total} ---\n{text.strip()}")
        if not pages:
            return f"[PDF-ERROR] PDF has no extractable text: {path}"
        full = "\n\n".join(pages)
        if max_chars and len(full) > max_chars:
            full = (
                full[:max_chars] + f"\n\n[PDF truncated: original >{max_chars} chars]"
            )
        return full
    except Exception as exc:
        return f"[PDF-ERROR] {type(exc).__name__}: {exc}"


# T2: format_code
async def format_code(path: str, check_only: bool = False) -> str:
    """Formats a Python file with ruff format (Black-compatible).

    Args:
        path: path to the Python file.
        check_only: True = only check whether formatting is needed (no writing).

    Returns:
        OK prefix + message, or the ERROR prefix with the ruff output.
    """
    p = Path(path).resolve()
    if not p.exists():
        return f"ERROR: File not found: {path}"
    cmd = ["ruff", "format", str(p)]
    if check_only:
        cmd.append("--diff")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        # `ruff format --diff` exits 1 when a file WOULD be reformatted. That exit code
        # is the answer to the question the caller asked, not a failure: read as ERROR
        # it handed the model a retry instruction for an operation that retrying cannot
        # change. Measured on ruff 0.15.7: --diff on a messy file -> 1, clean -> 0.
        if check_only and result.returncode == 1:
            return f"OK: ruff format {p.name} (formatting needed)"
        if result.returncode == 0:
            # ruff reports the write mode on stderr as "1 file reformatted" /
            # "1 file left unchanged". Any stdout counted as "changed" reported every
            # already-formatted file as changed.
            changed = "reformatted" in (result.stdout + result.stderr)
            return f"OK: ruff format {p.name} ({'changed' if changed else 'no change needed'})"
        output = (result.stdout + "\n" + result.stderr).strip()
        return f"ERROR: ruff format {p.name}: {output[:500]}"
    except FileNotFoundError:
        return "ERROR: ruff not installed. pip install ruff."
    except subprocess.TimeoutExpired:
        return "ERROR: ruff format timeout (>30s)."
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


# T3: run_linter
async def run_linter(path: str, fix: bool = False, max_issues: int = 50) -> str:
    """Runs ruff check on a file or a directory.

    Args:
        path: path to the file or directory.
        fix: True = apply automatic corrections (--fix).
        max_issues: maximum number of displayed issues (default 50).

    Returns:
        OK prefix + summary, or the ERROR prefix with the issue list.
    """
    p = Path(path).expanduser()
    if not p.is_absolute():
        from core.engine_config import get_workspace_dir

        p = Path(get_workspace_dir()) / p
    p = p.resolve()
    if not p.exists():
        return f"ERROR: Path not found: {path}"
    cmd = ["ruff", "check", "--no-cache", str(p)]
    if fix:
        cmd.append("--fix")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = (result.stdout + "\n" + result.stderr).strip()
        if result.returncode == 0:
            return f"OK: ruff check {p.name}: no issues found"
        issue_count = sum(
            1
            for line in output.splitlines()
            if line.strip() and not line.startswith("Found")
        )
        summary = f"ERROR: ruff check {p.name}: {issue_count} issue(s)\n{output[:1500]}"
        return summary
    except FileNotFoundError:
        return "ERROR: ruff not installed. pip install ruff."
    except subprocess.TimeoutExpired:
        return "ERROR: ruff check timeout (>30s)."
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"


# T4: validate_json
async def validate_json(data: str, schema: str) -> str:
    """Validates a JSON string against a JSON schema (Draft 2020-12).

    Args:
        data: the JSON string to validate (instance).
        schema: the JSON schema as a string (Draft 2020-12, $schema may be omitted).

    Returns:
        OK prefix for a valid document, otherwise the ERROR prefix with the error list.
    """
    try:
        instance = json.loads(data)
    except json.JSONDecodeError as exc:
        return f"ERROR: JSON instance invalid: {exc}"
    try:
        schema_dict = json.loads(schema)
    except json.JSONDecodeError as exc:
        return f"ERROR: JSON schema invalid: {exc}"
    try:
        import jsonschema

        validator = jsonschema.Draft202012Validator(schema=schema_dict)
        errors = list(validator.iter_errors(instance))
        if not errors:
            return "OK: JSON valid against schema (Draft 2020-12)"
        lines = [f"ERROR: {len(errors)} validation error(s):"]
        for e in errors[:10]:
            lines.append(f"  - {e.json_path}: {e.message}")
        return "\n".join(lines)
    except ImportError:
        # fallback: basic validation without the jsonschema package
        if not isinstance(instance, dict):
            return "ERROR: jsonschema package missing. Only dict instances supported."
        req = schema_dict.get("required") or []
        props = schema_dict.get("properties") or {}
        missing = [k for k in req if k not in instance]
        if missing:
            return f"ERROR: required fields missing: {','.join(missing)} (jsonschema package missing)"
        for key, spec in props.items():
            if key not in instance:
                continue
            expected_type = spec.get("type")
            value = instance[key]
            type_map = {
                "string": str,
                "number": (int, float),
                "integer": int,
                "boolean": bool,
                "array": list,
                "object": dict,
            }
            if expected_type in type_map and not isinstance(
                value, type_map[expected_type]
            ):
                return f"ERROR: {key} expected {expected_type}, got {type(value).__name__} (jsonschema package missing)"
        return "OK: JSON valid against schema (basic check)"
    except Exception as exc:
        return f"ERROR: {type(exc).__name__}: {exc}"
