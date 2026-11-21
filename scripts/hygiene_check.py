#!/usr/bin/env python3
"""Repository hygiene: the rules that are mechanical, in one place.

`CI Gates` and the pre-commit hook both call this file, so local and CI cannot disagree about
what a clean tree is. Case collision is the rule that only bites after a checkout on a
case-insensitive filesystem, which is every macOS box in this pipeline: `git ls-files` can carry
`a.py` and `A.py` while only one of them survives a working tree, so a leg on the laptop and a
leg on the Spark test different trees from the same commit.

Measured on 2026-10-11 over the 2031 tracked files: zero case collisions and zero matches for
every pattern below. That is why both halves exit non-zero -- the gate is written against a tree
that already satisfies it, not against a backlog someone has to read.
"""
from __future__ import annotations

import argparse
import collections
import re
import subprocess
import sys

#: Measured against the 2031 tracked files on 2026-10-11: every entry below matched nothing. A
#: pattern joins this list only once the tree is clean of it, so the file doubles as the record of
#: what the repository has decided never to carry.
#:
#: The entries added on 2026-11-01 were measured the same way over the 2925 tracked files of that
#: date, and against what is on disk but not ignored — a `git ls-files --others --exclude-standard`
#: in this checkout returns three paths, all of them agent-lane worktree directories, which is the
#: class the last entry below names. Each added pattern catches a shape the product itself produces
#: under its config root (`~/.ephe/…`), so a pattern targets a directory the sources do not use: the
#: store dump classes bind a filename inside a directory, and the bare word is ordinary here
#: (`artifacts/` alone covers 53 tracked paths — 24 sources under `app/src`, 29 marketplace files —
#: and `.jsonl` alone covers 18, most of them the committed benchmark corpus).

ARTIFACT_SOURCES = {
    "python bytecode": r"(^|/)__pycache__/|\.pyc$",
    "macos metadata": r"(^|/)\.DS_Store$",
    "node modules": r"(^|/)node_modules/",
    "local database": r"\.(db|sqlite3?|db-wal|db-shm)$",
    # `.env.example` and its siblings are templates this repository ships on purpose (AGENTS.md
    # names one); only a dotenv that is not a template is private state.
    "dotenv": r"(^|/)\.env(\.(?!(example|template|sample|dist)$)[^/]+)?$",
    "key or certificate": r"\.(pem|key|p12|pfx)$",
    "virtualenv": r"(^|/)\.venv/|(^|/)venv/",
    "build output": r"(^|/)dist/|\.egg-info/",
    "tool cache": (r"(^|/)\.cache/|(^|/)\.pytest_cache/|(^|/)\.mypy_cache/"
                   r"|(^|/)\.ruff_cache/|(^|/)\.coverage$|(^|/)coverage\.xml$"),
    "log file": r"\.log$",
    "patched wheel tree": r"(^|/)_patched/",
    "pth pointer": r"\.pth$",
    # A session store is JSON, so `local database` (the only store class here before this wave)
    # says nothing about it. Written by core/multi_session.py into the config root.
    "session store dump": r"(^|/)sessions/[^/]+\.json$",
    # Vision captures and recordings land beside the store they belong to
    # (server/routes/vision.py, server/routes/audio.py); a curated asset lives in `app/public`
    # or `docs` and never inside a session directory.
    "session media capture": r"(^|/)sessions/(audio|images)/",
    # The artifact workbench writes one directory per session or per benchmark run
    # (core/engine_config.py, `~/.ephe/artifacts/<session>`). The run-directory shape is required:
    # `(^|/)artifacts/` alone is 48 tracked sources under app/src.
    "artifact workbench dump": (r"(^|/)artifacts/([0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}"
                               r"|bench-[a-z]+-[0-9]+)/"),
    # The run ledger appends one JSONL per run id (core/run/ledger.py). `core/run/` is a package
    # directory of .py files, so a JSONL inside it is state that followed a config override.
    "run ledger jsonl": r"(^|/)run/[^/]+\.jsonl$",
    # Turn counters and the trajectory cache, each a single file the engine writes on the config
    # root; neither is a template and neither has a reason to be reviewed by hand.
    "usage ledger jsonl": r"(^|/)(usage|ephemeris)\.jsonl$|(^|/)trajectory\.json$",
    # The config root itself, when a run is pointed at a checkout with EPHE_CONFIG_DIR instead of
    # the home directory. Named by the directory, because its contents are every class above.
    "project-local state dir": r"(^|/)\.ephe(/|$)",
    # The persisted engine choice and its key file, including the backup siblings the app leaves
    # (`engine.json.bak-<stamp>`, `engine.key.pre-<provider>`). `engine.example.json` is the shipped
    # template and the anchored `engine.` prefix keeps it out.
    "live engine config": r"(^|/)engine\.(json|key)(\.[^/]+)?$",
    # The memory store's own tree: the Kepta SQLite files sit under a per-profile id directory
    # that `local database` catches by extension, while the profile and provider JSON beside it
    # carry the user's name and endpoint and match nothing else here.
    "memory store export": r"(^|/)memory/(kepta(/|$)|provider\.json$|user_profile\.json$)",
    # pytest-benchmark writes its history directory on every local run, and a `--benchmark-save`
    # leaves one behind; `tool cache` names only the caches measured before this wave.
    "bench runner output": r"(^|/)\.benchmarks(/|$)",

    # Model weights: a downloaded or exported model is gigabytes of machine-local state, and the
    # embedding runtime reads its ONNX file from the config root rather than from the package.
    "model weight blob": r"\.(onnx|gguf|safetensors)$",
    # An agent lane checks out a full copy of this tree beside the checkout it was sent from. On
    # the day this was measured the three live lanes held 42481, 41436 and 4090 files, so a broad
    # `git add` here would stage every one of them — including whatever a run of the product left
    # inside its own copy. Nothing under `.qoder/` is tracked, and `.gitignore` now names it.
    "lane worktree": r"(^|/)\.qoder(/|$)",
}

