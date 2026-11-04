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
import { fileOpenPlan, fileViews, withFileView, fileIsText } from './fileOpen'
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

  it('reads a CSV as the server\'s table and keeps its bytes beside it', () => {
    // The card draws a .csv as rows (core/artifact_preview.py TABLE_KINDS); the column now
    // agrees — the table is the rendered view, the source text the second one, exactly as
    // Markdown keeps page and source.
    const plan = fileOpenPlan('daten.csv')
    expect(plan.kind).toBe('table')
    if (plan.kind === 'table') {
      expect(plan.view).toBe('rendered')
      expect(plan.views).toEqual(['rendered', 'source'])
    }
    expect(fileViews(plan)).toEqual(['rendered', 'source'])
  })

  it('names the highlight language for source the way the card does', () => {
    expect(fileOpenPlan('panel.tsx')).toEqual({ kind: 'code', language: 'tsx' })
    expect(fileOpenPlan('run.py')).toEqual({ kind: 'code', language: 'python' })
    expect(fileOpenPlan('Cargo.toml')).toEqual({ kind: 'code', language: 'toml' })
    expect(fileOpenPlan('settings.json')).toEqual({ kind: 'code', language: 'json' })
  })

  it('keeps the words that have no grammar as words', () => {
    expect(fileOpenPlan('run.log')).toEqual({ kind: 'text' })
    // `tsv` stays text: the bytes are text, and the server does NOT put it in its own
    // table list (TABLE_KINDS is {xlsx, xls, csv}), so there is no rendered answer to ask
    // for — the column reads it itself, exactly as before.
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
    for (const name of ['a.md', 'a.txt', 'a.ts', 'a.py', 'a.json', 'a.csv']) {
      expect(artifactPreviewMode(name)).not.toBe('none')
      expect(['markdown', 'code', 'text', 'table']).toContain(fileOpenPlan(name).kind)
    }
  })

  it('agrees with the card that a CSV is a table with its bytes beside it', () => {
    // The card asks the server (content); the column now keeps a rendered table view for
    // the same name — the two surfaces no longer disagree for the suffix the server tabulates.
    expect(artifactPreviewMode('daten.csv')).toBe('content')
    expect(fileOpenPlan('daten.csv').kind).toBe('table')
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

  it('moves a CSV between the server\'s table and its own bytes', () => {
    const plan = fileOpenPlan('daten.csv')
    if (plan.kind !== 'table') throw new Error('daten.csv should read as a table')
    const source = withFileView(plan, 'source')
    expect(source.kind === 'table' && source.view).toBe('source')
    // The table view asks the server for rows; the source view reads the bytes, so it is
    // text again and keeps the copy gesture that belongs to text.
    expect(fileIsText(plan)).toBe(false)
    expect(fileIsText(source)).toBe(true)
  })

  it('leaves a file with one view alone, whatever it is asked for', () => {
    const code = fileOpenPlan('panel.tsx')
    expect(withFileView(code, 'rendered')).toBe(code)
    expect(fileIsText(code)).toBe(true)
    expect(fileIsText(fileOpenPlan('karte.png'))).toBe(false)
    expect(fileIsText(fileOpenPlan('zahlen.xlsx'))).toBe(false)
    expect(fileIsText(fileOpenPlan('run.log'))).toBe(true)
    // A suffix the server declines as a table stays single-view text.
    expect(fileViews(fileOpenPlan('table.tsv'))).toEqual([])
  })
})
