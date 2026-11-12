/**
 * The offer is dismissed as easily as it is accepted, and it never downloads by
 * itself — the first start must not pull 542 MB nobody asked for.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import EmbeddingModelPrompt from './EmbeddingModelPrompt'
import * as model from '@/lib/embeddingModel'

// A translator that keeps the interpolated values visible: the assertions are about
// what a person reads, and the real bundles are not loaded in this test.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key} ${Object.values(options).join(' ')}` : key,
  }),
}))

vi.mock('@/lib/embeddingModel', async () => {
  const real = await vi.importActual<typeof import('@/lib/embeddingModel')>('@/lib/embeddingModel')
  return { ...real, readEmbeddingModel: vi.fn(), startEmbeddingDownload: vi.fn() }
})

const status = (over: Partial<model.EmbeddingModelStatus> = {}): model.EmbeddingModelStatus => ({
  label: 'embeddinggemma-2',
  present: false,
  missing: ['onnx/model_fp16.onnx_data'],
  sizeMb: 542,
  host: 'huggingface.co',
  repo: 'onnx-community/embeddinggemma-2-ONNX',
  consent: false,
  offline: false,
  downloading: false,
  downloaded: false,
  error: '',
  reembed: {
    running: false,
    done: false,
    total: 0,
    embedded: 0,
    remaining: 0,
    label: '',
    error: '',
  },
  ...over,
})

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  vi.mocked(model.readEmbeddingModel).mockResolvedValue(status())
  vi.mocked(model.startEmbeddingDownload).mockResolvedValue(true)
})

describe('embedding model offer', () => {
  it('offers the fetch and names the size and the missing file', async () => {
    render(<EmbeddingModelPrompt />)
    const card = await screen.findByTestId('embedding-model-prompt')
    expect(card.textContent).toContain('542 MB')
    expect(card.textContent).toContain('model_fp16.onnx_data')
    expect(model.startEmbeddingDownload).not.toHaveBeenCalled()
  })

  it('starts one fetch when the button is pressed', async () => {
    render(<EmbeddingModelPrompt />)
    fireEvent.click(await screen.findByTestId('embedding-model-download'))
    await waitFor(() => expect(model.startEmbeddingDownload).toHaveBeenCalledTimes(1))
  })

  it('"Not now" hides the offer and remembers it', async () => {
    render(<EmbeddingModelPrompt />)
    fireEvent.click(await screen.findByTestId('embedding-model-dismiss'))
    expect(screen.queryByTestId('embedding-model-prompt')).toBeNull()
    expect(model.recentlyDismissed()).toBe(true)
  })

  it('says nothing when the model is already loadable', async () => {
    vi.mocked(model.readEmbeddingModel).mockResolvedValue(status({ present: true, missing: [] }))
    render(<EmbeddingModelPrompt />)
    await waitFor(() => expect(model.readEmbeddingModel).toHaveBeenCalled())
    expect(screen.queryByTestId('embedding-model-prompt')).toBeNull()
  })

  it('stays quiet while a dismissal is fresh', async () => {
    model.dismissOffer()
    render(<EmbeddingModelPrompt />)
    await waitFor(() => expect(model.readEmbeddingModel).not.toHaveBeenCalled())
    expect(screen.queryByTestId('embedding-model-prompt')).toBeNull()
  })

  it('stays visible and names the reason when the fetch failed', async () => {
    vi.mocked(model.readEmbeddingModel).mockResolvedValue(status({ error: 'the hub answered 503' }))
    render(<EmbeddingModelPrompt />)
    const card = await screen.findByTestId('embedding-model-prompt')
    expect(card.textContent).toContain('the hub answered 503')
    expect(screen.getByTestId('embedding-model-download')).toBeTruthy()
  })

  it('keeps the offer when the route refuses to start', async () => {
    vi.mocked(model.startEmbeddingDownload).mockResolvedValue(false)
    render(<EmbeddingModelPrompt />)
    fireEvent.click(await screen.findByTestId('embedding-model-download'))
    await waitFor(() => expect(model.startEmbeddingDownload).toHaveBeenCalledTimes(1))
    const card = await screen.findByTestId('embedding-model-prompt')
    expect(card.textContent).toContain('chat.model.embeddingStartFailed')
    expect(model.recentlyDismissed()).toBe(false)
  })
})
