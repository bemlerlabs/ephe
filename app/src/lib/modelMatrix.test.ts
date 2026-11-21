import { describe, expect, it } from 'vitest'
import {
  deduplicateEngineModels,
  estimateModelGb,
  evaluateModelHardwareFit,
  parameterBillions,
} from './modelMatrix'

describe('deduplicateEngineModels', () => {
  it('keeps one row per model id, first one wins', () => {
    const models = [
      { id: 'gemma4:12b', label: 'first' },
      { id: 'nous-hermes3:8b', label: 'second' },
      { id: 'Gemma4:12B ', label: 'duplicate' },
    ]
    expect(deduplicateEngineModels(models).map((m) => m.label)).toEqual(['first', 'second'])
  })

  it('drops an entry with no id rather than rendering an empty row', () => {
    expect(deduplicateEngineModels([{ id: '  ' }, { id: 'qwen2.5-coder:32b' }])).toHaveLength(1)
  })
})

describe('the hardware estimate', () => {
  it('reads billions of parameters out of the identifier', () => {
    expect(parameterBillions('gemma4:12b')).toBe(12)
    expect(parameterBillions('qwen2.5-coder:32b')).toBe(32)
    expect(parameterBillions('nous-hermes3:8b')).toBe(8)
    expect(parameterBillions('deepseek-flash')).toBeNull()
  })

  it('leaves the size unknown when the name states none', () => {
    expect(estimateModelGb('deepseek-flash')).toBeNull()
  })

  it('sizes a 12B model at Q4 near ten gigabytes', () => {
    const gb = estimateModelGb('gemma4:12b')!
    expect(gb).toBeGreaterThan(7)
    expect(gb).toBeLessThan(10)
  })

  it('sizes fp16 heavier than q4 for the same parameter count', () => {
    expect(estimateModelGb('m:8b-fp16')!).toBeGreaterThan(estimateModelGb('m:8b-q4')!)
  })

  it('prints no percentage without a real budget', () => {
    expect(evaluateModelHardwareFit('gemma4:12b', null)).toBeNull()
    expect(evaluateModelHardwareFit('deepseek-flash', 24)).toBeNull()
  })

  it('grades the fit against the budget it was given', () => {
    const tight = evaluateModelHardwareFit('qwen2.5-coder:32b', 24)!
    expect(tight.percent).toBeGreaterThan(60)
    expect(['tight', 'swap']).toContain(tight.verdict)
    const roomy = evaluateModelHardwareFit('nous-hermes3:8b', 64)!
    expect(roomy.verdict).toBe('optimal')
  })
})
