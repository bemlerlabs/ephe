import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const bridge = vi.hoisted(() => ({ available: true, invoke: vi.fn() }))
vi.mock('@/lib/tauriBridge', () => ({ tauriInvoke: () => (bridge.available ? bridge.invoke : null) }))
vi.mock('@/lib/api/http', () => ({ apiUrl: (path: string) => `http://127.0.0.1:8765${path}` }))

import { importPickedFolder } from './settingsImport'

const fetchMock = vi.fn()

beforeEach(() => {
  bridge.available = true
  bridge.invoke.mockReset()
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('the settings importer (M2)', () => {
  it('asks the shell for a folder, then spends the token on /api/import', async () => {
    bridge.invoke.mockResolvedValue('tok-1')
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ applied: { persona: true, skills: ['a', 'b'], mcp_servers: ['x'] } }),
    })
    const outcome = await importPickedFolder()
    expect(bridge.invoke).toHaveBeenCalledWith('pick_folder')
    expect(fetchMock).toHaveBeenCalledWith('http://127.0.0.1:8765/api/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: 'tok-1', apply: true }),
    })
    expect(outcome).toEqual({ skills: 2, servers: 1, persona: true })
  })

  it('does nothing in a browser tab, where no picker exists', async () => {
    bridge.available = false
    expect(await importPickedFolder()).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('stops when the picker is dismissed', async () => {
    bridge.invoke.mockResolvedValue('')
    expect(await importPickedFolder()).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('reports a refused import instead of pretending it ran', async () => {
    bridge.invoke.mockResolvedValue('tok-2')
    fetchMock.mockResolvedValue({ ok: false, status: 409, json: async () => ({}) })
    await expect(importPickedFolder()).rejects.toThrow('HTTP 409')
  })
})
