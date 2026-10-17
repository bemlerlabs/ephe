"""W10 visual check — portal pop-up (artifacts), two-row header, interleaving cadence.

Backend 8765 + Vite 5173. Desktop 1280x900, Mobile 390x844.
Fresh PNG names per pass (judge cache trap).
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5173/#/chat"
OUT = Path("docs/media/w10_2026-09-09")
OUT.mkdir(parents=True, exist_ok=True)

INIT_JS = "() => { localStorage.setItem('i18nextLng', 'de') }"

SEED_JS = """() => {
  const s = window.__epheStore.getState()
  const id = s.activeSessionId
  const msgs = [
    { id: 'u1', role: 'user', content: 'Erklaer mir die Architektur', timestamp: Date.now() },
    { id: 'a1', role: 'assistant', content: 'Die Architektur ist dreischichtig.', timestamp: Date.now(),
      thinking: { start: Date.now() - 2400, end: Date.now() - 1200, text: 'Ich lese zuerst das Manifest.' },
      thinkingPhases: [
        { start: Date.now() - 2400, end: Date.now() - 1200, text: 'Ich lese zuerst das Manifest.' },
        { start: Date.now() - 1100, end: Date.now() - 300, text: 'Danach traegt die Diff-Zeile das Ergebnis.' }
      ],
      tool_calls: [
        { id: 't1', name: 'read_file', args: { path: 'manifest.json' }, result: '{...}', status: 'completed', duration_ms: 120 },
        { id: 't2', name: 'run_shell', args: { command: 'rg -n "no_split" core' }, result: 'core/chat.py:41', status: 'completed', duration_ms: 80 },
        { id: 't3', name: 'spawn_swarm', args: { count: 2, role: 'general-purpose', subtasks: ['P2-Layout + P4-Doku'] }, result: 'fertig', status: 'completed', duration_ms: 900 }
      ],
      blocks: [
        { kind: 'thinking', index: 0 },
        { kind: 'tool', callId: 't1' },
        { kind: 'tool', callId: 't2' },
        { kind: 'thinking', index: 1 },
        { kind: 'tool', callId: 't3' },
        { kind: 'text', text: 'Die Architektur ist dreischichtig.' }
      ],
      activities: [{ id: 'ac1', label: 'manifest.json', status: 'done', path: '/tmp/konzept.html', fileType: 'html' }] }
  ]
  window.__epheStore.setState((st) => ({
    sessions: st.sessions.map((x) => (x.id === id ? { ...x, messages: msgs } : x)),
    currentSession: { ...st.currentSession, messages: msgs },
  }))
}"""

RECTS_JS = """() => { const out = {}; for (const t of ['toolbar-row','toolbar-meta','status-bar','artifact-modal','tool-stream-rows','side-panel-toggle']) {
  const el = document.querySelector(`[data-testid="${t}"]`); if (el) { const b = el.getBoundingClientRect(); out[t] = [b.x,b.y,b.width,b.height].map(Math.round) } } return out }"""


def boot(page) -> None:
    page.goto(BASE, wait_until="networkidle")
    page.evaluate("() => { localStorage.setItem('i18nextLng', 'de') }")
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(1200)


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # 1) Desktop: header/toolbar/status + the interleaving cadence in the stream
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.add_init_script(INIT_JS)
        boot(page)
        page.evaluate(SEED_JS)
        page.wait_for_timeout(700)
        page.screenshot(path=str(OUT / "w10_01_desktop_strom.png"))
        print("desktop rects:", page.evaluate(RECTS_JS))

        # 2) artifact pop-up (portal) at nearly main-window size
        page.get_by_test_id("artifact-library-toggle").click()
        page.wait_for_timeout(900)
        page.screenshot(path=str(OUT / "w10_02_artefakt_popup.png"))
        print("popup rects:", page.evaluate(RECTS_JS))
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "w10_03_nach_esc.png"))

        # 3) Subagents tab in the side panel
        page.get_by_test_id("side-panel-toggle").click()
        page.wait_for_timeout(500)
        page.evaluate(
            "() => { window.dispatchEvent(new CustomEvent('ephe:preview-open',"
            " { detail: { tab: 'subagents' } })) }"
        )
        page.wait_for_timeout(700)
        page.screenshot(path=str(OUT / "w10_04_subagenten_tab.png"))
        page.close()

        # 4) Mobile 390x844 — two rows + the slim pill bar
        mob = browser.new_page(viewport={"width": 390, "height": 844})
        mob.add_init_script(INIT_JS)
        boot(mob)
        mob.evaluate(SEED_JS)
        mob.wait_for_timeout(700)
        mob.screenshot(path=str(OUT / "w10_05_mobile.png"))
        print("mobile rects:", mob.evaluate(RECTS_JS))
        mob.close()

        browser.close()
        print("screenshots in", OUT)


if __name__ == "__main__":
    main()
