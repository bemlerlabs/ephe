"""server/routes/mobile.py – GET /api/mobile/qr"""

import io
import base64
import time
import os
import urllib.request
from urllib.parse import urlparse
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Literal

from utils.network import get_local_ip
from utils.tunnel import tunnel_manager

router = APIRouter(tags=["Mobile"])

# Global state for connection tracking
_device_connected = False

class MobileQRResponse(BaseModel):
    url: str
    qr_base64: str
    mode: str = "auto"
    is_public: bool = False
    requires_internet: bool = False
    lan_reachable: bool = True
    message: str = ""
    # The pairing surface offers one deliberate click into `mode=public` when this
    # answer says the LAN is not reachable. Nothing here opens the tunnel itself.
    public_offer: bool = False
    # Why a `mode=public` request came back without a public URL, as a code the
    # bundle renders: "" | "host_key_unverified" | "ssh_missing".
    tunnel_block: str = ""
    # The state of a running public hop: how long it has stood and how long until
    # the idle bound closes it. Both None while nothing is exposed.
    tunnel_uptime_seconds: float | None = None
    tunnel_stops_in_seconds: float | None = None


def _is_loopback_host(host: str | None) -> bool:
    normalized = (host or "").strip().lower()
    return normalized in {"127.0.0.1", "localhost", "::1"}


def _server_allows_lan(request: Request) -> bool:
    bound_host = os.environ.get("EPHE_HOST") or request.url.hostname
    return not _is_loopback_host(bound_host)


def _is_docker_runtime() -> bool:
    return (os.environ.get("EPHE_DOCKER")) == "1" or os.path.exists("/.dockerenv")


def _split_host_port(host: str) -> tuple[str, str] | None:
    """(host, port | "") for a scheme-less authority, or None when it is not one.

    A colon without a numeric port is the shape of another scheme written without
    its slashes (`data:text/html,x`, `javascript:alert(1)`), and handing that to
    `urlopen` as `http://…` is the same escape the scheme check above closes.
    """
    if host.startswith("["):
        end = host.find("]")
        if end < 0:
            return None
        rest = host[end + 1 :]
        if rest == "":
            return host[: end + 1], ""
        if rest.startswith(":") and rest[1:].isdigit():
            return host[: end + 1], rest[1:]
        return None
    if ":" not in host:
        return host, ""
    name, _, own_port = host.rpartition(":")
    if not name or not own_port.isdigit():
        return None
    return name, own_port


def _configured_mobile_base_url(port: int) -> str | None:
    host = (os.environ.get("EPHE_MOBILE_HOST") or "").strip()
    if not host:
        return None
    if "://" in host:
        parsed = urlparse(host)
        # The probe below calls urllib.request.urlopen with what this returns, so
        # a host written as ftp:// or file:// would be fetched on that protocol
        # while the QR still says http. Only the family the surface advertises.
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        return None
    authority = _split_host_port(host)
    if authority is None:
        return None
    name, own_port = authority
    return f"http://{name}:{own_port or port}".rstrip("/")


def _lan_probe_succeeds(base_url: str) -> bool:
    if (os.environ.get("EPHE_SKIP_LAN_PROBE")) == "1":
        return True
    try:
        with urllib.request.urlopen(f"{base_url}/api/health", timeout=0.75) as response:
            return 200 <= response.status < 500
    except Exception:
        return False

def _public_tunnel_idle_seconds() -> float:
    """How long a public hop may stand untouched, from the settings register."""
    from core.settings_schema import deep_number

    return float(deep_number("advanced.public_tunnel_idle_minutes")) * 60.0


def _start_public_tunnel(port: int, idle_seconds: float) -> str | None:
    # Root-Cause F1 (first-user QA 2026-09-04): the ssh/localhost.run tunnel raises
    # "[Errno 32] Broken pipe" on network/daemon problems. Uncaught that 500'd the
    # whole /api/mobile/qr endpoint → the first user saw a red "API 500" instead of a QR.
    # A guard HERE keeps the route answerable: no tunnel reachable == None, the caller
    # then falls back to the LAN URL + user hint. The hop itself refuses to start on a
    # host key the pinned file does not carry (utils/tunnel_known_hosts).
    try:
        tunnel_manager.start_tunnel(port, idle_seconds)
        first_seen_at = None
        # ponytail: blocks up to 25s on the very first cold start (ssh handshake from localhost.run);
        # after that the ssh daemon keeps running => warm => instant. Upgrade path: QR immediately with
        # a "tunnel is being built" status + poll, if the cold-start user count rises.
        for _ in range(250):
            if tunnel_manager.public_url and first_seen_at is None:
                first_seen_at = time.time()
            if first_seen_at is not None and time.time() - first_seen_at >= 2.0:
                break
            time.sleep(0.1)
        return tunnel_manager.public_url
    except Exception:
        return None


