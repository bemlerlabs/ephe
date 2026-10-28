import { afterEach, describe, expect, it, vi } from 'vitest'

import { multiplexIsOpen, subscribeMultiplex } from './multiplex'

class FakeEventSource extends EventTarget {
  static instances: FakeEventSource[] = []
  readonly url: string
  closed = false

  constructor(url: string) {
    super()
    this.url = url
    FakeEventSource.instances.push(this)
  }

  close(): void {
    this.closed = true
  }

  emit(type: string, payload?: unknown): void {
    const event = new Event(type) as Event & { data?: string }
    if (payload !== undefined) event.data = JSON.stringify(payload)
    this.dispatchEvent(event)
  }
}

const unsubscribeFns: Array<() => void> = []

function subscribe(fn: (event: unknown) => void, session?: string) {
  const off = subscribeMultiplex(fn as never, session)
  unsubscribeFns.push(off)
  return off
}

afterEach(() => {
  while (unsubscribeFns.length) unsubscribeFns.pop()!()
  FakeEventSource.instances = []
  vi.unstubAllGlobals()
})

describe('multiplex', () => {
  it('opens one stream for all listeners and keeps the session', () => {
    vi.stubGlobal('EventSource', FakeEventSource)
    const first = vi.fn()
    const second = vi.fn()
    subscribe(first, 's1')
    subscribe(second)

    expect(FakeEventSource.instances).toHaveLength(1)
    expect(FakeEventSource.instances[0]!.url).toContain('session=s1')
  })

  it('delivers a full snapshot and reports the stream open', () => {
    vi.stubGlobal('EventSource', FakeEventSource)
    const listener = vi.fn()
    subscribe(listener, 's1')
    const source = FakeEventSource.instances[0]!

    source.emit('open')
    source.emit('multiplex', { fleet: { workspaces: [], runs: [] }, cell: { alive: false } })

    expect(multiplexIsOpen()).toBe(true)
    expect(listener).toHaveBeenCalledWith({
      fleet: { workspaces: [], runs: [] },
      cell: { alive: false },
    })
  })

  it('ignores a malformed frame instead of throwing', () => {
    vi.stubGlobal('EventSource', FakeEventSource)
    const listener = vi.fn()
    subscribe(listener)
    const source = FakeEventSource.instances[0]!
    const event = new Event('multiplex') as Event & { data?: string }
    event.data = '{not json'
    source.dispatchEvent(event)
    expect(listener).not.toHaveBeenCalled()
  })

  it('closes the stream when the last listener leaves and falls back to polling', () => {
    vi.stubGlobal('EventSource', FakeEventSource)
    const off = subscribe(vi.fn(), 's1')
    off()
    expect(FakeEventSource.instances[0]!.closed).toBe(true)
    expect(multiplexIsOpen()).toBe(false)
  })

  it('survives a browser without EventSource', () => {
    vi.stubGlobal('EventSource', undefined)
    const off = subscribe(vi.fn())
    expect(multiplexIsOpen()).toBe(false)
    off()
  })
})
