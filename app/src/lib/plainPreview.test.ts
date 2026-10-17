import { describe, expect, it } from 'vitest'
import { plainPreview } from './plainPreview'

describe('plainPreview', () => {
  it('removes markdown emphasis, code and links for the one-line preview', () => {
    expect(plainPreview('**📅 Weekly Review — KW 39 / 2026** ✅ **Done**')).toBe(
      '📅 Weekly Review — KW 39 / 2026 ✅ Done',
    )
    expect(plainPreview('Siehe `monthly_budget_2026.xlsx` und [Doku](https://example.test)')).toBe(
      'Siehe monthly_budget_2026.xlsx und Doku',
    )
    expect(plainPreview('# Titel\n\n- Punkt eins\n- Punkt zwei')).toBe(
      'Titel - Punkt eins - Punkt zwei',
    )
  })

  // The first draft stripped '_' across the board and wrecked filenames that way —
  // exactly what the history shows (monthly_budget_2026.xlsx).
  it('laesst snake_case-Namen heil', () => {
    expect(plainPreview('Erstellt: monthly_budget_2026.xlsx und ephe_cli.py')).toBe(
      'Erstellt: monthly_budget_2026.xlsx und ephe_cli.py',
    )
  })

  it('leaves plain text untouched apart from whitespace', () => {
    expect(plainPreview('Standup erstellt,   keine Blocker.')).toBe(
      'Standup erstellt, keine Blocker.',
    )
  })
})
