"""W3a visual check — session branch chip (Z37) in header + session menu.

Real backend on 8765, dev server 5174. Desktop 1280x900 + mobile 390x844.
Flow: one chat turn -> open session menu (Branch entry) -> click Branch ->
header shows 'Zweig #N' chip (language-gate: ignore — the label the German UI renders). Fresh PNG names per pass (judge cache trap).
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5174/#/chat"
OUT = Path("docs/media/w3a_2026-09-09")
OUT.mkdir(parents=True, exist_ok=True)

INIT_JS = "() => { localStorage.setItem('i18nextLng', 'de') }"


def rects(page):
    return page.evaluate(
        "() => { const r = {}; const c = document.querySelector('[data-testid=\"header-branch-from\"]');"
        " if (c) { const b = c.getBoundingClientRect(); r.chip = [b.x, b.y, b.width, b.height].map(Math.round); r.chipText = c.textContent }"
        " const h = document.querySelector('h1'); if (h) { const b = h.getBoundingClientRect(); r.h1 = [b.x, b.y, b.width, b.height].map(Math.round) } return r }"
    )


def run_flow(page, msg):
    page.goto(BASE, wait_until="networkidle")
    page.evaluate("() => { localStorage.setItem('i18nextLng', 'de') }")
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(1800)
    composer = page.get_by_placeholder("Schreibe eine Nachricht...")
    composer.click()
    composer.fill(msg)
    page.keyboard.press("Enter")
    page.wait_for_timeout(12000)


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # Desktop
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        run_flow(page, "Antworte kurz: 1 plus 1.")

        # Session menu with Branch entry
        page.locator('[data-testid^="session-menu-"]').first.click()
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUT / "w3a_01_desktop_menu.png"))

        page.locator('[data-testid="menu-branch"]').click()
        page.wait_for_timeout(700)
        page.screenshot(path=str(OUT / "w3a_02_desktop_branch_chip.png"))
        print("desktop:", rects(page))
        page.close()

        # Mobile
        mob = browser.new_page(viewport={"width": 390, "height": 844})
        run_flow(mob, "Antworte kurz: 2 plus 2.")
        mob.get_by_label("Menü umschalten").first.click()
        mob.wait_for_timeout(500)
        mob.locator('[data-testid^="session-menu-"]').first.click()
        mob.wait_for_timeout(500)
        mob.locator('[data-testid="menu-branch"]').click()
        mob.wait_for_timeout(700)
        mob.screenshot(path=str(OUT / "w3a_03_mobile_branch_chip.png"))
        print("mobile:", rects(mob))

        browser.close()
        print("screenshots in", OUT)


if __name__ == "__main__":
    main()
