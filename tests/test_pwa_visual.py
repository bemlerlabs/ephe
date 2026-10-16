from __future__ import annotations

import contextlib
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest


# SUPERSEDED (2026-08-17): this suite tested the legacy PWA (tab-based UI with
# #mobile-bottomnav, mirrored out of app/src/ by a Python HTTP handler). The root
# PWA was migrated to React 19 + Vite 6 + Tailwind v4; app/src/ has no index.html
# anymore — the legacy UI does not exist. The UI coverage (landing/onboarding/chat,
# panels, modals, mobile viewport) was taken over by app/tests/playwright/
# (Playwright, 20 specs against a fresh build). The file stays for history — all
# tests are skipped module-wide.
pytestmark = pytest.mark.skip(
    reason=(
        "Legacy PWA migrated to React+Vite; UI refactored zu Hash-Router "
        "Landing/Onboarding/Chat; Coverage übernommen in app/tests/playwright/ "
        "(2026-08-17)"
    )
)


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app" / "src"
SERVICE_WORKER = APP_DIR / "service-worker.js"

SKILL_FIXTURES = [
    {
        "name": "Chart",
        "trigger": "/chart",
        "description": "Erstellt Diagramme und Datenvisualisierungen.",
        "tools": ["chart"],
        "is_builtin": True,
    },
    {
        "name": "Deck",
        "trigger": "/deck",
        "description": "Erstellt Pitchdecks und Praesentations-Slides.",
        "tools": ["create_pitch_deck"],
        "is_builtin": True,
    },
    {
        "name": "Review",
        "trigger": "/review",
        "description": "Prueft Code, Dokumente und Plaene kritisch.",
        "tools": ["review"],
        "is_builtin": True,
    },
    {
        "name": "Files",
        "trigger": "/files",
        "description": "Arbeitet mit lokalen Dateien.",
        "tools": ["files"],
        "is_builtin": True,
    },
    {
        "name": "Help",
        "trigger": "/help",
        "description": "Erklaert die lokalen Ephe Funktionen.",
        "tools": ["help"],
        "is_builtin": True,
    },
    {
        "name": "PDF",
        "trigger": "/pdf",
        "description": "Analysiert und erstellt PDF-Inhalte.",
        "tools": ["pdf"],
        "is_builtin": True,
    },
    {
        "name": "Shell",
        "trigger": "/shell",
        "description": "Bereitet Terminal-Befehle mit Approval vor.",
        "tools": ["shell"],
        "is_builtin": True,
    },
    {
        "name": "SVG",
        "trigger": "/svg",
        "description": "Erstellt SVG-Grafiken lokal.",
        "tools": ["svg"],
        "is_builtin": True,
    },
    {
        "name": "Scan",
        "trigger": "/scan",
        "description": "Liest Bilder, Screenshots und OCR-Inhalte.",
        "tools": ["vision"],
        "is_builtin": True,
    },
    {
        "name": "Research",
        "trigger": "/research",
        "description": "Recherchiert optional online, wenn der Nutzer es bewusst will.",
        "tools": ["web"],
        "is_builtin": True,
    },
    {
        "name": "Writer",
        "trigger": "/write",
        "description": "Schreibt E-Mails, Texte und Zusammenfassungen.",
        "tools": ["write"],
        "is_builtin": True,
    },
]


class PwaVisualHandler(SimpleHTTPRequestHandler):
    active_provider = {
        "provider": "local_ollama",
        "model": "gemma4:12b",
        "base_url": "http://localhost:11434",
        "requires_internet": False,
        "offline_capable": True,
    }
    mobile_qr_requests: list[str] = []
    mobile_qr_lan_reachable = True
    mobile_qr_public_fallback = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP_DIR), **kwargs)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if self.path.startswith("/api/health"):
            self._send_json(
                {
                    "status": "ok",
                    "ollama": True,
                    "active_model": self.active_provider["model"],
                    "active_provider": self.active_provider["provider"],
                    "offline_capable": self.active_provider["offline_capable"],
                    "requires_internet": self.active_provider["requires_internet"],
                }
            )
            return

        if parsed.path == "/api/mobile/qr":
            query = parse_qs(parsed.query)
            mode = query.get("mode", ["lan"])[0]
            is_public = mode == "public" or self.__class__.mobile_qr_public_fallback
            response_mode = "public" if is_public else "lan"
            self.__class__.mobile_qr_requests.append(self.path)
            self._send_json(
                {
                    "url": (
                        "https://ephe.example.test/mobile.html"
                        if is_public
                        else "http://192.168.1.23:8766/mobile.html"
                    ),
                    "qr_base64": (
                        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
                        "/x8AAwMB/axp3FoAAAAASUVORK5CYII="
                    ),
                    "mode": response_mode,
                    "is_public": is_public,
                    "requires_internet": is_public,
                    "lan_reachable": self.__class__.mobile_qr_lan_reachable or is_public,
                    "message": (
                        "Remote access enabled for this QR. Keep Ephe running on your Mac."
                        if is_public else "" if self.__class__.mobile_qr_lan_reachable
                        else "Mobile LAN pairing needs Ephe started with LAN access. Run: ephe start --lan"
                    ),
                }
            )
            return

        if parsed.path == "/api/mobile/status":
            self._send_json({"connected": False})
            return

        if self.path.startswith("/api/model/providers"):
            self._send_json(
                {
                    "active": self.active_provider,
                    "providers": [
                        {"provider": "local_ollama", "model": "gemma4:12b"},
                        {"provider": "custom_ollama", "model": "gemma4:12b"},
                        {"provider": "openai_compatible", "model": "custom-model"},
                    ],
                    "local_models": ["gemma4:12b"],
                }
            )
            return

        if self.path.startswith("/api/skills"):
            self._send_json({"skills": SKILL_FIXTURES})
            return

        if self.path.startswith("/api/tasks"):
            self._send_json([])
            return

        if self.path.startswith("/api/memory/list"):
            self._send_json({"entries": []})
            return

        super().do_GET()

    def do_POST(self) -> None:
        if self.path.startswith("/api/mobile/ping"):
            self._send_json({"ok": True})
            return

        self._send_json({"error": "not found"}, status=404)

    def do_PUT(self) -> None:
        if self.path.startswith("/api/model/provider"):
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            provider = body.get("provider", "local_ollama")
            self.__class__.active_provider = {
                "provider": provider,
                "model": body.get("model") or "gemma4:12b",
                "base_url": body.get("base_url") or "",
                "requires_internet": provider == "openai_compatible",
                "offline_capable": provider != "openai_compatible",
            }
            self._send_json({"active": self.active_provider})
            return

        self._send_json({"error": "not found"}, status=404)


