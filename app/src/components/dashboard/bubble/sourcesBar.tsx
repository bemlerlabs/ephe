import { Globe } from 'lucide-react'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import type { ToolCall } from '@/types'
import { extractSourceUrls } from '@/lib/toolCardModel'

/**
 * K3 Z14 (source bar): the citation line under the answer — numbered
 * chips built from the URL-carrying tool results (web_search/fetch_url).
 * A click opens the source in the page pane (PREVIEW_OPEN_EVENT pattern).
 */
export function SourcesBar({ tool_calls }: { tool_calls?: ToolCall[] }) {
  const urls = (tool_calls ?? []).reduce<string[]>(
    (acc, tc) => [
      ...acc,
      ...extractSourceUrls(typeof tc.result === 'string' ? tc.result : undefined),
    ],
    [],
  )
  const uniq = [...new Set(urls)].slice(0, 6)
  if (uniq.length === 0) return null
  return (
    <div className="mt-2 flex items-center gap-1.5 flex-wrap" data-testid="sources-bar">
      {uniq.map((url, i) => (
        <button
          key={url}
          type="button"
          data-testid={`source-chip-${i}`}
          onClick={() =>
            window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { url } }))
          }
          className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-ui-xs text-ink-soft hover:text-brand hover:bg-surface-interactive transition-colors max-w-full"
        >
          <Globe className="h-2.5 w-2.5 shrink-0" aria-hidden="true" />
          <span className="break-all text-left">{url.replace(/^https?:\/\//, '')}</span>
        </button>
      ))}
    </div>
  )
}
