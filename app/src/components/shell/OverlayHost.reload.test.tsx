/**
 * A reload keeps the open surface and sends the bundle back through hot-mount.
 * A moved contract is shown. The frame address stays until a mount event arrives.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import '@/i18n'
import { useChatStore } from '@/store'
import { EMPTY_STACK, type SurfaceSpec, type Viewport } from './overlayModel'

const request = vi.fn()

vi.mock('@/lib/api/http', () => {
  class ApiError extends Error {
    status: number
    reasonCode: string
    payload: unknown
    constructor(message: string, status: number, reasonCode = '', payload: unknown = null) {
      super(message)
      this.status = status
      this.reasonCode = reasonCode
      this.payload = payload
    }
  }
  return {
    request: (...args: unknown[]) => request(...args),
    apiUrl: (path: string) => path,
    ApiError,
  }
})

import { ApiError } from '@/lib/api/http'
import OverlayHost from './OverlayHost'

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

const VIEWPORT: Viewport = { width: 1280, height: 800 }
const URL = 'http://127.0.0.1:8765/api/plugins/ui/acme-countdown/n0nce/'

function open() {
  const spec: SurfaceSpec = {
    pluginId: 'acme-countdown',
    title: 'Countdown',
    surfaceType: 'floating-window',
    url: URL,
    width: 360,
    height: 240,
    transparent: false,
  }
  act(() => useChatStore.getState().openOverlay(spec, VIEWPORT))
}

beforeEach(() => {
  request.mockReset()
  FakeSource.latest = null
  vi.stubGlobal('EventSource', FakeSource)
  act(() => useChatStore.setState({ overlay: EMPTY_STACK }))
})

describe('hot reload of an open surface', () => {
  it('reloads the document in place when this bundle mounts again', () => {
    render(<OverlayHost />)
    open()
    const frame = document.querySelector('iframe')
    expect(frame?.getAttribute('src')).toBe(URL)
    const listener = FakeSource.latest?.listeners.get('plugin.mount')
    expect(listener).toBeTypeOf('function')
    act(() => {
      listener?.(
        new MessageEvent('plugin.mount', {
          data: JSON.stringify({ name: 'voice', phase: 'mounted' }),
        }),
      )
    })
    expect(frame?.getAttribute('src')).toBe(URL)
    act(() => {
      listener?.(
        new MessageEvent('plugin.mount', {
          data: JSON.stringify({ name: 'acme-countdown', phase: 'mounted' }),
        }),
      )
    })
    expect(frame?.getAttribute('src')).toBe(`${URL}?ephe_reload=1`)
    expect(document.querySelector('[data-overlay-window]')).toBeTruthy()
    expect(frame?.getAttribute('sandbox')).toBe('allow-scripts allow-popups')
  })

  it('asks the hot-mount route and shows a changed contract without moving the frame', async () => {
    request.mockRejectedValue(
      new ApiError('changed', 409, 'mount_change_unacknowledged', {
        diff: [{ name: 'tick' }],
      }),
    )
    render(<OverlayHost />)
    open()
    fireEvent.click(screen.getByTestId('overlay-reload-acme-countdown'))
    expect(request).toHaveBeenCalledWith('/api/plugins/acme-countdown/hot-mount', {
      method: 'POST',
      body: JSON.stringify({}),
    })
    expect(await screen.findByTestId('overlay-reload-diff-acme-countdown')).toBeTruthy()
    expect(screen.getByTestId('overlay-reload-diff-acme-countdown').textContent).toContain('tick')
    expect(document.querySelector('iframe')?.getAttribute('src')).toBe(URL)
  })
})
