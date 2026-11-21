import atexit
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

_TUNNEL_USER = "nokey"
_TUNNEL_HOST = "localhost.run"

#: The trust anchor for the public hop. ssh is told to verify against this file
#: alone, so a key an attacker or an earlier unverified connection put into
#: ~/.ssh/known_hosts decides nothing here. Rotation: utils/tunnel_known_hosts.
KNOWN_HOSTS_FILE = Path(__file__).resolve().parent / "tunnel_known_hosts"

#: Why a public pairing request came back with no URL, as the route reports it.
BLOCK_NONE = ""
BLOCK_HOST_KEY = "host_key_unverified"
BLOCK_NO_SSH = "ssh_missing"

#: What ssh prints when the peer cannot be matched to the pinned key. Each of
#: them is the pin doing its job, so none of them may retry without the pin.
_HOST_KEY_REFUSALS = (
    "Host key verification failed",
    "REMOTE HOST IDENTIFICATION HAS CHANGED",
    "No matching host key type is defined in the known hosts file",
)


def _extract_public_tunnel_url(line: str) -> str | None:
    match = re.search(r"https://([a-zA-Z0-9-]+\.(?:lhr\.life|localhost\.run))", line)
    if not match:
        return None
    host = match.group(1)
    if host == "admin.localhost.run":
        return None
    return f"https://{host}"


def _host_of(value: str) -> str:
    """The lowercase host of a `Host:` header or a URL, port and scheme dropped."""
    text = (value or "").strip().lower()
    if "://" in text:
        text = text.split("://", 1)[1]
    text = text.split("/", 1)[0]
    if text.startswith("["):  # IPv6 literal keeps its brackets, its port does not
        end = text.find("]")
        return text if end < 0 else text[: end + 1]
    return text.rsplit(":", 1)[0] if ":" in text else text


class TunnelManager:
    _instance = None

    def __init__(self):
        self.public_url = None
        self.process = None
        self.block_reason = BLOCK_NONE
        self._started_at = None
        self._last_activity = None
        self._idle_seconds = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = TunnelManager()
            atexit.register(cls._instance.cleanup)
        return cls._instance

    def cleanup(self):
        if self.process:
            print("🛑 Terminating Tunnel subprocess to prevent zombies...")
            self._terminate(self.process)
            self.process = None

    @staticmethod
    def _terminate(process) -> None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()

    def start_tunnel(self, port: int, idle_seconds: float, *, watchdog: bool = True):
        """Open the public hop for `idle_seconds` of quiet.

        The bound has no default here on purpose: an unbounded public tunnel is
        the state this class used to leave behind, so a caller has to say how
        long the exposure may stand. `watchdog=False` is for a caller that drives
        the clock and the termination itself.
        """
        # Does the process really live? Then do nothing. A finished ssh process
        # is also "not None" — that one has to be restarted, otherwise public_url
        # keeps serving a dead URL.
        if self.process is not None and self.process.poll() is None:
            return
        self.process = None
        self.public_url = None
        self.block_reason = BLOCK_NONE
        self._started_at = None
        self._last_activity = None
        self._idle_seconds = None

        ssh_path = shutil.which("ssh")
        if not ssh_path:
            self.block_reason = BLOCK_NO_SSH
            print("ssh client not found — public pairing unavailable. "
                  "Install openssh-client for remote access.")
            return
        if not KNOWN_HOSTS_FILE.is_file():
            # StrictHostKeyChecking=yes refuses on its own here; the reason is set
            # so the surface can name the move instead of showing a dead QR.
            self.block_reason = BLOCK_HOST_KEY
            print(f"public tunnel refused: the pinned host key file is missing ({KNOWN_HOSTS_FILE})")
            return

        print(f"Starting public remote tunnel for port {port} (via {ssh_path})...")
        argv = [
            ssh_path,
            "-o", "StrictHostKeyChecking=yes",
            "-o", f"UserKnownHostsFile={KNOWN_HOSTS_FILE}",
            # The pinned file is the only store this connection is checked
            # against, ssh may not write into it, and a DNS answer may not
            # substitute for it. BatchMode: an unknown key refuses in a server
            # process that has no terminal to answer a prompt on.
            "-o", "GlobalKnownHostsFile=/dev/null",
            "-o", "UpdateHostKeys=no",
            "-o", "VerifyHostKeyDNS=no",
            "-o", "BatchMode=yes",
            "-R", f"80:localhost:{port}",
            f"{_TUNNEL_USER}@{_TUNNEL_HOST}",
            "-T",
        ]
        self.process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        self._started_at = time.monotonic()
        self._last_activity = self._started_at
        self._idle_seconds = float(idle_seconds)

        def monitor():
            for line in self.process.stdout:
                public_url = _extract_public_tunnel_url(line)
                if public_url:
                    self.public_url = public_url
                    print(f"Public tunnel established: {public_url}")
                elif any(marker in line for marker in _HOST_KEY_REFUSALS):
                    self.block_reason = BLOCK_HOST_KEY
                    print(f"public tunnel refused: the endpoint host key does not match {KNOWN_HOSTS_FILE}")
                elif self.process.poll() is not None:
                    print(f"Tunnel process exited with code {self.process.returncode}")

        threading.Thread(target=monitor, daemon=True).start()
        if watchdog:
            threading.Thread(target=self._watch, daemon=True).start()

    def _watch(self):
        interval = max(1.0, min(60.0, (self._idle_seconds or 60.0) / 4))
        while self.process is not None and self.process.poll() is None:
            time.sleep(interval)
            self.stop_if_idle()

    def note_traffic(self, host_header: str | None) -> None:
        """Record a request admitted on the tunnel's own address.

        The tunnel forwards with a loopback peer, so the Host is what tells the
        phone on the public address apart from the desktop on this machine. Only
        the first one is a reason for the exposure to stand.
        """
        process = self.process
        if process is None or self.public_url is None or process.poll() is not None:
            return
        if _host_of(host_header or "") != _host_of(self.public_url):
            return
        self._last_activity = time.monotonic()

    def stop_if_idle(self, now: float | None = None) -> bool:
        """Close the hop once it has been quiet for the whole idle window."""
        process = self.process
        if process is None or self._idle_seconds is None or self._last_activity is None:
            return False
        if process.poll() is not None:
            return False
        now = time.monotonic() if now is None else now
        if now - self._last_activity < self._idle_seconds:
            return False
        print(f"Public tunnel closed after {int(self._idle_seconds)}s without mobile traffic")
        self._terminate(process)
        self.process = None
        self.public_url = None
        self._started_at = None
        self._last_activity = None
        return True

    def stop(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            self._terminate(process)
        self.process = None
        self.public_url = None
        self.block_reason = BLOCK_NONE
        self._started_at = None
        self._last_activity = None
        self._idle_seconds = None

    def _live(self):
        if self.process is None or self.process.poll() is not None:
            return None
        if self._started_at is None:
            return None
        return time.monotonic()

    def uptime_seconds(self) -> float | None:
        """How long the hop has stood, or None when nothing is exposed."""
        now = self._live()
        return None if now is None else max(0.0, now - self._started_at)

    def stops_in_seconds(self) -> float | None:
        """How long until the idle bound closes it, or None when nothing is exposed."""
        now = self._live()
        if now is None or self._idle_seconds is None or self._last_activity is None:
            return None
        return max(0.0, self._idle_seconds - (now - self._last_activity))


tunnel_manager = TunnelManager.get_instance()
