/**
 * R3: the tools Ephe registers, each with the gate's own verdict.
 *
 * `safe` comes from the server, which reads `SAFE_TOOLS` — the list that decides a
 * call runs without a prompt. The row therefore cannot claim a freedom the guard
 * would refuse. A server without the block renders nothing.
 *
 * The switch beside a row is the same decision the guard reads: off hides the tool
 * from the model and refuses a deferred call by name. A locked row is one of the
 * four bridge tools, without which the turn could not reach its own tools.
 */
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Code2,
  FileText,
  FolderOpen,
  Globe,
  Lock,
  Plus,
  Search,
  ShieldCheck,
  Terminal,
  Users,
  Wrench,
  X,
} from 'lucide-react'
import { Button, Card } from '@/components/ui'
import {
  getCapabilities,
  setCapability,
  setSubagentAllowlist,
  type ToolCatalogRow,
} from '@/lib/api'

const ICONS: Record<string, typeof Wrench> = {
  read_file: FileText,
  edit_file: FileText,
  write_file: FileText,
  list_directory: FolderOpen,
  file_search: Search,
  fetch_url: Globe,
  browser_go: Globe,
  browser_screenshot: Globe,
  execute_code: Code2,
  run_shell: Terminal,
  spawn_agent: Users,
  agent_message: Users,
}

function iconFor(name: string) {
  return ICONS[name] ?? Wrench
}

/** The catalogue reads in families, not as one 74-row table. The classifier uses
 *  the verb the tool's own name carries, so a new tool lands in a group without
 *  a second list to maintain. */
type Family = 'files' | 'web' | 'system' | 'media' | 'agents' | 'other'

const FAMILY_ORDER: Family[] = ['files', 'web', 'system', 'media', 'agents', 'other']

const MEDIA_TOKENS = /(pptx|docx|pdf|xlsx|svg|deck|chart|diagram|notebook|image|video|audio|qr|slide)/

function familyOf(name: string): Family {
  const n = name.toLowerCase()
  if (/^(browser_|fetch_|web_)/.test(n)) return 'web'
  if (MEDIA_TOKENS.test(n)) return 'media'
  if (/^(read_|write_|edit_|list_|file_|glob|grep|patch|search_|clipboard_)/.test(n)) return 'files'
  if (/^(run_|execute_|shell|system_|process_|code_)/.test(n)) return 'system'
  if (
    /^(create_|generate_|render_|export_|import_|analyze_image|take_screenshot|vision_|audio|tts|stt|record_)/.test(
      n,
    )
  )
    return 'media'
  if (/^(spawn_|agent_|task_|delegate|ask_user|manage_tasks)/.test(n)) return 'agents'
  return 'other'
}

/** The switch a row carries: on, off, or locked on by the turn's own needs. */
function CapabilitySwitch({
  row,
  busy,
  t,
  onToggle,
}: {
  row: ToolCatalogRow
  busy: boolean
  t: (key: string, options?: Record<string, unknown>) => string
  onToggle: (next: boolean) => void
}) {
  const enabled = row.enabled !== false
  if (row.locked) {
    return (
      <span
        data-testid={`tool-lock-${row.name}`}
        title={t('tools.switchLocked')}
        className="shrink-0 text-ink-faint"
      >
        <Lock className="h-3.5 w-3.5" strokeWidth={1.5} aria-hidden="true" />
      </span>
    )
  }
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      aria-label={t('tools.switchLabel', { name: row.name })}
      data-testid={`tool-switch-${row.name}`}
      disabled={busy}
      onClick={() => onToggle(!enabled)}
      className={`relative h-4 w-7 shrink-0 rounded-full border transition-colors pointer-coarse:h-6 pointer-coarse:w-10 ${
        enabled ? 'border-brand/50 bg-brand/25' : 'border-ink-faint/40 bg-surface/60'
      } ${busy ? 'opacity-50' : ''}`}
    >
      <span
        className={`absolute top-0.5 h-2.5 w-2.5 rounded-full transition-all pointer-coarse:top-1 pointer-coarse:h-3.5 pointer-coarse:w-3.5 ${
          enabled ? 'left-3.5 bg-brand-glow pointer-coarse:left-5' : 'left-0.5 bg-ink-faint'
        }`}
      />
    </button>
  )
}