@contextlib.contextmanager
def _static_server():
    PwaVisualHandler.active_provider = {
        "provider": "local_ollama",
        "model": "gemma4:12b",
        "base_url": "http://localhost:11434",
        "requires_internet": False,
        "offline_capable": True,
    }
    PwaVisualHandler.mobile_qr_requests = []
    PwaVisualHandler.mobile_qr_lan_reachable = True
    PwaVisualHandler.mobile_qr_public_fallback = False
    server = ThreadingHTTPServer(("127.0.0.1", 0), PwaVisualHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/index.html"
    finally:
        server.shutdown()
        thread.join(timeout=2)


@pytest.mark.parametrize(
    "viewport",
        [
            {"width": 1440, "height": 900},
            {"width": 1024, "height": 768},
            {"width": 820, "height": 844},
            {"width": 390, "height": 844},
        ],
    )
def test_given_root_pwa_when_rendered_then_core_controls_fit_without_horizontal_overflow(viewport, tmp_path):
    """
    GIVEN the Root-PWA is the flagship UI
    WHEN it renders on desktop/tablet/mobile viewports
    THEN core controls are visible and the layout has no horizontal overflow.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport=viewport, service_workers="block")
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'en');
                localStorage.setItem('ephe_onboarded', '1');
                """
            )
            console_errors: list[str] = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

            with _static_server() as url:
                page.goto(url, wait_until="domcontentloaded")
                page.screenshot(path=str(tmp_path / f"root-pwa-{viewport['width']}x{viewport['height']}.png"))

                assert page.locator("#chat-area").is_visible()
                assert page.locator("#chat-input").is_visible()
                assert page.locator("#attach-btn").is_visible()
                assert page.locator("#provider-badge").count() == 1
                assert page.locator("#provider-badge").is_visible()
                assert page.locator("#btn-provider-settings").is_visible()
                if viewport["width"] <= 768:
                    assert page.locator(".topnav").is_hidden()
                else:
                    assert page.locator(".topnav").is_visible()

                has_overflow = page.evaluate(
                    "() => document.documentElement.scrollWidth > window.innerWidth + 1"
                )
                assert has_overflow is False

                banned = [
                    "reachable worldwide",
                    "global tunnel",
                    "100% offline",
                    "nav.exportchat",
                    "nav.tasks",
                    "tasks.title",
                    "tasks.sub",
                    "chip.swarm",
                ]
                page_text = page.locator("body").inner_text().lower()
                assert [term for term in banned if term in page_text] == []

                if viewport["width"] > 1200:
                    page.locator("#btn-provider-settings").click()
                    page.wait_for_selector("#provider-modal:not(.hidden)")
                    page.locator('input[name="provider"][value="openai_compatible"]').check()
                    assert page.locator("#provider-online-warning").is_visible()
                    assert "data goes to your configured provider" in (
                        page.locator("#provider-online-warning").inner_text().lower()
                    )
                    page.locator("#provider-save-btn").click()
                    assert "confirm" in page.locator("#provider-status").inner_text().lower()
                    page.locator("#provider-online-confirm").check()
                    page.locator("#provider-save-btn").click()
                    page.wait_for_function(
                        "() => document.querySelector('#provider-badge')?.classList.contains('online')"
                    )

                assert console_errors == []


@pytest.mark.parametrize(
    "viewport",
    [
        {"width": 1024, "height": 768},
        {"width": 1366, "height": 768},
        {"width": 1440, "height": 900},
        {"width": 1600, "height": 900},
    ],
)
def test_given_common_desktop_widths_when_header_renders_then_topbar_controls_do_not_overlap(viewport):
    """
    GIVEN common laptop and desktop widths
    WHEN the Root-PWA header renders
    THEN navigation tabs and topbar actions stay visually separate with no overlapping hit targets.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport=viewport, service_workers="block")
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'de');
                localStorage.setItem('ephe_onboarded', '1');
                """
            )

            with _static_server() as url:
                page.goto(f"{url}?qa=header-overlap", wait_until="domcontentloaded")
                page.wait_for_function("() => window._ephe")

                overlaps = page.evaluate(
                    """
                    () => {
                      const nodes = [...document.querySelectorAll('.topbar button, .topbar .provider-badge, .topbar .status-badge')]
                        .map((el) => {
                          const rect = el.getBoundingClientRect();
                          return {
                            id: el.id,
                            text: (el.innerText || el.textContent || '').trim(),
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height,
                            visible: rect.width > 0 && rect.height > 0,
                          };
                        })
                        .filter((entry) => entry.visible);

                      const collisions = [];
                      for (let i = 0; i < nodes.length; i += 1) {
                        for (let j = i + 1; j < nodes.length; j += 1) {
                          const a = nodes[i];
                          const b = nodes[j];
                          const overlaps =
                            a.x < b.x + b.width &&
                            a.x + a.width > b.x &&
                            a.y < b.y + b.height &&
                            a.y + a.height > b.y;
                          if (overlaps) {
                            collisions.push([a.id || a.text, b.id || b.text]);
                          }
                        }
                      }
                      return collisions;
                    }
                    """
                )

                assert page.locator(".topnav").is_visible()
                assert overlaps == []


@pytest.mark.parametrize(
    "viewport",
    [
        {"width": 769, "height": 844},
        {"width": 820, "height": 844},
        {"width": 900, "height": 844},
    ],
)
def test_given_tablet_widths_between_mobile_and_desktop_when_rendered_then_primary_navigation_stays_available(viewport):
    """
    GIVEN tablet widths between the mobile and desktop shells
    WHEN the Root-PWA renders
    THEN users still have a visible primary navigation and can open every main tab.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport=viewport, service_workers="block")
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'de');
                localStorage.setItem('ephe_onboarded', '1');
                """
            )

            with _static_server() as url:
                page.goto(f"{url}?qa=tablet-nav", wait_until="domcontentloaded")
                page.wait_for_function("() => window._ephe")

                topnav_visible = page.evaluate(
                    """
                    () => {
                      const el = document.querySelector('.topnav');
                      if (!el) return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width > 0 && rect.height > 0;
                    }
                    """
                )
                bottomnav_visible = page.evaluate(
                    """
                    () => {
                      const el = document.querySelector('.mobile-bottomnav');
                      if (!el) return false;
                      const rect = el.getBoundingClientRect();
                      return rect.width > 0 && rect.height > 0;
                    }
                    """
                )

                assert topnav_visible or bottomnav_visible

                for tab in ["skills", "history", "tasks", "memory", "profile"]:
                    page.locator(f'button[data-tab="{tab}"]').first.click()
                    text = page.locator(f"#view-{tab}").inner_text()
                    assert "tasks.title" not in text
                    assert "tasks.sub" not in text


@pytest.mark.parametrize(
    "viewport",
    [
        {"width": 1440, "height": 900},
        {"width": 820, "height": 844},
    ],
)
def test_given_mobile_pairing_when_opened_then_lan_qr_is_default_and_accessible(viewport):
    """
    GIVEN the user opens mobile pairing from the Root-PWA
    WHEN the QR dialog loads
    THEN it defaults to local network pairing, exposes accessible controls and never starts public mode.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport=viewport, service_workers="block")
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'en');
                localStorage.setItem('ephe_onboarded', '1');
                """
            )

            with _static_server() as url:
                page.goto(f"{url}?qa=mobile-pairing", wait_until="domcontentloaded")
                page.wait_for_function("() => window._ephe")

                page.locator("#btn-mobile-pairing").click()
                modal = page.locator("#mobile-qr-overlay")
                page.wait_for_selector("#mobile-qr-overlay:not(.hidden)")
                page.wait_for_selector("#mobile-qr-img:not(.hidden)")

                text = modal.inner_text().lower()
                assert "local network" in text
                assert "public access is an explicit online option" in text
                assert "global tunnel" not in text
                assert "reachable worldwide" not in text
                assert page.locator("#mobile-qr-img").get_attribute("src", timeout=5000).startswith(
                    "data:image/png;base64,"
                )
                assert page.get_by_role("dialog", name="Mobile Pairing").is_visible()
                assert page.get_by_role("button", name="Close").is_visible()
                assert PwaVisualHandler.mobile_qr_requests == ["/api/mobile/qr"]

                has_overflow = page.evaluate(
                    "() => document.documentElement.scrollWidth > window.innerWidth + 1"
                )
                assert has_overflow is False

                page.get_by_role("button", name="Close").click()
                page.wait_for_function(
                    "() => document.querySelector('#mobile-qr-overlay')?.classList.contains('hidden')"
                )


