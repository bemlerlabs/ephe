"""The shipped-asset and catalog checks, exercised against planted trees.

Both instruments are path-bound: `scripts/asset_check.py` takes `--root` and
`scripts/catalog_freshness.py` takes `--root` for the knowledge-index half, so a plant is a directory in
`tmp_path` and the repository's own surface is only ever read. The generators the catalog leg calls run
against the real tree, and their red branches were proven by hand before this file existed -- a byte
appended to `skills/api-designer/SKILL.md` answers `skills_lock_mismatch pack=api-designer`, and one new
file under `plugins/browser-use/` moves that pack's sha256 -- then restored; the tests below keep the
parts that must not touch tracked content.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PWA_NAMES = ("favicon.png", "icon-192.png", "icon-512.png", "icon-maskable-192.png",
             "icon-maskable-512.png", "apple-touch-icon-180.png")


def png(path: Path, colour: tuple[int, int, int, int], size: int = 64) -> None:
    from PIL import Image

    image = Image.new("RGBA", (size, size), colour)
    image.save(path)


def checkerboard(path: Path, size: int = 64) -> None:
    """A two-tone asset: maximum contrast at any resample, so the floor cannot refuse it."""
    from PIL import Image

    image = Image.new("RGBA", (size, size), (0, 0, 0, 255))
    for x in range(0, size, 8):
        for y in range(0, size, 8):
            if (x // 8 + y // 8) % 2:
                for px in range(x, min(x + 8, size)):
                    for py in range(y, min(y + 8, size)):
                        image.putpixel((px, py), (255, 255, 255, 255))
    image.save(path)


def plant_surface(root: Path, *, mark: str = "checker") -> Path:
    public = root / "app" / "public"
    icons = root / "app" / "src-tauri" / "icons"
    public.mkdir(parents=True, exist_ok=True)
    icons.mkdir(parents=True, exist_ok=True)
    for name in PWA_NAMES:
        if mark == "checker":
            checkerboard(public / name)
        else:
            png(public / name, (128, 128, 128, 255))
    checkerboard(icons / "icon.png")
    (public / "favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"></svg>\n', encoding="utf-8")
    checkerboard(public / "screenshot-1080.png")
    (public / "manifest.json").write_text(json.dumps({
        "name": "Ephe", "icons": [{"src": name, "sizes": "192x192", "type": "image/png"}
                                  for name in PWA_NAMES if name.endswith("png")],
        "screenshots": [{"src": "screenshot-1080.png", "sizes": "1080x1920"}],
    }, indent=2) + "\n", encoding="utf-8")
    (root / "app" / "index.html").write_text(
        "<html><head><link rel=\"icon\" href=\"/favicon.svg\">"
        "<link rel=\"manifest\" href=\"/manifest.json\">"
        "<script type=\"module\" src=\"/src/main.tsx\"></script></head><body></body></html>\n",
        encoding="utf-8",
    )
    (root / "app" / "src").mkdir(parents=True, exist_ok=True)
    (root / "app" / "src" / "main.tsx").write_text("export {}\n", encoding="utf-8")
    return root


def run_asset_check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "asset_check.py"), "--root", str(root), "--quiet"],
        text=True, capture_output=True, check=False, cwd=ROOT,
    )


class TestAssetCheckOnItsOwnFixture:
    def test_a_planted_surface_with_contrast_and_resolving_references_passes(self, tmp_path):
        done = run_asset_check(plant_surface(tmp_path))
        assert done.returncode == 0, done.stdout + done.stderr
        assert "0 problem(s)" in done.stdout, done.stdout

    def test_a_flat_asset_is_refused_as_washed_out(self, tmp_path):
        done = run_asset_check(plant_surface(tmp_path, mark="flat"))
        assert done.returncode == 1, done.stdout
        assert "luminance spread 0.0" in done.stdout, done.stdout

    def test_a_reference_to_a_missing_file_names_its_referrer(self, tmp_path):
        """A screenshot, not an icon: a PWA-set icon missing from disk is refused earlier and louder,
        as `test_a_moved_icon_set_is_a_refusal_rather_than_a_green_of_zero_assets` shows.
        """
        root = plant_surface(tmp_path)
        (root / "app" / "public" / "screenshot-1080.png").unlink()
        done = run_asset_check(root)
        assert done.returncode == 1, done.stdout
        assert "app/public/manifest.json: references screenshot-1080.png" in done.stdout, done.stdout

    def test_a_png_with_the_wrong_header_is_refused_by_name(self, tmp_path):
        root = plant_surface(tmp_path)
        (root / "app" / "public" / "favicon.png").write_bytes(b"GIF89a not a png")
        done = run_asset_check(root)
        assert done.returncode == 1, done.stdout
        assert "does not start with the .png magic bytes" in done.stdout, done.stdout
        assert "does not decode as an image" in done.stdout, done.stdout

    def test_an_svg_without_a_view_box_is_refused(self, tmp_path):
        root = plant_surface(tmp_path)
        (root / "app" / "public" / "favicon.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"></svg>\n', encoding="utf-8")
        done = run_asset_check(root)
        assert done.returncode == 1, done.stdout
        assert "no viewBox" in done.stdout, done.stdout

    def test_a_moved_icon_set_is_a_refusal_rather_than_a_green_of_zero_assets(self, tmp_path):
        root = tmp_path / "empty"
        (root / "app" / "public").mkdir(parents=True)
        done = run_asset_check(root)
        assert done.returncode == 2, done.stdout + done.stderr
        assert "the PWA icon set moved or vanished" in done.stdout, done.stdout


class TestAssetCheckOnTheRepository:
    def test_the_shipped_surface_is_clean_and_weakest_far_above_the_floor(self):
        done = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "asset_check.py")],
            text=True, capture_output=True, check=False, cwd=ROOT,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        assert "0 problem(s)" in done.stdout, done.stdout
        # Measured 2026-10-11: 20 rasters, the weakest at spread 180.9 against a floor of 20.0.
        assert "20 raster asset(s)" in done.stdout, done.stdout
        assert "weakest at 16 px" in done.stdout, done.stdout


class TestKnowledgeIndexDrift:
    def knowledge(self, root: Path, domains: list[str], total_files: int | None) -> Path:
        base = root / "knowledge"
        for name in domains:
            (base / name).mkdir(parents=True, exist_ok=True)
            (base / name / "a.md").write_text("# x\n", encoding="utf-8")
        stats = {"totalFiles": total_files} if total_files is not None else {}
        (base / "index.json").write_text(json.dumps({
            "version": "1.0", "domains": [{"id": name} for name in domains], "stats": stats,
        }, indent=2) + "\n", encoding="utf-8")
        return base

    def test_a_matching_index_reports_no_drift(self, tmp_path):
        self.knowledge(tmp_path, ["medical", "survival"], total_files=2)
        # A directory on disk that the index names, and a count that matches: nothing to say.
        module = load_catalog_module()
        assert module.knowledge_drift(tmp_path) == []

    def test_both_directions_of_drift_are_named(self, tmp_path):
        base = self.knowledge(tmp_path, ["medical"], total_files=9)
        (base / "navigation").mkdir()
        (base / "navigation" / "b.md").write_text("# y\n", encoding="utf-8")
        module = load_catalog_module()
        problems = module.knowledge_drift(tmp_path)
        assert any("navigation/ exists on disk and no domain" in p for p in problems), problems
        assert any("totalFiles says 9" in p for p in problems), problems

    def test_a_domain_declared_without_a_directory_is_a_finding(self, tmp_path):
        self.knowledge(tmp_path, ["medical"], total_files=1)
        index = tmp_path / "knowledge" / "index.json"
        data = json.loads(index.read_text(encoding="utf-8"))
        data["domains"].append({"id": "phantom"})
        data["stats"]["totalFiles"] = 1
        index.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        module = load_catalog_module()
        problems = module.knowledge_drift(tmp_path)
        assert any("declares domain phantom" in p for p in problems), problems


def load_catalog_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "catalog_freshness", ROOT / "scripts" / "catalog_freshness.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class TestCatalogLegOnTheRepository:
    def test_both_committed_catalogs_are_fresh(self):
        done = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "catalog_freshness.py")],
            text=True, capture_output=True, check=False, cwd=ROOT,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        assert "fresh" in done.stdout, done.stdout

    def test_the_knowledge_findings_are_reported_without_gating(self):
        """The index drift is a live defect in another lane's surface, so it prints and stays out of
        `GATED` until that lane closes it."""
        module = load_catalog_module()
        assert "knowledge/index.json" not in module.GATED
        done = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "catalog_freshness.py")],
            text=True, capture_output=True, check=False, cwd=ROOT,
        )
        findings = [line for line in done.stdout.splitlines() if "knowledge/index.json:" in line]
        assert findings, done.stdout
