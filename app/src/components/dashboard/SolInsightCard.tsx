import { Lightbulb } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useChatStore } from '@/store/chatStore'

/**
 * SOL: the turn proved a rule about this project.
 *
 * The card names what was learned and opens the store that holds it. The rule
 * itself lives in `.ephe/learning/heuristics.md` in the workspace — this is the
 * notice, and the inspector is where it is edited or deleted.
 */
export function SolInsightCard() {
  const { t } = useTranslation()
  const insights = useChatStore((s) => s.solInsights)
  if (!insights || insights.length === 0) return null
  const openStore = () => {
    window.dispatchEvent(new CustomEvent('ephe:settings-tab', { detail: { tab: 'memory' } }))
    window.dispatchEvent(new CustomEvent('ephe:open-settings'))
  }
  return (
    <div
      data-testid="sol-insight"
      role="status"
      className="mx-auto mt-3 flex max-w-3xl flex-wrap items-center gap-3 rounded-xl border border-brand/30 bg-brand/10 px-3 py-2"
    >
      <Lightbulb className="h-4 w-4 shrink-0 text-brand" strokeWidth={1.5} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-ui-xs font-medium text-foreground/90">{t('chat.solLearned')}</p>
        <ul className="mt-0.5 space-y-0.5">
          {insights.map((rule) => (
            <li key={rule.id} className="truncate text-ui-xs text-ink-soft" title={rule.action}>
              {rule.title}
            </li>
          ))}
        </ul>
      </div>
      <button
        type="button"
        onClick={openStore}
        data-testid="sol-insight-open"
        className="shrink-0 rounded-lg bg-brand/20 px-2.5 py-1.5 text-ui-xs font-medium text-brand-deep transition-colors hover:bg-brand/30 max-lg:min-h-11"
      >
        {t('chat.solOpen')}
      </button>
    </div>
  )
}
