/**
 * W4 — `/tools` is the surface the vision and session-bundle bindings were
 * missing.
 *
 * Checked: an image upload reaches `analyzeImage`, the base64 field reaches
 * `analyzeImageBase64`, the bundle buttons reach `exportSessionsBundle` /
 * `importSessionsBundle`, and each refusal is shown rather than swallowed.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import axe from 'axe-core'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3', init: () => Promise.resolve() },
  // One shape for every call the page makes: `count` for the import total, and
  // `status` / `message` / `error` for a refusal. Joining the values keeps
  // `tools.imported:3` intact and lets an assertion read what was handed over.
  useTranslation: () => ({
    t: (k: string, opts?: Record<string, unknown>) =>
      opts ? `${k}:${Object.values(opts).join('|')}` : k,
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

const analysis = {
  analysis: 'a lighthouse',
  filename: 'upload_2.png',
  image_url: '/images/upload_2.png',
  model: 'local:7b',
  question: 'q',
}

function pick(input: HTMLElement, file: File) {
  fireEvent.change(input, { target: { files: [file] } })
}

beforeEach(() => {
  vi.clearAllMocks()
  api.analyzeImage.mockResolvedValue(analysis)
  api.analyzeImageBase64.mockResolvedValue(analysis)
  api.exportSessionsBundle.mockResolvedValue(new Uint8Array([80, 75, 3, 4]))
  api.importSessionsBundle.mockResolvedValue({ restored: 3 })
  vi.stubGlobal('URL', {
    ...URL,
    createObjectURL: vi.fn(() => 'blob:test'),
    revokeObjectURL: vi.fn(),
  })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
})
afterEach(() => vi.restoreAllMocks())

describe('ToolsPage (W4)', () => {
  it('analyses a chosen image through analyzeImage and shows the answer', async () => {
    render(<ToolsPage />)
    const file = new File(['png'], 'shot.png', { type: 'image/png' })

    pick(screen.getByTestId('tools-image-input'), file)
    expect(screen.getByTestId('tools-image-name').textContent).toBe('shot.png')

    fireEvent.change(screen.getByTestId('tools-question'), { target: { value: 'What is this?' } })
    fireEvent.click(screen.getByTestId('tools-analyze'))

    await waitFor(() => expect(api.analyzeImage).toHaveBeenCalledWith(file, 'What is this?'))
    expect((await screen.findByTestId('tools-vision-result')).textContent).toContain('a lighthouse')
  })

  it('routes the base64 field through analyzeImageBase64', async () => {
    render(<ToolsPage />)
    fireEvent.change(screen.getByTestId('tools-base64'), { target: { value: 'AAAA' } })
    fireEvent.click(screen.getByTestId('tools-analyze-base64'))

    await waitFor(() => expect(api.analyzeImageBase64).toHaveBeenCalledWith('AAAA', ''))
  })

  it('shows the refusal instead of swallowing it', async () => {
    api.analyzeImage.mockRejectedValueOnce(new Error('unsupported format: text/plain'))
    render(<ToolsPage />)
    pick(screen.getByTestId('tools-image-input'), new File(['x'], 'a.txt', { type: 'text/plain' }))
    fireEvent.click(screen.getByTestId('tools-analyze'))

    expect((await screen.findByTestId('tools-vision-error')).textContent).toContain(
      'unsupported format',
    )
  })

  it('exports the session store and imports a bundle back', async () => {
    render(<ToolsPage />)

    fireEvent.click(screen.getByTestId('tools-export'))
    await waitFor(() => expect(api.exportSessionsBundle).toHaveBeenCalledWith('zip'))

    const bundle = new File([new Uint8Array([80, 75, 3, 4])], 'sessions.zip', {
      type: 'application/zip',
    })
    pick(screen.getByTestId('tools-bundle-input'), bundle)

    await waitFor(() => expect(api.importSessionsBundle).toHaveBeenCalled())
    const call = api.importSessionsBundle.mock.calls[0] as [Uint8Array, string]
    expect(call[1]).toBe('sessions.zip')
    expect((await screen.findByTestId('tools-bundle-result')).textContent).toContain(
      'tools.imported:3',
    )
  })

  // D1: the binding throws `API 400: Bad Request` and reads no body
  // (lib/api/endpoints.ts:214,232), so the page has to turn a transport line into
  // a sentence about the file the user picked.
  it('turns a refused import into a sentence, not the transport line', async () => {
    api.importSessionsBundle.mockRejectedValueOnce(new Error('API 400: Bad Request'))
    render(<ToolsPage />)
    pick(
      screen.getByTestId('tools-bundle-input'),
      new File([new Uint8Array([80, 75, 3, 4])], 'broken.zip', { type: 'application/zip' }),
    )

    const sentence = await screen.findByTestId('tools-bundle-error-text')
    expect(sentence.textContent).toBe('tools.errorImport:HTTP 400')
    // The line itself is kept for a report, one disclosure below the sentence.
    expect(screen.getByTestId('tools-bundle-error-detail').textContent).toContain(
      'API 400: Bad Request',
    )
  })

  it('says nothing was sent when the backend does not answer', async () => {
    api.importSessionsBundle.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    render(<ToolsPage />)
    pick(
      screen.getByTestId('tools-bundle-input'),
      new File([new Uint8Array([80, 75, 3, 4])], 'broken.zip', { type: 'application/zip' }),
    )

    expect((await screen.findByTestId('tools-bundle-error-text')).textContent).toBe(
      'tools.errorOffline',
    )
  })

  it('keeps the engine sentence and adds the next step on a vision refusal', async () => {
    api.analyzeImage.mockRejectedValueOnce(new Error('unsupported format: text/plain'))
    render(<ToolsPage />)
    pick(screen.getByTestId('tools-image-input'), new File(['x'], 'a.txt', { type: 'text/plain' }))
    fireEvent.click(screen.getByTestId('tools-analyze'))

    expect((await screen.findByTestId('tools-vision-error-text')).textContent).toBe(
      'serverError.vision_failed:unsupported format: text/plain',
    )
  })
})

describe('ToolsPage accessibility', () => {
  it('names the question and base64 fields with visible labels', () => {
    render(<ToolsPage />)
    expect(screen.getByLabelText('tools.questionLabel')).toBe(screen.getByTestId('tools-question'))
    expect(screen.getByLabelText('tools.base64Label')).toBe(screen.getByTestId('tools-base64'))
  })

  it('passes the WCAG rules axe checks', async () => {
    const { container } = render(<ToolsPage />)
    const results = await axe.run(container, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] },
    })
    expect(results.violations).toEqual([])
  })
})
