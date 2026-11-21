/**
 * W4 guard — the retired client bindings stay retired.
 *
 * `sendMessage` (the non-streaming `/api/chat` call) was dead: the app streams
 * through `/api/chat/stream`. `/api/settings/autonomous` was a route the server
 * removed; no client may bind it again. This test is the pin: the decision is a
 * claim until something fails when it is undone.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

import * as api from './index'

const here = dirname(fileURLToPath(import.meta.url))

function apiSources(): { name: string; text: string }[] {
  return readdirSync(here)
    .filter((name) => name.endsWith('.ts') && !name.endsWith('.test.ts'))
    .map((name) => ({ name, text: readFileSync(join(here, name), 'utf8') }))
}

describe('retired client bindings (W4)', () => {
  it('no longer exposes sendMessage (the non-streaming /api/chat call)', () => {
    expect('sendMessage' in api).toBe(false)
    for (const { text } of apiSources()) {
      expect(text).not.toContain('sendMessage')
    }
  })

  it('binds no client code to /api/chat or /api/settings/autonomous', () => {
    for (const { name, text } of apiSources()) {
      expect(text, name).not.toMatch(/\/api\/chat['"`]/)
      expect(text, name).not.toContain('/api/settings/autonomous')
    }
  })
})
