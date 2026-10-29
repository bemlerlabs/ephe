/**
 * `/tools` — the standalone tool surface (W4).
 *
 * Two endpoints had no caller in the app: image analysis (`/api/vision/analyze`,
 * `/api/vision/base64`) and the portable session bundle (`/api/sessions/export`,
 * `/api/sessions/import`). The chat path carries images inside a turn; this page
 * is where one image is analysed on its own and where the session store is
 * backed up or restored as a bundle.
 */
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, Download, ImageIcon, Loader2, Upload } from 'lucide-react'
import { Button, Card } from '@/components/ui'
import PageHeader from '@/components/shell/PageHeader'
import { ToolCatalog } from '@/components/dashboard/ToolCatalog'
import {
  analyzeImage,
  analyzeImageBase64,
  exportSessionsBundle,
  importSessionsBundle,
  type VisionAnalysis,
} from '@/lib/api'
import { isNetworkLikeError } from '@/lib/streamErrors'

type Translator = (key: string, opts?: Record<string, unknown>) => string
type ToolsErrorKind = 'import' | 'export' | 'vision'
/** The sentence the reader gets, plus the transport line when it was replaced. */
type Refusal = { text: string; detail: string }

/** Both bundle bindings throw the raw fetch shape: `API <status>: <statusText>`. */
const STATUS_LINE = /^API (\d{3}):/

/**
 * The bundle bindings read no body (`lib/api/endpoints.ts:214,232`), so a refused
 * import arrives here as `API 400: Bad Request` — a transport line that names no
 * next step. The chat path refuses to show that shape (lib/streamErrors.ts,
 * lib/serverError.ts), so the two readers run here too: a vanished backend, and the
 * sentence the bundle holds for a refusal. The status survives as `HTTP 400`; the
 * untouched line stays behind the disclosure for a bug report.
 */
function toolsRefusal(err: unknown, t: Translator, kind: ToolsErrorKind): Refusal {
  const raw = (err instanceof Error ? err.message : String(err ?? '')).trim()
  if (isNetworkLikeError(err)) return { text: t('tools.errorOffline'), detail: '' }
  const status = STATUS_LINE.exec(raw)
  const message = status ? `HTTP ${status[1]}` : raw || t('chat.streamErrorUnknown')
  const detail = status ? raw : ''
  if (kind === 'vision') return { text: t('serverError.vision_failed', { error: message }), detail }
  if (kind === 'export') return { text: t('tools.errorExport', { message }), detail }
  return { text: t('tools.errorImport', { message }), detail }
}

/** One refusal on this page: the sentence first, the raw line one disclosure down. */
function RefusalNote({ testId, refusal }: { testId: string; refusal: Refusal }) {
  const { t } = useTranslation()
  return (
    <div data-testid={testId} role="alert" className="mt-3 text-ui-sm text-status-danger">
      <p data-testid={`${testId}-text`}>{refusal.text}</p>
      {refusal.detail && (
        <details className="mt-1">
          <summary className="cursor-pointer text-ui-xs text-ink-faint">
            {t('error.crashDetails')}
          </summary>
          <p
            data-testid={`${testId}-detail`}
            className="mt-1 break-words font-mono text-ui-xs text-ink-faint"
          >
            {refusal.detail}
          </p>
        </details>
      )}
    </div>
  )
}

