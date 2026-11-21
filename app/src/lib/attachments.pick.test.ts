import { describe, expect, it } from 'vitest'
import { attachmentFromPick } from './attachments'

describe('attachmentFromPick', () => {
  it('turns a picked image into the thumbnail shape', () => {
    const attachment = attachmentFromPick({
      name: 'shot.png',
      size: 4096,
      kind: 'image',
      dataUrl: 'data:image/png;base64,iVBORw==',
    })
    expect(attachment).toEqual({
      path: 'shot.png',
      name: 'shot.png',
      size: 4096,
      status: 'ready',
      kind: 'image',
      dataUrl: 'data:image/png;base64,iVBORw==',
    })
  })

  it('keeps a capped text file together with its flag', () => {
    const attachment = attachmentFromPick({
      name: 'notes.md',
      size: 70000,
      kind: 'text',
      text: 'a',
      truncated: true,
    })
    expect(attachment.kind).toBe('text')
    if (attachment.kind === 'text') {
      expect(attachment.text).toBe('a')
      expect(attachment.truncated).toBe(true)
    }
  })

  it('passes a plain file through with its name and size', () => {
    const attachment = attachmentFromPick({ name: 'report.pdf', size: 900, kind: 'file' })
    expect(attachment).toEqual({
      path: 'report.pdf',
      name: 'report.pdf',
      size: 900,
      status: 'ready',
      kind: 'file',
    })
  })

  it('carries the name where a path used to be, so no local path reaches the prompt', () => {
    const attachment = attachmentFromPick({
      name: 'shot.png',
      size: 1,
      kind: 'image',
      dataUrl: 'data:image/png;base64,AA==',
    })
    expect(attachment.path).toBe('shot.png')
    expect(JSON.stringify(attachment)).not.toContain('/Users/')
  })
})
