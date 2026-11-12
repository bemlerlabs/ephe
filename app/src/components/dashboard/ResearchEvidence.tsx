import { useEffect, useMemo, useState } from 'react'
import { ExternalLink, FileCode2, Globe, Link2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { getResearchEvidence, type ResearchEvidence as Evidence } from '@/lib/api'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import type { ToolCall } from '@/types'

/**
 * Wave 3 (web intake): the reader surface the `web_research` call opens.
 *
 * The tool's text stays the audit line; this panel is the reading view of the
 * same run. A page becomes a card with its title, its address, the fetch time
 * and the digest the answer's `s_…` id stands for. A workspace claim keeps its
 * `path:line` address. Every card wraps and shrinks, so the panel holds at the
 * 320 px floor without a horizontal scroll.
 *
 * No run to read (an older server, a restored history, a restart) means no
 * panel. The tool's own result already carries its sources, so the fallback is
 * the text the reader came from.
 */
export function ResearchEvidence({ tool }: { tool: ToolCall }) {
  const { t } = useTranslation()
  const query = typeof tool.args?.query === 'string' ? tool.args.query.trim() : ''
  const completed = tool.status === 'completed'
  const [evidence, setEvidence] = useState<Evidence | null>(null)

  useEffect(() => {
    if (!query || !completed) {
      setEvidence(null)
      return
    }
    const controller = new AbortController()
    getResearchEvidence({ query, limit: 8 }, controller.signal)
      .then((answer) => {
        if (!controller.signal.aborted) setEvidence(answer)
      })
      .catch(() => {
        // The tool result remains the record; an absent list costs the cards,
        // never the sources.
        if (!controller.signal.aborted) setEvidence(null)
      })
    return () => controller.abort()
  }, [query, completed])

  const run = useMemo(() => {
    if (!evidence) return null
    return (
      evidence.runs.find((one) => one.run_id === evidence.sources[0]?.run_id) ??
      evidence.runs[0] ??
      null
    )
  }, [evidence])

  if (!evidence || (evidence.sources.length === 0 && evidence.workspace.length === 0)) {
    return null
  }

  return (
    <section
      data-testid="research-evidence"
      className="mt-1 min-w-0 max-w-full overflow-hidden rounded-xl border border-hairline bg-canvas/40"
    >
      <header className="flex min-w-0 flex-wrap items-center gap-1.5 px-2.5 pt-2">
        <Globe className="h-3 w-3 shrink-0 text-brand/70" aria-hidden="true" />
        <span className="min-w-0 break-words text-ui-2xs uppercase tracking-wide text-ink-soft">
          {query ? t('chat.research.evidenceFor', { query }) : t('chat.research.sourcesTitle')}
        </span>
        <span className="ml-auto shrink-0 font-mono text-ui-2xs text-ink-faint">
          {evidence.total}
        </span>
      </header>

      {evidence.sources.length > 0 && (
        <ul className="m-0 list-none space-y-1.5 p-2.5" data-testid="research-sources">
          {evidence.sources.map((source) => {
            const host = hostOf(source.url)
            return (
              <li key={`${source.run_id}-${source.source_id}`} className="min-w-0">
                <button
                  type="button"
                  data-testid="research-source-card"
                  onClick={() =>
                    window.dispatchEvent(
                      new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url: source.url } }),
                    )
                  }
                  aria-label={t('chat.research.sourceOpened', { host })}
                  className="block w-full min-w-0 rounded-lg border border-hairline bg-surface/60 p-2 text-left transition-colors hover:border-brand/40 hover:bg-surface"
                >
                  <span className="flex min-w-0 items-start gap-1.5">
                    <Link2 className="mt-0.5 h-3 w-3 shrink-0 text-ink-faint" aria-hidden="true" />
                    <span className="min-w-0 break-words text-ui-xs text-foreground/90">
                      {source.title || source.url}
                    </span>
                    <ExternalLink
                      className="mt-0.5 h-3 w-3 shrink-0 text-ink-faint"
                      aria-hidden="true"
                    />
                  </span>
                  <span className="mt-0.5 block min-w-0 break-all font-mono text-ui-2xs text-ink-faint">
                    {t('chat.research.sourceMeta', {
                      host,
                      time: source.fetched_at,
                      sha: source.sha256.slice(0, 8),
                    })}
                  </span>
                  <span className="mt-1 block min-w-0 break-words text-ui-2xs leading-relaxed text-ink-soft line-clamp-2">
                    {source.excerpt}
                  </span>
                  <span className="mt-1 block font-mono text-ui-2xs text-ink-faint">
                    [{source.source_id}]
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}

      {evidence.workspace.length > 0 && (
        <div className="border-t border-hairline px-2.5 py-2" data-testid="research-workspace">
          <div className="flex items-center gap-1.5 text-ui-2xs uppercase tracking-wide text-ink-soft">
            <FileCode2 className="h-3 w-3 shrink-0 text-brand/70" aria-hidden="true" />
            <span className="min-w-0 break-words">{t('chat.research.workspaceTitle')}</span>
          </div>
          <ul className="m-0 mt-1.5 list-none space-y-1 p-0">
            {evidence.workspace.map((hit) => (
              <li key={`${hit.run_id}-${hit.reference}`} className="min-w-0">
                <span className="block min-w-0 break-all font-mono text-ui-2xs text-brand/80">
                  {hit.reference}
                </span>
                <span className="block min-w-0 break-words text-ui-2xs leading-relaxed text-ink-soft line-clamp-2">
                  {hit.text}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {run && run.verification.checked > 0 && (
        <p
          data-testid="research-verification"
          className="m-0 border-t border-hairline px-2.5 py-1.5 text-ui-2xs text-ink-faint"
        >
          {run.verification.verified === run.verification.checked
            ? t('chat.research.citationAll', { checked: run.verification.checked })
            : t('chat.research.citationMissing', {
                missing: run.verification.checked - run.verification.verified,
                checked: run.verification.checked,
              })}
        </p>
      )}
    </section>
  )
}

function hostOf(url: string): string {
  try {
    return new URL(url).host
  } catch {
    return url
  }
}
