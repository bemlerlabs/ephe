import { useState } from 'react'
import { Check, FolderDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { adoptArtifact } from '@/lib/api'
import { adoptWithTarget } from './adoptFlow'

/**
 * E3: the same adopt gesture the turn card and the library carry, on the rail
 * row. Desktop asks through the native dialog; a browser without a remembered
 * target gets the server's 422 and is asked for a path here, in the row.
 */
export function RailAdoptAction({ id, name }: { id: string; name: string }) {
  const { t } = useTranslation()
  const [busy, setBusy] = useState(false)
  const [adopted, setAdopted] = useState<string | null>(null)
  const [needsPath, setNeedsPath] = useState(false)
  const [path, setPath] = useState('')
  const [failed, setFailed] = useState(false)

  async function run(destination?: string) {
    setBusy(true)
    setFailed(false)
    try {
      const result = destination
        ? await adoptArtifact(id, destination)
        : await adoptWithTarget(id, name, t('artifacts.adopt'))
      setAdopted(result.adopted_path ?? '')
      setNeedsPath(false)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setNeedsPath(message.toLowerCase().includes('destination'))
      setFailed(!message.toLowerCase().includes('destination'))
    } finally {
      setBusy(false)
    }
  }

  if (adopted) {
    return (
      <span
        data-testid={`artifact-row-adopted-${id}`}
        title={adopted || t('artifacts.adopt')}
        className="inline-flex items-center gap-1 p-1 text-status-success/90"
      >
        <Check className="h-3.5 w-3.5" aria-hidden="true" />
      </span>
    )
  }

  if (needsPath) {
    return (
      <span className="inline-flex items-center gap-1" data-testid={`artifact-row-adopt-path-${id}`}>
        <input
          value={path}
          onChange={(event) => setPath(event.target.value)}
          placeholder="/Users/you/Documents"
          aria-label={t('artifacts.adoptHint')}
          className="w-28 rounded border border-hairline bg-surface px-1 py-0.5 text-ui-2xs"
        />
        <button
          type="button"
          disabled={!path.trim() || busy}
          onClick={() => void run(path.trim())}
          data-testid={`artifact-row-adopt-send-${id}`}
          className="rounded px-1 text-ui-2xs text-brand disabled:opacity-40"
        >
          {t('artifacts.adopt')}
        </button>
      </span>
    )
  }

  return (
    <span className="inline-flex flex-col items-end">
      <button
        type="button"
        disabled={busy}
        onClick={() => void run()}
        aria-label={`${t('artifacts.adopt')}: ${name}`}
        title={t('artifacts.adoptHint')}
        data-testid={`artifact-row-adopt-${id}`}
        className="rounded p-1 text-ink-soft hover:bg-surface hover:text-foreground disabled:opacity-40"
      >
        <FolderDown className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
      {failed && (
        <span className="text-ui-2xs text-status-danger" role="alert">
          {t('artifacts.adoptFailed')}
        </span>
      )}
    </span>
  )
}
