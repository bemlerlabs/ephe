"""Local project discovery and status analysis for Ephe."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


MARKER_WEIGHTS = {
    ".git": 5,
    "pyproject.toml": 4,
    "package.json": 4,
    "Cargo.toml": 4,
    "go.mod": 4,
    "requirements.txt": 3,
    "README.md": 2,
    "Dockerfile": 2,
    "docker-compose.yml": 2,
    "tests": 2,
    "src": 1,
}

PROJECT_DISCOVERY_CACHE_TTL_SECONDS = 60.0
_DISCOVERY_CACHE: dict[tuple, tuple[float, list[ProjectRecord]]] = {}

IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".next",
    "dist",
    "build",
    ".cache",
    "Library",
    "Applications",
}


@dataclass(frozen=True)
class ProjectRecord:
    name: str
    path: Path
    score: int
    markers: list[str]
    stacks: list[str]


def default_project_roots() -> list[Path]:
    home = Path.home()
    candidates = [
        home / "Developer",
        home / "Projects",
        home / "Projekte",
        home / "Documents",
        home / "Dokumente",
        home / "Desktop",
        home / "Downloads",
    ]
    return [path for path in candidates if path.exists()]


def _is_within_allowed_root(path: Path, roots: list[Path]) -> bool:
    resolved = path.expanduser().resolve()
    for root in roots:
        try:
            resolved.relative_to(root.expanduser().resolve())
            return True
        except ValueError:
            continue
    return False


def _project_markers(path: Path) -> list[str]:
    markers: list[str] = []
    for marker in MARKER_WEIGHTS:
        if (path / marker).exists():
            markers.append(marker)
    return markers


def _detect_stacks(path: Path, markers: list[str]) -> list[str]:
    stacks: list[str] = []
    if "pyproject.toml" in markers or "requirements.txt" in markers:
        stacks.append("python")
    if "package.json" in markers:
        stacks.append("node")
        try:
            package = json.loads((path / "package.json").read_text(encoding="utf-8"))
            deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
            if "react" in deps:
                stacks.append("react")
            if "vite" in deps:
                stacks.append("vite")
            if "next" in deps:
                stacks.append("nextjs")
        except (OSError, json.JSONDecodeError):
            pass
    if "Cargo.toml" in markers:
        stacks.append("rust")
    if "go.mod" in markers:
        stacks.append("go")
    if "Dockerfile" in markers or "docker-compose.yml" in markers:
        stacks.append("docker")
    return stacks or ["unknown"]


def _score_project(path: Path) -> ProjectRecord | None:
    markers = _project_markers(path)
    if not markers:
        return None
    score = sum(MARKER_WEIGHTS[m] for m in markers)
    if score < 4:
        return None
    return ProjectRecord(
        name=path.name,
        path=path.resolve(),
        score=score,
        markers=markers,
        stacks=_detect_stacks(path, markers),
    )


def discover_project_records(
    query: str = "",
    roots: list[Path] | None = None,
    max_results: int = 10,
    max_depth: int = 5,
) -> list[ProjectRecord]:
    search_roots = roots or default_project_roots()
    cache_key = (
        query.strip().lower(),
        tuple(str(root.expanduser().resolve()) for root in search_roots),
        int(max_results),
        int(max_depth),
    )
    now = time.monotonic()
    cached = _DISCOVERY_CACHE.get(cache_key)
    if cached and now - cached[0] < PROJECT_DISCOVERY_CACHE_TTL_SECONDS:
        return cached[1]

    records_by_path: dict[Path, ProjectRecord] = {}
    needle = query.strip().lower()

    for root in search_roots:
        root = root.expanduser()
        if not root.exists() or not root.is_dir():
            continue
        base_depth = len(root.resolve().parts)
        for current, dirs, _files in os.walk(root):
            current_path = Path(current)
            depth = len(current_path.resolve().parts) - base_depth
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
            if depth > max_depth:
                dirs[:] = []
                continue

            record = _score_project(current_path)
            if record is None:
                continue
            searchable = " ".join([record.name, str(record.path), *record.markers, *record.stacks]).lower()
            if needle and needle not in searchable:
                continue
            records_by_path[record.path] = record

    records = sorted(records_by_path.values(), key=lambda r: (-r.score, str(r.path)))[:max_results]
    _DISCOVERY_CACHE[cache_key] = (now, records)
    return records


def format_project_listing(records: list[ProjectRecord]) -> str:
    if not records:
        return "No matching code projects found."
    lines = ["## Found projects"]
    for idx, record in enumerate(records, 1):
        lines.append(
            f"{idx}. **{record.name}** — Score {record.score}\n   Path: `{record.path}`\n   Stack: {', '.join(record.stacks)}\n   Marker: {', '.join(record.markers)}"
        )
    return "\n".join(lines)


def analyze_project_path(path: str | Path) -> str:
    project = Path(path).expanduser().resolve()
    allowed = default_project_roots() + [Path("/tmp"), Path(os.environ.get("TMPDIR", "/tmp"))]
    if not _is_within_allowed_root(project, allowed):
        return f"Access to `{project}` is not allowed."
    if not project.exists() or not project.is_dir():
        return f"project folder not found: `{project}`"

    record = _score_project(project) or ProjectRecord(project.name, project, 0, [], ["unknown"])
    files = {p.name for p in project.iterdir()} if project.exists() else set()
    test_command = _recommended_test_command(record.markers)
    risks: list[str] = []
    if "README.md" not in files:
        risks.append("README.md is missing or not in the project root.")
    if "tests" not in files and not any(name.startswith("test_") for name in files):
        risks.append("No obvious test structure found in the project root.")
    if ".git" not in files:
        risks.append("No git repository detected in the project root.")
    if not risks:
        risks.append("No obvious baseline risks in the quick structure check.")

    return "\n".join([
        f"# Current state: {record.name}",
        f"Path: `{record.path}`",
        f"Score: {record.score}",
        f"Stack: {', '.join(_pretty_stack(s) for s in record.stacks)}",
        f"Marker: {', '.join(record.markers) if record.markers else 'none'}",
        "",
        "## Tests & Betrieb",
        f"Empfohlener Testbefehl: `{test_command}`" if test_command else "No standard test command detected.",
        "",
        "## Risiken",
        *[f"- {risk}" for risk in risks],
        "",
        "## Next steps",
        "- Verify README, install path and start command against the real state.",
        "- Run tests locally and document missing dependencies.",
        "- Prioritize public release risks: installation, privacy, error messages, artifact quality.",
    ])


def _recommended_test_command(markers: list[str]) -> str:
    if "pyproject.toml" in markers or "requirements.txt" in markers:
        return "pytest -q"
    if "package.json" in markers:
        return "npm test"
    if "Cargo.toml" in markers:
        return "cargo test"
    if "go.mod" in markers:
        return "go test ./..."
    return ""


def _pretty_stack(stack: str) -> str:
    return {
        "python": "Python",
        "node": "Node.js",
        "react": "React",
        "vite": "Vite",
        "nextjs": "Next.js",
        "rust": "Rust",
        "go": "Go",
        "docker": "Docker",
        "unknown": "Unknown",
    }.get(stack, stack)
