"""The public pairing hop asks first, verifies its peer and ends on its own.

`GET /api/mobile/qr` in `auto` mode opened a public tunnel whenever the LAN probe
failed, from inside the same branch whose message told the operator that public
mode needs an explicit choice. The hop ran with `StrictHostKeyChecking=no`, so a
device between this machine and the endpoint could terminate the reverse tunnel
and read or inject what it carried, and the ssh process lived until the server
exited. The owner set four bounds on 2026-11-20: `auto` never publishes, the hop
is pinned to a repository-owned key, the exposure has an idle end, and the
sentence in the answer and the behaviour behind it cannot drift apart.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.main import create_app
from utils import tunnel as tunnel_module
from utils.tunnel import TunnelManager, _extract_public_tunnel_url

REPO = Path(__file__).resolve().parent.parent

#: The sentence the LAN-dead branch answers with. The product promises public
#: pairing only on an explicit choice, so this text and the branch below it are
#: one claim; a rewording has to be a decision taken here as well.
LAN_DEAD_MESSAGE = (
    "Ephe is in LAN mode, but this Mac is not answering on the Wi-Fi address. "
    "Allow Python/Terminal in macOS Firewall or Local Network permissions, then reopen the QR. "
    "Public QR is available only when you choose public mode explicitly."
)

TUNNEL_URL = "https://a1b2c3.lhr.life"


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def dead_lan(monkeypatch):
    """The firewall case: a LAN bind whose Wi-Fi address never answers."""
    monkeypatch.delenv("EPHE_MOBILE_HOST", raising=False)
    monkeypatch.delenv("EPHE_SKIP_LAN_PROBE", raising=False)
    monkeypatch.setattr("server.routes.mobile.get_local_ip", lambda: "10.0.0.99")
    monkeypatch.setattr("server.routes.mobile._is_docker_runtime", lambda: False)
    monkeypatch.setattr("server.routes.mobile._lan_probe_succeeds", lambda base_url: False)


class _TunnelTripwire:
    """Stands in for the public hop and records every attempt to open it."""

    def __init__(self):
        self.calls: list[tuple] = []

    def __call__(self, port, *rest):
        self.calls.append((port, rest))
        return TUNNEL_URL


class _FakeProcess:
    """The ssh subprocess, alive until something terminates it."""

    def __init__(self, argv, lines=()):
        self.argv = list(argv)
        self.returncode = None
        self.terminated = False
        self.killed = False
        self._lines = list(lines)

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return 0

    @property
    def stdout(self):
        return iter(self._lines)


class _FakeClock:
    """A monotonic clock the test advances by hand, including the sleeps."""

    def __init__(self, start=1000.0):
        self.now = start

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class _FakeSsh:
    """The ssh client and its Popen, with the process lines the endpoint prints."""

    def __init__(self, clock):
        self.clock = clock
        self.processes: list[_FakeProcess] = []
        self.lines: list[str] = []
        self.which_result = "/usr/bin/ssh"

    def which(self, name):
        return self.which_result

    def popen(self, argv, **kwargs):
        process = _FakeProcess(argv, self.lines)
        self.processes.append(process)
        return process


@pytest.fixture
def ssh(monkeypatch):
    driver = _FakeSsh(_FakeClock())
    monkeypatch.setattr(tunnel_module.shutil, "which", driver.which)
    monkeypatch.setattr(tunnel_module.subprocess, "Popen", driver.popen)
    monkeypatch.setattr(tunnel_module, "time", driver.clock)
    yield driver
    tunnel_module.tunnel_manager.stop()


def _wait_for(predicate, timeout=2.0):
    """The monitor thread classifies what ssh printed; this is where the test meets it."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


# 1. `auto` never publishes


def test_auto_with_a_dead_lan_opens_no_public_tunnel(client, dead_lan, monkeypatch):
    """GIVEN the LAN is unreachable and the mode is auto
    WHEN the pairing surface asks for a QR
    THEN the public hop is never started and the answer says what to do next
    """
    tripwire = _TunnelTripwire()
    monkeypatch.setattr("server.routes.mobile._start_public_tunnel", tripwire)

    response = client.get("/api/mobile/qr")

    assert response.status_code == 200, response.text
    assert tripwire.calls == [], "auto must not open a public tunnel on its own"
    data = response.json()
    assert data["is_public"] is False
    assert data["mode"] != "public"
    assert data["url"].startswith("http://10.0.0.99:")
    assert data["public_offer"] is True, "the surface needs an explicit way into public mode"
    assert data["message"] == LAN_DEAD_MESSAGE


