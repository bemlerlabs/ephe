"""Ephe – redact: central secret redaction (R23).

Acceptance R23: "no secret in any log/trace". Everything that gets logged
(the audit log, error messages shown to the user) runs through `redact()`.
Conservative: better one mask too many than a key in the log.
"""
from __future__ import annotations

import hashlib
import json
import re

# API-key literals by prefix pattern (sk-, the gh*_ GitHub family, hf_, xox[b/p]-)
# The gh family: p = classic PAT, o = OAuth, u = user-to-server, s = installation,
# r = refresh. The installation form is the one that grows to ~520 characters, and it
# reaches logs as readily as the others.
_KEY_LITERALS = re.compile(
    r"\b(sk-[A-Za-z0-9_-]{8,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|hf_[A-Za-z0-9]{20,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|AIza[0-9A-Za-z_-]{35,}"
    r"|glpat-[A-Za-z0-9_-]{20,})\b"
)
# Private key blocks: the header and footer are the shape; the body is arbitrary.
# Two anchored patterns instead of one header-to-footer regex: a lazy body re-scans
# to the end of the input at every BEGIN it cannot close, so a model-written log line
# could stall the redactor (CodeQL py/polynomial-redos, 2026-10-18). The bounded label
# keeps each scan linear; _mask_pem pairs the spans in one forward walk.
_PEM_HEADER = re.compile(r"-----BEGIN [A-Z0-9 ]{0,64}PRIVATE KEY-----")
_PEM_FOOTER = re.compile(r"-----END [A-Z0-9 ]{0,64}PRIVATE KEY-----")
# Bearer/Basic headers
_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._-]{8,}")
# Query parameters (token= / key= / api_key=) in URLs
_QUERY_SECRET = re.compile(
    r"(?i)([?&](?:token|api_key|apikey|access_token|key)=)[^&\s\"']+"
)
# JSON/YAML/env-style assignments
_KV_SECRET = re.compile(
    r"(?i)((?:\"?api_?key\"?|\"?password\"?|\"?secret\"?|\"?access_token\"?|\"?authorization\"?)\"?\s*[:=]\s*)(\"[^\"]{4,}\"|'[^']{4,}'|[^\s,;}\]]{8,})"
)
# EPHE_* env values in logs (EPHE_OPENAI_COMPAT_API_KEY=…). The name run is bounded
# and free of the credential alternation, which is what a log line could otherwise
# drive into backtracking.
_ENV_ASSIGN = re.compile(r"(?i)((EPHE_[A-Z_]{0,64})\s*=\s*)(\S+)")
_ENV_SENSITIVE = re.compile(r"KEY|TOKEN|SECRET")

_MASK = "***"


def _mask_env_assignment(match: "re.Match[str]") -> str:
    """Mask one EPHE_* assignment when the variable name holds KEY, TOKEN or SECRET."""
    if _ENV_SENSITIVE.search(match.group(2)):
        return match.group(1) + _MASK
    return match.group(0)


def _mask_pem(text: str) -> str:
    """Masks each BEGIN/END private-key block; an unclosed header masks the rest.

    A log line and an error message are both truncated, so the header without a
    footer is exactly how a key reaches a sink: the body after it is key material
    whether or not the END line survived the cut.
    """
    out: list[str] = []
    pos = 0
    footers = list(_PEM_FOOTER.finditer(text))
    footer_at = 0
    for header in _PEM_HEADER.finditer(text):
        if header.start() < pos:
            continue
        while footer_at < len(footers) and footers[footer_at].start() < header.end():
            footer_at += 1
        if footer_at >= len(footers):
            out.append(text[pos:header.start()])
            out.append(_MASK)
            return "".join(out)
        out.append(text[pos:header.start()])
        out.append(_MASK)
        pos = footers[footer_at].end()
        footer_at += 1
    out.append(text[pos:])
    return "".join(out)


def redact(text: str) -> str:
    """Masks secrets in free text (logs, errors, audit details)."""
    if not text:
        return text
    out = text
    out = _mask_pem(out)
    out = _KEY_LITERALS.sub(lambda m: m.group(0)[:4] + _MASK, out)
    out = _BEARER.sub(lambda m: m.group(1) + _MASK, out)
    out = _QUERY_SECRET.sub(lambda m: m.group(1) + _MASK, out)
    out = _KV_SECRET.sub(lambda m: m.group(1) + _MASK, out)
    out = _ENV_ASSIGN.sub(_mask_env_assignment, out)
    return out


def args_hash(args: dict | None) -> str:
    """Short, stable identifier **of the unredacted** arguments (16 hex digits,
    without salt).

    This is an identity proof for one call, not a blacking-out: with
    low-entropy arguments — a file name, a title — the value can be recovered by
    guessing. That is why the surface (A3 provenance) shows the redacted short
    text and never this digest; and an audit that is shared or photographed
    carries it only as a reference to a line.
    """
    try:
        canonical = json.dumps(args or {}, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        canonical = repr(args)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


#: Characters a truncated value must not end with — a dangling `", ` or `;`
#: reads like the text itself.
_HAENGET = " ,;:=-\u201c\"'"


def _kurz(text: str, grenze: int) -> str:
    """Truncate a value **and** show the truncation.

    Two findings from the provenance line of a live card: a JSON value broke off
    at 80 characters in the middle of the object and left `", ; name=create_pdf`
    behind (read as broken), and a search text ended on `… Peter Möhring  # language-gate: ignore (verbatim truncated fixture text, quoted as the observed defect)
    Geschä` (read as complete). Both are the surface lying about its own brevity.  # language-gate: ignore (continuation of the quoted fixture above)
    """
    if len(text) <= grenze:
        return text
    return text[:grenze].rstrip(_HAENGET) + "…"


def args_summary(args: dict | None, limit: int = 160) -> str:
    """Redacted, short argument summary for the audit log."""
    try:
        parts = [f"{k}={_kurz(redact(str(v)), 80)}" for k, v in sorted((args or {}).items())]
        summary = "; ".join(parts)
    except Exception:
        summary = "<unserialisierbar>"
    return _kurz(redact(summary), limit)


def redact_deep(value: object) -> object:
    """Redacts every string inside a JSON-shaped value, keys and nesting preserved.

    The four sinks (model context, SSE, run ledger, audit log) carry structures, not
    one string; masking only the top level leaves a token inside an artifact payload
    or an event's nested result. Dict keys are left alone: they are field names from
    our own protocol, and renaming one would break the reader.
    """
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {key: redact_deep(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_deep(item) for item in value]
    return value
