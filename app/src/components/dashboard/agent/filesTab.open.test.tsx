/**
 * #111 — a click on a file opens the file, where the file was named.
 *
 * The behaviour this replaces was one line: the row handed `/api/file?path=…` to the
 * browser pane, so a README arrived with an address bar, a PNG arrived with a download,
 * and the column that had just listed the file showed nothing of it. These cases pin the
 * other answer — the tree, the strip, and the body a format can actually hold — and the
 * one gesture that still reaches the browser.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { FilesTab } from './filesTab'
import {
  closeAllWorkspaceFiles,
  openWorkspaceFile,
  showWorkspaceView,
  workspaceFiles,
} from '@/lib/workspaceFiles'

const ENTRIES = [
  { name: 'README.md', type: 'file', size: 18 },
  { name: 'karte.png', type: 'file', size: 2048 },
  { name: 'zahlen.xlsx', type: 'file', size: 4096 },
  { name: 'app.py', type: 'file', size: 4 },
  { name: 'src', type: 'dir' },
] as const

const listFs = vi.fn(async (dir?: string) => ({
  path: dir ?? '/werk',
  parent: null,
  home: '/home',
  workspace: '/werk',
  entries: dir && dir !== '/werk' ? [] : ENTRIES.map((e) => ({ ...e })),
}))
const onOpenFile = vi.fn()

vi.mock('@/lib/api', () => ({
  listFs: (...args: unknown[]) => listFs(...(args as [string | undefined])),
  getSettings: vi.fn(async () => ({ workspace_dir: '/werk' })),
  gitStatus: vi.fn(async () => ({ root: '/werk', changes: [], branch: 'main' })),
  gitDiff: vi.fn(async () => ({ diff: '', path: '', binary: false })),
  gitApplyPatch: vi.fn(async () => ({ ok: true })),
  listChangeSets: vi.fn(async () => ({ change_sets: [] })),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}))

/** The bytes the reader asks for, answered per path so a text and an image case differ. */
function stubFetch(text = '# Titel\n') {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string) => ({
      ok: true,
      status: 200,
      text: async () => text,
      url: String(input),
    })),
  )
}

beforeEach(() => {
  localStorage.clear()
  closeAllWorkspaceFiles()
  listFs.mockClear()
  onOpenFile.mockClear()
  stubFetch()
})

function renderTab() {
  return render(<FilesTab onOpenFile={onOpenFile} />)
}

async function awaitTree() {
  await waitFor(() => expect(screen.getByTestId('files-status')).toBeTruthy())
}

/** The tree is gone as soon as a file shows, so a case that clicked waits on the reader. */
async function awaitFile(name: string) {
  expect(await screen.findByTestId(`workspace-file-tab-${name}`)).toBeTruthy()
}

describe('a row click', () => {
  it('opens the file in the column and leaves the browser pane alone', async () => {
    renderTab()
    await awaitTree()
    fireEvent.click(screen.getByText('README.md'))
    await awaitFile('README.md')

    expect(onOpenFile).not.toHaveBeenCalled()
    expect(workspaceFiles().view).toBe('file')
    // The line names the folder the file came from — the address would name nothing.
    expect(screen.getByTestId('workspace-file-path').textContent).toBe('/werk')
    const tab = within(screen.getByTestId('workspace-file-tab-README.md')).getByRole('tab')
    expect(tab.getAttribute('aria-selected')).toBe('true')
  })

  it('names the folder the file came from, not an address', async () => {
    renderTab()
    await awaitTree()
    fireEvent.click(screen.getByText('app.py'))
    const path = await screen.findByTestId('workspace-file-path')
    expect(path.getAttribute('title')).toBe('/werk/app.py')
  })

  it('keeps a tab from the strip, where the second click can still land', async () => {
    renderTab()
    await awaitTree()
    fireEvent.click(screen.getByText('README.md'))
    // The row is gone as soon as the file shows, so a double click on the tree cannot
    // pin anything — measured in a real browser. The tab and the reader line carry it.
    fireEvent.doubleClick(
      within(screen.getByTestId('workspace-file-tab-README.md')).getByRole('tab'),
    )
    expect(workspaceFiles().files[0]?.pinned).toBe(true)
    expect(screen.getByTestId('workspace-file-tab-README.md').getAttribute('data-pinned')).toBe(
      'true',
    )

    fireEvent.click(await screen.findByTestId('workspace-files-toggle'))
    await waitFor(() => expect(screen.getByText('app.py')).toBeTruthy())
    fireEvent.click(screen.getByText('app.py'))
    // The kept file stayed, and the new one opened in the slot beside it.
    expect(workspaceFiles().files.map((f) => f.name)).toEqual(['README.md', 'app.py'])
  })

  it('releases the tab from the reader line, and the strip says so', async () => {
    openWorkspaceFile({ path: '/werk/a.md', name: 'a.md', pin: true })
    showWorkspaceView('tree')
    renderTab()
    await awaitTree()
    fireEvent.click(screen.getByText('README.md'))
    const pin = await screen.findByTestId('workspace-file-pin')
    expect(pin.getAttribute('aria-pressed')).toBe('false')
    fireEvent.click(pin)
    expect(workspaceFiles().files.find((f) => f.name === 'README.md')?.pinned).toBe(true)
    expect(pin.getAttribute('aria-pressed')).toBe('true')
  })

  it('shows an image as the image, after asking for its bytes once', async () => {
    renderTab()
    await awaitTree()
    fireEvent.click(screen.getByText('karte.png'))
    const img = await screen.findByTestId('workspace-file-image')
    expect(img.getAttribute('src')).toContain('/api/file?path=%2Fwerk%2Fkarte.png')
    expect(img.getAttribute('alt')).toBe('karte.png')
  })

  it('says what a spreadsheet is when the column cannot draw it', async () => {
    renderTab()
    await awaitTree()
    fireEvent.click(screen.getByText('zahlen.xlsx'))
    const held = await screen.findByTestId('workspace-file-held')
    expect(held.getAttribute('data-reason')).toBe('packed')
    expect(held.textContent).toContain('agentPanel.filePackedNote')
    // The size travels as a number: the words around it belong to the locale.
    expect(held.getAttribute('data-size')).toBe('4096')
    expect(within(held).getByRole('button').textContent).toContain('agentPanel.openInPreview')
  })

  it('empties the strip in one gesture and leaves the folder on screen', async () => {
    renderTab()
    await awaitTree()
    fireEvent.click(screen.getByText('README.md'))
    fireEvent.click(await screen.findByTestId('workspace-file-close-all'))
    expect(workspaceFiles().files).toEqual([])
    expect(workspaceFiles().view).toBe('tree')
    await waitFor(() => expect(screen.getByText('karte.png')).toBeTruthy())
  })
})