def test_auto_with_a_reachable_lan_offers_nothing_public(client, monkeypatch):
    """A working LAN is no reason to mention the public path at all."""
    tripwire = _TunnelTripwire()
    monkeypatch.delenv("EPHE_MOBILE_HOST", raising=False)
    monkeypatch.setattr("server.routes.mobile.get_local_ip", lambda: "10.0.0.99")
    monkeypatch.setattr("server.routes.mobile._is_docker_runtime", lambda: False)
    monkeypatch.setattr("server.routes.mobile._lan_probe_succeeds", lambda base_url: True)
    monkeypatch.setattr("server.routes.mobile._start_public_tunnel", tripwire)

    data = client.get("/api/mobile/qr").json()

    assert tripwire.calls == []
    assert data["lan_reachable"] is True
    assert data["public_offer"] is False
    assert data["message"] == ""


def test_public_mode_still_opens_the_tunnel_and_answers_the_url(client, monkeypatch):
    """The capability survives: one deliberate click, and the public URL is there."""
    tripwire = _TunnelTripwire()
    monkeypatch.setattr("server.routes.mobile._start_public_tunnel", tripwire)

    response = client.get("/api/mobile/qr", params={"mode": "public"})

    assert response.status_code == 200, response.text
    assert len(tripwire.calls) == 1
    data = response.json()
    assert data["is_public"] is True
    assert data["mode"] == "public"
    assert data["url"] == f"{TUNNEL_URL}/mobile.html"
    assert data["requires_internet"] is True
    assert data["message"] == ""


def test_a_blocked_public_answer_names_the_refusal_and_opens_nothing(client, monkeypatch):
    """A refused hop answers with no public URL and the reason the surface renders."""

    def blocked(port, *rest):
        tunnel_module.tunnel_manager.block_reason = "host_key_unverified"
        return None

    monkeypatch.delenv("EPHE_MOBILE_HOST", raising=False)
    monkeypatch.setattr("server.routes.mobile.get_local_ip", lambda: "10.0.0.99")
    monkeypatch.setattr("server.routes.mobile._is_docker_runtime", lambda: False)
    monkeypatch.setattr("server.routes.mobile._start_public_tunnel", blocked)

    data = client.get("/api/mobile/qr", params={"mode": "public"}).json()

    assert data["is_public"] is False
    assert data["mode"] != "public"
    assert not data["url"].startswith(TUNNEL_URL)
    assert data["tunnel_block"] == "host_key_unverified"


def test_a_public_answer_carries_the_exposure_state(client, monkeypatch):
    """How long the hop has been up and when it ends are part of the answer."""
    monkeypatch.setattr("server.routes.mobile._start_public_tunnel", _TunnelTripwire())
    monkeypatch.setattr(
        "server.routes.mobile.tunnel_manager",
        _StatefulManager(uptime=42.0, stops_in=1758.0),
    )

    data = client.get("/api/mobile/qr", params={"mode": "public"}).json()

    assert data["is_public"] is True
    assert data["tunnel_uptime_seconds"] == 42.0
    assert data["tunnel_stops_in_seconds"] == 1758.0


class _StatefulManager:
    """The manager's readable state as the route sees it."""

    block_reason = ""

    def __init__(self, uptime, stops_in):
        self._uptime = uptime
        self._stops_in = stops_in

    def uptime_seconds(self):
        return self._uptime

    def stops_in_seconds(self):
        return self._stops_in


# 2. The hop is pinned


def test_the_ssh_command_pins_the_endpoint_host_key(ssh):
    """GIVEN the manager builds its ssh command
    WHEN the argv is read back
    THEN it verifies strictly against the file this repository owns
    """
    manager = TunnelManager()
    manager.start_tunnel(8765, 60, watchdog=False)

    assert ssh.processes, "the hop should have been started"
    argv = ssh.processes[0].argv
    joined = " ".join(argv)
    assert "StrictHostKeyChecking=no" not in joined
    assert "StrictHostKeyChecking=yes" in argv or "-oStrictHostKeyChecking=yes" in argv
    known_hosts = [arg for arg in argv if arg.startswith("UserKnownHostsFile=")]
    assert known_hosts, "the trust anchor has to be named on the command line"
    pinned = Path(known_hosts[0].split("=", 1)[1])
    assert pinned.is_file()
    assert pinned == tunnel_module.KNOWN_HOSTS_FILE
    # The user's own known_hosts must not be able to decide this connection.
    assert "GlobalKnownHostsFile=/dev/null" in argv
    body = pinned.read_text(encoding="utf-8")
    key_lines = [line for line in body.splitlines() if line and not line.startswith("#")]
    assert key_lines, "a pinned file with no key in it verifies nothing"
    assert any("ssh-ed25519" in line for line in key_lines)


