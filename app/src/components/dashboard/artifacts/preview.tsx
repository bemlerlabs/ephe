/**
 * Ephe — the preview of a workbench card (R4/A5), one core for two surfaces.
 *
 * The mechanism is the same in the chat pop-up and on the archive page: the kind
 * decides what gets loaded, and **nothing** is ever emitted as an empty area.
 * Where a browser is blind (xlsx, docx) this surface asks the server (`/preview`)
 * and shows a real table or real text. Where even the server has nothing to say,
 * the card says it — instead of a white frame.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FileCode, RefreshCw } from 'lucide-react'
import { LoadingRow } from '@/components/ui'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import CodeBlock from '../CodeBlock'
import {
  artifactFileUrl,
  artifactPreview,
  type ArtifactContentPreview,
  type ArtifactEntry,
} from '@/lib/api'
import {
  artifactPreviewMode,
  codePreviewLanguage,
  previewSandbox,
  previewShowsInFrame,
  previewSrc,
} from '@/lib/previewMode'

function ContentPreview({ art }: { art: ArtifactEntry }) {
  const { t } = useTranslation()
  const [data, setData] = useState<ArtifactContentPreview | null>(null)
  const [failed, setFailed] = useState(false)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let cancelled = false
    setData(null)
    setFailed(false)
    artifactPreview(art.id)
      .then((r) => !cancelled && setData(r))
      .catch(() => !cancelled && setFailed(true))
    return () => {
      cancelled = true
    }
  }, [art.id, art.version, nonce])

  if (failed) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-ui-xs text-ink-faint">
        <span role="alert">{t('artifacts.preview.failed')}</span>
        <button
          type="button"
          onClick={() => setNonce((n) => n + 1)}
          data-testid="artifact-preview-retry"
          className="inline-flex min-h-7 items-center gap-1.5 rounded-md border border-hairline px-2.5 text-ui-2xs font-medium text-ink-soft transition-colors hover:bg-surface hover:text-foreground focus-ring"
        >
          <RefreshCw className="h-3 w-3" />
          {t('agentPanel.retry')}
        </button>
      </div>
    )
  }
  if (!data) {
    return <LoadingRow label={t('artifacts.preview.loading')} className="h-full justify-center" />
  }
  if (data.mode === 'table') {
    const header = data.header ?? []
    const rows = data.rows ?? []
    return (
      <div className="h-full overflow-auto">
        <table className="w-full border-collapse text-ui-xs">
          {data.sheets && data.sheets.length > 0 && (
            <caption className="sticky top-0 bg-surface px-2 py-1 text-left text-ui-2xs text-ink-faint">
              {data.sheets.join(' · ')}
            </caption>
          )}
          <thead>
            <tr>
              {header.map((h, i) => (
                <th
                  key={`${h}-${i}`}
                  scope="col"
                  className="sticky top-0 border-b border-hairline bg-surface px-2 py-1 text-left font-semibold text-foreground/80"
                >
                  {h || `—`}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, r) => (
              <tr key={r} className="odd:bg-surface/40">
                {header.map((_h, c) => (
                  <td
                    key={c}
                    className="border-b border-hairline px-2 py-1 align-top text-foreground/80"
                  >
                    {row[c] ?? ''}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {data.truncated && (
          <p className="px-2 py-1.5 text-ui-2xs text-ink-faint">
            {t('artifacts.preview.truncated')}
          </p>
        )}
      </div>
    )
  }
  if (data.mode === 'text') {
    const text = data.text ?? ''
    if (data.format === 'markdown') {
      return (
        <div className="prose prose-invert max-w-none h-full overflow-auto px-3 py-2 text-ui-sm prose-p:mb-2 prose-code:bg-surface prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-ui-xs prose-strong:text-foreground">
          <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
            {text}
          </ReactMarkdown>
        </div>
      )
    }
    return (
      <pre className="h-full overflow-auto px-3 py-2 font-mono text-ui-xs whitespace-pre-wrap text-foreground/80">
        {text}
      </pre>
    )
  }
  return <NoPreview art={art} reason={data.reason} />
}

/** Code as source: the bytes come from the file endpoint, so .ts/.py/.sh cards
 *  show a real view instead of the 'unsupported' answer they gave before. */
