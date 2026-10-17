"""W3b visual check — Settings skills tab (pack export, file install, URL install).

Against the real backend on 8765 and Vite on 5174, at 1280x900 and 390x844.
Each pass writes new PNG names: the judge caches by file name.
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5174/#/chat"
OUT = Path("docs/media/w3b_2026-09-09")
OUT.mkdir(parents=True, exist_ok=True)

INIT_JS = "() => { localStorage.setItem('i18nextLng', 'de') }"


def open_skills(page, mobile=False):
    page.goto(BASE, wait_until="networkidle")
    page.evaluate("() => { localStorage.setItem('i18nextLng', 'de') }")
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(1500)
    if mobile:
        page.get_by_label("Menü umschalten").first.click()
        page.wait_for_timeout(500)
    page.locator('[data-testid="sidebar-settings-btn"]').click()
    page.wait_for_timeout(800)
    page.evaluate("() => { window.dispatchEvent(new CustomEvent('ephe:settings-tab', { detail: { tab: 'skills' } })) }")
    page.wait_for_timeout(1200)


def rects(page):
    return page.evaluate(
        "() => { const out = {}; for (const sel of ['[data-testid=\"skill-install-url-input\"]', '[data-testid=\"skill-install-url\"]', '[data-testid=\"pack-export-core\"]']) {"
        " const el = document.querySelector(sel); if (el) { const b = el.getBoundingClientRect(); out[sel] = [b.x, b.y, b.width, b.height].map(Math.round) } } return out }"
    )


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.add_init_script(INIT_JS)
        open_skills(page)
        page.screenshot(path=str(OUT / "w3b_01b_skills_desktop.png"))
        print("desktop rects:", rects(page))
        page.close()

        mob = browser.new_page(viewport={"width": 390, "height": 844})
        mob.add_init_script(INIT_JS)
        open_skills(mob, mobile=True)
        mob.screenshot(path=str(OUT / "w3b_02b_skills_mobile.png"))
        print("mobile rects:", rects(mob))

        browser.close()
        print("screenshots in", OUT)


if __name__ == "__main__":
    main()