describe('the reader line', () => {
  it('hands the browser pane the same file when asked', async () => {
    renderTab()
    await awaitTree()
    fireEvent.click(screen.getByText('README.md'))
    fireEvent.click(await screen.findByTestId('workspace-file-open-browser'))
    expect(onOpenFile).toHaveBeenCalledWith('/api/file?path=%2Fwerk%2FREADME.md')
  })

  it('gives a Markdown file the choice of page and source, and nothing else the offer', async () => {
    renderTab()
    await awaitTree()
    fireEvent.click(screen.getByText('README.md'))
    expect(await screen.findByTestId('workspace-file-view-source')).toBeTruthy()
    expect(screen.getByTestId('workspace-file-view-rendered').getAttribute('aria-pressed')).toBe(
      'true',
    )

    fireEvent.click(await screen.findByTestId('workspace-files-toggle'))
    await waitFor(() => expect(screen.getByText('app.py')).toBeTruthy())
    fireEvent.click(screen.getByText('app.py'))
    await waitFor(() => expect(screen.queryByTestId('workspace-file-view-source')).toBeNull())
  })

  it('reads the page view as Markdown and the source view as its text', async () => {
    stubFetch('# Überschrift\n')
    renderTab()
    await awaitTree()
    fireEvent.click(screen.getByText('README.md'))
    const body = await screen.findByTestId('file-preview-body')
    expect(body.getAttribute('data-kind')).toBe('markdown')

    fireEvent.click(screen.getByTestId('workspace-file-view-source'))
    const source = await screen.findByTestId('file-preview-body')
    expect(source.getAttribute('data-kind')).toBe('code')
  })

  it('returns to the folder without closing the file', async () => {
    renderTab()
    await awaitTree()
    fireEvent.click(screen.getByText('README.md'))
    fireEvent.click(await screen.findByTestId('workspace-files-toggle'))
    expect(workspaceFiles().view).toBe('tree')
    expect(workspaceFiles().active).toBe('/werk/README.md')
    // The tree is back on screen: the entries are reachable again.
    await waitFor(() => expect(screen.getByText('karte.png')).toBeTruthy())
  })

  it('closes one tab and brings its neighbour forward', async () => {
    openWorkspaceFile({ path: '/werk/a.md', name: 'a.md', pin: true })
    showWorkspaceView('tree')
    renderTab()
    await awaitTree()
    fireEvent.click(screen.getByText('README.md'))
    fireEvent.click(await screen.findByTestId('workspace-file-tab-close-README.md'))

    expect(workspaceFiles().files.map((f) => f.name)).toEqual(['a.md'])
    // The closed file was in front, so the one that stayed is the one on screen.
    expect(workspaceFiles().active).toBe('/werk/a.md')
    expect(workspaceFiles().view).toBe('file')
  })
})

describe('the column without an open file', () => {
  it('shows no strip and the tree, so the first read stays the folder', async () => {
    renderTab()
    await awaitTree()
    expect(screen.queryByRole('tablist')).toBeNull()
    expect(screen.getByText('README.md')).toBeTruthy()
  })
})
