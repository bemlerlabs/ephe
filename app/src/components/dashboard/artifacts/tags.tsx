/**
 * Ephe — the labels of a workbench card (R4).
 *
 * The endpoint existed for a long time with no reader. Without a reader an
 * endpoint is not a feature but dead weight — so the card shows them now, and
 * "no label" stays a state, never an error.
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { setArtifactTags, type ArtifactEntry } from '@/lib/api'

export default function ArtifactTags({
  art,
  onSaved,
}: {
  art: ArtifactEntry
  onSaved: () => void
}) {
  const { t } = useTranslation()
  const existing = Array.isArray(art.tags) ? art.tags : []
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)

  async function save(next: string[]) {
    setBusy(true)
    try {
      await setArtifactTags(art.id, next)
      onSaved()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-lg border border-hairline bg-surface p-2.5" data-testid="artifact-tags">
      <p className="mb-1.5 text-ui-2xs font-semibold uppercase tracking-wide text-ink-faint">
        {t('artifacts.page.tags')}
      </p>
      <ul className="flex flex-wrap items-center gap-1.5">
        {existing.map((tag) => (
          <li key={tag}>
            <span className="inline-flex items-center gap-1 rounded-md border border-hairline px-1.5 py-0.5 text-ui-2xs text-foreground/80">
              {tag}
              <button
                type="button"
                onClick={() => void save(existing.filter((x) => x !== tag))}
                disabled={busy}
                aria-label={`${t('artifacts.page.tagRemove')}: ${tag}`}
                className="text-ink-faint hover:text-destructive"
              >
                ✕
              </button>
            </span>
          </li>
        ))}
        <li>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              const value = draft.trim()
              if (!value || existing.includes(value)) {
                setDraft('')
                return
              }
              setDraft('')
              void save([...existing, value].slice(0, 20))
            }}
          >
            <label className="flex items-center gap-1">
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder={t('artifacts.page.tagAdd')}
                aria-label={t('artifacts.page.tagAdd')}
                className="w-32 rounded-md border border-control bg-canvas px-1.5 py-1 text-ui-2xs text-foreground/80 placeholder:text-ink-faint focus-ring"
              />
              {/* An input field without a visible confirmation is a hidden
                  gesture — you have to guess that Enter does anything. */}
              <button
                type="submit"
                aria-label={t('artifacts.page.tagAddSubmit')}
                data-testid="artifact-tag-add"
                disabled={busy}
                className="rounded-md border border-control px-1.5 py-1 text-ui-2xs text-ink-soft hover:bg-surface hover:text-foreground/80"
              >
                +
              </button>
            </label>
          </form>
        </li>
      </ul>
    </div>
  )
}
