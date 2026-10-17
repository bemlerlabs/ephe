"""The packaging ratchet and the manifest renderer, on planted trees and on the real one.

Both instruments are path-bound: `scripts/packaging_freshness.py` takes `--root` and
`scripts/render_packaging.py` takes `--root` and `--outdir`, so a plant is a directory in
`tmp_path` and the repository's own surface is only read. The ratchet reaches the network only
when neither `--release` nor `--offline` is given, so these tests drive the offline path and the
explicit version; the live feed is deliberately not a test dependency, the way
`tests/test_ci_action_pins.py` keeps resolution out of the suite.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RATCHET = ROOT / "scripts" / "packaging_freshness.py"
RENDERER = ROOT / "scripts" / "render_packaging.py"
NOTES = ROOT / "scripts" / "release_notes.py"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def plant_tree(root: Path, *, release: str = "1.2.3", cask: str = "1.2.3",
               scoop: str = "1.2.3", npm: str = "1.2.3") -> Path:
    """The five files the ratchet reads: three manifests and the three version carriers."""
    write(root / "pyproject.toml", f'[project]\nname = "ephe"\nversion = "{release}"\n')
    write(root / "app" / "package.json", json.dumps({"version": release}) + "\n")
    write(root / "app" / "src-tauri" / "tauri.conf.json", json.dumps({"version": release}) + "\n")
    write(root / "packaging" / "homebrew" / "ephe.rb",
          f'cask "ephe" do\n  version "{cask}"\n  sha256 "{"0" * 64}"\nend\n')
    write(root / "packaging" / "scoop" / "ephe.json", json.dumps({
        "version": scoop,
        "url": f"https://github.com/bemlerlabs/ephe/archive/refs/tags/v{scoop}.zip",
        "hash": "0" * 64,
        "extract_dir": f"ephe-{scoop}",
    }) + "\n")
    write(root / "packaging" / "npm" / "package.json", json.dumps({"version": npm}) + "\n")
    return root


def run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(script), *args], text=True,
                          capture_output=True, check=False, cwd=ROOT)


class TestRatchetOnAPlant:
    def test_three_manifests_agreeing_with_the_carriers_pass(self, tmp_path):
        done = run(RATCHET, "--root", str(plant_tree(tmp_path)), "--offline")
        assert done.returncode == 0, done.stdout + done.stderr
        assert "PASS" in done.stdout and "3 manifest(s)" in done.stdout, done.stdout

    def test_a_stale_manifest_names_the_surface_and_the_two_versions(self, tmp_path):
        done = run(RATCHET, "--root", str(plant_tree(tmp_path, cask="1.2.4")), "--offline")
        assert done.returncode == 1, done.stdout
        assert "STALE cask 1.2.4 vs release 1.2.3" in done.stdout, done.stdout

    def test_a_named_release_outranks_the_tree_carriers(self, tmp_path):
        done = run(RATCHET, "--root", str(plant_tree(tmp_path)), "--release", "1.2.5")
        assert done.returncode == 1, done.stdout
        assert "vs release 1.2.5" in done.stdout, done.stdout

    def test_carriers_that_disagree_are_a_reference_the_check_declines(self, tmp_path):
        root = plant_tree(tmp_path)
        write(root / "app" / "package.json", json.dumps({"version": "9.9.9"}) + "\n")
        done = run(RATCHET, "--root", str(root), "--offline")
        assert done.returncode == 2, done.stdout
        assert "disagree" in done.stdout, done.stdout

    def test_a_manifest_that_cannot_be_read_is_not_a_silent_pass(self, tmp_path):
        root = plant_tree(tmp_path)
        (root / "packaging" / "npm" / "package.json").unlink()
        done = run(RATCHET, "--root", str(root), "--offline")
        assert done.returncode == 2, done.stdout
        assert "cannot decide" in done.stdout, done.stdout


class TestRatchetOnTheRepository:
    def test_the_shipped_manifests_agree_with_the_tree_carriers_offline(self):
        done = run(RATCHET, "--offline")
        assert done.returncode == 0, done.stdout + done.stderr
        assert "the tree carriers" in done.stdout, done.stdout


class TestRendererOnTheRepository:
    def current_values(self) -> tuple[str, str, str]:
        cask_text = (ROOT / "packaging" / "homebrew" / "ephe.rb").read_text(encoding="utf-8")
        scoop_text = (ROOT / "packaging" / "scoop" / "ephe.json").read_text(encoding="utf-8")
        dmg_sha = re.search(r'sha256 "([0-9a-f]{64})"', cask_text)
        assert dmg_sha is not None, cask_text
        return json.loads(scoop_text)["version"], dmg_sha.group(1), json.loads(scoop_text)["hash"]

    def test_rendering_the_current_values_reproduces_both_templates(self, tmp_path):
        version, dmg_sha, source_sha = self.current_values()
        done = run(RENDERER, "--version", version, "--dmg-sha256", dmg_sha,
                   "--source-sha256", source_sha, "--outdir", str(tmp_path))
        assert done.returncode == 0, done.stdout + done.stderr
        assert (tmp_path / "ephe.rb").read_text(encoding="utf-8") \
            == (ROOT / "packaging" / "homebrew" / "ephe.rb").read_text(encoding="utf-8")
        assert (tmp_path / "ephe.json").read_text(encoding="utf-8") \
            == (ROOT / "packaging" / "scoop" / "ephe.json").read_text(encoding="utf-8")

    def test_a_new_version_reaches_every_field_that_carries_one(self, tmp_path):
        _, dmg_sha, source_sha = self.current_values()
        done = run(RENDERER, "--version", "0.1.0-beta.4", "--dmg-sha256", dmg_sha,
                   "--source-sha256", source_sha, "--outdir", str(tmp_path))
        assert done.returncode == 0, done.stdout + done.stderr
        cask = (tmp_path / "ephe.rb").read_text(encoding="utf-8")
        scoop = json.loads((tmp_path / "ephe.json").read_text(encoding="utf-8"))
        assert 'version "0.1.0-beta.4"' in cask, cask
        assert scoop["version"] == "0.1.0-beta.4"
        assert scoop["url"].endswith("v0.1.0-beta.4.zip")
        assert scoop["extract_dir"] == "ephe-0.1.0-beta.4"
        assert "v0.1.0-beta.4" in scoop["notes"]

    def test_a_hash_that_is_not_a_sha256_is_refused(self, tmp_path):
        version, dmg_sha, source_sha = self.current_values()
        done = run(RENDERER, "--version", version, "--dmg-sha256", "not-a-hash",
                   "--source-sha256", source_sha, "--outdir", str(tmp_path))
        assert done.returncode == 1, done.stdout
        assert "not a lowercase 64-character sha256" in done.stdout, done.stdout


class TestReleaseNotes:
    def test_the_block_of_a_published_version_is_printed(self):
        done = run(NOTES, "0.1.0-beta.3")
        assert done.returncode == 0, done.stdout + done.stderr
        assert "### Security" in done.stdout, done.stdout

    def test_a_version_with_no_block_is_refused(self):
        done = run(NOTES, "9.9.9")
        assert done.returncode == 2, done.stdout
        assert "no `## [9.9.9]` section" in done.stderr, done.stderr
