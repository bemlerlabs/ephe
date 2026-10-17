/**
 * P1-5 LiveTerminal — the WebSocket protocol against xterm.js + WS (both mocked;
 * jsdom has neither Canvas nor WebSocket). Checks the frames in both directions
 * and the clean close that does not kill the backend session.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, act } from '@testing-library/react'

const xterm = vi.hoisted(() => ({
  instance: null as null | Record<string, ReturnType<typeof vi.fn>>,
  created: 0,
}))
const fitState = vi.hoisted(() => ({ fits: 0 }))
const sockets = vi.hoisted(() => ({ all: [] as FakeWs[] }))

class FakeWs {
  static OPEN = 1
  readyState = 1
  url: string
  onopen: (() => void) | null = null
  onmessage: ((ev: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  sent: string[] = []
  closed = false
  constructor(url: string) {
    this.url = url
    sockets.all.push(this)
  }
  send(data: string) {
    this.sent.push(data)
  }
  close() {
    this.closed = true
  }
}

vi.mock('@xterm/xterm', () => ({
  Terminal: class {
    cols = 80
    rows = 24
    write = vi.fn()
    open = vi.fn()
    loadAddon = vi.fn()
    focus = vi.fn()
    dispose = vi.fn()
    resize = vi.fn()
    onData = vi.fn((cb: (d: string) => void) => {
      ;(this as unknown as { __data: unknown }).__data = cb
      return { dispose: () => {} }
    })
    constructor() {
      xterm.created += 1
      xterm.instance = this as unknown as Record<string, ReturnType<typeof vi.fn>>
    }
  },
}))
vi.mock('@xterm/addon-fit', () => ({
  FitAddon: class {
    fit() {
      fitState.fits += 1
    }
  },
}))
vi.mock('@/lib/api', () => ({ wsUrl: (p: string) => `ws://test${p}` }))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))

import LiveTerminal from './LiveTerminal'

beforeEach(() => {
  xterm.instance = null
  xterm.created = 0
  fitState.fits = 0
  sockets.all = []
  vi.stubGlobal('WebSocket', FakeWs)
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('LiveTerminal WS-Protokoll (P1-5)', () => {
  it('baut Terminal + WS auf /api/shell/term und schickt resize beim open', () => {
    render(<LiveTerminal />)
    const ws = sockets.all[0]!
    expect(ws.url).toBe('ws://test/api/shell/term')
    act(() => ws.onopen?.())
    expect(JSON.parse(ws.sent[0]!)).toMatchObject({ type: 'resize', cols: 80, rows: 24 })
  })

  it('leitet getippte Keys als input-frame an den WS weiter', () => {
    render(<LiveTerminal />)
    const ws = sockets.all[0]!
    act(() => ws.onopen?.())
    act(() => (xterm.instance!.__data as (d: string) => void)('ls\n'))
    expect(JSON.parse(ws.sent[ws.sent.length - 1]!)).toEqual({ type: 'input', data: 'ls\n' })
  })

  it('schreibt output-frames ins Terminal und exit meldet Code', () => {
    render(<LiveTerminal />)
    const ws = sockets.all[0]!
    act(() => ws.onopen?.())
    act(() => ws.onmessage?.({ data: JSON.stringify({ type: 'output', data: 'hello\n' }) }))
    expect(xterm.instance!.write).toHaveBeenCalledWith('hello\n')
    act(() => ws.onmessage?.({ data: JSON.stringify({ type: 'exit', code: 3 }) }))
    const calls = xterm.instance!.write!.mock.calls as unknown as string[][]
    expect(String(calls[calls.length - 1]?.[0])).toMatch(/code 3/)
  })

  it('schließt WS und disposed Terminal beim Unmount (Backend-Session bleibt alive)', () => {
    const { unmount } = render(<LiveTerminal />)
    const ws = sockets.all[0]!
    act(() => ws.onopen?.())
    unmount()
    expect(ws.closed).toBe(true)
    expect(xterm.instance!.dispose).toHaveBeenCalled()
  })

  it('verbindet nach close mit Backoff neu', () => {
    vi.useFakeTimers()
    render(<LiveTerminal />)
    const first = sockets.all[0]!
    act(() => first.onclose?.())
    expect(sockets.all.length).toBe(1) // no reconnect yet before the timer fires
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(sockets.all.length).toBe(2)
    vi.useRealTimers()
  })
})
