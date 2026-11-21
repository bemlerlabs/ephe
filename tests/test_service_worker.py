"""Service Worker strategy: SSE and /api/* must NEVER be cached (D4)

WGT gate for PWA chat UX phase D4:
The Service Worker must not serve streaming traffic (text/event-stream) or API
requests (POST /api/chat/stream, /api/sandbox/approve, /api/*) from cache —
otherwise a stale tab blocks chat streaming, and rolling the cache key would
not revoke the old bundles.

Contract:
- /api/* requests     → always network-first, never served from cache, never cached
- text/event-stream   → always network-first, never cached (SSE streaming)
- Navigation requests (index.html, /) → network-first, cache only as the
  offline fallback (no stuck, outdated index.html)
- Static assets (hashed chunks, icons, manifest) → cache-first is fine
- Cache key → build-time placeholder stamped from package.json
  (Vite plugin `ephe-sw-version`); never bumped by hand
- New SW version → NO auto-activation (no skipWaiting in install);
  only via the message 'SKIP_WAITING' (user clicks "Neu laden", G7)  # language-gate: ignore (quoted German update-toast action label as it ships, app/src/locales/de.json:1052)
"""
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent / "app"
SW_FILE = APP_ROOT / "public" / "service-worker.js"


def _sw_source() -> str:
    assert SW_FILE.is_file(), f"Service-Worker fehlt: {SW_FILE}"
    return SW_FILE.read_text(encoding="utf-8")


def test_sw_exists_and_is_plain_js():
    """The SW is valid plain JS (no TS syntax such as `as const` — the browser rejects it)."""
    src = _sw_source()
    assert "addEventListener" in src
    # TS-like syntax would throw a SyntaxError in the browser
    assert "as const" not in src
    assert "import type" not in src


def test_sw_cache_name_uses_build_time_placeholder():
    """The cache key is stamped from package.json during the build, not bumped
    by hand inside the file (a source of errors). The source file contains the
    placeholder; dist/service-worker.js receives ephe-v<version>-sse."""
    src = _sw_source()
    import re
    m = re.search(r"CACHE_NAME\s*=\s*'([^']+)'", src)
    assert m, "CACHE_NAME nicht gefunden"
    cache_name = m.group(1)
    assert cache_name == "__EPHE_SW_VERSION__", (
        "CACHE_NAME ist nicht mehr der Build-Platzhalter — manuelle "
        "Cache-Bumps sind fehleranfällig; Platzhalter behalten und das "
        "ephe-sw-version-Vite-Plugin stampen lassen."
    )


def test_sw_version_stamping_is_wired_into_build():
    """The stamping has to be wired into the build pipeline
    (a Node script after `vite build`), otherwise every build runs with the
    unstamped placeholder. Standalone instead of a Vite plugin because
    Vite copies public/ into dist only after closeBundle()."""
    script = APP_ROOT / "scripts" / "stamp-sw-version.mjs"
    assert script.is_file(), f"Stamping-Skript fehlt: {script}"
    code = script.read_text(encoding="utf-8")
    assert "__EPHE_SW_VERSION__" in code, (
        "Skript referenziert nicht den Platzhalter — Stamping greift "
        "nicht."
    )
    pkg = (APP_ROOT / "package.json").read_text(encoding="utf-8")
    assert "stamp-sw-version.mjs" in pkg, (
        "build-Script ruft das Stamping-Skript nicht auf — "
        "dist/service-worker.js bliebe beim unge-stempelten "
        "Platzhalter."
    )


def test_sw_update_is_user_controlled():
    """G7: new SW versions do NOT activate themselves
    (no skipWaiting() in the install event) — otherwise a new worker would take
    over in the middle of a chat stream. Instead the app shows an update toast;
    the waiting SW only activates via the message 'SKIP_WAITING'
    (the click on 'Neu laden').  # language-gate: ignore (same quoted German reload label, app/src/locales/de.json:1052)"""
    src = _sw_source()
    import re
    m_install = re.search(
        r"addEventListener\('install'.*?\n\}\)", src, re.DOTALL
    )
    assert m_install, "install-Listener nicht gefunden"
    install_block = m_install.group(0)
    assert "skipWaiting" not in install_block, (
        "skipWaiting() im install-Event — neue SW-Version würde sich "
        "automatisch aktivieren und einen laufenden Chat-Turn "
        "mitten im Stream übernehmen können."
    )
    # The message handler for the explicit update consent must exist
    m_msg = re.search(r"addEventListener\('message'.*?\n\}\)", src, re.DOTALL)
    assert m_msg, "message-Listener nicht gefunden"
    msg_block = m_msg.group(0)
    assert "'SKIP_WAITING'" in msg_block and "skipWaiting" in msg_block, (
        "message-Handler löst bei 'SKIP_WAITING' kein skipWaiting() aus — "
        "der Update-Toast ('Neu laden') in der App könnte das Update "
        "nicht aktivieren."
    )


def test_api_requests_are_network_only():
    """/api/* requests are never served from cache and never cached."""
    src = _sw_source()
    assert "/api/" in src, "SW behandelt /api/* nicht explizit"
    # The /api/ branch has to be network-first and must NOT call cache.put
    # Structure check: the api block may not contain "cache.put"
    import re
    api_block = re.search(r"/api/.*?\}\)", src, re.DOTALL)
    assert api_block, "/api/-Branch im Fetch-Handler nicht gefunden"
    block_text = api_block.group(0)
    assert "cache.put" not in block_text, (
        "/api/* Antwort wird gecacht — Streaming/Approval-Requests dürfen "
        "nicht aus dem Cache kommen."
    )


def test_sse_streaming_is_network_only():
    """text/event-stream responses are never cached (SSE would break otherwise)."""
    src = _sw_source()
    assert "text/event-stream" in src, (
        "SW erkennt text/event-stream nicht — SSE-Streaming würde "
        "in den statischen Cache gezogen."
    )
    # The SSE check must sit around cache.put as a NEGATIVE CONDITION
    # (no caching OF event-stream responses)
    import re
    m = re.search(r"!ct\.includes\('text/event-stream'\)", src)
    assert m, "SSE-Prüfung sitzt nicht an der cache.put-Bedingung"
    # and /api/* (where the POST streams come from) is network-only
    assert "request.method !== 'GET'" in src, (
        "Non-GET Requests (POST /api/chat/stream) werden nicht als "
        "network-only behandelt."
    )


def test_navigation_is_network_first():
    """Navigation (index.html) is network-first, cache only as a fallback.
    A cache-first index.html plus a stuck old tab = the WSClient bundle
    forever (root cause of the C-smoke ws:// finding)."""
    src = _sw_source()
    assert "text/html" in src or "navigation" in src.lower() or "navigate" in src, (
        "SW behandelt Navigations-Requests nicht explizit"
    )
    # The navigation branch must exist and be network-first inside it:
    # fetch(request) before caches.match() within the block
    import re
    m_nav = re.search(
        r"if\s*\(\s*isNavigation\s*\)\s*\{(.*?)\n  \}", src, re.DOTALL
    )
    assert m_nav, "Navigations-Block (isNavigation) nicht gefunden"
    block = m_nav.group(1)
    assert "fetch(request)" in block and "caches.match" in block, (
        "Navigations-Block hat weder Netzwerk- noch Cache-Pfad"
    )
    assert block.index("fetch(request)") < block.index("caches.match"), (
        "Cache wird vor dem Netzwerk geprüft (cache-first) — Navigation "
        "würde den alten gecachten index.html liefern."
    )
