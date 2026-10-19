import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  BookOpen,
  CalendarClock,
  ChevronDown,
  ChevronRight,
  GitPullRequest,
  Play,
  Plus,
  ShieldAlert,
  Sunrise,
  Trash2,
  AlertTriangle,
} from 'lucide-react'
import type { ScheduleJob, SchedulePreset, ScheduleResult } from '@/lib/api'
import { getSchedulePresets, getScheduleResults, runScheduleJob } from '@/lib/api'
import KeepAwakeToggle from './KeepAwakeToggle'
import { toastBus } from '@/lib/toast'
import { plainPreview } from '@/lib/plainPreview'

interface SchedulerPanelProps {
  jobs: ScheduleJob[]
  onCreate: (task: string, cron: string, delayMinutes?: number, maxRuns?: number) => void
  onDelete: (id: string) => void
}

/**
 * P2-B automation templates: 4 curations as cards — a click fills the create
 * form with prompt + cadence (the form's confirmation pattern).
 * Own texts, i18n-capable (defaultValue = German). Cadence as a cron that
 * createSchedule really accepts (task + cron — nothing invented).
 */
interface AutomationTemplate {
  id: string
  cron: string
  Icon: typeof Sunrise
  title: string
  task: string
  cadence: string
}

const AUTOMATION_TEMPLATES: AutomationTemplate[] = [
  {
    id: 'devBrief',
    cron: '0 9 * * 1-5',
    Icon: Sunrise,
    title: 'Morgendlicher Dev-Brief',
    task: 'Fasse Commits, Modul-Änderungen, CI-Status und offene To-dos seit dem letzten Arbeitstag zusammen.',
    cadence: 'Werktags 09:00',
  },
  {
    id: 'riskScan',
    cron: '0 10 * * *',
    Icon: ShieldAlert,
    title: 'Risiko-Scan',
    task: 'Prüfe die Code-Änderungen der letzten 24 Stunden auf Risiken für Laufzeitfehler und Datenverlust.',
    cadence: 'Täglich 10:00',
  },
  {
    id: 'releaseBrief',
    cron: '0 16 * * 5',
    Icon: GitPullRequest,
    title: 'Release-Brief',
    task: 'Ordne die PRs und Commits der Woche in Features, Fixes und Verbesserungen.',
    cadence: 'Freitags 16:00',
  },
  {
    id: 'docSync',
    cron: '0 15 * * 3',
    Icon: BookOpen,
    title: 'Doku-Abgleich',
    task: 'Gleiche die Code-, Konfigurations- und API-Änderungen der letzten 7 Tage mit der Doku ab.',
    cadence: 'Mittwochs 15:00',
  },
]

/**
 * Scheduler frontend (P2-8) + R19 automation depth: presets as templates,
 * run history with failure surface, manual rerun, toast on new runs.
 * P2-B: template cards (templates section) + keep-awake toggle
 * (keep the machine awake while a chat runs — useKeepAwake).
 */
/** A field with its own label and its own explanation (I7-3). */
function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint: string
  children: React.ReactNode
}) {
  return (
    <label className="min-w-0">
      <span className="mb-0.5 block text-ui-2xs font-medium text-ink-faint">{label}</span>
      {children}
      <span className="mt-0.5 block text-ui-2xs leading-snug text-ink-faint">{hint}</span>
    </label>
  )
}

