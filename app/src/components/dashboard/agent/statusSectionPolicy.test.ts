import { describe, expect, it } from 'vitest'
import { STATUS_SECTION_SCROLL_POLICY, type StatusSectionKind } from './statusSectionPolicy'

describe('STATUS_SECTION_SCROLL_POLICY (P6 B2)', () => {
  it('carries the Ephe norm heights for the core sections', () => {
    expect(STATUS_SECTION_SCROLL_POLICY.plan).toBe('max-h-80')
    expect(STATUS_SECTION_SCROLL_POLICY.goal).toBe('max-h-48')
    expect(STATUS_SECTION_SCROLL_POLICY.agent).toBe('max-h-48')
    expect(STATUS_SECTION_SCROLL_POLICY.environment).toBe('max-h-48')
  })

  it('is complete: every section has a height', () => {
    const kinds: StatusSectionKind[] = [
      'goal',
      'sessionPlans',
      'plan',
      'terminal',
      'workflow',
      'agent',
      'environment',
      'queries',
      'usage',
    ]
    for (const k of kinds) {
      expect(STATUS_SECTION_SCROLL_POLICY[k]).toMatch(/^max-h-\d+$/)
    }
  })
})