def test_the_pinned_key_matches_the_published_fingerprint():
    """The pinned bytes are the key the endpoint publishes, checked by ssh itself."""
    fingerprints = _pinned_fingerprints()
    assert fingerprints == {
        "SHA256:pG6qrBxubYfWa1Zadu/V0NUgjEDiBds/7e2xzte/QNM",
        "SHA256:FV8IMJ4IYjYUTnd6on7PqbRjaZf4c1EhhEBgeUdE94I",
    }


def _pinned_fingerprints() -> set[str]:
    import subprocess

    listing = subprocess.run(
        ["ssh-keygen", "-l", "-f", str(tunnel_module.KNOWN_HOSTS_FILE)],
        capture_output=True,
        text=True,
        check=True,
    )
    return {line.split()[1] for line in listing.stdout.splitlines() if line.strip()}


def test_an_unpinned_host_key_refuses_the_tunnel_and_names_the_move(ssh):
    """GIVEN ssh cannot match the pinned key
    WHEN the operator asks for public pairing
    THEN there is no public URL and the answer carries the reason
    """
    ssh.lines = [
        "ssh: connect to host localhost.run port 22: Connection refused\n",
        "Host key verification failed.\n",
    ]
    manager = TunnelManager()
    manager.start_tunnel(8765, 60, watchdog=False)

    assert _wait_for(lambda: manager.block_reason != "")
    assert manager.block_reason == "host_key_unverified"
    assert manager.public_url is None


def test_a_changed_host_key_is_a_refusal_too(ssh):
    """The classic MITM warning is the same refusal, never a retry with trust."""
    ssh.lines = [
        "@    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @\n",
        "Host key verification failed.\n",
    ]
    manager = TunnelManager()
    manager.start_tunnel(8765, 60, watchdog=False)

    assert _wait_for(lambda: manager.block_reason == "host_key_unverified")
    assert manager.public_url is None


def test_a_missing_ssh_client_is_a_refusal_of_its_own(ssh):
    ssh.which_result = None
    manager = TunnelManager()
    manager.start_tunnel(8765, 60, watchdog=False)

    assert manager.process is None
    assert manager.block_reason == "ssh_missing"
    assert manager.public_url is None


def test_the_url_scraping_still_rejects_the_admin_host():
    """The endpoint prints its dashboard URL beside the tunnel URL; only the tunnel counts."""
    assert _extract_public_tunnel_url("https://a1b2c3.lhr.life") == "https://a1b2c3.lhr.life"
    assert _extract_public_tunnel_url("https://x.localhost.run/") == "https://x.localhost.run"
    assert _extract_public_tunnel_url("https://admin.localhost.run") is None
    assert _extract_public_tunnel_url("no url here") is None


# 3. The exposure ends


def test_a_tunnel_that_saw_no_traffic_is_stopped(ssh):
    manager = TunnelManager()
    manager.start_tunnel(8765, 60, watchdog=False)
    manager.public_url = TUNNEL_URL

    ssh.clock.now += 61
    assert manager.stop_if_idle() is True
    assert ssh.processes[0].terminated is True
    assert manager.public_url is None
    assert manager.uptime_seconds() is None


def test_a_tunnel_with_public_traffic_is_not_stopped(ssh):
    manager = TunnelManager()
    manager.start_tunnel(8765, 60, watchdog=False)
    manager.public_url = TUNNEL_URL

    ssh.clock.now += 50
    manager.note_traffic("a1b2c3.lhr.life")
    ssh.clock.now += 50
    assert manager.stop_if_idle() is False
    assert ssh.processes[0].terminated is False
    assert manager.public_url == TUNNEL_URL


def test_traffic_on_the_loopback_address_does_not_extend_the_exposure(ssh):
    """Desktop traffic is not a reason to keep the public address standing."""
    manager = TunnelManager()
    manager.start_tunnel(8765, 60, watchdog=False)
    manager.public_url = TUNNEL_URL

    for _ in range(4):
        ssh.clock.now += 20
        manager.note_traffic("127.0.0.1:8765")
    assert manager.stop_if_idle() is True
    assert ssh.processes[0].terminated is True


