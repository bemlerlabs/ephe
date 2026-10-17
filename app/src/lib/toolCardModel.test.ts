/**
 * Ephe — reference-B parity Z01–Z06: the classification model for the
 * tool-call cards in the chat stream.
 *
 * GIVEN  a ToolCall (name/args/result/status)
 * WHEN   classifyToolCall/parseExitCode/diffStats/filePreviewable
 * THEN   pure, deterministic decisions — family, icon, verb,
 *        human-facing target, exit chip, diff stats, preview suitability.
 */
import { describe, it, expect } from 'vitest'
import {
  classifyToolCall,
  parseExitCode,
  diffStats,
  filePreviewable,
  isDiffLike,
} from '@/lib/toolCardModel'

describe('classifyToolCall — Familien', () => {
  it('run_shell wird Terminal-Familie mit command-Ziel', () => {
    const m = classifyToolCall({
      id: '1',
      name: 'run_shell',
      args: { command: 'npm test' },
      result: 'ok',
      status: 'completed',
    })
    expect(m.family).toBe('shell')
    expect(m.icon).toBe('terminal')
    expect(m.command).toBe('npm test')
    expect(m.target).toBe('npm test')
  })

  it('edit_file wird Edit-Familie mit Basisnamen und Pfad', () => {
    const m = classifyToolCall({
      id: '1',
      name: 'edit_file',
      args: { path: '/tmp/proj/README.md' },
      status: 'completed',
    })
    expect(m.family).toBe('edit')
    expect(m.icon).toBe('filePen')
    expect(m.filePath).toBe('/tmp/proj/README.md')
    expect(m.target).toBe('README.md')
  })

  it('write_file bekommt Inhaltssprache per Endung', () => {
    const m = classifyToolCall({
      id: '1',
      name: 'write_file',
      args: { path: '/x/app.ts', content: 'const a=1' },
      status: 'completed',
    })
    expect(m.family).toBe('write')
    expect(m.icon).toBe('filePlus')
    expect(m.language).toBe('typescript')
  })

  it('manage_tasks wird Aufgaben-Familie', () => {
    const m = classifyToolCall({
      id: '1',
      name: 'manage_tasks',
      args: { action: 'add', title: 'Doks' },
      status: 'completed',
    })
    expect(m.family).toBe('task')
    expect(m.target).toBe('Doks')
  })

  it('browser_go/web_search sind Web-Familie, file_search Suche', () => {
    expect(
      classifyToolCall({
        id: '1',
        name: 'browser_go',
        args: { url: 'http://a' },
        status: 'completed',
      }).family,
    ).toBe('web')
    expect(
      classifyToolCall({ id: '2', name: 'web_search', args: { query: 'x' }, status: 'completed' })
        .family,
    ).toBe('web')
    expect(
      classifyToolCall({ id: '3', name: 'file_search', args: { query: 'y' }, status: 'completed' })
        .family,
    ).toBe('search')
  })

  it('Artefakt-Werkzeuge bekommen Package-Icon + Zielnamen', () => {
    const m = classifyToolCall({
      id: '1',
      name: 'create_pdf',
      args: { path: '/tmp/a/report.pdf' },
      status: 'completed',
    })
    expect(m.family).toBe('artifact')
    expect(m.icon).toBe('package')
    expect(m.target).toBe('report.pdf')
  })

  it('Unbekanntes faellt ehrlich auf generic zurueck', () => {
    const m = classifyToolCall({ id: '1', name: 'mystery_tool', args: {}, status: 'completed' })
    expect(m.family).toBe('generic')
    expect(m.icon).toBe('wrench')
  })

  it('fehllenhafte args brechen die Klassifikation nicht', () => {
    const m = classifyToolCall({
      id: '1',
      name: 'run_shell',
      args: { command: 42 },
      status: 'completed',
    })
    expect(m.family).toBe('shell')
    expect(m.command).toBe('')
  })

  it('P4-D/N-Regression: entscheidende Diskriminante, nicht Substring', () => {
    // tool_search carries "subagent" only inside the query payload — no subagent row:
    const s = classifyToolCall({
      id: '1',
      name: 'tool_search',
      args: { query: 'subagent delegate · P2-Layout' },
      status: 'completed',
    })
    expect(s.family).toBe('generic')
    // All three spawn-/chat names land in the subagent family:
    const sp = classifyToolCall({
      id: '2',
      name: 'spawn_agent',
      args: {
        description: 'P2-Layout',
        prompt: 'P2-Layout + P4-Doku',
        subagent_type: 'generalist',
      },
      status: 'completed',
    })
    expect(sp.family).toBe('subagent')
    expect(sp.target).toContain('generalist')
    expect(sp.target).toContain('P2-Layout + P4-Doku')
  })
})

describe('parseExitCode', () => {
  it('erkennt den run_shell-Suffix und liefert Rumpf + stderr-Rest', () => {
    const r = parseExitCode('fail out\n[exit 2] boom')
    expect(r).not.toBeNull()
    expect(r!.code).toBe(2)
    expect(r!.body).toBe('fail out')
    expect(r!.err).toBe('boom')
  })
  it('Marker ohne Fehler-Rhest → err leer', () => {
    expect(parseExitCode('out\n[exit 1]')?.err).toBe('')
  })
  it('kein Suffix → null', () => {
    expect(parseExitCode('alles gut')).toBeNull()
  })
})

describe('diffStats + Vorschau-Eignung', () => {
  const diff = [
    '--- a/x.py',
    '+++ b/x.py',
    '@@ -1,3 +1,4 @@',
    ' const a = 1',
    '+const b = 2',
    '+const c = 3',
    '-const d = 4',
  ].join('\n')

  it('zaehlt Zu- und Abnahmen gegen die Header', () => {
    expect(isDiffLike(diff)).toBe(true)
    expect(diffStats(diff)).toEqual({ added: 2, removed: 1 })
  })
  it('Nicht-Diff → null', () => {
    expect(diffStats('plain text')).toBeNull()
  })
  it('Markdown/Code sind vorschaufaehig; PDF/HTML/Bilder rendert der iframe nativ (Owner-Welle)', () => {
    expect(filePreviewable('/tmp/a/README.md')).toBe(true)
    expect(filePreviewable('/tmp/a/app.py')).toBe(true)
    expect(filePreviewable('/tmp/a/report.pdf')).toBe(true)
    expect(filePreviewable('/tmp/a/seite.html')).toBe(true)
    expect(filePreviewable('/tmp/a/pic.png')).toBe(true)
    expect(filePreviewable('')).toBe(false)
  })
})
