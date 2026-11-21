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

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "macos_sign_audit.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
INSTALL_DOC = ROOT / "docs" / "INSTALL.md"
INSTALL_OPTIONS_DOC = ROOT / "docs" / "INSTALL_OPTIONS.md"

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


def workflow_steps(job: str) -> list[dict]:
    """The steps of one release.yml job, parsed from the file the runner reads."""
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return doc["jobs"][job]["steps"]


def workflow_step(job: str, name: str) -> dict:
    for step in workflow_steps(job):
        if step.get("name") == name:
            return step
    raise AssertionError(f"release.yml has no step named {name!r}")


def test_the_summary_form_is_named_in_the_help():
    """
    GIVEN the audit script
    WHEN it is asked for its usage
    THEN the CI summary form is one of the two documented invocations, because the release
         workflow calls it and a hidden option is not a contract
    """
    result = subprocess.run(
        ["bash", str(SCRIPT), "--help"], capture_output=True, text=True, cwd=str(ROOT)
    )
    assert result.returncode == 0, result.stderr
    assert "--summary" in result.stdout, result.stdout


@DARWIN
def test_the_summary_block_calls_an_adhoc_seal_not_notarized(tmp_path):
    """
    GIVEN an ad-hoc signed bundle — the shape a release without Apple secrets produces
    WHEN the audit runs in its summary form, the one the workflow writes to $GITHUB_STEP_SUMMARY
    THEN it exits 0, names the artifact, and states the signature and notarization state in
         words: ad-hoc, not notarized, with the documented first-launch step
    """
    app = build_bundle(tmp_path, sign=True)
    result = audit("--summary", str(app))
    out = result.stdout + result.stderr

    assert result.returncode == 0, out
    assert "### macOS bundle seal" in result.stdout, out
    assert str(app) in result.stdout, out
    assert "state=adhoc-not-notarized" in result.stdout, out
    assert "Not notarized" in result.stdout, out
    assert "docs/INSTALL.md" in result.stdout, out


@DARWIN
def test_the_quiet_line_carries_the_state_the_summary_reports(tmp_path):
    """
    GIVEN the same ad-hoc bundle
    WHEN the audit runs with --quiet
    THEN the one line names the seal, the signature and the notarization state, so a log
         reader does not have to infer "not notarized" from a rejected spctl
    """
    app = build_bundle(tmp_path, sign=True)
    line = audit("--quiet", str(app)).stdout.strip()

    assert "seal=valid" in line, line
    assert "signature=adhoc" in line, line
    assert "state=adhoc-not-notarized" in line, line


def test_the_release_audit_writes_both_artifacts_state_to_the_step_summary():
    """
    GIVEN .github/workflows/release.yml
    WHEN the macOS audit step is read
    THEN the app and the DMG each get their state written to $GITHUB_STEP_SUMMARY, and the
         plain audit call stays in the step, so an invalid seal still fails the release
    """
    run = workflow_step("build-bundles", "Audit the macOS bundle seal")["run"]

    assert run.count("macos_sign_audit.sh --summary") == 2, (
        "the app and the DMG both have to record their state in the step summary; "
        f"the step carries {run.count('macos_sign_audit.sh --summary')} summary calls"
    )
    assert '>> "$GITHUB_STEP_SUMMARY"' in run, "the summary form is not redirected to the summary"
    assert re.search(r'scripts/macos_sign_audit\.sh "\$bundle"', run), (
        "the plain audit call is what fails the release on an invalid seal"
    )


def test_absent_apple_secrets_are_a_silent_adhoc_build():
    """
    GIVEN no APPLE_* secret in the repository
    WHEN the signing-decision step runs
    THEN the ad-hoc branch is taken quietly: no annotation, no failing exit, and the
         Developer ID plus notarization variables stay in the workflow for the day they exist
    """
    step = workflow_step("build-bundles", "Decide the macOS signature")
    run = step["run"]

    marker = 'if [ -z "${APPLE_CERTIFICATE:-}" ]'
    assert marker in run, "the ad-hoc decision is not keyed on the certificate secret"
    branch: list[str] = []
    for line in run.split(marker, 1)[1].splitlines():
        if line.strip() == "fi":
            break
        branch.append(line)
    body = "\n".join(branch)

    assert "adhoc" in body, body
    assert "exit 0" in body, body
    for annotation in ("::warning", "::error"):
        assert annotation not in body, (
            f"the ad-hoc branch raises {annotation}: an absent bonus secret is not a defect"
        )

    for name in ("APPLE_ID", "APPLE_TEAM_ID", "APPLE_API_KEY", "APPLE_API_ISSUER"):
        assert name in run, f"the notarization variable {name} is never handed to the build"


def test_the_install_docs_carry_the_normal_unnotarized_install_path():
    """
    GIVEN the install documentation
    WHEN it describes the macOS app a person downloads
    THEN it names the GitHub release the DMG comes from, the right-click → Open step and the
         scripted `xattr -d com.apple.quarantine` equivalent, and it makes no Apple signature
         claim
    """
    text = INSTALL_DOC.read_text(encoding="utf-8")
    lowered = text.lower()

    assert "right-click" in lowered
    assert "xattr -d com.apple.quarantine" in text
    assert "not notarized" in lowered
    assert "github.com/bemlerlabs/ephe/releases" in text
    assert "signed by apple" not in lowered, "the docs must not claim an Apple signature"
    assert "is notarized by apple" not in lowered, "the docs must not claim Apple notarization"

    options = INSTALL_OPTIONS_DOC.read_text(encoding="utf-8").lower()
    assert "right-click" in options, "INSTALL_OPTIONS.md lists no macOS app install step"
    assert "xattr" in options, "INSTALL_OPTIONS.md does not name the scripted unquarantine"


def test_the_install_docs_state_which_artifacts_a_release_ships():
    """
    GIVEN the install documentation
    WHEN it describes Windows
    THEN it names the artifacts the release actually builds (macOS DMG, Linux deb/AppImage/
         RPM), says there is no Windows binary for SmartScreen to check, and names the gate a
         Windows source install really meets
    """
    lowered = INSTALL_DOC.read_text(encoding="utf-8").lower()
    # Compare words regardless of how the file wraps them.
    unwrapped = " ".join(lowered.split())

    assert "no windows binary" in lowered, "the docs do not say that no Windows binary ships"
    assert "no `.exe` for smartscreen to check" in unwrapped, (
        "the docs do not say what SmartScreen does and does not see"
    )
    assert "appimage" in lowered, "the Linux artifacts the release builds are not named"
    assert "execution policy" in lowered, "the Windows source-install gate is not named"
