/**
 * A deck in the chat.
 *
 * No browser renders .pptx, so the card asks the server and shows what the
 * slides carry: the number, the title and the body lines, in file order.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import type { ArtifactEntry } from '@/lib/api'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'de' } }),
}))

const preview = vi.fn()
vi.mock('@/lib/api', async (io) => ({
  ...(await io<typeof import('@/lib/api')>()),
  artifactPreview: (...args: unknown[]) => preview(...args),
}))

const { default: ArtifactPreviewPane } = await import('./preview')

const deck = {
  id: 'd1',
  root_id: 'd1',
  version: 1,
  session_id: 's1',
  name: 'review.pptx',
  path: '/home/x/.ephe/artifacts/s1/review.pptx',
  kind: 'pptx',
  size: 4096,
  topic: '',
  created_at: '2026-10-06T09:00:00+00:00',
  favorite: false,
  tags: [],
} as ArtifactEntry

afterEach(() => {
  cleanup()
  preview.mockReset()
})

describe('deck preview', () => {
  it('names a deck as content, so the server is asked', async () => {
    preview.mockResolvedValue({ mode: 'none', reason: 'no-text-preview' })
    render(<ArtifactPreviewPane art={deck} />)
    expect(preview).toHaveBeenCalledWith('d1')
    expect(document.querySelector('iframe')).toBeNull()
    expect(screen.queryByTestId('artifact-preview-slides')).toBeNull()
  })

  it('renders every slide with its title and lines', async () => {
    preview.mockResolvedValue({
      mode: 'slides',
      count: 2,
      slides: [
        { title: 'Quarterly review', lines: ['Revenue up', 'Churn flat'] },
        { title: 'Next steps', lines: ['Hire two'] },
      ],
    })
    render(<ArtifactPreviewPane art={deck} />)
    const box = await screen.findByTestId('artifact-preview-slides')
    expect(box.textContent).toContain('Quarterly review')
    expect(box.textContent).toContain('Revenue up')
    expect(box.textContent).toContain('Next steps')
    expect(box.textContent).toContain('02')
  })
})
