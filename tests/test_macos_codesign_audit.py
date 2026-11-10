"""The macOS bundle seal: what it says, and the release that has to produce it.

Issue #192 measured the shipped app: `codesign -dv` reported
`flags=0x20002(adhoc,linker-signed)`, `Info.plist=not bound` and `Sealed Resources=none`,
so `codesign --verify --strict` exited 1 with "code has no resources but signature
indicates they must be present", `spctl` rejected the app, and no notarization ticket
existed. Two halves are pinned here:

* `scripts/macos_sign_audit.sh` reads a bundle and reports the four answers. The tests
  below run it for real against bundles this test builds in `tmp_path` — an unsigned one
  (the reported failure shape) and an ad-hoc signed one — because a string assertion
  cannot tell whether `codesign --verify` passes. On a host without `codesign` they are
  skipped with that reason.
* `release.yml` carries both documented outcomes: the Developer ID plus notarization
  path when the Apple secrets exist, and the ad-hoc identity (`signingIdentity: "-"`)
  when they do not. The ad-hoc path is what makes `codesign --verify --deep --strict`
  pass on a locally built or unsigned release bundle.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "macos_sign_audit.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"

HAVE_CODESIGN = sys.platform == "darwin" and shutil.which("codesign") is not None
DARWIN = pytest.mark.skipif(
    not HAVE_CODESIGN,
    reason="reading a macOS bundle seal needs Darwin and codesign, and this host has neither",
)

PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key><string>com.ephe.probe</string>
  <key>CFBundleExecutable</key><string>app</string>
  <key>CFBundleName</key><string>probe</string>
  <key>CFBundleShortVersionString</key><string>0.0.0</string>
</dict>
</plist>
"""


def build_bundle(tmp_path: Path, *, sign: bool) -> Path:
    """An `.app` shaped like the product's: a real Mach-O plus Info.plist and a resource.

    The executable is copied rather than compiled so the test needs no toolchain. Copied
    as-is it carries the signature `/bin` was shipped with, which is the shape the issue
    measured: a bundle whose inner signature claims more than the bundle seals.
    """
    app = tmp_path / "Ephe.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "Resources").mkdir()
    shutil.copy(shutil.which("echo") or "/bin/echo", app / "Contents" / "MacOS" / "app")
    (app / "Contents" / "Info.plist").write_text(PLIST, encoding="utf-8")
    (app / "Contents" / "Resources" / "LICENSE").write_text("BUSL-1.1\n", encoding="utf-8")
    if sign:
        done = subprocess.run(
            ["codesign", "--force", "--deep", "--sign", "-", str(app)],
            capture_output=True,
            text=True,
        )
        assert done.returncode == 0, done.stderr
    return app


def audit(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args], capture_output=True, text=True, cwd=str(ROOT)
    )


def test_the_script_is_executable_and_parses():
    """GIVEN the audit script WHEN it is read as a program THEN it is executable and bash parses it."""
    assert SCRIPT.is_file(), "scripts/macos_sign_audit.sh is missing"
    assert SCRIPT.stat().st_mode & 0o111, "the script is not executable"
    assert subprocess.run(["bash", "-n", str(SCRIPT)]).returncode == 0


def test_misuse_is_refused_with_exit_2(tmp_path):
    """GIVEN no target, an unknown option or a path that does not exist WHEN it runs THEN exit 2."""
    assert audit().returncode == 2
    assert audit("--nope", str(tmp_path)).returncode == 2
    missing = audit(str(tmp_path / "absent.app"))
    assert missing.returncode == 2
    assert "No such bundle" in missing.stderr


