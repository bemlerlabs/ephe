import { describe, it, expect } from 'vitest'
import {
  artifactPreviewMode,
  codePreviewLanguage,
  previewSandbox,
  previewShowsInFrame,
  previewSrc,
  resolveFilePreview,
  prettifyUrl,
} from '@/lib/previewMode'

describe('resolveFilePreview — DD-12', () => {
  it('erkennt ein Markdown-File im File-Endpoint und dekodiert den Pfad', () => {
    const r = resolveFilePreview('/api/file?path=%2Ftmp%2Fproj%2FREADME.md')
    expect(r).toEqual({ kind: 'markdown', path: '/tmp/proj/README.md', filename: 'README.md' })
  })

  it('mappt Code-Endungen auf Sprache und restliche Textdateien auf plain', () => {
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

  it('HTML/Unbekanntes bleibt beim IFrame (Side-by-Site rendering, kein entkommtes Markup)', () => {
    expect(resolveFilePreview('/api/file?path=%2Fsite%2Findex.html')).toBeNull()
    expect(resolveFilePreview('http://127.0.0.1:5173/')).toBeNull()
    expect(resolveFilePreview('')).toBeNull()
  })

  it('laesst sich nicht ueber Traversals oder fremde Queries zu einem Textpfad ueberreden', () => {
    expect(resolveFilePreview('/api/file?path=abc&other=%2Fx.md')).toBeNull()
  })
})

describe('prettifyUrl — DD-12 URL-Chip', () => {
  it('zeigt im File-Endpoint nur den Dateinamen, nicht das rohe Query', () => {
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
    ['deck.pptx', 'deck', 'none'],
    ['irgendwas.bin', 'file', 'none'],
  ] as const)('%s → %s', (name, kind, want) => {
    expect(artifactPreviewMode(name, kind)).toBe(want)
  })

  it('verlässt sich nicht auf die Endung allein: eine Art ohne Punkt folgt dem kind', () => {
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
    expect(artifactPreviewMode('deck.pptx', 'deck')).toBe('none')
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
describe('previewSandbox — eine Regel, zwei Flächen', () => {
  it('lässt dem toten Format die Direktive ganz', () => {
    expect(previewSandbox('analyse-2026.pdf')).toBeUndefined()
    expect(previewSandbox('ohneendung', 'pdf')).toBeUndefined()
  })

  // Round 12 stays tight: model-generated markup never got an origin, because
  // otherwise it could read the app session.
  it('hält HTML, Decks und alles andere im dichten Rahmen', () => {
    for (const name of ['seite.html', 'deck.htm', 'bericht.docx', 'tabelle.xlsx', 'bild.svg']) {
      const box = previewSandbox(name)
      expect(box).toBe('allow-popups')
      expect(box).not.toContain('allow-same-origin')
      expect(box).not.toContain('allow-scripts')
    }
  })

  it('lässt den Namen entscheiden, wenn beide etwas sagen', () => {
    // The card is named .html — then it stays isolated markup even when its kind
    // says pdf. The other way round, a name without a dot carries the type.
    expect(previewSandbox('a.html', 'pdf')).toBe('allow-popups')
    expect(previewSandbox('ohnepunkt', 'pdf')).toBeUndefined()
  })
})

describe('previewSrc — was in den Rahmen gehört', () => {
  // Measured in the image: without parameters the viewer showed a horizontally
  // cut strip of the sheet inside the short preview frame.
  it('legt das PDF auf die Rahmenbreite und lässt seine Werkzeugzeile weg', () => {
    expect(previewSrc('/api/artifacts/1/file', 'a.pdf')).toBe(
      '/api/artifacts/1/file#toolbar=0&navpanes=0&view=FitH',
    )
    expect(previewSrc('/api/artifacts/1/file', 'ohneendung', 'pdf')).toContain('view=FitH')
  })

  it('lässt jede andere Quelle exakt so, wie sie ist', () => {
    expect(previewSrc('/api/artifacts/1/file', 'a.html')).toBe('/api/artifacts/1/file')
    expect(previewSrc('/api/artifacts/1/file', 'bild', 'png')).toBe('/api/artifacts/1/file')
    expect(previewSrc('/api/file?path=%2Fa.pdf', 'a.pdf')).toContain('%2Fa.pdf#toolbar=0')
  })
})

describe('previewShowsInFrame — was dieser Rahmen hier zeigen kann', () => {
  // Measured on the running desktop window: the same address, 200 and
  // application/pdf, and the WebKit frame stayed white. A browser can do it.
  it('weist das PDF im Desktop-Fenster ab, im Browser nicht', () => {
    expect(previewShowsInFrame('bericht.pdf', 'pdf', true)).toBe(false)
    expect(previewShowsInFrame('bericht.pdf', 'pdf', false)).toBe(true)
  })

  it('lässt jedes andere Format durch, beide Flächen', () => {
    for (const desktop of [true, false]) {
      expect(previewShowsInFrame('seite.html', 'html', desktop)).toBe(true)
      expect(previewShowsInFrame('bild.png', 'png', desktop)).toBe(true)
      expect(previewShowsInFrame('tabelle.xlsx', 'xlsx', desktop)).toBe(true)
    }
  })
})
