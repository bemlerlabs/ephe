'use client'

import { useMemo, useState } from 'react'
import { Check, Loader2 } from 'lucide-react'

import { toastBus } from '@/lib/toast'
import { createTeam, updateTeam } from '@/lib/api'
import type { AgentRecord, TeamRecord } from '@/lib/api'
import { TeamBasics, TeamMembers, TeamMode } from './teamEditorFields'
import { TeamRunPanel } from './TeamRunPanel'
import { BLANK, BUTTON, PRIMARY, type T } from './teamShared'

export function TeamEditor({
  initial,
  agents,
  t,
  onClose,
  onSaved,
}: {
  initial: TeamRecord | null
  agents: AgentRecord[]
  t: T
  onClose: () => void
  onSaved: (record: TeamRecord) => void
}) {
  const [draft, setDraft] = useState<Partial<TeamRecord>>(() =>
    initial ? { ...initial } : { ...BLANK },
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const usable = useMemo(
    () => agents.filter((agent) => !agent.archived && agent.enabled && agent.id !== 'ephe'),
    [agents],
  )

  const set = (patch: Partial<TeamRecord>) => setDraft((prev) => ({ ...prev, ...patch }))

  const save = async () => {
    setError('')
    if (!(draft.name ?? '').trim() || !draft.leader_id || !(draft.member_ids ?? []).length) {
      setError(t('settings.teamMembersHint'))
      return
    }
    setSaving(true)
    try {
      const payload: Partial<TeamRecord> = {
        name: draft.name,
        description: draft.description,
        instructions: draft.instructions,
        leader_id: draft.leader_id,
        member_ids: draft.member_ids,
        orchestration: draft.orchestration,
        model_policy: draft.model_policy,
        model: draft.model ?? null,
        budget: draft.budget,
        shared_context: draft.shared_context,
      }
      const saved =
        initial && initial.id
          ? await updateTeam(initial.id, payload, initial.etag ?? '')
          : await createTeam(payload)
      toastBus.success(t('settings.teamSaved'))
      onSaved(saved)
    } catch (err) {
      setError(err instanceof Error ? err.message : t('settings.teamSaveFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4" data-testid="team-editor">
      <div className="flex flex-wrap items-center gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-display text-xl font-semibold text-foreground/95">
            {(draft.name ?? '').trim() || t('settings.teamNewName')}
          </h3>
          <p className="mt-0.5 text-ui-xs text-ink-faint">
            {t('settings.teamMembersCount', { count: (draft.member_ids ?? []).length })}
          </p>
        </div>
        <button type="button" className={BUTTON} onClick={onClose} data-testid="team-cancel">
          {t('settings.teamCancel')}
        </button>
        <button
          type="button"
          className={PRIMARY}
          onClick={() => void save()}
          disabled={saving}
          data-testid="team-save"
        >
          {saving ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Check className="h-3.5 w-3.5" />
          )}
          {saving ? t('settings.teamSaving') : t('settings.teamSave')}
        </button>
      </div>
      {error && (
        <p role="alert" data-testid="team-error" className="text-ui-xs text-status-danger">
          {error}
        </p>
      )}

      <TeamBasics draft={draft} set={set} t={t} />
      <TeamMembers draft={draft} set={set} usable={usable} t={t} />
      <TeamMode draft={draft} set={set} t={t} />
      {initial?.id && <TeamRunPanel teamId={initial.id} t={t} />}
    </div>
  )
}
