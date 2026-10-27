/**
 * QD-005 — the companion's live co-pilot loop.
 *
 * One crawl per surface change: read the store's waiting tool, open question,
 * context level and fresh output, classify through `companionCopilot.ts`, and
 * either point (scout), wait (warn_only) or run a visible 2500 ms countdown
 * before the action fires (copilot). Every act lands in the receipt trail; the
 * risky ones never act at all.
 *
 * The hook owns no timers beyond the countdown and the display tick, and it
 * never talks to the engine: the crawl is a store read plus pure classification.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { useChatStore } from '@/store/chatStore'
import { approveSandbox } from '@/lib/api/endpoints'
import { answerAsk } from '@/lib/api/endpoints'
import { PREVIEW_OPEN_EVENT } from '@/lib/panelEvents'
import { markSetupIntent } from '@/lib/setupGate'
import {
  bindEscapeCancel,
  COUNTDOWN_MS,
  CopilotCountdown,
  findCopilotTarget,
  pushReceipt,
  type CopilotFinding,
  type CopilotMode,
  type CopilotReceipt,
  type CopilotSnapshot,
} from '@/lib/companionCopilot'

export interface CopilotUi {
  finding: CopilotFinding | null
  countdownRemaining: number | null
  receipts: CopilotReceipt[]
  cancel: () => void
  /** The one-click pointer for scout hints and repair focus. */
  focus: () => void
}