def test_the_watchdog_closes_a_quiet_tunnel_on_its_own(ssh):
    """The bound closes the hop on the manager's own clock, without anyone asking."""
    manager = TunnelManager()
    manager.start_tunnel(8765, 60, watchdog=False)
    manager.public_url = TUNNEL_URL

    manager._watch()

    assert ssh.processes[0].terminated is True
    assert manager.public_url is None


def test_the_answer_says_when_the_tunnel_stops(ssh):
    manager = TunnelManager()
    manager.start_tunnel(8765, 60, watchdog=False)
    manager.public_url = TUNNEL_URL

    ssh.clock.now += 15
    assert manager.uptime_seconds() == 15
    assert manager.stops_in_seconds() == 45


def test_an_admitted_request_on_the_public_host_pushes_the_stop_back(ssh):
    """The traffic that keeps the hop alive is a request admitted on its own address."""
    from server import middleware

    app = create_app(lan_mode=True)
    token = middleware.LAN_AUTH_TOKEN
    assert token
    manager = tunnel_module.tunnel_manager
    manager.start_tunnel(8765, 60, watchdog=False)
    manager.public_url = TUNNEL_URL
    ssh.clock.now += 20

    before = manager.stops_in_seconds()
    TestClient(app).get(
        "/api/health",
        headers={"Host": "a1b2c3.lhr.life", "X-Auth-Token": token},
    )

    assert manager.stops_in_seconds() > before


def test_a_refused_request_on_the_public_host_does_not_extend_the_exposure(ssh):
    """A stranger hammering the public address cannot hold the tunnel open."""
    app = create_app(lan_mode=True)
    manager = tunnel_module.tunnel_manager
    manager.start_tunnel(8765, 60, watchdog=False)
    manager.public_url = TUNNEL_URL
    ssh.clock.now += 20

    before = manager.stops_in_seconds()
    for _ in range(5):
        TestClient(app).get("/api/sessions", headers={"Host": "a1b2c3.lhr.life"})

    assert manager.stops_in_seconds() == before


def test_the_idle_bound_follows_the_setting(monkeypatch, tmp_path):
    """One name in the settings register moves the bound the hop is started with."""
    from core import engine_config
    from core.settings_schema import SCHEMA, save_deep_settings, validate_sections

    field = SCHEMA["advanced.public_tunnel_idle_minutes"]
    assert field["default"] == 30
    assert field["min"] <= field["default"] <= field["max"]

    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
    monkeypatch.setattr(engine_config, "CONFIG_DIR", cfg, raising=False)
    assert save_deep_settings(
        validate_sections({"advanced": {"advanced.public_tunnel_idle_minutes": 7}})
    )

    seen: dict[str, float] = {}

    class _Recorder:
        block_reason = ""
        public_url = TUNNEL_URL

        def start_tunnel(self, port, idle_seconds):
            seen["idle_seconds"] = idle_seconds

        def uptime_seconds(self):
            return 1.0

        def stops_in_seconds(self):
            return 1.0

    monkeypatch.setattr("server.routes.mobile.tunnel_manager", _Recorder())
    TestClient(create_app()).get("/api/mobile/qr", params={"mode": "public"})

    assert seen["idle_seconds"] == 7 * 60


# 4. The sentence and the behaviour are one claim


def test_the_lan_dead_answer_is_the_sentence_the_product_claims(client, dead_lan, monkeypatch):
    """The message and the branch under it are the same promise, so they are pinned together."""
    tripwire = _TunnelTripwire()
    monkeypatch.setattr("server.routes.mobile._start_public_tunnel", tripwire)

    data = client.get("/api/mobile/qr").json()

    assert data["message"] == LAN_DEAD_MESSAGE
    assert "public mode explicitly" in data["message"]
    assert data["mode"] == "lan"
    assert data["is_public"] is False
    assert tripwire.calls == []


@pytest.mark.parametrize("mode", ["auto", "lan"])
def test_no_lan_mode_answer_reports_public_mode(client, dead_lan, monkeypatch, mode):
    """No path of a non-public request may set mode to public."""
    monkeypatch.setattr("server.routes.mobile._start_public_tunnel", _TunnelTripwire())

    data = client.get("/api/mobile/qr", params={"mode": mode}).json()

    assert data["mode"] != "public"
    assert data["is_public"] is False
