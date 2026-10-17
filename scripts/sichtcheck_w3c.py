"""W3c visual check — the Git tab (ReviewTab) with its stage/commit row.

Real backend on 8765, dev server 5174. Desktop 1280x900.
New PNG names every pass, because the judge keys its cache on the name.
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5174/#/chat"
OUT = Path("docs/media/w3c_2026-09-09")
OUT.mkdir(parents=True, exist_ok=True)

INIT_JS = "() => { localStorage.setItem('i18nextLng', 'de') }"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.add_init_script(INIT_JS)
        page.goto(BASE, wait_until="networkidle")
        page.evaluate("() => { localStorage.setItem('i18nextLng', 'de') }")
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(1500)
        # Open the Git tab straight from the toolbar row (parity with the reference)
        page.locator('[data-testid="toolbar-git"]').first.click()
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUT / "w3c_01c_git_tab_desktop.png"))
        print("rects:", page.evaluate(
            "() => { const out = {}; for (const t of ['git-stage-all', 'git-commit-msg', 'git-commit', 'review-file-list']) {"
            " const el = document.querySelector(`[data-testid=\"${t}\"]`); if (el) { const b = el.getBoundingClientRect(); out[t] = [b.x, b.y, b.width, b.height].map(Math.round) } } return out }"
        ))
        browser.close()
        print("screenshots in", OUT)


if __name__ == "__main__":
    main()