export default function SchedulerPanel({ jobs, onCreate, onDelete }: SchedulerPanelProps) {
  const { t } = useTranslation()
  const [task, setTask] = useState('')
  const [cron, setCron] = useState('')
  // J4: relative one-shot (minutes from now) + optional run cap
  const [delay, setDelay] = useState('')
  const [maxRuns, setMaxRuns] = useState('')
  // F-24: persist the collapse state. Default: expanded (Settings shows
  // presets/history); in the chat banner F-24 applies (visible only with jobs).
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem('ephe.scheduler.collapsed') === '1',
  )
  const [presets, setPresets] = useState<SchedulePreset[]>([])
  const [results, setResults] = useState<ScheduleResult[] | null>(null)
  const [runningId, setRunningId] = useState<string | null>(null)
  // R40: full detail of a run — bound to the run (job_id + executed_at),
  // not to its list position, so a polled-in new run does not re-hang
  // the open row onto a different run.
  const [openRunKey, setOpenRunKey] = useState<string | null>(null)
  const lastSeenRef = useRef<string | null>(null)

  // Load presets + run history (panel visible); poll history every 30 s
  //
  // D0-4: both lists are read out of the answer, and an engine that has no scheduler
  // answers without them. A missing list is an empty one here — the panel has its own
  // no-jobs state — rather than a tab that falls over.
  useEffect(() => {
    if (collapsed) return
    getSchedulePresets()
      .then((r) => setPresets(r.presets ?? []))
      .catch(() => setPresets([]))
    const load = () => {
      getScheduleResults()
        .then((r) => {
          const newest = (r.results ?? [])[0]
          if (newest && lastSeenRef.current && newest.executed_at !== lastSeenRef.current) {
            toastBus.info(
              newest.error ? t('scheduler.runFailed') : t('scheduler.runFinished'),
              newest.task.slice(0, 80),
            )
          }
          if (newest) lastSeenRef.current = newest.executed_at
          setResults(r.results)
        })
        .catch(() => setResults([]))
    }
    load()
    const id = setInterval(load, 30_000)
    return () => clearInterval(id)
  }, [collapsed, t])

  const submit = () => {
    if (!task.trim()) return
    const delayNum = delay.trim() ? Number(delay.trim()) : undefined
    const runsNum = maxRuns.trim() ? Number(maxRuns.trim()) : undefined
    if (!cron.trim() && !delayNum) return
    onCreate(task.trim(), cron.trim(), delayNum, runsNum)
    setTask('')
    setCron('')
    setDelay('')
    setMaxRuns('')
  }

  const applyPreset = (preset: SchedulePreset) => {
    setTask(preset.task)
    setCron(preset.cron)
    setDelay('')
  }

  // P2-B: template card → prefill the create form with prompt + cadence
  // (the form's confirmation pattern: the user reviews and creates it themselves).
  const applyTemplate = (tpl: AutomationTemplate) => {
    setTask(t(`automation.template.${tpl.id}.task`, { defaultValue: tpl.task }))
    setCron(tpl.cron)
    setDelay('')
    setMaxRuns('')
  }

  const rerun = async (jobId: string) => {
    setRunningId(jobId)
    try {
      const entry = await runScheduleJob(jobId)
      toastBus.success(t('scheduler.runFinished'), (entry.result || entry.task).slice(0, 80))
      setResults((prev) => (prev ? [entry, ...prev].slice(0, 20) : [entry]))
    } catch (e) {
      toastBus.error(t('scheduler.runFailed'), e instanceof Error ? e.message : '')
    } finally {
      setRunningId(null)
    }
  }

  return (
    <div className="rounded-2xl glass-reading overflow-hidden">
      {/* Header — clickable (collapse toggle) */}
      <button
        onClick={() => {
          setCollapsed((v) => {
            localStorage.setItem('ephe.scheduler.collapsed', v ? '0' : '1')
            return !v
          })
        }}
        aria-expanded={!collapsed}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-brand/80 hover:text-brand text-ui-sm font-medium transition-colors"
      >
        <CalendarClock className="h-4 w-4 shrink-0" />
        <span className="flex-1 text-left">{t('scheduler.title')}</span>
        {jobs.length > 0 && (
          <span className="text-ui-2xs bg-surface-raised px-1.5 py-0.5 rounded-full text-ink-soft">
            {jobs.length}
          </span>
        )}
        {collapsed ? (
          <ChevronRight className="h-3.5 w-3.5" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5" />
        )}
      </button>

      {!collapsed && (
        <div className="p-4 pt-0 space-y-3">
          {/* R19: automation templates (offline index) */}
          {presets.length > 0 && (
            <div
              className="flex flex-wrap gap-1.5"
              role="group"
              aria-label={t('scheduler.presets')}
            >
              {presets.map((p) => (
                <button
                  key={p.id}
                  onClick={() => applyPreset(p)}
                  title={p.task}
                  className="px-2 py-1 rounded-md text-ui-xs font-medium bg-surface text-ink-faint hover:text-brand hover:bg-brand/10 transition-colors"
                >
                  {t(`automation.preset.${p.id}.title`, { defaultValue: p.title })}
                </button>
              ))}
            </div>
          )}

          {/* P2-B: template cards — a click fills the create form */}
          <div className="space-y-1.5">
            <h4 className="text-ui-xs font-medium text-foreground/50 uppercase tracking-wide">
              {t('automation.templates', { defaultValue: 'Templates' })}
            </h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
              {AUTOMATION_TEMPLATES.map((tpl, i) => (
                <button
                  key={tpl.id}
                  type="button"
                  data-testid={`automation-template-${i}`}
                  onClick={() => applyTemplate(tpl)}
                  className="text-left rounded-xl border border-control bg-surface hover:bg-brand/10 hover:border-brand/30 px-3 py-2 transition-colors group"
                >
                  <span className="flex items-center gap-1.5 text-ui-sm font-medium text-foreground/80 group-hover:text-brand">
                    <tpl.Icon className="h-3.5 w-3.5 shrink-0" />
                    {t(`automation.template.${tpl.id}.title`, { defaultValue: tpl.title })}
                  </span>
                  <span className="block text-ui-xs text-ink-soft mt-0.5 line-clamp-2">
                    {t(`automation.template.${tpl.id}.task`, { defaultValue: tpl.task })}
                  </span>
                  <span className="block text-ui-2xs text-brand/60 mt-1 font-mono">
                    {t(`automation.template.${tpl.id}.cadence`, { defaultValue: tpl.cadence })}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-x-3 gap-y-2 max-sm:grid-cols-1">
            <Field label={t('scheduler.taskLabel')} hint={t('scheduler.taskFieldHint')}>
              <input
                value={task}
                onChange={(e) => setTask(e.target.value)}
                placeholder={t('scheduler.taskPlaceholder')}
                aria-label={t('scheduler.taskLabel')}
                className="w-full min-w-0 rounded-lg bg-surface px-2 py-1.5 text-ui-sm text-foreground outline-none placeholder:text-ink-faint focus-ring"
              />
            </Field>
            <Field label={t('scheduler.cronLabel')} hint={t('scheduler.cronFieldHint')}>
              <input
                value={cron}
                onChange={(e) => setCron(e.target.value)}
                placeholder={t('scheduler.cronPlaceholder')}
                aria-label={t('scheduler.cronLabel')}
                className="w-full min-w-0 rounded-lg bg-surface px-2 py-1.5 font-mono text-ui-sm text-foreground outline-none placeholder:text-ink-faint focus-ring"
              />
            </Field>
            <Field label={t('scheduler.delayLabel')} hint={t('scheduler.delayFieldHint')}>
              <input
                value={delay}
                onChange={(e) => setDelay(e.target.value)}
                placeholder={t('scheduler.delayPlaceholder')}
                aria-label={t('scheduler.delayLabel')}
                className="w-full min-w-0 rounded-lg bg-surface px-2 py-1.5 font-mono text-ui-sm text-foreground outline-none placeholder:text-ink-faint focus-ring"
              />
            </Field>
            <Field label={t('scheduler.maxRunsLabel')} hint={t('scheduler.maxRunsFieldHint')}>
              <input
                value={maxRuns}
                onChange={(e) => setMaxRuns(e.target.value)}
                placeholder={t('scheduler.maxRunsPlaceholder')}
                aria-label={t('scheduler.maxRunsLabel')}
                className="w-full min-w-0 rounded-lg bg-surface px-2 py-1.5 font-mono text-ui-sm text-foreground outline-none placeholder:text-ink-faint focus-ring"
              />
            </Field>
            <div className="col-span-2 flex justify-end max-sm:col-span-1">
              <button
                onClick={submit}
                title={t('scheduler.createJob')}
                aria-label={t('scheduler.createJob')}
                data-testid="scheduler-create"
                disabled={!task.trim() || (!cron.trim() && !delay.trim())}
                className="flex items-center gap-1.5 rounded-lg bg-brand px-3 py-1.5 text-ui-xs font-medium text-black transition-colors hover:bg-brand-glow disabled:cursor-not-allowed disabled:opacity-30 max-lg:min-h-11"
              >
                <Plus className="h-3.5 w-3.5" />
                {t('scheduler.createJob')}
              </button>
            </div>
          </div>
          <p className="text-ui-xs leading-relaxed text-ink-faint">{t('scheduler.formHint')}</p>
          {jobs.length === 0 && (
            <p data-testid="automation-empty" className="text-ui-xs text-ink-faint">
              {t('automation.empty', { defaultValue: 'No scheduled tasks yet.' })}
            </p>
          )}
          {/* P2-B keep-awake: honest — disabled without a mechanism (hint),
              active only while a chat is streaming (useKeepAwake). */}
          <KeepAwakeToggle />
          {jobs.length > 0 && (
            <div className="space-y-1.5">
              {jobs.map((job) => (
                <div key={job.id} className="flex items-center gap-2 text-ui-sm text-foreground/70">
                  <span className="flex-1 min-w-0 truncate" title={job.task}>
                    {job.task}
                  </span>
                  <span className="font-mono text-ui-xs text-ink-soft">{job.cron}</span>
                  {job.max_runs ? (
                    <span className="font-mono text-ui-2xs text-ink-faint">≤{job.max_runs}×</span>
                  ) : null}
                  {job.next_run && (
                    <span className="font-mono text-ui-xs text-brand/60">{job.next_run}</span>
                  )}
                  <button
                    onClick={() => void rerun(job.id)}
                    disabled={runningId === job.id}
                    title={t('scheduler.runNow')}
                    aria-label={t('scheduler.runNow')}
                    data-testid={`scheduler-run-${job.id}`}
                    className="p-1 rounded hover:text-brand text-ink-soft transition-colors disabled:opacity-40"
                  >
                    <Play className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => onDelete(job.id)}
                    title={t('scheduler.deleteJob', { id: job.id })}
                    className="p-1 rounded hover:text-status-danger text-ink-soft transition-colors"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
          {/* R19: run history with failure surface */}
          {results && results.length > 0 && (
            <div className="border-t border-hairline pt-2 space-y-1">
              <h4 className="text-ui-xs font-medium text-foreground/50 uppercase tracking-wide">
                {t('scheduler.history')}
              </h4>
              {results.map((res, i) => {
                const runKey = `${res.job_id}-${res.executed_at}`
                const isOpen = openRunKey === runKey
                const failed = !!res.error
                const body = failed ? res.error : res.result
                return (
                  <div key={`${runKey}-${i}`} className="text-ui-xs">
                    <button
                      type="button"
                      aria-expanded={isOpen}
                      data-testid={`scheduler-run-row-${i}`}
                      onClick={() => setOpenRunKey(isOpen ? null : runKey)}
                      className="flex w-full items-start gap-2 text-left"
                    >
                      {failed ? (
                        <AlertTriangle className="h-3.5 w-3.5 text-status-danger shrink-0 mt-0.5" />
                      ) : (
                        <span className="h-1.5 w-1.5 rounded-full bg-status-success/70 mt-1.5 shrink-0" />
                      )}
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-2">
                          <span className="truncate text-foreground/70">{res.task}</span>
                          <span className="font-mono text-ui-2xs text-ink-faint shrink-0">
                            {res.executed_at.slice(0, 16).replace('T', ' ')}
                          </span>
                        </span>
                        {body && !isOpen && (
                          <span
                            className={`block truncate ${failed ? 'text-status-danger/80' : 'text-ink-soft'}`}
                          >
                            {plainPreview(body)}
                          </span>
                        )}
                      </span>
                    </button>
                    {isOpen && (
                      <div
                        data-testid={`scheduler-run-detail-${i}`}
                        className="mt-1 mb-1.5 ml-5 rounded-lg bg-surface px-2.5 py-2"
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <span
                            className={`text-ui-2xs font-medium ${failed ? 'text-status-danger' : 'text-status-success'}`}
                          >
                            {failed ? t('scheduler.runFailed') : t('scheduler.runFinished')}
                          </span>
                          <span className="font-mono text-ui-2xs text-ink-faint">
                            {res.executed_at}
                          </span>
                        </div>
                        <p className="whitespace-pre-wrap break-words text-ink-soft">
                          {body || t('scheduler.noOutput')}
                        </p>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * R40 mobile pill — compact surface for scheduled tasks in the chat area.
 * Parity with the DD-10 pattern (StatusBar): an equal md:hidden counterpart to
 * the full SchedulerPanel (md:block), so mobile sees the same information
 * without the ~32px banner pushing the welcome area below the fold. The
 * pill shows the job count + the soonest run and opens the cron surface.
 */
export function SchedulerMobilePill({ jobs, onOpen }: { jobs: ScheduleJob[]; onOpen: () => void }) {
  const { t } = useTranslation()
  const runs = jobs
    .map((j) => j.next_run)
    .filter((s): s is string => Boolean(s))
    .sort()
  // ISO-like strings ("2026-08-09 08:00…") — lexicographic sort gives
  // the soonest run; trimmed to the minute so the pill stays compact.
  const soonest = runs[0]?.slice(0, 16)
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={t('scheduler.open')}
      data-testid="scheduler-mobile-pill"
      className="md:hidden flex items-center gap-2 px-3 py-2 rounded-2xl glass-control text-ui-sm text-brand/80 hover:text-brand transition-colors"
    >
      <CalendarClock className="h-4 w-4 shrink-0" />
      <span className="flex-1 text-left">{t('scheduler.title')}</span>
      {soonest && <span className="font-mono text-ui-2xs text-ink-faint">{soonest}</span>}
      <span className="text-ui-2xs bg-surface-raised px-1.5 py-0.5 rounded-full text-ink-soft">
        {jobs.length}
      </span>
    </button>
  )
}