@DARWIN
def test_an_unsigned_bundle_fails_the_seal_and_says_so(tmp_path):
    """
    GIVEN a bundle whose executable keeps a foreign signature and whose resources are
         not sealed — the shape issue #192 measured
    WHEN the audit runs
    THEN it exits 1, reports the `codesign --verify --deep --strict` failure and names
         the consequence, so a release cannot call that bundle verified
    """
    app = build_bundle(tmp_path, sign=False)
    result = audit(str(app))
    out = result.stdout + result.stderr

    assert result.returncode == 1, out
    assert "codesign --verify --deep --strict  FAIL" in out, out
    assert "seal=invalid" in result.stdout or "seal is invalid" in result.stderr, out
    assert "no resources" in out or "not signed at all" in out, out


@DARWIN
def test_the_documented_repair_produces_a_seal_the_audit_accepts(tmp_path):
    """
    GIVEN the same bundle
    WHEN it is signed across the whole bundle (`codesign --force --deep --sign -`), which
         is what `bundle.macOS.signingIdentity: "-"` makes the bundler do
    THEN the seal passes, the appended facts name an ad-hoc signature without a ticket,
         and the audit still exits 0 — an ad-hoc seal is valid, a downloaded copy is not
         accepted by Gatekeeper, and the script says both
    """
    app = build_bundle(tmp_path, sign=True)
    result = audit(str(app))
    out = result.stdout + result.stderr

    assert result.returncode == 0, out
    assert "codesign --verify --deep --strict  PASS" in out, out
    assert "Signature=adhoc" in out, out
    assert "seal=valid" in audit("--quiet", str(app)).stdout
    assert "spctl -a -vv  (rejected)" in out, out
    assert "Ad-hoc seal" in out, out
    assert "notarized" in out.lower(), out


@DARWIN
def test_a_disk_image_is_audited_through_the_app_it_carries(tmp_path):
    """
    GIVEN a DMG built from the signed bundle — the file a person downloads
    WHEN the audit runs on the image
    THEN it mounts it read-only, audits the `.app` inside and detaches again, so the
         released artifact is what gets checked rather than a staging copy
    """
    app = build_bundle(tmp_path, sign=True)
    dmg = tmp_path / "Ephe.dmg"
    built = subprocess.run(
        [
            "hdiutil", "create", "-volname", "Ephe", "-srcfolder", str(app),
            "-ov", "-format", "UDZO", str(dmg),
        ],
        capture_output=True,
        text=True,
    )
    assert built.returncode == 0, built.stdout + built.stderr
    result = audit(str(dmg))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "seal=valid" in audit("--quiet", str(dmg)).stdout


def test_the_release_workflow_carries_both_documented_outcomes():
    """
    GIVEN .github/workflows/release.yml
    WHEN the macOS steps are read
    THEN the Developer ID + notarization variables are read from secrets, the ad-hoc
         identity is the fallback, and the audit runs as a gate after the build.

    The two outcomes are the whole point of the issue's expected behaviour: a signed,
    notarized download when the repository can produce one, and an honestly sealed
    ad-hoc bundle otherwise — never a linker signature that claims to be one.
    """
    workflow = WORKFLOW.read_text(encoding="utf-8")

    for secret in (
        "secrets.APPLE_CERTIFICATE",
        "secrets.APPLE_CERTIFICATE_PASSWORD",
        "secrets.APPLE_SIGNING_IDENTITY",
        "secrets.APPLE_ID",
        "secrets.APPLE_PASSWORD",
        "secrets.APPLE_TEAM_ID",
        "secrets.APPLE_API_KEY",
        "secrets.APPLE_API_ISSUER",
    ):
        assert secret in workflow, f"release.yml does not read {secret}"

    assert 'signingIdentity\\":\\"-\\"' in workflow, (
        "the ad-hoc fallback (`signingIdentity: \"-\"`) is not in the workflow: without it "
        "an unsigned build keeps the linker signature that fails codesign --verify"
    )
    assert "scripts/macos_sign_audit.sh" in workflow, "the seal audit is not a release step"
    assert "$GITHUB_STEP_SUMMARY" in workflow, "the signing outcome is not recorded anywhere"
    assert "notarized" in workflow.lower(), (
        "the workflow has to say when a build is signed but not notarized"
    )
