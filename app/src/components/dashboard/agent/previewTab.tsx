'use client'

import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  RotateCw,
  Globe,
  ArrowLeft,
  ArrowRight,
  MoreHorizontal,
  Contrast,
  Smartphone,
} from 'lucide-react'
import { resolveFilePreview, prettifyUrl } from '@/lib/previewMode'
import { proxyFetch, LAN_TOKEN } from '@/lib/api'
import { isExternalHttpUrl, FRAME_SLOW_MS } from './previewUrl'
import { nativeBrowserHistory, openExternally } from '@/lib/nativeBrowser'
import { PreviewFrame, ReaderToggle } from './previewFrame'
import { useNativeBrowserPane } from './useNativeBrowserPane'

/** A loopback dev server, with the port as the capture — the proxy path needs both. */
const LOOPBACK_RE = /^(?:https?:\/\/)(?:localhost|127\.0\.0\.1|\[::1\])(?::(\d{1,5}))?(?:\/.*)?$/

export function PreviewTab({
  url,
  draft,
  nonce,
  inputRef,
  setDraft,
  recent,
  onPickRecent,
  onLoad,
  onReload,
  onBack,
  onForward,
  canBack,
  canForward,
}: {
  url: string
  draft: string
  nonce: number
  inputRef: React.RefObject<HTMLInputElement | null>
  setDraft: (v: string) => void
  onLoad: () => void
  onReload: () => void
  recent: string[]
  onPickRecent: (i: number) => void
  onBack: () => void
  onForward: () => void
  canBack: boolean
  canForward: boolean
}) {
  const { t } = useTranslation()
  // DD-12: text/markdown files render instead of going into an iframe (raw markup
  // presented as a "website" was unreadable); the address bar shows the file name
  // instead of the raw %2F query and switches to the full value while typing.
  const [editingUrl, setEditingUrl] = useState(false)
  // M1 (reference pattern): overflow menu + device/contrast toggles.
  const [menuOpen, setMenuOpen] = useState(false)
  const [narrow, setNarrow] = useState(false)
  const [contrast, setContrast] = useState(false)
  // G3: the frame gets an audible load state. `load`/`error` are the only
  // signals a cross-origin frame really delivers — anything else
  // would be an invented error diagnosis.
  const [frameState, setFrameState] = useState<'loading' | 'ready' | 'error'>('loading')
  // W1-b: the same address, two ways — the website or its text.
  const [reading, setReading] = useState(false)
  const [slow, setSlow] = useState(false)
  // W1: external pages run in the shell's native child WebView — an iframe cannot
  // show them (X-Frame-Options) yet reports "done" for an empty box. `native` is
  // the only state the surface knows about them.
  const {
    regionRef,
    native,
    loading: nativeLoading,
    title: nativeTitle,
    error: nativeError,
  } = useNativeBrowserPane(url, nonce, narrow ? 390 : undefined)
  const overflowRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  // U1b: Escape dismisses the preview overflow menu (keyboard parity).
  // G3: capture phase + stopPropagation — the panel listens for the same Escape on
  // the same window edge (panel.tsx) and would close the whole panel where only
  // the menu was meant to close. Focus returns to the trigger, otherwise it lands
  // on <body> after closing.
  useEffect(() => {
    if (!menuOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.stopPropagation()
      e.preventDefault()
      setMenuOpen(false)
      overflowRef.current?.focus()
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [menuOpen])

  // G3: opening the menu moves focus to its first entry (a menu without focus is
  // blind to keyboard users).
  useEffect(() => {
    if (!menuOpen) return
    menuRef.current?.querySelector<HTMLButtonElement>('button')?.focus()
  }, [menuOpen])

  const preview = resolveFilePreview(url)
  const framed = !!url && !preview
  useEffect(() => {
    setFrameState('loading')
    setSlow(false)
  }, [url, nonce])
  useEffect(() => {
    if (!framed || frameState !== 'loading') return
    const timer = setTimeout(() => setSlow(true), FRAME_SLOW_MS)
    return () => clearTimeout(timer)
  }, [framed, frameState, url, nonce])
  // P1-8 (option A — real-origin iframe): a loopback dev server (Vite/Next) gets
  // the iframe body on the REAL origin, so the dev server's native WebSocket HMR
  // runs browser→localhost:PORT directly — live updates, streaming and asset/router
  // fidelity come for free. The old srcDoc (a static snapshot) was exactly what
  // broke HMR.
  //
  // Remote case (LAN token through a QR link on the phone): that device does NOT
  // see the desktop loopback → a server-side reverse proxy fetches the body, and
  // srcDoc stays as a best-effort fallback. LAN_TOKEN is only set when a QR was
  // scanned — local desktop/PWA always runs on the real-origin path.
  const remote = !!LAN_TOKEN
  const [proxyHtml, setProxyHtml] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    const loopback = url.match(LOOPBACK_RE)
    if (!loopback || !remote) {
      setProxyHtml(null)
      return
    }
    const port = Number(loopback[1])
    if (!port || typeof proxyFetch !== 'function') return
    const path =
      url.replace(/^(?:https?:\/\/)?(?:localhost|127\.0\.0\.1|\[::1\]):\d{1,5}/, '') || '/'
    proxyFetch(port, path)
      .then((r) => {
        if (!cancelled && r.body) {
          setProxyHtml(r.body)
          setFrameState('ready')
        }
      })
      .catch(() => {
        // G3: the one honest frame error Ephe can actually get: our own proxy
        // request failed (remote case: the device cannot see the loopback). No
        // silence — the status line says so.
        if (!cancelled) setFrameState('error')
      })
    return () => {
      cancelled = true
    }
  }, [url, nonce, remote])
  const navBtn =
    'p-1.5 rounded-md text-ink-soft hover:text-foreground hover:bg-surface transition-colors disabled:opacity-30'
  // One state for both paths: the iframe reports load/error, the native pane its
  // real loading events. "ready" exists only once something has actually loaded.
  const phase: 'loading' | 'ready' | 'error' = native
    ? nativeError
      ? 'error'
      : nativeLoading
        ? 'loading'
        : 'ready'
    : frameState
  // In the native pane back/forward belongs to the page, not to the address list —
  // the address list stays reachable through the "recent" pills.
  const goBack = () => (native ? void nativeBrowserHistory('back') : onBack())
  const goForward = () => (native ? void nativeBrowserHistory('forward') : onForward())
  const goReload = () => {
    if (native) void nativeBrowserHistory('reload')
    else onReload()
  }
  return (
    <>
      <div className="relative flex items-center gap-2 px-3 h-12 border-b border-hairline flex-shrink-0">
        <button
          type="button"
          onClick={goBack}
          disabled={native ? false : !canBack}
          data-testid="preview-back"
          aria-label={t('agentPanel.previewBack')}
          title={t('agentPanel.previewBack')}
          className={navBtn}
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={goForward}
          disabled={native ? false : !canForward}
          data-testid="preview-forward"
          aria-label={t('agentPanel.previewForward')}
          title={t('agentPanel.previewForward')}
          className={navBtn}
        >
          <ArrowRight className="h-4 w-4" />
        </button>
        <button
          type="button"
          onClick={goReload}
          data-testid="preview-reload"
          aria-label={t('agentPanel.reload')}
          title={t('agentPanel.reload')}
          className={navBtn}
        >
          <RotateCw className="h-4 w-4" />
        </button>
        <input
          ref={inputRef}
          type="text"
          data-testid="preview-url-input"
          value={editingUrl ? draft : prettifyUrl(draft)}
          onChange={(e) => setDraft(e.target.value)}
          onFocus={() => setEditingUrl(true)}
          onBlur={() => setEditingUrl(false)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              setEditingUrl(false)
              onLoad()
            }
          }}
          placeholder={t('agentPanel.previewPlaceholder')}
          aria-label={t('agentPanel.previewUrlLabel')}
          title={url || undefined}
          // G3: an address bar is not a text box — URL keyboard, no autocomplete
          // from the browser's protocol store, no spell-check squiggles under a
          // hostname and no capitalisation at the start.
          inputMode="url"
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="none"
          spellCheck={false}
          className="flex-1 min-w-6 min-h-6 bg-transparent text-ui-sm text-foreground placeholder:text-ink-faint outline-none font-mono"
        />
        {/* R2-P1: at a 420 px pane the address bar kept 179 px — 23 characters of
            a 66-character URL. The two secondary switches do not belong in the row
            that is supposed to show the address; they live in the ⋯ menu now. */}
        {isExternalHttpUrl(url) && !preview && (
          <ReaderToggle active={reading} onToggle={() => setReading((v) => !v)} />
        )}
        <button
          type="button"
          ref={overflowRef}
          onClick={() => setMenuOpen((v) => !v)}
          aria-expanded={menuOpen}
          aria-haspopup="menu"
          data-testid="preview-overflow"
          aria-label={t('agentPanel.more')}
          title={t('agentPanel.more')}
          className={navBtn}
        >
          <MoreHorizontal className="h-4 w-4" />
        </button>
        {menuOpen && (
          <div
            ref={menuRef}
            data-testid="preview-menu"
            role="menu"
            className="absolute top-11 left-2 right-2 z-modal float-surface py-1.5 flex flex-col gap-0.5"
          >
            <button
              type="button"
              role="menuitem"
              aria-pressed={narrow}
              data-testid="preview-device"
              onClick={() => {
                setNarrow((v) => !v)
                setMenuOpen(false)
              }}
              className="w-full text-left px-3 py-1.5 text-ui-xs flex items-center gap-2 text-ink-faint hover:text-foreground hover:bg-surface transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
            >
              <Smartphone className="h-3.5 w-3.5" />
              {t('agentPanel.previewDeviceFit')}
            </button>
            {!native && (
              <button
                type="button"
                role="menuitem"
                aria-pressed={contrast}
                data-testid="preview-contrast"
                onClick={() => {
                  setContrast((v) => !v)
                  setMenuOpen(false)
                }}
                className="w-full text-left px-3 py-1.5 text-ui-xs flex items-center gap-2 text-ink-faint hover:text-foreground hover:bg-surface transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
              >
                <Contrast className="h-3.5 w-3.5" />
                {t('agentPanel.previewContrast')}
              </button>
            )}
            <button
              type="button"
              role="menuitem"
              data-testid="preview-menu-browser"
              onClick={() => {
                if (url) void openExternally(url)
                setMenuOpen(false)
              }}
              className="w-full text-left px-3 py-1.5 text-ui-xs flex items-center gap-2 text-ink-faint hover:text-foreground hover:bg-surface transition-colors focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2"
            >
              <Globe className="h-3.5 w-3.5" />
              {t('agentPanel.openInBrowser')}
            </button>
            {/* F-5: the old "open dev tools" item never opened dev tools (it
                reloaded the iframe) — removed as lying UI; the toolbar reload
                button covers the real action. */}
          </div>
        )}
      </div>
      {recent.length > 0 && (
        <div
          data-testid="preview-recent"
          className="px-3 py-1.5 flex flex-nowrap gap-1 overflow-x-auto border-b border-hairline flex-shrink-0"
        >
          {recent.map((u, i) => (
            <button
              key={`${i}-${u}`}
              type="button"
              data-testid={`preview-recent-${i}`}
              onClick={() => onPickRecent(i)}
              title={u}
              className="text-ui-xs font-mono px-1.5 py-0.5 rounded bg-surface border border-hairline text-ink-soft hover:text-foreground hover:border-brand/30 transition-colors truncate max-w-40 min-w-0 min-h-6"
            >
              {u}
            </button>
          ))}
        </div>
      )}
      <PreviewFrame
        url={url}
        nonce={nonce}
        preview={preview}
        native={native}
        nativeTitle={nativeTitle}
        nativeError={nativeError}
        phase={phase}
        slow={slow}
        contrast={contrast}
        narrow={narrow}
        proxyHtml={proxyHtml}
        reading={reading}
        regionRef={regionRef}
        onReload={onReload}
        onFrameReady={() => setFrameState('ready')}
      />
    </>
  )
}
