/**
 * WD-30 — the tools page's finish (visual pass).
 *
 * The page carried the only two `text-lg` card titles in `app/src`, so its
 * headings sat off the coupled `text-ui-*` scale and ignored the Appearance
 * font-size lever every other surface moves with. An answer landed as a bare
 * paragraph on the card, with nothing separating the prose from the controls
 * above it; a refusal and a restore confirmation carried no live role; and the
 * chosen filename could push the pick row. This file holds the page on the
 * treatments the rest of the app already uses: one reading surface for the
 * answer, an assertive role for failures, a polite one for confirmations.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (k: string, opts?: { count?: number }) =>
      opts && typeof opts.count === 'number' ? `${k}:${opts.count}` : k,
  }),
}))

const api = vi.hoisted(() => ({
  analyzeImage: vi.fn(),
  analyzeImageBase64: vi.fn(),
  exportSessionsBundle: vi.fn(),
  importSessionsBundle: vi.fn(),
}))
vi.mock('@/lib/api', () => api)

import ToolsPage from './ToolsPage'

// Read from the config root, as ArtifactsPage.finish.test.tsx does — jsdom hands
// out a non-file import.meta.url, so the URL form would not resolve.
const SRC = readFileSync('src/pages/ToolsPage.tsx', 'utf-8')

const analysis = {
  analysis: 'a lighthouse',
  filename: 'upload_2.png',
  image_url: '/images/upload_2.png',
  model: 'local:7b',
  question: 'q',
}

beforeEach(() => {
  vi.clearAllMocks()
  api.analyzeImage.mockResolvedValue(analysis)
  api.analyzeImageBase64.mockResolvedValue(analysis)
  api.importSessionsBundle.mockResolvedValue({ restored: 3 })
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn(() => 'blob:test'),
    revokeObjectURL: vi.fn(),
  })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('WD-30 — the tools page keeps one type scale', () => {
  it('carries no off-scale heading size', () => {
    expect(SRC).not.toContain('text-lg')
    expect(SRC).toContain('font-display text-ui-lg')
  })
})

describe('WD-30 — the reading surface and the state roles', () => {
  it('puts the answer on a reading surface and announces it politely', async () => {
    render(<ToolsPage />)
    fireEvent.change(screen.getByTestId('tools-image-input'), {
      target: { files: [new File(['png'], 'shot.png', { type: 'image/png' })] },
    })
    fireEvent.click(screen.getByTestId('tools-analyze'))

    const result = await screen.findByTestId('tools-vision-result')
    expect(result.className).toContain('glass-reading')
    expect(result.getAttribute('role')).toBe('status')
    expect(result.textContent).toContain('a lighthouse')
  })

  it('announces a refusal with the alert role', async () => {
    api.analyzeImage.mockRejectedValueOnce(new Error('unsupported format: text/plain'))
    render(<ToolsPage />)
    fireEvent.change(screen.getByTestId('tools-image-input'), {
      target: { files: [new File(['x'], 'a.txt', { type: 'text/plain' })] },
    })
    fireEvent.click(screen.getByTestId('tools-analyze'))

    const error = await screen.findByTestId('tools-vision-error')
    expect(error.getAttribute('role')).toBe('alert')
  })

  it('announces a restore confirmation politely', async () => {
    api.exportSessionsBundle.mockResolvedValue(new Uint8Array([80, 75, 3, 4]))
    render(<ToolsPage />)
    fireEvent.change(screen.getByTestId('tools-bundle-input'), {
      target: {
        files: [
          new File([new Uint8Array([80, 75, 3, 4])], 'sessions.zip', { type: 'application/zip' }),
        ],
      },
    })

    const result = await screen.findByTestId('tools-bundle-result')
    expect(result.getAttribute('role')).toBe('status')
  })
})

describe('WD-30 — the frame around the pick row', () => {
  it('lets a long filename truncate instead of pushing the row', async () => {
    render(<ToolsPage />)
    fireEvent.change(screen.getByTestId('tools-image-input'), {
      target: {
        files: [
          new File(['png'], 'a-very-long-capture-name-2026-10-11.png', { type: 'image/png' }),
        ],
      },
    })
    await waitFor(() =>
      expect(screen.getByTestId('tools-image-name').textContent).toBe(
        'a-very-long-capture-name-2026-10-11.png',
      ),
    )
    expect(screen.getByTestId('tools-image-name').className).toContain('truncate')
  })

  it('divides the two input paths with the hairline token, not a local opacity', () => {
    expect(SRC).not.toContain('border-border/40')
    expect(SRC).toContain('border-t border-hairline')
  })
})
