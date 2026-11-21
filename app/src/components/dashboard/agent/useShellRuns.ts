'use client'

import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { runShell, runShellPty } from '@/lib/api'
import type { ChatMessage } from '@/types'

export type ShellRun = { id: string; command: string; result?: string }

/**
 * The agent's run_shell activity (whitelist/approval filtered, view only)
 * plus the user-initiated runs of the full terminal (G1).
 */
export function useShellRuns(messages: ChatMessage[]) {
  const { t } = useTranslation()

  const shellRuns = useMemo(() => {
    const out: ShellRun[] = []
    for (const m of messages) {
      for (const tc of m.tool_calls ?? []) {
        if (tc.name === 'run_shell') {
          out.push({
            id: tc.id,
            command: String(tc.args?.command ?? ''),
            result: typeof tc.result === 'string' ? tc.result : undefined,
          })
        }
      }
    }
    return out
  }, [messages])

  // git activity: run_shell runs whose command starts with 'git '. Diff output is
  // coloured through DiffView (reused), otherwise the raw output.
  const gitRuns = useMemo(() => shellRuns.filter((r) => /^\s*git\s/.test(r.command)), [shellRuns])

  // G1 full terminal: user-initiated runs (alongside the agent runs).
  const [userRuns, setUserRuns] = useState<ShellRun[]>([])
  const [busy, setBusy] = useState(false)

  const submit = async (command: string) => {
    const cmd = command.trim()
    if (!cmd) return
    const id = `u${Date.now()}`
    setBusy(true)
    setUserRuns((prev) => [...prev, { id, command: cmd, result: '…' }])
    try {
      // W17 P1-1: the PTY pipe is preferred (keeps CRLF/ANSI); older
      // api mocks without runShellPty fall back to the PIPE path.
      const fn: (c: string) => Promise<{ command: string; output: string; ok: boolean }> =
        typeof runShellPty === 'function' ? (c) => runShellPty(c) : runShell
      const res = await fn(cmd)
      setUserRuns((prev) => prev.map((r) => (r.id === id ? { ...r, result: res.output } : r)))
    } catch (e) {
      setUserRuns((prev) =>
        prev.map((r) =>
          r.id === id ? { ...r, result: `[${t('agentPanel.error')} ${String(e)}]` } : r,
        ),
      )
    } finally {
      setBusy(false)
    }
  }

  return { shellRuns, gitRuns, userRuns, busy, submit }
}
