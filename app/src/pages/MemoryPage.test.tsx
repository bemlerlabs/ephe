/**
 * R2-A — "What remains" is a page, no longer a strip.
 *
 * The four cases that `SettingsPanel.memory.test.tsx` used to check on the
 * duplicated list live on here: the real document id when deleting, a reload on
 * the real path, metadata on the row, the collection in the header. Added now:
 * the sub-pages, the diagnosis of the two arms and the migration dry run — three
 * things the backend delivers numbers for and no surface used to show.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

vi.mock('react-i18next', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-i18next')>()
  return {
    ...actual,
    useTranslation: () => ({
      t: (k: string, opts?: unknown) => (opts ? `${k} ${JSON.stringify(opts)}` : k),
      i18n: { language: 'de', changeLanguage: vi.fn() },
    }),
  }
})

const api = vi.hoisted(() => ({
  listMemory: vi.fn(),
  searchMemory: vi.fn(),
  listDeletedMemory: vi.fn(async () => ({ entries: [], total: 0 })),
  getMemoryStats: vi.fn(),
  deleteMemoryEntry: vi.fn(async () => ({ deleted: '' })),
  updateMemoryEntry: vi.fn(async () => ({ updated: '' })),
  supersedeMemoryEntry: vi.fn(async () => ({ stored: true, id: '' })),
  restoreMemoryEntry: vi.fn(async () => ({ restored: '' })),
  migrateMemory: vi.fn(),
  setMemoryProvider: vi.fn(async () => ({ provider: 'kepta', reason: '', scope: '' })),
}))

vi.mock('@/lib/api', () => api)
vi.mock('@/lib/toast', () => ({ toastBus: { success: vi.fn(), error: vi.fn() } }))

import MemoryPage from './MemoryPage'

const HIT = {
  id: '7cea238ff07c3120',
  text: 'Der API-Gateway läuft auf Port 8765',
  metadata: { source: 'auto_memory', type: 'semantic', timestamp: 1_790_000_000, hits: 3 },
  score: 0.8123,
}
const SUPERSEDED = {
  id: 'a1b2c3d4',
  text: 'Der Gateway läuft auf Port 8080',
  metadata: { source: 'auto_memory', type: 'semantic', superseded_by: '7cea238ff07c3120' },
}
const CORRECTION = {
  id: '9f8e7d6c',
  text: 'Der Gateway läuft auf Port 8765, nicht 8080',
  metadata: { source: 'auto_memory', type: 'semantic', supersedes: 'a1b2c3d4' },
}
const STATS = {
  total: 7,
  scope: 'ephe_memory_3f2a1b90c4d5',
  provider: 'kepta',
  reason: 'Record aus dem eigenen Bestand',
  vector_leg: true,
  lexical_leg: false,
  deleted: 2,
}

function renderAt(path = '/memory') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/memory" element={<MemoryPage />} />
        <Route path="/memory/:view" element={<MemoryPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.listMemory.mockResolvedValue({ entries: [HIT, SUPERSEDED, CORRECTION], total: 3 })
  api.searchMemory.mockResolvedValue({ results: [HIT] })
  api.getMemoryStats.mockResolvedValue(STATS)
  api.migrateMemory.mockResolvedValue({
    dry_run: true,
    provider_source: 'chroma',
    provider_target: 'kepta',
    source_total: 41,
    source_remaining: 41,
    imported: 0,
    skipped: 3,
    target_total: 0,
    scope: '3f2a1b90c4d5',
    target_path: '/tmp/ephe-test/archiv.db',
  })
})

describe('MemoryPage — Bestand', () => {
  it('listet den Bestand mit seinen echten Metadaten', async () => {
    renderAt()
    const row = await screen.findByTestId('memory-row-0')
    expect(row.textContent).toContain('Der API-Gateway läuft auf Port 8765')
    expect(await screen.findByTestId('memory-page-count')).toHaveTextContent('3')
  })

  it('löscht über die echte Document-ID und lädt auf demselben Pfad neu', async () => {
    renderAt()
    await screen.findByTestId('memory-row-0')
    fireEvent.click(screen.getByTestId('memory-delete-0'))
    await waitFor(() => expect(api.deleteMemoryEntry).toHaveBeenCalledWith(HIT.id))
    await waitFor(() => expect(api.listMemory).toHaveBeenCalledTimes(2))
  })

  it('sucht über die semantische Suche, nicht über ein Filtern der Liste', async () => {
    renderAt()
    const input = await screen.findByLabelText('memory.search')
    fireEvent.change(input, { target: { value: 'gateway' } })
    await waitFor(() => expect(api.searchMemory).toHaveBeenCalledWith('gateway', 200))
  })

  it('zeigt den Papierkorb über dessen Endpunkt, nicht über eine gefilterte Liste', async () => {
    api.listDeletedMemory.mockResolvedValue({
      entries: [{ id: 'gone', text: 'Ein vergessener Fakt', metadata: { deleted_at: 1 } }],
      total: 1,
    } as never)
    renderAt('/memory/papierkorb')
    await waitFor(() => expect(api.listDeletedMemory).toHaveBeenCalled())
    const row = await screen.findByTestId('memory-row-0')
    fireEvent.click(screen.getByTestId('memory-restore-0'))
    await waitFor(() => expect(api.restoreMemoryEntry).toHaveBeenCalledWith('gone'))
    expect(row).toBeTruthy()
  })
})

describe('MemoryPage — Korrekturen', () => {
  it('führt nur Zeilen mit Abstammung, in beide Richtungen', async () => {
    renderAt('/memory/korrekturen')
    const rows = await screen.findAllByTestId(/^memory-row-/)
    // Both carriers of descent are corrections: the new spelling (`supersedes`)
    // and the retired one (`superseded_by`). Leaving out one direction would tell
    // half the story — the third entry has neither.
    expect(rows.length).toBe(2)
    expect(rows[0]?.textContent).toContain('Port 8080')
  })
})

describe('MemoryPage — Papierkorb of a finally-deleting store', () => {
  const FINAL_DETAIL = "the active store 'chroma' deletes finally: nothing is kept to restore."

  it('names the store reason instead of promising a trash that cannot fill', async () => {
    api.listDeletedMemory.mockResolvedValue({
      entries: [],
      total: 0,
      restore_supported: false,
      detail: FINAL_DETAIL,
    } as never)
    renderAt('/memory/papierkorb')
    const empty = await screen.findByTestId('memory-page-empty')
    await waitFor(() => expect(empty.textContent).toBe(FINAL_DETAIL))
    // The promise the page used to make ("where what Ephe forgot ends up") is gone.
    expect(screen.queryByText('memory.emptyTrash')).toBeNull()
  })

  it('offers no restore the store cannot deliver, and no edit on a trash row', async () => {
    api.listDeletedMemory.mockResolvedValue({
      entries: [{ id: 'gone', text: 'Ein vergessener Fakt', metadata: { deleted_at: 1 } }],
      total: 1,
      restore_supported: false,
      detail: FINAL_DETAIL,
    } as never)
    renderAt('/memory/papierkorb')
    await screen.findByTestId('memory-row-0')
    expect(screen.queryByTestId('memory-restore-0')).toBeNull()
    expect(screen.queryByTestId('memory-delete-0')).toBeNull()
    expect(screen.queryByTestId('memory-edit-0')).toBeNull()
  })

  it('keeps the restore control when the store does keep a deleted entry', async () => {
    api.listDeletedMemory.mockResolvedValue({
      entries: [{ id: 'gone', text: 'Ein vergessener Fakt', metadata: { deleted_at: 1 } }],
      total: 1,
      restore_supported: true,
    } as never)
    renderAt('/memory/papierkorb')
    await screen.findByTestId('memory-row-0')
    expect(screen.getByTestId('memory-restore-0')).toBeTruthy()
  })
})

describe('MemoryPage — Gehirne', () => {
  it('benennt Gehirn, Grund und beide Arme — die Zahlen kamen immer schon', async () => {
    renderAt('/memory/gehirne')
    // The value on the wire is spelled differently; the surface says its own word.
    expect(await screen.findByTestId('memory-page-provider')).toHaveTextContent(
      'memory.storeArchive',
    )
    expect(screen.getByTestId('memory-page-provider').textContent).toContain(
      'Record aus dem eigenen Bestand',
    )
    expect(screen.getByTestId('memory-page-scope').textContent).toContain(
      'ephe_memory_3f2a1b90c4d5',
    )
    expect(screen.getByTestId('memory-leg-vector').textContent).toContain('memory.legOn')
    expect(screen.getByTestId('memory-leg-lexical').textContent).toContain('memory.legOff')
  })

  it('rechnet erst die Vorschau, bevor irgendwo etwas umzieht', async () => {
    renderAt('/memory/gehirne')
    const go = await screen.findByTestId('memory-page-dryrun')
    fireEvent.click(go.querySelector('button')!)
    await waitFor(() => expect(api.migrateMemory).toHaveBeenCalledWith(true))
    const report = await screen.findByTestId('memory-migrate-report')
    expect(report.textContent).toContain('41')
    // The dry run only knows the source — it must not invent a moved-count.
    expect(report.textContent).not.toContain('would move')
    expect(report.textContent).toContain('memory.reportTargetHere')
    expect(api.migrateMemory).not.toHaveBeenCalledWith(false)
  })

  it('wechselt das Gehirn nur auf Wunsch', async () => {
    renderAt('/memory/gehirne')
    const row = await screen.findByTestId('memory-page-switch')
    fireEvent.click(row.querySelectorAll('button')[1]!)
    // The button reads "Index"; the value on the wire stays the backend contract.
    expect(row.querySelectorAll('button')[1]?.textContent).toBe('memory.storeIndex')
    await waitFor(() => expect(api.setMemoryProvider).toHaveBeenCalledWith('chroma'))
  })
})
