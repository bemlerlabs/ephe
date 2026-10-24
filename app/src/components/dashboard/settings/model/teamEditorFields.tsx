'use client'

import { Check, Users } from 'lucide-react'

import { SettingsGroup } from '@/components/shell/SettingsRow'
import type { AgentRecord, TeamRecord } from '@/lib/api'
import { Field, FIELD, type T } from './teamShared'

export function TeamBasics({
  draft,
  set,
  t,
}: {
  draft: Partial<TeamRecord>
  set: (patch: Partial<TeamRecord>) => void
  t: T
}) {
  return (
    <SettingsGroup icon={Users} title={t('settings.teamGroupBasic')} testid="team-group-basic">
      <div className="grid gap-3 px-4 py-3 sm:grid-cols-2">
        <Field label={t('settings.teamName')}>
          <input
            className={FIELD}
            value={draft.name ?? ''}
            maxLength={80}
            onChange={(e) => set({ name: e.target.value })}
            data-testid="team-name"
          />
        </Field>
        <Field label={t('settings.teamDescription')}>
          <input
            className={FIELD}
            value={draft.description ?? ''}
            maxLength={500}
            onChange={(e) => set({ description: e.target.value })}
            data-testid="team-description"
          />
        </Field>
        <div className="sm:col-span-2">
          <Field label={t('settings.teamInstructions')}>
            <textarea
              className={`${FIELD} min-h-24 resize-y font-mono text-ui-xs leading-relaxed`}
              value={draft.instructions ?? ''}
              maxLength={32000}
              onChange={(e) => set({ instructions: e.target.value })}
              data-testid="team-instructions"
            />
          </Field>
        </div>
      </div>
    </SettingsGroup>
  )
}

export function TeamMembers({
  draft,
  set,
  usable,
  t,
}: {
  draft: Partial<TeamRecord>
  set: (patch: Partial<TeamRecord>) => void
  usable: AgentRecord[]
  t: T
}) {
  const toggleMember = (id: string) => {
    const current = draft.member_ids ?? []
    if (current.includes(id)) {
      set({ member_ids: current.filter((member) => member !== id) })
    } else if (current.length < 4) {
      set({ member_ids: [...current, id] })
    }
  }

  return (
    <SettingsGroup
      icon={Users}
      title={t('settings.teamGroupMembers')}
      description={t('settings.teamMembersHint')}
      testid="team-group-members"
    >
      <div className="space-y-3 px-4 py-3">
        <Field label={t('settings.teamLeader')}>
          <select
            className={FIELD}
            value={draft.leader_id ?? ''}
            onChange={(e) => {
              const leader = e.target.value
              set({
                leader_id: leader,
                member_ids: (draft.member_ids ?? []).filter((id) => id !== leader),
              })
            }}
            data-testid="team-leader"
          >
            <option value="">—</option>
            {usable.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
          </select>
        </Field>
        <div>
          <p className="mb-1.5 text-ui-xs font-medium text-ink-soft">{t('settings.teamMembers')}</p>
          <div className="flex flex-wrap gap-2">
            {usable
              .filter((agent) => agent.id !== draft.leader_id)
              .map((agent) => {
                const active = (draft.member_ids ?? []).includes(agent.id)
                return (
                  <button
                    key={agent.id}
                    type="button"
                    aria-pressed={active}
                    onClick={() => toggleMember(agent.id)}
                    data-testid={`team-member-${agent.id}`}
                    className={`focus-ring inline-flex min-h-8 items-center gap-1.5 rounded-full border px-2.5 py-1 text-ui-xs transition-colors pointer-coarse:min-h-11 ${
                      active
                        ? 'border-brand/40 bg-brand/15 text-brand-deep'
                        : 'border-control bg-surface text-ink-soft hover:text-ink'
                    }`}
                  >
                    {active && <Check className="h-3 w-3" />}
                    {agent.name}
                  </button>
                )
              })}
            {usable.length === 0 && (
              <p className="text-ui-xs text-ink-faint">{t('settings.agentEmpty')}</p>
            )}
          </div>
        </div>
      </div>
    </SettingsGroup>
  )
}

export function TeamMode({
  draft,
  set,
  t,
}: {
  draft: Partial<TeamRecord>
  set: (patch: Partial<TeamRecord>) => void
  t: T
}) {
  return (
    <SettingsGroup icon={Users} title={t('settings.teamGroupMode')} testid="team-group-mode">
      <div className="grid gap-3 px-4 py-3 sm:grid-cols-2">
        <Field label={t('settings.teamOrchestration')}>
          <select
            className={FIELD}
            value={draft.orchestration ?? 'parallel'}
            onChange={(e) => set({ orchestration: e.target.value as TeamRecord['orchestration'] })}
            data-testid="team-orchestration"
          >
            <option value="parallel">{t('settings.teamOrchParallel')}</option>
            <option value="sequential">{t('settings.teamOrchSequential')}</option>
            <option value="review">{t('settings.teamOrchReview')}</option>
            <option value="leader">{t('settings.teamOrchLeader')}</option>
          </select>
        </Field>
        <Field label={t('settings.teamModelPolicy')}>
          <select
            className={FIELD}
            value={draft.model_policy ?? 'inherit'}
            onChange={(e) => set({ model_policy: e.target.value as TeamRecord['model_policy'] })}
            data-testid="team-model-policy"
          >
            <option value="inherit">{t('settings.teamPolicyInherit')}</option>
            <option value="per_member">{t('settings.teamPolicyPerMember')}</option>
            <option value="team">{t('settings.teamPolicyTeam')}</option>
          </select>
        </Field>
        {draft.model_policy === 'team' && (
          <Field label={t('settings.teamModel')}>
            <input
              className={FIELD}
              value={draft.model?.model ?? ''}
              onChange={(e) =>
                set({
                  model: e.target.value.trim()
                    ? { provider: null, model: e.target.value.trim(), tier: 'auto' }
                    : null,
                })
              }
              data-testid="team-model"
            />
          </Field>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label={t('settings.teamMaxRounds')}>
            <input
              type="number"
              min={1}
              max={12}
              className={FIELD}
              value={draft.budget?.max_rounds ?? 4}
              onChange={(e) =>
                set({
                  budget: {
                    max_rounds: Number(e.target.value) || 1,
                    wall_timeout: draft.budget?.wall_timeout ?? 300,
                  },
                })
              }
              data-testid="team-max-rounds"
            />
          </Field>
          <Field label={t('settings.teamWall')}>
            <input
              type="number"
              min={30}
              max={1800}
              step={30}
              className={FIELD}
              value={draft.budget?.wall_timeout ?? 300}
              onChange={(e) =>
                set({
                  budget: {
                    max_rounds: draft.budget?.max_rounds ?? 4,
                    wall_timeout: Number(e.target.value) || 30,
                  },
                })
              }
              data-testid="team-wall"
            />
          </Field>
        </div>
      </div>
    </SettingsGroup>
  )
}
