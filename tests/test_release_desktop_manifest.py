"""The updater manifest names the artifact the bundle actually writes.

`release_desktop.sh` named `Ephe.app.tar.gz` in the feed URL, the signature
check and both upload paths, while the Tauri bundle writes
`Ephe_aarch64.app.tar.gz` — the name the v0.1.11 release carries. A feed that
points at a name no release has answers 404, so the updater reports "check not
possible" on a machine where everything else is healthy. The script now reads
the name from the build; these lines keep it from drifting back.
"""
from __future__ import annotations

from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release_desktop.sh"


def test_feed_url_uses_the_artifact_name_the_build_wrote():
    src = SCRIPT.read_text(encoding="utf-8")
    assert "-name '*.app.tar.gz'" in src, "the artifact is found, not assumed"
    assert "download/v${version}/${assetName}" in src
    assert "download/v${version}/Ephe.app.tar.gz" not in src


def test_signature_and_upload_paths_follow_the_same_artifact():
    src = SCRIPT.read_text(encoding="utf-8")
    assert 'SIG="${ARTIFACT}.sig"' in src
    assert "macos/Ephe.app.tar.gz" not in src