def test_given_mobile_pairing_when_public_qr_is_chosen_then_user_confirms_online_mode():
    """
    GIVEN public mobile access is an advanced online option
    WHEN the user explicitly chooses Public QR and confirms
    THEN the frontend requests mode=public and marks the QR as remote access.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 1024, "height": 768}, service_workers="block")
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'en');
                localStorage.setItem('ephe_onboarded', '1');
                """
            )
            page.on("dialog", lambda dialog: dialog.accept())

            with _static_server() as url:
                page.goto(f"{url}?qa=mobile-pairing-public", wait_until="domcontentloaded")
                page.wait_for_function("() => window._ephe")

                page.locator("#btn-mobile-pairing").click()
                page.wait_for_selector("#mobile-qr-overlay:not(.hidden)")
                page.locator("#mobile-qr-public-btn").click()
                page.wait_for_function(
                    "() => window.__unused !== true || true"
                )
                page.wait_for_selector("#mobile-qr-warning:not(.hidden)")

                assert PwaVisualHandler.mobile_qr_requests[-1] == "/api/mobile/qr?mode=public"
                warning = page.locator("#mobile-qr-warning").inner_text()
                assert "Remote access enabled" in warning
                assert "https://ephe.example.test/mobile.html" in page.locator("#mobile-qr-url").inner_text()


def test_given_mobile_pairing_modal_when_dismissed_then_button_escape_and_backdrop_all_close_it():
    """
    GIVEN the pairing modal is open
    WHEN the user dismisses it with common dialog gestures
    THEN Close, Escape and backdrop click all close it without extra public requests.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 1024, "height": 768}, service_workers="block")
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'de');
                localStorage.setItem('ephe_onboarded', '1');
                """
            )

            with _static_server() as url:
                page.goto(f"{url}?qa=mobile-pairing-dismiss", wait_until="domcontentloaded")
                page.wait_for_function("() => window._ephe")

                page.locator("#btn-mobile-pairing").click()
                page.wait_for_selector("#mobile-qr-overlay:not(.hidden)")
                page.get_by_role("button", name="Schließen").click()
                page.wait_for_function(
                    "() => document.querySelector('#mobile-qr-overlay')?.classList.contains('hidden')"
                )

                page.locator("#btn-mobile-pairing").click()
                page.wait_for_selector("#mobile-qr-overlay:not(.hidden)")
                page.keyboard.press("Escape")
                page.wait_for_function(
                    "() => document.querySelector('#mobile-qr-overlay')?.classList.contains('hidden')"
                )

                page.locator("#btn-mobile-pairing").click()
                page.wait_for_selector("#mobile-qr-overlay:not(.hidden)")
                page.mouse.click(8, 8)
                page.wait_for_function(
                    "() => document.querySelector('#mobile-qr-overlay')?.classList.contains('hidden')"
                )

                assert all("mode=public" not in request for request in PwaVisualHandler.mobile_qr_requests)


def test_given_mobile_pairing_when_lan_is_unavailable_then_modal_shows_remote_qr_warning():
    """
    GIVEN LAN is unavailable but remote QR fallback is available
    WHEN the QR modal opens
    THEN the user sees that remote access is active for the QR.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'de');
                localStorage.setItem('ephe_onboarded', '1');
                """
            )

            with _static_server() as url:
                PwaVisualHandler.mobile_qr_lan_reachable = False
                PwaVisualHandler.mobile_qr_public_fallback = True
                page.goto(f"{url}?qa=mobile-pairing-loopback", wait_until="domcontentloaded")
                page.wait_for_function("() => window._ephe")

                page.evaluate("() => window._ephe._showMobileModal()")
                page.wait_for_selector("#mobile-qr-warning:not(.hidden)")

                warning = page.locator("#mobile-qr-warning").inner_text()
                assert "Remote access enabled" in warning
                assert page.locator("#mobile-qr-img").get_attribute("src").startswith("data:image/png;base64,")


@pytest.mark.skip(reason="Legacy PWA migrated to React+Vite; source files (app/src/index.html, main.js, i18n.js, service-worker.js) and legacy UI features (export button, mode toggle, tasks tab) were removed/refactored. Test references stale paths.")
def test_given_cached_pwa_when_release_assets_change_then_service_worker_fetches_them_network_first():
    """
    GIVEN the PWA has already cached an older release
    WHEN HTML, main JS, i18n or CSS change
    THEN the service worker must prefer network responses so users see the update.
    """
    source = SERVICE_WORKER.read_text(encoding="utf-8")
    index = (APP_DIR / "index.html").read_text(encoding="utf-8")
    main = (APP_DIR / "main.js").read_text(encoding="utf-8")

    assert "NETWORK_FIRST_ASSETS" in source
    for asset in ["/", "/index.html", "/main.js", "/i18n.js", "/style.css", "/service-worker.js"]:
        assert f"'{asset}'" in source

    assert "event.request.destination === 'document'" in source
    assert "fetch(event.request).then((response)" in source
    assert "self.clients.matchAll" in source
    assert "client.navigate(client.url)" in source
    app_js = (APP_DIR / "modules" / "app.js").read_text(encoding="utf-8")
    utils_js = (APP_DIR / "modules" / "utils.js").read_text(encoding="utf-8")
    assert "getServiceWorker()" in main or "getServiceWorker()" in app_js or "getServiceWorker()" in utils_js
    assert ".addEventListener('controllerchange'" in main or ".addEventListener('controllerchange'" in app_js
    assert 'src="main.js"' in index
    assert 'href="style.css"' in index
    assert "from '../i18n.js'" in app_js or "from './i18n.js'" in main


def test_given_index_opened_from_file_protocol_when_rendered_then_user_gets_start_instruction_without_module_errors():
    """
    GIVEN a user opens app/src/index.html directly from Finder
    WHEN the browser loads it via file://
    THEN the app does not attempt module boot and shows the supported local-server start path.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            page = context.new_page()
            console_errors: list[str] = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

            page.goto((APP_DIR / "index.html").as_uri(), wait_until="domcontentloaded")
            page.wait_for_selector("#file-protocol-notice")

            notice = page.locator("#file-protocol-notice").inner_text()
            assert "Ephe per lokalem Server starten" in notice
            assert "ephe start" in notice
            assert "http://127.0.0.1:8765" in notice
            assert page.evaluate("() => Boolean(window._ephe)") is False
            assert console_errors == []


def test_given_restricted_browser_storage_when_root_pwa_loads_then_no_storage_or_service_worker_console_errors():
    """
    GIVEN an embedded or sandboxed browser blocks localStorage and serviceWorker
    WHEN the Root-PWA loads
    THEN the frontend degrades without uncaught console errors.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 1024, "height": 768}, service_workers="block")
            page = context.new_page()
            page.add_init_script(
                """
                Object.defineProperty(window, 'localStorage', {
                  configurable: true,
                  get() { throw new DOMException('localStorage blocked', 'SecurityError'); }
                });
                Object.defineProperty(navigator, 'serviceWorker', {
                  configurable: true,
                  get() { throw new DOMException('serviceWorker blocked', 'SecurityError'); }
                });
                """
            )
            console_errors: list[str] = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

            with _static_server() as url:
                page.goto(f"{url}?qa=restricted-browser", wait_until="domcontentloaded")
                page.wait_for_function("() => window._ephe")

                assert page.locator("#chat-area").is_visible()
                assert page.locator("#chat-input").is_visible()
                assert console_errors == []


