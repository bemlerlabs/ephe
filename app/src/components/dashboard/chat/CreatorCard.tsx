import { useState } from 'react'
import { Loader2, Package } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { getPlugins } from '@/lib/api'
import type { PluginEntry } from '@/lib/api'
import { friendlyError } from '@/lib/errorText'
import { isPluginSurfaceOpen, showPluginSurface } from '@/lib/pluginDisplay'
import { creatorModelFor, type CreatorCallShape } from '@/lib/creatorCardModel'

/**
 * #28 — the plugin taking shape, and one way onto the screen.
 *
 * The rows above already carry the run's record: each call, its verb, its clock. This card
 * answers the one question those rows leave open — what the bundle now IS — and reads the
 * answer only out of what the four creator calls replied (see `creatorCardModel`). While a
 * call is still waiting for its reply the card says so and claims nothing about it.
 *
 * The action is the mount the platform already owns. Nothing is installed or enabled here:
 * the store view is read once, and whichever of its answers arrives is shown as it arrived,
 * including a refusal. `pluginDisplay` keeps the owner's rule that a fallback is loud, so a
 * surface the layer will not give is named, not quietly swapped for the other side.
 */
type OpenState =
  | { kind: 'idle' }
  | { kind: 'busy' }
  | { kind: 'shown'; name: string }
  | { kind: 'refused'; message: string }

const entryRows = (view: {
  public?: PluginEntry[]
  personal?: PluginEntry[]
  global?: PluginEntry[]
  session?: PluginEntry[]
}): PluginEntry[] => [
  ...(view.global ?? []),
  ...(view.session ?? []),
  ...(view.public ?? []),
  ...(view.personal ?? []),
]

export default function CreatorCard({
  tools,
  streaming,
}: {
  tools: CreatorCallShape[]
  streaming?: boolean
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState<OpenState>({ kind: 'idle' })
  const model = creatorModelFor(tools)
  if (!model) return null

  const standing = model.name ? isPluginSurfaceOpen(model.name) : false

  const handleOpen = async () => {
    if (open.kind === 'busy') return
    setOpen({ kind: 'busy' })
    try {
      const view = await getPlugins()
      const entry = entryRows(view).find((row) => row.id === model.name || row.name === model.name)
      if (!entry) {
        setOpen({ kind: 'refused', message: t('chat.creator.notListed') })
        return
      }
      if (!entry.surface) {
        setOpen({ kind: 'refused', message: t('chat.creator.noSurface') })
        return
      }
      const outcome = await showPluginSurface({ pluginId: entry.id, descriptor: entry.surface }, t)
      setOpen(
        outcome.opened
          ? { kind: 'shown', name: entry.name || entry.id }
          : { kind: 'refused', message: t(outcome.message) },
      )
    } catch (cause) {
      setOpen({
        kind: 'refused',
        message: friendlyError(cause instanceof Error ? cause.message : String(cause), (key) =>
          String(t(key)),
        ),
      })
    }
  }

  return (
    <div
      data-testid="creator-card"
      role="status"
      className="mt-2 max-w-3xl rounded-xl border border-hairline bg-surface/60 px-3 py-2 text-ui-xs"
    >
      <div className="flex flex-wrap items-center gap-2 font-medium text-foreground/90">
        <Package
          className="h-3.5 w-3.5 shrink-0 text-brand/70"
          strokeWidth={1.5}
          aria-hidden="true"
        />
        <span data-testid="creator-name" className="min-w-0 truncate font-mono">
          {model.name || t('chat.creator.unnamed')}
        </span>
        {model.version ? (
          <span className="tabular-nums text-ink-soft">v{model.version}</span>
        ) : null}
        {model.staged ? (
          <span className="text-ink-soft">
            {t('chat.creator.files', { count: model.files.length })}
          </span>
        ) : null}
      </div>

      {model.files.length > 0 ? (
        <ul className="mt-1 grid gap-0.5 font-mono text-ui-2xs text-ink-soft">
          {model.files.map((file) => (
            <li data-testid="creator-file" key={file} className="min-w-0 truncate">
              {file}
            </li>
          ))}
        </ul>
      ) : null}

      {model.verified ? (
        <p className="mt-1 text-status-success/90">
          {model.tools.length
            ? t('chat.creator.verifiedTools', { count: model.tools.length })
            : t('chat.creator.verified')}
        </p>
      ) : model.staged && streaming ? (
        <p className="mt-1 text-ink-soft">{t('chat.creator.notVerified')}</p>
      ) : null}

      {model.problems.map((problem) => (
        <p
          data-testid="creator-problem"
          key={problem}
          className="mt-1 text-status-danger/90"
          title={model.error}
        >
          {problem}
        </p>
      ))}

      {streaming && model.pending > 0 ? (
        <p data-testid="creator-running" className="mt-1 flex items-center gap-1.5 text-ink-soft">
          <Loader2 className="h-3 w-3 animate-spin text-brand" aria-hidden="true" />
          {t('chat.creator.running', { count: model.pending })}
        </p>
      ) : null}

      {model.installed ? (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="text-ink-faint">
            {model.enabled ? t('chat.creator.installed') : t('chat.creator.installedDisabled')}
          </span>
          <button
            type="button"
            data-testid="creator-open-surface"
            onClick={handleOpen}
            disabled={open.kind === 'busy'}
            className="flex min-h-6 max-lg:min-h-11 shrink-0 items-center gap-1.5 rounded-lg border border-hairline bg-canvas px-2.5 py-1 font-medium text-brand-deep transition-colors hover:border-brand/30 hover:bg-brand/10 disabled:opacity-60"
          >
            {open.kind === 'busy' ? (
              <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
            ) : null}
            {standing ? t('chat.creator.show') : t('chat.creator.open')}
          </button>
          {open.kind === 'shown' ? (
            <span data-testid="creator-open-state" className="text-status-success/90">
              {t('chat.creator.opened', { name: open.name })}
            </span>
          ) : null}
        </div>
      ) : null}

      {open.kind === 'refused' ? (
        <p role="alert" className="mt-1.5 text-status-danger/90">
          {open.message}
        </p>
      ) : null}
    </div>
  )
}
