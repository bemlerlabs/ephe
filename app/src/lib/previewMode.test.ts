import { describe, it, expect } from 'vitest'
import {
  artifactPreviewMode,
  codePreviewLanguage,
  documentAddress,
  previewSandbox,
  previewShowsInFrame,
  previewSrc,
  resolveFilePreview,
  prettifyUrl,
} from '@/lib/previewMode'

describe('resolveFilePreview — DD-12', () => {
  it('recognizes a markdown file in the file endpoint and decodes the path', () => {
    const r = resolveFilePreview('/api/file?path=%2Ftmp%2Fproj%2FREADME.md')
    expect(r).toEqual({ kind: 'markdown', path: '/tmp/proj/README.md', filename: 'README.md' })
  })

  it('maps code extensions to language and remaining text files to plain', () => {
    expect(resolveFilePreview('/api/file?path=%2Fsrc%2Fapp.tsx')).toEqual({
      kind: 'code',
      path: '/src/app.tsx',
      filename: 'app.tsx',
      language: 'tsx',
    })
    const log = resolveFilePreview('/api/file?path=%2Flogs%2Frun.log')
    expect(log).toEqual({
      kind: 'code',
      path: '/logs/run.log',
      filename: 'run.log',
      language: 'text',
    })
  })

  it('keeps HTML and the unknown at the iframe, side-by-side with no escaping markup', () => {
    expect(resolveFilePreview('/api/file?path=%2Fsite%2Findex.html')).toBeNull()
    expect(resolveFilePreview('http://127.0.0.1:5173/')).toBeNull()
    expect(resolveFilePreview('')).toBeNull()
  })

  it('cannot be talked into a text path by traversals or foreign queries', () => {
    expect(resolveFilePreview('/api/file?path=abc&other=%2Fx.md')).toBeNull()
  })
})

describe('prettifyUrl — DD-12 URL-Chip', () => {
  it('shows only the file name in the file endpoint, never the raw query', () => {
    expect(prettifyUrl('/api/file?path=%2Ftmp%2FREADME.md')).toBe('README.md')
  })
  it('laesst normale URLs unveraendert', () => {
    expect(prettifyUrl('http://localhost:5173/chat')).toBe('http://localhost:5173/chat')
    expect(prettifyUrl('')).toBe('')
  })
})

describe('R4/A5 — artifactPreviewMode', () => {
  it.each([
    ['bericht.pdf', 'pdf', 'frame'],
    ['bild.png', 'png', 'image'],
    ['logo.svg', 'svg', 'image'],
    ['tabelle.xlsx', 'xlsx', 'content'],
    ['dokument.docx', 'docx', 'content'],
    ['notiz.md', 'md', 'content'],
    ['sprache.mp3', 'audio', 'audio'],
    ['clip.mp4', 'mp4', 'video'],
    ['deck.pptx', 'deck', 'content'],
    ['folien.odp', 'odp', 'content'],
    ['irgendwas.bin', 'file', 'none'],
  ] as const)('%s → %s', (name, kind, want) => {
    expect(artifactPreviewMode(name, kind)).toBe(want)
  })

  it('does not trust the extension alone: a kind without a dot is followed', () => {
    expect(artifactPreviewMode('ephe_chart', 'chart')).toBe('image')
    expect(artifactPreviewMode('', 'xlsx')).toBe('content')
  })
})

// A5 edge: `artifactPreviewMode` answered `none` for every source file — a .ts
// card said "no content" although the file endpoint serves the bytes and the
// surface can show them. Code gets its own mode now (A5), and the language table
// behind `fileLanguage`/`resolveFilePreview` stays the single source.
describe('A5 edge — code was none, now its own view', () => {
  it.each([
    ['quelle.ts', 'ts', 'typescript'],
    ['komponente.tsx', 'tsx', 'tsx'],
    ['bundler.mjs', 'mjs', 'javascript'],
    ['skript.py', 'python', 'python'],
    ['main.rs', 'rs', 'rust'],
    ['stil.css', 'css', 'css'],
    ['schema.sql', 'sql', 'sql'],
    ['deploy.sh', 'bash', 'bash'],
  ] as const)('%s -> code (%s)', (name, kind, lang) => {
    expect(artifactPreviewMode(name, kind)).toBe('code')
    expect(codePreviewLanguage(name, kind)).toBe(lang)
  })

  it('keeps json/yaml on the server content path — both tables know them', () => {
    // Both tables carry these; CONTENT_EXT is checked first, so the server
    // extracts the text and the code path stays for the source formats.
    expect(artifactPreviewMode('daten.json', 'json')).toBe('content')
    expect(artifactPreviewMode('karte.yaml', 'yaml')).toBe('content')
    expect(artifactPreviewMode('pyproject.toml', 'toml')).toBe('content')
  })

  it('still calls a non-code file by its own name', () => {
    expect(codePreviewLanguage('bericht.pdf', 'pdf')).toBeNull()
    expect(codePreviewLanguage('irgendwas.bin')).toBeNull()
    expect(artifactPreviewMode('archiv.zip', 'zip')).toBe('none')
  })

  it('reads the language out of the kind when there is no dot, same rule as the mode', () => {
    expect(codePreviewLanguage('quelltext', 'py')).toBe('python')
    expect(codePreviewLanguage('', 'sh')).toBe('bash')
  })
})

