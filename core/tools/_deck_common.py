"""Ephe – Pitch deck / PPTX tools."""

from __future__ import annotations

import html
import re
from pathlib import Path

from core.tools.base import (
    FileNotAllowedError,
    _is_path_allowed,
)


def _safe_download_filename(filename: str, default: str, suffix: str) -> str:
    safe_name = Path(filename or default).name
    safe_name = re.sub(r"\s+", "_", safe_name.strip())
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "", safe_name)
    safe_name = re.sub(r"_+", "_", safe_name).strip("._-")
    if not safe_name:
        safe_name = default
    if not safe_name.lower().endswith(suffix):
        safe_name += suffix
    return safe_name


def _deck_slug(topic: str, filename: str, default: str, suffix: str) -> str:
    # Wave 10 (P1-1): prefix = a short title slug, not the raw prompt remainder.
    # The LLM often passes filename == prompt (>60 characters, collides). Only
    # when no explicit filename is set (== default) does the topic slug win.
    if filename and filename != default:
        return _safe_download_filename(filename, default, suffix)
    slug = re.sub(r"\s+", "_", str(topic or default).strip()).lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")
    slug = slug[:40].rstrip("_")
    return _safe_download_filename(slug or default, default, suffix)


def _split_lines(text: str, max_chars: int = 72, max_lines: int = 4) -> list[str]:
    words = (text or "").strip().split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:max_lines] or [""]


def _enterprise_clean_text(text: str) -> str:
    cleaned = re.sub(r"[\U0001F300-\U0001FAFF]", "", str(text or ""))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    replacements = {
        "awesome": "strong",
        "cool": "credible",
        "fun": "engaging",
        "cute": "clean",
        "wow": "notable",
        "magic": "workflow",
        "revolutionary": "material",
        "game changer": "strategic shift",
        "amazing": "strong",
        "super": "high",
        "mega": "large",
        "krass": "deutlich",
        "geil": "stark",
        "kindisch": "unreif",
        "lustig": "ansprechend",
    }
    for source, target in replacements.items():
        cleaned = re.sub(rf"\b{re.escape(source)}\b", target, cleaned, flags=re.IGNORECASE)
    return cleaned


