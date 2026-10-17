'use client'

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { File as FileIcon } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import { LoadingRow } from '@/components/ui'
import CodeBlock from '../CodeBlock'
import { resolveFilePreview } from '@/lib/previewMode'
import { apiUrl } from '@/lib/api/http'

/** DD-12: reads the file text and renders markdown as real markdown, or code
 *  through the chat code block (highlighting + copy). Reloads when the nonce rises. */
export function FilePreviewBody({
  preview,
  onReload,
}: {
  preview: NonNullable<ReturnType<typeof resolveFilePreview>>
  onReload: () => void
}) {
  const { t } = useTranslation()
  const [text, setText] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  // N1: what the read cost. The old sentence guessed the cause twice over
  // ("deleted or without access") and named neither the file nor the answer the
  // server gave. The status is the fact; null means the request never landed.
  const [httpStatus, setHttpStatus] = useState<number | null>(null)
  useEffect(() => {
    let cancelled = false
    setText(null)
    setFailed(false)
    setHttpStatus(null)
    fetch(apiUrl(`/api/file?path=${encodeURIComponent(preview.path)}`))
      .then((r) => {
        if (!r.ok) {
          if (!cancelled) setHttpStatus(r.status)
          throw new Error(String(r.status))
        }
        return r.text()
      })
      .then((body) => {
        if (!cancelled) setText(body)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [preview.path, preview.kind])
  const fileName = preview.path.split('/').pop() ?? preview.path
  if (failed) {
    return (
      <div
        data-testid="file-preview-failed"
        className="flex-1 flex flex-col items-center justify-center gap-2 text-ui-sm p-6 text-center"
        role="alert"
      >
        <FileIcon className="h-10 w-10 opacity-40 text-ink-faint" aria-hidden="true" />
        <p className="text-status-warning">{t('agentPanel.previewLoadFailed')}</p>
        <p
          className="max-w-full break-all font-mono text-ui-xs text-ink-faint"
          title={preview.path}
        >
          {preview.path}
        </p>
        <p className="text-ui-xs text-ink-faint font-mono">
          {httpStatus != null ? `HTTP ${httpStatus}` : t('agentPanel.fileUnreadNetwork')}
        </p>
        <button
          type="button"
          onClick={onReload}
          className="px-3 py-1.5 rounded-lg text-ui-xs font-medium border border-hairline text-foreground/80 hover:bg-surface-raised transition-colors"
        >
          {t('agentPanel.retry')}
        </button>
      </div>
    )
  }
  if (text === null) {
    // N1 (WD-32): the naked half-opacity spinner that stood here was the exact
    // drift `LoadingRow` was made to end — a spinner with no sentence, in a pane
    // that could not say which file it was reading.
    return (
      <div className="flex-1 flex items-center justify-center" aria-busy="true">
        <LoadingRow label={t('agentPanel.fileReading', { name: fileName })} />
      </div>
    )
  }
  return (
    <div
      className="flex-1 min-h-0 overflow-y-auto p-4"
      data-testid="file-preview-body"
      data-kind={preview.kind}
    >
      {preview.kind === 'markdown' ? (
        <div className="text-ui-sm text-foreground/90 prose prose-invert max-w-none prose-p:mb-2 prose-code:bg-surface prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-ui-xs prose-strong:text-foreground prose-em:text-foreground/90">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeHighlight]}
            components={{
              pre: (props: { children?: React.ReactNode }) => (
                <CodeBlock>{props.children}</CodeBlock>
              ),
            }}
          >
            {text}
          </ReactMarkdown>
        </div>
      ) : (
        <CodeBlock code={text} language={preview.language} />
      )}
    </div>
  )
}
