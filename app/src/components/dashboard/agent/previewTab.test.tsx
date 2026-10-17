/**
 * P1-8 (option A) — PreviewTab loads loopback dev servers on the REAL origin
 * (live HMR); only remote (LAN token) falls back to the srcDoc proxy.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

const api = vi.hoisted(() => ({ LAN_TOKEN: null as string | null, proxyFetch: vi.fn() }))

vi.mock('@/lib/api', () => api)
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))

import { PreviewTab } from './previewTab'

function renderPreview(url: string) {
  return render(
    <PreviewTab
      url={url}
      draft={url}
      nonce={0}
      inputRef={{ current: null }}
      setDraft={() => {}}
      recent={[]}
      onPickRecent={() => {}}
      onLoad={() => {}}
      onReload={() => {}}
      onBack={() => {}}
      onForward={() => {}}
      canBack={false}
      canForward={false}
    />,
  )
}

beforeEach(() => {
  api.LAN_TOKEN = null
  api.proxyFetch = vi.fn(async () => ({
    ok: true,
    status: 200,
    body: '<html>proxied</html>',
    url: '',
  }))
  vi.mocked(api.proxyFetch)
})

describe('PreviewTab Real-Origin (P1-8 Option A)', () => {
  it('laedt einen Loopback-Dev-Server lokal am echten src, OHNE srcDoc/Proxy', async () => {
    renderPreview('http://localhost:5173/')
    await vi.waitFor(() => {
      const frame = screen.getByTestId('preview-frame') as HTMLIFrameElement
      expect(frame.getAttribute('src')).toBe('http://localhost:5173/')
      expect(frame.getAttribute('srcdoc')).toBeNull()
    })
    expect(api.proxyFetch).not.toHaveBeenCalled()
  })

  it('nutzt remote (LAN-Token) den Proxy-Koerper als srcDoc-Fallback', async () => {
    api.LAN_TOKEN = 'secret-qr-token'
    renderPreview('http://127.0.0.1:3000/app')
    await vi.waitFor(() => {
      expect(api.proxyFetch).toHaveBeenCalledWith(3000, '/app')
    })
    const frame = screen.getByTestId('preview-frame') as HTMLIFrameElement
    await vi.waitFor(() => expect(frame.getAttribute('srcdoc')).toContain('proxied'))
  })

  it('externe URLs bleiben direkter src (kein Loopback-Proxy)', async () => {
    renderPreview('https://example.com/page')
    const frame = (await screen.findByTestId('preview-frame')) as HTMLIFrameElement
    expect(frame.getAttribute('src')).toBe('https://example.com/page')
    expect(api.proxyFetch).not.toHaveBeenCalled()
  })
})
