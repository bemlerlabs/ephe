"""A packaging template carries a sentinel, never a hash nobody measured.

`packaging/scoop/ephe.json` claimed a hash "measured from the v0.6.8 source archive" that was
not that archive's hash, and `scripts/packaging_freshness.py` compared only version strings, so
the claim stayed green until a bucket copy carried it. The template now names a sentinel, the
offline gate refuses any other unmeasured hash, and the publish job checks both measured hashes
against the templates before it renders them.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts" / "packaging_freshness.py"
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
SENTINEL = "0" * 64
REAL = "a" * 64
OTHER = "b" * 64


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def plant(root: Path, *, cask_sha: str = SENTINEL, scoop_sha: str = SENTINEL) -> Path:
    version = "1.2.3"
    write(root / "pyproject.toml", f'[project]\nname = "ephe"\nversion = "{version}"\n')
    write(root / "app" / "package.json", json.dumps({"version": version}) + "\n")
    write(root / "app" / "src-tauri" / "tauri.conf.json", json.dumps({"version": version}) + "\n")
    write(
        root / "packaging" / "homebrew" / "ephe.rb",
        f'cask "ephe" do\n  version "{version}"\n  sha256 "{cask_sha}"\nend\n',
    )
    write(
        root / "packaging" / "scoop" / "ephe.json",
        json.dumps(
            {
                "version": version,
                "url": f"https://github.com/bemlerlabs/ephe/archive/refs/tags/v{version}.zip",
                "hash": scoop_sha,
                "extract_dir": f"ephe-{version}",
            }
        )
        + "\n",
    )
    write(root / "packaging" / "npm" / "package.json", json.dumps({"version": version}) + "\n")
    return root


def run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE), "--root", str(root), "--offline", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_committed_templates_carry_the_sentinel():
    scoop = json.loads((ROOT / "packaging" / "scoop" / "ephe.json").read_text(encoding="utf-8"))
    cask = (ROOT / "packaging" / "homebrew" / "ephe.rb").read_text(encoding="utf-8")
    assert scoop["hash"] == SENTINEL
    assert re.search(rf'sha256 "{SENTINEL}"', cask)
    assert "measured from the v0.6.8 source archive" not in json.dumps(scoop)


def test_a_planted_sentinel_passes_offline(tmp_path):
    done = run(plant(tmp_path))
    assert done.returncode == 0, done.stdout + done.stderr
    assert "template sentinel" in done.stdout


def test_an_unmeasured_hash_is_refused_offline(tmp_path):
    done = run(plant(tmp_path, scoop_sha=REAL))
    assert done.returncode == 1, done.stdout
    assert "no run measured" in done.stdout


def test_a_measured_hash_that_matches_passes(tmp_path):
    done = run(plant(tmp_path, scoop_sha=REAL), "--source-sha256", REAL)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "matches the measured source archive" in done.stdout


def test_a_measured_hash_that_differs_is_refused(tmp_path):
    done = run(plant(tmp_path, scoop_sha=REAL), "--source-sha256", OTHER)
    assert done.returncode == 1, done.stdout
    assert "the source archive measures" in done.stdout


def test_a_malformed_measured_hash_is_a_usage_error(tmp_path):
    done = run(plant(tmp_path), "--source-sha256", "not-a-hash")
    assert done.returncode == 2, done.stdout
    assert "not a lowercase 64-character sha256" in done.stdout


def test_the_publish_job_checks_both_measured_hashes_before_rendering():
    doc = yaml.safe_load(RELEASE.read_text(encoding="utf-8")) or {}
    steps = (doc.get("jobs") or {})["publish-packages"]["steps"]
    runs = [str(step.get("run", "")) for step in steps]
    gate = next((text for text in runs if "packaging_freshness.py" in text), "")
    assert gate, "publish-packages does not run the hash gate"
    assert "--dmg-sha256" in gate and "--source-sha256" in gate
    render = next(index for index, text in enumerate(runs) if "render_packaging.py" in text)
    gate_index = next(index for index, text in enumerate(runs) if "packaging_freshness.py" in text)
    assert gate_index < render, "the templates are rendered before their hashes are checked"
