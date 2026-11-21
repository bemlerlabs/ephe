"""The Compose file chooses no engine — the operator names it.

The compose file used to ship `EPHE_MODEL_PROVIDER=local_ollama`, a
`EPHE_MODEL=gemma4:12b` default and an unconditional `ollama pull` of that tag,
so the documented `docker compose up` was a silent engine default: the instance
answered with a model nobody chose. AGENTS.md forbids exactly that (no silent
engine default, W18), and `core/engine_config.py` fails closed for every other
start path.

Now the file names neither a provider value nor a model tag, pulls nothing, and
stops on Compose's interpolation error naming the missing variable. The bundled
`ollama` service downloads a tag only when the operator names one
(`EPHE_OLLAMA_PULL`). The docs own half of the contract: both Docker sections
show the explicit command.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.subprocess_env import hermetic_env

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "docker-compose.yml"
DOCKER_DOCS = (ROOT / "docs/INSTALL.md", ROOT / "docs/INSTALL_OPTIONS.md")


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _environment(compose: dict) -> list[str]:
    return [str(entry) for entry in compose["services"]["ephe"]["environment"]]


def _raw(compose: dict, name: str) -> str:
    for entry in _environment(compose):
        if entry.startswith(f"{name}="):
            return entry.split("=", 1)[1]
    raise AssertionError(f"{name} is not in the ephe service environment")


def _default_of(raw: str) -> str:
    """`${VAR:-value}` -> `value`; a required `${VAR:?…}` and a bare `${VAR:-}` yield ''."""
    if ":?" in raw:
        return ""
    match = re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*:-([^}]*)\}", raw.strip())
    return match.group(1) if match else raw.strip()


def test_the_file_names_no_engine_or_model(compose: dict) -> None:
    provider = _raw(compose, "EPHE_MODEL_PROVIDER")
    assert ":?" in provider, f"the provider is not a required choice: {provider}"
    assert _default_of(provider) == "", f"the provider resolves to a default: {provider}"
    assert _default_of(_raw(compose, "EPHE_MODEL")) == "", "a model tag is still a default"
    assert "gemma4" not in COMPOSE.read_text(encoding="utf-8"), (
        "a concrete model tag is named in the compose file"
    )


def test_the_bundled_engine_pulls_only_a_named_tag(compose: dict) -> None:
    ollama = compose["services"]["ollama"]
    environment = [str(entry) for entry in ollama["environment"]]
    assert "EPHE_OLLAMA_PULL=${EPHE_OLLAMA_PULL:-}" in environment
    entrypoint = str(ollama["entrypoint"]).replace('\\"', '"')
    assert "$$EPHE_OLLAMA_PULL" in entrypoint, entrypoint
    pulls = re.findall(r"ollama pull", entrypoint)
    assert len(pulls) == 1, entrypoint
    assert re.search(r'if \[ -n "[^"]*EPHE_OLLAMA_PULL" \]', entrypoint), entrypoint


def test_the_override_for_another_engine_is_still_documented(compose: dict) -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    assert "EPHE_MODEL_PROVIDER=openai_compatible" in text
    assert "EPHE_OPENAI_COMPAT_BASE_URL" in text


@pytest.mark.parametrize("doc", DOCKER_DOCS, ids=lambda path: path.name)
def test_the_docker_docs_show_the_explicit_engine_command(doc: Path) -> None:
    text = doc.read_text(encoding="utf-8")
    sections = text.split("## Docker", 1)
    assert len(sections) == 2, f"{doc.name} has no Docker section"
    section = sections[1].split("\n## ", 1)[0]
    assert "EPHE_MODEL_PROVIDER=" in section, f"{doc.name}: the Docker section names no engine"
    assert "EPHE_MODEL=" in section, f"{doc.name}: the Docker section names no model tag"
    assert "gemma4" not in section, f"{doc.name}: the Docker section names a concrete tag"
    assert "default to `local_ollama`" not in section, (
        f"{doc.name}: the Docker section still claims a Compose default"
    )


def _compose_cli(tmp_path: Path) -> tuple[list[str], dict[str, str]] | None:
    """The compose frontend and the environment that can reach it.

    The plugin may live under the user's `~/.docker/cli-plugins`, so the probe keeps
    HOME: the point is to resolve the file, not to isolate the daemon config.
    """
    if shutil.which("docker") is None:
        return None
    env = hermetic_env(PATH=os.environ["PATH"], HOME=os.environ.get("HOME") or str(tmp_path))
    probe = subprocess.run(
        ["docker", "compose", "version"], capture_output=True, text=True, timeout=30, env=env
    )
    return (["docker", "compose"], env) if probe.returncode == 0 else None


def _run_config(cli: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*cli, "-f", str(COMPOSE), "config"],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        cwd=cwd,
    )


def test_compose_refuses_to_start_without_an_engine(tmp_path: Path) -> None:
    """What Docker actually interpolates with no EPHE_MODEL* in the environment."""
    found = _compose_cli(tmp_path)
    if found is None:
        pytest.skip("no `docker compose` frontend on this machine")
    cli, env = found
    env.pop("EPHE_MODEL_PROVIDER", None)
    env.pop("EPHE_MODEL", None)
    out = _run_config(cli, env, ROOT)
    assert out.returncode != 0, "Compose resolved without an engine choice"
    assert "EPHE_MODEL_PROVIDER" in out.stderr, out.stderr[:400]


def test_compose_resolves_with_the_operators_choice(tmp_path: Path) -> None:
    found = _compose_cli(tmp_path)
    if found is None:
        pytest.skip("no `docker compose` frontend on this machine")
    cli, env = found
    env["EPHE_MODEL_PROVIDER"] = "local_ollama"
    env["EPHE_MODEL"] = "my-tag"
    out = _run_config(cli, env, ROOT)
    assert out.returncode == 0, out.stderr[:400]
    resolved = yaml.safe_load(out.stdout)
    environment = resolved["services"]["ephe"]["environment"]
    if isinstance(environment, list):
        environment = dict(entry.split("=", 1) for entry in environment)
    assert environment["EPHE_MODEL_PROVIDER"] == "local_ollama"
    assert environment["EPHE_MODEL"] == "my-tag"
