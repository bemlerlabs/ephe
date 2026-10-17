import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import type { Session } from '@/types'
import { classifyToolCall } from '@/lib/toolCardModel'
import { fileUrl } from '@/lib/api'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { toastBus } from '@/lib/toast'
import { isWindowFocused } from '@/hooks/useWindowFocused'

/**
 * #93 (docs/AGENT_PANEL_CONDUCT_2026-10-11.md): a file that lands while the user is
 * looking at another window gets a notice with a way in. The pane itself never
 * moves on its own — where this window has the focus, the message the turn left
 * behind is already the notice, and its card carries open, adopt and download.
 *
 * Only NEW files of the ACTIVE session count: on a session switch everything is
 * marked as seen, so a reload or a jump through history says nothing.
 */
export function useArtifactNotice(currentSession: Session | null | undefined) {
  const seenRef = useRef<Set<string>>(new Set())
  const sessionRef = useRef<string | undefined>(undefined)
  const { t } = useTranslation()

  useEffect(() => {
    const notice = (detail: Record<string, unknown>, name: string) => {
      if (isWindowFocused()) return
      toastBus.info(t('toast.previewReady', { name }), undefined, {
        label: t('toast.open'),
        onClick: () => window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail })),
      })
    }

    const sessionId = currentSession?.id
    if (sessionId !== sessionRef.current) {
      sessionRef.current = sessionId
      seenRef.current = new Set()
      for (const m of currentSession?.messages ?? []) {
        for (const a of m.artifacts ?? []) seenRef.current.add(`${m.id}:art:${a.filename}`)
        for (const tc of m.tool_calls ?? []) {
          const model = classifyToolCall(tc)
          if (model.filePath) seenRef.current.add(`${m.id}:tool:${model.filePath}`)
        }
      }
      return
    }
    const msgs = currentSession?.messages ?? []
    if (msgs.length === 0) return
    // The last two messages are the ones a running turn can still add to; anything
    // older arrived before this hook existed.
    for (const m of msgs.slice(-2)) {
      for (const a of m.artifacts ?? []) {
        const key = `${m.id}:art:${a.filename}`
        if (seenRef.current.has(key) || !a.filename) continue
        seenRef.current.add(key)
        notice({ url: fileUrl(a.filename) }, a.filename)
      }
      for (const tc of m.tool_calls ?? []) {
        const model = classifyToolCall(tc)
        if (!model.filePath || !model.previewable || tc.status !== 'completed') continue
        const key = `${m.id}:tool:${model.filePath}`
        if (seenRef.current.has(key)) continue
        seenRef.current.add(key)
        notice(
          {
            tab: 'preview',
            url: `/api/file?path=${encodeURIComponent(model.filePath)}`,
          },
          model.filePath.split('/').pop() ?? model.filePath,
        )
      }
    }
  }, [currentSession?.id, currentSession?.messages, t])
}
