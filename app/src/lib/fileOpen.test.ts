/**
 * #111 — one opener for every file the workspace column holds.
 *
 * The defect this replaces was measured, not imagined: the Files tab could answer for
 * Markdown, code and plain text and nothing else, so a click on a PNG left the column and
 * opened the browser pane with an address bar. The artifact card beside it already had an
 * answer for images, PDF, audio, video, spreadsheets and decks. These cases pin that both
 * surfaces now answer the same question about the same name — and that every branch says
 * something, including the one that can only say "not here".
 */
import { describe, it, expect } from 'vitest'
import { fileOpenPlan, withFileView, fileIsText } from './fileOpen'
import { artifactPreviewMode } from './previewMode'

describe('fileOpenPlan — the format families', () => {
  it('reads Markdown as a page and offers the source beside it', () => {
    const plan = fileOpenPlan('README.md')
    expect(plan.kind).toBe('markdown')
    if (plan.kind === 'markdown') {
      expect(plan.view).toBe('rendered')
      expect(plan.views).toEqual(['rendered', 'source'])
    }
  })

  it('names the highlight language for source the way the card does', () => {
    expect(fileOpenPlan('panel.tsx')).toEqual({ kind: 'code', language: 'tsx' })
    expect(fileOpenPlan('run.py')).toEqual({ kind: 'code', language: 'python' })
    expect(fileOpenPlan('Cargo.toml')).toEqual({ kind: 'code', language: 'toml' })
    expect(fileOpenPlan('settings.json')).toEqual({ kind: 'code', language: 'json' })
  })

  it('keeps the words that have no grammar as words', () => {
    expect(fileOpenPlan('run.log')).toEqual({ kind: 'text' })
    expect(fileOpenPlan('export.csv')).toEqual({ kind: 'text' })
    // The suffix that used to be unknown in the reader and content on the card.
    expect(fileOpenPlan('table.tsv')).toEqual({ kind: 'text' })
    expect(fileOpenPlan('uv.lock')).toEqual({ kind: 'text' })
  })

  it('hands the formats a viewer draws to the viewer', () => {
    for (const name of ['karte.png', 'foto.jpg', 'rolle.webp', 'marke.svg']) {
      expect(fileOpenPlan(name).kind).toBe('image')
    }
    expect(fileOpenPlan('stimme.mp3').kind).toBe('audio')
    expect(fileOpenPlan('clip.mp4').kind).toBe('video')
    expect(fileOpenPlan('bericht.pdf').kind).toBe('frame')
    expect(fileOpenPlan('seite.html').kind).toBe('frame')
  })

  it('calls the office containers by what they are', () => {
    expect(fileOpenPlan('zahlen.xlsx')).toEqual({ kind: 'packed', format: 'table' })
    expect(fileOpenPlan('brief.docx')).toEqual({ kind: 'packed', format: 'document' })
    expect(fileOpenPlan('folien.pptx')).toEqual({ kind: 'packed', format: 'deck' })
  })

  it('answers for a file it cannot draw instead of answering nothing', () => {
    expect(fileOpenPlan('archiv.zip')).toEqual({ kind: 'binary' })
    expect(fileOpenPlan('no_extension')).toEqual({ kind: 'binary' })
  })

  it('takes the producing kind when a name carries no extension', () => {
    expect(fileOpenPlan('ephe_chart', 'chart').kind).toBe('image')
    expect(fileOpenPlan('no_dot', 'py')).toEqual({ kind: 'code', language: 'python' })
  })
})

describe('the two surfaces agree about one name', () => {
  // The card decides 'content' for anything the server can read back; the column decides
  // what it can draw from the bytes itself. The sets below are where those two questions
  // must not disagree about whether a file is a picture, a page, a sound or a moving image.
  const MEDIA: Record<string, 'image' | 'frame' | 'audio' | 'video'> = {
    'a.png': 'image',
    'a.svg': 'image',
    'a.pdf': 'frame',
    'a.html': 'frame',
    'a.mp3': 'audio',
    'a.mp4': 'video',
  }

  it.each(Object.entries(MEDIA))('%s reaches both surfaces as %s', (name, want) => {
    expect(artifactPreviewMode(name)).toBe(want)
    expect(fileOpenPlan(name).kind).toBe(want)
  })

  it('never leaves a name the card can show as nothing for the column', () => {
    for (const name of ['a.md', 'a.txt', 'a.ts', 'a.py', 'a.json']) {
      expect(artifactPreviewMode(name)).not.toBe('none')
      expect(['markdown', 'code', 'text']).toContain(fileOpenPlan(name).kind)
    }
  })
})

describe('withFileView — the choice stays inside what the file can show', () => {
  it('moves a Markdown file between the page and its source', () => {
    const plan = fileOpenPlan('README.md')
    if (plan.kind !== 'markdown') throw new Error('README should read as Markdown')
    const moved = withFileView(plan, 'source')
    const back = withFileView(plan, 'rendered')
    expect(moved.kind === 'markdown' && moved.view).toBe('source')
    expect(back.kind === 'markdown' && back.view).toBe('rendered')
    expect(moved).toEqual({ ...plan, view: 'source' })
  })

  it('holds the page view when nothing asks for another', () => {
    const rendered = (view: 'rendered' | 'source' | null | undefined) => {
      const plan = withFileView(fileOpenPlan('README.md'), view)
      return plan.kind === 'markdown' ? plan.view : null
    }
    expect(rendered(undefined)).toBe('rendered')
    expect(rendered(null)).toBe('rendered')
    expect(rendered('rendered')).toBe('rendered')
    expect(rendered('source')).toBe('source')
  })

  it('leaves a file with one view alone, whatever it is asked for', () => {
    const code = fileOpenPlan('panel.tsx')
    expect(withFileView(code, 'rendered')).toBe(code)
    expect(fileIsText(code)).toBe(true)
    expect(fileIsText(fileOpenPlan('karte.png'))).toBe(false)
    expect(fileIsText(fileOpenPlan('zahlen.xlsx'))).toBe(false)
    expect(fileIsText(fileOpenPlan('run.log'))).toBe(true)
  })
})
