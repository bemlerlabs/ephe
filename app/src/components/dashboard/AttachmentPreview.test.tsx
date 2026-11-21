/**
 * S21: the composer shows what is attached, not a 20 px chip.
 *
 * GIVEN  image, text and binary attachments, plus one still loading and one
 *        that could not be read
 * WHEN   the preview renders
 * THEN   images carry a thumbnail that opens a dialog (Escape closes it, focus
 *        returns), every card names the file and its size, removal names the
 *        file, and the strip passes axe.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import axe from 'axe-core'
import i18n from '@/i18n'
import AttachmentPreview from './AttachmentPreview'
import type { ChatAttachment } from '@/lib/attachments'

const image: ChatAttachment = {
  kind: 'image',
  path: '/tmp/shot.png',
  name: 'shot.png',
  size: 2048,
  status: 'ready',
  dataUrl: 'data:image/png;base64,AAAA',
}

const text: ChatAttachment = {
  kind: 'text',
  path: '/tmp/notes.md',
  name: 'notes.md',
  size: 512,
  status: 'ready',
  text: '# notes',
  truncated: false,
}

const binary: ChatAttachment = {
  kind: 'file',
  path: '/tmp/archive.zip',
  name: 'archive.zip',
  size: 1048576,
  status: 'ready',
}

const loading: ChatAttachment = {
  kind: 'file',
  path: '/tmp/big.bin',
  name: 'big.bin',
  size: 4096,
  status: 'loading',
}

const broken: ChatAttachment = {
  kind: 'file',
  path: '/tmp/locked.bin',
  name: 'locked.bin',
  size: 10,
  status: 'error',
}

afterEach(cleanup)

describe('AttachmentPreview', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('en')
  })

  it('shows a thumbnail, the name, the size and a named remove button', () => {
    const onRemove = vi.fn()
    render(<AttachmentPreview attachments={[image]} onRemove={onRemove} />)

    expect(screen.getByTestId('attachment-thumb')).toBeInTheDocument()
    expect(screen.getByText('shot.png')).toBeInTheDocument()
    expect(screen.getByText('2.0 KB')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('Remove shot.png'))
    expect(onRemove).toHaveBeenCalledWith(0)
  })

  it('opens the image in a dialog and closes it with Escape', () => {
    render(<AttachmentPreview attachments={[image]} onRemove={() => {}} />)
    const trigger = screen.getByTestId('attachment-thumb')
    trigger.focus()
    fireEvent.click(trigger)

    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByAltText('shot.png')).toBeInTheDocument()
    expect(document.activeElement).toBe(screen.getByLabelText('Close preview'))

    fireEvent.keyDown(document, { key: 'Escape' })

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(document.activeElement).toBe(trigger)
  })

  it('names text and binary files with their size', () => {
    render(<AttachmentPreview attachments={[text, binary]} onRemove={() => {}} />)

    expect(screen.getByText('notes.md')).toBeInTheDocument()
    expect(screen.getByText('512 B')).toBeInTheDocument()
    expect(screen.getByText('archive.zip')).toBeInTheDocument()
    expect(screen.getByText('1.0 MB')).toBeInTheDocument()
    expect(screen.getByLabelText('Remove archive.zip')).toBeInTheDocument()
  })

  it('reports a file it is reading and one it could not read', () => {
    render(<AttachmentPreview attachments={[loading, broken]} onRemove={() => {}} />)

    expect(screen.getByText('big.bin')).toBeInTheDocument()
    expect(screen.getByText('Reading big.bin…')).toBeInTheDocument()
    expect(screen.getByText('locked.bin could not be read')).toBeInTheDocument()
    expect(screen.getByText('locked.bin').closest('li')).toHaveAttribute(
      'data-state',
      'error',
    )
  })

  it('has no axe violations', async () => {
    const { container } = render(
      <AttachmentPreview attachments={[image, text, binary]} onRemove={() => {}} />,
    )

    const results = await axe.run(container)

    expect(results.violations).toEqual([])
  })
})
