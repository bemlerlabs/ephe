/**
 * R4 (A1, W5) — the native file dialogs.
 *
 * Both gestures live over the same bridge and both share the same excuse: no
 * shell or a cancel means null, never an exception. For years the composer
 * called a command the shell had never registered — which is why this checks
 * the response shape of the real `tauri-plugin-dialog` V2, not an invented
 * one.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { pickSaveTarget } from './nativeDialog'

const invoke = vi.fn()

beforeEach(() => {
  invoke.mockReset()
  ;(window as unknown as { __TAURI__?: unknown }).__TAURI__ = { core: { invoke } }
})
afterEach(() => {
  delete (window as unknown as { __TAURI__?: unknown }).__TAURI__
})

describe('pickSaveTarget', () => {
  it('hängt die Endung des Vorschlags als Filter an', async () => {
    invoke.mockResolvedValue('/tmp/Ziel/bericht.pdf')
    expect(await pickSaveTarget('bericht.pdf')).toEqual({
      path: '/tmp/Ziel/bericht.pdf',
      name: 'bericht.pdf',
    })
    expect(invoke.mock.calls[0]?.[1]).toMatchObject({
      options: { defaultPath: 'bericht.pdf', filters: [{ name: 'PDF', extensions: ['pdf'] }] },
    })
  })

  it('ohne Endung filtert es nicht, und ohne Brücke kommt null', async () => {
    invoke.mockResolvedValue({ path: '/tmp/ohne-enung' })
    expect(await pickSaveTarget('ohne-endung')).toEqual({
      path: '/tmp/ohne-enung',
      name: 'ohne-enung',
    })
    expect(invoke.mock.calls[0]?.[1]).toMatchObject({ options: { filters: [] } })
    delete (window as unknown as { __TAURI__?: unknown }).__TAURI__
    expect(await pickSaveTarget('bericht.pdf')).toBeNull()
  })
})
