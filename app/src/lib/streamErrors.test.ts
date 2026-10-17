import { describe, it, expect } from 'vitest'
import { humanizeStreamError } from '@/lib/streamErrors'
import { StreamChatError } from '@/lib/stream'

const t = (key: string, opts?: Record<string, unknown>) =>
  opts ? `${key}:${JSON.stringify(opts)}` : key

describe('humanizeStreamError — DD-15', () => {
  it('netzwerkartiger TypeError (fetch fehlgeschlagen) -> freundlicher Offline-Hinweis, kein Roh-String', () => {
    for (const raw of [
      'Failed to fetch',
      'Load failed',
      'NetworkError when trying to fetch resource',
    ]) {
      const out = humanizeStreamError(new TypeError(raw), t)
      expect(out).toBe('chat.offlineStreamError')
      expect(out).not.toContain('TypeError')
    }
  })

  it('echter Stream-Fehler mit Botschaft bleibt sichtbar (message interpoliert)', () => {
    const err = new StreamChatError('HTTP 500 vom Backend', 500)
    const out = humanizeStreamError(err, t)
    expect(out).toMatch(/^chat\.streamError:/)
    expect(out).toContain('HTTP 500')
  })

  it('leere/unklare Fehlerobjekte werden nie als rohes [object Object] ausgeliefert', () => {
    const out = humanizeStreamError({} as unknown, t)
    expect(out).toMatch(/^chat\.streamError:/)
    expect(out).not.toContain('[object Object]')
  })
})