function downloadBytes(filename: string, bytes: Uint8Array): void {
  const url = URL.createObjectURL(new Blob([bytes], { type: 'application/zip' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export default function ToolsPage() {
  const { t } = useTranslation()
  const imageInputRef = useRef<HTMLInputElement>(null)
  const bundleInputRef = useRef<HTMLInputElement>(null)

  const [file, setFile] = useState<File | null>(null)
  const [question, setQuestion] = useState('')
  const [base64, setBase64] = useState('')
  const [analysis, setAnalysis] = useState<VisionAnalysis | null>(null)
  const [visionBusy, setVisionBusy] = useState(false)
  const [visionError, setVisionError] = useState<Refusal | null>(null)

  const [restored, setRestored] = useState<number | null>(null)
  const [bundleBusy, setBundleBusy] = useState(false)
  const [bundleError, setBundleError] = useState<Refusal | null>(null)

  async function runVision(run: () => Promise<VisionAnalysis>) {
    setVisionBusy(true)
    setVisionError(null)
    setAnalysis(null)
    try {
      setAnalysis(await run())
    } catch (err) {
      setVisionError(toolsRefusal(err, t, 'vision'))
    } finally {
      setVisionBusy(false)
    }
  }

  async function onExport() {
    setBundleBusy(true)
    setBundleError(null)
    try {
      const bytes = await exportSessionsBundle('zip')
      downloadBytes('sessions.zip', bytes)
    } catch (err) {
      setBundleError(toolsRefusal(err, t, 'export'))
    } finally {
      setBundleBusy(false)
    }
  }

  async function onImport(bundle: File) {
    setBundleBusy(true)
    setBundleError(null)
    setRestored(null)
    try {
      const bytes = new Uint8Array(await bundle.arrayBuffer())
      const { restored: count } = await importSessionsBundle(bytes, bundle.name)
      setRestored(count)
    } catch (err) {
      setBundleError(toolsRefusal(err, t, 'import'))
    } finally {
      setBundleBusy(false)
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-6">
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="icon"
          data-testid="tools-back"
          aria-label={t('a11y.navBack')}
          onClick={() => {
            window.location.hash = '#/chat'
          }}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <PageHeader title={t('tools.title')} subtitle={t('tools.subtitle')} />
      </div>

      <ToolCatalog />

      <Card data-testid="tools-vision">
        <h3 className="flex items-center gap-2 font-display text-ui-lg font-semibold text-foreground/95">
          <ImageIcon className="h-4 w-4" />
          {t('tools.visionTitle')}
        </h3>
        <p className="mt-1 text-ui-sm text-ink-faint">{t('tools.visionHint')}</p>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <input
            ref={imageInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            aria-label={t('tools.chooseImage')}
            data-testid="tools-image-input"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <Button
            variant="secondary"
            size="sm"
            data-testid="tools-image-pick"
            className="pointer-coarse:min-h-11"
            onClick={() => imageInputRef.current?.click()}
          >
            <Upload className="h-4 w-4" />
            {t('tools.chooseImage')}
          </Button>
          <span
            data-testid="tools-image-name"
            className="min-w-0 truncate text-ui-sm text-ink-faint"
          >
            {file?.name ?? t('tools.noImage')}
          </span>
        </div>

        <label className="mt-3 block text-ui-xs text-ink-soft" htmlFor="tools-question">
          {t('tools.questionLabel')}
        </label>
        <input
          id="tools-question"
          className="glass-control focus-ring mt-1.5 w-full rounded-xl px-4 py-3 text-ui-sm text-foreground placeholder:text-ink-faint pointer-coarse:min-h-11 pointer-coarse:text-ui-input"
          placeholder={t('tools.questionPlaceholder')}
          data-testid="tools-question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />

        <div className="mt-3">
          <Button
            size="sm"
            data-testid="tools-analyze"
            className="pointer-coarse:min-h-11"
            disabled={!file || visionBusy}
            onClick={() => file && runVision(() => analyzeImage(file, question))}
          >
            {visionBusy && <Loader2 className="h-4 w-4 animate-spin" />}
            {t('tools.analyze')}
          </Button>
        </div>

        <div className="mt-4 border-t border-hairline pt-4">
          <label className="block text-ui-xs text-ink-soft" htmlFor="tools-base64">
            {t('tools.base64Label')}
          </label>
          <textarea
            id="tools-base64"
            className="glass-control focus-ring mt-1.5 w-full rounded-xl px-4 py-3 text-ui-sm text-foreground placeholder:text-ink-faint pointer-coarse:text-ui-input"
            rows={2}
            placeholder={t('tools.base64Placeholder')}
            data-testid="tools-base64"
            value={base64}
            onChange={(e) => setBase64(e.target.value)}
          />
          <div className="mt-2">
            <Button
              variant="secondary"
              size="sm"
              data-testid="tools-analyze-base64"
              className="pointer-coarse:min-h-11"
              disabled={!base64.trim() || visionBusy}
              onClick={() => runVision(() => analyzeImageBase64(base64, question))}
            >
              {t('tools.analyzeBase64')}
            </Button>
          </div>
        </div>

        {visionError && <RefusalNote testId="tools-vision-error" refusal={visionError} />}
        {analysis && (
          <div
            data-testid="tools-vision-result"
            role="status"
            className="mt-3 glass-reading rounded-xl p-4"
          >
            <p className="whitespace-pre-wrap text-ui-sm leading-relaxed text-foreground/90">
              {analysis.analysis}
            </p>
            <p className="mt-3 text-ui-xs text-ink-faint">
              {t('tools.model')}: {analysis.model}
            </p>
          </div>
        )}
      </Card>

      <Card data-testid="tools-bundle">
        <h3 className="flex items-center gap-2 font-display text-ui-lg font-semibold text-foreground/95">
          <Download className="h-4 w-4" />
          {t('tools.bundleTitle')}
        </h3>
        <p className="mt-1 text-ui-sm text-ink-faint">{t('tools.bundleHint')}</p>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button size="sm" data-testid="tools-export" disabled={bundleBusy} onClick={onExport}>
            <Download className="h-4 w-4" />
            {t('tools.exportBundle')}
          </Button>
          <input
            ref={bundleInputRef}
            type="file"
            accept=".zip,.tgz,.gz"
            className="hidden"
            aria-label={t('tools.importBundle')}
            data-testid="tools-bundle-input"
            onChange={(e) => {
              const picked = e.target.files?.[0]
              if (picked) void onImport(picked)
            }}
          />
          <Button
            variant="secondary"
            size="sm"
            data-testid="tools-import"
            disabled={bundleBusy}
            onClick={() => bundleInputRef.current?.click()}
          >
            <Upload className="h-4 w-4" />
            {t('tools.importBundle')}
          </Button>
        </div>

        {bundleError && <RefusalNote testId="tools-bundle-error" refusal={bundleError} />}
        {restored !== null && (
          <p
            data-testid="tools-bundle-result"
            role="status"
            className="mt-3 text-ui-sm text-foreground/90"
          >
            {t('tools.imported', { count: restored })}
          </p>
        )}
      </Card>
    </div>
  )
}