def test_given_first_run_when_language_is_needed_then_only_language_dialog_is_visible_until_choice():
    """
    GIVEN a first-run browser with no language or onboarding state
    WHEN the PWA loads and the user chooses German
    THEN the user sees one modal step at a time and onboarding appears only after language choice.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 645, "height": 830}, service_workers="block")
            page = context.new_page()

            with _static_server() as url:
                page.goto(f"{url}?qa=first-run-sequence", wait_until="domcontentloaded")
                page.get_by_role("dialog", name="Select Language").wait_for(state="visible")
                assert page.get_by_role("dialog", name="Select Language").count() == 1
                assert page.locator("#onboarding-overlay:not(.hidden)").count() == 0

                page.get_by_role("button", name="🇩🇪 Deutsch").click()
                page.wait_for_selector("#lang-overlay", state="detached")
                page.wait_for_selector("#onboarding-overlay:not(.hidden)")
                assert page.get_by_role("dialog", name="Willkommen bei Ephe").count() == 1
                assert page.get_by_role("button", name="Starten →").is_disabled()

                category = page.locator('#ob-categories .ob-cat[data-cat="allround"]')
                assert category.get_attribute("role") != "listitem"
                assert category.get_attribute("aria-pressed") == "false"
                category.click()
                assert category.get_attribute("aria-pressed") == "true"
                assert page.get_by_role("button", name="Starten →").is_enabled()


def test_given_localized_tabs_when_opened_then_no_raw_i18n_keys_or_misleading_built_in_edits_show():
    """
    GIVEN the German Root-PWA after onboarding
    WHEN users visit Chat, Tasks and Skills
    THEN no raw i18n keys leak and built-in skills are presented as inspect/copy, not direct editing.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 645, "height": 830}, service_workers="block")
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'de');
                localStorage.setItem('ephe_onboarded', '1');
                """
            )

            with _static_server() as url:
                page.goto(f"{url}?qa=localized-tabs", wait_until="domcontentloaded")
                page.wait_for_function("() => window._ephe")

                assert "Offline-first" in page.locator(".welcome-sub").inner_text()
                assert "Aktuelle News suchen" not in page.locator("body").inner_text()

                page.get_by_role("tab", name="✅ Aufgaben").click()
                task_text = page.locator("#view-tasks").inner_text()
                assert "tasks.title" not in task_text
                assert "tasks.sub" not in task_text
                assert "Aufgaben" in task_text

                page.get_by_role("tab", name="⚡ Skills").click()
                page.wait_for_selector(".skill-action-btn")
                skills_text = page.locator("#view-skills").inner_text()
                assert "Create new skill" not in skills_text
                assert "Bearbeiten" not in skills_text
                assert "Ansehen" in skills_text


def test_given_ai_answer_when_action_buttons_clicked_then_each_action_uses_that_answer_context():
    """
    GIVEN an AI answer with action buttons
    WHEN the user clicks read aloud, copy, feedback and deepen
    THEN every action operates on the exact prompt/answer pair and deepen starts a contextual follow-up.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(
                viewport={"width": 1024, "height": 768},
                service_workers="block",
            )
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'de');
                localStorage.setItem('ephe_onboarded', '1');
                window.__copiedText = [];
                window.__playedAudio = [];
                Object.defineProperty(navigator, 'clipboard', {
                  value: { writeText: async (text) => { window.__copiedText.push(text); } },
                  configurable: true
                });
                window.Audio = function(url) {
                  this.url = url;
                  this.paused = true;
                  this.play = async () => { this.paused = false; window.__playedAudio.push(url); };
                  this.pause = () => { this.paused = true; };
                };
                """
            )

            feedback_calls: list[dict] = []
            audio_calls: list[dict] = []
            chat_calls: list[dict] = []

            def route_audio(route):
                audio_calls.append(route.request.post_data_json)
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"audio_url": "/audio/mock-tts.mp3"}),
                )

            def route_feedback(route):
                feedback_calls.append(
                    {
                        "url": route.request.url,
                        "body": route.request.post_data_json,
                    }
                )
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"saved": True}),
                )

            def route_chat(route):
                chat_calls.append(route.request.post_data_json)
                body = "\n".join(
                    [
                        'data: {"type":"chunk","data":"Vertiefte Antwort mit Kontext."}',
                        'data: {"type":"done"}',
                        "",
                    ]
                )
                route.fulfill(status=200, content_type="text/event-stream", body=body)

            page.route("**/api/audio/synthesize", route_audio)
            page.route("**/api/feedback/**", route_feedback)
            page.route("**/api/chat/stream", route_chat)

            with _static_server() as url:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_function("() => window._ephe")
                page.evaluate(
                    """
                    () => {
                      const app = window._ephe;
                      app._hideWelcome();
                      app.history = [
                        { role: 'user', content: 'Was kann Ephe?' },
                        { role: 'assistant', content: 'Ephe kann lokale Dateien analysieren.' }
                      ];
                      const bubble = app.renderAIBubble(101);
                      bubble.classList.remove('streaming-cursor');
                      bubble.textContent = 'Ephe kann lokale Dateien analysieren.';
                      app._showBubbleActions(
                        101,
                        'Was kann Ephe?',
                        'Ephe kann lokale Dateien analysieren.'
                      );
                    }
                    """
                )

                actions = page.locator('.bubble-actions[data-msg-id="101"]')
                assert actions.count() == 1
                for action in ["speak", "copy", "thumbs_up", "thumbs_down", "deepen"]:
                    assert actions.locator(f'[data-action="{action}"]').count() == 1

                actions.locator('[data-action="copy"]').click()
                assert page.evaluate("() => window.__copiedText") == ["Ephe kann lokale Dateien analysieren."]
                assert "Kopiert" in actions.locator('[data-action="copy"]').inner_text()

                actions.locator('[data-action="speak"]').click()
                page.wait_for_function("() => window.__playedAudio.length === 1")
                assert audio_calls[-1]["text"] == "Ephe kann lokale Dateien analysieren."
                assert page.evaluate("() => window.__playedAudio") == ["/audio/mock-tts.mp3"]

                actions.locator('[data-action="thumbs_up"]').click()
                assert feedback_calls[-1]["url"].endswith("/api/feedback/thumbs_up")
                assert feedback_calls[-1]["body"]["prompt"] == "Was kann Ephe?"
                assert feedback_calls[-1]["body"]["response"] == "Ephe kann lokale Dateien analysieren."

                actions.locator('[data-action="thumbs_down"]').click()
                assert page.locator("#reason-picker").is_visible()
                page.locator("#reason-picker").get_by_text("Falsch", exact=True).click()
                assert feedback_calls[-1]["url"].endswith("/api/feedback/thumbs_down")
                assert feedback_calls[-1]["body"]["reason"] == "Falsch"

                actions.locator('[data-action="deepen"]').click()
                page.wait_for_function("() => document.querySelectorAll('.bubble-ai').length >= 2")
                assert chat_calls
                assert "Was kann Ephe?" in chat_calls[-1]["message"]
                assert "Ephe kann lokale Dateien analysieren." in chat_calls[-1]["message"]
                user_bubbles = page.locator(".bubble-user")
                assert "Vertiefe" in user_bubbles.nth(user_bubbles.count() - 1).inner_text()


def test_given_clipboard_api_rejects_when_copy_clicked_then_legacy_copy_fallback_confirms_action():
    """
    GIVEN the browser exposes navigator.clipboard but rejects writes
    WHEN the user clicks copy on an AI answer
    THEN Ephe falls back to selection copy and still gives visible confirmation.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(
                viewport={"width": 1024, "height": 768},
                service_workers="block",
            )
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'de');
                localStorage.setItem('ephe_onboarded', '1');
                window.__execCommandCalls = [];
                Object.defineProperty(navigator, 'clipboard', {
                  value: { writeText: async () => { throw new Error('denied'); } },
                  configurable: true
                });
                document.execCommand = (cmd) => {
                  window.__execCommandCalls.push(cmd);
                  return cmd === 'copy';
                };
                """
            )

            with _static_server() as url:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_function("() => window._ephe")
                page.evaluate(
                    """
                    () => {
                      const app = window._ephe;
                      app._hideWelcome();
                      const bubble = app.renderAIBubble(102);
                      bubble.classList.remove('streaming-cursor');
                      bubble.textContent = 'Fallback Copy Antwort';
                      app._showBubbleActions(102, 'Prompt', 'Fallback Copy Antwort');
                    }
                    """
                )

                copy = page.locator('.bubble-actions[data-msg-id="102"] [data-action="copy"]')
                assert copy.count() == 1
                copy.click()
                assert page.evaluate("() => window.__execCommandCalls") == ["copy"]
                assert "Kopiert" in copy.inner_text()


def test_given_skill_shortcuts_when_each_chip_is_clicked_then_composer_selects_and_sends_that_skill():
    """
    GIVEN the visible shortcut row lists all built-in skills
    WHEN a user clicks each chip and sends
    THEN the composer shows the selected skill and the chat request contains that exact trigger.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(
                viewport={"width": 645, "height": 830},
                service_workers="block",
            )
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'de');
                localStorage.setItem('ephe_onboarded', '1');
                """
            )
            chat_calls: list[dict] = []

            def route_chat(route):
                chat_calls.append(route.request.post_data_json)
                body = "\n".join(
                    [
                        'data: {"type":"chunk","data":"Skill ok."}',
                        'data: {"type":"done"}',
                        "",
                    ]
                )
                route.fulfill(status=200, content_type="text/event-stream", body=body)

            page.route("**/api/chat/stream", route_chat)

            with _static_server() as url:
                page.goto(f"{url}?qa=skill-shortcuts", wait_until="domcontentloaded")
                page.wait_for_function(
                    f"() => document.querySelectorAll('#skill-chips .skill-chip').length >= {len(SKILL_FIXTURES)}"
                )

                for expected_index, skill in enumerate(SKILL_FIXTURES, start=1):
                    trigger = skill["trigger"]
                    chip = page.locator(f'#skill-chips .skill-chip[data-trigger="{trigger}"]')
                    assert chip.count() == 1
                    assert chip.get_attribute("aria-label")
                    assert chip.get_attribute("title")

                    chip.click()
                    page.wait_for_function(
                        "(trigger) => document.querySelector('#input-wrap')?.dataset.selectedSkill === trigger && document.querySelector('#chat-input')?.value === ''",
                        arg=trigger,
                    )
                    assert page.locator("#input-wrap").get_attribute("data-selected-skill") == trigger
                    assert page.locator("#selected-skill-pill").inner_text().strip() == trigger
                    assert "active" in (chip.get_attribute("class") or "")
                    assert chip.get_attribute("aria-pressed") == "true"

                    page.locator("#chat-input").fill(f"Pruefe Funktion {expected_index}")
                    page.locator("#send-btn").click()
                    if trigger == "/research":
                        assert page.locator("#desktop-online-confirm").is_visible()
                        page.locator("#desktop-online-start").click()
                    page.wait_for_function(
                        "(expected) => window._ephe && window._ephe.isStreaming === false && document.querySelectorAll('.bubble-ai').length >= expected",
                        arg=expected_index,
                    )
                    assert chat_calls[-1]["message"].startswith(trigger)
                    assert page.locator("#input-wrap").get_attribute("data-selected-skill") in (None, "")
                    assert "hidden" in (page.locator("#selected-skill-pill").get_attribute("class") or "")
                    assert chip.get_attribute("aria-pressed") == "false"


def test_given_desktop_skill_row_when_risky_skills_render_then_scope_badges_are_visible():
    """
    GIVEN the desktop shortcut row contains local, online, and approval-gated skills
    WHEN the chips render
    THEN optional online and approval functions are visibly marked before use.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 1024, "height": 768}, service_workers="block")
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'de');
                localStorage.setItem('ephe_onboarded', '1');
                """
            )

            with _static_server() as url:
                page.goto(f"{url}?qa=desktop-skill-scope", wait_until="domcontentloaded")
                page.wait_for_function(
                    "() => document.querySelector('#skill-chips .skill-chip[data-trigger=\"/research\"] .skill-chip-badge')"
                )

                research = page.locator('#skill-chips .skill-chip[data-trigger="/research"]')
                shell = page.locator('#skill-chips .skill-chip[data-trigger="/shell"]')
                write = page.locator('#skill-chips .skill-chip[data-trigger="/write"]')

                assert research.get_attribute("data-scope") == "online"
                assert "Online optional" in research.inner_text()
                assert shell.get_attribute("data-scope") == "approval"
                assert "Approval" in shell.inner_text()
                assert write.get_attribute("data-scope") == "local"
                assert "Online optional" not in write.inner_text()
                assert "Approval" not in write.inner_text()


def test_given_desktop_research_skill_when_sent_then_online_confirmation_is_required_before_chat():
    """
    GIVEN /research can leave the offline-first boundary
    WHEN the desktop user sends a research request
    THEN no chat request is sent until the explicit online confirmation is accepted.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 1024, "height": 768}, service_workers="block")
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'de');
                localStorage.setItem('ephe_onboarded', '1');
                """
            )
            chat_calls: list[dict] = []

            def route_chat(route):
                chat_calls.append(route.request.post_data_json)
                body = "\n".join(
                    [
                        'data: {"type":"chunk","data":"Research Desktop OK"}',
                        'data: {"type":"done"}',
                        "",
                    ]
                )
                route.fulfill(status=200, content_type="text/event-stream", body=body)

            page.route("**/api/chat/stream", route_chat)

            with _static_server() as url:
                page.goto(f"{url}?qa=desktop-research-confirm", wait_until="domcontentloaded")
                page.wait_for_function("() => window._ephe")

                page.locator('#skill-chips .skill-chip[data-trigger="/research"]').click()
                page.locator("#chat-input").fill("Pruefe aktuelle Quellen")
                page.locator("#send-btn").click()

                assert chat_calls == []
                confirm = page.locator("#desktop-online-confirm")
                assert confirm.is_visible()
                assert "Online optional" in confirm.inner_text()
                assert page.locator("#chat-input").input_value() == "Pruefe aktuelle Quellen"

                page.locator("#desktop-online-cancel").click()
                assert chat_calls == []
                assert page.locator("#chat-input").input_value() == "Pruefe aktuelle Quellen"

                page.locator("#send-btn").click()
                page.locator("#desktop-online-start").click()
                page.wait_for_function("() => document.body.innerText.includes('Research Desktop OK')")

                assert chat_calls
                assert chat_calls[-1]["message"].startswith("/research")
                assert chat_calls[-1]["autonomous"] is False


def test_given_missing_gemma_model_when_root_pwa_loads_then_recovery_help_is_visible():
    """
    GIVEN Ollama is reachable but gemma4:12b is missing
    WHEN the Root-PWA checks health
    THEN the UI shows concrete recovery commands instead of a generic offline warning.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 1024, "height": 768}, service_workers="block")
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'de');
                localStorage.setItem('ephe_onboarded', '1');
                """
            )

            def route_health(route):
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "status": "degraded",
                            "ollama": True,
                            "active_model": "gemma4:12b",
                            "active_provider": "local_ollama",
                            "offline_capable": True,
                            "requires_internet": False,
                            "model_installed": False,
                            "detail": "Modell 'gemma4:12b' nicht installiert",
                        }
                    ),
                )

            page.route("**/api/health", route_health)

            with _static_server() as url:
                page.goto(f"{url}?qa=missing-model-help", wait_until="domcontentloaded")
                page.wait_for_selector("#offline-banner:not(.hidden)")

                text = page.locator("#offline-banner").inner_text()
                assert "gemma4:12b" in text
                assert "ephe doctor" in text
                assert "ephe start" in text
                assert "Modell" in text or "model" in text.lower()


def test_given_desktop_chat_stream_reports_missing_model_then_recovery_help_is_rendered():
    """
    GIVEN chat starts while gemma4:12b is missing
    WHEN the backend streams a model error
    THEN the desktop chat renders a repair path instead of a bare model exception.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 1024, "height": 768}, service_workers="block")
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'de');
                localStorage.setItem('ephe_onboarded', '1');
                """
            )

            def route_chat(route):
                body = "\n".join(
                    [
                        "data: {\"type\":\"error\",\"msg\":\"Modell 'gemma4:12b' nicht installiert\"}",
                        'data: {"type":"done"}',
                        "",
                    ]
                )
                route.fulfill(status=200, content_type="text/event-stream", body=body)

            page.route("**/api/chat/stream", route_chat)

            with _static_server() as url:
                page.goto(f"{url}?qa=desktop-stream-missing-model", wait_until="domcontentloaded")
                page.wait_for_function("() => window._ephe")
                page.locator("#chat-input").fill("hey")
                page.locator("#send-btn").click()
                page.wait_for_function("() => document.querySelector('.bubble-ai') && !window._ephe.isStreaming")

                text = page.locator(".bubble-ai").last.inner_text()
                assert "gemma4:12b" in text
                assert "ephe doctor" in text
                assert "ephe start" in text


def test_given_mobile_chat_stream_reports_missing_model_then_recovery_help_is_rendered():
    """
    GIVEN the phone is paired but gemma4:12b is missing
    WHEN the backend streams a model error
    THEN mobile.html gives a concrete recovery path the user can run on the Mac.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            page = context.new_page()
            page.add_init_script("localStorage.setItem('ephe-lang', 'de');")

            def route_chat(route):
                body = "\n".join(
                    [
                        "data: {\"type\":\"error\",\"msg\":\"Modell 'gemma4:12b' nicht installiert\"}",
                        'data: {"type":"done"}',
                        "",
                    ]
                )
                route.fulfill(status=200, content_type="text/event-stream", body=body)

            page.route("**/api/chat/stream", route_chat)

            with _static_server() as url:
                mobile_url = url.replace("/index.html", "/mobile.html")
                page.goto(f"{mobile_url}?qa=mobile-stream-missing-model", wait_until="domcontentloaded")
                page.wait_for_selector("#input")
                page.locator("#input").fill("hey")
                page.locator("#send-btn").click()
                page.wait_for_function("() => document.body.innerText.includes('ephe doctor')")

                text = page.locator("#chat .msg.ai").last.inner_text()
                assert "gemma4:12b" in text
                assert "ephe doctor" in text
                assert "ephe start" in text


