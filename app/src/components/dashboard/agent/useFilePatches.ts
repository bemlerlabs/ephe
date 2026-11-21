'use client'

import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { askConfirm } from '@/lib/confirmAction'
import { gitDiff, gitApplyPatch } from '@/lib/api'
import type { GitDiffResponse } from '@/lib/api'
import { toastBus } from '@/lib/toast'

/**
 * Ephe — the git gestures one file row offers (#111).
 *
 * The tree lists a workspace; these three things act on a repository: read a file's patch,
 * reverse it, and remember which file is open in a diff. They live apart because they are
 * the part that must answer for a write — the same endpoint `DiffView` discards hunks
 * through, so no second write path appears beside it — and because a tree that also owns
 * the patch cache stops being readable at the width the pane gives it.
 */
export function useFilePatches(refresh: () => Promise<void> | void) {
  const { t } = useTranslation()
  const [patches, setPatches] = useState<Record<string, GitDiffResponse>>({})
  const [diffFor, setDiffFor] = useState('')
  const [busy, setBusy] = useState('')

  const toggleDiff = useCallback(
    async (rel: string) => {
      if (diffFor === rel) {
        setDiffFor('')
        return
      }
      setDiffFor(rel)
      if (patches[rel]) return
      try {
        const patch = await gitDiff(rel)
        setPatches((prev) => ({ ...prev, [rel]: patch }))
      } catch {
        setDiffFor('')
        toastBus.error(t('agentPanel.diffFailed'))
      }
    },
    [diffFor, patches, t],
  )

  const revertFile = useCallback(
    async (rel: string) => {
      if (
        !(await askConfirm({
          title: t('agentPanel.revertConfirm'),
          action: t('common.actions.fileRevert'),
        }))
      )
        return
      setBusy(rel)
      try {
        const patch = patches[rel] ?? (await gitDiff(rel))
        if (patch.binary || !patch.diff) {
          toastBus.error(t('agentPanel.revertFailed'))
          return
        }
        // Reversing the file's own patch is the working-tree revert.
        await gitApplyPatch(patch.diff, { reverse: true })
        toastBus.success(t('agentPanel.revertDone', { path: rel }))
        setPatches((prev) => {
          const next = { ...prev }
          delete next[rel]
          return next
        })
        setDiffFor('')
        await refresh()
      } catch {
        toastBus.error(t('agentPanel.revertFailed'))
      } finally {
        setBusy('')
      }
    },
    [patches, refresh, t],
  )

  return { patches, diffFor, busy, toggleDiff, revertFile }
}
