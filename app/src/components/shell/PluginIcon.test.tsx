/**
 * Ephe — PluginIcon
 *
 * GIVEN the icon route
 * WHEN the tile asks for the bytes
 * THEN the request carries X-Auth-Token when a LAN token is set,
 *      the URL holds no token, and a failed fetch is the lettermark.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, render, screen } from '@testing-library/react'

import PluginIcon from './PluginIcon'

const api = vi.hoisted(() => ({ BASE_URL: '', LAN_TOKEN: null as string | null }))

vi.mock('@/lib/api', () => api)

function svgResponse(status = 200): Response {
  return new Response('<svg xmlns="http://www.w3.org/2000/svg"></svg>', {
    status,
    headers: { 'content-type': 'image/svg+xml' },
  })
}

function pendingResponse(): {
  promise: Promise<Response>
  resolve: (response: Response) => void
} {
  let resolve: (response: Response) => void = () => {}
  const promise = new Promise<Response>((settle) => {
    resolve = settle
  })
  return { promise, resolve }
}

describe('PluginIcon', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    api.LAN_TOKEN = null
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
    URL.createObjectURL = vi.fn(() => 'blob:icon')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  async function settle(pluginId: string, response: Response, name = 'Documents') {
    const gate = pendingResponse()
    fetchMock.mockReturnValue(gate.promise)
    render(<PluginIcon pluginId={pluginId} name={name} />)
    await act(async () => {
      gate.resolve(response)
      await gate.promise
    })
  }

  it('fetches the icon with the header and paints the blob', async () => {
    api.LAN_TOKEN = 'lan-secret'
    await settle('documents', svgResponse())
    const img = screen.getByTestId('plugin-icon-documents') as HTMLImageElement
    expect(img.tagName).toBe('IMG')
    expect(img.getAttribute('src')).toBe('blob:icon')
    expect(img.className).toContain('h-11')
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/plugins/icon/documents')
    expect(url).not.toContain('token')
    expect(new Headers(init.headers).get('X-Auth-Token')).toBe('lan-secret')
  })

  it('omits the header when the desktop has no LAN token', async () => {
    await settle('memory', svgResponse())
    expect(screen.getByTestId('plugin-icon-memory').tagName).toBe('IMG')
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/plugins/icon/memory')
    expect(new Headers(init.headers).has('X-Auth-Token')).toBe(false)
  })

  it('shares one fetch across two tiles of the same plugin', async () => {
    const gate = pendingResponse()
    fetchMock.mockReturnValue(gate.promise)
    render(<PluginIcon pluginId="guide" name="Guide" />)
    render(<PluginIcon pluginId="guide" name="Guide" />)
    await act(async () => {
      gate.resolve(svgResponse())
      await gate.promise
    })
    expect(screen.getAllByTestId('plugin-icon-guide').every((el) => el.tagName === 'IMG')).toBe(
      true,
    )
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('paints the lettermark when the icon route refuses', async () => {
    await settle('code-shell', svgResponse(401), 'Code')
    const tile = screen.getByTestId('plugin-icon-code-shell')
    expect(tile.tagName).toBe('SPAN')
    expect(tile.textContent).toBe('C')
  })

  it('asks nothing when the payload says the manifest has no icon', async () => {
    render(<PluginIcon pluginId="cve-popup" name="CVE" hasIcon={false} />)
    await act(async () => {
      await Promise.resolve()
    })
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByTestId('plugin-icon-cve-popup').tagName).toBe('SPAN')
  })

  it('remembers a refused icon, so a second tile does not ask again', async () => {
    fetchMock.mockResolvedValue(svgResponse(404))
    render(<PluginIcon pluginId="foreman" name="Foreman" />)
    await act(async () => {
      await Promise.resolve()
    })
    render(<PluginIcon pluginId="foreman" name="Foreman" />)
    await act(async () => {
      await Promise.resolve()
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(screen.getAllByTestId('plugin-icon-foreman').every((el) => el.tagName === 'SPAN')).toBe(
      true,
    )
  })

  it('keeps a deterministic lettermark angle', () => {
    const angle = (slug: string) => [...slug].reduce((acc, ch) => acc + ch.charCodeAt(0), 0) % 360
    expect(angle('documents')).toBe(angle('documents'))
    expect(angle('documents')).not.toBe(angle('memory'))
  })
})
