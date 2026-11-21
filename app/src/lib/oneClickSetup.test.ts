import { describe, expect, it } from 'vitest'
import { recommendOneClickSetup } from './oneClickSetup'
import type { DetectedEngine } from './api/providers'

function engine(over: Partial<DetectedEngine>): DetectedEngine {
  return {
    provider: 'local_ollama',
    url: 'http://127.0.0.1:11434',
    reachable: true,
    models: [],
    detail: '',
    ...over,
  }
}

describe('recommendOneClickSetup', () => {
  it('takes the largest model that fits the reported memory', () => {
    const choice = recommendOneClickSetup(
      [
        engine({
          models: ['qwen2.5-coder:32b', 'llama3:8b'],
        }),
      ],
      24,
    )
    expect(choice?.model).toBe('llama3:8b')
    expect(choice?.fit?.verdict).toBe('optimal')
    expect(choice?.basis).toBe('local')
  })

  it('uses the full budget for the larger model when the machine holds it', () => {
    const choice = recommendOneClickSetup([engine({ models: ['llama3:8b', 'qwen2.5-coder:32b'] })], 64)
    expect(choice?.model).toBe('qwen2.5-coder:32b')
  })

  it('states an unknown size instead of guessing when no memory is reported', () => {
    const choice = recommendOneClickSetup([engine({ models: ['llama3:8b', 'qwen2.5-coder:32b'] })], null)
    expect(choice).toEqual({
      kind: 'local_ollama',
      url: 'http://127.0.0.1:11434',
      model: 'llama3:8b',
      fit: null,
      basis: 'local',
    })
  })

  it('never recommends a model that would swap', () => {
    expect(recommendOneClickSetup([engine({ models: ['qwen2.5-coder:32b'] })], 16)).toBeNull()
  })

  it('skips an engine whose probe answered with a borrowed key', () => {
    expect(
      recommendOneClickSetup([engine({ models: ['llama3:8b'], key_source: 'foreign' })], 24),
    ).toBeNull()
  })

  it('ignores keyed cloud endpoints and unreachable candidates', () => {
    expect(
      recommendOneClickSetup(
        [
          engine({ provider: 'openai_compatible', models: ['gpt-4o-mini'], url: 'https://x/v1' }),
          engine({ reachable: false, models: ['llama3:8b'] }),
        ],
        24,
      ),
    ).toBeNull()
  })

  it('falls back to an endpoint the user already runs', () => {
    const choice = recommendOneClickSetup(
      [engine({ reachable: false }), engine({ provider: 'custom_ollama', url: 'http://10.0.0.5:11434', models: ['llama3:8b'] })],
      24,
    )
    expect(choice?.kind).toBe('custom_ollama')
    expect(choice?.url).toBe('http://10.0.0.5:11434')
    expect(choice?.basis).toBe('own')
  })
})
