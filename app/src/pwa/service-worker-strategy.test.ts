/**
 * Service-worker strategy + behaviour.
 *
 * The manifest test next door guards the precache list. This suite pins the
 * routing rules a regression would silently break — API/SSE never cached,
 * navigation network-first with an offline fallback, static cache-first — and
 * runs the worker in a VM with fake caches/fetch so the rules are exercised,
 * not only read. The offline shell depends on every one of them.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import vm from 'node:vm'
import { describe, expect, it, vi } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const swPath = resolve(here, '../../public/service-worker.js')
const rawSource = readFileSync(swPath, 'utf8')
const SOURCE = rawSource.replace(/__EPHE_SW_VERSION__/g, 'test-cache-v1')

interface FakeResponse {
  status: number
  headers: { get(name: string): string | null }
  clone(): FakeResponse
  url?: string
}

function fakeResponse(status: number, contentType?: string): FakeResponse {
  const res: FakeResponse = {
    status,
    headers: { get: (n) => (n.toLowerCase() === 'content-type' ? (contentType ?? null) : null) },
    clone: () => res,
  }
  return res
}

interface FakeRequest {
  url: string
  method: string
  mode: string
  destination: string
}

interface SwEvent {
  request?: FakeRequest
  data?: unknown
  waitUntil?(p: Promise<unknown>): void
  respondWith?(p: Promise<unknown>): void
}

interface Harness {
  listeners: Record<string, (event: SwEvent) => void>
  cache: Map<string, FakeResponse>
  putCalls: string[]
  deleted: string[]
  fetch: ReturnType<typeof vi.fn>
  skipWaiting: ReturnType<typeof vi.fn>
  claim: ReturnType<typeof vi.fn>
}

function loadSw(fetchImpl: (request: unknown) => unknown): Harness {
  const cache = new Map<string, FakeResponse>()
  const listeners: Harness['listeners'] = {}
  const putCalls: string[] = []
  const deleted: string[] = []

  const key = (req: { url?: string } | string) => (typeof req === 'string' ? req : (req.url ?? ''))
  const cacheStore = {
    put: async (req: { url?: string } | string, res: FakeResponse) => {
      putCalls.push(key(req))
      cache.set(key(req), res)
    },
    addAll: async () => {},
    match: async (req: { url?: string } | string) => cache.get(key(req)),
  }
  const caches = {
    open: async () => cacheStore,
    match: async (req: { url?: string } | string) => cache.get(key(req)),
    keys: async () => ['test-cache-v1', 'old-cache'],
    delete: async (name: string) => {
      deleted.push(name)
      return true
    },
  }
  const self = {
    addEventListener: (type: string, cb: Harness['listeners'][string]) => {
      listeners[type] = cb
    },
    skipWaiting: vi.fn(),
    clients: { claim: vi.fn() },
  }
  const context = { self, caches, fetch: vi.fn(fetchImpl), URL, console }
  vm.createContext(context)
  vm.runInContext(SOURCE, context)

  return {
    listeners,
    cache,
    putCalls,
    deleted,
    fetch: context.fetch as Harness['fetch'],
    skipWaiting: self.skipWaiting,
    claim: self.clients.claim,
  }
}

function dispatchFetch(h: Harness, request: FakeRequest): Promise<unknown> {
  const handler = h.listeners.fetch
  if (!handler) throw new Error('no fetch listener')
  let captured: Promise<unknown> | undefined
  handler({ request, respondWith: (p) => (captured = p) })
  if (!captured) throw new Error('respondWith was not called')
  return captured
}

/** Let the un-awaited cache writes settle. */
const flush = () => new Promise((r) => setTimeout(r, 0))

