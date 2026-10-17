"""I2-4: the Docker surface binds conservatively.

AGENTS.md demands a conservative server binding. The app itself delivers that
(run_server.py --host defaults to 127.0.0.1, 0.0.0.0 only as the --lan opt-in,
and every non-loopback binding forces auth). Docker was the exception:
`docker-compose.yml` published "8765:8765" without a host address, and Docker
binds such a publication to ALL host interfaces — so the project sat on the
local network without anybody doing anything. What is checked here is the host
exposure, not the bind *inside* the container: the Docker proxy reaches the
container's routable IP, and a loopback bind inside the network would be
unreachable from outside (see
test_container_bind_stays_reachable_for_the_proxy).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "docker-compose.yml"
DOCKERFILE = ROOT / "Dockerfile"
README = ROOT / "README.md"


@pytest.fixture(scope="module")
def compose() -> dict:
    assert COMPOSE.exists(), "docker-compose.yml fehlt"
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


_PORT_RE = re.compile(r"^(\$\{[^}]*\}|[^:]+)\s*:\s*(\d+)\s*:\s*(\d+)$")


def _split_port(entry: str) -> tuple[str | None, str, str]:
    """'HOST:PUB:TARGET' -> (HOST, PUB, TARGET); 'PUB:TARGET' -> (None, ...).

    The short form without a host is the failure case: Docker publishes it on all
    host interfaces. The host part may be a ${VAR:-default} substitution.
    """
    m = _PORT_RE.match(entry.strip())
    if m:
        return m.group(1), m.group(2), m.group(3)
    parts = [s.strip() for s in entry.split(":")]
    if len(parts) == 2:
        return None, parts[0], parts[1]
    raise AssertionError(f"Port-Angabe nicht lesbar: {entry!r}")


def _default_of(token: str) -> str:
    """`${VAR:-127.0.0.1}` -> `127.0.0.1`. The default is what counts, because it
    applies when nobody sets the variable — the opt-in lies after that."""
    m = re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*:-([^}]*)\}", token.strip())
    return m.group(1) if m else token.strip()


def _ports_of(compose: dict, service: str) -> list[str]:
    svc = compose.get("services", {}).get(service)
    assert svc, f"Service {service} fehlt in docker-compose.yml"
    ports = svc.get("ports") or []
    # treat the short form "8765:8765" and the long form alike
    out: list[str] = []
    for entry in ports:
        if isinstance(entry, dict):
            host_ip = entry.get("host_ip", "")
            published = str(entry.get("published", ""))
            target = str(entry.get("target", ""))
            out.append(f"{host_ip}:{published}:{target}" if host_ip else f"{published}:{target}")
        else:
            out.append(str(entry))
    return out


def test_ephe_port_is_published_on_loopback_only(compose: dict) -> None:
    """Publishing the API server stays on the host loopback.

    An entry without a host address ("8765:8765") attaches the port to every
    host interface — exactly the thing the release bar demands for mobile access
    as an explicit opt-in.
    """
    assert _ports_of(compose, "ephe"), "ephe publiziert keinen Port"
    for entry in _ports_of(compose, "ephe"):
        host, published, target = _split_port(entry)
        assert host is not None, (
            f"{entry!r} nennt keine Host-Adresse und bindet damit alle Interfaces; "
            "erwartet '127.0.0.1:PORT:PORT' (oder ${VAR:-127.0.0.1}:PORT:PORT)"
        )
        assert _default_of(host) == "127.0.0.1", (
            f"{entry!r}: Default-Bind am Host ist {_default_of(host)!r}, nicht Loopback"
        )
        assert target == "8765", f"{entry!r}: Zielport inesperterweise {target}"
        assert published == target


def test_ollama_port_is_published_on_loopback_only(compose: dict) -> None:
    """The model backend hangs on the loopback for the same reason — an openly
    published 11434 is an unprotected model server on the local network."""
    for entry in _ports_of(compose, "ollama"):
        host, _published, _target = _split_port(entry)
        assert host is not None, f"{entry!r} bindet alle Host-Interfaces"
        assert _default_of(host) == "127.0.0.1", (
            f"{entry!r}: Default-Bind am Host ist {_default_of(host)!r}, nicht Loopback"
        )


def test_compose_documents_the_deliberate_opt_in(compose: dict) -> None:
    """LAN/mobile access stays possible, but only as a visible decision: the file
    names the way there and turns auth on by default."""
    text = COMPOSE.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "127.0.0.1" in text, "keine Loopback-Veroeffentlichung dokumentiert"
    assert "lan" in lowered, "LAN-Modus wird mit keinem Wort erwaehnt"
    env = compose["services"]["ephe"].get("environment", [])
    joined = " ".join(str(e) for e in env)
    assert "EPHE_LAN" in joined, "EPHE_LAN fehlt — Auth waere nicht erzwungen"


def test_dockerfile_bind_is_documented_and_overridable() -> None:
    """The bind inside the container is a reasoned, overridable decision,
    not a bare 0.0.0.0 command-line stone."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "--host" in text, "kein --host im Dockerfile"
    assert "EPHE_BIND" in text or "127.0.0.1" in text, (
        "der Container-Bind ist weder ueberschreibbar noch begruendet"
    )


def test_readme_run_example_publishes_on_loopback() -> None:
    """If the README shows a `docker run` with -p, it may only publish on the loopback."""
    if not README.exists():
        pytest.skip("README.md fehlt")
    text = README.read_text(encoding="utf-8")
    for line in text.splitlines():
        if "docker run" in line and "-p" in line:
            assert "127.0.0.1:" in line, f"{line.strip()} publiziert an alle Interfaces"


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker-CLI nicht verfuegbar")
def test_resolved_compose_binds_loopback() -> None:
    """The bind Docker actually applies, not just the intent written in the YAML.

    `docker compose config` resolves the variables; only here does it show whether
    the default really lands on the loopback or silently falls back to all interfaces.
    """
    if not COMPOSE.exists():
        pytest.skip("docker-compose.yml fehlt")
    # The engine is a declared choice and compose refuses to start without one (`:?`), so
    # this check supplies it; what it measures is the bind Docker applies.
    env = {**os.environ, "EPHE_MODEL_PROVIDER": "local_ollama", "EPHE_MODEL": "a-served-model"}
    out = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), "config"],
        capture_output=True, text=True, cwd=ROOT, timeout=120, env=env,
    )
    assert out.returncode == 0, f"compose config fehlschlug: {out.stderr[:200]}"
    resolved = yaml.safe_load(out.stdout)
    for service in ("ephe", "ollama"):
        ports = resolved["services"][service].get("ports") or []
        assert ports, f"{service} publiziert keinen Port"
        for entry in ports:
            host_ip = entry.get("host_ip") if isinstance(entry, dict) else None
            assert host_ip == "127.0.0.1", (
                f"{service}: Docker wendet host_ip={host_ip!r} an, erwartet 127.0.0.1"
            )