def test_given_mobile_composer_when_rendered_then_tools_are_clear_tap_targets_and_image_attach_has_state(tmp_path):
    """
    GIVEN a mobile viewport comparable to the in-app browser
    WHEN the composer renders and the user attaches an image
    THEN all composer tools are visible, non-overlapping tap targets and attachment state is explicit.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    image_file = tmp_path / "tiny.png"
    image_file.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
        )
    )

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(
                viewport={"width": 390, "height": 844},
                service_workers="block",
            )
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'de');
                localStorage.setItem('ephe_onboarded', '1');
                """
            )

            with _static_server() as url:
                page.goto(f"{url}?qa=composer-mobile", wait_until="domcontentloaded")
                page.wait_for_selector("#input-wrap")

                viewport_width = page.evaluate("() => window.innerWidth")
                wrap = page.locator("#input-wrap").bounding_box()
                assert wrap
                assert wrap["width"] >= viewport_width - 32

                tool_selectors = ["#attach-btn", "#camera-btn", "#mic-btn", "#send-btn"]
                boxes = {}
                for selector in tool_selectors:
                    locator = page.locator(selector)
                    assert locator.is_visible()
                    assert locator.get_attribute("aria-label") or locator.get_attribute("title")
                    box = locator.bounding_box()
                    assert box
                    boxes[selector] = box
                    assert box["width"] >= 44
                    assert box["height"] >= 44

                for left, right in zip(tool_selectors, tool_selectors[1:]):
                    assert boxes[left]["x"] + boxes[left]["width"] <= boxes[right]["x"] + 1

                page.set_input_files("#img-input", str(image_file))
                page.wait_for_function("() => document.querySelector('#img-preview-bar')?.style.display === 'flex'")
                assert "has-image" in (page.locator("#attach-btn").get_attribute("class") or "")
                assert "Bild angefuegt" in (page.locator("#input-wrap").get_attribute("aria-label") or "")

                page.locator("#img-remove-btn").click()
                assert "has-image" not in (page.locator("#attach-btn").get_attribute("class") or "")


