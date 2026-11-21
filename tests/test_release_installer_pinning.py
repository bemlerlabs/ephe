"""A release install checks out the tag its installer URL names.

The documented one-liner fetched `install.sh` from `v0.6.8` and the installer then cloned
`main`, so a release user ran untagged code behind a shell that believed it was on the
release. The installer now accepts `--tag` / `EPHE_REF` (and `install.ps1 -Ref`), fetches
the tag and checks it out detached; the README and the install documents pass the same tag.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SH = ROOT / "install.sh"
PS1 = ROOT / "install.ps1"


def test_the_bash_installer_takes_a_ref_and_checks_it_out():
    text = SH.read_text(encoding="utf-8")
    assert "REF=\"${EPHE_REF:-}\"" in text
    assert "--tag|--ref" in text
    assert "clone_checkout" in text
    assert 'checkout --detach "$REF"' in text
    assert "EPHE_REF" in text


def test_the_powershell_installer_takes_the_same_ref_and_reenters_with_it():
    text = PS1.read_text(encoding="utf-8")
    assert "[string]$Ref" in text
    assert "$env:EPHE_REF" in text
    assert "checkout --detach $Ref" in text
    assert "-Ref $Ref" in text, "the re-entry drops the ref and installs the branch tip"


def test_an_invalid_ref_is_refused_before_git_runs(tmp_path):
    done = subprocess.run(
        ["bash", str(SH), "--dry-run", "--tag", "bad ref"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "EPHE_INSTALL_DIR": str(tmp_path / "install")},
    )
    assert done.returncode == 2, done.stdout + done.stderr
    assert "must be a git ref name" in done.stdout + done.stderr


def test_a_dry_run_reports_the_clone_and_the_tag_checkout(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    git = ["git", "-C", str(source)]
    subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
    (source / "README.md").write_text("release\n", encoding="utf-8")
    subprocess.run([*git, "add", "README.md"], check=True)
    subprocess.run(
        [*git, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "a"],
        check=True,
    )
    subprocess.run([*git, "tag", "v1.2.3"], check=True)

    done = subprocess.run(
        ["bash", str(SH), "--dry-run", "--tag", "v1.2.3"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={
            **os.environ,
            "EPHE_REPO_URL": str(source),
            "EPHE_INSTALL_DIR": str(tmp_path / "install"),
            "EPHE_DRY_RUN": "1",
        },
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "git clone" in done.stdout
    assert 'checkout --detach v1.2.3' in done.stdout


def test_the_install_documents_pass_the_tag():
    from scripts.version_carriers import read_versions

    tag = f"v{next(iter(read_versions(ROOT).values()))}"
    for name in (
        "README.md",
        "README.es.md",
        "README.zh-CN.md",
        "docs/INSTALL.md",
        "docs/INSTALL_OPTIONS.md",
        "docs/QUICKSTART.md",
        "docs/FIRST_RUN.md",
    ):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert f"--tag {tag}" in text or f"-Ref {tag}" in text, f"{name} names no release ref"
