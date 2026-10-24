"""`scripts/hygiene_check.py` over a planted index, so the leg's two rules are provable offline.

The collision half cannot be planted by writing two files on this machine: macOS runs a
case-insensitive filesystem, so `src/module.py` and `src/Module.py` are one file and the second write
silently overwrites the first. The plant therefore goes through `git update-index --add --cacheinfo`,
which is also how the case-colliding pair arrives in real life -- a Linux or CI commit adding the second
spelling to a tree that already had the first.

The green case runs against the real repository, which is the claim the leg makes on every push: zero
collision groups and zero tracked artifacts over the whole index.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hygiene_check.py"


def new_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "plant@example.invalid"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "plant"], cwd=repo, check=True)
    return repo


def stage(repo: Path, rel: str, content: str = "x\n") -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "--", rel], cwd=repo, check=True)


def stage_virtual(repo: Path, rel: str) -> None:
    """An index entry with no working file, which is what a case collision looks like on this disk."""
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=repo, input=b"x\n",
                          capture_output=True, check=True).stdout.decode().strip()
    # Three arguments, not `--cacheinfo=mode,sha,path`: this git build rejects the single-argument
    # form with "option `cacheinfo' takes no value", which a check=False call would have hidden as a
    # clean-looking index with one file in it.
    subprocess.run(["git", "update-index", "--add", "--cacheinfo", f"100644", blob, rel],
                   cwd=repo, check=True)


def run(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), "--all"], cwd=repo, text=True,
                          capture_output=True, check=False)


class TestPlantedFindings:
    def test_a_case_colliding_pair_is_one_group_naming_both_paths(self, tmp_path):
        repo = new_repo(tmp_path)
        stage(repo, "src/module.py")
        stage_virtual(repo, "src/Module.py")
        done = run(repo)
        assert done.returncode == 1, done.stdout + done.stderr
        assert "case collisions: 1 groups" in done.stdout, done.stdout
        assert "src/Module.py, src/module.py" in done.stdout, done.stdout
        assert "case-insensitive checkout" in done.stderr, done.stderr

    def test_generated_and_private_state_is_named_by_pattern(self, tmp_path):
        repo = new_repo(tmp_path)
        for rel in ("__pycache__/mod.cpython-312.pyc", ".env", "secrets.pem", "node_modules/p/x.js"):
            stage(repo, rel)
        done = run(repo)
        assert done.returncode == 1, done.stdout + done.stderr
        for label in ("python bytecode", "dotenv", "key or certificate", "node modules"):
            assert label in done.stdout, (label, done.stdout)

    def test_a_shipped_dotenv_template_is_not_private_state(self, tmp_path):
        """`AGENTS.md` names `.env.example` as a shipped file, so the refusal targets a dotenv that is
        not a template. Proven here because the pattern once caught the template and the leg would have
        refused a file the repository intends to carry.
        """
        repo = new_repo(tmp_path)
        for rel in (".env.example", ".env.template", ".env.sample", ".env.dist"):
            stage(repo, rel)
        done = run(repo)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "tracked artifacts: 0 files" in done.stdout, done.stdout

    def test_a_dotenv_holding_state_is_refused_even_when_it_looks_like_a_template(self, tmp_path):
        repo = new_repo(tmp_path)
        stage(repo, ".env.local")
        stage(repo, "app/.env.production")
        done = run(repo)
        assert done.returncode == 1, done.stdout
        assert done.stdout.count("dotenv:") == 2, done.stdout

    def test_the_first_party_public_key_is_a_shipped_file(self, tmp_path):
        repo = new_repo(tmp_path)
        stage(repo, "plugins/first-party.pub.pem")
        stage(repo, "plugins/other.pem")
        done = run(repo)
        assert done.returncode == 1, done.stdout + done.stderr
        assert "plugins/first-party.pub.pem" not in done.stdout, done.stdout
        assert "plugins/other.pem" in done.stdout, done.stdout


class TestTooling:
    def test_a_check_without_a_rule_selected_is_refused_by_the_parser(self, tmp_path):
        repo = new_repo(tmp_path)
        done = subprocess.run([sys.executable, str(SCRIPT)], cwd=repo, text=True,
                              capture_output=True, check=False)
        assert done.returncode != 0, done.stdout + done.stderr
        assert "name the check to run" in done.stderr, done.stderr

    def test_the_patterns_are_compiled_once_and_are_named_by_their_rule(self):
        """`--all` reports a rule name per hit, and a pattern stored as a string would raise
        `AttributeError: 'str' object has no attribute 'search'` on the first finding instead of
        reporting it.
        """
        import importlib.util

        spec = importlib.util.spec_from_file_location("hygiene_check", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert set(module.ARTIFACT_PATTERNS) == set(module.ARTIFACT_SOURCES)
        assert all(hasattr(pattern, "search") for pattern in module.ARTIFACT_PATTERNS.values())
        assert len(module.ARTIFACT_PATTERNS) == 12, len(module.ARTIFACT_PATTERNS)


class TestTheRealIndex:
    def test_this_repository_is_clean_under_both_rules(self):
        done = subprocess.run([sys.executable, str(SCRIPT), "--all"], cwd=ROOT, text=True,
                              capture_output=True, check=False)
        assert done.returncode == 0, done.stdout + done.stderr
        # Read the count out of the line the script prints, so a report that stops naming a number
        # fails here rather than comparing an empty string.
        match = re.search(r"hygiene: (\d+) tracked files", done.stdout)
        assert match, done.stdout
        assert int(match.group(1)) > 2000, done.stdout
        assert "case collisions: 0 groups" in done.stdout, done.stdout
        assert "tracked artifacts: 0 files" in done.stdout, done.stdout

    def test_the_local_hook_runs_the_same_script_with_the_same_flag(self):
        text = (ROOT / "scripts" / "ci_local.sh").read_text(encoding="utf-8")
        assert "python3 scripts/hygiene_check.py --all" in text, "the hook drifted from the leg"
        leg = (ROOT / ".github" / "workflows" / "hygiene.yml").read_text(encoding="utf-8")
        assert "python3 scripts/hygiene_check.py --all" in leg, "the leg drifted from the hook"
