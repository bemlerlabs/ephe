/**
 * One occupancy number for every surface that shows context.
 *
 * QA-0.1.11 (F8) found the status bar and the composer's ring contradicting
 * each other in the same window: the bar read the server's mirror under the
 * server's window, the ring estimated the messages under 32 768 — two
 * numerators and two denominators, so "62 % used" could sit above a ring
 * showing a third. The derivation now lives here and both read it.
 */
import { useEffect, useMemo, useState } from 'react'
import type { ChatMessage } from '@/types'
import { getContextBudget, type ContextBudget } from './api'
import { estimateContextUsage, type ContextUsage } from './contextMeter'
import { useChatStore } from '@/store/chatStore'

export interface ContextOccupancy {
  budget: ContextBudget | null
  window?: number
  /** The offline estimate — still the per-role breakdown's source. */
  usage: ContextUsage
  percent: number
  tokens: number
  remaining: number
  tokenizer?: string
}

export function useContextOccupancy(
  messages: ChatMessage[] | undefined,
  windowTokens?: number,
  sessionId?: string,
): ContextOccupancy {
  // A model/provider switch invalidates the cached server window: the surfaces
  // re-fetch, but until the answer arrives the old denominator must not sit
  // beside the new engine's messages — the offline estimate takes over instead.
  // Two channels carry the switch: the 'ephe:model-changed' event (composer chip)
  // and the caller's own window prop (the settings page knows the number from the
  // switch response). Nothing else moves this value; a mount with a settled prop
  // keeps the offline estimate stable, which is what the meter tests pin.
  const [budget, setBudget] = useState<ContextBudget | null>(null)
  const [seenWindow, setSeenWindow] = useState(windowTokens)
  useEffect(() => {
    const onModelChanged = () => setBudget(null)
    window.addEventListener('ephe:model-changed', onModelChanged)
    return () => window.removeEventListener('ephe:model-changed', onModelChanged)
  }, [])
  useEffect(() => {
    if (windowTokens !== seenWindow) {
      setSeenWindow(windowTokens)
      setBudget(null)
    }
  }, [windowTokens, seenWindow])
  // Order: the server's own count first, then the caller's window — one
  // denominator at a time. A model switch clears the cached budget below, so the
  // estimate over the caller's (fresh) window answers while the re-fetch runs.
  const effectiveWindow = budget?.window_tokens || windowTokens
  const usage = useMemo(
    () => estimateContextUsage(messages || [], effectiveWindow),
    [messages, effectiveWindow],
  )

  useEffect(() => {
    let cancelled = false
    getContextBudget(sessionId)
      .then((b) => {
        if (!cancelled) setBudget(b)
      })
      .catch(() => {
        if (!cancelled) setBudget(null)
      })
    return () => {
      cancelled = true
    }
  }, [sessionId, messages?.length, seenWindow])

  // P5-1 measurement order: 1) the real server count (rest mirror filled),
  // 2) the measured usage balance of the last turn, 3) the offline estimate.
  const turnUsage = useChatStore((s) => s.lastTurnUsage)
  const measuredTotal = (turnUsage?.in ?? 0) + (turnUsage?.out ?? 0)
  const mirrorLive = budget != null && budget.message_count > 0
  const percent = Math.min(
    mirrorLive
      ? budget.percent
      : measuredTotal > 0 && effectiveWindow
        ? Math.round((measuredTotal / effectiveWindow) * 100)
        : usage.percent,
    100,
  )
  const tokens = mirrorLive
    ? budget.estimated_tokens
    : measuredTotal > 0
      ? measuredTotal
      : usage.tokens.total
  // R6/S2 + F8: "free" has to come from the same count as the percent and the
  // used figure — in the measured branch too, not just beside the server mirror.
  const countedLive = mirrorLive || (measuredTotal > 0 && !!effectiveWindow)
  const remaining =
    countedLive && effectiveWindow ? Math.max(0, effectiveWindow - tokens) : usage.remaining

  return {
    budget,
    window: effectiveWindow,
    usage,
    percent,
    tokens,
    remaining,
    tokenizer: budget?.tokenizer,
  }
}