ARTIFACT_PATTERNS = {name: re.compile(src) for name, src in ARTIFACT_SOURCES.items()}

#: A public verification key ships so signatures can be checked; it is not private state.
PUBLIC_KEYS = frozenset({"plugins/first-party.pub.pem"})


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True, text=True)
    return [p for p in out.stdout.split("\0") if p]


def case_collisions(files: list[str]) -> list[tuple[str, list[str]]]:
    groups: dict[str, list[str]] = collections.defaultdict(list)
    for path in files:
        groups[path.casefold()].append(path)
    return sorted((k, v) for k, v in groups.items() if len(v) > 1)


def tracked_artifacts(files: list[str]) -> list[tuple[str, str]]:
    hits = []
    for name, pattern in ARTIFACT_PATTERNS.items():
        for path in files:
            if pattern.search(path) and path not in PUBLIC_KEYS:
                hits.append((name, path))
    return sorted(hits)


def report(files: list[str]) -> int:
    collisions = case_collisions(files)
    artifacts = tracked_artifacts(files)
    print(f"hygiene: {len(files)} tracked files")
    print(f"  case collisions: {len(collisions)} groups")
    for folded, paths in collisions:
        print(f"    {folded}: {', '.join(paths)}")
    print(f"  tracked artifacts: {len(artifacts)} files across {len(ARTIFACT_PATTERNS)} patterns")
    for kind, path in artifacts:
        print(f"    {kind}: {path}")
    if collisions:
        print("::error::case-colliding paths -- only one of each survives a case-insensitive "
              "checkout, so the legs on macOS and Linux are not testing the same tree",
              file=sys.stderr)
    if artifacts:
        print("::error::generated or private state is tracked -- caches, databases and key "
              "material belong to a machine, not to a commit", file=sys.stderr)
    return 1 if (collisions or artifacts) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--all", action="store_true", help="check every rule and exit non-zero on any finding")
    args = parser.parse_args(argv)
    if args.all:
        return report(tracked_files())
    parser.error("name the check to run, for example --all")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
