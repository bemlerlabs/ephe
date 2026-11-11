"""QA residue 2 — `docker compose up` runs the quickstart the docs promise.

`docs/INSTALL.md` and `docs/INSTALL_OPTIONS.md` both show `docker compose up` as the
whole Docker path, while the compose file required `EPHE_MODEL_PROVIDER` and `EPHE_MODEL`
with `${VAR:?…}` and aborted before a container started.

The file already ships the engine it means: an `ollama` service that pulls one tag, and
an in-network OLLAMA_HOST default. The two engine variables now default to exactly that
service and that tag, so the documented command starts the stack, and an operator who
wants another engine still overrides both variables (the override block stays in the
file). The app's own "no silent default" rule (W18, `core/engine_config.py`) is untouched:
nothing is guessed at run time — this packaging file names its engine.
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


def _default_of(raw: str) -> str | None:
    """`${VAR:-value}` -> `value`; a plain value is its own default."""
    match = re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*:-([^}]*)\}", raw.strip())
    return match.group(1) if match else raw.strip()


def test_no_engine_variable_aborts_before_the_stack_starts(compose: dict) -> None:
    for name in ("EPHE_MODEL_PROVIDER", "EPHE_MODEL"):
        raw = _raw(compose, name)
        assert ":?" not in raw, f"{name} still aborts without an override: {raw}"
        assert _default_of(raw), f"{name} resolves to nothing: {raw}"


def test_the_default_engine_is_the_service_the_file_starts(compose: dict) -> None:
    assert _default_of(_raw(compose, "EPHE_MODEL_PROVIDER")) == "local_ollama"
    assert _default_of(_raw(compose, "OLLAMA_HOST")).endswith("//ollama:11434")


def test_the_default_model_is_the_tag_the_bundled_engine_pulls(compose: dict) -> None:
    entrypoint = str(compose["services"]["ollama"]["entrypoint"])
    pulled = re.search(r"ollama pull ([^\s&;\"']+)", entrypoint)
    assert pulled, entrypoint
    assert _default_of(_raw(compose, "EPHE_MODEL")) == pulled.group(1)


def test_the_override_for_another_engine_is_still_documented(compose: dict) -> None:
    text = COMPOSE.read_text(encoding="utf-8")
    assert "EPHE_MODEL_PROVIDER=openai_compatible" in text
    assert "EPHE_OPENAI_COMPAT_BASE_URL" in text


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


def test_compose_resolves_without_any_engine_environment(tmp_path: Path) -> None:
    """What Docker actually interpolates, with no EPHE_MODEL* in the environment."""
    found = _compose_cli(tmp_path)
    if found is None:
        pytest.skip("no `docker compose` frontend on this machine")
    cli, env = found
    out = subprocess.run(
        [*cli, "-f", str(COMPOSE), "config"],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        cwd=ROOT,
    )
    assert out.returncode == 0, out.stderr[:400]
    resolved = yaml.safe_load(out.stdout)
    environment = resolved["services"]["ephe"]["environment"]
    assert environment["EPHE_MODEL_PROVIDER"] == "local_ollama"
    assert environment["EPHE_MODEL"]
