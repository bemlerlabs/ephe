/**
 * The preview tab at desktop width — the 24px floor and one glyph size per row.
 *
 * jsdom measures no layout, so what is held here is the class contract the
 * breakpoints encode. The measured defects at 1440px were the address bar
 * (251x15) and the recent-file pills (~20px tall): both now reach 24px on the
 * control itself. The two glyph rows are pinned to one size each — the toolbar
 * row is 16px, the overflow menu is 14px (the inline tier).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const api = vi.hoisted(() => ({ LAN_TOKEN: null as string | null, proxyFetch: vi.fn() }))

vi.mock('@/lib/api', () => api)
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))

import { PreviewTab } from './previewTab'

const tokens = (el: Element | null): string[] => (el?.getAttribute('class') ?? '').split(/\s+/)
const has = (el: Element | null, token: string): boolean => tokens(el).includes(token)

function renderPreview(recent: string[] = []) {
  return render(
    <PreviewTab
      url="http://localhost:5173/"
      draft="http://localhost:5173/"
      nonce={0}
      inputRef={{ current: null }}
      setDraft={() => {}}
      recent={recent}
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
  api.proxyFetch = vi.fn(async () => ({ ok: true, status: 200, body: '', url: '' }))
})

describe('the preview tab at desktop width — the 24px floor', () => {
  it('the address bar reaches 24px', () => {
    renderPreview()
    const input = screen.getByTestId('preview-url-input')
    expect(has(input, 'min-h-6'), 'address bar 24px height').toBe(true)
  })

  it('the recent-file pills reach 24px', () => {
    renderPreview(['http://localhost:5173/a', 'http://localhost:5173/b'])
    const pill = screen.getByTestId('preview-recent-0')
    expect(has(pill, 'min-h-6'), 'recent pill 24px height').toBe(true)
  })

  it('the toolbar buttons reach 24px', () => {
    renderPreview()
    for (const id of ['preview-back', 'preview-forward', 'preview-reload', 'preview-overflow']) {
      const btn = screen.getByTestId(id)
      // 16px glyph + 6px padding on each side = 28px, above the floor.
      expect(has(btn, 'p-1.5'), `${id} padding`).toBe(true)
      expect(btn.querySelector('svg'), `${id} glyph`).not.toBeNull()
    }
  })
})

describe('the preview tab at desktop width — one glyph size per row', () => {
  it('the toolbar row is a single 16px glyph size', () => {
    renderPreview()
    const sizes = new Set<string>()
    for (const id of ['preview-back', 'preview-forward', 'preview-reload', 'preview-overflow']) {
      const glyph = screen.getByTestId(id).querySelector('svg')!
      expect(has(glyph, 'h-4') && has(glyph, 'w-4'), `${id} 16px glyph`).toBe(true)
      sizes.add(
        tokens(glyph)
          .filter((t) => t === 'h-4' || t === 'h-3.5' || t === 'h-3')
          .join(),
      )
    }
    expect(sizes.size, 'one glyph size in the toolbar row').toBe(1)
  })

  it('the overflow menu is a single 14px inline glyph size', () => {
    renderPreview()
    fireEvent.click(screen.getByTestId('preview-overflow'))
    const rows = screen.getAllByRole('menuitem')
    expect(rows.length).toBeGreaterThanOrEqual(2)
    const sizes = new Set<string>()
    for (const row of rows) {
      const glyph = row.querySelector('svg')!
      expect(has(glyph, 'h-3.5') && has(glyph, 'w-3.5'), '14px inline glyph').toBe(true)
      sizes.add(
        tokens(glyph)
          .filter((t) => t === 'h-3.5' || t === 'h-3')
          .join(),
      )
    }
    expect(sizes.size, 'one glyph size in the menu row').toBe(1)
  })
})
