'use client'

/**
 * R2-A: the one data path to the memory facts.
 *
 * Before: the panel tab (`agent/tabsMemory.tsx`) and the settings section
 * (`settings/model/sections-memory.tsx`) listed the same inventory through two
 * own chains — one with trash, correction and provider, the other with 50
 * entries and a delete button. Two addresses for one list are not a deep link
 * but two half truths.
 *
 * The hook knows nothing about layout. It fetches what the API offers and says
 * honestly when a part is missing: no stats payload means "knowing less", and a
 * store that does not answer means "cannot be read" — never an empty inventory.
 */
import { useCallback, useEffect, useState } from 'react'
import {
  getMemoryStats,
  listDeletedMemory,
  listMemory,
  searchMemory,
  type MemoryStats,
} from '@/lib/api'
import { useDebouncedValue } from '@/lib/useDebouncedValue'
import { formatNumber } from '@/lib/dateLocale'
import type { MemoryRow } from '@/components/dashboard/agent/memoryRowCard'

export type MemoryView = 'live' | 'trash'

/**
 * Three answers, and B1 was exactly their collapse: `unreachable` has no rows
 * because none were readable, `ready` with `rows.length === 0` has none because
 * the store holds none.
 */
export type MemoryStoreState = 'loading' | 'ready' | 'unreachable'

/** Compare without accents like the store's lexical leg: "zurich" finds "Zürich". — language-gate: ignore (the quoted pair is the fold's example datum, not prose) */
export function foldText(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
}

/**
 * What the count line of the inventory says. A query never comes back with nothing:
 * the store ranks its whole inventory and answers with the closest `top_k`, and the
 * measured score band of a nonsense word lies inside the band of a real one
 * (0.567–0.585 against 0.549–0.589 over the same 66 facts), so no floor is statable
 * from here. The line names the list it is showing instead.
 */
export function memoryCountLine(
  query: string,
  shown: number,
  stats: MemoryStats | null,
  t: (k: string, o?: Record<string, unknown>) => string,
  language?: string,
): string | number {
  if (!query.trim() || !stats) return shown
  return t('memory.searchRanking', {
    shown: formatNumber(shown, language),
    total: formatNumber(stats.total, language),
  })
}

export interface MemoryFacts {
  rows: MemoryRow[]
  stats: MemoryStats | null
  view: MemoryView
  query: string
  /** The field holds a word the request was not made for yet. */
  pending: boolean
  state: MemoryStoreState
  /** The technical answer of the store that stayed silent, as the route sent it. */
  reason: string
  /**
   * Wave 10: whether the active store keeps a deleted entry at all, as the trash
   * route reports it. `true` while unknown — a backend that predates the field
   * must not lose its restore control.
   */
  restoreSupported: boolean
  /** Why not, in the store's own line; empty when restore is possible. */
  restoreDetail: string
  setView: (view: MemoryView) => void
  setQuery: (query: string) => void
  reload: () => void
}

export function useMemoryFacts(limit = 100): MemoryFacts {
  const [rows, setRows] = useState<MemoryRow[]>([])
  const [stats, setStats] = useState<MemoryStats | null>(null)
  const [view, setView] = useState<MemoryView>('live')
  const [query, setQuery] = useState('')
  const heldQuery = useDebouncedValue(query)
  const [state, setState] = useState<MemoryStoreState>('loading')
  const [reason, setReason] = useState('')
  // Wave 10: the trash route is the authority on whether a restore can work at
  // all (`restore_supported` + `detail`). Unknown defaults to supported, so a
  // backend without the field keeps the old contract.
  const [restoreSupported, setRestoreSupported] = useState(true)
  const [restoreDetail, setRestoreDetail] = useState('')
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let cancelled = false
    setState('loading')
    setReason('')
    const needle = heldQuery.trim() ? foldText(heldQuery.trim()) : ''
    const read: Promise<MemoryRow[]> =
      view === 'trash'
        ? listDeletedMemory(limit).then((r) => {
            setRestoreSupported(r.restore_supported !== false)
            setRestoreDetail(r.detail ?? '')
            return (
              needle ? r.entries.filter((e) => foldText(e.text).includes(needle)) : r.entries
            ).map((e) => ({ id: e.id, text: e.text, metadata: e.metadata ?? {} }))
          })
        : needle
          ? searchMemory(heldQuery.trim(), limit).then((r) =>
              r.results.map((x) => ({ id: x.id, text: x.text, metadata: x.metadata ?? {} })),
            )
          : listMemory(limit).then((r) =>
              r.entries.map((e) => ({ id: e.id, text: e.text, metadata: e.metadata ?? {} })),
            )
    read
      .then((next) => {
        if (cancelled) return
        setRows(next)
        setState('ready')
      })
      .catch((e: unknown) => {
        if (cancelled) return
        setRows([])
        setReason(e instanceof Error ? e.message : String(e))
        setState('unreachable')
      })
    return () => {
      cancelled = true
    }
  }, [view, heldQuery, limit, nonce])

  const loadStats = useCallback(async () => {
    try {
      setStats(await getMemoryStats())
    } catch {
      setStats(null)
    }
  }, [])

  useEffect(() => {
    void loadStats()
  }, [loadStats, nonce])

  return {
    rows,
    stats,
    view,
    query,
    pending: query.trim() !== heldQuery.trim(),
    state,
    reason,
    restoreSupported,
    restoreDetail,
    setView,
    setQuery,
    reload: () => setNonce((n) => n + 1),
  }
}