function CodePreview({ art }: { art: ArtifactEntry }) {
  const { t } = useTranslation()
  const [text, setText] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [nonce, setNonce] = useState(0)
  const language = codePreviewLanguage(art.name, art.kind) ?? 'text'

  useEffect(() => {
    let cancelled = false
    setText(null)
    setFailed(false)
    fetch(artifactFileUrl(art.id))
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status))
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
  }, [art.id, art.version, nonce])

  if (failed) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-ui-xs text-ink-faint">
        <span role="alert">{t('artifacts.preview.failed')}</span>
        <button
          type="button"
          onClick={() => setNonce((n) => n + 1)}
          data-testid="artifact-preview-code-retry"
          className="inline-flex min-h-7 items-center gap-1.5 rounded-md border border-hairline px-2.5 text-ui-2xs font-medium text-ink-soft transition-colors hover:bg-surface hover:text-foreground focus-ring"
        >
          <RefreshCw className="h-3 w-3" />
          {t('agentPanel.retry')}
        </button>
      </div>
    )
  }
  if (text === null) {
    return <LoadingRow label={t('artifacts.preview.loading')} className="h-full justify-center" />
  }
  return (
    <div className="h-full overflow-auto" data-testid="artifact-preview-code">
      <CodeBlock code={text} language={language} />
    </div>
  )
}

function NoPreview({ art, reason }: { art: ArtifactEntry; reason?: string }) {
  const { t } = useTranslation()
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-ui-xs text-ink-soft">
      <FileCode className="h-9 w-9 opacity-40" aria-hidden />
      <span className="break-all">{art.name}</span>
      <span className="text-ink-faint">
        {reason === 'missing'
          ? t('artifacts.preview.missing')
          : reason === 'no-viewer'
            ? t('artifacts.preview.noViewer')
            : t('artifacts.preview.unsupported')}
      </span>
    </div>
  )
}

/** Image, audio or video — with an explanation when the bytes are missing.
 *
 * This file promises never to emit nothing but an empty area. The image branch
 * did not keep that: a card whose file has been cleared away answers 404, and the
 * frame showed a broken-image glyph without a word about it (re-measured on
 * `ephe_github_qr.png` in the live index). */
function Media({ art, src }: { art: ArtifactEntry; src: string }) {
  const mode = artifactPreviewMode(art.name, art.kind)
  const [fehlt, setFehlt] = useState(false)
  if (fehlt) return <NoPreview art={art} reason="missing" />
  if (mode === 'image') {
    return (
      <img
        src={src}
        alt={art.name}
        onError={() => setFehlt(true)}
        className="h-full w-full object-contain"
      />
    )
  }
  if (mode === 'audio') {
    return (
      <div className="flex h-full items-center p-4">
        <audio controls src={src} onError={() => setFehlt(true)} className="w-full" />
      </div>
    )
  }
  return (
    <video
      controls
      src={src}
      onError={() => setFehlt(true)}
      className="h-full w-full bg-canvas object-contain"
    />
  )
}

export default function ArtifactPreviewPane({ art }: { art: ArtifactEntry }) {
  const mode = artifactPreviewMode(art.name, art.kind)
  const src = artifactFileUrl(art.id)
  if (mode === 'image' || mode === 'audio' || mode === 'video') {
    return <Media art={art} src={src} />
  }
  if (mode === 'frame' && previewShowsInFrame(art.name, art.kind)) {
    return (
      <iframe
        src={previewSrc(src, art.name, art.kind)}
        title={art.name}
        // A dead format stays without the directive (otherwise the browser shows its
        // white rectangle); anything that can carry scripts goes in the dense frame.
        sandbox={previewSandbox(art.name, art.kind)}
        style={{ colorScheme: 'light' }}
        className="h-full w-full bg-white"
      />
    )
  }
  if (mode === 'content') {
    return <ContentPreview art={art} />
  }
  if (mode === 'code') {
    return <CodePreview art={art} />
  }
  return <NoPreview art={art} reason={mode === 'frame' ? 'no-viewer' : undefined} />
}
