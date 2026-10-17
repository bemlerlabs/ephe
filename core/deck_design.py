"""Deck Engine v2 visual language and role metadata."""
from __future__ import annotations


ENTERPRISE_DECK_PROFILES = {
    "engineering-platform",
    "product-platform",
    "gtm-growth",
    "strategy-leadership",
    "finance-ir",
}

ENTERPRISE_DESIGN_THEMES = {"evergreen", "executive", "studio"}


THEMES = {
    "executive": {
        "paper": "0.980 0.980 0.965",
        "ink": "0.055 0.090 0.140",
        "muted": "0.330 0.360 0.390",
        "band": "0.055 0.090 0.140",
        "accent": "0.086 0.639 0.290",
        "soft": "0.930 0.940 0.930",
        "line": "0.790 0.830 0.805",
        "warn": "0.780 0.350 0.030",
    },
    "studio": {
        "paper": "0.990 0.985 0.972",
        "ink": "0.080 0.090 0.110",
        "muted": "0.320 0.360 0.410",
        "band": "0.035 0.569 0.698",
        "accent": "0.086 0.639 0.290",
        "soft": "0.925 0.965 0.972",
        "line": "0.780 0.850 0.860",
        "warn": "0.820 0.420 0.050",
    },
    "evergreen": {
        "paper": "0.984 0.988 0.984",
        "ink": "0.060 0.090 0.130",
        "muted": "0.320 0.380 0.440",
        "band": "0.086 0.639 0.290",
        "accent": "0.035 0.569 0.698",
        "soft": "0.928 0.972 0.941",
        "line": "0.790 0.880 0.830",
        "warn": "0.850 0.467 0.024",
    },
}


ROLE_LABELS = {
    "cover": "Decision Thesis",
    "executive_summary": "Executive Summary",
    "problem": "Constraint Map",
    "market_map": "Market Map",
    "metric": "Metric View",
    "architecture": "Architecture",
    "workflow": "Workflow",
    "comparison_matrix": "Decision Matrix",
    "roadmap": "Roadmap",
    "risk_controls": "Risk Controls",
    "ask": "Decision Ask",
    "appendix_sources": "Sources",
}


def theme_palette(design_theme: str) -> dict[str, str]:
    return THEMES.get((design_theme or "executive").lower(), THEMES["executive"])


def normalize_theme(design_theme: str, enterprise_grade: bool = True) -> str:
    theme = (design_theme or "executive").lower()
    if theme not in ENTERPRISE_DESIGN_THEMES:
        return "executive"
    if enterprise_grade and theme == "evergreen":
        return "executive"
    return theme


def normalize_profile(deck_profile: str) -> str:
    profile = (deck_profile or "strategy-leadership").lower()
    return profile if profile in ENTERPRISE_DECK_PROFILES else "strategy-leadership"


def normalize_brand_kit(brand_name: str = "", brand_primary: str = "", brand_secondary: str = "") -> dict[str, str]:
    def clean_hex(value: str) -> str:
        text = str(value or "").strip().lstrip("#")
        return text.upper() if len(text) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in text) else ""

    return {
        "brand_name": str(brand_name or "").strip()[:80],
        "primary": clean_hex(brand_primary),
        "secondary": clean_hex(brand_secondary),
    }