/** The types and sources the store really writes (wave D). */
export const MEMORY_TYPES = ['semantic', 'episodic', 'procedural'] as const

export function memoryTypeOf(row: MemoryRow): string {
  const v = row.metadata.memory_type ?? row.metadata.type
  return typeof v === 'string' ? v : ''
}

export function memorySourceOf(row: MemoryRow): string {
  const v = row.metadata.source
  return typeof v === 'string' ? v : ''
}

/** A spelling that supersedes an older fact is a correction. */
export function memorySupersedes(row: MemoryRow): string {
  const v = row.metadata.supersedes
  return typeof v === 'string' ? v : ''
}

/**
 * The three write paths on the inventory — edit, correct, forget —
 * and the restore. Written once, because the panel tab and the page
 * would otherwise hold two opinions about the same word "Bearbeiten". // language-gate: ignore (the German edit label the UI renders, locales/de.json:64 edit — a noun the wide net does not list)
 */
import { toastBus } from '@/lib/toast'
import { useTranslation } from 'react-i18next'
import {
  deleteMemoryEntry,
  restoreMemoryEntry,
  supersedeMemoryEntry,
  updateMemoryEntry,
} from '@/lib/api'
import type { WriteKind } from '@/components/dashboard/agent/memoryRowCard'

export function useMemoryActions(reload: () => void) {
  const { t } = useTranslation()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  const closeEdit = () => {
    setEditingId(null)
    setDraft('')
  }

  const startEdit = (row: MemoryRow) => {
    setEditingId(row.id)
    setDraft(row.text)
  }

  const commit = async (row: MemoryRow, kind: WriteKind) => {
    const next = draft.trim()
    // An empty value would not be an edit but silent data destruction.
    if (!next) return
    setSaving(true)
    try {
      if (kind === 'supersede') await supersedeMemoryEntry(row.id, next)
      else await updateMemoryEntry(row.id, next)
      toastBus.success(
        kind === 'supersede' ? t('agentPanel.memorySupersedeDone') : t('agentPanel.memoryUpdated'),
      )
      closeEdit()
      reload()
    } catch {
      toastBus.error(t('agentPanel.memoryUpdateFailed'))
    } finally {
      setSaving(false)
    }
  }

  const remove = async (row: MemoryRow) => {
    try {
      await deleteMemoryEntry(row.id)
      reload()
    } catch {
      toastBus.error(t('common.changeFailed'))
    }
  }

  const restore = async (row: MemoryRow) => {
    try {
      await restoreMemoryEntry(row.id)
      toastBus.success(t('agentPanel.memoryRestored'))
      reload()
    } catch {
      toastBus.error(t('common.changeFailed'))
    }
  }

  return { editingId, draft, saving, setDraft, startEdit, closeEdit, commit, remove, restore }
}

/** A row belongs to the lineage when it is a correction itself or has
    received one — both directions stand in the metadata. */
export function memoryIsCorrection(row: MemoryRow): boolean {
  return memorySupersedes(row) !== '' || typeof row.metadata.superseded_by === 'string'
}