def _normalize_enterprise_slides(slides: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for index, slide in enumerate(slides, 1):
        title = _enterprise_clean_text(slide.get("title") or f"Slide {index}")
        claim = _enterprise_clean_text(slide.get("claim") or title)
        body = _enterprise_clean_text(slide.get("body") or "")
        proof = _enterprise_clean_text(slide.get("proof") or "Proof object")
        visual = re.sub(r"[^a-z0-9_-]", "", str(slide.get("visual") or "custom").lower()) or "custom"
        normalized.append({"title": title, "claim": claim, "body": body, "visual": visual, "proof": proof})
    return normalized


def _default_deck_slides(topic: str, audience: str, thesis: str) -> list[dict[str, str]]:
    subject = topic.strip() or "Ephe"
    audience_text = audience.strip() or "decision makers"
    thesis_text = thesis.strip() or f"{subject} turns local AI workflows into reliable, private execution."
    return [
        {"title": subject, "claim": thesis_text, "body": f"For {audience_text}: a focused investment-grade story with proof, workflow, and next step.", "visual": "hero", "proof": "Thesis card"},
        {"title": "The Shift", "claim": "Users now expect local AI to produce finished work, not rough drafts.", "body": "Privacy, latency, and tool control are becoming product requirements. The winning system makes local execution feel premium and verifiable.", "visual": "trend", "proof": "Market shift curve"},
        {"title": "Problem", "claim": "Most local assistants fail when work becomes multi-step or artifact-heavy.", "body": "They lose context, over-promise tool results, and generate files that are hard to trust without manual inspection.", "visual": "pain", "proof": "Failure stack"},
        {"title": "Solution", "claim": f"{subject} combines skills, tools, memory, and quality gates into one local workflow.", "body": "The user asks naturally; the system selects the right skill, executes real local tools, checks artifacts, and returns grounded output.", "visual": "system", "proof": "Workflow architecture"},
        {"title": "Product Experience", "claim": "The interface must show progress, evidence, and artifacts without making users manage the machinery.", "body": "Skill chips, activity status, file paths, and artifact checks keep the workflow understandable while the assistant does the work.", "visual": "interface", "proof": "Experience map"},
        {"title": "Proof Of Quality", "claim": "High-end output comes from repeatable rubrics, not from style prompts alone.", "body": "Each flagship skill needs a rubric, examples, deterministic validation, and local eval cases for regression control.", "visual": "score", "proof": "Quality ladder"},
        {"title": "Market Logic", "claim": "Local-first AI is a defensible wedge where privacy and control matter.", "body": "Developers, founders, operators, and creators need artifact-grade output while keeping files, screenshots, and workflows on the machine.", "visual": "market", "proof": "Segment matrix"},
        {"title": "Execution Roadmap", "claim": "The next milestone is premium artifact creation across PDFs, decks, charts, scans, and code.", "body": "Start with deck/PDF quality, then expand validators and evals across every user-facing skill.", "visual": "roadmap", "proof": "Milestone plan"},
        {"title": "Risks And Controls", "claim": "Trust improves when uncertainty is visible and fake success is impossible.", "body": "Missing inputs, failed tools, weak evidence, and invalid artifacts should surface as warnings instead of confident claims.", "visual": "risk", "proof": "Control gates"},
        {"title": "The Ask", "claim": "Standardize every skill around real tools, evidence, and polished artifacts.", "body": "Approve the local high-end artifact system as the default for future Ephe user workflows.", "visual": "ask", "proof": "Decision frame"},
        {"title": "Appendix", "claim": "Animation plan, source notes, and scorecard are included for presenter-ready refinement.", "body": "Use the companion HTML preview for motion direction. Replace generated visual motifs with product screenshots or brand assets when available.", "visual": "appendix", "proof": "Source notes"},
    ]


def _parse_deck_slides(slides: list[dict] | str | None, topic: str, audience: str, thesis: str) -> list[dict[str, str]]:
    if isinstance(slides, str) and slides.strip():
        parsed: list[dict[str, str]] = []
        blocks = [block.strip() for block in re.split(r"\n\s*\n", slides) if block.strip()]
        # R40c: labeled fields (slidev parity: title/claim/body + note) are
        # detected before the line protocol; unlabeled sequences stay 1:1 compatible.
        _LABELS = ("title", "claim", "body", "note")
        for index, block in enumerate(blocks, 1):
            lines = [line.strip(" -") for line in block.splitlines() if line.strip()]
            if not lines:
                continue
            labeled: dict[str, str] = {}
            plain: list[str] = []
            for line in lines:
                head, _, tail = line.partition(":")
                key = head.strip().lower().lstrip("# ")
                if key in _LABELS and tail.strip():
                    labeled[key] = tail.strip()
                else:
                    plain.append(line.lstrip("# ").strip())
            if not plain and not labeled:
                continue
            title = labeled.get("title") or (plain[0] if plain else f"Slide {index}")
            if labeled.get("claim"):
                claim = labeled["claim"]
            elif len(plain) > (1 if labeled.get("title") or not plain else 1):
                # mixed: title labeled → the first plain line is the claim;
                # otherwise as before: plain[0]=title, plain[1]=claim.
                claim = plain[0] if labeled.get("title") else (plain[1] if len(plain) > 1 else plain[0])
            else:
                claim = title
            body = labeled.get("body") or " ".join(
                plain[1:] if (labeled.get("title") or not plain) else plain[2:]
            )
            slide = {
                "title": title or f"Slide {index}",
                "claim": claim or title,
                "body": body,
                "visual": "custom",
                "proof": "Proof object",
            }
            if labeled.get("note"):
                slide["speaker_note"] = labeled["note"]
            parsed.append(slide)
        if parsed:
            return parsed

    if isinstance(slides, list) and slides:
        normalized = []
        for index, raw in enumerate(slides, 1):
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title") or raw.get("headline") or f"Slide {index}").strip()
            claim = str(raw.get("claim") or raw.get("subtitle") or title).strip()
            body = str(raw.get("body") or raw.get("notes") or raw.get("content") or "").strip()
            visual = str(raw.get("visual") or raw.get("layout") or "custom").strip()
            proof = str(raw.get("proof") or raw.get("proof_object") or raw.get("evidence") or "Proof object").strip()
            normalized.append({"title": title, "claim": claim, "body": body, "visual": visual, "proof": proof})
        if normalized:
            return normalized

    return _default_deck_slides(topic, audience, thesis)


def _pdf_escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _pdf_text(text: str, x: float, y: float, size: int, font: str = "F1", color: str = "0.06 0.09 0.13") -> str:
    return f"BT {color} rg /{font} {size} Tf {x:.1f} {y:.1f} Td ({_pdf_escape(text)}) Tj ET\n"


def _xml_escape(text: str) -> str:
    return html.escape(str(text or ""), quote=True)


def _resolve_allowed_file(path: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not _is_path_allowed(candidate):
        raise FileNotAllowedError(str(candidate))
    return candidate.resolve()


def _normalize_hex_color(value: str, fallback: str = "") -> str:
    text = str(value or "").strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{6}", text):
        return text.upper()
    return fallback


def _normalize_brand_kit(brand_name: str = "", brand_primary: str = "", brand_secondary: str = "") -> dict[str, str]:
    primary = _normalize_hex_color(brand_primary, "")
    secondary = _normalize_hex_color(brand_secondary, "")
    return {
        "brand_name": _enterprise_clean_text(brand_name)[:80],
        "primary": primary,
        "secondary": secondary,
    }


def _deck_v2_brand_kit(brand_name: str = "", brand_primary: str = "", brand_secondary: str = "") -> dict[str, str]:
    from core.deck_design import normalize_brand_kit
    return normalize_brand_kit(brand_name=brand_name, brand_primary=brand_primary, brand_secondary=brand_secondary)


def _normalize_deck_asset_paths(asset_paths: list[str] | str | None) -> list[str]:
    if not asset_paths:
        return []
    raw_paths = [asset_paths] if isinstance(asset_paths, str) else list(asset_paths)
    normalized: list[str] = []
    for raw in raw_paths:
        candidate = Path(str(raw)).expanduser()
        if candidate.exists() and _is_path_allowed(candidate):
            normalized.append(str(candidate.resolve()))
    return normalized


def _deck_palette(design_theme: str) -> dict[str, str]:
    themes = {
        "evergreen": {
            "paper": "0.984 0.988 0.984",
            "band": "0.086 0.639 0.290",
            "soft": "0.928 0.972 0.941",
            "ink": "0.06 0.09 0.13",
            "muted": "0.32 0.38 0.44",
            "accent": "0.035 0.569 0.698",
            "warn": "0.850 0.467 0.024",
        },
        "executive": {
            "paper": "0.980 0.980 0.965",
            "band": "0.055 0.090 0.140",
            "soft": "0.930 0.940 0.930",
            "ink": "0.055 0.090 0.140",
            "muted": "0.330 0.360 0.390",
            "accent": "0.086 0.639 0.290",
            "warn": "0.780 0.350 0.030",
        },
        "studio": {
            "paper": "0.990 0.985 0.972",
            "band": "0.035 0.569 0.698",
            "soft": "0.925 0.965 0.972",
            "ink": "0.080 0.090 0.110",
            "muted": "0.320 0.360 0.410",
            "accent": "0.086 0.639 0.290",
            "warn": "0.820 0.420 0.050",
        },
    }
    return themes.get((design_theme or "").lower(), themes["evergreen"])


def _visual_commands(kind: str, x: int, y: int, w: int, h: int, palette: dict[str, str]) -> list[str]:
    accent = palette["accent"]
    band = palette["band"]
    warn = palette["warn"]
    inner_x = x + 34
    inner_y = y + 46
    inner_w = w - 68
    inner_h = h - 108
    if kind in {"trend", "market", "score"}:
        points = [
            (inner_x, inner_y + 8),
            (inner_x + inner_w * 0.28, inner_y + inner_h * 0.35),
            (inner_x + inner_w * 0.58, inner_y + inner_h * 0.68),
            (inner_x + inner_w, inner_y + inner_h),
        ]
        line = f"{band} RG 3 w {points[0][0]:.1f} {points[0][1]:.1f} m " + " ".join(
            f"{px:.1f} {py:.1f} l" for px, py in points[1:]
        ) + " S\n"
        dots = " ".join(f"{band} rg {px - 4:.1f} {py - 4:.1f} 8 8 re f" for px, py in points)
        return [
            line,
            f"{dots}\n",
            f"{accent} RG 1.3 w {inner_x:.1f} {inner_y:.1f} m {inner_x + inner_w:.1f} {inner_y:.1f} l S\n",
        ]
    if kind in {"roadmap", "system"}:
        commands = []
        for row, label in enumerate(("Discover", "Build", "Validate", "Scale")):
            yy = y + 146 - row * 38
            commands.append(f"1 1 1 rg {x + 34} {yy} 172 24 re f {band} RG {x + 34} {yy} 172 24 re S\n")
            commands.append(_pdf_text(label, x + 49, yy + 8, 9, "F2", palette["ink"]))
        return commands
    if kind in {"pain", "risk"}:
        commands = []
        for row, label in enumerate(("Input", "Tool", "Artifact")):
            yy = y + 142 - row * 48
            commands.append(f"{warn} RG 1.6 w {x + 38} {yy} 152 30 re S\n")
            commands.append(_pdf_text(label, x + 80, yy + 10, 10, "F2", palette["ink"]))
        return commands
    if kind == "market":
        return [f"{band} RG 2 w {inner_x:.1f} {inner_y:.1f} {inner_w:.1f} {inner_h:.1f} re S\n"]
    return [
        f"{band} RG 2.2 w {inner_x + 36:.1f} {inner_y + 34:.1f} 86 86 re S\n",
        f"{accent} RG 2 w {inner_x + 14:.1f} {inner_y + 12:.1f} m {inner_x + inner_w - 12:.1f} {inner_y + inner_h - 12:.1f} l S\n",
        f"{band} rg {inner_x + 76:.1f} {inner_y + 76:.1f} 28 28 re f\n",
    ]
