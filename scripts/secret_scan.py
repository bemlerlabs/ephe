#!/usr/bin/env python3
"""Repo-own secret scanner: a committed credential refuses the build.

The repository decides its gates with its own scripts (`hygiene_check.py`,
`attribution_check.py`, `tauri_parity.py`), so the rule set here stays a file
this tree owns, greppable and testable offline. A pinned third-party binary
(gitleaks-action) would add a download, a licence question for organisations
and a rule set nobody here can read. There is no dependency beyond the standard
library and `git`.

Three exit codes, because an unscanned file is not a clean one:

  0  clean: every path in scope was read and nothing matched
  1  a finding: a secret pattern matched a line in scope
  2  no verdict: git or a path could not be read, so nothing was decided

Scopes, so the same rule set serves CI and any index-reading hook:
  --all                 every tracked file (`git ls-files`), whole content
  --staged              the staged blobs, whole content
  --range <rev>         the added lines of every commit in the range, so a
                        secret that was committed and then removed in the same
                        push is still reported
  --files <path> ...    the named paths, whole content

A finding prints the path, the line and the rule, never the value: the first
four characters and the length identify the leak without handing back the key.
A line may opt out with a `secret-scan: allow` comment, and a value or a path
on the allowlist file is exempted everywhere. Both are greppable, so every
exemption is a visible decision.
"""
from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ALLOW_MARKER = "secret-scan: allow"
DEFAULT_ALLOWLIST = REPO_ROOT / ".github" / "secrets-allowlist.txt"

#: The scanner source and its allowlist name the patterns and the acceptances;
#: scanning them would only report the tool to itself.
SELF_EXEMPT = ("scripts/secret_scan.py", "secrets-allowlist.txt")

#: A quoted value shorter than this is a placeholder, not a credential.
MIN_GENERIC_LEN = 16
#: Below this Shannon entropy a long quoted value is prose ("this is a test"),
#: above it the near-random shape of a key is the signal.
MIN_ENTROPY = 3.4

#: Words that mark a value as a deliberate non-secret. Case-insensitive.
#: `stub`, `masked` and the ellipsis cover the demo values a fixture writes down.
PLACEHOLDERS = (
    "example", "dummy", "placeholder", "sample", "redacted", "fake", "stub",
    "changeme", "change-me", "your-", "your_", "xxxx", "<", ">", "...", "\u2026",
    "supersecret", "super-secret", "super_secret", "masked",
    "test-", "test_", "secrets.", "not-a-", "not_a_",
)

#: A quoted value shaped like a file name is skipped even when the identifier
#: carries the keyword: `TOKEN_FILENAME = "discord_token.json"` holds a path.
FILENAME_LIKE = re.compile(
    r"(?i)^[A-Za-z0-9_.-]+\.(json|key|txt|py|ts|tsx|js|mjs|cjs|md|ya?ml|toml|"
    r"env|log|lock|sh|bash|zsh|ini|cfg|conf|sql|db|sqlite|pem|crt|cer|pub|"
    r"example|sample)$"
)

#: A lowercase hyphenated slug (`wg49-serve-token`) is a fixture naming itself;
#: key material carries mixed case or digits without the word-shaped dashes.
SLUG_LIKE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")

KEYWORDS = r"secret|token|passwd|password|pwd|api[_-]?key|apikey|access[_-]?key|private[_-]?key|credential"

