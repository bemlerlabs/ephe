/**
 * W19 F3 — workspace dialog: Desktop quick-pick + "New folder".
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import FolderPickerDialog from './FolderPickerDialog'

const listFs = vi.fn()
const createWorkspaceFolder = vi.fn()

vi.mock('@/lib/api', () => ({
  listFs: (...a: unknown[]) => listFs(...(a as [])),
  createWorkspaceFolder: (...a: unknown[]) => createWorkspaceFolder(...(a as [])),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

const listing = (path: string) => ({
  path,
  parent: '/home',
  home: '/home',
  workspace: null,
  entries: [{ name: 'Projekte', type: 'dir' as const }],
})

beforeEach(() => {
  listFs.mockReset().mockResolvedValue(listing('/home'))
  createWorkspaceFolder.mockReset().mockResolvedValue({ path: '/home/Desktop/Neu', created: true })
})

function openDialog() {
  return render(<FolderPickerDialog open onClose={vi.fn()} onPick={vi.fn()} />)
}

describe('FolderPickerDialog — W19 F3', () => {
  it('Desktop-Schnellwahl lädt ~/Desktop statt Browse-Pfad', async () => {
    openDialog()
    await screen.findByText('Projekte')
    fireEvent.click(screen.getByTestId('folder-quick-desktop'))
    await waitFor(() => expect(listFs).toHaveBeenLastCalledWith('~/Desktop'))
  })

  it('„Neuer Ordner“ legt im aktuellen Ordner an und wechselt hinein', async () => {
    listFs.mockResolvedValueOnce(listing('/home/Desktop'))
    openDialog()
    await screen.findByText('Projekte')
    fireEvent.change(screen.getByTestId('folder-new-input'), { target: { value: 'Neu' } })
    fireEvent.click(screen.getByTestId('folder-new-create'))
    await waitFor(() => expect(createWorkspaceFolder).toBeCalledWith('/home/Desktop', 'Neu'))
    await waitFor(() => expect(listFs).toHaveBeenLastCalledWith('/home/Desktop/Neu'))
  })

  it('Create-Button ist ohne Namen disabled', async () => {
    openDialog()
    await screen.findByText('Projekte')
    expect((screen.getByTestId('folder-new-create') as HTMLButtonElement).disabled).toBe(true)
  })
})
