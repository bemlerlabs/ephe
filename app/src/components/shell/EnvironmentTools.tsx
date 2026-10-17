/**
 * Ephe — wave B, B2/B3 (docs/EXTENSIONS_V2_PLAN.md): EnvironmentTools.
 *
 * The app-shell section "your existing tools": an opt-in scan of agent tools
 * already installed — one row per detected tool, with the
 * plugin-store anatomy (letter tile + name + auth dot + model chips). The scan
 * happens ONLY on click (POST, never an auto-fetch) and never shows credentials —
 * core/environment_mirror guarantees that.
 *
 * Optional onPick: setup/settings can take a recognised model as a preselected
 * engine (derivePick decides whether that is honestly derivable — otherwise the
 * chip stays purely informative).
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2, Radar, ScanSearch } from 'lucide-react'
import { scanEnvironment, type MirrorTool } from '@/lib/api/environment'
import slugAngle from './slugAngle'

export type EnginePick = {
  providerKind: 'local_ollama' | 'custom_ollama' | 'openai_compatible'
  endpoint?: string
  model: string
}

const URL_RE = /^https?:\/\//

/** Strip query parameters off endpoints (never expose keys in a URL). */
export function scrubUrl(url: string): string {
  const i = url.indexOf('?')
  return i >= 0 ? url.slice(0, i) : url
}

/** Every http(s) endpoint hidden inside the providers/models strings. */
export function endpointsOf(tool: MirrorTool): string[] {
  const raw = [...tool.providers, ...tool.models].filter((s) => URL_RE.test(s))
  return [...new Set(raw.map(scrubUrl))]
}

/**
 * An honest preselection: only when an endpoint can be derived.
 * Ollama port/provider → local_ollama (the standard endpoint), otherwise
 * openai_compatible with the endpoint that was found. No endpoint → null
 * (the chip stays informative — never a silent fallback).
 */
export function derivePick(tool: MirrorTool, model: string): EnginePick | null {
  // Honest pairing: the catalog endpoint of THIS model (models.dev 'api')
  // wins — otherwise an unrelated :11434 entry in the provider list would
  // outvote the pairing. No catalog endpoint: guess from the provider list.
  const catalogEp = tool.model_endpoints?.[model]
  if (catalogEp) {
    if (catalogEp.includes(':11434')) {
      return { providerKind: 'custom_ollama', endpoint: catalogEp, model }
    }
    return { providerKind: 'openai_compatible', endpoint: catalogEp, model }
  }
  const endpoints = endpointsOf(tool)
  const isOllamaish =
    tool.providers.some((p) => p.toLowerCase().includes('ollama')) ||
    endpoints.some((e) => e.includes(':11434'))
  if (isOllamaish) {
    const ep = endpoints.find((e) => e.includes(':11434'))
    return { providerKind: ep ? 'custom_ollama' : 'local_ollama', endpoint: ep, model }
  }
  if (endpoints.length > 0) {
    return { providerKind: 'openai_compatible', endpoint: endpoints[0], model }
  }
  return null
}

export default function EnvironmentTools({
  onPick,
}: {
  onPick?: (pick: EnginePick, tool: MirrorTool) => void
}) {
  const { t } = useTranslation()
  const [tools, setTools] = useState<MirrorTool[] | null>(null)
  const [scanning, setScanning] = useState(false)
  const [error, setError] = useState('')

  async function runScan(): Promise<void> {
    setScanning(true)
    setError('')
    try {
      const res = await scanEnvironment()
      setTools(res.tools)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setScanning(false)
    }
  }

  const installed = (tools ?? []).filter((tl) => tl.installed)
  const missing = (tools ?? []).filter((tl) => !tl.installed).map((tl) => tl.tool)

  return (
    <div data-testid="environment-tools" className="space-y-2.5">
      <div className="flex items-center gap-2">
        <Radar className="h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
        <p className="min-w-0 flex-1 text-ui-xs text-ink-soft">{t('environment.hint')}</p>
      </div>
      <button
        type="button"
        data-testid="environment-scan-button"
        onClick={() => void runScan()}
        disabled={scanning}
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-hairline bg-surface-raised px-4 py-2.5 text-ui-xs text-foreground/80 transition-colors hover:bg-surface-interactive disabled:opacity-40 focus-ring pointer-coarse:min-h-11"
      >
        {scanning ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-brand" />
        ) : (
          <ScanSearch className="h-3.5 w-3.5 text-brand" />
        )}
        {scanning
          ? t('environment.scanning')
          : tools
            ? t('environment.rescan')
            : t('environment.scan')}
      </button>
      <p className="text-ui-2xs text-ink-faint">{t('environment.privacy')}</p>

      {error && (
        <p data-testid="environment-error" className="text-ui-xs text-status-danger">
          {error}
        </p>
      )}

      {tools && (
        <div data-testid="environment-scan-status" className="space-y-2">
          {installed.length === 0 ? (
            <p className="text-ui-xs text-ink-faint">{t('environment.noneFound')}</p>
          ) : (
            installed.map((tl) => {
              const models = tl.models.filter((m) => !URL_RE.test(m))
              const visible = models.slice(0, 4)
              return (
                <div
                  key={tl.tool}
                  data-testid={`environment-row-${tl.tool}`}
                  className="glass-reading rounded-xl p-3 space-y-1.5"
                >
                  <div className="flex items-center gap-2">
                    <span
                      data-testid={`environment-icon-${tl.tool}`}
                      aria-hidden="true"
                      className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-brand/20 text-ui-base font-semibold text-foreground/90"
                      style={{
                        background: `linear-gradient(${slugAngle(tl.tool)}deg, color-mix(in oklab, var(--color-brand) 22%, var(--color-canvas)), var(--color-canvas))`,
                      }}
                    >
                      {tl.tool.charAt(0).toUpperCase()}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-ui-xs font-medium text-foreground/90">
                        {tl.tool}
                        <span
                          data-testid={`environment-auth-${tl.tool}`}
                          className={`ml-1.5 rounded-md px-1.5 py-0.5 text-ui-2xs align-middle ${tl.auth_present ? 'bg-status-success/10 text-status-success' : 'bg-surface text-ink-faint'}`}
                        >
                          {tl.auth_present ? t('environment.authYes') : t('environment.authNo')}
                        </span>
                      </p>
                      <p className="text-ui-2xs text-ink-faint">
                        {t('environment.modelsLabel', { count: models.length })}
                      </p>
                    </div>
                  </div>
                  {visible.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {visible.map((m) => {
                        const pick = onPick ? derivePick(tl, m) : null
                        const cls =
                          'rounded-lg px-2 py-1 font-mono text-ui-2xs transition-colors focus-ring'
                        return pick && onPick ? (
                          <button
                            key={m}
                            type="button"
                            data-testid={`environment-model-${tl.tool}-${m}`}
                            onClick={() => onPick(pick!, tl)}
                            className={`${cls} border border-brand/25 bg-brand/10 text-brand hover:bg-brand/20`}
                            title={t('environment.pickHint')}
                          >
                            {m}
                          </button>
                        ) : (
                          <span
                            key={m}
                            data-testid={`environment-model-${tl.tool}-${m}`}
                            className={`${cls} border border-hairline bg-surface-raised text-ink-soft`}
                          >
                            {m}
                          </span>
                        )
                      })}
                      {models.length > visible.length && (
                        <span className="self-center text-ui-2xs text-ink-faint">
                          +{models.length - visible.length}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              )
            })
          )}
          {missing.length > 0 && (
            <p className="text-ui-2xs text-ink-faint">
              {t('environment.alsoFound', { tools: missing.join(', ') })}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
