import { describe, it, expect } from 'vitest'
import { aggregateToolCalls, type ToolCallShape } from '@/lib/toolStreamModel'

// I1 (2026-09-07, reference parity): the chat stream groups consecutive tool
// calls of the same family into ONE compact line — like the reference
// ("Terminal · 3 Befehle"), not one chip per call. // language-gate: ignore — quotes the German summary row the reference UI renders
// Aggregation is a pure function; rendering only consumes its groups.

const call = (over: Partial<ToolCallShape>): ToolCallShape => ({
  id: over.id ?? 't',
  name: over.name ?? 'run_shell',
  args: over.args ?? {},
  status: 'completed',
  result: over.result,
  ...over,
})

describe('aggregateToolCalls (I1, Referenz-Paritaet)', () => {
  it('gruppiert aufeinanderfolgende Shell-Aufrufe zu einer Terminal-Zeile mit Zaehler', () => {
    const groups = aggregateToolCalls([
      call({ id: '1', name: 'run_shell', args: { command: 'ls' } }),
      call({ id: '2', name: 'run_shell', args: { command: 'git status' } }),
      call({ id: '3', name: 'run_shell', args: { command: 'pnpm test' } }),
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0]!.family).toBe('shell')
    expect(groups[0]!.calls).toHaveLength(3)
    expect(groups[0]!.summaryKey).toBe('streamGroup.terminal')
    expect(groups[0]!.count).toBe(3)
  })

  it('bricht die Gruppe bei Familienwechsel (shell -> edit -> shell = 3 Gruppen)', () => {
    const groups = aggregateToolCalls([
      call({ id: '1', name: 'run_shell', args: { command: 'ls' } }),
      call({
        id: '2',
        name: 'edit_file',
        args: { path: '/tmp/a.ts' },
        result: '--- a\n+++ b\n@@ -1 +1 @@\n-x\n+y',
      }),
      call({ id: '3', name: 'run_shell', args: { command: 'pnpm test' } }),
    ])
    expect(groups.map((g) => g.family)).toEqual(['shell', 'edit', 'shell'])
  })

  it('Einzel-Edit zeigt Ziel + Stats in der Zeile (Referenz: "Bearbeitet app.ts +38 −39")', () => {
    const groups = aggregateToolCalls([
      call({
        id: 'e1',
        name: 'edit_file',
        args: { path: '/proj/src/app.ts' },
        result:
          '--- a\n+++ b\n@@ -1,5 +1,7 @@\n' +
          Array(38).fill('+x').join('\n') +
          Array(39).fill('-y').join('\n'),
      }),
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0]!.family).toBe('edit')
    expect(groups[0]!.target).toBe('app.ts')
    expect(groups[0]!.additions).toBeGreaterThan(30)
    expect(groups[0]!.deletions).toBeGreaterThan(30)
  })

  it('Read-Gruppe zaehlt Dateien ("Gelesen · 2 Dateien")', () => {
    const groups = aggregateToolCalls([
      call({ id: 'r1', name: 'read_file', args: { path: '/p/a.ts' } }),
      call({ id: 'r2', name: 'read_file', args: { path: '/p/b.ts' } }),
    ])
    expect(groups[0]!.family).toBe('read')
    expect(groups[0]!.count).toBe(2)
    expect(groups[0]!.summaryKey).toBe('streamGroup.read')
  })

  it('leere Eingabe -> keine Gruppen', () => {
    expect(aggregateToolCalls([])).toEqual([])
  })

  // w10-12: a refusal is an outcome in its own right. The store writes `denied` for a
  // call that never ran, so the group accent has to read it — otherwise a denied
  // row keeps the "· Completed" wording (walkthrough 2026-10-12, FINDINGS §medium).
  it('counts a denied call as a failure (a refusal is never a success accent)', () => {
    const groups = aggregateToolCalls([
      call({
        id: 'd1',
        name: 'run_shell',
        status: 'denied',
        args: { command: 'echo hi' },
        result: '[TOOL-DENIED] run_shell was not executed: the user did not approve the run.',
      }),
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0]!.hasFailure).toBe(true)
  })

  it('keeps the group red when only one call in the group was denied', () => {
    const groups = aggregateToolCalls([
      call({ id: '1', name: 'run_shell', args: { command: 'ls' } }),
      call({ id: '2', name: 'run_shell', status: 'denied', args: { command: 'rm -rf /' } }),
    ])
    expect(groups).toHaveLength(1)
    expect(groups[0]!.hasFailure).toBe(true)
  })

  it('a group of plain completed calls stays without a failure accent', () => {
    const groups = aggregateToolCalls([
      call({ id: '1', name: 'run_shell', args: { command: 'ls' } }),
      call({ id: '2', name: 'read_file', args: { path: '/p/a.ts' } }),
    ])
    expect(groups.map((g) => g.hasFailure)).toEqual([false, false])
  })
})
