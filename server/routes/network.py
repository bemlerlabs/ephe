'''server/routes/network.py – I6-6: the actual state of the network, not a banner.

The network area wants to say what Ephe really hangs on. Until now this
answer existed nowhere: bind address and port live only in the process environment
(`run_server.py` sets EPHE_HOST/EPHE_PORT after the socket choice), the LAN token
is created anew per start and is never persisted. A surface that showed figures
for this from the docs would be guessing. So: this endpoint reads the same sources
that also determine the behaviour — env, the token global, the share roots of the
file route and the share policy of the network guardian.

Nothing here is a control. Bind, CORS and token are start decisions
(CORS is built when the app is imported, the token is regenerated per start); a
switch that writes them while the runtime does not read it would be a dead
button. The lines in the area therefore name where each value gets set.
'''
from __future__ import annotations

import os

from fastapi import APIRouter

from core.net_guard import allow_private_by_default
from core.tools.base import _get_allowed_roots

router = APIRouter(tags=["Network"])


def network_status() -> dict:
    """The actual state of the server — from the same sources that enforce it."""
    from server.middleware import LAN_AUTH_TOKEN

    host = os.environ.get("EPHE_HOST", "")
    lan = os.environ.get("EPHE_LAN") == "1" or host == "0.0.0.0"
    try:
        port = int(os.environ.get("EPHE_PORT") or 0)
    except ValueError:
        port = 0
    extra = [p.strip() for p in (os.environ.get("EPHE_PROXY_PORTS") or "").split(",")]
    return {
        "bind_host": host,
        "bind_port": port,
        "lan": lan,
        "setup_mode": os.environ.get("EPHE_SETUP_MODE") == "1",
        "token_required": LAN_AUTH_TOKEN is not None,
        "file_roots": [str(root) for root in _get_allowed_roots()],
        "proxy_extra_ports": [p for p in extra if p],
        "allow_private_fetches": allow_private_by_default(),
    }


@router.get("/network/status")
async def get_network_status() -> dict:
    """Read-only: bind, reach, shares. See the module docstring for why none
    of this is adjustable here."""
    return network_status()
