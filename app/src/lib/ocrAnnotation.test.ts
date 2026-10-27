import { describe, expect, it } from 'vitest'
import { annotateWithOcr } from './ocrAnnotation'
import type { ChatAttachment } from './attachments'

const image = (over: Partial<ChatAttachment> = {}): ChatAttachment =>
  ({
    kind: 'image',
    path: '/tmp/a.png',
    name: 'error.png',
    dataUrl: 'data:image/png;base64,AA==',
    ...over,
  }) as ChatAttachment

describe('N7 — OCR text travels with its turn', () => {
  it('leaves a message without text-bearing images untouched', () => {
    expect(annotateWithOcr('hello', undefined)).toBe('hello')
    expect(annotateWithOcr('hello', [])).toBe('hello')
    expect(annotateWithOcr('hello', [image()])).toBe('hello')
  })

  it('appends the extracted text with the file name beside it', () => {
    const out = annotateWithOcr('what is this?', [image({ ocrText: 'Traceback: KeyError' })])
    expect(out).toBe('what is this?\n\n[Text from image error.png:\nTraceback: KeyError]')
  })

  it('keeps every image that carried text, in order', () => {
    const out = annotateWithOcr('x', [
      image({ name: 'a.png', ocrText: 'first' }),
      image({ name: 'b.png' }),
      image({ name: 'c.png', ocrText: 'second' }),
    ])
    expect(out).toContain('[Text from image a.png:\nfirst]')
    expect(out).toContain('[Text from image c.png:\nsecond]')
    expect(out.indexOf('a.png')).toBeLessThan(out.indexOf('c.png'))
  })
})
