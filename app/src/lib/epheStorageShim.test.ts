/**
 * The page-storage shim a sandboxed surface gets instead of an origin.
 *
 * The served file (`sdk/ephe-storage.js`) is a classic script; evaluating its body
 * in this realm is what a document does with it, so these tests exercise the exact
 * bytes the mount serves. jsdom's own `localStorage` works, which is the control:
 * a working native area is left alone, and only a refused one is replaced.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const SOURCE = readFileSync(resolve(__dirname, '../../../sdk/ephe-storage.js'), 'utf-8')

type Send = (method: string, fields: Record<string, unknown>) => Promise<unknown>

type StoreOptions = {
  force?: boolean
  snapshot?: Record<string, unknown> | null
  sessionSnapshot?: Record<string, unknown>
  send?: Send
}

type Shim = {
  install(options?: StoreOptions): void
  failure(code: string, message: string): Error
}

function shim(): Shim {
  return (globalThis as unknown as { EpheStorageShim: Shim }).EpheStorageShim
}

function load(): Shim {
  new Function(SOURCE)()
  return shim()
}

/** The engine's own refusal: the property read itself throws in a sandbox. */
function refuseNative(...names: Array<'localStorage' | 'sessionStorage'>) {
  for (const name of names) {
    Object.defineProperty(window, name, {
      configurable: true,
      get() {
        throw new DOMException(
          `Failed to read the '${name}' property from 'Window': The document is sandboxed and lacks the 'allow-same-origin' flag.`,
          'SecurityError',
        )
      },
    })
  }
}

/** The error a call threw, so its `name` and `code` can be read. */
function thrown(call: () => unknown): Error {
  try {
    call()
  } catch (error) {
    return error as Error
  }
  throw new Error('the call did not throw')
}

const original = new Map<string, PropertyDescriptor | undefined>()

beforeEach(() => {
  for (const name of ['localStorage', 'sessionStorage']) {
    original.set(name, Object.getOwnPropertyDescriptor(window, name))
  }
})

afterEach(() => {
  for (const name of ['localStorage', 'sessionStorage']) {
    const descriptor = original.get(name)
    if (descriptor) Object.defineProperty(window, name, descriptor)
    else delete (window as unknown as Record<string, unknown>)[name]
  }
  vi.restoreAllMocks()
})

