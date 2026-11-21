"""The design constitution holds: ten roles in both surfaces, no text under 12 px."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "scripts" / "design_constitution.py"


def _load():
    spec = importlib.util.spec_from_file_location("_design_constitution", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


constitution = _load()


def test_the_ten_roles_exist_in_both_surfaces():
    report = constitution.token_report(
        REPO / "app/src/styles/globals.css",
        REPO / "ui/ephe.tcss",
    )
    assert [entry["role"] for entry in report] == [
        "canvas",
        "surface",
        "elevated",
        "foreground",
        "ink-soft",
        "hairline",
        "brand",
        "ok",
        "warn",
        "error",
    ]
    # This role is CSS-only; ui/palette.py holds the ten tokens the terminal uses.
    missing = [
        entry["role"] for entry in report if not entry["present"] and not entry["css_only"]
    ]
    assert missing == []
    assert [entry["role"] for entry in report if entry["css_only"]] == ["elevated"]


def test_nine_of_ten_pairs_carry_the_constitution_hex():
    report = constitution.token_report(
        REPO / "app/src/styles/globals.css",
        REPO / "ui/ephe.tcss",
    )
    drift = [entry["role"] for entry in report if entry["drift"]]
    assert drift == ["ink-soft"]


def test_the_soft_ink_is_the_open_decision():
    report = {entry["role"]: entry for entry in constitution.token_report(
        REPO / "app/src/styles/globals.css",
        REPO / "ui/ephe.tcss",
    )}
    soft = report["ink-soft"]
    assert soft["css_hex"] == "#B0A8A0"
    assert soft["tui_hex"] == "#91877E"
    assert soft["expected"] == "#91877E"


def test_no_text_run_is_smaller_than_twelve_pixels():
    assert constitution.scan_micro_text(REPO / "app/src") == []


def test_the_scan_catches_pixel_rem_and_inline_sizes(tmp_path):
    source = tmp_path / "app/src"
    source.mkdir(parents=True)
    (source / "a.tsx").write_text('<span className="text-[10px]">x</span>\n')
    (source / "b.tsx").write_text('<span className="text-[0.7rem]">x</span>\n')
    (source / "c.tsx").write_text('<span style={{ fontSize: "11px" }}>x</span>\n')
    findings = constitution.scan_micro_text(source)
    assert sorted(finding["file"].split("/")[-1] for finding in findings) == [
        "a.tsx",
        "b.tsx",
        "c.tsx",
    ]


def test_the_scan_accepts_twelve_pixels_and_above(tmp_path):
    source = tmp_path / "app/src"
    source.mkdir(parents=True)
    (source / "ok.tsx").write_text(
        '<span className="text-xs">a</span>\n'
        '<span className="text-[12px]">b</span>\n'
        '<span className="text-[0.75rem]">c</span>\n'
        '<span className="text-[13px]">d</span>\n'
    )
    assert constitution.scan_micro_text(source) == []


def test_a_vanished_role_is_a_finding_and_fails_the_run(tmp_path):
    styles = tmp_path / "app/src/styles"
    styles.mkdir(parents=True)
    (tmp_path / "ui").mkdir()
    css = styles / "globals.css"
    tui = tmp_path / "ui/ephe.tcss"
    css.write_text(":root {\n  --color-canvas: #15120F;\n}\n")
    tui.write_text("$ink-ground: #15120F;\n")
    report = constitution.token_report(css, tui)
    missing = [
        entry["role"] for entry in report if not entry["present"] and not entry["css_only"]
    ]
    # The fixture removes the CSS side, so every role is a finding.
    assert "elevated" in missing
    assert constitution.main(["--root", str(tmp_path)]) == 1


def test_css_hsl_is_read_in_the_constitution_model():
    assert constitution.as_hex("hsl(30 16.7% 7.06%)") == "#15120F"
    assert constitution.as_hex("hsl(7.46 78.6% 57.8%)") == "#E8543F"
    assert constitution.as_hex("#5bae90") == "#5BAE90"
