'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Archive, Plus, RotateCcw, Users, X } from 'lucide-react'

import PageHeader from '@/components/shell/PageHeader'
import { SettingsGroup } from '@/components/shell/SettingsRow'
import SearchInput from '@/components/shell/SearchInput'
import { LoadingRow } from '@/components/ui'
import { toastBus } from '@/lib/toast'
import { createTeam, listAgents, listTeamTemplates, listTeams, setTeamArchived } from '@/lib/api'
import type { AgentRecord, TeamRecord, TeamTemplate } from '@/lib/api'
import { TeamEditor } from './TeamEditor'
import { BUTTON, PRIMARY, TEMPLATE_TEXT } from './teamShared'
import type { SettingsModel } from './types'

export function renderTeams(model: SettingsModel) {
  return <TeamsSection model={model} />
}

export default function TeamsSection({ model }: { model: SettingsModel }) {
  const { t } = model
  const [teams, setTeams] = useState<TeamRecord[] | null>(null)
  const [agents, setAgents] = useState<AgentRecord[]>([])
  const [templates, setTemplates] = useState<TeamTemplate[]>([])
  const [view, setView] = useState<'current' | 'archived'>('current')
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState<TeamRecord | null | undefined>(undefined)
  const [creating, setCreating] = useState(false)
  const [busyId, setBusyId] = useState('')

  const load = useCallback(async () => {
    try {
      const [teamData, agentData, templateData] = await Promise.all([
        listTeams(),
        listAgents(),
        listTeamTemplates(),
      ])
      setTeams(teamData.teams ?? [])
      setAgents(agentData.agents ?? [])
      setTemplates(templateData.templates ?? [])
    } catch (err) {
      toastBus.error(t('settings.teamSaveFailed'), err instanceof Error ? err.message : undefined)
      setTeams([])
    }
  }, [t])

  useEffect(() => {
    void load()
  }, [load])

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return (teams ?? []).filter(
      (team) =>
        team.archived === (view === 'archived') &&
        (!q || team.name.toLowerCase().includes(q) || team.description.toLowerCase().includes(q)),
    )
  }, [teams, query, view])

  const createFromTemplate = async (key: string) => {
    setCreating(false)
    if (!key) {
      setEditing(null)
      return
    }
    const text = TEMPLATE_TEXT[key]
    try {
      const record = await createTeam({
        template: key,
        ...(text
          ? {
              name: t(`settings.${text.name}`),
              description: t(`settings.${text.description}`),
            }
          : {}),
      })
      setEditing(record)
      await load()
    } catch (err) {
      toastBus.error(t('settings.teamSaveFailed'), err instanceof Error ? err.message : undefined)
    }
  }

  const mutate = async (id: string, action: () => Promise<unknown>) => {
    setBusyId(id)
    try {
      await action()
      await load()
    } catch (err) {
      toastBus.error(t('settings.teamSaveFailed'), err instanceof Error ? err.message : undefined)
    } finally {
      setBusyId('')
    }
  }

  if (editing !== undefined) {
    return (
      <TeamEditor
        initial={editing}
        agents={agents}
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
    <div className="space-y-4" data-testid="settings-teams">
      <PageHeader
        title={t('settings.teamsTitle')}
        subtitle={t('settings.teamsHint')}
        actions={
          <button
            type="button"
            className={PRIMARY}
            onClick={() => setCreating(true)}
            data-testid="team-create"
          >
            <Plus className="h-3.5 w-3.5" /> {t('settings.teamCreate')}
          </button>
        }
      />
      {creating && (
        <SettingsGroup
          icon={Users}
          title={t('settings.teamTemplate')}
          description={t('settings.teamTemplateHint')}
          testid="team-template-picker"
        >
          <div className="flex flex-wrap gap-2 px-4 py-3">
            <button type="button" className={BUTTON} onClick={() => void createFromTemplate('')}>
              {t('settings.teamTemplateNone')}
            </button>
            {templates.map((template) => {
              const text = TEMPLATE_TEXT[template.key]
              return (
                <button
                  key={template.key}
                  type="button"
                  className={BUTTON}
                  title={text ? t(`settings.${text.description}`) : template.description}
                  onClick={() => void createFromTemplate(template.key)}
                  data-testid={`team-template-${template.key}`}
                >
                  {text ? t(`settings.${text.name}`) : template.name}
                </button>
              )
            })}
            <button type="button" className={BUTTON} onClick={() => setCreating(false)}>
              <X className="h-3.5 w-3.5" /> {t('settings.teamCancel')}
            </button>
          </div>
        </SettingsGroup>
      )}
      <SearchInput
        value={query}
        onChange={setQuery}
        placeholder={t('settings.teamSearch')}
        label={t('settings.teamSearch')}
        testid="team-search"
      />
      <div className="flex gap-1.5">
        {(['current', 'archived'] as const).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setView(key)}
            aria-pressed={view === key}
            data-testid={`team-tab-${key}`}
            className={`focus-ring rounded-full px-3 py-1 text-ui-xs transition-colors ${
              view === key ? 'bg-brand/15 text-brand-deep' : 'text-ink-faint hover:text-ink'
            }`}
          >
            {key === 'current' ? t('settings.teamCurrent') : t('settings.teamArchivedTab')}
          </button>
        ))}
      </div>
      {teams === null ? (
        <LoadingRow label={t('settings.loading')} />
      ) : rows.length === 0 ? (
        <p className="text-ui-xs text-ink-faint" data-testid="team-empty">
          {t('settings.teamEmpty')}
        </p>
      ) : (
        <SettingsGroup icon={Users} testid="team-list">
          {rows.map((team) => (
            <div
              key={team.id}
              data-testid={`team-row-${team.id}`}
              className="flex flex-col gap-2 border-b border-hairline px-4 py-3 last:border-0 sm:flex-row sm:items-center"
            >
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2 text-ui-sm text-ink">
                  <span className="truncate">{team.name}</span>
                  <span className="rounded-md bg-surface px-1.5 py-0.5 text-ui-2xs text-ink-faint">
                    {t('settings.teamMembersCount', { count: team.member_ids.length })}
                  </span>
                </p>
                <p className="line-clamp-1 text-ui-xs text-ink-faint">
                  {team.description || t('settings.teamPolicyPerMember')}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <button
                  type="button"
                  className={BUTTON}
                  onClick={() => setEditing(team)}
                  data-testid={`team-edit-${team.id}`}
                >
                  {t('settings.agentEdit')}
                </button>
                <button
                  type="button"
                  className={BUTTON}
                  onClick={() =>
                    void mutate(team.id, () => setTeamArchived(team.id, view === 'current'))
                  }
                  disabled={busyId === team.id}
                  data-testid={`team-archive-${team.id}`}
                  title={view === 'current' ? t('settings.teamArchive') : t('settings.teamRestore')}
                  aria-label={`${
                    view === 'current' ? t('settings.teamArchive') : t('settings.teamRestore')
                  } ${team.name}`}
                >
                  {view === 'current' ? (
                    <Archive className="h-3.5 w-3.5" />
                  ) : (
                    <RotateCcw className="h-3.5 w-3.5" />
                  )}
                </button>
              </div>
            </div>
          ))}
        </SettingsGroup>
      )}
    </div>
  )
}
