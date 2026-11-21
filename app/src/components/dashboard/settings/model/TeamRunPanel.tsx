'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Loader2, Play, X } from 'lucide-react'

import { SettingsGroup } from '@/components/shell/SettingsRow'
import { toastBus } from '@/lib/toast'
import { cancelTeamRun, getTeamRun, listTeamRuns, runTeam } from '@/lib/api'
import type { TeamRunResult, TeamRunSummary } from '@/lib/api'
import { BUTTON, FIELD, PRIMARY, runId, type T } from './teamShared'

export function TeamRunPanel({ teamId, t }: { teamId: string; t: T }) {
  const [task, setTask] = useState('')
  const [running, setRunning] = useState(false)
  const [activeRun, setActiveRun] = useState('')
  const [runStatus, setRunStatus] = useState('')
  const [result, setResult] = useState<TeamRunResult | null>(null)
  const [runs, setRuns] = useState<TeamRunSummary[]>([])
  const pollRef = useRef<number | null>(null)

  const loadRuns = useCallback(async (id: string) => {
    try {
      setRuns((await listTeamRuns(id)).runs)
    } catch {
      setRuns([])
    }
  }, [])

  useEffect(() => {
    void loadRuns(teamId)
  }, [teamId, loadRuns])

  useEffect(
    () => () => {
      if (pollRef.current !== null) window.clearInterval(pollRef.current)
    },
    [],
  )

  const startRun = async () => {
    if (!task.trim()) return
    const id = runId()
    setRunning(true)
    setResult(null)
    setRunStatus('running')
    setActiveRun(id)
    pollRef.current = window.setInterval(() => {
      void getTeamRun(id)
        .then((state) => setRunStatus(state.status))
        .catch(() => undefined)
    }, 1500)
    try {
      const answer = await runTeam(teamId, task.trim(), undefined, id)
      setResult(answer)
      await loadRuns(teamId)
    } catch (err) {
      toastBus.error(t('settings.teamRunFailed'), err instanceof Error ? err.message : undefined)
    } finally {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current)
        pollRef.current = null
      }
      setRunning(false)
      setActiveRun('')
      setRunStatus('')
    }
  }

  const cancel = async () => {
    if (!activeRun) return
    try {
      await cancelTeamRun(activeRun)
    } catch {
      /* the run may have finished between the click and the request */
    }
  }

  return (
    <SettingsGroup icon={Play} title={t('settings.teamRun')} testid="team-group-run">
      <div className="space-y-2 px-4 py-3">
        <textarea
          className={`${FIELD} min-h-20 resize-y`}
          value={task}
          maxLength={8000}
          placeholder={t('settings.teamRunPlaceholder')}
          onChange={(e) => setTask(e.target.value)}
          data-testid="team-run-task"
        />
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className={PRIMARY}
            onClick={() => void startRun()}
            disabled={running || !task.trim()}
            data-testid="team-run-start"
          >
            {running ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            {running ? t('settings.teamRunning') : t('settings.teamRunStart')}
          </button>
          {running && runStatus && (
            <span className="text-ui-2xs text-ink-faint" data-testid="team-run-status">
              {runStatus}
            </span>
          )}
          {running && (
            <button type="button" className={BUTTON} onClick={() => void cancel()}>
              <X className="h-3.5 w-3.5" /> {t('settings.teamCancelRun')}
            </button>
          )}
          {result?.budget_hit && (
            <span className="text-ui-xs text-status-warning">{t('settings.teamBudgetHit')}</span>
          )}
        </div>
        {result && (
          <div className="space-y-2" data-testid="team-run-result">
            <p className="text-ui-2xs text-ink-faint">
              {result.status} · {result.members.length} · {result.duration_ms ?? 0} ms
            </p>
            <pre className="glass-reading max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-xl p-3 text-ui-xs text-foreground/90">
              {result.report}
            </pre>
            <div className="space-y-1">
              {result.members.map((member) => (
                <div
                  key={member.agent_id}
                  className="flex flex-wrap items-center gap-2 text-ui-2xs text-ink-soft"
                >
                  <span className="font-medium">{member.name}</span>
                  <span className="text-ink-faint">{member.role ?? 'member'}</span>
                  <span>{member.status}</span>
                  <span className="text-ink-faint">
                    {member.model || '—'} · {member.duration_ms} ms · {member.tool_calls} tools
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
        {runs.length > 0 && (
          <div className="space-y-1 pt-1">
            <p className="text-ui-xs font-medium text-ink-soft">{t('settings.teamRuns')}</p>
            {runs.map((run) => (
              <div
                key={run.run_id}
                className="flex flex-wrap items-center gap-2 text-ui-2xs text-ink-faint"
              >
                <span className="font-mono">{run.finished_at}</span>
                <span>{run.status}</span>
                <span>
                  {run.members} · {run.duration_ms} ms
                </span>
              </div>
            ))}
          </div>
        )}
        {runs.length === 0 && (
          <p className="text-ui-xs text-ink-faint">{t('settings.teamNoRuns')}</p>
        )}
      </div>
    </SettingsGroup>
  )
}
