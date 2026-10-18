import { useState } from 'react'
import DiffView from './DiffView'
import CodeBlock from './CodeBlock'
import {
  ChevronRight,
  Terminal,
  Pencil,
  FilePlus,
  FileText,
  Search,
  Globe,
  ListTodo,
  Package,
  Wrench,
  Loader2,
  Copy,
  Eye,
  Check,
  Circle,
  Network,
  AlertCircle,
} from 'lucide-react'
import { Badge } from '@/components/ui'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import SmartTip from './SmartTip'
import type { ToolCall } from '@/store/chatStore'
import {
  classifyToolCall,
  isDiffLike,
  type ToolCardModel,
  type ToolIconKind,
} from '@/lib/toolCardModel'
import { useTasks } from '@/hooks/useTasks'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import './ToolCallDisplay.css'
/**
 * Ephe — tool activities in the chat stream (reference-B parity Z01–Z06, round E).
 *
 * One card per tool call, with a summary row (icon + verb + human target +
 * status chips) and expandable details. The classification cases were decided
 * in the pure model (lib/toolCardModel); this file only renders.
 *
 * - shell:    `$ command` row with a copy button, output block, `exit N` chip.
 * - edit:     path basename + `+N`/`−N` stats, unified diff coloured,
 *             opened automatically on success; the "open in preview" action.
 * - write:    file content in a syntax view (language by file extension).
 * - task:     task checklist taken from the real /api/tasks list.
 * - rest:     name badge + args/result details as before (honest JSON).
 */
export default function ToolCallDisplay({ tool_calls }: { tool_calls: ToolCall[] }) {
  return (
    <div className="mt-2 space-y-1">
      {tool_calls.map((tool) => (
        <ToolCallEntry key={tool.id} tool={tool} />
      ))}
    </div>
  )
}

function statusVariant(
  status: ToolCall['status'],
): 'success' | 'destructive' | 'info' | 'warning' | 'default' {
  switch (status) {
    case 'approved':
      return 'success'
    case 'denied':
      return 'destructive'
    case 'completed':
      return 'info'
    case 'waiting':
      return 'warning'
    default:
      return 'default'
  }
}

export const ICONS: Record<ToolIconKind, typeof Terminal> = {
  terminal: Terminal,
  filePen: Pencil,
  filePlus: FilePlus,
  fileText: FileText,
  search: Search,
  globe: Globe,
  tasks: ListTodo,
  package: Package,
  subagent: Network,
  wrench: Wrench,
}

