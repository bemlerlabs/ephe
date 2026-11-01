"""The state classes Ephe itself produces are refused, and the assets it ships are not.

`scripts/hygiene_check.py` runs over `git ls-files`, so its rules are only provable against a tree
that already has the state in it -- and a tree with a live session store in it is the thing the
repository promises never to carry. The plant therefore goes through the module's own pure
functions, `tracked_artifacts()` and `case_collisions()`, over a file list rather than over files:
every shape below is read out of the code that writes it (core/multi_session.py,
core/run/ledger.py, core/engine_config.py, server/routes/vision.py), so the pattern is checked
against the name the product actually produces and not against an invented one.

The second half matters as much as the first. A guard that fires on our own assets is worse than
no guard, because the next person disables the leg instead of the file: `app/public` and `docs`
carry images and video on purpose, `.env.example` and `engine.example.json` are templates the
installer points at, and `evals/trajectories.jsonl` is a committed benchmark corpus whose
extension alone looks like a transcript. Both directions are asserted here.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hygiene_check.py"

_spec = importlib.util.spec_from_file_location("hygiene_check", SCRIPT)
assert _spec is not None and _spec.loader is not None
_hygiene = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hygiene)

tracked_artifacts = _hygiene.tracked_artifacts
case_collisions = _hygiene.case_collisions
ARTIFACT_PATTERNS = _hygiene.ARTIFACT_PATTERNS

#: The classes this wave added, each paired with a path holding the shape the product writes.
STATE_CLASSES = {
    "session store dump": [
        "sessions/registry.json",
        "sessions/ef3b9c2a.json",
        "sessions/pwa-14e7fe29-ad4b-4f3d-b628-addaad95d5ee.json",
    ],
    "session media capture": [
        "sessions/audio/20261028_170407_49f72c0f.webm",
        "sessions/images/browser_1792737635.jpeg",
    ],
    "artifact workbench dump": [
        "artifacts/03d82f15-1039-468a-9a58-b30364b887a3/report.pdf",
        "artifacts/bench-documents-1/ephe_qrCode.png",
    ],
    "run ledger jsonl": ["run/01c5df1037f1.jsonl", "core/run/01c5df1037f1.jsonl"],
    "usage ledger jsonl": ["usage.jsonl", "ephemeris.jsonl", "trajectory.json"],
    "project-local state dir": [".ephe/sessions/registry.json", "workspace/.ephe/index.db"],
    "live engine config": [
        "engine.json",
        "engine.key",
        "engine.key.binding.json",
        "engine.json.bak-20261028T201820Z",
        "engine.json.nemotron-backup",
    ],
    "memory store export": [
        "memory/kepta/06e96ec17bbe8278/kepta.db",
        "memory/user_profile.json",
        "memory/provider.json",
    ],
    "bench runner output": [".benchmarks/bench-timing-py3.13.17-s2.json"],
    "model weight blob": ["core/models/embedding.onnx", "models/builder.gguf",
                          "weights/scores.safetensors"],
    "lane worktree": [".qoder/worktrees/agent-lane-4f2ad1/scripts/hygiene_check.py",
                      ".qoder/config.json"],
}

#: Tracked paths that must stay invisible to every pattern, including the pre-existing ones. Each
#: entry is read from this checkout below, so the list cannot quietly drift into fiction while still
#: claiming to prove the guard does not cry wolf.
LEGITIMATE = [
    ".env.example", "engine.example.json", "plugins/first-party.pub.pem",
    "app/public/apple-touch-icon-180.png", "app/public/favicon.png",
    "app/public/backgrounds/black-forest-mist.jpg",
    "app/public/onboarding/first-run-film.webm",
    "app/public/onboarding/first-run-film.mp4",
    "docs/screenshots/readme-chat-1280.png",
    "evals/trajectories.jsonl", "evals/judge/labels.jsonl",
    "plugins/documents/prompts/golden.jsonl", "plugins/memory/prompts/golden.jsonl",
    "core/run/__init__.py", "core/run/ledger.py", "core/engine_config.py",
    "core/session.py", "core/session_lifecycle.py", "core/session_search.py",
    "core/settings_hints.py", "core/audit_log.py", "plugins/memory/ephe-plugin.json",
    "app/src/components/dashboard/artifacts/adoptFlow.ts",
    "app/src/components/dashboard/artifacts/detail.tsx",
    "app/src/components/dashboard/artifacts/duplicateOrigin.test.tsx",
    "app/tests/playwright/artifact-export.spec.ts",
    "run_server.py", "ephe.py", "ephe_cli.py",
    "skills-lock.json", "uv.lock", "app/package.json", ".github/workflows/hygiene.yml",
    "ui/app.py", "tests/fixtures/memory_embed_golden.json",
]

#: Paths this tree does not carry yet but could acquire as ordinary source, in the same words the
#: state classes match on. A state pattern that fires here has made future source uncommittable.
LOOKALIKE_SOURCE = [
    "app/src/stores/session.ts", "app/src/sessions-view/Panel.tsx",
    "app/src/features/artifacts/artifactStore.test.ts", "ui/sessions/registry.ts",
    "core/engine/config.py", "docs/run/README.md", "evals/corpus/usage_notes.jsonl",
    "app/src/components/memory/user_profile_card.tsx",
]



class TestStateClasses:
    def test_each_new_class_catches_the_shape_its_writer_produces(self):
        hits = {name: set() for name in STATE_CLASSES}
        for name, paths in STATE_CLASSES.items():
            found = {path for kind, path in tracked_artifacts(paths) if kind == name}
            assert found == set(paths), (name, sorted(found ^ set(paths)))
            hits[name] = found

    def test_a_file_inside_the_config_root_is_named_by_two_classes(self):
        """Deliberate overlap: `project-local state dir` names the root, the content class names
        what the file is, and a report that prints both tells a reviewer the finding is doubly
        private rather than making the two rules compete for one path.
        """
        doubly = {"sessions/registry.json": {"session store dump"},
                  ".ephe/sessions/registry.json": {"project-local state dir", "session store dump"},
                  "workspace/.ephe/index.db": {"project-local state dir", "local database"},
                  "memory/kepta/06e96ec17bbe8278/kepta.db": {"memory store export",
                                                             "local database"}}
        for path, expected in doubly.items():
            kinds = {kind for kind, hit in tracked_artifacts([path]) if hit == path}
            assert kinds == expected, (path, sorted(kinds))

    def test_a_planted_state_file_makes_the_gate_refuse(self):
        planted = [path for paths in STATE_CLASSES.values() for path in paths]
        refused = {path for _, path in tracked_artifacts(planted)}
        assert refused == set(planted), sorted(planted) ^ sorted(refused)
        kinds = {kind for kind, _ in tracked_artifacts(planted)}
        assert kinds >= set(STATE_CLASSES), sorted(set(STATE_CLASSES) - kinds)
        # Two shapes are private twice over: `engine.key` ends in `.key` and the Kepta and
        # index SQLite files end in `.db`, so the pre-existing rules name them as well.
        assert kinds - set(STATE_CLASSES) == {"key or certificate", "local database"}, sorted(kinds)

    def test_the_pre_existing_classes_still_catch_after_the_additions(self):
        """The additions share one dict with the original twelve rules, so a regression there is
        a regression here.
        """
        shapes = {
            "python bytecode": "core/__pycache__/chat.cpython-313.pyc",
            "macos metadata": "core/.DS_Store",
            "node modules": "app/node_modules/x/index.js",
            "local database": "memory/search.db",
            "dotenv": ".env.local",
            "key or certificate": "deploy/host.pem",
            "virtualenv": ".venv/bin/python",
            "build output": "app/dist/index.html",
            "tool cache": ".pytest_cache/v/cache/nodeids",
            "log file": "var/run/ephe.log",
            "patched wheel tree": "_patched/cell/policy.py",
            "pth pointer": "site-packages/ephe.pth",
        }
        for name, path in shapes.items():
            caught = {kind for kind, hit in tracked_artifacts([path]) if hit == path}
            assert name in caught, (name, path, sorted(caught))

    def test_the_new_classes_are_named_entries_with_a_compiled_pattern(self):
        for name in STATE_CLASSES:
            assert name in ARTIFACT_PATTERNS, name
            assert hasattr(ARTIFACT_PATTERNS[name], "search"), name

    def test_every_new_pattern_is_anchored_or_suffix_bound(self):
        """An unanchored `sessions/` matches a source directory; the classes here either name the
        directory they sit in or bind the extension at the end of the path.
        """
        for name in STATE_CLASSES:
            src = _hygiene.ARTIFACT_SOURCES[name]
            assert "(^|/)" in src or src.endswith("$") or "\\." in src, (name, src)


class TestLegitimatePaths:
    def test_the_guarded_asset_list_is_this_checkout(self):
        """The list is only a wolf test while it names files that exist here; a stale entry would
        let the class pass on fiction.
        """
        files = set(subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                                   text=True, check=True).stdout.split("\n"))
        absent = [p for p in LEGITIMATE if p not in files]
        assert absent == [], absent

    def test_shipped_templates_public_keys_and_media_are_not_caught(self):
        assert tracked_artifacts(LEGITIMATE) == []

    def test_a_source_path_using_the_same_word_is_not_caught(self):
        assert tracked_artifacts(LOOKALIKE_SOURCE) == []

    def test_the_state_words_alone_do_not_match_a_source_path(self):
        """`artifacts/` and `.jsonl` are ordinary parts of this tree: 53 tracked paths live under an
        `artifacts/` directory and the committed corpus is JSONL. The patterns bind a filename
        inside a directory, so the bare word stays committable.
        """
        sources = [
            "app/src/components/dashboard/artifacts/adoptFlow.ts",
            "app/src/features/artifacts/artifactStore.test.ts",
            "evals/trajectories.jsonl",
            "plugins/guide/prompts/golden.jsonl",
            "docs/media/user-walkthrough-2026-10-12/plan-accept/trace.jsonl",
        ]
        assert tracked_artifacts(sources) == []


    def test_an_example_engine_config_is_not_the_persisted_one(self):
        assert tracked_artifacts(["engine.example.json", "app/engine.example.json"]) == []
        assert tracked_artifacts(["engine.json", "app/engine.json"]) == [
            ("live engine config", "app/engine.json"),
            ("live engine config", "engine.json"),
        ]

    def test_the_existing_allow_list_still_holds(self):
        assert "plugins/first-party.pub.pem" in _hygiene.PUBLIC_KEYS
        assert tracked_artifacts(["plugins/first-party.pub.pem"]) == []


class TestTheRealTree:
    def test_this_repository_is_clean_under_every_state_class(self):
        done = subprocess.run([sys.executable, str(SCRIPT), "--all"], cwd=ROOT, text=True,
                              capture_output=True, check=False)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "tracked artifacts: 0 files" in done.stdout, done.stdout
        match = re.search(r"across (\d+) patterns", done.stdout)
        assert match and int(match.group(1)) == len(ARTIFACT_PATTERNS), done.stdout

    def test_no_tracked_path_of_this_checkout_is_state(self):
        """Runs the same file list the hook runs, so a pattern added here cannot be green only
        against the plant above.
        """
        files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True,
                               text=True, check=True).stdout.split("\0")
        files = [p for p in files if p]
        # The tree carried 2031 tracked files when this gate was written and 2925 when the state
        # classes joined it, so a list under 2000 is a short read, not a slimmed-down repository.
        assert len(files) > 2000, len(files)
        assert tracked_artifacts(files) == []
        assert case_collisions(files) == []