export function useCompanionCopilot(args: {
  enabled: boolean
  mode: CopilotMode
  runState: 'ready' | 'working' | 'waiting' | 'done'
  contextPercent: number | null
  repairVisible: boolean
}): CopilotUi {
  const { enabled, mode, runState, contextPercent, repairVisible } = args
  const session = useChatStore((s) => s.currentSession)
  const [finding, setFinding] = useState<CopilotFinding | null>(null)
  const [receipts, setReceipts] = useState<CopilotReceipt[]>([])
  const [deadline, setDeadline] = useState<number | null>(null)
  const [remaining, setRemaining] = useState<number | null>(null)

  const countdown = useRef<CopilotCountdown | null>(null)
  const escapeRelease = useRef<(() => void) | null>(null)
  const executedKey = useRef<string | null>(null)
  const activeKey = useRef<string | null>(null)
  const prevRunState = useRef(args.runState)
  const compactedSession = useRef<string | null>(null)

  const log = useCallback((entry: Omit<CopilotReceipt, 'at'> & { at?: number }) => {
    setReceipts((list) => pushReceipt(list, entry))
  }, [])

  const cancel = useCallback(() => {
    countdown.current?.cancel()
    countdown.current = null
    escapeRelease.current?.()
    escapeRelease.current = null
    // A countdown the user stopped belongs to the prompt it was counting for.
    // Remembering that key is what keeps a later re-render of the same waiting
    // tool from offering the act again.
    if (activeKey.current) executedKey.current = activeKey.current
    activeKey.current = null
    setDeadline(null)
    setRemaining(null)
  }, [])

  const highlight = useCallback((selector: string | null) => {
    for (const el of document.querySelectorAll('[data-copilot-highlight="true"]')) {
      el.removeAttribute('data-copilot-highlight')
    }
    if (!selector) return
    for (const el of document.querySelectorAll(selector)) {
      el.setAttribute('data-copilot-highlight', 'true')
    }
  }, [])

  const focus = useCallback(() => {
    const selector = finding?.selector ?? null
    const onScreen = selector !== null && document.querySelector(selector) !== null
    highlight(selector)
    if (selector) {
      const el = document.querySelector<HTMLElement>(selector)
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      el?.focus({ preventScroll: true })
    }
    // The repair card is drawn on the setup route, so a repair the chat cannot
    // show is a repair the pointer has to walk the user to. Same hand-off the
    // engine chip uses: mark the intent, then the hash.
    if (!onScreen && repairVisible && finding?.target === 'error_or_setup_repair') {
      markSetupIntent()
      window.location.hash = '#/setup'
    }
    if (finding) {
      log({
        target: finding.target,
        verdict: 'focus',
        actionKey: finding.actionKey,
        actionParam: finding.actionParam,
        reasonKey: finding.reasonKey,
      })
    }
  }, [finding, highlight, log, repairVisible])

  useEffect(() => {
    if (!enabled || mode === 'perch') {
      cancel()
      setFinding(null)
      highlight(null)
      return
    }

    const messages = session?.messages ?? []
    const last = messages[messages.length - 1]
    const assistant = last && last.role === 'assistant' ? last : null
    const toolCalls = assistant?.tool_calls ?? []
    const waiting = toolCalls.find((c) => c.status === 'waiting') ?? null
    const turnJustFinished = prevRunState.current === 'working' && runState === 'done'
    prevRunState.current = runState

    const snapshot: CopilotSnapshot = {
      waitingTool: waiting
        ? { name: waiting.name, args: waiting.args, description: waiting.description }
        : null,
      ask: assistant?.ask
        ? {
            recommendation: assistant.ask.recommendation,
            options: assistant.ask.options.map((o) => o.label),
            token: assistant.ask.token,
          }
        : null,
      runState,
      contextPercent,
      hasCompact: true,
      compactedThisSession: compactedSession.current === (session?.id ?? null),
      turnJustFinished,
      newArtifacts: assistant?.artifacts?.length ?? 0,
      newEdits: toolCalls.filter(
        (c) =>
          c.status === 'completed' && (c.name === 'edit_file' || c.name === 'write_file'),
      ).length,
      toolError: toolCalls.some((c) => c.status === 'failed'),
      repairVisible,
    }

    const next = findCopilotTarget(snapshot, mode)
    setFinding(next)
    if (!next) {
      cancel()
      highlight(null)
      executedKey.current = null
      return
    }

    if (next.verdict !== 'auto_act') {
      cancel()
      highlight(next.selector)
      executedKey.current = null
      return
    }

    // The token is what makes two runs of the same command two prompts: the
    // key has to name the call, not only the session and the verb.
    const token = snapshot.waitingTool?.description ?? snapshot.ask?.token ?? ''
    const key = `${session?.id ?? '?'}:${next.target}:${next.actionKey}:${
      next.actionParam ?? ''
    }:${token}`
    if (executedKey.current === key) return
    if (countdown.current) return

    const count = new CopilotCountdown(COUNTDOWN_MS)
    countdown.current = count
    activeKey.current = key
    setDeadline(Date.now() + COUNTDOWN_MS)
    setRemaining(COUNTDOWN_MS)
    escapeRelease.current = bindEscapeCancel(cancel)
    count.start(() => {
      countdown.current = null
      escapeRelease.current?.()
      escapeRelease.current = null
      setDeadline(null)
      setRemaining(null)
      executedKey.current = key
      activeKey.current = null

      const entry = {
        target: next.target,
        verdict: 'auto_act' as const,
        actionKey: next.actionKey,
        actionParam: next.actionParam,
        reasonKey: next.reasonKey,
      }
      log(entry)

      if (next.target === 'tool_approval') {
        const token = snapshot.waitingTool?.description
        if (!token) return
        void approveSandbox(token, true, false)
          .then(() => useChatStore.getState().approveSandbox())
          .catch(() => undefined)
        return
      }
      if (next.target === 'ask_user') {
        const answer = next.actionParam
        const token = snapshot.ask?.token
        if (!answer || !token) return
        void answerAsk(token, answer).then(() =>
          useChatStore.getState().markAskAnswered(token, answer),
        )
        return
      }
      if (next.target === 'context_compact') {
        if (session?.id) compactedSession.current = session.id
        useChatStore.getState().compactSession()
        return
      }
      if (next.target === 'open_review_or_preview') {
        window.dispatchEvent(new CustomEvent(PREVIEW_OPEN_EVENT, { detail: { tab: 'git' } }))
      }
    })
  }, [
    enabled,
    mode,
    runState,
    contextPercent,
    repairVisible,
    session,
    cancel,
    highlight,
    log,
  ])

  // The visible countdown number.
  useEffect(() => {
    if (deadline === null) {
      setRemaining(null)
      return
    }
    const tick = () => setRemaining(Math.max(0, deadline - Date.now()))
    tick()
    const id = setInterval(tick, 100)
    return () => clearInterval(id)
  }, [deadline])

  return { finding, countdownRemaining: remaining, receipts, cancel, focus }
}
