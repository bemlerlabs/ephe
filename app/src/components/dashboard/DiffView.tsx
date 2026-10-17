/** DiffView — interactive unified-diff hunk viewer (W16-P1).
 *  Parses `@@ -l,s +l,s @@` into single hunks; per-hunk buttons for applying
 *  (git apply --cached) and discarding (git apply -R, confirm-
 *  gated). `onApplied` reloads the parent list. Without filePath there are no
 *  actions — it then stays the plain colour readout. */
import { useState } from 'react'
import { gitApplyPatch } from '@/lib/api'
import { toastBus } from '@/lib/toast'
import { useTranslation } from 'react-i18next'

export interface DiffHunk {
  index: number
  header: string
  /** This hunk's complete patch: file header + hunk lines. */
  patch: string
  lines: string[]
}

/** Line classification by prefix (as before, only blocked per hunk). */
function lineClass(line: string): string {
  if (line.startsWith('+') && !line.startsWith('+++'))
    return 'text-status-success bg-status-success/10'
  if (line.startsWith('-') && !line.startsWith('---'))
    return 'text-status-danger bg-status-danger/10'
  if (line.startsWith('@@')) return 'text-yellow-400'
  return 'text-ink-soft'
}

/** P1-1: word-level diff of two lines (trim the shared prefix/suffix edges,
 *  mark the middle part as changed words). Returns the segment colours for
 *  the -/+ side. No full LCS — for hunk lines the edge trim is enough. */
function wordDiff(
  oldLine: string,
  newLine: string,
): { old: Array<[string, 'ctx' | 'chg']>; new: Array<[string, 'ctx' | 'chg']> } {
  const a = oldLine.slice(1)
  const b = newLine.slice(1)
  let s = 0
  while (s < a.length && s < b.length && a[s] === b[s]) s++
  let e = 0
  while (e < a.length - s && e < b.length - s && a[a.length - 1 - e] === b[b.length - 1 - e]) e++
  const midA = a.slice(s, a.length - e)
  const midB = b.slice(s, b.length - e)
  const pre = a.slice(0, s)
  const suf = e > 0 ? a.slice(a.length - e) : ''
  return {
    old: [
      [oldLine[0] ?? '', 'ctx'],
      [pre, 'ctx'],
      ...(midA ? [[midA, 'chg'] as [string, 'chg']] : []),
      ...(suf ? [[suf, 'ctx'] as [string, 'ctx']] : []),
    ],
    new: [
      [newLine[0] ?? '', 'ctx'],
      [pre, 'ctx'],
      ...(midB ? [[midB, 'chg'] as [string, 'chg']] : []),
      ...(suf ? [[suf, 'ctx'] as [string, 'ctx']] : []),
    ],
  }
}

/** Parses a standard unified diff into hunks. Without a hunk header → []. */
export function parseUnifiedDiff(diff: string, filePath?: string): DiffHunk[] {
  const lines = (diff || '').split('\n')
  const firstHunk = lines.findIndex((l) => l.startsWith('@@'))
  if (firstHunk < 0) return []

  const preamble = lines.slice(0, firstHunk)
  const hasFileHeader = preamble.some((l) => l.startsWith('--- ') || l.startsWith('+++ '))
  if (!hasFileHeader && filePath) {
    // The edit_file-/route form carries no file header: synthesise a prefix so
    // that `git apply` knows the target file.
    preamble.unshift(`+++ b/${filePath}`, `--- a/${filePath}`)
  }

  const hunks: DiffHunk[] = []
  let current: { header: string; lines: string[] } | null = null
  for (const line of lines.slice(firstHunk)) {
    if (line.startsWith('@@')) {
      if (current) hunks.push(finishHunk(current, hunks.length, preamble))
      current = { header: line, lines: [line] }
    } else if (current) {
      current.lines.push(line)
    }
  }
  if (current) hunks.push(finishHunk(current, hunks.length, preamble))
  return hunks
}

function finishHunk(
  h: { header: string; lines: string[] },
  index: number,
  preamble: string[],
): DiffHunk {
  return {
    index,
    header: h.header,
    patch: [...preamble, ...h.lines].join('\n') + '\n',
    lines: h.lines,
  }
}