@router.get("/mobile/qr", response_model=MobileQRResponse)
def get_mobile_qr(request: Request, mode: Literal["auto", "lan", "public"] = "auto") -> MobileQRResponse:
    """Returns the local or public URL and a base64 encoded QR code for mobile pairing."""
    global _device_connected
    _device_connected = False  # Reset on new pairing request
    port = request.url.port or 8765

    target_url = None
    is_public = False
    lan_reachable = _server_allows_lan(request)
    message = ""
    tunnel_block = ""

    if mode == "public":
        # The only door onto the public hop: an operator who asked for it by name.
        target_url = _start_public_tunnel(port, _public_tunnel_idle_seconds())
        is_public = bool(target_url)
        if not is_public:
            tunnel_block = tunnel_manager.block_reason

    if not target_url:
        configured_mobile_base_url = _configured_mobile_base_url(port)
        docker_without_mobile_host = _is_docker_runtime() and configured_mobile_base_url is None
        ip = get_local_ip()
        target_url = configured_mobile_base_url or f"http://{ip}:{port}"
        if docker_without_mobile_host:
            lan_reachable = False
        if not lan_reachable:
            mode = "lan"
            if docker_without_mobile_host:
                message = (
                    "Docker cannot expose its internal network address to your phone. "
                    "Set EPHE_MOBILE_HOST to your Mac Wi-Fi IP or choose public QR mode explicitly."
                )
            else:
                message = (
                    "Mobile LAN pairing needs Ephe started with LAN access. "
                    "Run: ephe start --lan"
                )
        elif not _lan_probe_succeeds(target_url):
            lan_reachable = False
            mode = "lan"
            message = (
                "Ephe is in LAN mode, but this Mac is not answering on the Wi-Fi address. "
                "Allow Python/Terminal in macOS Firewall or Local Network permissions, then reopen the QR. "
                "Public QR is available only when you choose public mode explicitly."
            )
        else:
            mode = "lan"
        # A dead LAN is a diagnosis, never a reason to publish. `auto` used to open
        # the public hop from inside this branch, in the same answer whose message
        # said public mode needs an explicit choice. The operator decides that now;
        # `public_offer` is what lets the surface ask.
    else:
        lan_reachable = True

    public_offer = not is_public and not lan_reachable

    # Mobile users get the clean chat-only page
    mobile_url = f"{target_url}/mobile.html"

    # Embed the auth token in the URL (only in LAN mode)
    from server.middleware import LAN_AUTH_TOKEN
    if LAN_AUTH_TOKEN:
        separator = "&" if "?" in mobile_url else "?"
        mobile_url = f"{mobile_url}{separator}token={LAN_AUTH_TOKEN}"

    import qrcode

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(mobile_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    qr_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')

    return MobileQRResponse(
        url=mobile_url,
        qr_base64=qr_base64,
        mode=mode,
        is_public=is_public,
        requires_internet=is_public,
        lan_reachable=lan_reachable,
        message=message,
        public_offer=public_offer,
        tunnel_block=tunnel_block,
        tunnel_uptime_seconds=tunnel_manager.uptime_seconds() if is_public else None,
        tunnel_stops_in_seconds=tunnel_manager.stops_in_seconds() if is_public else None,
    )


@router.post("/mobile/ping")
def mobile_ping():
    """Triggered by the PWA when it opens on a smartphone."""
    global _device_connected
    _device_connected = True
    return {"status": "ok"}


@router.get("/mobile/status")
def mobile_status():
    """Polled by the Desktop UI while the QR code is open."""
    global _device_connected
    return {"connected": _device_connected}
