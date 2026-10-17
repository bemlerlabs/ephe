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
import { pickOpenPath, pickSaveTarget } from './nativeDialog'

const invoke = vi.fn()

beforeEach(() => {
  invoke.mockReset()
  ;(window as unknown as { __TAURI__?: unknown }).__TAURI__ = { core: { invoke } }
})
afterEach(() => {
  delete (window as unknown as { __TAURI__?: unknown }).__TAURI__
})

describe('pickOpenPath', () => {
  it('fragt das Shell-Dialog nach einer Datei, nicht nach einem Ordner', async () => {
    invoke.mockResolvedValue('/Users/x/Downloads/tisch.pdf')
    expect(await pickOpenPath()).toBe('/Users/x/Downloads/tisch.pdf')
    expect(invoke).toHaveBeenCalledWith('plugin:dialog|open', {
      options: { title: 'Datei anhängen', multiple: false, directory: false },
    })
  })

  it('nimmt aus einer Mehrfachauswahl den ersten Treffer', async () => {
    invoke.mockResolvedValue(['/a/b.pdf', '/c/d.pdf'])
    expect(await pickOpenPath('Anhang')).toBe('/a/b.pdf')
    expect(invoke.mock.calls[0]?.[1]).toMatchObject({ options: { title: 'Anhang' } })
  })

  it('ist null bei Abbruch, object-förmigem FilePath und ohne Shell', async () => {
    invoke.mockResolvedValue({ path: '/x/y.pdf', name: 'y.pdf' })
    expect(await pickOpenPath()).toBe('/x/y.pdf')
    invoke.mockResolvedValue(null)
    expect(await pickOpenPath()).toBeNull()
    delete (window as unknown as { __TAURI__?: unknown }).__TAURI__
    expect(await pickOpenPath()).toBeNull()
  })

  it('wirft nicht, wenn die Brücke nicht antwortet', async () => {
    invoke.mockRejectedValue(new Error('Dialog-Plugin fehlt'))
    expect(await pickOpenPath()).toBeNull()
  })
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
