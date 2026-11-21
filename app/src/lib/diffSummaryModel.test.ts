import { describe, it, expect } from 'vitest'
import { summarizeToolDiff } from './diffSummaryModel'

// M3 (reference parity): the "26 files changed +1187 -20" stat line per run
// — pure counting helpers over the tool calls of the message.

describe('summarizeToolDiff (M3)', () => {
  it('counts files and plus/minus lines from diff results', () => {
    const calls = [
      {
        name: 'edit_file',
        args: { path: '/tmp/a.ts' },
        result: '--- a.ts\n+++ a.ts\n@@\n+const x = 1\n+const y = 2\n+const z = 3\n-old = 0\n',
      },
    ]
    expect(summarizeToolDiff(calls)).toEqual({ files: 1, additions: 3, deletions: 1 })
  })

  it('deduplicates paths and ignores non-file tools', () => {
    const calls = [
      { name: 'edit_file', args: { path: '/tmp/a.ts' }, result: '+x\n-y' },
      { name: 'edit_file', args: { path: '/tmp/a.ts' }, result: '+z' },
      { name: 'read_file', args: { path: '/tmp/a.ts' }, result: '1\tschema' },
    ]
    expect(summarizeToolDiff(calls)).toEqual({ files: 1, additions: 2, deletions: 1 })
  })

  it('null without file-family calls (the row then does not render)', () => {
    expect(
      summarizeToolDiff([{ name: 'run_shell', args: { command: 'ls' }, result: 'a\nb' }]),
    ).toBeNull()
    expect(summarizeToolDiff([])).toBeNull()
  })

  it('write_file without diff output counts content as additions', () => {
    const calls = [{ name: 'write_file', args: { path: '/tmp/b.md' }, result: 'zeile1\nzeile2\n' }]
    expect(summarizeToolDiff(calls)).toEqual({ files: 1, additions: 2, deletions: 0 })
  })
})
