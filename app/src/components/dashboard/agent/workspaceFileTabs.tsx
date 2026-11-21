'use client'

import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { X } from 'lucide-react'
import {
  closeAllWorkspaceFiles,
  closeWorkspaceFile,
  selectWorkspaceFile,
  setWorkspaceFilePinned,
  showWorkspaceView,
  useWorkspaceFiles,
} from '@/lib/workspaceFiles'

/**
 * Ephe — the strip of files the workspace column holds (#111).
 *
 * One row, three jobs: back to the folder, the files themselves, and closing all of them.
 * The preview slot is drawn in italics and stays in the row, so what a person is about to
 * lose by a single click is visible before the click — the part an editor gets right and a
 * list of closed tabs cannot be recovered from afterwards.
 */

const STRIP_BUTTON =
  'inline-grid place-items-center p-1 min-h-6 rounded text-ink-faint hover:text-foreground hover:bg-surface-raised transition-colors shrink-0 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2'

export function WorkspaceFileTabs() {
  const { t } = useTranslation()
  const { files, active, view } = useWorkspaceFiles()
  const barRef = useRef<HTMLDivElement>(null)
  const restoreFocus = useRef(false)

  // Closing a pill removes the element that held the focus, so it goes back to a tab
  // that is still there rather than to the page behind the panel.
  useEffect(() => {
    if (!restoreFocus.current) return
    restoreFocus.current = false
    barRef.current?.querySelector<HTMLElement>('[role="tab"]')?.focus()
  }, [files])

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return
    const nodes = Array.from(barRef.current?.querySelectorAll<HTMLElement>('[role="tab"]') ?? [])
    if (!nodes.length) return
    const current = nodes.indexOf(e.target as HTMLElement)
    if (current < 0) return
    // The pane's own bar listens for the same arrows; without stopping here, one press
    // moves the file tab and the pane tab at once.
    e.preventDefault()
    e.stopPropagation()
    const index =
      e.key === 'Home'
        ? 0
        : e.key === 'End'
          ? nodes.length - 1
          : (current + (e.key === 'ArrowRight' ? 1 : -1) + nodes.length) % nodes.length
    const file = files[index]
    if (file) selectWorkspaceFile(file.path)
    nodes[index]?.focus()
  }

  if (!files.length) return null

  return (
    <div className="@container flex flex-nowrap items-center gap-1 border-b border-hairline bg-surface/60 px-2 py-1">
      <button
        type="button"
        data-testid="workspace-files-toggle"
        aria-pressed={view === 'tree'}
        onClick={() => showWorkspaceView('tree')}
        title={t('agentPanel.fileBackToTree')}
        className={`shrink-0 rounded-md px-2 py-1 text-ui-2xs font-medium transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 ${
          view === 'tree'
            ? 'bg-surface-raised text-foreground'
            : 'text-ink-faint hover:bg-surface-raised hover:text-foreground'
        }`}
      >
        {t('agentPanel.tabFiles')}
      </button>
      <div
        ref={barRef}
        role="tablist"
        aria-label={t('agentPanel.fileTabsLabel')}
        onKeyDown={onKeyDown}
        className="flex min-w-0 flex-1 flex-nowrap items-center gap-1 overflow-x-auto"
      >
        {files.map((file) => {
          const isActive = file.path === active
          return (
            <div
              key={file.path}
              data-testid={`workspace-file-tab-${file.name}`}
              data-pinned={file.pinned ? 'true' : 'false'}
              className={`flex shrink-0 items-center rounded-md border transition-colors ${
                isActive
                  ? // The same accent the pane's own pills use, so the two rows of tabs
                    // in one column do not speak two languages.
                    'border-hairline bg-brand/20'
                  : 'border-transparent hover:bg-surface-raised'
              }`}
            >
              <button
                type="button"
                role="tab"
                data-file={file.path}
                aria-selected={isActive}
                tabIndex={isActive ? 0 : -1}
                title={file.pinned ? file.path : `${file.path}\n${t('agentPanel.fileSlotHint')}`}
                onClick={() => selectWorkspaceFile(file.path)}
                onDoubleClick={() => setWorkspaceFilePinned(file.path, true)}
                className={`max-w-[11rem] truncate rounded-l-md px-2 py-1 text-ui-2xs transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 ${
                  isActive ? 'text-brand' : 'text-ink-faint hover:text-foreground'
                } ${file.pinned ? '' : 'italic'}`}
              >
                {file.name}
              </button>
              <button
                type="button"
                data-testid={`workspace-file-tab-close-${file.name}`}
                onClick={() => {
                  restoreFocus.current = true
                  closeWorkspaceFile(file.path)
                }}
                aria-label={t('agentPanel.fileTabClose', { name: file.name })}
                title={t('agentPanel.fileTabClose', { name: file.name })}
                className="grid shrink-0 place-items-center rounded-r-md p-1 text-ink-faint transition-colors hover:text-foreground focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            </div>
          )
        })}
      </div>
      <button
        type="button"
        data-testid="workspace-file-close-all"
        onClick={closeAllWorkspaceFiles}
        aria-label={t('agentPanel.fileCloseAll')}
        title={t('agentPanel.fileCloseAll')}
        className={STRIP_BUTTON}
      >
        <X className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </div>
  )
}
