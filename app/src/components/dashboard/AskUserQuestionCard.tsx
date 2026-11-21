import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { AskSpec } from '@/lib/askUserQuestion'

interface AskUserQuestionCardProps {
  spec: AskSpec
  onPick: (answer: string) => void
  /** G1: the run behind this card no longer waits for an answer (it continued, or it
   *  was stopped), so the options are shown but cannot be picked any more. */
  disabled?: boolean
}

/**
 * J6 (point 14): the structured option card below the answer.
 * Single choice: a click sends the label directly. Multiple choice: toggle +
 * apply button (labels comma-separated). The recommendation is marked.
 */
export default function AskUserQuestionCard({
  spec,
  onPick,
  disabled = false,
}: AskUserQuestionCardProps) {
  const { t } = useTranslation()
  const [picked, setPicked] = useState<number[]>([])
  const rec = (spec.recommendation || '').trim().toLowerCase()

  const isRecommended = (opt: { label: string; description?: string }, index: number) => {
    if (!rec) return false
    const label = opt.label.trim().toLowerCase()
    const num = String(index + 1)
    // exact, a prefix of the other, or a shared start (models reply with longer sentence versions)
    return (
      label === rec ||
      num === rec ||
      label.startsWith(rec) ||
      rec.startsWith(label) ||
      label.slice(0, 12) === rec.slice(0, 12)
    )
  }

  const toggle = (index: number) => {
    setPicked((prev) => (prev.includes(index) ? prev.filter((i) => i !== index) : [...prev, index]))
  }

  const takeOver = () => {
    const labels = picked
      .sort((a, b) => a - b)
      .map((i) => spec.options[i]?.label)
      .filter(Boolean)
    if (labels.length > 0) onPick(labels.join(', '))
  }

  return (
    <div
      role="group"
      aria-label={spec.question}
      className="mt-2 rounded-2xl glass-reading p-3 space-y-1.5"
      data-testid="ask-card"
    >
      <p className="text-ui-sm font-medium text-brand/90">{spec.question}</p>
      {spec.options.map((opt, i) => {
        const active = picked.includes(i)
        return (
          <button
            key={`${opt.label}-${i}`}
            onClick={() => (spec.multiSelect ? toggle(i) : onPick(opt.label))}
            disabled={disabled}
            data-testid={`ask-option-${i}`}
            aria-pressed={spec.multiSelect ? active : undefined}
            className="w-full flex items-start gap-2 text-left px-2 py-1.5 rounded-lg bg-surface hover:bg-brand/10 transition-colors disabled:opacity-50 disabled:hover:bg-surface disabled:cursor-not-allowed"
          >
            <span
              aria-hidden="true"
              className="shrink-0 h-4 w-4 rounded-full bg-brand/20 text-brand text-ui-2xs flex items-center justify-center mt-0.5"
            >
              {i + 1}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-ui-xs text-foreground/80">
                {opt.label}
                {isRecommended(opt, i) && (
                  <span className="ml-1.5 text-ui-2xs text-brand/80">
                    <span aria-hidden="true">★</span> {t('chat.askRecommended')}
                  </span>
                )}
              </span>
              {opt.description && (
                <span className="block text-ui-xs text-ink-soft">{opt.description}</span>
              )}
            </span>
            {spec.multiSelect && (
              <span
                aria-hidden
                className={`shrink-0 h-3 w-3 mt-1 rounded-sm border ${active ? 'bg-brand border-brand' : 'border-mist/40'}`}
              />
            )}
          </button>
        )
      })}
      {spec.multiSelect && (
        <button
          onClick={takeOver}
          disabled={disabled || picked.length === 0}
          data-testid="ask-takeover"
          className="px-3 py-1 rounded-lg text-ui-xs bg-brand text-black hover:bg-brand disabled:opacity-30 transition-colors"
        >
          {t('chat.askTakeover')}
        </button>
      )}
    </div>
  )
}
