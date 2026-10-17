"""R24 visual check: Settings → Mobile tab with the Telegram card @ 390px (read-only).

Opens the PWA in a mobile viewport, opens Settings through the ephe:open-settings
event, clicks the Mobile tab and takes desktop/mobile screenshots.
Stores NO token and never calls /pair (read-only visual check).
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("docs/media/r24_telegram_sichtcheck")
OUT.mkdir(parents=True, exist_ok=True)
BASE = "http://localhost:5173"

with sync_playwright() as p:
    browser = p.chromium.launch()
    # Mobile 390px
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    page = ctx.new_page()
    page.goto(f"{BASE}/#/chat", wait_until="networkidle")
    page.wait_for_timeout(1200)
    page.evaluate("window.dispatchEvent(new CustomEvent('ephe:open-settings'))")
    page.wait_for_timeout(600)
    mobile_tab = page.get_by_text("Mobile", exact=True)
    if mobile_tab.count() == 0:
        mobile_tab = page.locator("[role=tab], button").filter(has_text="Mobile")
    mobile_tab.first.click()
    page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT / "mobile_390_settings.png"))
    # Bring the Telegram card into view (scroll)
    card = page.locator('[data-testid="telegram-card"]')
    if card.count() > 0:
        card.scroll_into_view_if_needed()
        page.wait_for_timeout(400)
    page.screenshot(path=str(OUT / "mobile_390_telegram_card.png"))
    print("telegram-card present:", card.count() > 0)
    ctx.close()

    # Desktop control screenshot
    ctx2 = browser.new_context(viewport={"width": 1440, "height": 900})
    page2 = ctx2.new_page()
    page2.goto(f"{BASE}/#/chat", wait_until="networkidle")
    page2.wait_for_timeout(1000)
    page2.evaluate("window.dispatchEvent(new CustomEvent('ephe:open-settings'))")
    page2.wait_for_timeout(600)
    page2.get_by_text("Mobile", exact=True).first.click()
    page2.wait_for_timeout(1200)
    card2 = page2.locator('[data-testid="telegram-card"]')
    card2.scroll_into_view_if_needed()
    page2.screenshot(path=str(OUT / "desktop_telegram_card.png"))
    print("desktop telegram-card present:", card2.count() > 0)
    ctx2.close()
    browser.close()
print("saved to", OUT)