def test_given_mobile_page_when_socketio_is_missing_then_chat_still_sends_and_renders():
    """
    GIVEN the phone opens mobile.html through the FastAPI server without Socket.IO
    WHEN the user sends a chat message
    THEN the mobile frontend does not crash and renders the streamed answer.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            page = context.new_page()
            page_errors: list[str] = []
            chat_calls: list[dict] = []
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))

            def route_chat(route):
                chat_calls.append(route.request.post_data_json)
                body = "\n".join(
                    [
                        'data: {"type":"chunk","data":"Mobile OK"}',
                        'data: {"type":"done"}',
                        "",
                    ]
                )
                route.fulfill(status=200, content_type="text/event-stream", body=body)

            page.route("**/api/chat/stream", route_chat)

            with _static_server() as url:
                mobile_url = url.replace("/index.html", "/mobile.html")
                page.goto(f"{mobile_url}?qa=mobile-chat-no-socket", wait_until="domcontentloaded")
                page.wait_for_selector("#input")

                page.locator("#input").fill("Hallo vom Handy")
                page.locator("#send-btn").click()
                page.wait_for_function("() => document.body.innerText.includes('Mobile OK')")

                assert chat_calls
                assert chat_calls[-1]["message"] == "Hallo vom Handy"
                assert chat_calls[-1]["autonomous"] is False
                assert page_errors == []


@pytest.mark.parametrize(
    "viewport",
    [
        {"width": 390, "height": 844},
        {"width": 375, "height": 667},
        {"width": 320, "height": 568},
    ],
)
def test_given_phone_qr_page_when_opened_then_primary_controls_are_visible_and_tappable(viewport):
    """
    GIVEN the phone opens mobile.html from the QR code
    WHEN the first screen renders on common phone sizes
    THEN the chat, skills, input, camera, mic, and send controls are visible, tappable, and do not overflow.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport=viewport, service_workers="block")
            page = context.new_page()
            page.add_init_script("localStorage.setItem('ephe-lang', 'de');")

            with _static_server() as url:
                mobile_url = url.replace("/index.html", "/mobile.html")
                page.goto(f"{mobile_url}?qa=phone-visible-tappable", wait_until="domcontentloaded")
                page.wait_for_selector("#input")

                assert page.evaluate(
                    "() => document.documentElement.scrollWidth <= window.innerWidth"
                )
                assert page.locator("#chat #welcome").is_visible()

                selectors = ["#mobile-skill-chips", ".input-wrap", "#camera-btn", "#mic-btn", "#send-btn"]
                for selector in selectors:
                    box = page.locator(selector).bounding_box()
                    assert box, selector
                    assert box["x"] >= 0, selector
                    assert box["x"] + box["width"] <= viewport["width"] + 1, selector
                    assert box["y"] >= 0, selector
                    assert box["y"] + box["height"] <= viewport["height"] + 1, selector

                for selector in ["#camera-btn", "#mic-btn", "#send-btn"]:
                    result = page.evaluate(
                        """(selector) => {
                            const el = document.querySelector(selector);
                            const rect = el.getBoundingClientRect();
                            const hit = document.elementFromPoint(
                                rect.left + rect.width / 2,
                                rect.top + rect.height / 2
                            );
                            return {
                                width: rect.width,
                                height: rect.height,
                                hit: hit === el || el.contains(hit),
                            };
                        }""",
                        selector,
                    )
                    assert result["width"] >= 44
                    assert result["height"] >= 44
                    assert result["hit"] is True, selector

                page.locator("#input").fill("Hallo")
                page.locator("#send-btn").click()
                assert page.locator(".msg.user").last.inner_text() == "Hallo"


