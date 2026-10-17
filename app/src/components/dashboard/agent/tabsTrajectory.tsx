'use client'

import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Loader2, Pause, Play } from 'lucide-react'
import { useChatStore } from '@/store/chatStore'
import { getTrajectory, listArtifacts } from '@/lib/api'
import type { TrajTurn } from '@/lib/api'
import { diffTurns } from '@/lib/api/trajectory'
import { TrajectoryHeader } from './trajectoryHeader'
import { TurnHead, TurnSteps } from './trajectoryParts'
import { TurnMemories } from './turnMemories'

export function TrajectoryTab() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const sessionId = useChatStore((s) => s.activeSessionId)
  const [turns, setTurns] = useState<TrajTurn[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const turnsRef = useRef<TrajTurn[] | null>(null)
  turnsRef.current = turns
  const [nonce, setNonce] = useState(0)
  const [searchOpen, setSearchOpen] = useState(false)
  const [query, setQuery] = useState('')
  const deferredQuery = useDeferredValue(query)
  const [onlyUsage, setOnlyUsage] = useState(false)
  const [allExpanded, setAllExpanded] = useState(false)
  // N5: the Δ toggle — deltas per turn.
  const [deltaOn, setDeltaOn] = useState(false)
  // P6/A6: expanded step details ("ti-n") and code blocks opened with ⤢
  // ("ti-n-in|out") — two separate sets, so that ⤢ does not collapse the row too.
  const [openSteps, setOpenSteps] = useState<Set<string>>(new Set())
  const [openCode, setOpenCode] = useState<Set<string>>(new Set())
  const scrollRef = useRef<HTMLDivElement>(null)
  // N3′: the active step of the keyboard navigation.
  const [activeStep, setActiveStep] = useState<string | null>(null)
  // Live in an open turn: the ticker keeps the timeline fresh for as long as the
  // last turn has no measured duration_ms yet.
  const [tick, setTick] = useState(0)
  // A3 backwards: an assignment's files hang off its turn_id, not off its step
  // list — one task can have borne several, and a tool without a file result borne
  // none. So the index counts here, not the timeline, and it counts by root_id:
  // three versions are one file.
  const [filesByTurn, setFilesByTurn] = useState<Record<string, number>>({})
  const pullFiles = useCallback(() => {
    if (!sessionId) {
      setFilesByTurn({})
      return
    }
    listArtifacts({ session_id: sessionId, limit: 500 })
      .then(({ artifacts }) => {
        const roots: Record<string, Set<string>> = {}
        for (const a of artifacts) {
          if (!a.turn_id) continue // cards from before the chain belong to no assignment
          ;(roots[a.turn_id] ??= new Set()).add(a.root_id || a.id)
        }
        setFilesByTurn(Object.fromEntries(Object.entries(roots).map(([k, v]) => [k, v.size])))
      })
      .catch(() => setFilesByTurn({}))
  }, [sessionId])
  useEffect(() => {
    if (!sessionId) {
      setTurns([])
      return
    }
    const pull = () =>
      getTrajectory(sessionId)
        .then((r) => {
          if (JSON.stringify(r.turns) !== JSON.stringify(turnsRef.current)) {
            setTurns(r.turns)
            pullFiles()
          }
          setError(null)
        })
        .catch((e: unknown) => {
          setError(e instanceof Error ? e.message : String(e))
        })
    pull()
    pullFiles()
    const id = setInterval(() => {
      setTick((v) => v + 1)
      pull()
    }, 600)
    return () => clearInterval(id)
  }, [sessionId, nonce, pullFiles])
  void tick
  // allExpanded only takes effect from A6 (section expansion); bound to the
  // buttons already as a placeholder ref so the header state stays stable.
  void allExpanded

  // Summary (ref-12): count every step, sum usage IN/OUT, dedup models.
  const summary = useMemo(() => {
    const list = turns ?? []
    let calls = 0
    let tokens = 0
    const models: string[] = []
    for (const turn of list) {
      calls += turn.steps.length
      if (turn.model && !models.includes(turn.model)) models.push(turn.model)
      for (const s of turn.steps) {
        tokens += s.usage?.in ?? 0
        tokens += s.usage?.out ?? 0
      }
    }
    return { calls, tokens, models: models.join(', ') }
  }, [turns])

  // Search: index of the first turn with hits in the deferred query.
  const matchIndex = useMemo(() => {
    const q = deferredQuery.trim().toLowerCase()
    if (!q) return -1
    return (turns ?? []).findIndex((turn) =>
      turn.steps.some((s) => s.title.toLowerCase().includes(q) || s.type.toLowerCase().includes(q)),
    )
  }, [turns, deferredQuery])

  // Filter pill: only steps with usage (the token axis); search: only turns with
  // a match — both applied to the same visible list, the rest stays hidden.
  const visibleTurns = useMemo(() => {
    let list = turns ?? []
    if (onlyUsage) {
      list = list
        .map((turn) => ({ ...turn, steps: turn.steps.filter((s) => s.usage) }))
        .filter((turn) => turn.steps.length > 0)
    }
    const q = deferredQuery.trim().toLowerCase()
    if (q) {
      list = list.filter((turn) =>
        turn.steps.some(
          (s) => s.title.toLowerCase().includes(q) || s.type.toLowerCase().includes(q),
        ),
      )
    }
    return list
  }, [turns, onlyUsage, deferredQuery])

  // N5: deltas over the visible list (index == ti in the header rows).
  const deltas = useMemo(() => (deltaOn ? diffTurns(visibleTurns) : null), [deltaOn, visibleTurns])

  // N3′: the sequential step order of the visible turns ("ti-n") used as the
  // cursor path for keyboard navigation.
  const stepSeq = useMemo(
    () => visibleTurns.flatMap((turn, ti) => turn.steps.map((s) => `${ti}-${s.n}`)),
    [visibleTurns],
  )
  const focusStep = useCallback(
    (idx: number) => {
      const key = stepSeq[idx]
      if (!key) return
      setActiveStep(key)
      document
        .querySelector(`[data-trajectory-step="${key}"]`)
        ?.scrollIntoView({ block: 'nearest' })
    },
    [stepSeq],
  )

  // 2026 task focus: replay playback — play runs the timeline step by step (the
  // cursor through focusStep), pause holds, and the end stops it automatically.
  const [playing, setPlaying] = useState(false)
  const playIdx = useRef(0)
  useEffect(() => {
    if (!playing) return
    const id = window.setInterval(() => {
      if (playIdx.current >= stepSeq.length) {
        setPlaying(false)
        playIdx.current = 0
        return
      }
      focusStep(playIdx.current)
      playIdx.current += 1
    }, 900)
    return () => window.clearInterval(id)
  }, [playing, stepSeq.length, focusStep])
  const togglePlayback = useCallback(() => {
    if (playing) {
      setPlaying(false)
      return
    }
    playIdx.current = 0
    setPlaying(true)
  }, [playing])
  const toggleStepDetail = useCallback((stepKey: string) => {
    setOpenSteps((prev) => {
      const next = new Set(prev)
      if (next.has(stepKey)) next.delete(stepKey)
      else next.add(stepKey)
      return next
    })
  }, [])
  const toggleCode = useCallback((codeKey: string) => {
    setOpenCode((prev) => {
      const next = new Set(prev)
      if (next.has(codeKey)) next.delete(codeKey)
      else next.add(codeKey)
      return next
    })
  }, [])
  // The click leads to the workbench page with the same scope the card itself
  // takes (?turn=) — the list stays a source, never a second view.
  const openTurnFiles = useCallback(
    (turnId: string) => navigate(`/artifacts?turn=${encodeURIComponent(turnId)}`),
    [navigate],
  )
  // N3′: arrow keys move the active step, Home/End jump to the edges,
  // Enter/Space opens the sections, Esc only clears the selection —
  // so the unshortened Esc is what closes the pane (panel listener on window).
  const onTimelineKey = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      const idx = activeStep == null ? -1 : stepSeq.indexOf(activeStep)
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        focusStep(idx < 0 ? 0 : Math.min(idx + 1, stepSeq.length - 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        focusStep(idx < 0 ? 0 : Math.max(idx - 1, 0))
      } else if (e.key === 'Home') {
        e.preventDefault()
        focusStep(0)
      } else if (e.key === 'End') {
        e.preventDefault()
        focusStep(stepSeq.length - 1)
      } else if (e.key === 'Enter' || e.key === ' ') {
        if (!activeStep) return
        e.preventDefault()
        e.stopPropagation()
        toggleStepDetail(activeStep)
      } else if (e.key === 'Escape') {
        if (!activeStep) return
        e.stopPropagation()
        setActiveStep(null)
      }
    },
    [activeStep, stepSeq, focusStep, toggleStepDetail],
  )

  // P6/A4: timeline virtualisation on the reference layout — only the window plus
  // overscan stands in the DOM. jsdom reports offsetHeight 0; falling back to the
  // estimate keeps the range from growing to the full list size.
  const rowVirtualizer = useVirtualizer<HTMLElement, HTMLDivElement>({
    count: visibleTurns.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 240,
    overscan: 3,
    measureElement: (el) => el?.offsetHeight || 240,
  })
  const virtualItems = rowVirtualizer.getVirtualItems()
  const totalSize = rowVirtualizer.getTotalSize()
  const topSpacer = virtualItems[0]?.start ?? 0
  const lastVirtual = virtualItems[virtualItems.length - 1]
  const bottomSpacer = lastVirtual ? Math.max(0, totalSize - lastVirtual.end) : 0

  return (
    <div className="flex-1 min-h-0 flex flex-col" data-testid="trajectory-view">
      <TrajectoryHeader
        turns={turns}
        summary={summary}
        searchOpen={searchOpen}
        query={query}
        matchIndex={matchIndex}
        deltaOn={deltaOn}
        scrollRef={scrollRef}
        onToggleSearch={() => setSearchOpen((v) => !v)}
        onToggleFilter={() => setOnlyUsage((v) => !v)}
        onToggleExpand={() => setAllExpanded((v) => !v)}
        onRefresh={() => setNonce((n) => n + 1)}
        onToggleDelta={() => setDeltaOn((v) => !v)}
        onQueryChange={setQuery}
      />
      {/* Replay bar: plays the step timeline (the agentPanel.replayPlay pattern) */}
      <div className="flex items-center gap-2 px-3 pt-2" data-testid="trajectory-playback">
        <button
          type="button"
          onClick={togglePlayback}
          disabled={!stepSeq.length}
          aria-label={playing ? t('agentPanel.replayPause') : t('agentPanel.replayPlay')}
          title={playing ? t('agentPanel.replayPause') : t('agentPanel.replayPlay')}
          data-testid="trajectory-play"
          className="inline-flex items-center gap-1.5 rounded-md border border-hairline px-2 py-1 text-ui-xs text-ink-soft hover:text-foreground hover:bg-surface-interactive transition-colors disabled:opacity-40"
        >
          {playing ? (
            <Pause className="h-3 w-3" aria-hidden="true" />
          ) : (
            <Play className="h-3 w-3" aria-hidden="true" />
          )}
          {playing ? t('agentPanel.replayPause') : t('agentPanel.replayPlay')}
        </button>
        {playing && (
          <span className="text-ui-xs text-ink-faint">
            {t('agentPanel.replayStep', {
              current: Math.min(playIdx.current + 1, stepSeq.length),
              total: stepSeq.length,
            })}
          </span>
        )}
      </div>
      <div
        ref={scrollRef}
        tabIndex={0}
        onKeyDown={onTimelineKey}
        className="flex-1 min-h-0 overflow-y-auto p-3 outline-none"
      >
        {error ? (
          <div className="flex flex-col items-start gap-2 px-1 py-1">
            <p role="alert" className="text-ui-xs text-destructive font-mono">
              {error}
            </p>
            <button
              type="button"
              data-testid="trajectory-retry"
              onClick={() => setNonce((n) => n + 1)}
              className="inline-flex min-h-7 items-center rounded-md border border-hairline px-2.5 py-1 text-ui-xs text-ink-soft hover:text-foreground hover:bg-surface transition-colors max-lg:min-h-11"
            >
              {t('agentPanel.retry')}
            </button>
          </div>
        ) : !sessionId || turns === null ? (
          <Loader2 className="h-4 w-4 animate-spin text-brand/50" />
        ) : turns.length === 0 ? (
          <p
            data-testid="trajectory-empty"
            className="flex flex-col items-center gap-1 px-4 py-10 text-center text-ui-xs text-ink-faint"
          >
            {t('agentPanel.trajectoryEmpty')}
          </p>
        ) : (
          <ol
            data-testid="trajectory-list"
            className="grid grid-cols-[max-content_minmax(0,1fr)_auto] gap-x-2"
          >
            {/* P6/A4: a ghost li reserves the number column (max-content), so that
                every turn shares the same indentation. */}
            <li
              data-testid="trajectory-ghost"
              aria-hidden="true"
              className="invisible font-mono text-ui-sm"
            >
              00
            </li>
            {topSpacer > 0 && (
              <li aria-hidden="true" className="col-span-full" style={{ height: topSpacer }} />
            )}
            {virtualItems.map((vi) => {
              const ti = vi.index
              const turn = visibleTurns[ti]
              if (!turn) return null
              return (
                <article
                  key={vi.key}
                  ref={rowVirtualizer.measureElement}
                  data-index={ti}
                  data-trajectory-call
                  data-testid={`trajectory-turn-${ti}`}
                  className="col-span-full grid grid-cols-subgrid"
                >
                  <TurnHead
                    ti={ti}
                    turn={turn}
                    delta={deltas?.[ti]}
                    fileCount={turn.turn_id ? (filesByTurn[turn.turn_id] ?? 0) : 0}
                    onOpenFiles={openTurnFiles}
                  />
                  {/* G7: the stored facts this turn's prompt carried, right under
                      the header that names the turn — each one correctable in place. */}
                  <TurnMemories
                    ti={ti}
                    memories={turn.memories}
                    reload={() => setNonce((n) => n + 1)}
                  />
                  <TurnSteps
                    ti={ti}
                    turn={turn}
                    allExpanded={allExpanded}
                    openSteps={openSteps}
                    openCode={openCode}
                    activeStep={activeStep}
                    onStepClick={(stepKey) => {
                      setActiveStep(stepKey)
                      toggleStepDetail(stepKey)
                    }}
                    onToggleCode={toggleCode}
                  />
                </article>
              )
            })}
            {bottomSpacer > 0 && (
              <li aria-hidden="true" className="col-span-full" style={{ height: bottomSpacer }} />
            )}
          </ol>
        )}
      </div>
    </div>
  )
}
