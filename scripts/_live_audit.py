from playwright.sync_api import sync_playwright
import json, time
OUT = "/work/ephe/.audit"

GEO_JS = """() => {const d=document.querySelector('[data-testid="settings-panel"]');if(!d)return 'closed';const r=d.getBoundingClientRect();return r.width>1?('open w='+Math.round(r.width)+' x='+Math.round(r.x)):'collapsed';}"""

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)

    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.goto("http://127.0.0.1:8765", wait_until="networkidle"); time.sleep(0.6)
    pg.evaluate("""()=>{const b=[...document.querySelectorAll('button')].find(x=>/settings/i.test(x.getAttribute('aria-label')||x.textContent||''));b&&b.click();}""")
    time.sleep(0.5)
    print("POPUP_OPEN:", pg.evaluate(GEO_JS))

    cats = pg.evaluate("""()=>{const d=document.querySelector('[data-testid="settings-panel"]');return [...d.querySelectorAll('button')].map(b=>b.textContent.trim()).filter(Boolean);}""")
    print("NAV_BTNS:", json.dumps(cats[:14], ensure_ascii=False))

    for name in ["Persona","Privacy","About","Mobile"]:
        pg.evaluate("() => {const d=document.querySelector('[data-testid=\"settings-panel\"]');const bs=[...d.querySelectorAll('button')];const b=bs.find(x=>x.textContent.trim().startsWith('%s'));if(b)b.click();}" % name)
        time.sleep(0.3)
        body = pg.evaluate("""()=>{const d=document.querySelector('[data-testid="settings-panel"]');const c=d.querySelector('div[class*="overflow-y-auto"],div[style*="overflow"]');return c?c.innerText.slice(0,220):null;}""")
        print("CAT[%s]:" % name, json.dumps(body, ensure_ascii=False))

    pg.keyboard.press("Escape"); time.sleep(1.2)
    print("AFTER_ESC:", pg.evaluate(GEO_JS))

    # Backdrop-Klick schliesst?
    pg.evaluate("""()=>{const b=[...document.querySelectorAll('button')].find(x=>/settings/i.test(x.getAttribute('aria-label')||x.textContent||''));b&&b.click();}""")
    time.sleep(0.4)
    pg.mouse.click(5,5); time.sleep(1.1)
    print("AFTER_BACKDROP_CLICK:", pg.evaluate(GEO_JS))

    # Mobile Viewport
    m = b.new_page(viewport={"width": 390, "height": 780})
    m.goto("http://127.0.0.1:8765", wait_until="networkidle"); time.sleep(0.6)
    m.screenshot(path=f"{OUT}/03_mobile.png")
    m.evaluate("""()=>{const b=[...document.querySelectorAll('button')].find(x=>/settings/i.test(x.getAttribute('aria-label')||x.textContent||''));b&&b.click();}""")
    time.sleep(0.5)
    mg = m.evaluate("""()=>{const d=document.querySelector('[data-testid="settings-panel"]');if(!d)return null;const r=d.getBoundingClientRect();return{x:Math.round(r.x),w:Math.round(r.width),vw:innerWidth};}""")
    print("MOBILE_GEO:", json.dumps(mg))
    m.screenshot(path=f"{OUT}/04_mobile_settings.png")

    b.close()
