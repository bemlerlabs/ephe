"""W3d visual check — the Discord channel card in the Settings mobile tab.

Runs against the live 8765 backend and the 5174 dev server, desktop and 390 mobile.
PNG names change per pass so a cached judgement cannot be reused.
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5174/#/chat"
OUT = Path("docs/media/w3d_2026-09-09")
OUT.mkdir(parents=True, exist_ok=True)

INIT_JS = "() => { localStorage.setItem('i18nextLng', 'de') }"


def open_mobile(page, mobile=False):
    page.goto(BASE, wait_until="networkidle")
    page.evaluate("() => { localStorage.setItem('i18nextLng', 'de') }")
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(1500)
    if mobile:
        page.get_by_label("Menü umschalten").first.click()
        page.wait_for_timeout(500)
    page.locator('[data-testid="sidebar-settings-btn"]').click()
    page.wait_for_timeout(800)
    page.evaluate(
        "() => { window.dispatchEvent(new CustomEvent('ephe:settings-tab', { detail: { tab: 'mobile' } })) }"
    )
    page.wait_for_timeout(1200)


def rects(page):
    return page.evaluate(
        "() => { const out = {}; for (const t of ['discord-card', 'discord-status-dot', 'discord-setup', 'discord-token-input', 'discord-token-save']) {"
        " const el = document.querySelector(`[data-testid=\"${t}\"]`); if (el) { const b = el.getBoundingClientRect(); out[t] = [b.x, b.y, b.width, b.height].map(Math.round) } } return out }"
    )


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.add_init_script(INIT_JS)
        open_mobile(page)
        page.screenshot(path=str(OUT / "w3d_01b_discord_desktop.png"))
        print("desktop rects:", rects(page))
        page.close()

        mob = browser.new_page(viewport={"width": 390, "height": 844})
        mob.add_init_script(INIT_JS)
        open_mobile(mob, mobile=True)
        mob.evaluate(
            "() => { const el = document.querySelector('[data-testid=\"discord-card\"]');"
            " if (el) el.scrollIntoView({ block: 'center' }); }"
        )
        mob.wait_for_timeout(300)
        mob.screenshot(path=str(OUT / "w3d_02b_discord_mobile.png"))
        print("mobile rects:", rects(mob))

        browser.close()
        print("screenshots in", OUT)


if __name__ == "__main__":
    main()
