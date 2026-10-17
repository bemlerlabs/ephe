'use client'

import { useTranslation } from 'react-i18next'
import { BookOpen, Globe, Loader2 } from 'lucide-react'
import { isExternalHttpUrl } from './previewUrl'
import { FilePreviewBody } from './filePreview'
import { ReaderView } from './readerView'
import { openExternally } from '@/lib/nativeBrowser'
import type { FilePreview } from '@/lib/previewMode'

/**
 * The content below the address bar (W1-R2: split out of previewTab.tsx so the
 * address bar carries its own weight and this surface carries its own).
 *
 * Three states that must stay distinguishable: a file preview, a web page (an
 * iframe in the PWA, a child WebView above this node on the desktop), and the
 * reader view that fetches the same material as text.
 */
export function PreviewFrame({
  url,
  nonce,
  preview,
  native,
  nativeTitle,
  nativeError,
  phase,
  slow,
  contrast,
  narrow,
  proxyHtml,
  reading,
  regionRef,
  onReload,
  onFrameReady,
}: {
  url: string
  nonce: number
  preview: FilePreview | null
  native: boolean
  nativeTitle: string
  nativeError: string | null
  phase: 'loading' | 'ready' | 'error'
  slow: boolean
  contrast: boolean
  narrow: boolean
  proxyHtml: string | null
  reading: boolean
  regionRef: React.RefObject<HTMLDivElement | null>
  onReload: () => void
  onFrameReady: () => void
}) {
  const { t } = useTranslation()

  if (preview) {
    return (
      <FilePreviewBody key={`${preview.path}:${nonce}`} preview={preview} onReload={onReload} />
    )
  }

  if (reading && isExternalHttpUrl(url)) {
    return <ReaderView key={`${url}:${nonce}`} url={url} nonce={nonce} />
  }

  if (!url) {
    // M1 (reference pattern): a three-part empty state — globe, title, hint.
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-2 text-ink-faint text-ui-sm p-6 text-center">
        <Globe className="h-10 w-10 opacity-40" />
        <p className="font-medium text-foreground/80" data-testid="preview-empty-title">
          {t('agentPanel.browserTitle')}
        </p>
        <p data-testid="preview-empty-hint">{t('agentPanel.previewEmpty')}</p>
      </div>
    )
  }

  return (
    <>
      {/* P6 B5: an honest fallback hint for external pages (X-Frame-Options /
          CSP frame-ancestors cannot be seen cross-origin — instead of a fake error
          message, the "open externally" hint sits there permanently). */}
      {isExternalHttpUrl(url) && !native && (
        <div
          data-testid="preview-external-fallback"
          className="px-3 py-1 flex items-center gap-2 border-b border-hairline flex-shrink-0 text-ui-xs text-ink-faint"
        >
          {/* No truncate: the sentence names two reasons, and the second one (a
              format with no viewer in the window) would be cut off exactly when it
              happens to be the right one. */}
          <p className="flex-1 min-w-0">
            {t('agentPanel.browserEmbedHint', {
              defaultValue:
                'Page stays blank? Some sites forbid embedding (X-Frame-Options). Formats with no viewer in this window — PDF among them — stay white.',
            })}
          </p>
          <button
            type="button"
            onClick={() => url && void openExternally(url)}
            className="flex items-center gap-1 px-1.5 py-0.5 rounded-md text-ui-xs text-ink-soft hover:text-foreground hover:bg-surface border border-hairline transition-colors shrink-0"
          >
            <Globe className="h-3 w-3" aria-hidden="true" />
            {t('agentPanel.openExternal', { defaultValue: 'Open externally' })}
          </button>
        </div>
      )}
      {/* G3: a landing row for the frame state. role="status" (polite) while
          loading, role="alert" only on a real error event — a page that is merely
          slow must not be announced as a failure. After a successful load the row
          is gone (no permanent spinner as UI noise). */}
      {phase !== 'ready' && (
        <div
          data-testid="preview-frame-status"
          role={phase === 'error' ? 'alert' : 'status'}
          aria-live={phase === 'error' ? 'assertive' : 'polite'}
          data-state={phase === 'error' ? 'error' : !native && slow ? 'slow' : 'loading'}
          className="px-3 py-1 flex items-center gap-2 border-b border-hairline flex-shrink-0 text-ui-xs text-ink-faint"
        >
          {phase === 'loading' && (
            <Loader2 className="h-3 w-3 animate-spin opacity-70" aria-hidden="true" />
          )}
          <p className="flex-1 min-w-0 truncate">
            {phase === 'error'
              ? native && nativeError
                ? nativeError
                : t('agentPanel.previewFrameError', {
                    defaultValue: 'The frame could not load this address.',
                  })
              : !native && slow
                ? t('agentPanel.previewFrameSlow', {
                    defaultValue:
                      'Still loading — the page may refuse embedding or the server is not answering.',
                  })
                : t('agentPanel.previewFrameLoading', { defaultValue: 'Loading page…' })}
          </p>
          {((!native && slow) || phase === 'error') && (
            <button
              type="button"
              data-testid="preview-frame-retry"
              onClick={onReload}
              className="px-1.5 py-0.5 rounded-md text-ui-xs text-ink-soft hover:text-foreground hover:bg-surface border border-hairline transition-colors shrink-0"
            >
              {t('agentPanel.retry')}
            </button>
          )}
        </div>
      )}
      <div
        ref={regionRef}
        data-testid="preview-frame-region"
        role="region"
        aria-label={t('agentPanel.browserTitle')}
        aria-busy={phase === 'loading'}
        className="flex-1 min-h-0 flex justify-center overflow-hidden"
        style={{ filter: !native && contrast ? 'invert(1)' : undefined }}
      >
        {native ? (
          /* The border belongs to the child WebView. What stands here is read by a
             screen reader (the native pane is invisible to it) and shows who is
             waiting before the page paints. */
          <p
            data-testid="preview-frame-native"
            className="m-auto max-w-64 px-4 text-center text-ui-xs text-ink-faint truncate"
          >
            {nativeTitle || url}
          </p>
        ) : (
          <iframe
            key={nonce}
            data-testid="preview-frame"
            src={url}
            srcDoc={proxyHtml ?? undefined}
            title={t('commandPalette.items.preview')}
            onLoad={onFrameReady}
            // F-L: color-scheme:dark used to inherit into the iframe — Chrome
            // rendered text/markdown files black.
            // G3: allow-popups-to-escape-sandbox is out — a popout that leaves the
            // sandbox lifts the directive for everything after it.
            style={{ maxWidth: narrow ? 390 : undefined, colorScheme: 'light' }}
            className="w-full h-full bg-white"
            sandbox="allow-scripts allow-forms allow-modals allow-popups allow-pointer-lock allow-same-origin"
          />
        )}
      </div>
    </>
  )
}

/** The reader icon belongs in the tool row, not in a menu: it is the second way
 *  to the very same address. */
export function ReaderToggle({ active, onToggle }: { active: boolean; onToggle: () => void }) {
  const { t } = useTranslation()
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-pressed={active}
      data-testid="preview-reader-toggle"
      aria-label={t('agentPanel.readerToggle', { defaultValue: 'Read the page as text' })}
      title={t('agentPanel.readerToggle', { defaultValue: 'Read the page as text' })}
      className={`p-1.5 rounded-md transition-colors ${
        active ? 'text-brand bg-surface' : 'text-ink-soft hover:text-foreground hover:bg-surface'
      }`}
    >
      <BookOpen className="h-4 w-4" />
    </button>
  )
}
