import { useEffect, useState } from 'react'
import DiffView from './DiffView'
import CodeBlock from './CodeBlock'
import {
  ChevronRight,
  ListTodo,
  Loader2,
  Copy,
  Eye,
  Check,
  Circle,
  AlertCircle,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { fmtMs } from '@/lib/format'
import type { TFunction } from 'i18next'
import type { ToolCall } from '@/store/chatStore'
import { classifyToolCall, isDiffLike, type ToolCardModel } from '@/lib/toolCardModel'
import { ICONS, isToolError, shouldAutoOpen, toolOutcome } from '@/lib/toolRound'
import { useTasks } from '@/hooks/useTasks'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { readerText } from '@/lib/readerText'
import { BrowserWatch } from './agent/BrowserWatch'
import { RunWatch } from './agent/RunWatch'
import { StepEvidence } from './agent/StepEvidence'
import './ToolCallDisplay.css'
/**
 * Ephe — tool activities in the chat stream (UI-CHAT: one calm row per call).
 *
 * The summary is a single quiet line: status mark · tool name · duration ·
 * outcome (ok/failed/running). No second name, no verb word, no "completed"
 * suffix. Everything else — arguments, output, diff, digest, preview — lives
 * one level down in `ToolCallDetails`, behind the row's chevron.
 *
 * The family bodies are unchanged:
 * - shell:    `$ command` row with a copy button, output block, `exit N` chip.
 * - edit:     path basename + `+N`/`−N` stats, unified diff coloured.
 * - write:    file content in a syntax view (language by file extension).
 * - task:     task checklist taken from the real /api/tasks list.
 * - rest:     name badge + args/result details as before (honest JSON).
 */
function liveBrowserSession(tools: ToolCall[], live: boolean): string | null {
  if (!live) return null
  for (let index = tools.length - 1; index >= 0; index -= 1) {
    const tool = tools[index]
    if (!tool?.name.startsWith('browser_')) continue
    if (tool.status === 'pending' || tool.status === 'waiting') {
      return String(tool.args?.session ?? 'default')
    }
  }
  return null
}

export default function ToolCallDisplay({
  tool_calls,
  live = true,
}: {
  tool_calls: ToolCall[]
  /** The turn is streaming in this page life. Restored history is not: a failed or pending
   *  browser row from a previous page must not open a stream for a session that ended with it. */
  live?: boolean
}) {
  const liveSession = liveBrowserSession(tool_calls, live)
  return (
    <div className="mt-1 space-y-1">
      {liveSession && <RunWatch session={liveSession} />}
      {tool_calls.map((tool) => (
        <ToolCallEntry
          key={tool.id}
          tool={tool}
          live={live}
          suppressWatch={
            liveSession !== null &&
            tool.name.startsWith('browser_') &&
            String(tool.args?.session ?? 'default') === liveSession
          }
        />
      ))}
    </div>
  )
}

/** The shared left-hand read of a call: running, failed, or settled. */
export function ToolStatusMark({ tool }: { tool: ToolCall }) {
  const kind =
    tool.status === 'pending' || tool.status === 'waiting'
      ? 'is-running'
      : isToolError(tool)
        ? 'is-error'
        : 'is-done'
  return (
    <span className={`tool-status ${kind}`} aria-hidden="true" data-testid="tool-status-mark">
      {kind === 'is-running' ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : kind === 'is-error' ? (
        <AlertCircle className="h-3.5 w-3.5" />
      ) : (
        <Check className="h-3.5 w-3.5" />
      )}
    </span>
  )
}

function ToolCallEntry({
  tool,
  suppressWatch,
  live,
}: {
  tool: ToolCall
  suppressWatch: boolean
  live: boolean
}) {
  const { t } = useTranslation()
  const model = classifyToolCall(tool)
  const [open, setOpen] = useState(() => shouldAutoOpen(tool))
  const hasArgs = Object.keys(tool.args ?? {}).length > 0
  const result = typeof tool.result === 'string' ? tool.result : null
  const hasContent =
    hasArgs ||
    result !== null ||
    model.family === 'task' ||
    (typeof tool.reason_code === 'string' && tool.reason_code !== '')
  const Icon = ICONS[model.icon]
  const outcome = toolOutcome(tool, t)

  return (
    <div
      className="tool-row rounded-md"
      data-testid="tool-card"
      data-family={model.family}
      data-status={tool.status}
    >
      {hasContent ? (
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls={`tool-body-${tool.id ?? tool.name}`}
          aria-label={`${tool.name} Details`}
          className="flex w-full min-w-0 items-center gap-1.5 rounded-md px-1 py-0.5 text-left transition-colors hover:bg-surface-interactive"
        >
          <ToolStatusMark tool={tool} />
          <Icon className="h-3.5 w-3.5 shrink-0 text-brand/70" aria-hidden="true" />
          <span
            data-testid="tool-name"
            className="min-w-0 truncate font-mono text-ui-xs text-foreground/80"
          >
            {tool.name}
          </span>
          {tool.duration_ms != null && (
            <span
              data-testid="round-duration"
              className="shrink-0 font-mono text-ui-2xs tabular-nums text-ink-faint"
            >
              {fmtMs(Math.round(tool.duration_ms))}
            </span>
          )}
          <span
            data-testid="tool-outcome"
            className={`shrink-0 text-ui-xs ${isToolError(tool) ? 'text-status-danger' : 'text-ink-soft'}`}
          >
            · {outcome}
          </span>
          {model.runtime !== null && <RuntimeChip model={model} />}
          {model.stats !== null && (model.family === 'edit' || model.family === 'write') && (
            <StatsChip model={model} />
          )}
          <ChevronRight
            className={`ml-auto h-3 w-3 shrink-0 text-ink-faint transition-transform ${open ? 'rotate-90' : ''}`}
            aria-hidden="true"
          />
        </button>
      ) : (
        <div className="flex w-full min-w-0 items-center gap-1.5 px-1 py-0.5">
          <ToolStatusMark tool={tool} />
          <Icon className="h-3.5 w-3.5 shrink-0 text-brand/70" aria-hidden="true" />
          <span
            data-testid="tool-name"
            className="min-w-0 truncate font-mono text-ui-xs text-foreground/80"
          >
            {tool.name}
          </span>
          {tool.duration_ms != null && (
            <span
              data-testid="round-duration"
              className="shrink-0 font-mono text-ui-2xs tabular-nums text-ink-faint"
            >
              {fmtMs(Math.round(tool.duration_ms))}
            </span>
          )}
          <span
            data-testid="tool-outcome"
            className={`shrink-0 text-ui-xs ${isToolError(tool) ? 'text-status-danger' : 'text-ink-soft'}`}
          >
            · {outcome}
          </span>
          {model.runtime !== null && <RuntimeChip model={model} />}
        </div>
      )}

      {open && hasContent && (
        <div id={`tool-body-${tool.id ?? tool.name}`}>
          <ToolCallDetails tool={tool} suppressWatch={suppressWatch} live={live} />
        </div>
      )}

      {/* 2026 task focus: the task checklist always lives visibly in the
          stream (todo anchor pattern) — never behind a chevron. */}
      {model.family === 'task' && (tool.status === 'pending' || tool.status === 'completed') && (
        <div className="ml-5 mt-2">
          <TaskBody completed={tool.status === 'completed'} live={tool.status === 'pending'} />
        </div>
      )}
    </div>
  )
}

/** The body of one call: everything the summary line left out. */
export function ToolCallDetails({
  tool,
  suppressWatch = false,
  live = false,
}: {
  tool: ToolCall
  suppressWatch?: boolean
  /** Whether this page life is streaming the turn; a restored detail opens no stream. */
  live?: boolean
}) {
  const { t } = useTranslation()
  const model = classifyToolCall(tool)
  const result = typeof tool.result === 'string' ? tool.result : null
  const isDiffResult = result !== null && isDiffLike(result)
  const reasonText =
    tool.status === 'failed'
      ? readerText(
          t,
          tool.reason_code,
          tool.reason_params,
          (result ?? '').split('\n')[0]?.replace(/^\[fetch failed\]\s*/, '') ?? '',
        )
      : ''

  const canPreview =
    model.filePath !== null &&
    model.previewable &&
    tool.status === 'completed' &&
    (model.family === 'edit' || model.family === 'write' || model.family === 'artifact')

  const familyTipKey: Record<string, string> = {
    shell: 'chat.toolTipShell',
    edit: 'chat.toolTipEdit',
    write: 'chat.toolTipWrite',
    read: 'chat.toolTipRead',
    search: 'chat.toolTipSearch',
    web: 'chat.toolTipWeb',
    task: 'chat.toolTipTask',
  }
  const tipKey = familyTipKey[model.family] ?? 'chat.toolTipGeneric'

  return (
    <div className="tool-body mt-1 space-y-2" data-testid="tool-details">
      {reasonText !== '' && (
        <div
          data-testid="tool-failure-reason"
          className="break-words text-ui-xs text-status-danger"
        >
          {reasonText}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-2 gap-y-1" data-testid="tool-meta">
        {model.target !== '' && model.target !== tool.name && (
          <span
            className="min-w-0 break-words font-mono text-ui-2xs text-ink-soft"
            title={model.target}
            data-testid="tool-target"
          >
            {model.target}
          </span>
        )}
        {model.family === 'shell' && model.exit !== null && (
          <span
            data-testid="tool-exit-chip"
            className={`shrink-0 rounded px-1.5 py-0.5 font-mono text-ui-2xs ${
              model.exit.code === 0
                ? 'text-status-success bg-status-success/20'
                : 'text-status-danger bg-status-danger/20'
            }`}
          >
            exit {model.exit.code}
          </span>
        )}
        {tool.sha256 && (
          <span
            data-testid="tool-digest"
            className="shrink-0 font-mono text-ui-2xs text-ink-faint"
            title={`sha256:${tool.sha256}`}
          >
            sha256:{tool.sha256.slice(0, 8)}
          </span>
        )}
        {canPreview && (
          <button
            type="button"
            onClick={() =>
              window.dispatchEvent(
                new CustomEvent(PREVIEW_OPEN_EVENT, {
                  detail: {
                    tab: 'preview',
                    url: `/api/file?path=${encodeURIComponent(model.filePath ?? '')}`,
                  },
                }),
              )
            }
            aria-label={t('chat.toolOpenPreview')}
            title={t('chat.toolOpenPreview')}
            data-testid="tool-open-preview"
            className="inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-ui-2xs text-ink-soft transition-colors hover:bg-surface-interactive hover:text-foreground/80"
          >
            <Eye className="h-3 w-3" aria-hidden="true" />
          </button>
        )}
      </div>

      <div data-testid="tool-card-hint" className="break-words text-ui-2xs text-ink-faint">
        {t(`${tipKey}.title`)} — {t(`${tipKey}.body`)}
      </div>
      {model.family === 'shell' && <ShellBody model={model} result={result} />}
      {model.family === 'edit' && <EditBody result={result} isDiff={isDiffResult} />}
      {model.family === 'write' && <WriteBody tool={tool} model={model} result={result} />}
      {model.family === 'web' && <WebBody tool={tool} suppressWatch={suppressWatch} live={live} />}
      {!['shell', 'edit', 'write', 'task', 'web'].includes(model.family) && (
        <GenericBody tool={tool} />
      )}
    </div>
  )
}

function RuntimeChip({ model }: { model: ToolCardModel }) {
  const { t } = useTranslation()
  return (
    <span
      data-testid="tool-runtime-chip"
      data-runtime={model.runtime}
      className={`shrink-0 rounded px-1.5 py-0.5 font-mono text-ui-2xs ${
        model.runtime === 'kernel'
          ? 'text-status-danger bg-status-danger/20'
          : 'text-status-success bg-status-success/20'
      }`}
      title={
        model.runtime === 'kernel' ? t('chat.toolRuntimeKernelHint') : t('chat.toolRuntimeCellHint')
      }
    >
      {model.runtime === 'kernel' ? t('chat.toolRuntimeKernel') : t('chat.toolRuntimeCell')}
    </span>
  )
}

function StatsChip({ model }: { model: ToolCardModel }) {
  if (model.stats === null) return null
  return (
    <span
      data-testid="tool-stats"
      className="flex shrink-0 items-center gap-1 font-mono text-ui-2xs"
    >
      <span className="text-status-success">+{model.stats.added}</span>
      <span className="text-status-danger">−{model.stats.removed}</span>
    </span>
  )
}

/** `$ command` + copy, the output below it (exit suffix stripped, chip on top). */
function ShellBody({ model, result }: { model: ToolCardModel; result: string | null }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const command = model.command ?? ''
  const body = model.exit !== null ? model.exit.body : result
  return (
    <div data-testid="tool-shell-body">
      {command !== '' && (
        <div
          data-testid="tool-cmdline"
          className="flex items-start gap-2 rounded bg-canvas border border-hairline px-2 py-1.5 font-mono text-ui-xs"
        >
          <span className="text-brand/80 select-none shrink-0">$</span>
          <span className="text-foreground/90 whitespace-pre-wrap break-all min-w-0">
            {command}
          </span>
          <button
            type="button"
            onClick={() => {
              void navigator.clipboard?.writeText(command).then(() => {
                setCopied(true)
                window.setTimeout(() => setCopied(false), 1200)
              })
            }}
            aria-label={t('chat.toolCopyCmd')}
            title={t('chat.toolCopyCmd')}
            data-testid="tool-copy-cmd"
            className="ml-auto shrink-0 text-ink-faint hover:text-foreground/80 transition-colors"
          >
            {copied ? (
              <Check className="h-3 w-3 text-status-success" />
            ) : (
              <Copy className="h-3 w-3" />
            )}
          </button>
        </div>
      )}
      {body !== null && body !== '' ? (
        <pre
          data-testid="tool-result"
          className="mt-1.5 text-ui-xs text-ink-soft max-h-52 overflow-auto rounded bg-canvas p-2 whitespace-pre-wrap font-mono"
        >
          {body}
          {model.exit !== null && model.exit.err !== '' && (
            <span className="block text-status-danger mt-1">{model.exit.err}</span>
          )}
        </pre>
      ) : model.exit !== null && model.exit.err !== '' ? (
        <pre
          data-testid="tool-stderr"
          className="mt-1.5 text-ui-xs text-status-danger max-h-52 overflow-auto rounded bg-status-danger/10 p-2 whitespace-pre-wrap font-mono"
        >
          {model.exit.err}
        </pre>
      ) : null}
    </div>
  )
}

function EditBody({ result, isDiff }: { result: string | null; isDiff: boolean }) {
  if (result === null) return null
  return isDiff ? <DiffView diff={result} /> : <ResultPre result={result} />
}

function WriteBody({
  tool,
  model,
  result,
}: {
  tool: ToolCall
  model: ToolCardModel
  result: string | null
}) {
  const content =
    typeof tool.args?.['content'] === 'string' ? (tool.args['content'] as string) : null
  if (content !== null && content !== '') {
    return <CodeBlock code={content} language={model.language ?? 'text'} />
  }
  if (result !== null && isDiffLike(result)) return <DiffView diff={result} />
  return result !== null ? <ResultPre result={result} /> : null
}

/** manage_tasks: the real task list as a checklist (parity Z06).
 *  2026 task focus: with a progress header ("3/5 done") and live follow
 *  (poll 2.5 s) while the task is still running — the todo anchor.
 *  P1-11: tasks are global (no session scope in /api/tasks) — the poll
 *  runs through the shared useTasks store, ONE interval for all cards. */
export function TaskBody({ completed, live = false }: { completed: boolean; live?: boolean }) {
  const { t } = useTranslation()
  const { tasks, failed } = useTasks(live)

  if (!completed && !live) return null
  if (failed)
    return (
      <div className="text-ui-xs text-ink-faint" data-testid="tool-task-state">
        —
      </div>
    )
  if (tasks === null) {
    return (
      <div
        className="flex items-center gap-1.5 text-ui-xs text-ink-faint"
        data-testid="tool-task-state"
      >
        <Loader2 className="h-[0.875em] w-[0.875em] animate-spin" aria-hidden="true" />
      </div>
    )
  }
  const done = tasks.filter((task) => task.status === 'done').length
  return (
    <div data-testid="tool-task-live">
      <div
        className="flex items-center gap-2 text-ui-xs text-ink-soft mb-1"
        data-testid="tool-task-progress"
      >
        <ListTodo className="h-3 w-3 shrink-0 text-brand/80" aria-hidden="true" />
        <span>{t('chat.taskProgress', { done, total: tasks.length })}</span>
      </div>
      <ul className="space-y-1" data-testid="tool-task-list">
        {tasks.map((task) => (
          <li
            key={task.id}
            data-testid="tool-task-row"
            data-status={task.status}
            className="flex items-center gap-2 text-ui-xs"
          >
            {task.status === 'done' ? (
              <Check className="h-3.5 w-3.5 shrink-0 text-status-success" aria-hidden="true" />
            ) : (
              <Circle className="h-3.5 w-3.5 shrink-0 text-ink-faint" aria-hidden="true" />
            )}
            <span
              className={
                task.status === 'done'
                  ? 'text-ink-soft line-through decoration-2 decoration-mist/80 truncate'
                  : 'text-foreground/80 truncate'
              }
            >
              {task.title}
            </span>
          </li>
        ))}
        {tasks.length === 0 && <li className="text-ui-xs text-ink-faint">—</li>}
      </ul>
    </div>
  )
}

function ResultPre({ result }: { result: string }) {
  const { t } = useTranslation()
  return (
    <div>
      <div className="text-ui-xs uppercase tracking-wide text-foreground/70 mb-1">
        {t('chat.toolResultLabel')}
      </div>
      <pre
        data-testid="tool-result"
        className="text-ui-xs text-ink-faint max-h-40 overflow-auto rounded bg-canvas p-2 whitespace-pre-wrap"
      >
        {result}
      </pre>
    </div>
  )
}

/** A coded refusal reads in the user's language; an unknown code keeps the server's
 * sentence, because a newer app meets an older backend. */
function refusalLine(tool: ToolCall, t: TFunction, result: string): string {
  if (!tool.reason_code) return result
  return t(`reader.${tool.reason_code}`, { ...tool.reason_params, defaultValue: result })
}

/**
 * A browser step, with the page it is standing on.
 *
 * The arguments and the result stay exactly as `GenericBody` shows them; what a web step has
 * that no other family has is a screen, and the run surface that refuses to show it leaves
 * the reader one line of text about a page they never saw.
 *
 * The session is the tool's own argument, and `default` is what `core/browser.py` opens when
 * the call names none, so the view follows the run rather than a name this file invented.
 */
function WebBody({
  tool,
  suppressWatch,
  live,
}: {
  tool: ToolCall
  suppressWatch: boolean
  live: boolean
}) {
  const { t } = useTranslation()
  const session = String(tool.args?.session ?? 'default')
  // Only a `browser_*` step owns a page. `web_search` shares the display family (globe,
  // "Browse") but never opens a browser, so it has no session to watch: it asked for
  // `default` and the route answered 404 on every boot of a failed, restored search.
  const browserStep = tool.name.startsWith('browser_')
  // A restored step outlives its browser: the run ended with the previous tab. The page
  // stays reachable, but the stream opens on the reader's click, never at boot.
  const [showPage, setShowPage] = useState(live)
  useEffect(() => {
    if (live) setShowPage(true)
  }, [live])
  return (
    <>
      <GenericBody tool={tool} />
      <StepEvidence result={typeof tool.result === 'string' ? tool.result : null} />
      {browserStep && !suppressWatch && (
        <>
          {showPage ? (
            <BrowserWatch session={session} />
          ) : (
            <button
              type="button"
              data-testid="browser-watch-open"
              onClick={() => setShowPage(true)}
              className="inline-flex items-center gap-1.5 rounded-md border border-hairline bg-canvas/40 px-2 py-1 text-ui-xs text-ink-soft transition-colors hover:bg-surface hover:text-foreground"
            >
              <Eye className="h-3 w-3" aria-hidden="true" />
              {t('chat.showBrowserPage')}
            </button>
          )}
        </>
      )}
    </>
  )
}

function GenericBody({ tool }: { tool: ToolCall }) {
  const { t } = useTranslation()
  const hasArgs = Object.keys(tool.args ?? {}).length > 0
  const result = typeof tool.result === 'string' ? tool.result : null
  return (
    <>
      {hasArgs && (
        <div>
          <div className="text-ui-xs uppercase tracking-wide text-foreground/70 mb-1">
            {t('chat.toolArgsLabel')}
          </div>
          <pre
            data-testid="tool-args"
            className="text-ui-xs text-ink-faint max-h-40 overflow-auto rounded bg-canvas p-2"
          >
            {JSON.stringify(tool.args, null, 2)}
          </pre>
        </div>
      )}
      {result !== null && <ResultPre result={refusalLine(tool, t, result)} />}
    </>
  )
}
