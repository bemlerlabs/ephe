"""WB-13 / G1: the docker head is binding again.

`docker`/`docker-compose` stay in ALLOWED_COMMANDS, but `validate_shell_command`
now reads their argv: only read-only subcommands pass, and the host-handing flags
are refused. These are the probes that reached the host root before.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.tools.shell_tools import validate_shell_command
from server.main import create_app

XHR_HEADERS = {"X-Requested-With": "XMLHttpRequest"}

# The probe from docs/HOST_EXEC_BOUNDARY_REVIEW_2026-10-11.md, verbatim.
HOST_ROOT_ESCAPE = "docker run --privileged -v /:/host alpine sh -c 'cat /host/etc/shadow'"


def _refused(command: str) -> str:
    refusal = validate_shell_command(command)
    assert refusal is not None, f"expected a refusal for: {command}"
    assert "⚠" in refusal and "Security" in refusal
    return refusal


class TestEscapeIsRefused:
    def test_recorded_probe_is_refused(self):
        _refused(HOST_ROOT_ESCAPE)

    def test_mount_without_privileged_is_refused(self):
        _refused("docker run -v /etc:/h alpine cat /h/passwd")

    def test_mount_flag_alone_is_refused(self):
        _refused("docker run --mount type=bind,source=/,target=/host alpine ls /host")

    @pytest.mark.parametrize(
        "subcommand",
        [
            "run", "exec", "create", "start", "build", "pull", "push",
            "cp", "commit", "save", "load", "import", "export",
            "rm", "rmi", "kill", "stop", "restart", "pause", "unpause",
            "volume", "network", "system", "container", "image", "compose",
        ],
    )
    def test_container_creating_subcommands_are_refused(self, subcommand):
        _refused(f"docker {subcommand} whatever")

    @pytest.mark.parametrize(
        "command",
        [
            "docker-compose up",
            "docker-compose run alpine sh",
            "docker-compose exec web sh",
            "docker-compose down",
            "docker-compose build",
            # 'inspect' is docker-only; the compose allowlist is its own set.
            "docker-compose inspect web",
            # plugin form: 'compose' is not a read-only docker subcommand.
            "docker compose up",
            "docker compose ps",
        ],
    )
    def test_compose_paths_are_refused(self, command):
        _refused(command)

    def test_bare_heads_are_refused(self):
        _refused("docker")
        _refused("docker-compose")

    def test_host_flag_deny_binds_even_under_an_allowed_subcommand(self):
        # The flag layer is independent of the subcommand: a host-handing flag is
        # refused even when the subcommand itself is read-only.
        assert "flag" in _refused("docker ps --privileged")
        assert "flag" in _refused("docker inspect -v /:/host web")
        assert "flag" in _refused("docker logs --volume=/:/host web")

    def test_flag_with_equals_value_is_caught(self):
        assert "flag" in _refused("docker ps --mount=/:/host")


class TestSegmentChaining:
    def test_a_docker_escape_behind_a_clean_segment_is_refused(self):
        _refused("ls && docker run -v /:/host alpine sh")
        _refused("git status; docker run --privileged -v /:/host alpine")

    def test_a_clean_docker_inspection_segment_passes(self):
        assert validate_shell_command("ls && docker ps") is None
        assert validate_shell_command("git status && docker logs web") is None


class TestSandboxDoesNotLiftDockerHardening:
    def test_sandboxed_true_still_refuses_the_escape(self):
        # Seatbelt contains the local process; the daemon runs the container outside it.
        assert validate_shell_command(HOST_ROOT_ESCAPE, sandboxed=True) is not None
        assert validate_shell_command("docker exec web sh", sandboxed=True) is not None


class TestLegitimateInspectionStaysAllowed:
    @pytest.mark.parametrize(
        "command",
        [
            "docker ps",
            "docker ps -a",
            "docker ps -q",
            "docker images",
            "docker version",
            "docker info",
            "docker logs -f web",
            "docker inspect web",
            "docker port web",
            "docker stats --no-stream",
            "docker top web",
            "docker history web",
            "docker-compose ps",
            "docker-compose logs --tail 50 web",
            "docker-compose config",
            "docker-compose version",
        ],
    )
    def test_read_only_subcommands_pass(self, command):
        assert validate_shell_command(command) is None


class TestRouteLevel:
    def test_escape_refused_through_post_api_shell(self):
        client = TestClient(create_app())
        r = client.post("/api/shell", json={"command": HOST_ROOT_ESCAPE, "approved": True}, headers=XHR_HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert "Security" in data["output"]
