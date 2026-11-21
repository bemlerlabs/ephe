'use client'

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { BookOpen } from 'lucide-react'
import { LoadingRow } from '@/components/ui'
import { readUrl, type ReaderResult } from '@/lib/api/endpoints'

/** The server splits the reader version into lines; here each line kind only gets
 *  its shape. No markdown library for four cases. */
function blocks(text: string): { kind: 'h' | 'li' | 'p'; text: string }[] {
  const out: { kind: 'h' | 'li' | 'p'; text: string }[] = []
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    if (!line) continue
    const heading = /^#{1,6}\s+(.*)$/.exec(line)
    if (line.startsWith('#') && !heading?.[1]) continue
    if (heading?.[1]) {
      out.push({ kind: 'h', text: heading[1] })
    } else if (line.startsWith('- ')) {
      out.push({ kind: 'li', text: line.slice(2) })
    } else {
      out.push({ kind: 'p', text: line })
    }
  }
  return out
}

/**
 * W1-b: the reader view. An iframe can show a page that permits it; this surface
 * shows the text of every page the scope guard lets through — the same network
 * window as the agent tools, never a second one.
 */
export function ReaderView({ url, nonce }: { url: string; nonce: number }) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [result, setResult] = useState<ReaderResult | null>(null)

  useEffect(() => {
    let dead = false
    setLoading(true)
    readUrl(url)
      .then((r) => {
        if (!dead) setResult(r)
      })
      .catch((e: unknown) => {
        if (!dead)
          setResult({
            ok: false,
            reason: e instanceof Error ? e.message : String(e),
            title: '',
            text: '',
            chars: 0,
            truncated: false,
            target: url,
          })
      })
      .finally(() => {
        if (!dead) setLoading(false)
      })
    return () => {
      dead = true
    }
  }, [url, nonce])

  // The failure payload carries a reason code beside the sentence the route has
  // always sent. `endpoints.ts` types the payload without it, so the two fields
  // are read off the object — the pane has to work with a server that sends them
  // and with one that does not.
  const failure = result as
    | (ReaderResult & {
        reason_code?: string | null
        reason_params?: Record<string, string | number>
      })
    | null
  const reasonShown = failure?.reason_code
    ? t(`reader.${failure.reason_code}`, {
        ...failure.reason_params,
        defaultValue: failure.reason,
      })
    : failure?.reason

  if (loading) {
    return (
      <div
        data-testid="reader-loading"
        role="status"
        aria-live="polite"
        className="flex-1 min-h-0 flex flex-col items-center justify-center gap-2 text-ink-faint text-ui-sm"
      >
        <LoadingRow label={t('agentPanel.readerLoading')} />
      </div>
    )
  }

  if (!result?.ok) {
    return (
      <div
        data-testid="reader-error"
        role="alert"
        className="flex-1 min-h-0 flex flex-col items-center justify-center gap-2 p-6 text-center"
      >
        <BookOpen className="h-8 w-8 opacity-40" aria-hidden="true" />
        <p className="text-ui-sm text-foreground/80">
          {t('agentPanel.readerFailed', { defaultValue: 'This page yields no text.' })}
        </p>
        <p className="text-ui-xs text-ink-faint max-w-72">{reasonShown}</p>
      </div>
    )
  }

  return (
    <article
      data-testid="reader-view"
      className="flex-1 min-h-0 overflow-y-auto px-4 py-3 space-y-2 text-ui-sm leading-relaxed text-foreground/90"
    >
      <h2 className="text-ui-lg font-semibold text-foreground break-words">{result.title}</h2>
      <p className="text-ui-xs text-ink-faint font-mono break-all">{result.target}</p>
      {blocks(result.text).map((b, i) =>
        b.kind === 'h' ? (
          <h3 key={i} className="text-ui-sm font-semibold pt-2 break-words">
            {b.text}
          </h3>
        ) : b.kind === 'li' ? (
          <p key={i} className="pl-4 break-words">
            · {b.text}
          </p>
        ) : (
          <p key={i} className="break-words">
            {b.text}
          </p>
        ),
      )}
      {result.truncated && (
        <p data-testid="reader-truncated" className="text-ui-xs text-ink-faint pt-2">
          {t('agentPanel.readerTruncated', {
            defaultValue: 'The text ends here — the surface shows what the fetch carries.',
          })}
        </p>
      )}
    </article>
  )
}