// The finding that forced this rule: a PDF card showed a white rectangle. The
// endpoint was innocent — /api/artifacts/<id>/file answered with 200 and
// application/pdf. Measured in real Chrome, three variants of the same frame:
//   allow-popups                   -> sad document
//   allow-popups allow-same-origin -> sad document
//   (no directive)                 -> the page
// The viewer is an extension, and an extension runs in no sandboxed frame — giving
// it its origin back was not enough (the first attempt, refuted here). Isolation
// therefore happens on the response (CSP `sandbox` on the file routes,
// server/middleware.py), and only where scripts are possible.
describe('previewSandbox: one rule, two surfaces', () => {
  it('leaves the directive wholly to the dead format', () => {
    expect(previewSandbox('analyse-2026.pdf')).toBeUndefined()
    expect(previewSandbox('ohneendung', 'pdf')).toBeUndefined()
  })

  // Round 12 stays tight: model-generated markup never got an origin, because
  // otherwise it could read the app session.
  it('keeps HTML, decks and everything else in the dense frame', () => {
    for (const name of ['seite.html', 'deck.htm', 'bericht.docx', 'tabelle.xlsx', 'bild.svg']) {
      const box = previewSandbox(name)
      expect(box).toBe('allow-popups')
      expect(box).not.toContain('allow-same-origin')
      expect(box).not.toContain('allow-scripts')
    }
  })

  it('lets the name decide when both the name and the kind speak', () => {
    // The card is named .html — then it stays isolated markup even when its kind
    // says pdf. The other way round, a name without a dot carries the type.
    expect(previewSandbox('a.html', 'pdf')).toBe('allow-popups')
    expect(previewSandbox('ohnepunkt', 'pdf')).toBeUndefined()
  })
})

describe('previewSrc: what belongs inside the frame', () => {
  // Measured in the image: without parameters the viewer showed a horizontally
  // cut strip of the sheet inside the short preview frame.
  it('fits the PDF to the frame width and drops its toolbar', () => {
    expect(previewSrc('/api/artifacts/1/file', 'a.pdf')).toBe(
      '/api/artifacts/1/file#toolbar=0&navpanes=0&view=FitH',
    )
    expect(previewSrc('/api/artifacts/1/file', 'ohneendung', 'pdf')).toContain('view=FitH')
  })

  it('leaves every other source exactly as it is', () => {
    expect(previewSrc('/api/artifacts/1/file', 'a.html')).toBe('/api/artifacts/1/file')
    expect(previewSrc('/api/artifacts/1/file', 'bild', 'png')).toBe('/api/artifacts/1/file')
    expect(previewSrc('/api/file?path=%2Fa.pdf', 'a.pdf')).toContain('%2Fa.pdf#toolbar=0')
  })
})

describe('previewShowsInFrame: what this frame can show here', () => {
  // Measured on the running desktop window: the same address, 200 and
  // application/pdf, and the WebKit frame stayed white. A browser can do it.
  it('turns the PDF away in the desktop window and not in the browser', () => {
    expect(previewShowsInFrame('bericht.pdf', 'pdf', true)).toBe(false)
    expect(previewShowsInFrame('bericht.pdf', 'pdf', false)).toBe(true)
  })

  it('lets every other format through, on both surfaces', () => {
    for (const desktop of [true, false]) {
      expect(previewShowsInFrame('seite.html', 'html', desktop)).toBe(true)
      expect(previewShowsInFrame('bild.png', 'png', desktop)).toBe(true)
      expect(previewShowsInFrame('tabelle.xlsx', 'xlsx', desktop)).toBe(true)
    }
  })
})

describe('documentAddress — A1', () => {
  it('splits a file endpoint into the name and the folder it came from', () => {
    expect(documentAddress('/api/file?path=%2Ftmp%2Fproj%2Fbericht.pdf')).toEqual({
      name: 'bericht.pdf',
      folder: 'tmp/proj',
    })
  })

  it('names a file at the root with no folder', () => {
    expect(documentAddress('/api/file?path=%2FREADME.md')).toEqual({
      name: 'README.md',
      folder: '',
    })
  })

  it('reads a plain path the same way', () => {
    expect(documentAddress('/srv/app/docs/index.html').name).toBe('index.html')
  })

  it('keeps a malformed escape instead of throwing', () => {
    expect(documentAddress('/api/file?path=%25zz%25.pdf').name).toContain('.pdf')
  })
})

describe('the interactive frame the artifact panel asks for', () => {
  it('stays hard until a caller asks on purpose', () => {
    expect(previewSandbox('seite.html')).toBe('allow-popups')
    expect(previewSrc('/api/artifacts/1/file', 'seite.html')).toBe('/api/artifacts/1/file')
  })

  it('gives the panel its scripts and never its origin', () => {
    const box = previewSandbox('seite.html', 'html', true)
    expect(box).toBe('allow-scripts allow-popups')
    expect(box).not.toContain('allow-same-origin')
    expect(previewSandbox('folie.pdf', 'pdf', true)).toBeUndefined()
  })

  it('marks only our own API address, once', () => {
    expect(previewSrc('/api/artifacts/1/file', 'a.html', 'html', true)).toBe(
      '/api/artifacts/1/file?preview=1',
    )
    expect(previewSrc('/api/artifacts/1/file?token=abc', 'a.html', 'html', true)).toBe(
      '/api/artifacts/1/file?token=abc&preview=1',
    )
    expect(previewSrc('/api/artifacts/1/file?preview=1', 'a.html', 'html', true)).toBe(
      '/api/artifacts/1/file?preview=1',
    )
    // A foreign URL never carries the marker: the answer for it is not ours to loosen.
    expect(previewSrc('https://example.test/a.html', 'a.html', 'html', true)).toBe(
      'https://example.test/a.html',
    )
  })
})
