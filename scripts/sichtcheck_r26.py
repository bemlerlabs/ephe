"""R26 visual check — redesigned shell (desktop 1440x900 + mobile 390x844).

Read-only: loads the chat page, screenshots the redesigned sidebar/topbar/
toolbar/welcome cards, opens the workspace picker dialog (no pick), and
screenshots the mobile drawer. Never clicks create/delete actions.
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
OUT = Path("docs/media/r26_shell_sichtcheck")
OUT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Desktop
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(f"{BASE}/#/chat", wait_until="networkidle")
        page.wait_for_timeout(4000)
        page.screenshot(path=str(OUT / "desktop_welcome.png"), full_page=False)

        # Retina sharpness probe (DPR 2): verifies the background asset is
        # not upscaled/pixelated on 2x displays (user-reported regression).
        page2x = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page2x.goto(f"{BASE}/#/chat", wait_until="networkidle")
        page2x.wait_for_timeout(4000)
        page2x.screenshot(path=str(OUT / "desktop_welcome_retina2x.png"), full_page=False)
        page2x.close()

        # Workspace picker dialog open (core R26 requirement)
        if page.locator('[data-testid="workspace-picker"]').count() > 0:
            page.click('[data-testid="workspace-picker"]')
            page.wait_for_timeout(900)
            page.screenshot(path=str(OUT / "desktop_workspace_picker.png"))
            # close without picking (Escape)
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)

        # Toolbar row present?
        tb = page.locator('[data-testid="toolbar-row"]').count()
        print(f"toolbar-row present: {tb}")

        # Mobile
        mob = browser.new_page(viewport={"width": 390, "height": 844})
        mob.goto(f"{BASE}/#/chat", wait_until="networkidle")
        mob.wait_for_timeout(2500)
        mob.screenshot(path=str(OUT / "mobile_welcome.png"))

        # Open the mobile sidebar drawer via the menu button
        menu_btn = mob.get_by_role("button", name="Menu")
        if menu_btn.count() > 0:
            menu_btn.first.click()
            mob.wait_for_timeout(900)
            mob.screenshot(path=str(OUT / "mobile_sidebar.png"))

        browser.close()
        print(f"screenshots in {OUT}")


if __name__ == "__main__":
    main()
