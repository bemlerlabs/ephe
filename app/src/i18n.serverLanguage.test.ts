/**
 * QA-E2E F2: the desktop window and the PWA of the same installation showed two
 * languages. `i18n.ts` booted from localStorage/navigator only, so the Tauri
 * origin (no detector cache) read English while the server said `language: de`.
 * The entry now applies the saved language before the first render.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { i18n as I18n } from 'i18next'

async function boot(settings: () => Promise<Response>): Promise<I18n> {
  vi.resetModules()
  localStorage.clear()
  vi.stubGlobal('fetch', vi.fn(settings))
  const module = await import('./i18n')
  await module.applyServerLanguage()
  return module.default
}

function settingsAnswer(body: unknown, status = 200): () => Promise<Response> {
  return async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { 'content-type': 'application/json' },
    })
}

describe('the boot language follows the saved product setting (F2)', () => {
  afterEach(async () => {
    vi.unstubAllGlobals()
    localStorage.clear()
    vi.resetModules()
  })

  it('reads language=de from /api/settings and paints German on first load', async () => {
    const instance = await boot(settingsAnswer({ language: 'de' }))

    expect(instance.language).toBe('de')
    expect(instance.t('workspaces.title')).toBe('Arbeitsbereiche')
    await instance.changeLanguage('en')
  })

  it('asks the settings route exactly once, at the entry', async () => {
    const instance = await boot(settingsAnswer({ language: 'de' }))
    const fetchMock = vi.mocked(fetch)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(/\/api\/settings$/)
    await instance.changeLanguage('en')
  })

  it('does not read settings when a component only imports i18n', async () => {
    vi.resetModules()
    localStorage.clear()
    const fetchMock = vi.fn(settingsAnswer({ language: 'de' }))
    vi.stubGlobal('fetch', fetchMock)

    await import('./i18n')

    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('lets the product setting outrank a stale client cache', async () => {
    vi.resetModules()
    localStorage.setItem('i18nextLng', 'en')
    vi.stubGlobal('fetch', vi.fn(settingsAnswer({ language: 'de' })))

    const module = await import('./i18n')
    await module.applyServerLanguage()

    expect(module.default.language).toBe('de')
    await module.default.changeLanguage('en')
  })

  it('keeps the stored choice when the backend does not answer', async () => {
    vi.resetModules()
    localStorage.setItem('i18nextLng', 'de')
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new Error('offline')
      }),
    )

    const module = await import('./i18n')
    await module.applyServerLanguage()

    expect(module.default.language).toBe('de')
    await module.default.changeLanguage('en')
  })

  it('falls back to the browser language when the settings answer is not a language', async () => {
    const instance = await boot(settingsAnswer({ language: 'fr' }))

    expect(instance.language).toBe('en')
    await instance.changeLanguage('en')
  })
})
