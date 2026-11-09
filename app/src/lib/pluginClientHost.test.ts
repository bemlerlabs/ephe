import { beforeEach, describe, expect, it, vi } from 'vitest'

const request = vi.fn()

vi.mock('./api/http', () => ({
  request: (...args: unknown[]) => request(...args),
  apiUrl: (path: string) => path,
  ApiError: class ApiError extends Error {
    reasonCode: string
    constructor(message: string, _status: number, reasonCode = '') {
      super(message)
      this.reasonCode = reasonCode
    }
  },
}))

import { SDK_CHANNEL, attachPluginClient } from './pluginClientHost'

class FakeSource {
  static latest: FakeSource | null = null
  listeners = new Map<string, (event: Event) => void>()
  constructor() {
    FakeSource.latest = this
  }
  addEventListener(name: string, listener: (event: Event) => void) {
    this.listeners.set(name, listener)
  }
  close() {}
}

beforeEach(() => {
  request.mockReset()
  vi.stubGlobal('EventSource', FakeSource)
})

function frame() {
  const posted: unknown[] = []
  const child = { postMessage: (data: unknown) => posted.push(data) } as unknown as Window
  return { child, posted, node: { contentWindow: child } }
}

describe('attachPluginClient', () => {
  it('ignores a message that did not come from its frame', async () => {
    const mounted = frame()
    attachPluginClient(mounted.node, 'web-research')
    window.dispatchEvent(
      new MessageEvent('message', {
        data: { channel: SDK_CHANNEL, id: '1', method: 'storage.get', key: 'note' },
        source: window,
      }),
    )
    await Promise.resolve()
    expect(request).not.toHaveBeenCalled()
    expect(mounted.posted).toEqual([])
  })

  it('reads one key through the storage route and answers the frame', async () => {
    request.mockResolvedValue({ value: { n: 1 }, present: true })
    const mounted = frame()
    attachPluginClient(mounted.node, 'web-research')
    window.dispatchEvent(
      new MessageEvent('message', {
        data: { channel: SDK_CHANNEL, id: '7', method: 'storage.get', key: 'note' },
        source: mounted.child,
      }),
    )
    await vi.waitFor(() => expect(mounted.posted).toHaveLength(1))
    expect(request).toHaveBeenCalledWith('/api/plugins/web-research/client/storage?key=note')
    expect(mounted.posted[0]).toMatchObject({
      channel: SDK_CHANNEL,
      id: '7',
      ok: true,
      result: { value: { n: 1 }, present: true },
    })
  })

  it('drops a lifecycle event that names another bundle', () => {
    const mounted = frame()
    attachPluginClient(mounted.node, 'web-research')
    const listener = FakeSource.latest?.listeners.get('plugin.state')
    expect(listener).toBeTypeOf('function')
    listener?.(new MessageEvent('plugin.state', { data: JSON.stringify({ name: 'voice' }) }))
    expect(mounted.posted).toEqual([])
    listener?.(new MessageEvent('plugin.state', { data: JSON.stringify({ name: 'web-research' }) }))
    expect(mounted.posted).toEqual([
      {
        channel: SDK_CHANNEL,
        method: 'event',
        event: 'plugin.state',
        data: { name: 'web-research' },
      },
    ])
  })
})
