// N2 — tool replay frame per assistant turn: collapsed to one row (the header),
// expanded into numbered steps (TYPE in the role colour, text, duration). The data source
// is the existing trajectory snapshot (GET /api/trajectory?session=), no
// new endpoint. Turn assignment follows the order of the
// assistant messages in the store — the same sequence as the turns from the API.
'use client'

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { History, ChevronRight } from 'lucide-react'
import { useChatStore } from '@/store/chatStore'
import { getTrajectory, type TrajTurn } from '@/lib/api'
import { fmtMs } from '@/lib/format'
import { trajectoryRoleTextClass } from './agent/trajectoryRoleStyles'
import type { ChatMessage } from '@/types'

export function ToolReplayKader({ message }: { message: ChatMessage }) {
  const { t } = useTranslation()
  const sessionId = useChatStore((s) => s.activeSessionId)
  const list = useChatStore((s) => s.currentSession?.messages)
  let ti = -1
  if (Array.isArray(list)) {
    let n = 0
    for (const mm of list) {
      if (mm.role === 'assistant') {
        if (mm.id === message.id) {
          ti = n
          break
        }
        n++
      }
    }
  }
  const [turn, setTurn] = useState<TrajTurn | null>(null)
  useEffect(() => {
    if (!sessionId || ti < 0) return
    let cancelled = false
    getTrajectory(sessionId)
      .then((r) => {
        if (!cancelled) setTurn(r.turns[ti] ?? null)
      })
      .catch(() => {
        if (!cancelled) setTurn(null)
      })
    return () => {
      cancelled = true
    }
  }, [sessionId, ti])
  const [open, setOpen] = useState(false)
  if (ti < 0 || !turn || turn.steps.length === 0) return null
  const total = turn.steps.reduce((a, s) => a + s.ms, 0)
  return (
    <div className="mt-2" data-testid={`tool-replay-kader-${ti}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 rounded-lg border border-hairline bg-canvas px-3 py-1.5 text-ui-xs text-ink-soft transition-colors hover:text-foreground"
      >
        <History className="h-3 w-3 shrink-0 text-brand/70" aria-hidden="true" />
        <span className="font-medium">{t('chat.replayTitle')}</span>
        <span className="ml-auto font-mono tabular-nums">
          {turn.steps.length} steps · {fmtMs(total)}
        </span>
        <ChevronRight
          className={`h-3 w-3 shrink-0 transition-transform ${open ? 'rotate-90' : ''}`}
          aria-hidden="true"
        />
      </button>
      {open && (
        <ol className="mt-1 space-y-0.5 pl-1">
          {turn.steps.map((s, i) => (
            <li
              key={s.n}
              data-testid={`replay-row-${ti}-${i}`}
              className="flex items-baseline gap-2 text-ui-xs text-ink-soft"
            >
              <span className="shrink-0 font-mono text-ink-faint tabular-nums">
                {String(i + 1).padStart(2, '0')}
              </span>
              <span
                className={`shrink-0 font-mono uppercase ${trajectoryRoleTextClass(s.type) || 'text-ink-faint'}`}
              >
                {s.type}
              </span>
              <span className="min-w-0 flex-1 truncate font-mono">
                {s.text || s.title || s.state}
              </span>
              <span className="shrink-0 font-mono tabular-nums">{fmtMs(s.ms)}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
