#!/usr/bin/env python3
"""
◑ Ephe – start the server
run_server.py

Starts the FastAPI server on port 8765.
Usage:
    python run_server.py             # default
    python run_server.py --port 9000 # different port
    python run_server.py --reload    # dev mode with auto-reload
"""
import argparse
import os
import sys
from pathlib import Path

# Keep the Ephe directory on the import path
sys.path.insert(0, str(Path(__file__).parent))

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="◑ Ephe API Server")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument("--port", default=8765, type=int, help="Port (default: 8765)")
    parser.add_argument("--lan", action="store_true", help="Expose on the local network for QR mobile pairing")
    parser.add_argument("--reload", action="store_true", help="Auto-Reload im Dev-Modus")
    return parser


def _is_loopback(host: str) -> bool:
    """Whether a bind answers on this machine only."""
    name = (host or "").strip().lower()
    return name in ("localhost", "::1") or name.startswith("127.")


def _is_wildcard(host: str) -> bool:
    """Whether a bind with this spelling answers on every interface.

    uvicorn hands an empty host and ``::`` to the OS the same way it hands it
    ``0.0.0.0``, so all three are the same exposure and all three force auth.
    """
    return (host or "").strip().lower() in ("0.0.0.0", "::", "")


def select_free_port(host: str, port: int, max_tries: int = 20) -> int:
    """W4 S1: free-port selection with sequential retry starting at the intended port.

    Strategy:
      - ``port == 0``  → ephemeral bind; the real port is read from the bound
        socket (``getsockname``) and returned.
      - otherwise      → sequential retry from ``port`` (up to ``max_tries``)
        until a bind succeeds; the ACTUAL port from the socket is authoritative.

    The returned port is the ONLY source for the banner, ``EPHE_PORT`` and the
    uvicorn bind — never an intended port that drifts away from reality.

    The probe binds 127.0.0.1 whatever ``host`` names. A probe is not a service, and
    the one bind that may answer on every interface is the server's own, behind the
    ``--lan`` / ``--host 0.0.0.0`` opt-in that forces ``EPHE_LAN`` and the pairing
    token in ``main``. A port held only on a specific non-loopback address is
    therefore not seen here; it surfaces once, at that bind, naming port and host.
    """
    import socket

    bind_host = "127.0.0.1"
    target_host = (host or "").strip() or bind_host
    base = port if port else 8765
    candidates = [0] if port == 0 else [base + off for off in range(max_tries)]
    for candidate in candidates:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((bind_host, candidate))
            return int(sock.getsockname()[1])
        except OSError:
            continue
        finally:
            sock.close()
    raise SystemExit(
        f"no free port in {candidates[0]}..{candidates[-1]} for {target_host}"
    )


def _bootstrap_engine_choice():
    """Resolve the engine choice for the server through the very same resolver the CLI uses.

    Returns the resolved EngineChoice (None when the env was already explicit).

    Why: the server's provider resolver reads EPHE_MODEL_PROVIDER (see
    core.model_provider._provider_from_env). Direct server starts
    (``python run_server.py``, Docker, IDE) do not go through ephe_cli.py, which
    is what resolves the engine — without this bootstrap engine.json was never
    read and the PWA always ran on local Ollama even though CLI + engine.json
    pointed at a different engine. This makes engine.json the single source
    across every start path.

    W18 (audit): NO silent Ollama fallback anymore. When engine.json AND the
    engine env are both missing, this runs the same fail-closed path as the CLI:
    interactively (TTY) the onboarding, otherwise an abort with instructions.

    An explicit env wins: anyone who set EPHE_MODEL_PROVIDER themselves
    (e.g. ``ephe start``, which already resolved the engine) is left untouched.
    """
    if os.environ.get("EPHE_MODEL_PROVIDER"):
        return None
    try:
        from core.engine_config import (
            EngineNotConfigured,
            resolve_engine_choice,
            stdin_is_interactive,
        )
    except Exception:
        return None

    prompt_fn = None
    if stdin_is_interactive():
        # The onboarding lives in the CLI (same text/flow as `ephe configure`);
        # imported only here so a server start without a TTY loads nothing extra.
        try:
            from ephe_cli import _run_engine_onboarding as prompt_fn  # type: ignore
        except Exception:
            prompt_fn = None

    try:
        choice = resolve_engine_choice(
            allow_prompt=prompt_fn is not None,
            prompt_fn=prompt_fn,
        )
    except EngineNotConfigured as exc:
        # W19 (live audit P1): a complete newcomer with no terminal experience NEVER
        # saw the UI — the start aborted before there was any setup page. On
        # loopback the server now starts in SETUP MODE: /api/setup/status reports
        # configured=false and the setup gate shows the setup page. Chat stays
        # fail-closed (no engine, no answers). --lan still aborts — no
        # unconfigured LAN exposure (release bar).
        #
        # Defence-in-depth: also `--host 0.0.0.0` (directly, or as an ephe spawn
        # that never passes `--lan`) and the env mirrors of it count as a LAN start
        # — setup mode binds exclusively on loopback.
        if (
            "--lan" in sys.argv
            or any(_is_wildcard(part) for part in sys.argv[1:])
            or (os.environ.get("EPHE_LAN")) == "1"
            or (
                os.environ.get("EPHE_HOST") is not None
                and _is_wildcard(os.environ["EPHE_HOST"])
            )
        ):
            print(f"\n  ✗ {exc}", file=sys.stderr)
            print(f"  Fix: {getattr(exc, 'hint', '')}\n", file=sys.stderr)
            raise SystemExit(1) from exc
        print("\n  ◐ No engine configured yet — starting SETUP MODE (localhost only).")
        print("  Open the printed URL and pick your engine on the Setup page.")
        print(f"  Hint: {getattr(exc, 'hint', '')}\n")
        # Chat fail-closed anchor: chat endpoints decline while no engine is
        # chosen (see server/routes/chat.py::_ensure_engine_ready).
        os.environ["EPHE_SETUP_MODE"] = os.environ["EPHE_SETUP_MODE"] = "1"
        return None
    choice.apply_env()
    return choice


