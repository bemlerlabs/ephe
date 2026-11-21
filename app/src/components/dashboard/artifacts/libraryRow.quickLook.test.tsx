import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ArtifactEntry } from '@/lib/api'
import ArtifactLibraryRow from './libraryRow'

const { canUse, look } = vi.hoisted(() => ({
  canUse: vi.fn(() => true),
  look: vi.fn(async () => true),
}))

vi.mock('@/lib/fileActions', () => ({
  canUseNativeFileActions: canUse,
  quickLook: look,
  revealInFinder: vi.fn(async () => true),
  openInDefaultApp: vi.fn(async () => true),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { language: 'en' } }),
}))

vi.mock('@/lib/api', async (importOriginal) => {
  const real = await importOriginal<typeof import('@/lib/api')>()
  return { ...real, favoriteArtifact: vi.fn(), adoptArtifact: vi.fn() }
})

const ART: ArtifactEntry = {
  id: 'art-look',
  root_id: 'art-look',
  version: 1,
  session_id: 's1',
  name: 'dims.py',
  path: '/Users/someone/.ephe/artifacts/s1/dims.py',
  kind: 'file',
  size: 790,
  topic: '',
  created_at: '2026-10-27T12:00:00+00:00',
  favorite: false,
  tags: [],
}

const onSelect = vi.fn()

function row() {
  return (
    <ArtifactLibraryRow
      art={ART}
      selected={false}
      onSelect={onSelect}
      onFavorite={() => {}}
    />
  )
}

beforeEach(() => {
  canUse.mockReturnValue(true)
  look.mockClear()
  onSelect.mockClear()
})
afterEach(cleanup)

describe('N5 — Quick Look from the shelf', () => {
  it('previews through the shell from the eye button', async () => {
    render(row())

    fireEvent.click(screen.getByTestId('artifact-quick-look'))

    await waitFor(() => expect(look).toHaveBeenCalledWith(ART.path))
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('uses the space bar on the focused row instead of selecting it', async () => {
    render(row())
    const select = screen.getByTestId('artifact-select-art-look')

    const event = new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true })
    select.dispatchEvent(event)

    await waitFor(() => expect(look).toHaveBeenCalledWith(ART.path))
    expect(event.defaultPrevented).toBe(true)
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('leaves the space bar to the page in a browser', () => {
    canUse.mockReturnValue(false)
    render(row())
    const select = screen.getByTestId('artifact-select-art-look')

    const event = new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true })
    select.dispatchEvent(event)

    expect(look).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
    expect(screen.queryByTestId('artifact-quick-look')).toBeNull()
  })
})
