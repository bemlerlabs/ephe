#!/usr/bin/env python3
"""The design constitution, as a check instead of a paragraph.

Two things the product may not drift on: no text run below 12 px, and the ten
semantic colours existing in both surfaces under the same role. The colour part
reports presence as a verdict and value drift as a measurement, because a token
that moved is a decision for the owner, while a token that vanished is a bug in
the surface.

    python scripts/design_constitution.py           # verdict, exit 1 on findings
    python scripts/design_constitution.py --json    # the report as JSON
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: (constitution name, CSS custom property, Textual variable, expected hex)
TOKENS: tuple[tuple[str, str, str, str], ...] = (
    ("canvas", "--color-canvas", "$ink-ground", "#15120F"),
    ("surface", "--color-surface", "$ink-panel", "#1D1917"),
    ("elevated", "--color-elevated", "$ink-elevated", "#25201D"),
    ("foreground", "--color-ink", "$ink-text", "#F2EFE8"),
    ("ink-soft", "--color-ink-soft", "$ink-dim", "#91877E"),
    ("hairline", "--color-hairline", "$ink-line", "#2E2926"),
    ("brand", "--color-brand", "$ink-accent", "#E8543F"),
    ("ok", "--color-ok", "$ink-ok", "#5BAE90"),
    ("warn", "--color-warn", "$ink-warn", "#F6A328"),
    ("error", "--color-error", "$ink-error", "#F63B1E"),
)

MICRO_PX = re.compile(r"text-\[(\d+(?:\.\d+)?)px\]")
MICRO_REM = re.compile(r"text-\[(0?\.\d+)rem\]")
INLINE_PX = re.compile(r"font-?[sS]ize\s*[:=]\s*['\"]([0-9.]+)px['\"]")
CSS_VAR = re.compile(r"(--color-[a-z0-9-]+)\s*:\s*([^;]+);")
TUI_VAR = re.compile(r"^(\$ink-[a-z0-9-]+)\s*:\s*([^;]+);", re.MULTILINE)
CSS_HSL = re.compile(r"hsl\(\s*([0-9.]+)\s+([0-9.]+)%\s+([0-9.]+)%\s*\)")


def hsl_to_hex(text: str) -> str | None:
    match = CSS_HSL.search(text)
    if not match:
        return None
    hue, sat, light = (float(value) for value in match.groups())
    hue %= 360
    sat /= 100
    light /= 100
    chroma = (1 - abs(2 * light - 1)) * sat
    second = chroma * (1 - abs((hue / 60) % 2 - 1))
    match_light = light - chroma / 2
    red, green, blue = (
        (chroma, second, 0.0),
        (second, chroma, 0.0),
        (0.0, chroma, second),
        (0.0, second, chroma),
        (second, 0.0, chroma),
        (chroma, 0.0, second),
    )[int(hue // 60) % 6]
    return "#%02X%02X%02X" % (
        round((red + match_light) * 255),
        round((green + match_light) * 255),
        round((blue + match_light) * 255),
    )


def as_hex(value: str) -> str | None:
    text = value.strip()
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", text):
        return text.upper()
    return hsl_to_hex(text)


def read_vars(path: Path, pattern: re.Pattern[str]) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    found: dict[str, str] = {}
    for name, value in pattern.findall(text):
        found.setdefault(name, value.strip())
    return found


def resolve(name: str, values: dict[str, str], depth: int = 0) -> str | None:
    value = values.get(name)
    if value is None or depth > 4:
        return None
    alias = re.fullmatch(r"var\((--[a-z0-9-]+)\)", value)
    if alias:
        return resolve(alias.group(1), values, depth + 1)
    return as_hex(value)


def token_report(css_path: Path, tui_path: Path) -> list[dict[str, object]]:
    css = read_vars(css_path, CSS_VAR)
    tui = read_vars(tui_path, TUI_VAR)
    report: list[dict[str, object]] = []
    for role, css_name, tui_name, expected in TOKENS:
        css_hex = resolve(css_name, css)
        tui_hex = resolve(tui_name, tui)
        report.append(
            {
                "role": role,
                "css": css_name,
                "tui": tui_name,
                "expected": expected,
                "css_hex": css_hex,
                "tui_hex": tui_hex,
                "present": css_hex is not None and tui_hex is not None,
                "drift": [
                    surface
                    for surface, hex_value in (("css", css_hex), ("tui", tui_hex))
                    if hex_value is not None and hex_value != expected
                ],
            }
        )
    return report


def scan_micro_text(source_root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path in sorted(source_root.rglob("*")):
        if path.suffix not in {".tsx", ".ts", ".css"} or path.name.endswith(".test.ts"):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(lines, 1):
            for match in MICRO_PX.finditer(line):
                if float(match.group(1)) < 12:
                    findings.append(_finding(path, number, line, match.group(0)))
            for match in MICRO_REM.finditer(line):
                if float(match.group(1)) * 16 < 12:
                    findings.append(_finding(path, number, line, match.group(0)))
            for match in INLINE_PX.finditer(line):
                if float(match.group(1)) < 12:
                    findings.append(_finding(path, number, line, match.group(0)))
    return findings


def _finding(path: Path, number: int, line: str, token: str) -> dict[str, object]:
    return {
        "file": str(path),
        "line": number,
        "token": token,
        "text": line.strip()[:160],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    report = token_report(
        args.root / "app/src/styles/globals.css",
        args.root / "ui/ephe.tcss",
    )
    micro = scan_micro_text(args.root / "app/src")
    missing = [entry["role"] for entry in report if not entry["present"]]
    drift = [entry["role"] for entry in report if entry["drift"]]

    if args.json:
        json.dump({"tokens": report, "micro_text": micro}, sys.stdout, indent=2)
        print()
    else:
        print(f"design constitution — {args.root}")
        for entry in report:
            mark = "ok  " if entry["present"] else "MISS"
            drift_note = f" drift: {', '.join(entry['drift'])}" if entry["drift"] else ""
            print(
                f"  {mark} {entry['role']:<10} {entry['css']:<18} {entry['tui']:<15}"
                f" {entry['css_hex'] or '-':>7} {entry['tui_hex'] or '-':>8}"
                f" (expected {entry['expected']}){drift_note}"
            )
        for finding in micro:
            print(f"  MICRO {finding['file']}:{finding['line']} {finding['token']}")
        if drift:
            print(f"  drift is a measurement for the owner: {', '.join(drift)}")
        print(f"  micro-text findings: {len(micro)}")

    if missing or micro:
        if missing:
            print(f"  missing tokens: {', '.join(missing)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
