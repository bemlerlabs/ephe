/**
 * P6 B5: one URL pane — scheme-less inputs get their protocol
 * (the preview tab's address bar, panel-load). Migrated from the
 * tabsBrowser test (component absorbed by the dedup).
 */
import { describe, it, expect } from 'vitest'
import { normalizeBrowserUrl, paneMode } from './previewUrl'

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

describe('paneMode', () => {
  it('names a workspace file as the document it is', () => {
    expect(paneMode('/api/file?path=%2Ftmp%2Fbericht.pdf')).toBe('document')
    expect(paneMode('/api/file?path=/srv/app/README.md')).toBe('document')
  })

  it("names this machine's own server as a site", () => {
    for (const url of [
      'http://localhost:5173/',
      'http://127.0.0.1:3000/app',
      'http://[::1]:8080',
    ]) {
      expect(paneMode(url)).toBe('site')
    }
  })

  it('names everything else a page on the web', () => {
    expect(paneMode('https://example.com/page')).toBe('web')
    // an empty pane is a place to type an address, not a document with no name
    expect(paneMode('')).toBe('web')
    expect(paneMode('   ')).toBe('web')
  })

  it('does not read a file endpoint on another host as a document', () => {
    expect(paneMode('https://example.com/api/file?path=%2Fa.pdf')).toBe('web')
  })
})
