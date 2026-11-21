/**
 * The figures that left the visible status row: they are still one click away in
 * the status popover, with the same numbers and the same hints.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import StatusDetails from './StatusDetails'

vi.mock('@/store/chatStore', () => ({
  useChatStore: (sel: (st: { sessions: unknown[] }) => unknown) =>
    sel({
      sessions: [
        { id: 'a', messages: [] },
        { id: 'b', messages: [] },
      ],
    }),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    fetchIndexStatus: vi.fn(async () => ({
      state: 'idle',
      files: 0,
      symbols: 0,
      indexed: 0,
      total: 0,
    })),
  }
})

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        'statusBar.storage': `${String(opts?.count ?? '')} sessions · ~${String(opts?.mb ?? '')} MB`,
        'statusBar.storageHint': 'Browser cache (IndexedDB)',
        'statusBar.contextFreeOf': `${String(opts?.free ?? '')} free of ${String(opts?.window ?? '')}`,
        'statusBar.contextFree': 'free',
        'statusBar.detailsTitle': 'Usage and storage',
        'status.bpeExact': 'exact BPE',
        'codebase.pillIdle': 'Index codebase',
      }
      return map[key] ?? key
    },
    i18n: { language: 'en' },
  }),
}))

describe('StatusDetails — the raw figures behind the status pill', () => {
  it('states the free-of-window pair and the device footprint', async () => {
    render(<StatusDetails remaining={998_183} window={1_000_000} tokenizer={null} />)
    expect(screen.getByTestId('status-details').textContent).toContain('998,183 free of 1,000,000')
    const chip = screen.getByTestId('statusbar-storage-chip')
    expect(chip.textContent).toMatch(/2 sessions/)
    expect(chip.textContent).toMatch(/\d+(\.\d+)? MB/)
    expect(await screen.findByTestId('codebase-pill')).toBeTruthy()
  })

  it('keeps the tokenizer truth beside the number it qualifies', () => {
    render(<StatusDetails remaining={10} window={100} tokenizer="tiktoken-bpe" />)
    expect(screen.getByText(/·bpe/)).toBeTruthy()
  })
})