#: (name, compiled pattern, group holding the secret). group 0 = whole match.
RULES: tuple[tuple[str, re.Pattern[str], int], ...] = (
    ("aws-access-key-id",
     re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)[0-9A-Z]{16}\b"), 0),
    ("aws-secret-access-key",
     re.compile(r"(?i)aws\D{0,24}(?:secret|access)\D{0,24}key\D{0,8}"
                r"([0-9A-Za-z/+]{40})"), 1),
    ("github-token",
     re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b"), 0),
    ("github-fine-grained-pat",
     re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b"), 0),
    ("slack-token",
     re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), 0),
    ("stripe-live-key",
     re.compile(r"\brk_live_[A-Za-z0-9]{24,}\b|\bsk_live_[A-Za-z0-9]{24,}\b"), 0),
    ("openai-key",
     re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"), 0),
    ("google-api-key",
     re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), 0),
    ("private-key-block",
     re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"), 0),
    # The identifier may embed the keyword (`db_password`, `AWS_SECRET_ACCESS_KEY`),
    # so the pattern is any name carrying a sensitive word followed by an assign:
    # a `\b` before `password` never fires inside `db_password`, which is a leak
    # the plain word list missed. Length, entropy and the placeholder list below
    # keep `max_tokens = "8192"` out.
    ("generic-secret-assignment",
     re.compile(r"(?i)[A-Za-z0-9_.]*(?:" + KEYWORDS + r")[A-Za-z0-9_.]*"
                r"\s*[:=]\s*['\"]([^'\"\n]{8,})['\"]"), 1),
)


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    value: str

    def render(self) -> str:
        head = self.value[:4]
        return (f"{self.path}:{self.line}: {self.rule}: "
                f"{head}\u2026<{len(self.value)} chars>")


def entropy(value: str) -> float:
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    total = len(value)
    return -sum((n / total) * math.log2(n / total) for n in counts.values())


def is_placeholder(value: str) -> bool:
    low = value.lower()
    return any(marker in low for marker in PLACEHOLDERS)


def generic_value_below_threshold(value: str) -> bool:
    """True when a generic assignment value is not a credential-shaped token.

    A key is one run of non-space characters with near-random entropy: anything
    with whitespace is prose, anything shaped like a file name is a name, and
    the length, entropy and placeholder checks keep `max_tokens = "8192"` and
    `tokenize='…'` out.
    """
    if len(value) < MIN_GENERIC_LEN:
        return True
    if any(ch.isspace() for ch in value):
        return True
    if "/" in value or "\\" in value:
        return True
    if FILENAME_LIKE.match(value):
        return True
    if SLUG_LIKE.match(value):
        return True
    if value.startswith("--") and value.replace("-", "").replace("_", "").isalnum():
        # A CSS custom property name (`token="--color-figure-plate"`). A credential
        # does not start with two hyphens and does not read as a word.
        return True
    return entropy(value) < MIN_ENTROPY or is_placeholder(value)


def load_allowlist(path: Path) -> list[str]:
    """Each non-comment, non-blank line is a substring that exempts a match.

    A line `path:<glob>` exempts a whole path, so a fixture directory can be
    accepted in one line instead of by value.
    """
    if not path.is_file():
        return []
    entries: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(line)
    return entries


def allowed(value: str, allow: list[str]) -> bool:
    for entry in allow:
        if entry.startswith("path:"):
            continue
        if entry in value:
            return True
    return False


def is_self(path: str) -> bool:
    return any(path == suffix or path.endswith("/" + suffix) for suffix in SELF_EXEMPT)


def path_allowed(path: str, allow: list[str]) -> bool:
    for entry in allow:
        if entry.startswith("path:") and fnmatch(path, entry[5:]):
            return True
    return False


def scan_lines(path: str, numbered: list[tuple[int, str]], allow: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in numbered:
        if ALLOW_MARKER in line:
            continue
        for name, pattern, group in RULES:
            for match in pattern.finditer(line):
                value = match.group(group)
                if name == "generic-secret-assignment" and generic_value_below_threshold(value):
                    continue
                if allowed(value, allow):
                    continue
                findings.append(Finding(path, number, name, value))
    return findings


def scan_text(path: str, text: str, allow: list[str]) -> list[Finding]:
    return scan_lines(path, list(enumerate(text.splitlines(), start=1)), allow)


def git(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, check=False)


def iter_tracked(root: Path):
    proc = git(["ls-files", "-z"], root)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git ls-files failed")
    for name in (proc.stdout or "").split("\0"):
        if name:
            yield name


def iter_staged(root: Path):
    proc = git(["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"], root)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "git diff --cached failed")
    for name in (proc.stdout or "").split("\0"):
        if name:
            yield name


def read_blob(root: Path, rev: str, path: str) -> str | None:
    proc = git(["show", f"{rev}:{path}"], root)
    if proc.returncode != 0:
        return None
    return proc.stdout


def iter_range_added_lines(root: Path, rev: str):
    """Yield (path, line_number, text) for every added line in the range.

    The commits are walked one at a time so a secret introduced and then
    deleted inside the same push is still reported: the added-line view is what
    history carries, and `--all` at HEAD would no longer see it.
    """
    log = git(["log", "--format=%H", "--no-color", rev], root)
    if log.returncode != 0:
        raise RuntimeError(log.stderr.strip() or f"git log {rev} failed")
    for sha in (log.stdout or "").split():
        diff = git(["show", "--no-color", "--format=", "--unified=0",
                    "--diff-filter=ACMR", sha], root)
        if diff.returncode != 0:
            raise RuntimeError(diff.stderr.strip() or f"git show {sha} failed")
        path = ""
        number = 0
        for line in (diff.stdout or "").splitlines():
            if line.startswith("+++ b/"):
                path = line[6:]
            elif line.startswith("@@"):
                match = re.search(r"\+(\d+)", line)
                number = int(match.group(1)) if match else 0
            elif line.startswith("+") and not line.startswith("+++"):
                yield path, number, line[1:]
                number += 1


def dedupe(findings: list[Finding]) -> list[Finding]:
    """One finding per (path, line, value), the first rule wins.

    The specific rules run before the generic one, so `AKIA…` is reported as
    `aws-access-key-id` and not twice as a generic assignment.
    """
    seen: set[tuple[str, int, str]] = set()
    out: list[Finding] = []
    for finding in findings:
        key = (finding.path, finding.line, finding.value)
        if key in seen:
            continue
        seen.add(key)
        out.append(finding)
    return out


def report(findings: list[Finding]) -> None:
    for finding in findings:
        print(finding.render())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--all", action="store_true", help="every tracked file")
    scope.add_argument("--staged", action="store_true", help="the staged blobs")
    scope.add_argument("--range", metavar="REV", help="added lines of a commit range")
    scope.add_argument("--files", nargs="+", metavar="PATH", help="explicit paths")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="tree to scan")
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument("--report", action="store_true",
                        help="print findings and exit 0 instead of failing")
    args = parser.parse_args(argv)

    allow = load_allowlist(args.allowlist)
    findings: list[Finding] = []
    scanned = 0
    skipped_binary = 0
    unreadable: list[str] = []

    try:
        if args.files:
            for name in args.files:
                path = Path(name)
                target = path if path.is_absolute() else args.root / name
                rel = name if not path.is_absolute() else str(path)
                if is_self(rel) or path_allowed(rel, allow):
                    continue
                if not target.is_file():
                    unreadable.append(rel)
                    continue
                raw = target.read_bytes()
                if b"\x00" in raw:
                    skipped_binary += 1
                    continue
                scanned += 1
                findings += scan_text(rel, raw.decode("utf-8", "replace"), allow)
        elif args.staged:
            for name in iter_staged(args.root):
                if is_self(name) or path_allowed(name, allow):
                    continue
                blob = read_blob(args.root, "", name)
                if blob is None:
                    unreadable.append(name)
                    continue
                if "\x00" in blob:
                    skipped_binary += 1
                    continue
                scanned += 1
                findings += scan_text(name, blob, allow)
        elif args.range:
            for path, number, text in iter_range_added_lines(args.root, args.range):
                if is_self(path) or path_allowed(path, allow):
                    continue
                scanned += 1
                findings += scan_lines(path, [(number, text)], allow)
        else:
            for name in iter_tracked(args.root):
                if is_self(name) or path_allowed(name, allow):
                    continue
                target = args.root / name
                if target.is_file():
                    raw = target.read_bytes()
                else:
                    # A tracked path removed from the working tree mid-edit (another
                    # lane's `rm` before its `git rm`) still has its index blob; scan
                    # that rather than refuse a tree that committed fine.
                    blob = read_blob(args.root, "", name)
                    if blob is None:
                        unreadable.append(name)
                        continue
                    raw = blob.encode("utf-8", "replace")
                if b"\x00" in raw:
                    skipped_binary += 1
                    continue
                scanned += 1
                findings += scan_text(name, raw.decode("utf-8", "replace"), allow)
    except RuntimeError as error:
        print(f"secret-scan: NO VERDICT: {error}", file=sys.stderr)
        return 2

    findings = dedupe(findings)
    report(findings)
    print(f"secret-scan: {scanned} path(s)/line(s) scanned, "
          f"{skipped_binary} binary skipped, {len(findings)} finding(s)",
          file=sys.stderr)

    if args.report:
        return 0
    if unreadable:
        for name in unreadable:
            print(f"secret-scan: NO VERDICT: {name} could not be read", file=sys.stderr)
        return 2
    if findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
