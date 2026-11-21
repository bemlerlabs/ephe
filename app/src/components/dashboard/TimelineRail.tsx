import { useTranslation } from 'react-i18next'
import { useMemo } from 'react'
import type { ChatMessage, MessageRole } from '@/types'

/**
 * Ephe — Timeline Rail (P2-6)
 *
 * Narrow vertical marker rail beside the messages. Each dot is one message;
 * colour by role; clicking scrolls to that message.
 * The message currently in view is highlighted (via activeIndex).
 */

const ROLE_COLOR: Record<MessageRole, string> = {
  user: 'bg-brand',
  assistant: 'bg-moss-light/40',
  system: 'bg-status-warning/70',
}

interface TimelineRailProps {
  messages: ChatMessage[]
  activeIndex?: number
  onSelect: (index: number) => void
}

export default function TimelineRail({ messages, activeIndex, onSelect }: TimelineRailProps) {
  const { t } = useTranslation()
  const markers = useMemo(
    () =>
      (messages || []).map((m, i) => ({
        index: i,
        color: ROLE_COLOR[m.role] ?? 'bg-surface',
        active: i === activeIndex,
      })),
    [messages, activeIndex],
  )

  if (markers.length === 0) return null

  return (
    <div
      data-testid="timeline-rail"
      role="navigation"
      className="w-[24px] flex-shrink-0 self-stretch flex flex-col items-center gap-1 py-2 select-none"
      aria-label="Timeline"
    >
      {markers.map((m) => (
        <button
          key={m.index}
          data-testid={'timeline-marker-' + m.index}
          onClick={() => onSelect(m.index)}
          title={`${t('chat.goToMessage', { n: m.index + 1 })}${m.active ? ` ${t('chat.activeMarker')}` : ''}`}
          aria-label={t('chat.goToMessage', { n: m.index + 1 })}
          aria-current={m.active ? 'true' : undefined}
          className="flex min-h-6 w-[24px] items-center justify-center cursor-pointer"
        >
          <span
            className={`block w-1.5 h-1.5 rounded-full transition-all ${m.color} ${
              m.active ? 'ring-2 ring-white/70 scale-125' : 'opacity-40 hover:opacity-100'
            }`}
          />
        </button>
      ))}
    </div>
  )
}