describe('the page-storage shim', () => {
  it('leaves a working native area alone', () => {
    const api = load()
    const native = window.localStorage
    api.install()
    expect(window.localStorage).toBe(native)
  })

  it('answers reads from the snapshot the mount embedded', () => {
    load()
    refuseNative('localStorage')
    shim().install({ force: true, snapshot: { theme: 'dark', count: 3 } })
    expect(localStorage.getItem('theme')).toBe('dark')
    // A value an `ephe.storage.set` call wrote keeps its JSON text here.
    expect(localStorage.getItem('count')).toBe('3')
    expect(localStorage.getItem('missing')).toBeNull()
    expect(localStorage.length).toBe(2)
  })

  it('keeps a read after a write, and sends the write over the bridge', async () => {
    load()
    refuseNative('localStorage')
    const send = vi.fn((_method: string, _fields: Record<string, unknown>) =>
      Promise.resolve({ present: true }),
    )
    shim().install({ force: true, snapshot: {}, send })

    localStorage.setItem('note', 'first')
    expect(localStorage.getItem('note')).toBe('first')
    localStorage.setItem('note', 2)
    expect(localStorage.getItem('note')).toBe('2')
    expect(localStorage.length).toBe(1)
    expect(localStorage.key(0)).toBe('note')
    expect(localStorage.key(9)).toBeNull()

    await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(2))
    expect(send).toHaveBeenNthCalledWith(1, 'storage.set', { key: 'note', value: 'first' })
    expect(send).toHaveBeenNthCalledWith(2, 'storage.set', { key: 'note', value: '2' })
  })

  it('forgets a removed key and clears what it knows', async () => {
    load()
    refuseNative('localStorage')
    const send = vi.fn((_method: string, _fields: Record<string, unknown>) =>
      Promise.resolve({ present: false }),
    )
    shim().install({ force: true, snapshot: { a: '1', b: '2' }, send })

    localStorage.removeItem('a')
    expect(localStorage.getItem('a')).toBeNull()
    localStorage.clear()
    expect(localStorage.length).toBe(0)

    await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(2))
    expect(send).toHaveBeenNthCalledWith(1, 'storage.set', { key: 'a', value: null })
    expect(send).toHaveBeenNthCalledWith(2, 'storage.set', { key: 'b', value: null })
  })

  it('names a refused write and puts the key back to its confirmed value', async () => {
    load()
    refuseNative('localStorage')
    const refused = shim().failure('storage_refused', 'the host refused')
    const send = vi.fn((_method: string, _fields: Record<string, unknown>) =>
      Promise.reject(refused),
    )
    const heard: CustomEvent[] = []
    window.addEventListener('ephestorageerror', (event) => heard.push(event as CustomEvent))
    shim().install({ force: true, snapshot: { note: 'confirmed' }, send })

    localStorage.setItem('note', 'optimistic')
    // The write-through view is what a read straight after the write sees.
    expect(localStorage.getItem('note')).toBe('optimistic')

    await vi.waitFor(() => expect(heard).toHaveLength(1))
    expect(heard[0].detail).toMatchObject({ key: 'note', code: 'storage_refused' })
    expect(thrown(() => localStorage.getItem('note'))).toMatchObject({
      name: 'EpheStorageError',
      code: 'storage_refused',
    })
    // The view fell back to what the shell confirmed, so nothing silent survives.
    expect(localStorage.key(0)).toBe('note')
    expect(localStorage.length).toBe(1)
  })

  it('does not drop a newer write when an earlier one is refused', async () => {
    load()
    refuseNative('localStorage')
    const refused = shim().failure('storage_refused', 'the host refused')
    const send = vi.fn((_method: string, fields: Record<string, unknown>) =>
      fields.key === 'a' && fields.value === '1'
        ? Promise.reject(refused)
        : Promise.resolve({ present: true }),
    )
    window.EpheStorageShim.install({ force: true, snapshot: {}, send })

    localStorage.setItem('a', '1')
    localStorage.setItem('b', '2')
    localStorage.setItem('a', '3')
    expect(localStorage.getItem('b')).toBe('2')
    expect(localStorage.getItem('a')).toBe('3')

    await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(3))
    // `a`'s refused write reverts only its own key; the later writes kept theirs,
    // and the newest `a` value is the one the view shows.
    expect(localStorage.getItem('a')).toBe('3')
    expect(localStorage.getItem('b')).toBe('2')
    expect(localStorage.length).toBe(2)
  })

  it('refuses a key the page store can never hold', () => {
    load()
    refuseNative('localStorage')
    const send = vi.fn((_method: string, _fields: Record<string, unknown>) =>
      Promise.resolve({ present: true }),
    )
    shim().install({ force: true, snapshot: {}, send })

    expect(thrown(() => localStorage.setItem('a b', 'v'))).toMatchObject({
      name: 'EpheStorageError',
      code: 'storage_key_invalid',
    })
    expect(thrown(() => localStorage.getItem('../../etc')).message).toMatch(/page-storage key/)
    expect(send).not.toHaveBeenCalled()
  })

  it('refuses to guess when the mount delivered no snapshot', () => {
    load()
    refuseNative('localStorage')
    shim().install({ force: true, snapshot: null })
    expect(thrown(() => localStorage.getItem('anything'))).toMatchObject({
      name: 'EpheStorageError',
      code: 'storage_unavailable',
    })
    // Not even the size is invented: an empty view over an unknown store is the
    // silent wrong answer this file exists to avoid.
    expect(thrown(() => localStorage.length)).toMatchObject({ code: 'storage_unavailable' })
  })

  it('keeps sessionStorage as a per-document memory area, off the bridge', () => {
    load()
    refuseNative('localStorage', 'sessionStorage')
    const send = vi.fn((_method: string, _fields: Record<string, unknown>) =>
      Promise.resolve({ present: true }),
    )
    shim().install({ force: true, snapshot: {}, send })

    sessionStorage.setItem('wizard', 'step-2')
    expect(sessionStorage.getItem('wizard')).toBe('step-2')
    expect(localStorage.getItem('wizard')).toBeNull()
    expect(send).not.toHaveBeenCalled()

    sessionStorage.clear()
    expect(sessionStorage.length).toBe(0)
  })
})