export function ToolCatalog() {
  const { t } = useTranslation()
  const [rows, setRows] = useState<ToolCatalogRow[] | null>(null)
  const [filter, setFilter] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState(false)
  const [extra, setExtra] = useState<string[] | null>(null)
  const [base, setBase] = useState<string[]>([])
  const [pick, setPick] = useState('')

  useEffect(() => {
    let alive = true
    getCapabilities()
      .then((view) => {
        if (!alive) return
        setRows(view.tools?.tools ?? null)
        setBase(view.subagent.base_tools ?? [])
        setExtra(view.subagent.extra_tools ?? null)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [])

  const shown = useMemo(() => {
    if (!rows) return []
    const needle = filter.trim().toLowerCase()
    if (!needle) return rows
    return rows.filter(
      (row) =>
        row.name.toLowerCase().includes(needle) ||
        row.description.toLowerCase().includes(needle),
    )
  }, [rows, filter])

  const groups = useMemo(() => {
    const buckets = new Map<Family, ToolCatalogRow[]>()
    for (const row of shown) {
      const family = familyOf(row.name)
      const bucket = buckets.get(family)
      if (bucket) bucket.push(row)
      else buckets.set(family, [row])
    }
    return FAMILY_ORDER.filter((family) => buckets.has(family)).map((family) => ({
      family,
      rows: buckets.get(family)!,
    }))
  }, [shown])

  if (!rows || rows.length === 0) return null
  const safe = rows.filter((row) => row.safe).length
  const on = rows.filter((row) => row.enabled !== false).length

  async function toggle(row: ToolCatalogRow, next: boolean) {
    setBusy(row.name)
    setError(false)
    setRows((current) =>
      current
        ? current.map((entry) => (entry.name === row.name ? { ...entry, enabled: next } : entry))
        : current,
    )
    try {
      await setCapability(row.name, next)
    } catch {
      setError(true)
      setRows((current) =>
        current
          ? current.map((entry) =>
              entry.name === row.name ? { ...entry, enabled: !next } : entry,
            )
          : current,
      )
    } finally {
      setBusy(null)
    }
  }

  async function editAllowlist(names: string[]) {
    const previous = extra
    setExtra(names)
    setError(false)
    try {
      const answer = await setSubagentAllowlist(names)
      setExtra(answer.extra_tools)
    } catch {
      setError(true)
      setExtra(previous)
    }
  }

  const addable = rows
    .filter((row) => !base.includes(row.name) && !(extra ?? []).includes(row.name))
    .map((row) => row.name)

  return (
    <>
      <Card data-testid="tools-catalog">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <h3 className="flex items-center gap-2 font-display text-ui-lg font-semibold text-foreground/95">
            <Wrench className="h-4 w-4" strokeWidth={1.5} aria-hidden="true" />
            {t('tools.catalogTitle')}
          </h3>
          <span
            data-testid="tools-catalog-count"
            className="font-mono text-ui-xs tabular-nums text-ink-faint"
          >
            {t('tools.catalogOn', { on, total: rows.length })}
          </span>
          <label className="ml-auto flex items-center gap-1.5">
            <Search className="h-3.5 w-3.5 text-ink-faint" strokeWidth={1.5} aria-hidden="true" />
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder={t('tools.catalogFilter')}
              aria-label={t('tools.catalogFilter')}
              data-testid="tools-catalog-filter"
              className="w-32 rounded-md border border-hairline bg-surface/40 px-2 py-1 text-ui-xs text-foreground placeholder:text-ink-faint focus-ring pointer-coarse:min-h-11"
            />
          </label>
        </div>
        <p className="mt-1 text-ui-sm text-ink-faint">
          {t('tools.catalogHint', { safe, total: rows.length })}
        </p>
        <div className="mt-1">
          {groups.map((group) => (
            <section key={group.family} data-testid={`tool-group-${group.family}`}>
              <h4 className="mt-4 flex items-baseline gap-2 text-ui-xs font-medium text-ink-soft">
                {t(`tools.catalogFamily.${group.family}`)}
                <span className="font-mono text-ui-xs tabular-nums text-ink-faint">
                  {group.rows.length}
                </span>
              </h4>
              <ul className="mt-1 divide-y divide-hairline">
                {group.rows.map((row) => {
                  const Icon = iconFor(row.name)
                  const enabled = row.enabled !== false
                  return (
                    <li
                      key={row.name}
                      data-testid={`tool-row-${row.name}`}
                      data-safe={row.safe ? 'true' : 'false'}
                      data-enabled={enabled ? 'true' : 'false'}
                      className="flex items-start gap-3 py-2.5"
                    >
                      <Icon
                        className="mt-0.5 h-4 w-4 shrink-0 text-ink-faint"
                        strokeWidth={1.5}
                        aria-hidden="true"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                          <span className="font-mono text-ui-xs text-foreground/90">
                            {row.name}
                          </span>
                          <span
                            className={`text-ui-xs ${
                              row.safe ? 'text-status-success/90' : 'text-status-warning/90'
                            }`}
                          >
                            {row.safe ? t('tools.catalogSafe') : t('tools.catalogAsks')}
                          </span>
                        </div>
                        <p
                          className="mt-0.5 line-clamp-2 text-ui-xs leading-relaxed text-ink-faint"
                          title={row.description}
                        >
                          {row.description}
                        </p>
                      </div>
                      <CapabilitySwitch
                        row={row}
                        busy={busy === row.name}
                        t={t}
                        onToggle={(next) => void toggle(row, next)}
                      />
                    </li>
                  )
                })}
              </ul>
            </section>
          ))}
        </div>
        {error && (
          <p role="alert" data-testid="tools-catalog-error" className="mt-2 text-ui-xs text-status-danger">
            {t('tools.switchFailed')}
          </p>
        )}
      </Card>

      {extra !== null && (
        <Card data-testid="tools-allowlist">
          <h3 className="flex items-center gap-2 font-display text-ui-lg font-semibold text-foreground/95">
            <ShieldCheck className="h-4 w-4" strokeWidth={1.5} aria-hidden="true" />
            {t('tools.allowTitle')}
          </h3>
          <p className="mt-1 text-ui-sm text-ink-faint">{t('tools.allowHint')}</p>
          <ul className="mt-3 flex flex-wrap gap-1.5">
            {[...base, ...extra].map((name) => {
              const own = extra.includes(name)
              return (
                <li
                  key={name}
                  data-testid={`allow-chip-${name}`}
                  className="flex items-center gap-1 rounded-md border border-hairline bg-surface/40 px-2 py-1"
                >
                  <span className="font-mono text-ui-xs text-foreground/85">{name}</span>
                  {own ? (
                    <button
                      type="button"
                      aria-label={t('tools.allowRemove', { name })}
                      data-testid={`allow-remove-${name}`}
                      onClick={() => void editAllowlist(extra.filter((entry) => entry !== name))}
                      className="text-ink-faint hover:text-status-danger focus-ring"
                    >
                      <X className="h-3 w-3" aria-hidden="true" />
                    </button>
                  ) : (
                    <Lock
                      className="h-3 w-3 text-ink-faint/60"
                      strokeWidth={1.5}
                      aria-hidden="true"
                    />
                  )}
                </li>
              )
            })}
          </ul>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <select
              value={pick}
              onChange={(e) => setPick(e.target.value)}
              aria-label={t('tools.allowPick')}
              data-testid="tools-allow-pick"
              className="rounded-md border border-hairline bg-surface/40 px-2 py-1 text-ui-xs text-foreground focus-ring pointer-coarse:min-h-11"
            >
              <option value="">{t('tools.allowPick')}</option>
              {addable.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              variant="secondary"
              data-testid="tools-allow-add"
              disabled={!pick}
              className="pointer-coarse:min-h-11"
              onClick={() => {
                if (!pick) return
                void editAllowlist([...extra, pick])
                setPick('')
              }}
            >
              <Plus className="h-3.5 w-3.5" aria-hidden="true" />
              {t('tools.allowAdd')}
            </Button>
          </div>
        </Card>
      )}
    </>
  )
}
