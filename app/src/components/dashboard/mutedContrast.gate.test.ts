// P4 finding 7 (this round only, no global tokens): muted text with
// text-status-info below /70 fails 4.5:1 for 10-11 px text on paper
// (measured: /50 = 2.93:1, /55 = 3.31:1, /60 = 3.83:1; /70 = 5.12:1,
// text-ink-faint = 4.98:1). This gate file reads the sources of this round and
//fails as soon as a weak step returns.
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const FILES = [
  'components/dashboard/agent/panelAddMenu.tsx',
  'components/dashboard/agent/useTabRegistry.ts',
  'components/dashboard/agent/panelTabBar.tsx',
  'components/dashboard/agent/tabsTabPill.tsx',
  'components/dashboard/settings/index.tsx',
  'components/dashboard/StatusBar.tsx',
]

// The brand's muted text step: text-status-info/50|55|60|65 stay below 4.5:1
// on paper. (The signal colours success/warning reach that value at no alpha —
// they are token decisions, not alpha steps; the status line instead uses
// text-ink-faint + a coloured icon.)
const WEAK = /text-status-info\/(?:50|55|60|65)\b/

describe('Gedaempfter Text in den Dateien dieser Runde (P4 Befund 7)', () => {
  it('keine Stufe unter 4,5:1 auf Papier', () => {
    const hits = FILES.flatMap((rel) => {
      const src = readFileSync(resolve(__dirname, '..', '..', rel), 'utf8')
      return src
        .split('\n')
        .map((line, i) => ({ rel, no: i + 1, line }))
        .filter(({ line }) => WEAK.test(line))
    })
    expect(hits.map((h) => `${h.rel}:${h.no} ${h.line.trim()}`)).toEqual([])
  })

  it('jede gedaeempfte Textstufe in diesen Dateien haelt /70 oder hoeher', () => {
    for (const rel of FILES) {
      const src = readFileSync(resolve(__dirname, '..', '..', rel), 'utf8')
      const steps = [...src.matchAll(/text-status-info\/(\d+)/g)].map((m) => Number(m[1]))
      for (const step of steps) expect(step).toBeGreaterThanOrEqual(70)
    }
  })
})