def _watch_parent() -> None:
    """LC-1: exit when the desktop shell that started this backend is gone.

    A shell killed with SIGKILL cannot run its exit hook, and the Python child then
    survives as an orphan that keeps the port. The shell passes its pid; a change in
    our parent means the shell is gone (we were reparented), so the backend follows.
    Only set by the desktop shell — a CLI start has no such owner and is unaffected.
    """
    raw = os.environ.get("EPHE_PARENT_PID", "")
    if not raw.isdigit():
        return
    parent = int(raw)
    if os.getppid() != parent:
        return

    import threading
    import time

    def _watch() -> None:
        while True:
            if os.getppid() != parent:
                os._exit(0)
            time.sleep(1.5)

    threading.Thread(target=_watch, name="ephe-parent-watch", daemon=True).start()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    _watch_parent()
    # Fail-closed: every bind that may answer on all interfaces forces auth. Named by
    # value because `--host 0.0.0.0` is what the CLI spawn sends (`ephe start --lan`
    # passes it without --lan), and `::` and an empty host are the same wildcard under
    # another name — uvicorn gives each of them to the OS as "every address".
    # W19: the LAN env has to be set BEFORE the engine bootstrap so that setup
    # mode (loopback only) can never outlive a wildcard start.
    if args.lan:
        args.host = "0.0.0.0"
    # Every bind that answers beyond this machine forces auth, and a specific LAN address
    # does: `--host 192.168.1.20` reaches the network the same way `0.0.0.0` does, while
    # arming the token only for the wildcard left that bind serving every /api route
    # without one.
    if not _is_loopback(args.host):
        os.environ["EPHE_LAN"] = "1"
    choice = _bootstrap_engine_choice()
    # W4 S1: the ACTUAL port from the bound socket is authoritative — banner,
    # env and uvicorn bind all agree on the same port (free-port selection).
    args.port = select_free_port(args.host, args.port)
    os.environ["EPHE_HOST"] = os.environ["EPHE_HOST"] = args.host
    os.environ["EPHE_PORT"] = os.environ["EPHE_PORT"] = str(args.port)

    print(f"\n  ◑ Ephe API Server")
    print(f"  ─────────────────────────────────────")
    # W18: the active engine is shown in the start banner (chosen, not
    # guessed — without engine.json/env the start above already aborted).
    if choice is not None:
        print(f"  Engine: {choice.provider} / {choice.model}"
              + (f" @ {choice.api_url}" if choice.api_url else ""))
    print(f"  URL:    http://{args.host}:{args.port}")
    if not _is_loopback(args.host):
        print(f"  LAN:    scan the in-app QR code from a phone on the same Wi-Fi")
    print(f"  Docs:   http://{args.host}:{args.port}/api/docs")
    print(f"  Reload: {'aktiviert' if args.reload else 'deaktiviert'}")
    print(f"  ─────────────────────────────────────\n")

    import logging

    # uvicorn only configures its own loggers — without a root handler the
    # structured request lines from core.observability (rid + duration_ms,
    # finding P3-1 of the 1000-message report) are emitted into a sinkless
    # tree and vanish. One stderr handler at INFO makes them observable;
    # existing handlers (tests, embedding apps) are respected.
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO)

    # W4 S4: production handler on the ephe tree — level contract: debug is not
    # persistent, info and above are. propagate=False prevents double output
    # through the root handler.
    from core.observability import make_prod_handler

    _obs_root = logging.getLogger("ephe")
    if not _obs_root.handlers:
        _obs_root.addHandler(make_prod_handler())
    _obs_root.propagate = False

    import uvicorn

    # P0-1: the approval registry (_active_sandbox_events) and the ContextVar
    # isolation are process-local. With >1 worker an approve token from worker A
    # would 404 in worker B → approval divergence. Deliberately 1 worker.
    uvicorn.run(
        "server.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
        workers=1,
    )


if __name__ == "__main__":
    main()
