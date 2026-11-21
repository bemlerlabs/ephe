import { History, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'

/**
 * QA-E2E F6: a cold open used to land straight in the previous conversation,
 * red failed-tool bodies and all. When that restored conversation ends in
 * failures, its transcript waits behind this card until the reader asks for it;
 * the first screen offers the new task instead of an error report.
 */
export default function RestoredConversation({
  onShow,
  onNewTask,
}: {
  onShow: () => void
  onNewTask: () => void
}) {
  const { t } = useTranslation()
  return (
    <section
      data-testid="restored-conversation"
      aria-label={t('chat.restoredConversationTitle')}
      className="flex flex-1 min-h-0 items-center justify-center px-4 py-6"
    >
      <div className="w-full max-w-lg rounded-2xl border border-hairline bg-surface/60 p-5">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-brand/20 bg-brand/10 text-brand">
            <History className="h-4 w-4" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h2 className="text-ui-sm font-semibold text-foreground/90">
              {t('chat.restoredConversationTitle')}
            </h2>
            <p className="mt-1 text-ui-xs leading-relaxed text-ink-soft">
              {t('chat.restoredConversationBody')}
            </p>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            data-testid="restored-conversation-show"
            onClick={onShow}
            className="focus-ring rounded-lg border border-control bg-surface px-3 py-1.5 text-ui-xs text-ink-soft transition-colors hover:border-brand/30 hover:text-foreground"
          >
            {t('chat.restoredConversationShow')}
          </button>
          <button
            type="button"
            data-testid="restored-conversation-new"
            onClick={onNewTask}
            className="focus-ring inline-flex items-center gap-1.5 rounded-lg border border-brand/40 bg-brand/10 px-3 py-1.5 text-ui-xs font-medium text-brand transition-colors hover:bg-brand/20"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" />
            {t('sidebar.newChat')}
          </button>
        </div>
      </div>
    </section>
  )
}
