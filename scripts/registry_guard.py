#!/usr/bin/env python3
"""Refuse a shipped file that pipes a remote script into a shell.

An npm wrapper of ours handed the remote PowerShell script of a release tag to `iex`, and the
remote shell script of the same tag to `bash`, from its `bin` script. The registry blocked the
package and suspended the account: what was punished was
not a bad download, it was a download handed to an interpreter without a single byte being
looked at. `.github/AGENTS.md` already refuses that shape in a workflow ("A download that feeds
`sh` or `bash` is refused"); this is the same rule over the files a user or a registry installs,
written down as a gate rather than as a convention a reviewer has to remember.

The guarded surface is what ships or is fetched: `packaging/`, `scripts/`, `server/`, `core/`
and `.github/`. `install.sh` and `install.ps1` are deliberately outside it — they download
release assets, which is legal, and the rule below only ever fires on the pipe-into-shell shape,
never on a download. An npm package that runs code at install time is the second finding, so a
`package.json` in scope carrying a `preinstall` or `postinstall` hook fails too.

    scripts/registry_guard.py                 # the whole guarded surface
    scripts/registry_guard.py path/to/file    # named files, whatever directory they sit in

A comment line states the rule instead of executing it, so comment leaders and Markdown bodies
are not findings; nothing a shell, a Python interpreter or npm would run is skipped.

Exit codes: 0 nothing in scope matched, 1 a finding, 2 a file could not be read so nothing was
decided. An unscanned file is never reported as a clean one.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Directories whose files reach a user, a registry or a runner.
GUARDED_DIRS = ("packaging", "scripts", "server", "core", ".github")

#: Prose carries the rule and its explanations; the scanner source and its allowlist name the
#: patterns, and reporting the tool to itself teaches nobody anything.
DOC_SUFFIXES = frozenset({".md", ".rst", ".txt"})

#: A directory nobody ships. `dist` and `node_modules` are named by the task; the rest are the
#: build and cache output this tree produces, and a scan that stopped on them would decide nothing.
SKIP_DIRS = frozenset({
    ".git", "node_modules", "dist", ".venv", "venv", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".benchmarks", "target",
})

#: The marker that excuses one line, in the shape `secret_scan.py` uses: greppable, so every
#: acceptance is a sentence a reviewer can find.
ALLOW_MARKER = "registry-guard: allow"

#: Accepted findings live in a file rather than in this script, so the exceptions are a list a
#: diff shows. Entry form: a fnmatch pattern over the repo-relative path, optionally
#: `path::needle` where the needle has to appear in the offending line.
DEFAULT_ALLOWLIST = REPO_ROOT / "scripts" / "registry-guard-allowlist.txt"

#: The scanner source names every pattern and its allowlist names every acceptance; matching the
#: rule table against its own rules reports the tool to itself. Same exemption `secret_scan.py`
#: carries, for the same reason.
SELF_EXEMPT = ("scripts/registry_guard.py", "registry-guard-allowlist.txt")

#: npm lifecycle hooks that run without the user asking for them.
INSTALL_HOOKS = ("preinstall", "postinstall")

#: Comment leaders per language. A line whose first non-space character is one of these is a
#: comment in that language, which means no interpreter reads it. An unknown suffix is scanned
#: whole rather than given a leader it may not honour.
COMMENT_LEADERS: dict[str, tuple[str, ...]] = {
    ".py": ("#",), ".sh": ("#",), ".bash": ("#",), ".zsh": ("#",),
    ".yml": ("#",), ".yaml": ("#",), ".rb": ("#",), ".toml": ("#",),
    ".js": ("//", "/*"), ".mjs": ("//", "/*"), ".cjs": ("//", "/*"),
    ".ts": ("//", "/*"), ".json": (), ".ps1": ("#",), ".psm1": ("#",),
}

#: One rule per way a remote script reaches an interpreter. Each id is what a finding prints and
#: what an allowlist needle may name.
RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("download-piped-to-shell",
     re.compile(r"\b(?:curl|wget)\b[^|]*\|\s*(?:sudo\s+)?(?:ba|z)?sh\b", re.IGNORECASE)),
    ("download-piped-to-shell",
     re.compile(r"\b(?:ba|z)?sh\b[^|]*<\(\s*(?:curl|wget)\b", re.IGNORECASE)),
    ("irm-piped-to-iex",
     re.compile(r"\b(?:irm|invoke-webrequest|iwr|curl|wget)\b[^|]*\|\s*iex\b", re.IGNORECASE)),
    ("invoke-expression", re.compile(r"\binvoke-expression\b", re.IGNORECASE)),
    ("execution-policy-bypass",
     re.compile(r"executionpolicy\s*[:=]?\s*['\"]?bypass", re.IGNORECASE)),
    ("eval-subshell-download",
     re.compile(r"\beval\s+\$\(\s*(?:curl|wget)\b", re.IGNORECASE)),
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    text: str

    def render(self) -> str:
        snippet = " ".join(self.text.split())
        if len(snippet) > 160:
            snippet = snippet[:157] + "..."
        return f"registry-guard: FAIL {self.path}:{self.line} {self.rule}: {snippet}"


def _is_binary(raw: bytes) -> bool:
    return b"\0" in raw[:8192]


def _scannable_lines(rel: str, raw: bytes) -> list[tuple[int, str]]:
    """The lines a rule may judge: every byte decoded, minus the comment leaders of that file."""
    text = raw.decode("utf-8", errors="replace")
    leaders = COMMENT_LEADERS.get(Path(rel).suffix.lower())
    numbered: list[tuple[int, str]] = []
    for index, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if leaders and any(stripped.startswith(leader) for leader in leaders):
            continue
        if ALLOW_MARKER in line:
            continue
        numbered.append((index, line))
    return numbered


def _install_hooks(rel: str, raw: bytes) -> list[tuple[int, str]]:
    """The line numbers of a `preinstall` or `postinstall` key in an npm manifest.

    Parsed rather than matched as text, because a hook buried in a nested object is still a hook
    npm runs, and a manifest that will not parse is no verdict at all -- the caller treats a
    `ValueError` here as the run failing to decide.
    """
    if Path(rel).name != "package.json":
        return []
    text = raw.decode("utf-8", errors="replace")
    document = json.loads(text)
    if not isinstance(document, dict):
        return []
    scripts = document.get("scripts")
    if not isinstance(scripts, dict):
        return []
    wanted = sorted({str(hook) for hook in scripts if str(hook).lower() in INSTALL_HOOKS})
    if not wanted:
        return []
    lines = text.splitlines()
    hits: list[tuple[int, str]] = []
    for hook in wanted:
        pattern = re.compile(rf'"\s*{re.escape(hook)}\s*"\s*:')
        for index, line in enumerate(lines, start=1):
            if pattern.search(line):
                hits.append((index, line))
                break
        else:
            # A manifest written on one line: the hook is real, the key just has no line of its own.
            hits.append((1, f'"scripts": {{"{hook}": ...}}'))
    return hits


def load_allowlist(path: Path) -> list[tuple[str, str | None]]:
    """`(pattern, needle)` per entry; `#` lines and blanks are the file's own prose."""
    if not path.exists():
        return []
    entries: list[tuple[str, str | None]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        file_pattern, _, needle = entry.partition("::")
        entries.append((file_pattern.strip(), needle.strip() or None))
    return entries


def _exempted(finding: Finding, allow: list[tuple[str, str | None]]) -> bool:
    for pattern, needle in allow:
        if not fnmatch.fnmatch(finding.path, pattern):
            continue
        if needle is None or needle in finding.text:
            return True
    return False


def scan_file(target: Path, rel: str) -> list[Finding]:
    """Every rule against one file, or `OSError`/`ValueError` from the caller's read."""
    raw = target.read_bytes()
    if _is_binary(raw):
        return []
    findings: list[Finding] = []
    for rule, pattern in RULES:
        for index, line in _scannable_lines(rel, raw):
            if pattern.search(line):
                findings.append(Finding(rel, index, rule, line))
    for index, line in _install_hooks(rel, raw):
        findings.append(Finding(rel, index, "npm-install-hook", line))
    return findings


def tracked_files(root: Path) -> list[str] | None:
    """`git ls-files`, or None when git cannot answer -- which is the state of a tree that has
    not been initialised yet, and of a shallow export of one."""
    try:
        done = subprocess.run(
            ["git", "ls-files", "-z"], cwd=root, capture_output=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    paths = [entry for entry in done.stdout.decode("utf-8", errors="replace").split("\0") if entry]
    return paths or None


def _in_scope(rel: str) -> bool:
    """A guarded directory, not build output, not prose -- the same answer from the index and
    from a walk, so an uninitialised tree and a committed one are judged by one rule."""
    if not rel.startswith(tuple(f"{name}/" for name in GUARDED_DIRS)):
        return False
    if rel in SELF_EXEMPT:
        return False
    if any(part in SKIP_DIRS for part in rel.split("/")[:-1]):
        return False
    return Path(rel).suffix.lower() not in DOC_SUFFIXES


def guarded_files(root: Path) -> list[str]:
    """Every path under the guarded directories, from the index when there is one."""
    tracked = tracked_files(root)
    if tracked is not None:
        return sorted(rel for rel in tracked if _in_scope(rel))
    found: list[str] = []
    for name in GUARDED_DIRS:
        base = root / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if _in_scope(rel):
                found.append(rel)
    return sorted(found)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refuse a remote script piped into a shell.")
    parser.add_argument("paths", nargs="*", help="files to judge; default: the guarded surface")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="checkout to judge")
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    args = parser.parse_args(argv)

    root = args.root.resolve()
    candidates: list[tuple[Path, str]] = []
    if args.paths:
        for given in args.paths:
            target = Path(given)
            target = target if target.is_absolute() else root / target
            if not target.is_file():
                print(f"registry-guard: NO VERDICT {given} is not a file", file=sys.stderr)
                return 2
            target = target.resolve()
            try:
                display = str(target.relative_to(root))
            except ValueError:
                # A planted file outside the checkout is judged by the name it was given, so a
                # test can hand the guard a path it does not own.
                display = str(target)
            candidates.append((target, display))
    else:
        candidates = [(root / rel, rel) for rel in guarded_files(root)]
        if not candidates:
            print(
                f"registry-guard: NO VERDICT none of {', '.join(GUARDED_DIRS)} exists under {root}",
                file=sys.stderr,
            )
            return 2

    allow = load_allowlist(args.allowlist)
    findings: list[Finding] = []
    exempted = 0
    for target, rel in candidates:
        try:
            file_findings = scan_file(target, rel)
        except OSError as exc:
            print(f"registry-guard: NO VERDICT {rel} could not be read: {exc}", file=sys.stderr)
            return 2
        except ValueError as exc:
            print(f"registry-guard: NO VERDICT {rel} is not parseable: {exc}", file=sys.stderr)
            return 2
        for finding in file_findings:
            if _exempted(finding, allow):
                exempted += 1
                continue
            findings.append(finding)

    if exempted:
        print(
            f"registry-guard: {exempted} finding(s) exempted by {args.allowlist.name} "
            "(each one is a decision a diff has to carry)"
        )
    if findings:
        for finding in findings:
            print(finding.render())
        print(
            f"registry-guard: FAIL {len(findings)} remote-code-into-shell finding(s) in "
            f"{len(candidates)} file(s); fetch the artifact, verify it, then run it"
        )
        return 1
    print(f"registry-guard: PASS {len(candidates)} file(s) carry no remote script piped into a shell")
    return 0


if __name__ == "__main__":
    sys.exit(main())
