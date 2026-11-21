import { test, expect } from '@playwright/test'
import { ensureOnboarded, gotoHash, hasDevHandle } from './helpers'

/**
 * Round 12: long-session benchmark — 120 messages in ONE session
 * (seeded through the DEV store handle, no real LLM turns). Checks:
 *  1. Virtualization: the rendered bubbles stay bounded in number
 *  2. Interaction performance: frame time while scrolling stays measurably smooth
 *  3. Persistence: reload restores all 120 messages from IndexedDB
 */
test.describe('Langsession-Benchmark (Runde 12)', () => {
  test('120 Nachrichten: Virtualisierung, Scroll-Performance, Persistenz', async ({ page }) => {
    test.setTimeout(120_000)
    await ensureOnboarded(page)
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    // The handle is defined by src/store/chatStore.ts under `import.meta.env.DEV`, so it
    // exists on the page this lane serves (a Vite dev server) and not in the built bundle
    // the static-dist leg serves. Ask after the navigation: on about:blank the answer is
    // false on every lane, which made the guard a permanent skip.
    test.skip(!(await hasDevHandle(page)), 'needs vite dev server (DEV-only __epheStore handle)')

    // Create a session + seed 120 messages
    const seeded = await page.evaluate(() => {
      const store = (
        window as unknown as {
          __epheStore?: {
            getState: () => {
              createSession: (title?: string) => void
              addMessage: (role: 'user' | 'assistant', content: string) => void
              currentSession: { id: string; messages: unknown[] } | null
            }
          }
        }
      ).__epheStore
      if (!store) return { ok: false }
      const s = store.getState()
      s.createSession('Langsession-Benchmark')
      for (let i = 1; i <= 60; i++) {
        s.addMessage('user', `Frage ${i}: Erkläre Aspekt ${i} des Themas etwas ausführlicher.`)
        s.addMessage(
          'assistant',
          `Antwort ${i}:\n\nDas ist eine ausführliche Antwort mit mehreren Sätzen, damit jede Bubble realistische Höhe hat.\n\n- Punkt eins zu Aspekt ${i}\n- Punkt zwei mit etwas mehr Text\n- Punkt drei als Abschluss der Antwort.`,
        )
      }
      return { ok: true, count: store.getState().currentSession?.messages.length ?? 0 }
    })
    expect(seeded.ok).toBe(true)
    expect((seeded as { count: number }).count).toBe(120)
    await page.waitForTimeout(600)

    // 1) Virtualization: NOT all 120 bubbles are in the DOM
    const renderedBubbles = await page.evaluate(
      () =>
        document.querySelectorAll('[data-testid="panel-chat"] [data-testid="message-row"]').length,
    )
    expect(renderedBubbles).toBeGreaterThan(0)
    expect(renderedBubbles).toBeLessThan(120)

    // 2) Main-thread blocking while scrolling (long tasks ≥50ms).
    //    NOTE: rAF gaps are not a valid metric under headless (frame scheduling
    //    throttles there to ~800ms even when idle — measured independently of the app). Long
    //    tasks measure real main-thread blocking.
    const perf = await page.evaluate(async () => {
      const scroller = document.querySelector('[data-testid="panel-chat"]')
      if (!scroller) return { longTasks: [999], totalBlockingMs: 9999 }
      const durations: number[] = []
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) durations.push(entry.duration)
      })
      observer.observe({ entryTypes: ['longtask'] })
      scroller.scrollTop = 0
      await new Promise((r) => requestAnimationFrame(r))
      for (let i = 0; i < 40; i++) {
        scroller.scrollTop += 600
        await new Promise((r) => requestAnimationFrame(r))
      }
      observer.disconnect()
      // count only blocking beyond the 50ms threshold (long-task definition)
      const blocking = durations.reduce((acc, d) => acc + Math.max(0, d - 50), 0)
      return {
        longTasks: durations.map((d) => Math.round(d)),
        totalBlockingMs: Math.round(blocking),
      }
    })
    console.log(
      `[langsession] Long-Task-Maximum ${perf.longTasks.length ? Math.max(...perf.longTasks) : 0}ms, Blockierung gesamt ${perf.totalBlockingMs}ms (40 Scroll-Schritte, 120 Nachrichten)`,
    )
    expect(Math.max(...perf.longTasks)).toBeLessThan(300)
    expect(perf.totalBlockingMs).toBeLessThan(3000)

    // 3) Persistence: reload → IndexedDB restores the session again
    // Let the debounced IndexedDB save settle before the reload test
    await page.waitForTimeout(1500)
    await page.reload()
    await gotoHash(page, '/chat', '[data-testid="panel-chat"]')
    // initFromDb is async (IndexedDB) — poll instead of using a fixed wait time
    await expect
      .poll(
        async () =>
          page.evaluate(() => {
            const store = (
              window as unknown as {
                __epheStore?: {
                  getState: () => {
                    currentSession: { messages: unknown[] } | null
                  }
                }
              }
            ).__epheStore
            return store?.getState().currentSession?.messages.length ?? 0
          }),
        { timeout: 15_000, interval: 500 },
      )
      .toBe(120)
    const restored = await page.evaluate(() => {
      const store = (
        window as unknown as {
          __epheStore?: {
            getState: () => {
              currentSession: { messages: unknown[] } | null
            }
          }
        }
      ).__epheStore
      return store?.getState().currentSession?.messages.length ?? 0
    })
    console.log(`[langsession] Persistenz nach Reload: ${restored}/120 Nachrichten`)
  })
})
