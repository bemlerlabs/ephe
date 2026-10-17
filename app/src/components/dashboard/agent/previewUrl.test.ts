/**
 * P6 B5: one URL pane — scheme-less inputs get their protocol
 * (the preview tab's address bar, panel-load). Migrated from the
 * tabsBrowser test (component absorbed by the dedup).
 */
import { describe, it, expect } from 'vitest'
import { normalizeBrowserUrl } from './previewUrl'

describe('normalizeBrowserUrl', () => {
  it('ergaenzt https:// fuer scheme-freie Hosts', () => {
    expect(normalizeBrowserUrl('example.com')).toBe('https://example.com')
    expect(normalizeBrowserUrl('example.com/docs?q=1')).toBe('https://example.com/docs?q=1')
  })
  it('laesst http(s)-URLs unveraendert', () => {
    expect(normalizeBrowserUrl('https://example.com')).toBe('https://example.com')
    expect(normalizeBrowserUrl('http://example.com/a')).toBe('http://example.com/a')
  })
  it('Loopback/localhost bekommt http (kein Zertifikat-Fehler)', () => {
    expect(normalizeBrowserUrl('localhost:5173')).toBe('http://localhost:5173')
    expect(normalizeBrowserUrl('127.0.0.1:8765/api')).toBe('http://127.0.0.1:8765/api')
  })
  it('Leereingabe bleibt leer', () => {
    expect(normalizeBrowserUrl('   ')).toBe('')
  })
})
