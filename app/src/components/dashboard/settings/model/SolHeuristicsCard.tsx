'use client'

/**
 * SOL: the rules this workspace learned, read straight from the store file.
 *
 * The list is the file — every edit and every delete here is the same edit and
 * delete a hand edit performs. Nothing is added from this card: a rule comes
 * from a turn that showed the correction working.
 */
import { useEffect, useState } from 'react'
import { Brain, Pencil, Trash2 } from 'lucide-react'
import { SettingsGroup, SettingsRow } from '@/components/shell/SettingsRow'
import {
  deleteSolHeuristic,
  getSolHeuristics,
  updateSolHeuristic,
  type SolHeuristicDto,
} from '@/lib/api/endpoints'

type LoadState = 'idle' | 'loading' | 'failed' | 'ready'

export function SolHeuristicsCard({ t }: { t: (key: string) => string }) {
  const [rules, setRules] = useState<SolHeuristicDto[]>([])
  const [state, setState] = useState<LoadState>('idle')
  const [editing, setEditing] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [confirming, setConfirming] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    setState('loading')
    getSolHeuristics()
      .then((view) => {
        if (!live) return
        setRules(view.heuristics)
        setState('ready')
      })
      .catch(() => {
        if (live) setState('failed')
      })
    return () => {
      live = false
    }
  }, [])

  const save = async (rule: SolHeuristicDto) => {
    const updated = await updateSolHeuristic(rule.id, { action: draft })
    setRules((current) => current.map((item) => (item.id === rule.id ? updated.heuristic : item)))
    setEditing(null)
  }

  const remove = async (rule: SolHeuristicDto) => {
    await deleteSolHeuristic(rule.id)
    setRules((current) => current.filter((item) => item.id !== rule.id))
    setConfirming(null)
  }

  return (
    <SettingsGroup icon={Brain} title={t('settings.solGroup')}>
      {state === 'failed' ? (
        <SettingsRow icon={Brain} title={t('settings.solUnavailable')} description={t('settings.solUnavailableHint')} testid="sol-unavailable">
          <span className="text-ui-xs text-ink-soft">—</span>
        </SettingsRow>
      ) : state !== 'ready' || rules.length === 0 ? (
        <SettingsRow icon={Brain} title={t('settings.solEmpty')} description={t('settings.solEmptyHint')} testid="sol-empty">
          <span className="text-ui-xs text-ink-soft">{state === 'loading' ? '…' : '0'}</span>
        </SettingsRow>
      ) : (
        rules.map((rule) => (
          <SettingsRow
            key={rule.id}
            icon={Brain}
            title={rule.title}
            description={editing === rule.id ? t('settings.solEditHint') : rule.action}
            testid={`sol-rule-${rule.id}`}
          >
            {editing === rule.id ? (
              <span className="flex flex-wrap items-center justify-end gap-2">
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  aria-label={t('settings.solActionLabel')}
                  data-testid={`sol-draft-${rule.id}`}
                  className="min-h-16 w-64 rounded-lg border border-white/10 bg-surface/60 px-2 py-1.5 text-ui-xs text-foreground"
                />
                <button
                  type="button"
                  onClick={() => void save(rule)}
                  data-testid={`sol-save-${rule.id}`}
                  className="rounded-lg bg-brand/20 px-2.5 py-1.5 text-ui-xs font-medium text-brand-deep hover:bg-brand/30 max-lg:min-h-11"
                >
                  {t('settings.solSave')}
                </button>
                <button
                  type="button"
                  onClick={() => setEditing(null)}
                  className="rounded-lg px-2.5 py-1.5 text-ui-xs text-foreground/60 hover:text-foreground max-lg:min-h-11"
                >
                  {t('settings.cancel')}
                </button>
              </span>
            ) : (
              <span className="flex items-center gap-1">
                <button
                  type="button"
                  aria-label={t('settings.solEdit')}
                  data-testid={`sol-edit-${rule.id}`}
                  onClick={() => {
                    setEditing(rule.id)
                    setDraft(rule.action)
                  }}
                  className="rounded-lg p-2 text-foreground/60 transition-colors hover:text-foreground max-lg:min-h-11 max-lg:min-w-11"
                >
                  <Pencil className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
                </button>
                <button
                  type="button"
                  aria-label={confirming === rule.id ? t('settings.solDeleteConfirm') : t('settings.solDelete')}
                  data-testid={`sol-delete-${rule.id}`}
                  onClick={() => (confirming === rule.id ? void remove(rule) : setConfirming(rule.id))}
                  className={`rounded-lg p-2 transition-colors max-lg:min-h-11 max-lg:min-w-11 ${
                    confirming === rule.id
                      ? 'bg-status-danger/20 text-status-danger'
                      : 'text-foreground/60 hover:text-status-danger'
                  }`}
                >
                  <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
                </button>
              </span>
            )}
          </SettingsRow>
        ))
      )}
    </SettingsGroup>
  )
}
