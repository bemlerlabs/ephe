import { describe, expect, it } from 'vitest'
import { engineStateOf } from './engineState'
import type { HealthInfo } from '@/lib/api'

const health = (overrides: Partial<HealthInfo>): HealthInfo =>
  ({ active_model: 'm', active_tier: 't', status: 'ok', ...overrides }) as HealthInfo

describe('engineStateOf', () => {
  it('waits while the answer has not landed', () => {
    expect(engineStateOf(null)).toBe('checking')
  })

  it('reads a reachable engine with a model as ready', () => {
    expect(engineStateOf(health({ active_model: 'm', engine_online: true }))).toBe('ready')
  })

  it('keeps a refused key apart from an unreachable engine', () => {
    expect(engineStateOf(health({ engine_key_challenge: true }))).toBe('key-refused')
    expect(engineStateOf(health({ engine_state: 'unreachable' }))).toBe('unreachable')
    expect(engineStateOf(health({ engine_online: false }))).toBe('unreachable')
  })

  it('asks for a model when the engine answers without one', () => {
    expect(engineStateOf(health({ active_model: '' }))).toBe('no-model')
  })
})