describe('service worker routing', () => {
  it('serves /api/* from the network only, never the cache', async () => {
    const h = loadSw(async () => fakeResponse(200))
    const res = await dispatchFetch(h, {
      url: 'http://ephe.local/api/chat/stream',
      method: 'GET',
      mode: 'cors',
      destination: '',
    })
    expect((res as FakeResponse).status).toBe(200)
    expect(h.fetch).toHaveBeenCalledTimes(1)
    await flush()
    expect(h.putCalls).toEqual([])
  })

  it('never caches a non-GET request', async () => {
    const h = loadSw(async () => fakeResponse(200))
    await dispatchFetch(h, {
      url: 'http://ephe.local/api/chat',
      method: 'POST',
      mode: 'cors',
      destination: '',
    })
    await flush()
    expect(h.putCalls).toEqual([])
  })

  it('navigation: network-first, and a fresh 200 is cached for the offline path', async () => {
    const h = loadSw(async () => fakeResponse(200, 'text/html'))
    const res = await dispatchFetch(h, {
      url: 'http://ephe.local/',
      method: 'GET',
      mode: 'navigate',
      destination: 'document',
    })
    expect((res as FakeResponse).status).toBe(200)
    await flush()
    expect(h.putCalls).toContain('http://ephe.local/')
  })

  it('navigation: falls back to the cached shell when the network is gone', async () => {
    const h = loadSw(async () => {
      throw new Error('offline')
    })
    h.cache.set('/', fakeResponse(200, 'text/html'))
    const res = await dispatchFetch(h, {
      url: 'http://ephe.local/deep/link',
      method: 'GET',
      mode: 'navigate',
      destination: 'document',
    })
    expect((res as FakeResponse).status).toBe(200)
  })

  it('static assets: cache-first, the network is not touched on a hit', async () => {
    const h = loadSw(async () => {
      throw new Error('the network must not be reached')
    })
    h.cache.set('http://ephe.local/assets/app-abc.js', fakeResponse(200, 'text/javascript'))
    const res = await dispatchFetch(h, {
      url: 'http://ephe.local/assets/app-abc.js',
      method: 'GET',
      mode: 'cors',
      destination: 'script',
    })
    expect((res as FakeResponse).status).toBe(200)
    expect(h.fetch).not.toHaveBeenCalled()
  })

  it('never stores an event-stream response', async () => {
    const h = loadSw(async () => fakeResponse(200, 'text/event-stream'))
    await dispatchFetch(h, {
      url: 'http://ephe.local/stream',
      method: 'GET',
      mode: 'cors',
      destination: '',
    })
    await flush()
    expect(h.putCalls).toEqual([])
  })
})

describe('service worker lifecycle', () => {
  it('install precaches but does not skipWaiting — updates stay user-controlled', async () => {
    const h = loadSw(async () => fakeResponse(200))
    let waited: Promise<unknown> | undefined
    h.listeners.install?.({ waitUntil: (p) => (waited = p) })
    await waited
    expect(h.skipWaiting).not.toHaveBeenCalled()
  })

  it('activate drops the old caches and claims the clients', async () => {
    const h = loadSw(async () => fakeResponse(200))
    let waited: Promise<unknown> | undefined
    h.listeners.activate?.({ waitUntil: (p) => (waited = p) })
    await waited
    expect(h.deleted).toEqual(['old-cache'])
    expect(h.claim).toHaveBeenCalledTimes(1)
  })

  it('a SKIP_WAITING message activates the waiting worker', () => {
    const h = loadSw(async () => fakeResponse(200))
    h.listeners.message?.({ data: { type: 'SKIP_WAITING' } })
    expect(h.skipWaiting).toHaveBeenCalledTimes(1)
  })

  it('ignores any other message', () => {
    const h = loadSw(async () => fakeResponse(200))
    h.listeners.message?.({ data: { type: 'something-else' } })
    h.listeners.message?.({ data: 'not-an-object' })
    expect(h.skipWaiting).not.toHaveBeenCalled()
  })

  it('keeps the cache-version placeholder for the build stamp', () => {
    expect(rawSource).toContain('__EPHE_SW_VERSION__')
  })
})