def test_given_mobile_health_when_local_ollama_is_ready_then_status_shows_local_not_offline():
    """
    GIVEN the mobile page receives the current /api/health payload
    WHEN the status label is rendered
    THEN it shows the offline-first local state instead of a false offline warning.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            page = context.new_page()
            page.add_init_script("localStorage.setItem('ephe-lang', 'de');")

            with _static_server() as url:
                mobile_url = url.replace("/index.html", "/mobile.html")
                page.goto(f"{mobile_url}?qa=mobile-health-local", wait_until="domcontentloaded")
                page.wait_for_selector("#status-label")
                page.wait_for_function(
                    "() => document.querySelector('#status-label')?.textContent?.trim() !== 'Online'"
                )

                label = page.locator("#status-label")
                assert "Lokal" in label.inner_text()
                assert "offline" not in (label.get_attribute("class") or "")
                assert "offline" not in (page.locator("#status-dot").get_attribute("class") or "")


def test_given_mobile_user_clears_chat_when_welcome_returns_then_cards_still_work():
    """
    GIVEN the user starts over with the mobile New button
    WHEN the welcome state is restored
    THEN the task cards remain available and still send the selected prompt.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            page = context.new_page()
            page.add_init_script("localStorage.setItem('ephe-lang', 'de');")
            chat_calls: list[dict] = []

            def route_chat(route):
                chat_calls.append(route.request.post_data_json)
                body = "\n".join(
                    [
                        'data: {"type":"chunk","data":"Karten OK"}',
                        'data: {"type":"done"}',
                        "",
                    ]
                )
                route.fulfill(status=200, content_type="text/event-stream", body=body)

            page.route("**/api/chat/stream", route_chat)

            with _static_server() as url:
                mobile_url = url.replace("/index.html", "/mobile.html")
                page.goto(f"{mobile_url}?qa=mobile-clear-cards", wait_until="domcontentloaded")
                page.wait_for_selector("#btn-clear")

                page.locator("#btn-clear").click()
                assert page.locator("#chat #welcome").is_visible()
                assert page.locator("#chat .welcome-card").count() == 4

                page.locator("#chat .welcome-card").nth(2).click()
                page.wait_for_function("() => document.body.innerText.includes('Karten OK')")

                assert chat_calls
                assert chat_calls[-1]["message"].startswith("/write")
                assert chat_calls[-1]["autonomous"] is False


def test_given_mobile_skill_row_when_loaded_then_only_real_skill_triggers_are_shown_and_tappable():
    """
    GIVEN the mobile shortcut row is loaded from /api/skills
    WHEN the user taps visible shortcuts
    THEN every shortcut maps to a real public skill trigger and fills the composer.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            page = context.new_page()

            with _static_server() as url:
                mobile_url = url.replace("/index.html", "/mobile.html")
                page.goto(f"{mobile_url}?qa=mobile-real-skills", wait_until="domcontentloaded")
                page.wait_for_function(
                    "() => document.querySelectorAll('#mobile-skill-chips .skill-chip').length >= 4"
                )

                expected = {skill["trigger"] for skill in SKILL_FIXTURES}
                actual = page.locator("#mobile-skill-chips .skill-chip").evaluate_all(
                    "(chips) => chips.map(chip => chip.dataset.trigger)"
                )
                assert set(actual).issubset(expected)
                assert "/repair" not in actual
                assert "/map" not in actual

                for trigger in actual[:4]:
                    chip = page.locator(f'#mobile-skill-chips .skill-chip[data-trigger="{trigger}"]')
                    assert chip.count() == 1
                    chip.click()
                    assert page.locator("#input").input_value() == f"{trigger} "


def test_given_mobile_skill_row_when_risky_skills_render_then_scope_badges_are_visible():
    """
    GIVEN the mobile shortcut row contains local, online, and approval-gated skills
    WHEN the chips render
    THEN optional online and approval functions are visibly marked before use.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            page = context.new_page()

            with _static_server() as url:
                mobile_url = url.replace("/index.html", "/mobile.html")
                page.goto(f"{mobile_url}?qa=mobile-skill-scope", wait_until="domcontentloaded")
                page.wait_for_function(
                    "() => document.querySelector('#mobile-skill-chips .skill-chip[data-trigger=\"/research\"] .skill-chip-badge')"
                )

                research = page.locator('#mobile-skill-chips .skill-chip[data-trigger="/research"]')
                shell = page.locator('#mobile-skill-chips .skill-chip[data-trigger="/shell"]')
                write = page.locator('#mobile-skill-chips .skill-chip[data-trigger="/write"]')

                assert research.get_attribute("data-scope") == "online"
                assert "Online optional" in research.inner_text()
                assert shell.get_attribute("data-scope") == "approval"
                assert "Approval" in shell.inner_text()
                assert write.get_attribute("data-scope") == "local"
                assert "Online optional" not in write.inner_text()
                assert "Approval" not in write.inner_text()


