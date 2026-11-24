"""Check README contracts offline; --public verifies the install tag on GitHub."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

PUBLIC_REPOSITORY = "bemlerlabs/ephe"
READMES = ("README.md", "README.zh-CN.md", "README.es.md")
START_DOCS = (
    "docs/QUICKSTART.md",
    "docs/INSTALL.md",
    "docs/INSTALL_OPTIONS.md",
    "docs/FIRST_RUN.md",
)
EN_SECTIONS = (
    "What Ephe is",
    "What you can do",
    "What happens in a task",
    "Desktop, terminal, phone",
    "Quick start",
    "What you need",
    "What it costs",
    "Private and in control",
    "Plugins, skills, and connectors",
    "What is not there yet",
    "If something goes wrong",
    "Docs, contributing, and license",
)
CANONICAL_MARKER = "canonical: README.md is authoritative"
ROLLING_REF = "main"
INSTALL = re.compile(
    r"raw\.githubusercontent\.com/bemlerlabs/ephe/"
    r"(v[0-9]+\.[0-9]+\.[0-9]+|main)/install\.(sh|ps1)"
)
FENCE = re.compile(r"```.*?```", re.DOTALL)
# A document that ships a rolling URL must say so in prose a reader sees, and a
# document may not claim a tag is published or absent unless the remote agrees.
# Measured 2026-11-24: the public repository carried a v0.1.0 install URL in seven
# files while `git ls-remote --tags origin` was empty; the offline gate could not
# see it because the existence of a tag is only knowable on the network.
NO_TAG_CLAIM = re.compile(r"\bno (?:release )?tag exists\b", re.IGNORECASE)
# The second alternative is Chinese for "the tag is published", spelled in
# escapes because the script-hygiene gate keeps sources latin-only.
PUBLISHED_CLAIM = re.compile(
    r"the tag is published|\u6807\u7b7e\u5df2\u53d1\u5e03|(?:tag|etiqueta) está publicada",
    re.IGNORECASE,
)
VERSION_TAG = re.compile(r"\bv([0-9]+\.[0-9]+\.[0-9]+)\b")
MD_LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)")
HTML_IMG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
HTML_SRC = re.compile(r"<img\b[^>]*\bsrc=\"([^\"]+)\"", re.IGNORECASE)
HTML_HREF = re.compile(r"<a\b[^>]*\bhref=\"([^\"]+)\"", re.IGNORECASE)
HTML_ALT = re.compile(r"\balt=\"([^\"]*)\"", re.IGNORECASE)
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]")
CLAIMS = re.compile(r"\b(?:SOTA|state[- ]of[- ]the[- ]art|audited|secure)\b", re.IGNORECASE)
PRIVATE_HOST = re.compile(
    r"\b(?:10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|"
    r"172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+|[A-Za-z0-9.-]+\.ts\.net)\b"
)
SECRET = re.compile(r"\bsk-[A-Za-z0-9]{12,}")
H2 = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
PROJECT_VERSION = re.compile(r"(?m)^\s*version\s*=\s*[\"']([^\"']+)[\"']")


@dataclass
class Result:
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def h2(text: str) -> list[str]:
    return [m.group(1).strip().rstrip("#").strip() for m in H2.finditer(text)]


def check_sections(text: str, label: str, result: Result) -> None:
    found = h2(text)
    if found != list(EN_SECTIONS):
        missing = [name for name in EN_SECTIONS if name not in found]
        extra = [name for name in found if name not in EN_SECTIONS]
        result.problems.append(
            f"{label}: section list differs (missing={missing}, extra={extra})"
        )


def _names_rolling_ref(text: str) -> bool:
    """A reader must be told the rolling ref is rolling, in prose."""
    body = FENCE.sub("", text)
    return any(
        f"`{ROLLING_REF}`" in sentence and "rolling ref" in sentence.lower()
        for sentence in re.split(r"(?<=[.!?])\s+", body)
    )


FLAG = re.compile(r"(?:--tag|--ref|(?<!\w)-Ref)[ \t=]+([A-Za-z0-9][A-Za-z0-9._/-]*)")


def check_ref_pairing(text: str, label: str, result: Result) -> None:
    """Each documented command must ask the installer for the ref its URL fetches.

    The v0.6.8 defect: the URL fetched install.sh from the tag while the installer
    cloned the branch tip, so a release user ran untagged code believing it was the
    release. The installer's refless default is the branch tip
    (install.sh `REF="${EPHE_REF:-}"`), which makes the flagless rolling command the
    one consistent form; a rolling URL with a ref flag and a tag URL without one are
    both the old bug in a new coat. Whether a named tag exists is --public's question.
    """
    for block in re.findall(r"```(?:bash|powershell)\n(.*?)```", text, re.DOTALL):
        urls = {ref for ref, _script in INSTALL.findall(block)}
        if not urls:
            continue
        flags = {value for value in FLAG.findall(block)}
        if ROLLING_REF in flags:
            result.problems.append(
                f"{label}: a documented command pins {ROLLING_REF} by flag; "
                "the rolling install is flagless"
            )
        wanted = urls - {ROLLING_REF}
        for ref in sorted(wanted - flags):
            result.problems.append(
                f"{label}: {ref} is fetched by URL but not passed to the installer"
            )
        for ref in sorted(flags - urls - {ROLLING_REF}):
            result.problems.append(
                f"{label}: the installer is told {ref}, which the install URL does not name"
            )


def check_install(text: str, label: str, expected: str, tags: set[str], result: Result) -> None:
    found = INSTALL.findall(text)
    if not found:
        result.problems.append(f"{label}: no install URL")
        return
    for ref, script in found:
        if ref == ROLLING_REF:
            if not _names_rolling_ref(text):
                result.problems.append(
                    f"{label}: install URL uses the rolling ref {ROLLING_REF} "
                    "without a sentence naming it as a rolling ref"
                )
            continue
        if ref != expected:
            result.problems.append(
                f"{label}: install URL uses {ref}, expected {expected} ({script})"
            )
        if ref not in tags:
            result.problems.append(f"{label}: install tag {ref} does not exist")


def check_version_tags(text: str, label: str, expected: str, result: Result) -> None:
    """A release tag named in prose is the tag this tree ships.

    The install tarball once carried one tag in its URL and another in the
    sentence under it, and only the URL was checked.
    """
    body = INSTALL.sub("", text)
    for match in VERSION_TAG.finditer(body):
        named = f"v{match.group(1)}"
        if named != expected:
            line = body.count("\n", 0, match.start()) + 1
            result.problems.append(f"{label}:{line}: prose names {named}, expected {expected}")


def check_powershell(text: str, label: str, result: Result) -> None:
    blocks = re.findall(r"```powershell\n(.*?)```", text, re.DOTALL)
    if not blocks:
        return
    joined = "\n".join(blocks)
    if re.search(r"\bcurl\b", joined, re.IGNORECASE):
        result.problems.append(f"{label}: PowerShell block uses curl")
    if "install.ps1" not in joined:
        result.problems.append(f"{label}: PowerShell block does not name install.ps1")
    if not re.search(r"\b(?:irm|Invoke-WebRequest)\b", joined):
        result.problems.append(f"{label}: PowerShell block has no irm/Invoke-WebRequest")


def check_macos(text: str, label: str, result: Result) -> None:
    if "still open" in text.lower():
        result.problems.append(f"{label}: old macOS wording 'Still Open'")
    if "notarized" in text.lower() and "open anyway" not in text.lower():
        result.problems.append(f"{label}: notarized-app note lacks 'Open Anyway'")


def check_emoji(text: str, label: str, result: Result) -> None:
    hits = sorted(set(EMOJI.findall(text)))
    if hits:
        result.problems.append(f"{label}: emoji present: {hits}")


def check_claims(text: str, label: str, result: Result) -> None:
    hits = sorted({m.group(0) for m in CLAIMS.finditer(text)})
    if hits:
        result.problems.append(f"{label}: unsupported claim words: {hits}")


def check_private_hosts(text: str, label: str, result: Result) -> None:
    hits = sorted(set(PRIVATE_HOST.findall(text)))
    if hits:
        result.problems.append(f"{label}: private host addresses: {hits}")


def check_secrets(text: str, label: str, result: Result) -> None:
    if SECRET.search(text):
        result.problems.append(f"{label}: key-shaped string")


def local_targets(text: str) -> list[str]:
    out = MD_LINK.findall(text)
    out.extend(HTML_SRC.findall(text))
    out.extend(HTML_HREF.findall(text))
    return out


def check_links(text: str, label: str, root: Path, result: Result) -> None:
    base = (root / label).parent
    for target in local_targets(text):
        target = target.strip()
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = target.split("#", 1)[0].strip()
        if not target:
            continue
        if not (base / target).exists():
            result.problems.append(f"{label}: dead local link {target}")


def check_alt(text: str, label: str, result: Result) -> None:
    for alt, _target in MD_IMAGE.findall(text):
        if not alt.strip():
            result.problems.append(f"{label}: image without alt text")
    for tag in HTML_IMG.findall(text):
        match = HTML_ALT.search(tag)
        if not match or not match.group(1).strip():
            result.problems.append(f"{label}: HTML image without alt text")


def check_code_fences(text: str, label: str, result: Result) -> None:
    inside = False
    for line in text.splitlines():
        if not line.startswith("```"):
            continue
        if inside:
            inside = False
            continue
        inside = True
        if not line[3:].strip():
            result.problems.append(f"{label}: code fence without a language")


def check_canonical(text: str, label: str, en_h2: int, result: Result) -> None:
    if len(h2(text)) != en_h2:
        result.problems.append(f"{label}: {len(h2(text))} sections != {en_h2}")


def check_examples(text: str, label: str, english: str, result: Result) -> None:
    pattern = r"```(?:bash|powershell)\n(.*?)```"
    if re.findall(pattern, text, re.DOTALL) != re.findall(pattern, english, re.DOTALL):
        result.problems.append(f"{label}: executable examples differ from README.md")


def readability(text: str, label: str, result: Result) -> None:
    body = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    body = re.sub(r"^\s*\|.*\|\s*$", "", body, flags=re.MULTILINE)
    body = re.sub(r"^\s*\[!\[.*$", "", body, flags=re.MULTILINE)
    body = re.sub(r"<[^>]+>", "", body)
    body = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", body)
    body = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", body)
    body = re.sub(r"^#{1,6}\s*.*$", "", body, flags=re.MULTILINE)
    body = re.sub(r"\n\s*\n+", "\n", body)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?:;])\s+", body) if s.strip()]
    if not sentences:
        return
    lengths = [len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’-]*", s)) for s in sentences]
    average = sum(lengths) / len(lengths)
    longest = max(lengths)
    if average > 20:
        result.warnings.append(f"{label}: average sentence {average:.1f} words")
    if longest > 30:
        result.warnings.append(f"{label}: longest sentence {longest} words")


def public_tags(tag: str, repository: str = PUBLIC_REPOSITORY, remote: str | None = None) -> set[str]:
    """The install tag exists on the public repository."""
    url = remote or f"https://github.com/{repository}.git"
    ref = f"refs/tags/{tag}"
    try:
        response = subprocess.run(
            ["git", "ls-remote", "--exit-code", url, ref, ref + "^{}"],
            capture_output=True, text=True, check=True, timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"install tag {tag} does not exist on {repository}") from exc
    refs = {name for _sha, name in (line.split() for line in response.stdout.splitlines())}
    if ref not in refs:
        raise ValueError(f"install tag {tag} does not exist on {repository}")
    return {tag}


def public_branch(ref: str, repository: str = PUBLIC_REPOSITORY, remote: str | None = None) -> str:
    """The rolling ref exists as a branch on the public repository."""
    url = remote or f"https://github.com/{repository}.git"
    head = f"refs/heads/{ref}"
    try:
        response = subprocess.run(
            ["git", "ls-remote", "--exit-code", url, head],
            capture_output=True, text=True, check=True, timeout=30,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"rolling ref {ref} does not exist on {repository}") from exc
    if not any(line.split("\t", 1)[-1] == head for line in response.stdout.splitlines()):
        raise ValueError(f"rolling ref {ref} does not exist on {repository}")
    return ref


def public_release_tags(repository: str = PUBLIC_REPOSITORY, remote: str | None = None) -> set[str]:
    """Every release tag on the public repository, for the prose that talks about tags."""
    url = remote or f"https://github.com/{repository}.git"
    response = subprocess.run(
        ["git", "ls-remote", url, "refs/tags/*"],
        capture_output=True, text=True, check=True, timeout=30,
    )
    return {
        match.group(0)
        for line in response.stdout.splitlines()
        for match in [VERSION_TAG.search(line.split("\t", 1)[-1])]
        if match
    }


def _checked_texts(root: Path) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for rel in (*READMES, *START_DOCS):
        path = root / rel
        if path.is_file():
            found.append((rel, path.read_text(encoding="utf-8")))
    return found


def verify_public(root: Path, repository: str = PUBLIC_REPOSITORY, remote: str | None = None) -> None:
    """--public: the refs and tag claims the texts make must be true on the remote.

    Offline the gate can only compare a tag against this tree's version; on the
    network it can ask what actually exists. Measured 2026-11-24: seven files sold
    a v0.1.0 install URL while the public repository had no tags at all.
    """
    texts = _checked_texts(root)
    refs = {ref for _rel, text in texts for ref, _script in INSTALL.findall(text)}
    for ref in sorted(refs):
        if ref == ROLLING_REF:
            public_branch(ref, repository, remote)
        else:
            public_tags(ref, repository, remote)
    if any(NO_TAG_CLAIM.search(text) for _rel, text in texts):
        existing = public_release_tags(repository, remote)
        if existing:
            raise ValueError(
                f"a checked text claims no tag exists, but {repository} carries {sorted(existing)}"
            )
    if any(PUBLISHED_CLAIM.search(text) for _rel, text in texts):
        if not public_release_tags(repository, remote):
            raise ValueError(
                f"a checked text claims a tag is published, but {repository} has no release tag"
            )


def shipped_tag(root: Path) -> str:
    """The tag this tree ships, from `[project].version`."""
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    section = re.search(r"(?ms)^\[project\]\s*$(.*?)(?=^\[[^\]]+\]|\Z)", text)
    match = PROJECT_VERSION.search(section.group(1) if section else text)
    if not match or not re.fullmatch(r"\d+\.\d+\.\d+", match.group(1)):
        raise ValueError("pyproject.toml carries no concrete [project].version")
    return "v" + match.group(1)


def check(root: Path, *, tag: str | None = None, tags: set[str] | None = None) -> Result:
    tag = tag or shipped_tag(root)
    if tags is None:
        tags = {tag}
    result = Result()
    en_text = (root / "README.md").read_text(encoding="utf-8")
    en_h2 = len(h2(en_text))
    check_sections(en_text, "README.md", result)

    for label in READMES:
        path = root / label
        if not path.is_file():
            result.problems.append(f"{label}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        check_install(text, label, tag, tags, result)
        check_ref_pairing(text, label, result)
        check_version_tags(text, label, tag, result)
        check_powershell(text, label, result)
        check_macos(text, label, result)
        check_emoji(text, label, result)
        check_claims(text, label, result)
        check_private_hosts(text, label, result)
        check_secrets(text, label, result)
        check_links(text, label, root, result)
        check_alt(text, label, result)
        check_code_fences(text, label, result)
        if label != "README.md":
            check_canonical(text, label, en_h2, result)
            check_examples(text, label, en_text, result)

    for label in START_DOCS:
        path = root / label
        if not path.is_file():
            result.problems.append(f"{label}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        check_install(text, label, tag, tags, result)
        check_ref_pairing(text, label, result)
        check_version_tags(text, label, tag, result)
        check_powershell(text, label, result)
        check_macos(text, label, result)
        check_claims(text, label, result)
        check_links(text, label, root, result)
        check_code_fences(text, label, result)

    readability(en_text, "README.md", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--tag", help="override the expected install tag")
    parser.add_argument("--tags", nargs="*", default=None)
    parser.add_argument("--public", action="store_true", help="verify the install tag on the public repository")
    args = parser.parse_args(argv)
    try:
        if args.public:
            expected = args.tag or shipped_tag(args.root)
            verify_public(args.root)
            if args.tag:
                public_tags(args.tag)
            tags = {expected}
        elif args.tags is not None:
            tags = set(args.tags)
        else:
            tags = None
        result = check(args.root, tag=args.tag, tags=tags)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"readme-check: FAIL - {exc}", file=sys.stderr)
        return 1
    for warning in result.warnings:
        print(f"warning: {warning}")
    for problem in result.problems:
        print(f"problem: {problem}", file=sys.stderr)
    if result.problems:
        print(f"readme-check: FAIL - {len(result.problems)} problem(s)", file=sys.stderr)
        return 1
    print("readme-check: PASS - 0 problem(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
