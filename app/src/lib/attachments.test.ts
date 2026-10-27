/**
 * G3 — attachment handling (browser PWA, no Tauri requirement)
 *
 * GIVEN  File objects coming from an <input type="file">
 * WHEN   images or text files get attached
 * THEN   images are read as a base64 data URL (for the images parameter)
 * AND    text files are read as content (cap 64 KB, above that a size hint)
 * AND    compositePayload appends the text contents as a code block + paths
 * AND    compositeImages returns only image data URLs (plain base64 without
 *        prefix handling — the consumer takes that over)
 */
import { describe, it, expect } from 'vitest'
import {
  readImageAsDataUrl,
  readTextAttachment,
  MAX_TEXT_ATTACHMENT_BYTES,
  isImageFile,
  compositePayload,
  compositeImages,
  type ChatAttachment,
} from './attachments'

function file(name: string, type: string, content = 'x'): File {
  return new File([content], name, { type })
}

describe('attachments (G3)', () => {
  it('isImageFile erkennt image/*', () => {
    expect(isImageFile(file('a.png', 'image/png'))).toBe(true)
    expect(isImageFile(file('a.txt', 'text/plain'))).toBe(false)
    expect(isImageFile(file('a.bin', 'application/octet-stream'))).toBe(false)
  })

  it('readImageAsDataUrl liefert eine data:-URL', async () => {
    const url = await readImageAsDataUrl(file('a.png', 'image/png', 'img'))
    expect(url.startsWith('data:image/png;base64,')).toBe(true)
  })

  it('readTextAttachment liest Text + Capability Cap bei >64 KB', async () => {
    const small = await readTextAttachment(file('a.md', 'text/markdown', '# Hallo'))
    expect(small.text).toBe('# Hallo')
    expect(small.truncated).toBe(false)

    const big = 'a'.repeat(MAX_TEXT_ATTACHMENT_BYTES + 100)
    const capped = await readTextAttachment(file('big.log', 'text/plain', big))
    expect(capped.truncated).toBe(true)
    expect(capped.text.length).toBeLessThanOrEqual(MAX_TEXT_ATTACHMENT_BYTES)
  })

  it('compositePayload: Nachricht + Textinhalt als Codeblock + Pfad-/Bild-Hinweis', () => {
    const atts: ChatAttachment[] = [
      { kind: 'text', path: '/tmp/a.md', name: 'a.md', text: '# Hallo', truncated: false },
      { kind: 'image', path: '/tmp/b.png', name: 'b.png', dataUrl: 'data:image/png;base64,QQ==' },
    ]
    const payload = compositePayload('Sieh dir das an', atts)
    expect(payload.startsWith('Sieh dir das an')).toBe(true)
    expect(payload).toContain('```markdown')
    expect(payload).toContain('# Hallo')
    expect(payload).toContain('/tmp/b.png')
    // image data URLs do NOT go into the text payload (they go to the images parameter)
    expect(payload).not.toContain('base64')
  })

  it('compositeImages: nur Bild-Attachments als reine Base64-Werte', () => {
    const atts: ChatAttachment[] = [
      { kind: 'image', path: '/b.png', name: 'b.png', dataUrl: 'data:image/png;base64,QQ==' },
      { kind: 'text', path: '/a.md', name: 'a.md', text: 'x', truncated: false },
    ]
    expect(compositeImages(atts)).toEqual(['QQ=='])
    expect(compositeImages([])).toEqual([])
  })
})

describe('compositePayload names a file once', () => {
  it('drops the path when it repeats the name', () => {
    const atts: ChatAttachment[] = [
      { kind: 'file', path: 'photo.jpg', name: 'photo.jpg', size: 3, status: 'ready' },
    ]
    const payload = compositePayload('x', atts)
    expect(payload).toContain('[Anhang: photo.jpg]')
    expect(payload).not.toContain('photo.jpg — photo.jpg')
  })

  it('keeps the path when it adds information', () => {
    const atts: ChatAttachment[] = [
      { kind: 'file', path: '/tmp/b.png', name: 'b.png', size: 3, status: 'ready' },
    ]
    expect(compositePayload('x', atts)).toContain('[Anhang: b.png — /tmp/b.png]')
  })
})
