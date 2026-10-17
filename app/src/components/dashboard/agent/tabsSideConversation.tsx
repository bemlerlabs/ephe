'use client'

import { useTranslation } from 'react-i18next'
import { useChatStore } from '@/store/chatStore'
import { fmtClock } from '@/lib/format'
import { trajectoryRoleTextClass } from './trajectoryRoleStyles'

// N1 — side conversation: a compact reading form of the active session's history
// inside the pane. The same role colour series as the trajectory pane
// (trajectoryRoleTextClass), so both panes share one visual axis. No endpoint of
// its own — the store already is the source of the chat list.
export function SideConversationTab() {
  const { t } = useTranslation()
  const sessionId = useChatStore((s) => s.activeSessionId)
  const messages = useChatStore((s) => s.currentSession?.messages)
  if (!sessionId || !messages || messages.length === 0)
    return (
      <div
        data-testid="side-conversation-empty"
        className="flex-1 px-3 py-4 text-ui-xs text-ink-faint"
      >
        {/* N1: one source for this sentence. The inline English `defaultValue`
            duplicated the bundle and made the German surface fall back to the
            English string whenever the key moved. */}
        {t('agentPanel.sideEmpty')}
      </div>
    )
  return (
    <div className="flex-1 min-h-0 overflow-y-auto px-3 py-2" data-testid="side-conversation">
      <ol className="space-y-2">
        {messages.map((m, i) => (
          <li
            key={m.id ?? i}
            data-testid={`side-msg-${i}`}
            className="rounded-lg border border-hairline bg-canvas px-3 py-2"
          >
            <div className="flex items-baseline gap-2">
              <span
                className={`font-mono text-ui-xs uppercase ${trajectoryRoleTextClass(m.role) || 'text-ink-faint'}`}
              >
                {m.role}
              </span>
              <span className="ml-auto font-mono text-ui-xs text-ink-faint tabular-nums">
                {fmtClock(m.timestamp)}
              </span>
            </div>
            <p className="mt-1 text-ui-xs text-ink-soft whitespace-pre-wrap break-words">
              {m.content ?? ''}
            </p>
          </li>
        ))}
      </ol>
    </div>
  )
}
