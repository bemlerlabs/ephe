"""The README contract: one green surface and a gate for each hard rule.

The real check reads the three READMEs and the four start documents. The unit
cases below invent the failure each rule exists for, so a later edit cannot
turn the gate into prose.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "readme_check_under_test", ROOT / "scripts" / "readme_check.py"
)
readme = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = readme
SPEC.loader.exec_module(readme)


def test_the_readme_contract_is_green():
    result = readme.check(ROOT)
    assert result.problems == [], "\n".join(result.problems)


def _minimal_tree(tmp_path: Path) -> Path:
    root = tmp_path / "tree"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "ephe"\nversion = "0.1.3"\n', encoding="utf-8")
    install = "https://raw.githubusercontent.com/bemlerlabs/ephe/v0.1.3/install.sh"
    headings = "\n\n".join(f"## {name}" for name in readme.EN_SECTIONS)
    (root / "README.md").write_text(f"# Ephe\n\n{headings}\n\n{install}\n", encoding="utf-8")
    for name in ("README.zh-CN.md", "README.es.md"):
        translated = "\n\n".join(f"## Part {number}" for number in range(1, 13))
        (root / name).write_text(f"# Ephe\n\n{translated}\n\n{install}\n", encoding="utf-8")
    for rel in readme.START_DOCS:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# Start\n\n{install}\n", encoding="utf-8")
    return root


def test_an_explicit_tag_is_used_as_given(tmp_path):
    root = _minimal_tree(tmp_path)
    result = readme.check(root, tag="v0.1.3")
    assert result.problems == [], "\n".join(result.problems)


def test_the_shipped_version_is_the_tag(tmp_path):
    """The tree's own version is the only tag source; no release manifest exists."""
    root = _minimal_tree(tmp_path)
    assert readme.shipped_tag(root) == "v0.1.3"
    result = readme.check(root)
    assert result.problems == [], "\n".join(result.problems)


def test_no_concrete_version_is_refused(tmp_path):
    root = _minimal_tree(tmp_path)
    (root / "pyproject.toml").write_text(
        '[project]\nversion = "0.0.0+unknown"\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="concrete"):
        readme.check(root)


def test_offline_cli_derives_the_tag_from_the_version(monkeypatch):
    monkeypatch.setattr(readme.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "v0.0.0\n", ""))
    assert readme.main(["--root", str(ROOT)]) == 0


def test_a_later_version_needs_no_code_changes(tmp_path):
    root = _minimal_tree(tmp_path)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "ephe"\nversion = "9.8.7"\n', encoding="utf-8"
    )
    for rel in ("README.md", "README.zh-CN.md", "README.es.md", *readme.START_DOCS):
        path = root / rel
        path.write_text(
            path.read_text(encoding="utf-8").replace("/v0.1.3/", "/v9.8.7/"),
            encoding="utf-8",
        )
    result = readme.check(root)
    assert result.problems == [], "\n".join(result.problems)


def test_no_tag_evidence_is_a_failure():
    result = readme.Result()
    readme.check_install(
        "https://raw.githubusercontent.com/bemlerlabs/ephe/v9.8.7/install.sh",
        "README.md", "v9.8.7", set(), result,
    )
    assert any("does not exist" in problem for problem in result.problems)


def test_a_missing_public_tag_is_refused(monkeypatch):
    monkeypatch.setattr(
        readme.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, "", ""),
    )
    with pytest.raises(ValueError, match="does not exist"):
        readme.public_tags("v9.8.7")


def test_public_tag_verification_uses_the_public_repository(monkeypatch):
    seen: dict[str, list[str]] = {}

    def remote(args, **kwargs):
        seen["args"] = args
        output = "b" * 40 + "\trefs/tags/v9.8.7\n" + "a" * 40 + "\trefs/tags/v9.8.7^{}\n"
        return subprocess.CompletedProcess(args, 0, output, "")

    monkeypatch.setattr(readme.subprocess, "run", remote)
    assert readme.public_tags("v9.8.7") == {"v9.8.7"}
    assert any("github.com/bemlerlabs/ephe" in arg for arg in seen["args"])


def test_a_foreign_install_tag_is_refused():
    result = readme.Result()
    readme.check_install(
        "https://raw.githubusercontent.com/bemlerlabs/ephe/v0.9.9/install.sh",
        "README.md", "v1.2.3", {"v1.2.3"}, result,
    )
    assert result.problems


@pytest.mark.parametrize("filename, headings", [
    ("README.zh-CN.md", ["Ephe 是什么", "你可以做什么", "一项任务如何进行", "桌面、终端与手机", "快速开始", "需要准备什么", "费用", "隐私与控制权", "插件、技能与连接器", "尚未提供的功能", "遇到问题时", "文档、贡献与许可证"]),
    ("README.es.md", ["Qué es Ephe", "Qué puedes hacer", "Qué ocurre durante una tarea", "Escritorio, terminal y teléfono", "Inicio rápido", "Qué necesitas", "Cuánto cuesta", "Privacidad y control", "Plugins, habilidades y conectores", "Qué falta todavía", "Si algo falla", "Documentación, contribuciones y licencia"]),
])
def test_translations_keep_all_sections_and_executable_examples(filename, headings):
    import re

    english = (ROOT / "README.md").read_text(encoding="utf-8")
    translated = (ROOT / filename).read_text(encoding="utf-8")
    assert readme.h2(translated) == headings
    examples = r"```(?:bash|powershell)\n(.*?)```"
    assert re.findall(examples, translated, re.DOTALL) == re.findall(examples, english, re.DOTALL)


def test_a_powershell_curl_is_refused():
    result = readme.Result()
    readme.check_powershell(
        "```powershell\ncurl -fsSL https://example.test/install.ps1 -o install.ps1\n```",
        "README.md", result,
    )
    assert any("curl" in problem for problem in result.problems)


def test_an_emoji_is_refused():
    result = readme.Result()
    readme.check_emoji("## ⚡ Quick start", "README.md", result)
    assert result.problems


def test_a_claim_is_refused():
    result = readme.Result()
    readme.check_claims("A secure and audited SOTA build.", "README.md", result)
    assert result.problems


def test_a_dead_link_is_refused(tmp_path):
    result = readme.Result()
    readme.check_links("[guide](missing.md)", "README.md", tmp_path, result)
    assert any("missing.md" in problem for problem in result.problems)


def test_an_image_without_alt_is_refused():
    result = readme.Result()
    readme.check_alt("![](shot.png)", "README.md", result)
    assert result.problems


def test_a_bare_code_fence_is_refused():
    result = readme.Result()
    readme.check_code_fences("```\nplain\n```\n", "README.md", result)
    assert result.problems


def test_a_translation_without_banner_or_parity_is_refused():
    result = readme.Result()
    readme.check_canonical("## One\n", "README.zh-CN.md", 12, result)
    assert result.problems


def test_a_canonical_banner_does_not_hide_missing_sections():
    result = readme.Result()
    readme.check_canonical(
        f"<!-- {readme.CANONICAL_MARKER} -->\n## One\n", "README.zh-CN.md", 12, result
    )
    assert result.problems


def test_a_translation_must_keep_the_same_executable_commands():
    result = readme.Result()
    readme.check_examples("```bash\nephe start\n```", "README.es.md", "```bash\nephe configure\n```", result)
    assert result.problems
