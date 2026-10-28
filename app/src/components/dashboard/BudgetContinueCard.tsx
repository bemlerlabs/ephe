import { ArrowRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useChatStore } from '@/store/chatStore'

/**
 * QD-015 Z2: the turn used up its tool rounds.
 *
 * The answer already says so; this card is the way on. One click sends a normal
 * turn that carries the cap the server reported plus the rounds the button
 * promised, so the work continues where it stopped instead of starting over.
 */
export function BudgetContinueCard({ onContinue }: { onContinue: () => void }) {
  const { t } = useTranslation()
  const notice = useChatStore((s) => s.budgetNotice)
  const typing = useChatStore((s) => s.isTyping)
  if (!notice || typing) return null
  return (
    <div
      data-testid="budget-continue"
      role="status"
      className="mx-auto mt-3 flex max-w-3xl flex-wrap items-center gap-3 rounded-xl border border-status-warning/40 bg-status-warning/10 px-3 py-2"
    >
      <div className="min-w-0 flex-1">
        <p className="text-ui-xs font-medium text-foreground/90">{t('chat.continueTitle')}</p>
        <p className="text-ui-xs text-ink-soft">
          {t('chat.continueBody', { cap: notice.cap })}
        </p>
      </div>
      <button
        type="button"
        onClick={onContinue}
        data-testid="budget-continue-button"
        className="flex shrink-0 items-center gap-1.5 rounded-lg bg-status-warning/20 px-2.5 py-1.5 text-ui-xs font-medium text-status-warning transition-colors hover:bg-status-warning/30"
      >
        {t('chat.continueButton', { extra: notice.extra })}
        <ArrowRight className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
      </button>
    </div>
  )
}