export default function DiffView({
  diff,
  filePath,
  onApplied,
}: {
  diff: string
  filePath?: string
  /** Called after a hunk apply/discard succeeds so the caller can refresh
   *  its file list — otherwise the action has no visible acknowledgement. */
  onApplied?: () => void
}) {
  const { t } = useTranslation()
  const hunks = parseUnifiedDiff(diff, filePath)
  const [busy, setBusy] = useState<{ index: number; kind: 'apply' | 'discard' } | null>(null)
  const header = hunks.length
    ? diff
        .split('\n')
        .slice(0, diff.split('\n').findIndex((l) => l.startsWith('@@')) ?? diff.split('\n').length)
    : []

  const run = async (hunk: DiffHunk, kind: 'apply' | 'discard') => {
    if (busy) return
    // F-10: discarding reverts on-disk work — one click from a text link is
    // too cheap for a destructive action, so gate it behind a confirm.
    if (kind === 'discard' && !window.confirm(t('common.discardConfirm'))) return
    setBusy({ index: hunk.index, kind })
    try {
      await gitApplyPatch(hunk.patch, kind === 'apply' ? { staged: true } : { reverse: true })
      onApplied?.()
    } catch {
      // F-10: a failed hunk application must not stay silent — the file stays
      // unchanged on disk, so the user has to know.
      toastBus.error(t('common.changeFailed'))
    } finally {
      setBusy(null)
    }
  }

  return (
    <pre className="text-ui-xs max-h-60 overflow-auto rounded bg-canvas p-2 leading-5">
      {header.map((line, i) => (
        <div key={`h-${i}`} className={`whitespace-pre ${lineClass(line)}`}>
          {line || ' '}
        </div>
      ))}
      {hunks.map((hunk) => {
        // P1-1: diff the -/+ line pairs at word level.
        const wd = new Map<number, ReturnType<typeof wordDiff>>()
        for (let i = 0; i < hunk.lines.length; i++) {
          const cur = hunk.lines[i] ?? ''
          const nxt = hunk.lines[i + 1] ?? ''
          if (
            cur.startsWith('-') &&
            nxt.startsWith('+') &&
            !cur.startsWith('---') &&
            !nxt.startsWith('+++')
          ) {
            wd.set(i, wordDiff(cur, nxt))
            wd.set(i + 1, wd.get(i)!)
          }
        }
        return (
          <div key={hunk.index} data-testid={`hunk-${hunk.index}`}>
            {hunk.lines.map((line, i) => {
              const pair = wd.get(i)
              const segs = pair ? (line.startsWith('-') ? pair.old : pair.new) : null
              return (
                <div key={i} className={`whitespace-pre ${lineClass(line)}`}>
                  {segs
                    ? segs.map(([txt, k], j) => (
                        <span
                          key={j}
                          className={
                            k === 'chg' ? 'bg-surface-interactive rounded-[2px]' : undefined
                          }
                        >
                          {txt}
                        </span>
                      ))
                    : line || ' '}
                </div>
              )
            })}
            {filePath ? (
              <div className="flex gap-2 my-1" data-testid={`hunk-actions-${hunk.index}`}>
                {/* WP2b keep: apply (green) against discard (warning) is a semantic pair. */}
                <button
                  data-testid={`hunk-apply-${hunk.index}`}
                  onClick={() => void run(hunk, 'apply')}
                  disabled={busy !== null}
                  className="py-1 text-ui-xs text-status-success hover:text-status-success disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {busy?.index === hunk.index && busy.kind === 'apply'
                    ? t('common.applying')
                    : t('common.apply')}
                </button>
                <button
                  data-testid={`hunk-discard-${hunk.index}`}
                  onClick={() => void run(hunk, 'discard')}
                  disabled={busy !== null}
                  className="py-1 text-ui-xs text-status-warning hover:text-status-warning disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {busy?.index === hunk.index && busy.kind === 'discard'
                    ? t('common.discarding')
                    : t('common.discard')}
                </button>
              </div>
            ) : null}
          </div>
        )
      })}
    </pre>
  )
}