def test_given_mobile_research_card_when_tapped_then_online_confirmation_is_required_before_chat():
    """
    GIVEN /research can leave the offline-first boundary
    WHEN the user taps the web-search welcome card
    THEN the mobile UI asks for explicit online confirmation before sending chat.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            page = context.new_page()
            page.add_init_script("localStorage.setItem('ephe-lang', 'de');")
            chat_calls: list[dict] = []

            def route_chat(route):
                chat_calls.append(route.request.post_data_json)
                body = "\n".join(
                    [
                        'data: {"type":"chunk","data":"Research OK"}',
                        'data: {"type":"done"}',
                        "",
                    ]
                )
                route.fulfill(status=200, content_type="text/event-stream", body=body)

            page.route("**/api/chat/stream", route_chat)

            with _static_server() as url:
                mobile_url = url.replace("/index.html", "/mobile.html")
                page.goto(f"{mobile_url}?qa=mobile-research-confirm", wait_until="domcontentloaded")
                page.wait_for_selector("#chat .welcome-card")

                page.locator('#chat .welcome-card[data-prompt^="/research"]').click()
                assert chat_calls == []
                assert page.locator("#online-confirm").is_visible()
                assert "Online optional" in page.locator("#online-confirm").inner_text()
                assert page.locator("#input").input_value().startswith("/research")

                page.locator("#online-confirm-start").click()
                page.wait_for_function("() => document.body.innerText.includes('Research OK')")

                assert chat_calls
                assert chat_calls[-1]["message"].startswith("/research")
                assert chat_calls[-1]["autonomous"] is False


def test_given_mobile_power_monitor_is_hidden_when_page_loads_then_no_missing_power_api_is_called():
    """
    GIVEN the mobile power monitor is hidden
    WHEN the page initializes
    THEN it must not call the unavailable /api/system/power endpoint in the background.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            page = context.new_page()
            power_calls: list[str] = []

            def route_power(route):
                power_calls.append(route.request.url)
                route.fulfill(status=404, content_type="application/json", body=json.dumps({"detail": "missing"}))

            page.route("**/api/system/power", route_power)

            with _static_server() as url:
                mobile_url = url.replace("/index.html", "/mobile.html")
                page.goto(f"{mobile_url}?qa=mobile-no-hidden-power", wait_until="domcontentloaded")
                page.wait_for_selector("#mobile-skill-chips .skill-chip")
                page.wait_for_timeout(250)

                assert power_calls == []


def test_given_model_streams_thinking_when_rendered_then_raw_reasoning_is_not_exposed():
    """
    GIVEN the model/provider sends internal thinking events
    WHEN the Root-PWA renders the response stream
    THEN users see only progress/duration UI, not raw reasoning text.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(
                viewport={"width": 645, "height": 830},
                service_workers="block",
            )
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'de');
                localStorage.setItem('ephe_onboarded', '1');
                """
            )

            def route_chat(route):
                body = "\n".join(
                    [
                        'data: {"type":"thinking_start"}',
                        'data: {"type":"thinking","data":"SECRET_INTERNAL_REASONING should never render"}',
                        'data: {"type":"chunk","data":"Ich arbeite lokal."}',
                        'data: {"type":"done"}',
                        "",
                    ]
                )
                route.fulfill(status=200, content_type="text/event-stream", body=body)

            page.route("**/api/chat/stream", route_chat)

            with _static_server() as url:
                page.goto(f"{url}?qa=thinking-safe", wait_until="domcontentloaded")
                page.locator("#chat-input").fill("Was kannst du offline?")
                page.locator("#send-btn").click()
                page.wait_for_function(
                    "() => document.querySelector('.bubble-ai') && !document.querySelector('.bubble-ai').classList.contains('streaming-cursor')"
                )

                messages = page.locator("#messages").inner_text()
                assert "Ich arbeite lokal." in messages
                assert "SECRET_INTERNAL_REASONING" not in messages
                assert "should never render" not in messages
                assert "thinking-open" not in (page.locator(".thinking-panel").get_attribute("class") or "")
                assert "Gedacht" in page.locator(".thinking-label").inner_text()


@pytest.mark.skip(reason="Legacy PWA migrated to React+Vite; source files (app/src/index.html, main.js, i18n.js, service-worker.js) and legacy UI features (export button, mode toggle, tasks tab) were removed/refactored. Test references stale paths.")
def test_given_root_pwa_html_when_loaded_then_no_external_font_hosts_are_required():
    """
    GIVEN Ephe claims an offline-first first-run path
    WHEN the root PWA HTML is inspected
    THEN it does not require Google Fonts or other remote font hosts.
    """
    html = (ROOT / "app" / "src" / "index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html


def test_given_long_chat_history_when_user_sends_message_then_stream_request_history_is_compacted():
    """
    GIVEN a long local chat with large assistant outputs
    WHEN the user sends a new message
    THEN the PWA sends a compact bounded history to the stream endpoint.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 1280, "height": 820}, service_workers="block")
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'en');
                localStorage.setItem('ephe_onboarded', '1');
                """
            )

            chat_calls: list[dict] = []

            def route_chat(route):
                chat_calls.append(route.request.post_data_json)
                body = "\n".join(
                    [
                        'data: {"type":"chunk","data":"ok"}',
                        'data: {"type":"done"}',
                        "",
                    ]
                )
                route.fulfill(status=200, content_type="text/event-stream", body=body)

            page.route("**/api/chat/stream", route_chat)

            with _static_server() as url:
                page.goto(f"{url}?qa=long-history", wait_until="domcontentloaded")
                page.wait_for_function("() => window._ephe")
                page.evaluate(
                    """
                    () => {
                      const huge = 'Workspace analysis '.repeat(900);
                      window._ephe.history = Array.from({ length: 40 }, (_, index) => ({
                        role: index % 2 ? 'assistant' : 'user',
                        content: `${index}: ${huge}`
                      }));
                    }
                    """
                )

                page.locator("#chat-input").fill("ja starte")
                page.locator("#send-btn").click()
                page.wait_for_function("() => !window._ephe.isStreaming")

                assert chat_calls
                payload = chat_calls[-1]
                assert payload["message"] == "ja starte"
                assert len(payload["history"]) <= 12
                assert len(json.dumps(payload["history"])) <= 30_000
                assert page.locator("#chat-input").is_enabled()


def test_given_stream_quality_events_when_rendered_then_activity_panel_shows_quality_and_artifact_status():
    """
    GIVEN the backend emits local quality and artifact checks
    WHEN the PWA consumes the stream
    THEN the user sees visible quality/artifact status instead of a silent background check.
    """
    sync_api = pytest.importorskip("playwright.sync_api")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed: {exc}")

        with browser:
            context = browser.new_context(viewport={"width": 1280, "height": 820}, service_workers="block")
            page = context.new_page()
            page.add_init_script(
                """
                localStorage.setItem('ephe-lang', 'en');
                localStorage.setItem('ephe_onboarded', '1');
                """
            )

            def route_chat(route):
                body = "\n".join(
                    [
                        'data: {"type":"thinking_start"}',
                        'data: {"type":"quality_check","status":"running","skill":"pdf-creator"}',
                        'data: {"type":"artifact_check","artifact_type":"pdf","status":"passed","path":"/Users/test/Downloads/report.pdf","warnings":[]}',
                        'data: {"type":"quality_check","status":"passed","skill":"pdf-creator","issues":[]}',
                        'data: {"type":"chunk","data":"PDF saved."}',
                        'data: {"type":"done"}',
                        "",
                    ]
                )
                route.fulfill(status=200, content_type="text/event-stream", body=body)

            page.route("**/api/chat/stream", route_chat)

            with _static_server() as url:
                page.goto(f"{url}?qa=quality-events", wait_until="domcontentloaded")
                page.locator("#chat-input").fill("/pdf Create report")
                page.locator("#send-btn").click()
                page.wait_for_function("() => !window._ephe.isStreaming")

                terminal = page.locator("#ap-terminal").inner_text()
                assert "Quality check" in terminal
                assert "Quality OK" in terminal
                assert "Artifact" in terminal
                assert "report.pdf" in terminal
