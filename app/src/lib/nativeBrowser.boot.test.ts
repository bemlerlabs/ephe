/**
 * Boot guard: the browser pane is a child WebView of the desktop window, not a
 * node of the page — it paints above the app and survives a reload of it
 * (`browser.rs` hides it only from the page life that opened it). A reload while
 * the pane was showing a foreign page left that page floating over the chat with
 * no panel around it. The entry must therefore ask the shell once per load to
 * close a pane it did not create.
 *
 * GIVEN  the desktop shell with its bridge (window.__TAURI__)
 * WHEN   a page load runs the boot guard
 * THEN   it hands `browser_close` to the shell exactly once and never lets a
 *        refusal surface as an unhandled rejection; in the PWA (no bridge) it is
 *        a no-op.
 * AND    main.tsx actually calls it before the React mount — the guard is worth
 *        nothing if the entry does not run it (the source read below is the
 *        wiring assertion).
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { closeOrphanedBrowserPane } from './nativeBrowser'

type Shell = { __TAURI__?: { core: { invoke: (cmd: string, args?: unknown) => Promise<unknown> } } }

function installShell(invoke: (cmd: string, args?: unknown) => Promise<unknown>) {
  ;(window as unknown as Shell).__TAURI__ = { core: { invoke } }
}

afterEach(() => {
  delete (window as unknown as Shell).__TAURI__
})

describe('closeOrphanedBrowserPane', () => {
  it('asks the shell to close a pane left behind by the previous page life', () => {
    const invoke = vi.fn<(cmd: string, args?: unknown) => Promise<unknown>>(async () => null)
    installShell(invoke)
    closeOrphanedBrowserPane()
    expect(invoke).toHaveBeenCalledTimes(1)
    expect(invoke.mock.calls[0]?.[0]).toBe('browser_close')
  })

  it('is a no-op in the PWA, where no shell bridge exists', () => {
    expect(() => closeOrphanedBrowserPane()).not.toThrow()
  })

  it('swallows a shell refusal instead of starting with an unhandled rejection', async () => {
    installShell(async () => {
      throw new Error('no pane to close')
    })
    expect(() => closeOrphanedBrowserPane()).not.toThrow()
    // Let the rejected promise settle: an unhandled rejection would fail the run.
    await Promise.resolve()
    await Promise.resolve()
  })

  it('is wired into the entry before the React mount, so every page load runs it', () => {
    const main = readFileSync('src/main.tsx', 'utf8')
    const call = main.indexOf('closeOrphanedBrowserPane()')
    const mount = main.indexOf('createRoot(')
    expect(call).toBeGreaterThan(-1)
    expect(mount).toBeGreaterThan(-1)
    expect(call).toBeLessThan(mount)
  })
})
