import { useEffect, useState } from 'react'
import { ChevronRight, ShieldCheck } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { getCapabilities, steerTurn } from '@/lib/api'
import { useDeepSelect } from '@/lib/deepSettings'
import { deckDone, deckFromActivities, deckPhase, type DeckActivity } from '@/lib/swarmDeck'

/**
 * C1/C2: the orchestra as a deck, not a ribbon of 6 px dots. It appears only
 * when the turn actually spawned agents, states the phase, and shows one card per
 * helper with the read-only seal.
 */
export function SwarmDeck({
  activities,
  sessionId,
  turnId,
}: {
  activities: readonly DeckActivity[]
  sessionId?: string
  turnId?: string | null
}) {
  const { t } = useTranslation()
  // D1: the same register switch picks the wording of the steer field.
  const detailsMode = useDeepSelect('chat.details_mode', 'expanded')
  const [open, setOpen] = useState(true)
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [steered, setSteered] = useState<Record<string, string>>({})
  const [steerError, setSteerError] = useState<string | null>(null)
  // The seal counts the tools the guard actually grants.
  const [toolCount, setToolCount] = useState<number | null>(null)

  useEffect(() => {
    let alive = true
    getCapabilities()
      .then((view) => {
        if (alive) setToolCount(view.subagent?.tool_count ?? null)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  async function steer(agentId: string) {
    const text = (draft[agentId] ?? '').trim()
    if (!text || !sessionId) return
    setSteerError(null)
    try {
      await steerTurn({ sessionId, turnId, text, agentId })
      setSteered((prev) => ({ ...prev, [agentId]: text }))
      setDraft((prev) => ({ ...prev, [agentId]: '' }))
    } catch (error) {
      setSteerError(error instanceof Error ? error.message : String(error))
    }
  }
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
          {t('swarm.seal', { n: toolCount ?? '—' })}
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
              {agent.status === 'running' && sessionId && (
                <span className="ml-auto inline-flex shrink-0 items-center gap-1">
                  <input
                    value={draft[agent.id] ?? ''}
                    onChange={(event) =>
                      setDraft((prev) => ({ ...prev, [agent.id]: event.target.value }))
                    }
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') void steer(agent.id)
                    }}
                    placeholder={
                      detailsMode === 'expanded' ? t('swarm.steerExpert') : t('swarm.steerEveryday')
                    }
                    aria-label={t('swarm.steerAria', { id: agent.id })}
                    data-testid={`swarm-steer-${agent.id}`}
                    className="w-28 rounded border border-hairline bg-surface px-1 py-0.5 text-ui-2xs"
                  />
                  <button
                    type="button"
                    onClick={() => void steer(agent.id)}
                    data-testid={`swarm-steer-send-${agent.id}`}
                    className="rounded px-1 text-ui-2xs text-brand"
                  >
                    →
                  </button>
                </span>
              )}
              {(steered[agent.id] || agent.steered || agent.status !== 'running') && (
                <span
                  className={`ml-auto shrink-0 ${
                    steered[agent.id] || agent.steered
                      ? 'text-status-warning'
                      : agent.status === 'failed'
                        ? 'text-status-danger'
                        : 'text-ink-faint'
                  }`}
                  data-testid={`swarm-agent-state-${agent.id}`}
                  title={steered[agent.id] ?? agent.steered}
                >
                  {steered[agent.id] || agent.steered
                    ? t('swarm.agent.steered')
                    : t(`swarm.agent.${agent.status}`)}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {steerError && (
        <p className="pl-5 text-ui-2xs text-status-danger" role="alert">
          {steerError}
        </p>
      )}
    </div>
  )
}
