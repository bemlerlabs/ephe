'use client'

import { Check, Loader2, Trash2, Activity, Plug } from 'lucide-react'
import { putMcpSettings } from '@/lib/api'
import '@/lib/nativeBrowser'
import { toastBus } from '@/lib/toast'
import PageHeader from '@/components/shell/PageHeader'
import '@/components/ui'
import { SettingsGroup } from '@/components/shell/SettingsRow'
import { McpSandboxStrip } from './McpSandboxStrip'
import type { SettingsModel } from './types'

export function renderMcp(model: SettingsModel) {
  const {
    handleMcpHealthCheck,
    mcpHealth,
    mcpHealthLoading,
    mcpLoading,
    mcpSaving,
    mcpServers,
    mcpSource,
    mcpTools,
    setMcpHealth,
    setMcpSaving,
    setMcpServers,
    setMcpSource,
    setMcpTools,
    t,
  } = model
  return (
    <div className="space-y-4">
      {/* E3c: PageHeader + server cards with health dot + curated catalog.
              I7-4: the group texts say what Save does to the list, and the
              catalog speaks the language of the interface. */}
      <PageHeader
        title={t('settings.mcpTitle')}
        subtitle={t('settings.mcpHint')}
        actions={
          <span
            data-testid="mcp-count-pill"
            className="rounded-full bg-brand/15 px-2.5 py-1 text-ui-xs font-medium text-brand-deep"
          >
            {mcpServers.filter((s) => s.trim()).length}
          </span>
        }
      />
      {mcpSource === 'env' && (
        <p className="text-ui-xs text-status-warning/80">{t('settings.mcpEnvOverride')}</p>
      )}
      <SettingsGroup
        icon={Plug}
        title={t('settings.mcpServers')}
        description={t('settings.mcpGroupServersHint')}
        testid="mcp-section-servers"
        action={
          <button
            type="button"
            onClick={handleMcpHealthCheck}
            disabled={mcpHealthLoading || mcpServers.length === 0}
            data-testid="mcp-health-button"
            className="flex shrink-0 items-center gap-1.5 rounded-lg border border-control bg-white/[0.04] px-2.5 py-1.5 text-ui-xs text-foreground/80 transition-colors hover:bg-white/[0.08] disabled:opacity-40 focus-ring"
          >
            {mcpHealthLoading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Activity className="h-3.5 w-3.5" />
            )}
            {t('settings.mcpHealthCheck')}
          </button>
        }
      >
        <div className="space-y-2.5">
          {mcpServers.map((spec, i) => {
            const h = mcpHealth[spec]
            const dotTone =
              !h || h.status === undefined
                ? 'bg-mist/40'
                : h.status === 'ok'
                  ? 'bg-status-success'
                  : 'bg-status-danger'
            return (
              <div
                key={i}
                data-testid={`mcp-server-${i}`}
                className="glass-reading rounded-xl p-3 space-y-1.5"
              >
                <div className="flex items-center gap-2">
                  <span
                    data-testid={`mcp-health-dot-${i}`}
                    title={
                      h
                        ? h.status === 'ok'
                          ? t('settings.mcpHealthOk', {
                              count: h.tool_count,
                              ms: h.latency_ms ?? 0,
                            })
                          : h.error || t('settings.mcpHealthFail')
                        : t('settings.mcpHealthUnknown')
                    }
                    className={`h-2.5 w-2.5 shrink-0 rounded-full ${dotTone}`}
                  />
                  <input
                    type="text"
                    aria-label={`MCP-Server ${i + 1}`}
                    value={spec}
                    onChange={(e) =>
                      setMcpServers((prev) => prev.map((s, j) => (j === i ? e.target.value : s)))
                    }
                    className="min-w-0 flex-1 rounded-lg bg-surface px-2 py-2 text-ui-input font-mono text-foreground/80 outline-none focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-ring focus-visible:outline-offset-2 focus:bg-surface transition-colors max-lg:min-h-11"
                  />
                  <button
                    type="button"
                    onClick={() => setMcpServers((prev) => prev.filter((_, j) => j !== i))}
                    data-testid={`mcp-server-remove-${i}`}
                    className="shrink-0 rounded-lg text-ink-faint hover:text-foreground px-2 py-1.5 text-ui-xs"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
                {h && (
                  <p
                    data-testid={`mcp-health-detail-${i}`}
                    className={`text-ui-2xs ${h.status === 'ok' ? 'text-status-success/80' : 'text-status-danger/80'}`}
                  >
                    {h.status === 'ok'
                      ? t('settings.mcpHealthOk', { count: h.tool_count, ms: h.latency_ms ?? 0 })
                      : h.error || t('settings.mcpHealthFail')}
                  </p>
                )}
                <McpSandboxStrip server={spec || `#${i + 1}`} />
              </div>
            )
          })}
          {mcpServers.length === 0 && (
            <p className="text-ui-xs text-ink-faint">{t('settings.mcpEmpty')}</p>
          )}
        </div>
      </SettingsGroup>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={() => setMcpServers((prev) => [...prev, ''])}
          data-testid="mcp-add"
          className="rounded-lg bg-brand/20 text-brand-deep hover:bg-brand/20 px-3 py-2 text-ui-xs font-medium transition-colors max-lg:min-h-11"
        >
          {t('settings.mcpAdd')}
        </button>
        <button
          type="button"
          disabled={mcpSaving || mcpLoading}
          onClick={() => {
            setMcpSaving(true)
            putMcpSettings(mcpServers.filter((s) => s.trim()))
              .then((r) => {
                setMcpServers(r.servers ?? [])
                setMcpSource(r.source ?? '')
                setMcpTools(r.tools ?? [])
                setMcpHealth({})
              })
              .catch(() => toastBus.error(t('common.changeFailed')))
              .finally(() => setMcpSaving(false))
          }}
          data-testid="mcp-save"
          className="flex items-center gap-1.5 rounded-lg bg-brand/20 text-brand-deep hover:bg-brand/20 px-3 py-2 text-ui-xs font-medium transition-colors disabled:opacity-50 max-lg:min-h-11"
        >
          {mcpSaving ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Check className="h-3.5 w-3.5" />
          )}
          {t('settings.mcpSave')}
        </button>
      </div>
      {mcpTools.length > 0 && (
        <div className="glass-reading rounded-xl p-3 space-y-1 text-ui-xs">
          <span className="text-ink-soft">
            {t('settings.mcpTools')} ({mcpTools.length}):
          </span>
          <p className="block text-ui-2xs text-ink-faint">{t('settings.mcpToolsHint')}</p>
          <div className="flex flex-wrap gap-1.5">
            {mcpTools.map((tool) => (
              <span
                key={tool}
                className="rounded-md bg-surface px-1.5 py-0.5 font-mono text-foreground/70"
              >
                {tool}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
