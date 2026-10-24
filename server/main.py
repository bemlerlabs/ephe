"""
◑ Ephe – FastAPI Server
server/main.py

Starts the API server for the desktop app.
Paths for memory/profile/etc. are configured through env variables
so tests can use isolated tmp directories.

LAN mode: with --lan active, an auth token is generated and every
API endpoint has to send X-Auth-Token in the header.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from core.observability import (
    REQUEST_ID_HEADER,
    ErrorCode,
    error_payload,
    make_observability_middleware,
)

from server.routes import (
    agents,
    agent_teams,
    artifacts,
    audit,
    cell,
    learning,
    channels,
    fs,
    git_info,
    hooks,
    audio,
    chat,
    environment,
    ephemeris,
    export,
    feedback,
    files,
    health,
    importer,
    memory,
    memory_trash,
    metrics,
    mobile,
    network,
    model_provider,
    marketplace,
    mcp,
    plugins,
    profile,
    proxy,
    schedule,
    search,
    sessions,
    settings,
    shell,
    skills,
    subagents,
    tasks,
    tour,
    trajectory,
    usage,
    vision,
    context,
    update,
    reader,
    workspaces,
)
from server.spa import SPAStaticFiles
from core import __version__, __edition__, __tagline__
from contextlib import asynccontextmanager
import asyncio


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    """Lifecycle events: Start background warmup tasks."""

    # Warmup STT in the background — from the local cache only. The unqualified
    # `_get_model()` this used to call fetched the speech model from
    # huggingface.co on a fresh start, without asking (first-start probe,
    # 2026-10-15). `warm_if_cached` leaves the network alone when the model is
    # absent: the fetch belongs to the transcription feature, and that feature
    # asks first (core/transcribe.py).
    def warmup_whisper():
        try:
            from core.transcribe import warm_if_cached

            warm_if_cached()
        except Exception:
            pass

    # P0-1: keep task references — without a bound handle the GC can resolve
    # the task mid-execution (CPython docs warning about create_task).
    _background_tasks: list = []
    warm_task = asyncio.create_task(asyncio.to_thread(warmup_whisper))
    _background_tasks.append(warm_task)

    # --- GUI Automation Safety Setup ---
    def configure_gui_safety():
        import sys
        import logging

        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            if sys.platform == "darwin":
                logging.getLogger("uvicorn.error").warning(
                    "⚡ [GUI Automation] Ensure Ephe (Terminal/App) has 'Accessibility' "
                    "and 'Screen Recording' permissions in macOS System Settings > Privacy & Security, "
                    "otherwise vision_click tools will crash immediately."
                )
        except Exception:
            pass

    asyncio.create_task(asyncio.to_thread(configure_gui_safety))

    # --- Background Scheduler ---
    # MUST start on the event-loop thread: AsyncIOScheduler requires a running
    # loop in the calling thread. Via asyncio.to_thread it silently failed and
    # every scheduled job stayed pending forever (next_run=None, never fired).
    try:
        from core.scheduler import ephe_scheduler

        ephe_scheduler.start()
    except Exception:
        logging.getLogger("uvicorn.error").exception(
            "Failed to start background scheduler"
        )

    # --- P1: import the legacy plugin registry once, before any request reads state ---
    try:
        from core import plugin_runtime

        plugin_runtime.lifecycle()
    except Exception:
        logging.getLogger("uvicorn.error").exception("plugin state migration failed")

    # --- R40 (Z44): attach the MCP server opt-in (env > mcp.json; fault-tolerant) ---
    try:
        from core.mcp_config import init_mcp_from_config

        registered = await init_mcp_from_config()
        if registered:
            logging.getLogger("uvicorn.access").info(
                f"MCP tools registered: {', '.join(registered)}"
            )
    except Exception:
        logging.getLogger("uvicorn.error").exception("MCP init failed")

    yield

    try:
        from core.scheduler import ephe_scheduler

        ephe_scheduler.stop()
    except Exception:
        pass

    try:
        await channels.shutdown_channels()
    except Exception:
        pass

    # I1-8: configured MCP servers are child processes — letting them outlive the
    # parent is a leak you only notice in the process table.
    try:
        from core.tools.mcp_client import close_all_mcp_clients

        await close_all_mcp_clients()
    except Exception:
        pass


def create_app(lan_mode: bool = False) -> FastAPI:
    """
    FastAPI app factory.
    Used in tests (TestClient) and in run.py (uvicorn).

    lan_mode: when True, an auth token is generated + security/rate limit enabled.
    """
    # Init auth (generates the token in LAN mode)
    from server.middleware import (
        init_auth,
        SecurityHeadersMiddleware,
        RateLimitMiddleware,
        AuthMiddleware,
        LocalRequestGuardMiddleware,
    )

    init_auth(lan_mode=lan_mode)

    app = FastAPI(
        title=f"{__edition__} Ephe API",
        description=__tagline__,
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
    )

    # Security Middleware
    app.add_middleware(SecurityHeadersMiddleware)
    # A loopback TCP peer is not an identity: DNS rebinding reaches the port
    # under the attacker's Host. This guard runs for desktop and loopback LAN
    # clients; a non-loopback LAN client stays behind AuthMiddleware.
    app.add_middleware(LocalRequestGuardMiddleware)
    if lan_mode:
        app.add_middleware(AuthMiddleware)
        app.add_middleware(RateLimitMiddleware, max_requests=400, window=60)

    # CORS for the desktop shell, and for a dev server that is not proxied.
    #
    # The product itself needs no permissive rule: the PWA is served by this server, so its
    # requests are same-origin; the Vite dev server proxies `/api` (app/vite.config.ts), so
    # dev is same-origin too; and the desktop shell arrives as `tauri://localhost`. What stood
    # here granted **any** `http://localhost:<port>` credentials, which is every page a local
    # service happens to serve - a dev server someone else started, a tool with a web UI -
    # and CORS is the one place where "local" is not a security boundary.
    #
    # A dev server that does want its own origin names it: EPHE_DEV_ORIGINS, comma-separated
    # (`.env.example`). This server's own origin is always allowed, under both loopback
    # spellings, because a page it serves may call it under the other one (`localhost` page,
    # `127.0.0.1` API).
    port = os.environ.get("EPHE_PORT") or "8765"
    own_origins = [
        f"http://127.0.0.1:{port}",
        f"http://localhost:{port}",
        f"http://[::1]:{port}",
    ]
    dev_origins = [
        o.strip()
        for o in os.environ.get("EPHE_DEV_ORIGINS", "").split(",")
        if o.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "tauri://localhost",
            "http://tauri.localhost",
            *own_origins,
            *dev_origins,
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Observability (phase 4 item 15): request ID + structured logs
    # Last add_middleware ⇒ outermost: request.state.rid is set for all inner
    # middlewares (auth 401, rate limit) + the handlers.
    app.middleware("http")(make_observability_middleware(prefix="api"))

    # Registered on the Starlette base: FastAPI's own HTTPException
    # (a subclass) resolves the same handler through the MRO, and router 404/405
    # (real Starlette HTTPException) are caught by it as well.
    def _transport_code(status_code: int) -> ErrorCode:
        """The envelope's own code for a status, so both refusal handlers answer it alike."""
        if status_code in (401, 403):
            return ErrorCode.AUTH
        if status_code == 409:
            return ErrorCode.SETUP_REQUIRED  # W19: chat without an engine in setup mode
        if status_code in (404, 405):
            return ErrorCode.NOT_FOUND
        if status_code in (400, 422):
            return ErrorCode.VALIDATION
        if status_code == 429:
            return ErrorCode.USAGE
        if status_code in (502, 503):
            return ErrorCode.UPSTREAM
        return ErrorCode.INTERNAL

    async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Starlette/FastAPI HTTPException carry status_code + detail;
        # getattr keeps the handler type-safe for both classes.
        rid = getattr(request.state, "rid", None)
        detail = getattr(exc, "detail", None)
        extra = detail if isinstance(detail, dict) else None
        if isinstance(detail, dict):
            message = str(detail.get("detail") or detail.get("code") or "Error")
        else:
            message = detail if isinstance(detail, str) else str(detail or "Error")
        status_code = int(getattr(exc, "status_code", 500))
        code_id = _transport_code(status_code)
        body = error_payload(code_id, message, rid)
        if extra is not None:
            body["error"]["detail"] = extra
        return JSONResponse(
            body,
            status_code=status_code,
            headers={REQUEST_ID_HEADER: rid or ""},
        )

    # Starlette base (router 404/405) + FastAPI subclass (raised in routes)
    # — the exception middleware's MRO lookup is exact per class, hence both.
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(HTTPException, _http_exception_handler)

    from server.refusals import Refused

    # A refusal that knows its reason travels in the same envelope, with the reason beside
    # the transport code — the sentence stays what it is, the surface gets a key to answer in.
    async def _refused_handler(request: Request, exc: Refused) -> JSONResponse:
        rid = getattr(request.state, "rid", None)
        # The same mapping the plain handler uses, so a coded 404 or 429 keeps the transport
        # code its route answered with before the code existed.
        transport = _transport_code(exc.status_code)
        body = error_payload(transport, exc.message, rid)
        body["error"]["reason_code"] = exc.code
        if exc.params:
            body["error"]["reason_params"] = dict(exc.params)
        return JSONResponse(
            body, status_code=exc.status_code, headers={REQUEST_ID_HEADER: rid or ""}
        )

    app.add_exception_handler(Refused, _refused_handler)

    # Honest /v1 hint (R33, stress triage P2)
    # Before this, /v1/* fell through to the SPA catch-all of the frontend mounts
    # and was a silent 404 saying nothing. The OpenAI-compatible engine lives in
    # server/openai.py and is started via ``ephe serve`` — this now says so too.
    # Deliberately registered BEFORE mount_frontend.
    _V1_HINT = (
        "OpenAI-compatible endpoints (/v1/models, /v1/chat/completions) are not "
        "mounted on the main PWA server. Run `ephe serve` to start the "
        "OpenAI-compatible engine, or use POST /api/chat on this server."
    )

    def _v1_not_found(full_path: str) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "not_found",
                    "message": _V1_HINT,
                    "path": f"/v1/{full_path}",
                }
            },
            status_code=404,
        )

    @app.get("/v1/{full_path:path}")
    async def _v1_hint_get(full_path: str) -> JSONResponse:
        return _v1_not_found(full_path)

    @app.post("/v1/{full_path:path}")
    async def _v1_hint_post(full_path: str) -> JSONResponse:
        return _v1_not_found(full_path)

    # API routes
    app.include_router(health.router, prefix="/api")
    app.include_router(usage.router, prefix="/api")
    app.include_router(files.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(shell.router, prefix="/api")
    app.include_router(memory.router, prefix="/api")
    app.include_router(memory_trash.router, prefix="/api")
    app.include_router(skills.router, prefix="/api")
    app.include_router(artifacts.router, prefix="/api")
    app.include_router(audit.router, prefix="/api")
    app.include_router(cell.router, prefix="/api")
    app.include_router(hooks.router, prefix="/api")
    app.include_router(network.router, prefix="/api")
    app.include_router(channels.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")
    app.include_router(learning.router, prefix="/api")
    app.include_router(context.router, prefix="/api")
    app.include_router(metrics.router, prefix="/api")
    app.include_router(profile.router, prefix="/api")
    app.include_router(feedback.router, prefix="/api")
    app.include_router(audio.router, prefix="/api")
    app.include_router(mobile.router, prefix="/api")
    app.include_router(schedule.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")
    app.include_router(plugins.router, prefix="/api")
    app.include_router(importer.router, prefix="/api")
    app.include_router(tour.router, prefix="/api")
    app.include_router(environment.router, prefix="/api")
    app.include_router(ephemeris.router, prefix="/api")
    app.include_router(mcp.router, prefix="/api")
    app.include_router(vision.router, prefix="/api")
    app.include_router(tasks.router, prefix="/api")
    app.include_router(subagents.router, prefix="/api")
    app.include_router(agents.router, prefix="/api")
    app.include_router(agent_teams.router, prefix="/api")
    app.include_router(trajectory.router, prefix="/api")
    app.include_router(export.router, prefix="/api")
    app.include_router(model_provider.router, prefix="/api")
    app.include_router(marketplace.router, prefix="/api")
    app.include_router(fs.router, prefix="/api")
    app.include_router(git_info.router, prefix="/api")
    app.include_router(proxy.router, prefix="/api")
    app.include_router(update.router, prefix="/api")
    app.include_router(reader.router, prefix="/api")
    app.include_router(workspaces.router, prefix="/api")

    # Static files (audio recordings for playback)
    audio_dir = Path(
        os.environ.get(
            "EPHE_AUDIO_DIR", str(Path.home() / ".ephe" / "sessions" / "audio")
        )
    )
    audio_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/audio", StaticFiles(directory=str(audio_dir)), name="audio")

    # Static files (images/screenshots for remote)
    image_dir = Path(
        os.environ.get(
            "EPHE_IMAGE_DIR", str(Path.home() / ".ephe" / "sessions" / "images")
        )
    )
    image_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/images", StaticFiles(directory=str(image_dir)), name="images")

    # Static files (the artifacts the chart tool writes, served from their own directory)
    from core.engine_config import artifact_output_dir

    charts_dir = artifact_output_dir()
    charts_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/charts", StaticFiles(directory=str(charts_dir)), name="charts")

    # Mobile entry point (/mobile.html = QR target, ping + redirect)
    _register_mobile_entrypoint(app)

    # Static files (web frontend / PWA)
    mount_frontend(app)

    return app


# Frontend (PWA) resolution
# The PWA build lives in app/dist (a git-ignored build artifact). app/src is
# only the Vite source (no index.html) — mounting it served a silent 404.
# EPHE_FRONTEND_DIR lets tests/CI plug in an isolated build directory
# without overwriting the production path.
def resolve_frontend_dir() -> Path:
    override = os.environ.get("EPHE_FRONTEND_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "app" / "dist"


def _frontend_missing_hint() -> HTMLResponse:
    """Root fallback when the PWA build is missing: repair instructions instead of a 404."""
    return HTMLResponse(
        """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ephe — PWA setup</title>
<style>body{font-family:system-ui,sans-serif;max-width:40rem;margin:4rem auto;
line-height:1.6;color:#111}code{background:#f2f2f2;padding:.1rem .4rem;
border-radius:4px}pre{background:#111;color:#eee;padding:1rem;border-radius:8px;
overflow:auto}</style></head>
<body><h1>◑ Ephe — preparing the PWA</h1>
<p>The web app (PWA) has not been built yet. The API server is already running —
only the frontend is missing. This is how you build the PWA locally:</p>
<pre>cd app
npm install
npm run build</pre>
<p>…then simply reload this page. Alternatively, the one-command installer
runs the build for you.</p>
<p>API endpoints are already reachable: <a href="/api/health">/api/health</a>
· <a href="/api/docs">/api/docs</a></p>
</body></html>""",
        status_code=200,
    )


def mount_frontend(app: FastAPI) -> None:
    """Serve the PWA under `/`.

    - Build present  → SPAStaticFiles(html=True): index.html + assets, and the
      app shell for a navigation path the router owns (`/workspaces` after a
      reload). `/api/*` and `/v1/*` keep their JSON 404, and a path that names a
      file keeps its 404 — see `server/spa.py`.
    - Build missing  → root shows the build instructions (200, not a 404)
    """
    frontend_dir = resolve_frontend_dir()
    if (frontend_dir / "index.html").is_file():
        app.mount(
            "/",
            SPAStaticFiles(directory=str(frontend_dir), html=True),
            name="frontend",
        )
    else:

        @app.get("/", include_in_schema=False)
        async def _root_missing_build() -> HTMLResponse:
            return _frontend_missing_hint()


# Standalone instance (for uvicorn directly)
def get_app() -> FastAPI:
    """Creates the app with LAN mode taken from the env variable."""
    lan = (os.environ.get("EPHE_LAN")) == "1"
    return create_app(lan_mode=lan)


_MOBILE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Ephe</title>
<style>
  body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
       background:#0b1319;color:#9fb4a8;font:15px/1.5 system-ui,sans-serif}
  .box{text-align:center}
  .dot{width:10px;height:10px;border-radius:50%;background:#22c55e;
       display:inline-block;animation:p 1.2s infinite}
  @keyframes p{0%,100%{opacity:.3}50%{opacity:1}}
</style>
</head>
<body>
<div class="box"><p><span class="dot"></span> Opening Ephe…</p></div>
<script>
  // QR target (server/routes/mobile.py): /mobile.html?token=<LAN-Auth>
  // 1) Ping: the desktop UI shows "connected" (GET /mobile/status)
  // 2) On to the PWA — api.ts reads ?token= and sends X-Auth-Token.
  (function () {
    var url = new URL(location.href);
    var token = url.searchParams.get('token');
    var headers = {'Content-Type': 'application/json'};
    if (token) headers['X-Auth-Token'] = token;
    fetch('/api/mobile/ping', {method: 'POST', headers: headers})
      .catch(function () {});
    var target = '/';
    if (token) target += '?token=' + encodeURIComponent(token);
    location.replace(target);
  })();
</script>
</body>
</html>"""


def _register_mobile_entrypoint(app: FastAPI) -> None:
    """/mobile.html = QR target: ping + redirect onto the PWA.

    A route instead of a StaticFile: app/dist is git-ignored (a build artifact),
    so the QR page has to be available without a build step.
    """

    @app.get("/mobile.html", include_in_schema=False)
    async def _mobile_entrypoint() -> Response:
        return Response(_MOBILE_HTML, media_type="text/html")


app = get_app()
