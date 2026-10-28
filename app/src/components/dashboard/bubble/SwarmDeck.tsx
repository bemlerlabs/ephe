import { useState } from 'react'
import { ChevronRight, ShieldCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { deckDone, deckFromActivities, deckPhase, type DeckActivity } from '@/lib/swarmDeck'

/**
 * C1/C2: the orchestra as a deck, not a ribbon of 6 px dots. It appears only
 * when the turn actually spawned agents, states the phase, and shows one card per
 * helper with the read-only seal.
 */
export function SwarmDeck({ activities }: { activities: readonly DeckActivity[] }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(true)
  const state = deckFromActivities(activities)
  const phase = deckPhase(state)
  if (phase == null) return null
  const done = deckDone(state)

  return (
    <div
      className="glass-control mt-1 rounded-lg px-2 py-1"
      data-testid="swarm-deck"
      data-phase={phase}
    >
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        data-testid="swarm-deck-toggle"
        className="flex w-full items-center gap-2 rounded-md px-1 py-1 text-left hover:bg-surface-interactive transition-colors"
      >
        <ChevronRight
          className={`h-3 w-3 shrink-0 text-ink-faint transition-transform ${open ? 'rotate-90' : ''}`}
          aria-hidden="true"
        />
        <span className="text-ui-xs text-ink-soft" data-testid="swarm-deck-phase">
          {t(`swarm.phase.${done ? 'done' : phase}`)}
        </span>
        <span className="tabular-nums text-ui-2xs text-ink-faint">
          {state.agents.length}/{state.count ?? '?'}
        </span>
        <span
          data-testid="swarm-deck-seal"
          className="ml-auto inline-flex shrink-0 items-center gap-1 text-ui-2xs text-status-success/90"
        >
          <ShieldCheck className="h-3 w-3" aria-hidden="true" />
          {t('swarm.seal')}
        </span>
      </button>
      {open && (
        <ul className="mt-0.5 space-y-0.5 pl-5" data-testid="swarm-deck-agents">
          {state.agents.map((agent) => (
            <li
              key={agent.id}
              data-testid={`swarm-agent-${agent.id}`}
              data-status={agent.status}
              className="flex items-center gap-2 text-ui-xs"
            >
              <span className="font-mono text-ink-faint">{agent.id}</span>
              {agent.role && <span className="text-ink-soft">{agent.role}</span>}
              {agent.task && <span className="truncate text-ink-faint">{agent.task}</span>}
              <span
                className={`ml-auto shrink-0 ${
                  agent.status === 'failed' ? 'text-status-danger' : 'text-ink-faint'
                }`}
              >
                {t(`swarm.agent.${agent.status}`)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
