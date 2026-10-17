import subprocess
import threading
import re
import time
import atexit
import shutil

def _extract_public_tunnel_url(line: str) -> str | None:
    match = re.search(r"https://([a-zA-Z0-9-]+\.(?:lhr\.life|localhost\.run))", line)
    if not match:
        return None
    host = match.group(1)
    if host == "admin.localhost.run":
        return None
    return f"https://{host}"


class TunnelManager:
    _instance = None

    def __init__(self):
        self.public_url = None
        self.process = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = TunnelManager()
            atexit.register(cls._instance.cleanup)
        return cls._instance

    def cleanup(self):
        if self.process:
            print("🛑 Terminating Tunnel subprocess to prevent zombies...")
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

    def start_tunnel(self, port: int):
        # Does the process really live? Then do nothing. A finished ssh process
        # is also "not None" — that one has to be restarted, otherwise public_url
        # keeps serving a dead URL.
        if self.process is not None and self.process.poll() is None:
            return
        self.process = None
        self.public_url = None

        ssh_path = shutil.which("ssh")
        if not ssh_path:
            print("⚠️  ssh client not found — tunnel unavailable, falling back to local IP. "
                  "Install openssh-client for remote access.")
            return

        print(f"🌍 Starting public remote tunnel for port {port} (via {ssh_path})...")
        self.process = subprocess.Popen(
            ["ssh", "-o", "StrictHostKeyChecking=no", "-R", f"80:localhost:{port}", "nokey@localhost.run", "-T"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        def monitor():
            for line in self.process.stdout:
                public_url = _extract_public_tunnel_url(line)
                if public_url:
                    self.public_url = public_url
                    print(f"✅ Public Tunnel established: {self.public_url}")
                elif self.process.poll() is not None:
                    print(f"⚠️  Tunnel process exited with code {self.process.returncode}")

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()

tunnel_manager = TunnelManager.get_instance()