function ToolCallEntry({ tool }: { tool: ToolCall }) {
  const { t } = useTranslation()
  const model = classifyToolCall(tool)
  const result = typeof tool.result === 'string' ? tool.result : null
  const isDiffResult = result !== null && isDiffLike(result)

  const hasArgs = Object.keys(tool.args ?? {}).length > 0
  const isTask = model.family === 'task'
  const hasContent = hasArgs || result !== null || isTask

  // Auto-open rule (parity with the reference behaviour): a finished document —
  // edited (diff result) or created (content arg) — shows its body
  // immediately; a failed shell run surfaces its output; a running call stays
  // open so the spinner/terminal line is visible.
  const writeHasContent =
    model.family === 'write' &&
    typeof tool.args?.['content'] === 'string' &&
    (tool.args['content'] as string).trim() !== ''
  // A failed run: a non-zero shell exit, or a call the guard refused outright.
  const isError =
    tool.status === 'denied' ||
    (tool.status === 'completed' &&
      model.family === 'shell' &&
      model.exit !== null &&
      model.exit.code !== 0)
  // Compact pill default; the body opens on click, on a running call, on a
  // finished document, on a failed run, and on an approval the user must answer.
  const [open, setOpen] = useState(
    tool.status === 'waiting' ||
      tool.status === 'pending' ||
      isError ||
      (tool.status === 'completed' &&
        ((model.family === 'edit' && isDiffResult) ||
          (model.family === 'write' && writeHasContent))),
  )

  // I6 P2c: the status is NEVER rendered raw from the enum — 'approved'/
  // 'denied'/waiting showed up as raw EN values in the German UI (deep-test finding).
  const statusLabel =
    tool.status === 'waiting'
      ? t('chat.toolWaiting')
      : tool.status === 'pending'
        ? t('chat.toolRunning', { tool: tool.name })
        : tool.status === 'completed'
          ? t('chat.toolCompleted', { tool: tool.name })
          : tool.status === 'approved'
            ? t('chat.toolApproved', { tool: tool.name })
            : tool.status === 'denied'
              ? t('chat.toolDenied', { tool: tool.name })
              : tool.status

  const Icon = ICONS[model.icon]
  const monoTarget =
    model.family === 'shell' ||
    model.family === 'edit' ||
    model.family === 'write' ||
    model.family === 'read'
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

  // The leading status mark: an amber spinner while it runs or waits on an
  // approval, a red alert on a failed or denied call, a settled green check once done.
  const statusKind =
    tool.status === 'pending' || tool.status === 'waiting'
      ? 'is-running'
      : isError
        ? 'is-error'
        : 'is-done'

  return (
    <SmartTip
      testId="tool-card-tip"
      block
      tip={{ title: t(`${tipKey}.title`), body: t(`${tipKey}.body`) }}
    >
      <div
        className="tool-pill rounded-lg px-2.5 py-1"
        data-testid="tool-card"
        data-family={model.family}
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className={`tool-status ${statusKind}`} aria-hidden="true">
            {statusKind === 'is-running' ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : statusKind === 'is-error' ? (
              <AlertCircle className="h-3.5 w-3.5" />
            ) : (
              <Check className="h-3.5 w-3.5" />
            )}
          </span>
          {hasContent && (
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              aria-expanded={open}
              aria-controls={`tool-body-${tool.id ?? tool.name}`}
              className="shrink-0 text-ink-soft hover:text-foreground/70 transition-colors"
              aria-label={`${tool.name} Details`}
            >
              <ChevronRight
                className={`h-3.5 w-3.5 transition-transform ${open ? 'rotate-90' : ''}`}
              />
            </button>
          )}
          <Icon className="h-3.5 w-3.5 shrink-0 text-brand/70" aria-hidden="true" />
          <span className="text-ui-xs uppercase tracking-wide text-ink-faint shrink-0">
            {t(model.verbKey)}
          </span>
          {model.target !== '' && (
            <span
              className={`text-ui-xs text-foreground/80 truncate min-w-0 ${monoTarget ? 'font-mono' : ''}`}
              title={model.target}
              data-testid="tool-target"
            >
              {model.target}
            </span>
          )}
          {model.family === 'shell' && model.exit !== null && (
            <span
              data-testid="tool-exit-chip"
              className={`shrink-0 rounded px-1.5 py-0.5 text-ui-xs font-mono ${
                model.exit.code === 0
                  ? 'text-status-success bg-status-success/20'
                  : 'text-status-danger bg-status-danger/20'
              }`}
            >
              exit {model.exit.code}
            </span>
          )}
          {/* WP2b keep: user-land (green) vs kernel (danger) = harmlessness readout. */}
          {model.runtime !== null && (
            <span
              data-testid="tool-runtime-chip"
              data-runtime={model.runtime}
              className={`shrink-0 rounded px-1.5 py-0.5 text-ui-xs font-mono ${
                model.runtime === 'kernel'
                  ? 'text-status-danger bg-status-danger/20'
                  : 'text-status-success bg-status-success/20'
              }`}
              title={
                model.runtime === 'kernel'
                  ? t('chat.toolRuntimeKernelHint')
                  : t('chat.toolRuntimeCellHint')
              }
            >
              {model.runtime === 'kernel' ? t('chat.toolRuntimeKernel') : t('chat.toolRuntimeCell')}
            </span>
          )}
          {model.stats !== null && (model.family === 'edit' || model.family === 'write') && (
            <span
              data-testid="tool-stats"
              className="shrink-0 text-ui-xs font-mono flex items-center gap-1"
            >
              <span className="text-status-success">+{model.stats.added}</span>
              <span className="text-status-danger">−{model.stats.removed}</span>
            </span>
          )}
          {/* The right group may shrink on narrow screens: the status label is
            the truncation victim (ellipsised), while badge and buttons keep
            their intrinsic width. Without this the card clipped the label. */}
          <div className="ml-auto flex items-center gap-1.5 min-w-0">
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
                className="inline-flex items-center gap-1 shrink-0 rounded-md px-1.5 py-0.5 text-ui-xs text-ink-soft hover:text-foreground/80 hover:bg-surface-interactive transition-colors"
              >
                <Eye className="h-3 w-3" aria-hidden="true" />
              </button>
            )}
            {tool.duration_ms != null && (
              <span
                data-testid="tool-duration"
                className="shrink-0 font-mono text-ui-2xs tabular-nums text-ink-faint"
              >
                {(tool.duration_ms / 1000).toFixed(1)}s
              </span>
            )}
            <Badge variant={statusVariant(tool.status)} className="shrink-0 hidden xl:inline-flex">
              {tool.name}
            </Badge>
            <span className="text-ui-xs text-ink-faint truncate max-w-32" title={statusLabel}>
              {statusLabel}
            </span>
          </div>
        </div>

        {open && hasContent && (
          <div className="tool-body mt-1.5 space-y-2" id={`tool-body-${tool.id ?? tool.name}`}>
            {model.family === 'shell' && <ShellBody model={model} result={result} />}
            {model.family === 'edit' && <EditBody result={result} isDiff={isDiffResult} />}
            {model.family === 'write' && <WriteBody tool={tool} model={model} result={result} />}
            {!['shell', 'edit', 'write', 'task'].includes(model.family) && (
              <GenericBody tool={tool} />
            )}
          </div>
        )}

        {/* 2026 task focus: the task checklist always lives visibly in the
          stream (todo anchor pattern) — never behind a chevron. While the task
          is still running the list follows live; otherwise it shows the final state. */}
        {isTask && (tool.status === 'pending' || tool.status === 'completed') && (
          <div className="ml-5 mt-2">
            <TaskBody completed={tool.status === 'completed'} live={tool.status === 'pending'} />
          </div>
        )}
      </div>
    </SmartTip>
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
        <pre className="mt-1.5 text-ui-xs text-ink-soft max-h-52 overflow-auto rounded bg-canvas p-2 whitespace-pre-wrap font-mono">
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
function TaskBody({ completed, live = false }: { completed: boolean; live?: boolean }) {
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
      <div className="text-ui-xs uppercase tracking-wide text-ink-faint mb-1">
        {t('chat.toolResultLabel')}
      </div>
      <pre className="text-ui-xs text-ink-faint max-h-40 overflow-auto rounded bg-canvas p-2 whitespace-pre-wrap">
        {result}
      </pre>
    </div>
  )
}

/** Long-standing behaviour for all remaining families: args + result as details. */
/** A coded refusal reads in the user's language; an unknown code keeps the server's
 * sentence, because a newer app meets an older backend. */
function refusalLine(tool: ToolCall, t: TFunction, result: string): string {
  if (!tool.reason_code) return result
  return t(`reader.${tool.reason_code}`, { ...tool.reason_params, defaultValue: result })
}

function GenericBody({ tool }: { tool: ToolCall }) {
  const { t } = useTranslation()
  const hasArgs = Object.keys(tool.args ?? {}).length > 0
  const result = typeof tool.result === 'string' ? tool.result : null
  return (
    <>
      {hasArgs && (
        <div>
          <div className="text-ui-xs uppercase tracking-wide text-ink-faint mb-1">
            {t('chat.toolArgsLabel')}
          </div>
          <pre className="text-ui-xs text-ink-faint max-h-40 overflow-auto rounded bg-canvas p-2">
            {JSON.stringify(tool.args, null, 2)}
          </pre>
        </div>
      )}
      {result !== null && <ResultPre result={refusalLine(tool, t, result)} />}
    </>
  )
}
