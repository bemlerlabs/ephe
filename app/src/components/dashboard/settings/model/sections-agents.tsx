'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Archive, Bot, Copy, FolderInput, Pencil, Plus, RotateCcw } from 'lucide-react'

import PageHeader from '@/components/shell/PageHeader'
import { SettingsGroup } from '@/components/shell/SettingsRow'
import SearchInput from '@/components/shell/SearchInput'
import Switch from '@/components/shell/Switch'
import { LoadingRow } from '@/components/ui'
import { toastBus } from '@/lib/toast'
import { importPickedFolder } from '@/lib'
import { isDesktopShell } from '@/lib/tauriBridge'
import {
  duplicateAgent,
  getModelProviders,
  listAgentTools,
  listAgents,
  setAgentArchived,
  updateAgent,
} from '@/lib/api'
import type { AgentRecord, AgentTool } from '@/lib/api'
import { AgentEditor } from './AgentEditor'
import { agentAvatar, BUTTON, initials, originLabel, PRIMARY } from './agentShared'
import type { SettingsModel } from './types'

export function renderAgents(model: SettingsModel) {
  return <AgentsSection model={model} />
}

export default function AgentsSection({ model }: { model: SettingsModel }) {
  const { t } = model
  const [list, setList] = useState<AgentRecord[] | null>(null)
  const [quarantined, setQuarantined] = useState<Record<string, string>>({})
  const [tools, setTools] = useState<AgentTool[]>([])
  const [models, setModels] = useState<string[]>([])
  const [provider, setProvider] = useState('')
  const [view, setView] = useState<'current' | 'archived'>('current')
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState<AgentRecord | null | undefined>(undefined)
  const [busyId, setBusyId] = useState('')

  const load = useCallback(async () => {
    try {
      const [data, toolData] = await Promise.all([listAgents(), listAgentTools()])
      setList(data.agents ?? [])
      setQuarantined(data.quarantined ?? {})
      setTools(toolData.tools ?? [])
    } catch (err) {
      toastBus.error(t('settings.agentSaveFailed'), err instanceof Error ? err.message : undefined)
      setList([])
    }
  }, [t])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    // One probe per visit: the model list is a picker aid, not part of a save.
    void getModelProviders()
      .then((data) => {
        setModels(data.local_models ?? [])
        setProvider(data.active?.type ?? '')
      })
      .catch(() => undefined)
  }, [])

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (list ?? []).filter(
      (agent) =>
        agent.archived === (view === 'archived') &&
        (!q || agent.name.toLowerCase().includes(q) || agent.description.toLowerCase().includes(q)),
    )
  }, [list, query, view])

  const mutate = async (id: string, action: () => Promise<unknown>) => {
    setBusyId(id)
    try {
      await action()
      await load()
    } catch (err) {
      toastBus.error(t('settings.agentSaveFailed'), err instanceof Error ? err.message : undefined)
    } finally {
      setBusyId('')
    }
  }

  if (editing !== undefined) {
    return (
      <AgentEditor
        initial={editing}
        tools={tools}
        models={models}
        provider={provider}
        t={t}
        onClose={() => setEditing(undefined)}
        onSaved={() => {
          setEditing(undefined)
          void load()
        }}
      />
    )
  }

  return (
    <div className="space-y-4" data-testid="settings-agents">
      <PageHeader
        title={t('settings.agentsTitle')}
        subtitle={t('settings.agentsHint')}
        actions={
          <>
            {/* M2: an AGENT.md folder from another agent framework, imported where the
                agents live — the tour already does this once, this is the second door. */}
            {isDesktopShell() && (
              <button
                type="button"
                className={BUTTON}
                data-testid="agent-import"
                onClick={() => {
                  void importPickedFolder()
                    .then((outcome) => {
                      if (!outcome) return
                      toastBus.success(
                        t('settings.agentImportDone', {
                          skills: outcome.skills,
                          servers: outcome.servers,
                        }),
                      )
                    })
                    .catch(() => toastBus.error(t('settings.agentImportFailed')))
                }}
              >
                <FolderInput className="h-3.5 w-3.5" /> {t('settings.agentImport')}
              </button>
            )}
            <button
              type="button"
              className={PRIMARY}
              onClick={() => setEditing(null)}
              data-testid="agent-create"
            >
              <Plus className="h-3.5 w-3.5" /> {t('settings.agentCreate')}
            </button>
          </>
        }
      />
      <SearchInput
        value={query}
        onChange={setQuery}
        placeholder={t('settings.agentSearch')}
        label={t('settings.agentSearch')}
        testid="agent-search"
      />
      <div className="flex gap-1.5">
        {(['current', 'archived'] as const).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setView(key)}
            aria-pressed={view === key}
            data-testid={`agent-tab-${key}`}
            className={`focus-ring rounded-full px-3 py-1 text-ui-xs transition-colors ${
              view === key ? 'bg-brand/15 text-brand-deep' : 'text-ink-faint hover:text-ink'
            }`}
          >
            {key === 'current' ? t('settings.agentCurrent') : t('settings.agentArchivedTab')}
          </button>
        ))}
      </div>
      {list === null ? (
        <LoadingRow label={t('settings.loading')} />
      ) : rows.length === 0 ? (
        <p className="text-ui-xs text-ink-faint" data-testid="agent-empty">
          {t('settings.agentEmpty')}
        </p>
      ) : (
        <SettingsGroup icon={Bot} testid="agent-list">
          {rows.map((agent) => (
            <div
              key={agent.id}
              data-testid={`agent-row-${agent.id}`}
              className="flex flex-col gap-2 border-b border-hairline px-4 py-3 last:border-0 sm:flex-row sm:items-center"
            >
              <span
                aria-hidden="true"
                className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-ui-xs font-semibold text-white ${agentAvatar(agent.name)}`}
              >
                {initials(agent.name)}
              </span>
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2 text-ui-sm text-ink">
                  <span className="truncate">{agent.name}</span>
                  <span className="rounded-md bg-surface px-1.5 py-0.5 text-ui-2xs text-ink-faint">
                    {originLabel(agent.origin, t)}
                  </span>
                  {agent.model?.model && (
                    <span className="font-mono text-ui-2xs text-ink-faint">
                      {agent.model.model}
                    </span>
                  )}
                </p>
                <p className="line-clamp-1 text-ui-xs text-ink-faint">
                  {agent.origin === 'ephe'
                    ? t('settings.agentDefaultDescription')
                    : agent.description ||
                      t('settings.agentToolsCount', { count: agent.tools.length })}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {!agent.read_only && (
                  <Switch
                    checked={agent.enabled}
                    label={t('settings.agentAvailable')}
                    testid={`agent-toggle-${agent.id}`}
                    busy={busyId === agent.id}
                    onChange={(next) =>
                      void mutate(agent.id, () =>
                        updateAgent(agent.id, { enabled: next }, agent.etag ?? ''),
                      )
                    }
                  />
                )}
                {!agent.read_only && (
                  <button
                    type="button"
                    className={BUTTON}
                    onClick={() => setEditing(agent)}
                    data-testid={`agent-edit-${agent.id}`}
                  >
                    <Pencil className="h-3.5 w-3.5" /> {t('settings.agentEdit')}
                  </button>
                )}
                <button
                  type="button"
                  className={BUTTON}
                  onClick={() =>
                    void mutate(agent.id, async () => {
                      const copy = await duplicateAgent(agent.id)
                      setEditing(copy)
                    })
                  }
                  disabled={busyId === agent.id}
                  data-testid={`agent-duplicate-${agent.id}`}
                  title={t('settings.agentDuplicate')}
                  aria-label={`${t('settings.agentDuplicate')} ${agent.name}`}
                >
                  <Copy className="h-3.5 w-3.5" />
                </button>
                {!agent.read_only && (
                  <button
                    type="button"
                    className={BUTTON}
                    onClick={() =>
                      void mutate(agent.id, () => setAgentArchived(agent.id, view === 'current'))
                    }
                    disabled={busyId === agent.id}
                    data-testid={`agent-archive-${agent.id}`}
                    title={
                      view === 'current' ? t('settings.agentArchive') : t('settings.agentRestore')
                    }
                    aria-label={`${
                      view === 'current' ? t('settings.agentArchive') : t('settings.agentRestore')
                    } ${agent.name}`}
                  >
                    {view === 'current' ? (
                      <Archive className="h-3.5 w-3.5" />
                    ) : (
                      <RotateCcw className="h-3.5 w-3.5" />
                    )}
                  </button>
                )}
              </div>
            </div>
          ))}
        </SettingsGroup>
      )}
      {Object.entries(quarantined).length > 0 && (
        <p className="text-ui-2xs text-status-warning">
          {Object.entries(quarantined)
            .map(([file, reason]) => `${file}: ${reason}`)
            .join(' · ')}
        </p>
      )}
    </div>
  )
}
