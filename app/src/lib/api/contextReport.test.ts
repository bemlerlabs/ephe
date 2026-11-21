// The report keeps the resolver's own vocabulary: a status it does not know stays
// visible, a layer without a name never becomes an empty row, and the total is the
// route's number when it sends one.
import { describe, expect, it } from 'vitest'

import { isKnownRuleStatus, parseContextReport } from './contextReport'

const PAYLOAD = {
  total_chars: 16_000,
  stages: [
    { name: 'identity', chars: 700, preview: 'You are Ephe' },
    {
      name: 'workspace_rules',
      chars: 15_300,
      preview: '## Project rules',
      files: [
        { name: 'AGEN' + 'TS.md', chars: 400, status: 'included' },
        {
          name: '.ephe/rules/big.md',
          chars: 6_000,
          status: 'truncated',
          reason: '',
        },
        {
          name: '.ephe/rules/locked.md',
          chars: 0,
          status: 'denied',
          reason: 'protected-root',
        },
        { name: '.ephe/rules/empty.md', chars: 0, status: 'empty' },
        { name: '.ephe/rules/late.md', chars: 0, status: 'skipped', reason: 'no-budget' },
      ],
    },
  ],
}

describe('parseContextReport', () => {
  it('keeps every layer and file the route reported', () => {
    const report = parseContextReport(PAYLOAD)
    expect(report.totalChars).toBe(16_000)
    expect(report.stages.map((s) => s.name)).toEqual(['identity', 'workspace_rules'])
    expect(report.stages[1]?.files).toHaveLength(5)
    expect(report.stages[1]?.files[2]).toEqual({
      name: '.ephe/rules/locked.md',
      chars: 0,
      status: 'denied',
      reason: 'protected-root',
    })
  })

  it('counts the caps that were hit, with what still arrived', () => {
    const report = parseContextReport(PAYLOAD)
    expect(report.caps).toEqual({
      truncatedFiles: 1,
      truncatedChars: 6_000,
      filesWithoutBudget: 1,
    })
  })

  it('does not read a skip for another reason as a cap hit', () => {
    const report = parseContextReport({
      total_chars: 10,
      stages: [
        {
          name: 'workspace_rules',
          chars: 10,
          files: [{ name: 'x.md', chars: 10, status: 'skipped', reason: 'outside-root' }],
        },
      ],
    })
    expect(report.caps.filesWithoutBudget).toBe(0)
  })

  it('sums the layers when the payload carries no total', () => {
    const report = parseContextReport({
      stages: [
        { name: 'identity', chars: 120 },
        { name: 'date', chars: 30 },
      ],
    })
    expect(report.totalChars).toBe(150)
    expect(report.caps.truncatedFiles).toBe(0)
  })

  it('prefers the reported total over the sum of the layers', () => {
    const report = parseContextReport({
      total_chars: 300,
      stages: [
        { name: 'identity', chars: 120 },
        { name: 'date', chars: 30 },
      ],
    })
    expect(report.totalChars).toBe(300)
  })

  it('keeps a status it has no label for, verbatim', () => {
    const report = parseContextReport({
      stages: [
        {
          name: 'workspace_rules',
          chars: 1,
          files: [{ name: 'q.md', chars: 1, status: 'quarantined' }],
        },
      ],
    })
    expect(report.stages[0]?.files[0]?.status).toBe('quarantined')
    expect(isKnownRuleStatus('quarantined')).toBe(false)
    expect(isKnownRuleStatus('truncated')).toBe(true)
  })

  it('drops a layer or file that carries no name instead of showing a zero row', () => {
    const report = parseContextReport({
      total_chars: 5,
      stages: [
        { chars: 5 },
        { name: '   ', chars: 5 },
        { name: 'identity', chars: 5, files: [{ chars: 5, status: 'included' }] },
      ],
    })
    expect(report.stages.map((s) => s.name)).toEqual(['identity'])
    expect(report.stages[0]?.files).toEqual([])
  })

  it('reports an empty prompt as empty, not as an error', () => {
    expect(parseContextReport({ stages: [], total_chars: 0 })).toEqual({
      stages: [],
      totalChars: 0,
      caps: { truncatedFiles: 0, truncatedChars: 0, filesWithoutBudget: 0 },
    })
    expect(parseContextReport(null)).toEqual({
      stages: [],
      totalChars: 0,
      caps: { truncatedFiles: 0, truncatedChars: 0, filesWithoutBudget: 0 },
    })
    expect(parseContextReport({ stages: 'nope', total_chars: 'nope' })).toEqual({
      stages: [],
      totalChars: 0,
      caps: { truncatedFiles: 0, truncatedChars: 0, filesWithoutBudget: 0 },
    })
  })
})
