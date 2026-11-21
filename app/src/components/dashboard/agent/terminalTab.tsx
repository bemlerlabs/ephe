'use client'

// TerminalTab — split out of tabsC 1:1 (the architecture boundary maxFileLines=400).

import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { TerminalSquare } from 'lucide-react'
import LiveTerminal from './LiveTerminal'
import { renderAnsi, useWorkspaceDir, WorkspaceBadge } from './primitives'

export function TerminalTab({
  runs,
  busy,
  onSubmit,
}: {
  runs: { id: string; command: string; result?: string }[]
  busy: boolean
  onSubmit: (command: string) => void | Promise<void>
}) {
  const { t } = useTranslation()
  const workspace = useWorkspaceDir()
  // P1-5: live = a real interactive PTY (default); history = one-shot runs
  // (agent commands + manually submitted ones) with a prompt — as before P1-5.
  const [mode, setMode] = useState<'live' | 'history'>('live')
  const [cmd, setCmd] = useState('')
  // K3 Z29 (reference parity): command history with ↑/↓ recall in the prompt.
  const termHistoryRef = useRef<string[]>([])
  const recallIdxRef = useRef(0) // 0 = current input, 1..n = history walking backwards
  const [recallInfo, setRecallInfo] = useState<{ pos: number; total: number }>({ pos: 0, total: 0 })
  const onTermHistoryKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    const hist = termHistoryRef.current
    if (hist.length === 0) return
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      recallIdxRef.current = Math.min(recallIdxRef.current + 1, hist.length)
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      recallIdxRef.current = Math.max(recallIdxRef.current - 1, 0)
    } else {
      return
    }
    const pos = recallIdxRef.current
    if (pos > 0) setCmd(hist[hist.length - pos] ?? '')
    setRecallInfo({ pos, total: hist.length })
  }
  const send = () => {
    const c = cmd.trim()
    if (!c || busy) return
    termHistoryRef.current = [...termHistoryRef.current.filter((x) => x !== c), c].slice(-30)
    recallIdxRef.current = 0
    setRecallInfo({ pos: 0, total: termHistoryRef.current.length })
    void onSubmit(c)
    setCmd('')
  }
  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <WorkspaceBadge dir={workspace} />
      <div className="flex items-center gap-1 px-3 py-2 border-b border-hairline shrink-0">
        <button
          type="button"
          data-testid="terminal-mode-live"
          onClick={() => setMode('live')}
          className={`px-2 py-1 rounded-md text-ui-xs font-medium transition-colors ${
            mode === 'live' ? 'bg-brand/20 text-brand' : 'text-ink-faint hover:text-ink-soft'
          }`}
        >
          {t('agentPanel.terminalLive')}
        </button>
        <button
          type="button"
          data-testid="terminal-mode-history"
          onClick={() => setMode('history')}
          className={`px-2 py-1 rounded-md text-ui-xs font-medium transition-colors ${
            mode === 'history' ? 'bg-brand/20 text-brand' : 'text-ink-faint hover:text-ink-soft'
          }`}
        >
          {t('agentPanel.terminalHistory')}
        </button>
      </div>
      {mode === 'live' && <LiveTerminal className="flex-1 min-h-0" />}
      {mode === 'history' && (
        <>
          <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-3 font-mono text-ui-xs">
            {runs.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center gap-2 text-ink-faint text-ui-sm p-6 text-center">
                <TerminalSquare className="h-10 w-10 opacity-40" />
                <p>
                  {t('agentPanel.terminalEmptyBefore')} <code className="text-brand/80">ls</code>,{' '}
                  <code className="text-brand/80">git status</code>{' '}
                  {t('agentPanel.terminalEmptyAfter')}
                </p>
              </div>
            ) : (
              runs.map((r) => (
                <div
                  key={r.id}
                  className="rounded-lg border border-hairline bg-canvas overflow-hidden"
                >
                  <div className="flex items-center gap-2 px-3 py-1.5 border-b border-hairline bg-surface">
                    <span className="text-brand">$</span>
                    <span className="text-foreground/80 break-all">{r.command}</span>
                  </div>
                  <pre className="px-3 py-2 text-ink-faint whitespace-pre-wrap break-words max-h-64 overflow-auto">
                    {r.result ? renderAnsi(r.result) : '…'}
                  </pre>
                </div>
              ))
            )}
          </div>
          {/* The prompt bar (always) */}
          <div className="flex items-center gap-2 px-3 h-12 border-t border-hairline flex-shrink-0 font-mono">
            <span className="text-brand text-ui-sm">$</span>
            <input
              type="text"
              value={cmd}
              onChange={(e) => setCmd(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') send()
                else onTermHistoryKey(e)
              }}
              placeholder={
                busy ? t('agentPanel.terminalBusy') : t('agentPanel.terminalPlaceholder')
              }
              disabled={busy}
              aria-label={t('agentPanel.terminalCommandLabel')}
              data-testid="terminal-prompt-input"
              className="flex-1 bg-transparent text-ui-xs text-foreground placeholder:text-ink-faint outline-none"
            />
            {recallInfo.total > 0 && recallInfo.pos > 0 && (
              <span
                data-testid="terminal-recall-counter"
                className="text-ui-xs text-ink-faint shrink-0"
              >
                ↑/↓ {recallInfo.pos}/{recallInfo.total}
              </span>
            )}
            <button
              type="button"
              onClick={send}
              disabled={busy || !cmd.trim()}
              className="px-2.5 py-1 rounded-md text-ui-xs font-medium bg-brand/20 text-brand hover:bg-brand/20 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {t('agentPanel.terminalRun')}
            </button>
          </div>
        </>
      )}
    </div>
  )
}
