"""The sandbox lets a workspace start its own dev server, and nothing else.

"Look at my project and start it" ends in a server the user opens in a browser.
The Seatbelt profile denied every network operation, so `python3 -m http.server`
died with "Operation not permitted" and the model retried instead of serving the
project. Loopback bind/inbound is allowed now; outbound connections and every
other bind stay refused.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

from core import shell_sandbox


def test_the_profile_allows_a_loopback_listener_and_denies_outbound():
    profile = shell_sandbox.build_profile("/tmp/ws")
    assert "(deny network*)" in profile
    assert '(allow network-bind network-inbound (local ip "localhost:*"))' in profile
    # The narrower allow must come after the deny, or the deny wins.
    assert profile.index("(deny network*)") < profile.index("network-bind")


pytestmark_sandbox = pytest.mark.skipif(
    not shell_sandbox.is_available(), reason="sandbox-exec exists on macOS only"
)


def _run_in_sandbox(workspace, script: str) -> subprocess.CompletedProcess[str]:
    argv = shell_sandbox.wrap_command(f"{sys.executable} {script}", str(workspace))
    assert argv is not None
    return subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)


@pytestmark_sandbox
def test_a_bind_on_loopback_succeeds_inside_the_sandbox(tmp_path):
    script = tmp_path / "bind.py"
    script.write_text(
        "import socket\n"
        "s = socket.socket()\n"
        "s.bind(('127.0.0.1', 0))\n"
        "s.listen(1)\n"
        "print('bound', s.getsockname()[1])\n",
        encoding="utf-8",
    )
    done = _run_in_sandbox(tmp_path, script)
    assert done.returncode == 0, done.stderr
    assert "bound" in done.stdout


@pytestmark_sandbox
def test_an_outbound_connection_stays_refused(tmp_path):
    script = tmp_path / "connect.py"
    script.write_text(
        "import socket\n"
        "socket.create_connection(('1.1.1.1', 80), timeout=3)\n"
        "print('connected')\n",
        encoding="utf-8",
    )
    done = _run_in_sandbox(tmp_path, script)
    assert done.returncode != 0
    assert "connected" not in done.stdout
