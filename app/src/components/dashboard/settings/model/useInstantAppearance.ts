'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { DeepSection } from '@/types'
import type { TabKey } from '../types'
import { countDeepChangesIn } from './bounds'

export type InstantAppearanceStatus = 'idle' | 'saving' | 'saved' | 'error'

type Draft = Record<string, Record<string, string | number | boolean>>
const SECTION = 'appearance'
const DEBOUNCE_MS = 500
const SAVED_MS = 2000

function baselineValues(sections: DeepSection[] | null): Record<string, string | number | boolean> {
  const sec = (sections ?? []).find((s) => s.key === SECTION)
  const out: Record<string, string | number | boolean> = {}
  for (const f of sec?.fields ?? []) out[f.key] = f.value ?? f.default ?? ''
  return out
}

/**
 * The one instant surface: appearance rows persist through the register's own
 * save path, debounced, and roll back to the last persisted value when the write
 * fails. The footer keeps every other section's draft untouched.
 */
export function useInstantAppearance({
  isOpen,
  activeTab,
  deepDraft,
  deepSections,
  setDeepDraft,
  saveDeepSettings,
}: {
  isOpen: boolean
  activeTab: TabKey
  deepDraft: Draft
  deepSections: DeepSection[] | null
  setDeepDraft: Dispatch<SetStateAction<Draft>>
  saveDeepSettings: (scope?: string[]) => Promise<{ ok: boolean; detail?: string }>
}) {
  const [status, setStatus] = useState<InstantAppearanceStatus>('idle')
  const [instantError, setInstantError] = useState<string | undefined>()

  const draft = useRef(deepDraft)
  const sections = useRef(deepSections)
  const save = useRef(saveDeepSettings)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mounted = useRef(true)
  const saving = useRef(false)
  const queued = useRef(false)

  draft.current = deepDraft
  sections.current = deepSections
  save.current = saveDeepSettings

  const flush = useCallback(async () => {
    if (timer.current) {
      clearTimeout(timer.current)
      timer.current = null
    }
    if (countDeepChangesIn(sections.current, draft.current, [SECTION]) === 0) return
    if (saving.current) {
      queued.current = true
      return
    }
    saving.current = true
    if (mounted.current) {
      setStatus('saving')
      setInstantError(undefined)
    }
    const result = await save.current([SECTION])
    saving.current = false
    if (!mounted.current) {
      queued.current = false
      return
    }
    if (result.ok) {
      setStatus('saved')
      if (savedTimer.current) clearTimeout(savedTimer.current)
      savedTimer.current = setTimeout(() => {
        if (mounted.current) setStatus('idle')
      }, SAVED_MS)
    } else {
      setDeepDraft((prev) => ({ ...prev, [SECTION]: baselineValues(sections.current) }))
      setStatus('error')
      setInstantError(result.detail)
    }
    if (queued.current) {
      queued.current = false
      void flush()
    }
  }, [setDeepDraft])

  const signature = JSON.stringify(deepDraft[SECTION] ?? {})

  useEffect(() => {
    if (!isOpen) return
    if (countDeepChangesIn(deepSections, deepDraft, [SECTION]) === 0) return
    setStatus('idle')
    setInstantError(undefined)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      timer.current = null
      void flush()
    }, DEBOUNCE_MS)
    return () => {
      if (timer.current) {
        clearTimeout(timer.current)
        timer.current = null
      }
    }
  }, [signature, isOpen, flush, deepSections, deepDraft])

  const wasOpen = useRef(isOpen)
  useEffect(() => {
    if (wasOpen.current && !isOpen) void flush()
    wasOpen.current = isOpen
  }, [isOpen, flush])

  const previousTab = useRef(activeTab)
  useEffect(() => {
    if (previousTab.current !== activeTab) {
      previousTab.current = activeTab
      void flush()
    }
  }, [activeTab, flush])

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      if (savedTimer.current) clearTimeout(savedTimer.current)
      void flush()
    }
  }, [flush])

  return { instantStatus: status, instantError }
}
