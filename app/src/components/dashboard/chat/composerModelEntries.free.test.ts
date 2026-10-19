// S2 host 3: a scan row is marked free only where the mirror's own free list says so.
// The `-free` / `:free` suffix is another service's naming convention; this surface
// states what our endpoint reported, so the suffix no longer decides anything.
import { describe, it, expect } from 'vitest'
import { buildScanEntries } from './composerModelEntries'
import type { MirrorTool } from '@/lib/api/environment'

const tool = (over: Partial<MirrorTool>): MirrorTool => ({
  tool: 'opencode',
  installed: true,
  config_path: '',
  providers: ['openrouter'],
  models: [],
  auth_present: true,
  model_endpoints: { 'deepseek/deepseek-chat:free': 'https://openrouter.ai/api/v1' },
  ...over,
})

describe("scan entries carry only the mirror's own free statement", () => {
  it('leaves a :free-suffixed model unknown when the mirror does not list it as free', () => {
    const [entry] = buildScanEntries([
      tool({ models: ['deepseek/deepseek-chat:free'], free_models: [] }),
    ])
    expect(entry?.free, JSON.stringify(entry)).toBeUndefined()
  })

  it('marks free only from free_models membership', () => {
    const [entry] = buildScanEntries([
      tool({
        models: ['deepseek/deepseek-chat:free'],
        free_models: ['deepseek/deepseek-chat:free'],
      }),
    ])
    expect(entry?.free).toBe(true)
  })

  it('keeps every local Ollama model free, because the mirror says so for the whole list', () => {
    const entries = buildScanEntries([
      tool({ providers: ['ollama'], models: ['llama3.1:8b'], free_models: ['llama3.1:8b'] }),
    ])
    expect(entries[0]?.free).toBe(true)
  })
})
